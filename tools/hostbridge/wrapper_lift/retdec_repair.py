"""RetDec 分割 lift 出力 C の機械的修復 (#1339)。

使い方 (cwd=リポジトリルート):
  python3 tools/hostbridge/wrapper_lift/retdec_repair.py <in_dir> <out_dir>

修復内容 (1 ファイルごと・非破壊。入力は変更しない):
  - 本体で呼ばれているが宣言の無い helper (`__asm_*`・`llvm_*`・`__readgsqword` 等) を、
    関数プロトタイプの直前に `int64_t NAME();` (引数未指定の宣言) として補う。
    C の引数未指定宣言は呼び出し側の引数を検査しないため、引数型が不明でも宣言できる。
  - 対象外: int/pointer 混在・goto/label は触らない (REPORT §8 の未修復分)。
"""
import os
import re
import sys

CALL_RE = re.compile(r"\b(__asm_\w+|llvm_\w+|__read\w+|__write\w+|__cpuid\w*|__\w+_intrinsic)\s*\(")
DECL_MARK = "// ------------------- Function Prototypes --------------------"


def declared_names(text):
    return set(re.findall(r"\b(\w+)\s*\([^;{)]*\)\s*\{", text)) | set(re.findall(r"^[^\s/][^;]*?\b(\w+)\s*\([^;]*\)\s*;", text, re.M))


def repair(text):
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


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    total = 0
    for f in sorted(os.listdir(src)):
        if not f.endswith(".c"):
            continue
        with open(os.path.join(src, f), errors="replace") as fh:
            text = fh.read()
        out, missing = repair(text)
        total += len(missing)
        with open(os.path.join(dst, f), "w") as fh:
            fh.write(out)
    print("declared_helpers", total)


if __name__ == "__main__":
    main()
