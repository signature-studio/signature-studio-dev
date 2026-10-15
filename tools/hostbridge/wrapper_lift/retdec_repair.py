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
  - --struct (#2853): `__asm_*` helper を `int64_t NAME();` と宣言すると、RetDec の変数型 `struct structN` への代入
    (`assigning to 'struct structN' from 'int64_t'`) と、その戻り値の `.eN` 参照 (`member reference base type 'int64_t'`) が
    emcc で落ちる。代入先の struct 型 (同じ file の宣言より前に定義された struct) を宣言に写す。代入が無く `.eN` だけの場合は、
    その member を全て持つ struct のうち、定義の順で最初のもの (候補の member 型・名前が全て同一のときだけ)。
    helper の全呼出しが診断行にあり、直した後の emcc 診断が直す前の行の部分集合のときだけ採る (新しい error 行が出たら戻す)。
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
ASSIGN_STRUCT_RE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): error: assigning to 'struct (?P<tag>\w+)' from incompatible type 'int64_t'",
    re.M,
)
MEMBER_INT64_RE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?P<col>\d+): error: member reference base type 'int64_t' \(aka 'long long'\) is not a structure or union",
    re.M,
)
ERR_LINE_RE = re.compile(r"^(?P<file>[^:\n]+):(?P<line>\d+):\d+: (?:fatal )?error: ", re.M)
HELPER_RE = re.compile(r"\b(__asm_\w+)\s*\(")
STRUCT_RE = re.compile(r"^struct (\w+) \{\n(.*?)^\};", re.M | re.S)
MEMBER_DECL_RE = re.compile(r"^\s*(\w+) (\w+);", re.M)
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


def emcc_diag(path, cc="emcc"):
    p = subprocess.run(
        [cc, "-c", "-fsyntax-only", "-w", "-ferror-limit=0", path],
        capture_output=True, text=True,
    )
    return p.stderr + p.stdout


def file_diags(diag, path, rx):
    return [m for m in rx.finditer(diag) if os.path.basename(m.group("file")) == os.path.basename(path)]


def error_lines(diag, path):
    return {int(m.group("line")) for m in file_diags(diag, path, ERR_LINE_RE)}


def struct_defs(lines):
    text = "\n".join(lines)
    defs = {}
    for m in STRUCT_RE.finditer(text):
        layout = tuple(MEMBER_DECL_RE.findall(m.group(2)))
        defs[m.group(1)] = (text.count("\n", 0, m.start()) + 1, layout)
    return defs


def struct_helper_fixes(text, path, cc="emcc"):
    lines = text.split("\n")
    with open(path, "w") as fh:
        fh.write(text)
    diag = emcc_diag(path, cc)
    before = error_lines(diag, path)
    rec = {}
    found = [(m, "tag") for m in file_diags(diag, path, ASSIGN_STRUCT_RE)]
    found += [(m, "member") for m in file_diags(diag, path, MEMBER_INT64_RE)]
    for m, kind in found:
        ln = int(m.group("line"))
        names = set(HELPER_RE.findall(lines[ln - 1]))
        if len(names) != 1:
            continue
        r = rec.setdefault(names.pop(), {"tags": set(), "members": set(), "lines": set()})
        r["lines"].add(ln)
        if kind == "tag":
            r["tags"].add(m.group("tag"))
        else:
            mm = re.match(r"\.(\w+)", lines[ln - 1][int(m.group("col")) - 1:])
            r["members"].add(mm.group(1) if mm else "")
    defs = struct_defs(lines)
    changes = {}
    for h, r in rec.items():
        decl = "int64_t %s();" % h
        at = [i for i, l in enumerate(lines) if l == decl]
        uses = {i + 1 for i, l in enumerate(lines) if l != decl and re.search(r"\b%s\s*\(" % h, l)}
        if len(at) != 1 or not uses <= r["lines"] or len(r["tags"]) > 1:
            continue
        decl_line = at[0] + 1
        if r["tags"]:
            tag = r["tags"].pop()
            if tag not in defs or defs[tag][0] >= decl_line or not r["members"] <= {n for _, n in defs[tag][1]}:
                continue
        else:
            cands = sorted(
                (t for t, (pos, lay) in defs.items() if pos < decl_line and r["members"] <= {n for _, n in lay}),
                key=lambda t: defs[t][0],
            )
            if not cands or len({defs[t][1] for t in cands}) != 1:
                continue
            tag = cands[0]
        changes[at[0]] = "struct %s %s();" % (tag, h)
    if not changes:
        return text, 0, 0
    new = list(lines)
    for i, s in changes.items():
        new[i] = s
    new_text = "\n".join(new)
    with open(path, "w") as fh:
        fh.write(new_text)
    after = error_lines(emcc_diag(path, cc), path)
    if not after <= before:
        with open(path, "w") as fh:
            fh.write(text)
        return text, 0, 0
    return new_text, len(changes), len(before - after)


def main():
    args = sys.argv[1:]
    int_ptr = "--int-ptr" in args
    wide = "--wide" in args
    struct = "--struct" in args
    args = [a for a in args if a not in ("--int-ptr", "--wide", "--struct")]
    src, dst = args[0], args[1]
    os.makedirs(dst, exist_ok=True)
    total = 0
    wrapped = 0
    widened = 0
    widen_skipped = 0
    struct_fixed = 0
    struct_removed = 0
    for f in sorted(os.listdir(src)):
        if not f.endswith(".c"):
            continue
        path = os.path.join(src, f)
        with open(path, errors="replace") as fh:
            text = fh.read()
        out, missing = repair_decls(text)
        total += len(missing)
        if struct:
            out, n, rm = struct_helper_fixes(out, os.path.join(dst, f))
            struct_fixed += n
            struct_removed += rm
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
    if struct:
        print("struct_decl_fixed", struct_fixed, "struct_error_lines_removed", struct_removed)
    if int_ptr:
        print("int_ptr_wrapped", wrapped)
    if wide:
        print("wide_widened", widened, "wide_skipped", widen_skipped)


if __name__ == "__main__":
    main()
