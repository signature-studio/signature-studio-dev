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
  - --wide: emcc が `incompatible pointer types passing 'int[N]' to parameter of type 'int16_t *'` (引数)・
    `assigning to 'int16_t *' (aka 'short *') from 'int[N]'`・`initializing 'int16_t *' (aka 'short *') with an expression of type 'int[N]'`
    (代入・初期化、#2071) と報告した位置だけ、`L"..."` を `(int16_t *)u"..."` に直す。Win64 の wchar_t は 2B で、PE 内の文字列は
    UTF-16LE (REPORT §9)。宣言側の `int16_t *` は Win32 の LPCWSTR と一致するので残し、呼出側だけを直す。
    `L"..."` は wasm32 で 4B 単位になり、同じ宣言に渡すとバイト列が変わる。全コードポイントが 1 単位 (BMP・非代理) の
    literal だけ直し、それ以外は触らない。
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
WIDE_RE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): error: incompatible pointer types "
    r"(?:passing 'int\[(?P<n>\d+)\]' to parameter of type 'int16_t \*'"
    r"|(?:assigning to|initializing) 'int16_t \*' \(aka 'short \*'\) (?:from|with an expression of type) 'int\[(?P<n2>\d+)\]')",
    re.M,
)
ESC = {"n": 10, "r": 13, "t": 9, "\\": 92, '"': 34, "'": 39, "0": 0}


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


def wide_positions(path, cc="emcc"):
    p = subprocess.run(
        [cc, "-c", "-fsyntax-only", "-w", "-ferror-limit=0", path],
        capture_output=True, text=True,
    )
    pos = set()
    for m in WIDE_RE.finditer(p.stderr + p.stdout):
        if os.path.basename(m.group("file")) == os.path.basename(path):
            units = int(m.group("n") or m.group("n2"))
            pos.add((int(m.group("line")), int(m.group("col")), units))
    return pos


def wide_to_utf16(line, col):
    if line[col - 1:col + 1] != 'L"':
        return None
    j = col + 1
    while j < len(line) and line[j] != '"':
        if line[j] == "\\":
            if j + 1 >= len(line) or line[j + 1] not in ESC:
                return None
            j += 2
        elif ord(line[j]) >= 0x80 or line[j] < " ":
            return None
        else:
            j += 1
    if j >= len(line):
        return None
    return line[:col - 1] + "(int16_t *)u" + line[col:j + 1] + line[j + 1:]


def lit_units(line, q):
    j = q + 1
    k = 0
    while j < len(line) and line[j] != '"':
        j += 2 if line[j] == "\\" else 1
        k += 1
    return k if j < len(line) else -1


def wide_at_size(line, units):
    cands = [
        c for c in range(len(line) - 1)
        if line[c:c + 2] == 'L"' and (c == 0 or not (line[c - 1].isalnum() or line[c - 1] == "_"))
        and lit_units(line, c + 1) == units - 1
    ]
    return cands[0] + 1 if len(cands) == 1 else None


def wrap_wide(text, pos):
    out = text.split("\n")
    n = 0
    skipped = 0
    for ln, col, units in sorted(pos, reverse=True):
        new = wide_to_utf16(out[ln - 1], col)
        if new is None:
            c = wide_at_size(out[ln - 1], units)
            if c is not None:
                new = wide_to_utf16(out[ln - 1], c)
        if new is None:
            skipped += 1
            continue
        out[ln - 1] = new
        n += 1
    return "\n".join(out), n, skipped


def main():
    args = sys.argv[1:]
    int_ptr = "--int-ptr" in args
    wide = "--wide" in args
    args = [a for a in args if a not in ("--int-ptr", "--wide")]
    src, dst = args[0], args[1]
    os.makedirs(dst, exist_ok=True)
    total = 0
    wrapped = 0
    widened = 0
    widen_skipped = 0
    for f in sorted(os.listdir(src)):
        if not f.endswith(".c"):
            continue
        path = os.path.join(src, f)
        with open(path, errors="replace") as fh:
            text = fh.read()
        out, missing = repair_decls(text)
        total += len(missing)
        if wide:
            tmp = os.path.join(dst, f)
            with open(tmp, "w") as fh:
                fh.write(out)
            out, n, sk = wrap_wide(out, wide_positions(tmp))
            widened += n
            widen_skipped += sk
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
    if wide:
        print("wide_widened", widened, "wide_skipped", widen_skipped)


if __name__ == "__main__":
    main()
