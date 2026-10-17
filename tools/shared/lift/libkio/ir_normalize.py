#!/usr/bin/env python3
# M2-5 補助: RetDec (LLVM 12 系) が吐く .ll を、現行 llvm (opaque pointer 時代,
# 本環境 clang 21 / emsdk clang-24) でそのまま読める形へ機械正規化するステージ。
#
# 対応する形 (RetDec v5.0 観測):
#   1. `%wide-string` 準借用 (`constant [Nx i16] %wide-string`) → zeroinitializer 化
#   2. 型付きポインタ (i32*, %T*, ptr* 等) → opaque `ptr` 統一
#      (bitcast pointer→pointer は no-op として除去: `ptr` 化後 LLVM は
#       型変換を concat 統合で受けるため)
#   3. `zext (i32 xor (i32 A, i32 A) to i64)` 型 constexpr の 0 化 (RetDec が
#      address identity を xor 0 で出す形)
#
#   4. (opt-in --drop-uselistorder) `  uselistorder ...` 行 (use-list 順序の
#      メタ情報・意味なし) を除く。emcc 6.0.12 の LLVM は読めず
#      `wrong number of indexes` で止まる (REPORT_CI §9-3・T-SH-164 #6235)
#
# python3 ir_normalize.py [--drop-uselistorder] IN.ll OUT.ll

import re
import sys

POINTER_TYPE = re.compile(r"i[0-9]+\*")
NAMED_PTR_TYPE = re.compile(r"%[\w.\-]+\*")


def normalize(text: str, drop_uselistorder: bool = False) -> str:
    if drop_uselistorder:
        text = re.sub(r"(?m)^  uselistorder [^\n]*\n", "", text)

    # (0) datalayout を wasm32 互換に差し替え (RetDec は x86-64 の datalayout
    #     のまま出すため wasm バックエンドの MachineFunction 作成でいずれも致命)
    text = re.sub(
        r'(?m)^target datalayout = ".*"$',
        'target datalayout = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-i128:128'
        '-f128:64-n32:64-S128-ni:1:10:20"',
        text)

    # (1) wide-string named-constant 破損
    text = re.sub(r"(constant \[[0-9]+ x i(?:16|8)\])\s+(?:%[\w.\-]+)",
                  r"\1 zeroinitializer", text)

    # (3) xor(identical) → 0 (RetDec 特産)
    text = re.sub(r"zext \(i32 xor \(i32 ([^,()]+), \1\) to i64\)", "0", text)

    # (2) bitcast pointer→pointer (opaque への no-op 化) を先に除去
    text = re.sub(r"bitcast \((?:i[0-9]+|%[\w.\-]+)\* ([^)]+) "
                  r"to (?:i[0-9]+|%[\w.\-]+)\*\)", r"\1", text)
    for _ in range(4):
        prev = text
        text = re.sub(r"(?<![\w])ptr\*", "ptr", text)
        text = NAMED_PTR_TYPE.sub("ptr", text)
        text = POINTER_TYPE.sub("ptr", text)
        # これから残るポインタ間 no-op bitcast (`= call ptr bitcast ptr X to ptr,`)
        text = re.sub(r"(= \w+) bitcast ptr ([%\w.\-]+) to ptr, ",
                      r"\1 \2, ", text)
        if text == prev:
            break

    # (2d) ptrtoint の 幅不整合 (ptr @x to i32) → to i64
    #      あわせて呼出先が i32 を期待する constexpr の過大料も ( RetDec が addr
    #      arithmetic を i64 に逃している面) i64→i32 の trunc は当 cam/m2 では不要とし、
    #      呼び出し側の型を i32 期待に合わせる形で trunc (constexpr) 文法
    #      (`trunc (i64 X to i32)`) は LLVM 17+ で constexpr trunc が廃止なので
    #      ここでは *呼出側の引数型を i64 に懐柔済みの形にしかみない* でよい:
    #      RetDecの declare 側引数型はすでに i64 (i64 %arg) なので (m2観測),
    #      i32 期待の形は charset 例外として観察ベースで対応。
    text = re.sub(r"ptrtoint \((ptr|%[\w.\-]+) (@[\w.\-]+) to i32\)",
                  lambda m: f"ptrtoint (ptr {m.group(2)} to i64)", text)
    text = re.sub(r"ptrtoint \(ptr (%[\w.\-]+) to i32\) ",
                  lambda m: f"ptrtoint (ptr {m.group(1)} to i64) ", text)
    return text


def main():
    args = sys.argv[1:]
    drop = "--drop-uselistorder" in args
    args = [a for a in args if a != "--drop-uselistorder"]
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    with open(args[0]) as fh:
        text = fh.read()
    text = normalize(text, drop_uselistorder=drop)
    with open(args[1], "w") as fh:
        fh.write(text)
    print(f"[ir_normalize] wrote {args[1]}")


if __name__ == "__main__":
    main()
