#!/usr/bin/env python3
"""PY-368 (#5409): pe_py368_terminal.py の未分類 2 件と ENTRY 値の直接呼出し元 1 段を、逆アセンブルで確認する。

- 0x12c609e (edx = ebx): 関数 0x12c5f20 のループ添字。合流元 0x12c6252 の `jne 0x12c5fa8` と、0x12c68f0 の戻り値を出す。
- 0xfc820f (edx = edi): 関数 0xfc8150 の clamp 節 (0xfc81ac・0xfc81c2) を出す。
- ENTRY 値の 1 段上: pe_py203_edx_sites.resolve で直接呼出し元の格納元 (r8・ecx) を分類する。

  FL_WIN64_DIR=<展開先> python3 analysis/flapi/pe_py368_merge_probe.py

終了 0 = 完了 (出力は人手で読む。自動判定はしない)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pe_py203_edx_sites as E  # noqa: E402
import pe_py273_base as B  # noqa: E402


def dump(lo, hi):
    for k in range(len(E.INS)):
        a = E.INS[k][0]
        if lo <= a <= hi:
            print(f"  0x{a:x}: {E.INS[k][1]} {E.INS[k][2]}")


def jumps_into(lo, hi):
    for tv, sv in E.JTS:
        if lo <= tv <= hi:
            print(f"  0x{sv:x} -> 0x{tv:x}")


def main():
    B.setup()
    print("== 0x12c609e: 0x12c6240..0x12c6260 と 0x12c68f0 (ループ添字の戻り値)")
    dump(0x12c6240, 0x12c6260)
    print("  jumps into 0x12c5fa8..0x12c6252:")
    jumps_into(0x12c5fa8, 0x12c6252)
    dump(0x12c68f0, 0x12c6907)

    print("== 0xfc820f: 0xfc81a6..0xfc81c7 (clamp 節)")
    dump(0xfc81a6, 0xfc81c7)
    print("  jumps into 0xfc81ac..0xfc81c7:")
    jumps_into(0xfc81ac, 0xfc81c7)

    print("== ENTRY 値の直接呼出し元 1 段 (分類は resolve)")
    for callee, fam, callers in [
        (0x118a1c0, "r8", [0xfee12f, 0x12a739d, 0x12b7e6b]),
        (0x12e6960, "rcx", [0xe71c30, 0xe7a192]),
        (0x12ab710, "r8", [0x12ac257]),
    ]:
        print(f"  callee 0x{callee:x} (ENTRY {fam})")
        for c in callers:
            cfn = E.func_of(c)
            r = E.resolve(E.ADDR_IDX[cfn], E.ADDR_IDX[c], fam)
            print(f"    call 0x{c:x} (in 0x{cfn:x}) {fam} = {E.desc(r)}")


if __name__ == "__main__":
    main()
