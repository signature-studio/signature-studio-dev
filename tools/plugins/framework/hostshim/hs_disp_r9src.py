#!/usr/bin/env python3
"""hs_disp_r9src.py — Dispatcher (0x13173a0) の第 4 引数 r9 (Index) の直前設定を、間接呼出し `call [reg+0x70]` ごとに出す (#5421 / PLG-P0b-58)。

`call qword ptr [reg+0x70]` は Dispatcher (vtable slot 0) 以外の呼出しも含むため、本スクリプトは呼出元の同定ではなく候補列挙である。
各候補の直前 (窓 64 命令・線形) で r9/r9d に値を入れる命令を出す。呼出先が Dispatcher かどうかは判定しない。
`mov r9, ...`・`mov r9d, ...`・`xor r9d, r9d`・`lea r9, ...` を候補とする。

限界: 直線窓だけを見る。分岐越しの設定・rcx の object 型は判定しない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared> python3 hs_disp_r9src.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E
import hs_store_111c as W

WIN = 64
R9_WRITE = ('mov', 'lea', 'xor', 'movzx', 'movsx', 'movsxd')


def sets_r9(i):
    if i.mnemonic not in R9_WRITE:
        return False
    dst = i.op_str.split(',')[0].strip()
    return dst in ('r9', 'r9d')


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)
    insns = W.scan(rd, 0x1000000, 0x1400000)
    calls = [k for k, i in enumerate(insns) if i.mnemonic == 'call' and '+ 0x70]' in i.op_str]
    print('== call qword ptr [reg+0x70] 件数 (0x1000000..0x1400000): %d' % len(calls))
    with_r9 = 0
    for k in calls:
        i = insns[k]
        found = None
        for j in range(k - 1, max(k - WIN, 0) - 1, -1):
            if sets_r9(insns[j]):
                found = insns[j]
                break
            if insns[j].mnemonic == 'call':
                break
        if found is not None:
            with_r9 += 1
            print('  0x%x %-28s r9 直前: 0x%x %s %s' % (i.address, i.op_str, found.address, found.mnemonic, found.op_str))
        else:
            print('  0x%x %-28s r9 直前設定なし (窓内)' % (i.address, i.op_str))
    print('== r9 直前設定ありの件数: %d / %d' % (with_r9, len(calls)))


if __name__ == '__main__':
    main()
