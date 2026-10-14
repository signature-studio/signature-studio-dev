"""RetDec 分割 lift 出力 C の機械的修復 (#1339・#1521)。

使い方 (cwd=リポジトリルート):
  python3 tools/hostbridge/wrapper_lift/retdec_repair.py <in_dir> <out_dir>
  EM_CONFIG=<emsdk>/.emscripten PATH=<emsdk>/upstream/emscripten:$PATH \
    python3 tools/hostbridge/wrapper_lift/retdec_repair.py --int-ptr <in_dir> <out_dir>

修復内容 (1 ファイルごと・非破壊。入力は変更しない):
  - 本体で呼ばれているが宣言の無い helper (`__asm_*`・`llvm_*`・`__read*` 等) を、
    関数プロトタイプの直前に `int64_t NAME();` (引数未指定の宣言) として補う。
    C の引数未指定宣言は呼び出し側の引数を検査しないため、引数型が不明でも宣言できる。
  - --int-ptr: emcc が `-Wint-conversion` (整数型への `&x` 代入) と報告した行だけ、
    その行の `&` を `(int64_t)&` に包む。番地を 64bit 整数として保持する意図の代入で、
    値は変わらない。診断行の列を見るので、型を推測せず、コンパイラの判定に従う。
  - 対象外: goto/break・label は触らない。`break -> 0x...` は RetDec の制御フロー復元で、
    機械的に C の制御構造を変えると silent miscompile になる (docs/DEFECTS.md D19 型)。
"""
import os
import re
import subprocess
import sys

CALL_RE = re.compile(r"\b(__asm_\w+|llvm_\w+|__read\w+|__write\w+|__cpuid\w*|__\w+_intrinsic|__frontend_\w+)\s*\(")
DECL_MARK = "// ------------------- Function Prototypes --------------------"
INT_CONV_RE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): error: .*-Wint-conversion\]", re.M)


def declared_names(text):
    return set(re.findall(r"\b(\w+)\s*\([^;{)]*\)\s*\{", text)) | set(re.findall(r"^[^\s/][^;]*?\b(\w+)\s*\([^;]*\)\s*;", text, re.M))


def repair_decls(text):
    names = set(CALL_RE.findall(text))
    defined = declared_names(text)
    missing = sorted(n for n in names if n not in defined)
    if not missing:
        return text, []
    decls = "".join("int64_t %s();\n" % n for n in missing)
    if DECL_MARK in text:
        text = text.replace(DECL_MARK + "\n", DECL_MARK + "\n" + decls, 1)
    else:
        text = decls + text
    return text, missing


def int_conv_lines(path, cc="emcc"):
    p = subprocess.run(
        [cc, "-c", "-fsyntax-only", "-w", "-Wint-conversion", "-ferror-limit=0", path],
        capture_output=True, text=True,
    )
    lines = set()
    for m in INT_CONV_RE.finditer(p.stderr + p.stdout):
        if os.path.basename(m.group("file")) == os.path.basename(path):
            lines.add(int(m.group("line")))
    return lines


def wrap_amp(text, lines):
    out = text.split("\n")
    n = 0
    for ln in lines:
        s = out[ln - 1]
        new, k = re.subn(r"((?:=|\breturn)\s*)&(?=[\w(])", r"\1(int64_t)&", s, count=1)
        if k:
            out[ln - 1] = new
            n += 1
    return "\n".join(out), n


def main():
    args = sys.argv[1:]
    int_ptr = "--int-ptr" in args
    args = [a for a in args if a != "--int-ptr"]
    src, dst = args[0], args[1]
    os.makedirs(dst, exist_ok=True)
    total = 0
    wrapped = 0
    for f in sorted(os.listdir(src)):
        if not f.endswith(".c"):
            continue
        path = os.path.join(src, f)
        with open(path, errors="replace") as fh:
            text = fh.read()
        out, missing = repair_decls(text)
        total += len(missing)
        if int_ptr:
            tmp = os.path.join(dst, f)
            with open(tmp, "w") as fh:
                fh.write(out)
            lines = int_conv_lines(tmp)
            out, n = wrap_amp(out, lines)
            wrapped += n
        with open(os.path.join(dst, f), "w") as fh:
            fh.write(out)
    print("declared_helpers", total)
    if int_ptr:
        print("int_ptr_wrapped", wrapped)


if __name__ == "__main__":
    main()
