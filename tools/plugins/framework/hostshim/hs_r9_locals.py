#!/usr/bin/env python3
"""hs_r9_locals.py — hs_disp_r9src.py が出した r9 設定の 2 件 (0x1090dc4・0x1090ff9) の呼出元関数 (#5421 / PLG-P0b-58) の、r9 の元になるスタック変数の書込みと、その関数の直接呼出元を出す。

関数先頭は「直前が ret/int3/nop で、その次の push rbp」を後方探索して求める。
出す事実 (機械語・VA):
  1. 関数内で [rbp+0x60]・[rbp+0x98] (r9 の元) に対する全命令 (mov 以外の書込みも含む参照)
  2. 関数先頭を呼ぶ直接の call 命令 (`call rel32` の形式のみ)

限界: 関数先頭の近似。間接 call・関数外からの書込みは含まない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared> python3 hs_r9_locals.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E
import hs_store_111c as W

SITES = (0x1090dc4, 0x1090ff9)
TARGETS = ('+ 0x60]', '+ 0x98]')


def func_start(insns, idx):
    for j in range(idx, 0, -1):
        i = insns[j]
        if i.mnemonic == 'push' and i.op_str == 'rbp':
            if insns[j - 1].mnemonic in ('ret', 'int3', 'nop'):
                return j
    return None


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)
    insns = W.scan(rd, 0x1080000, 0x10a0000)
    pos = {i.address: k for k, i in enumerate(insns)}
    starts = set()
    for site in SITES:
        k = pos.get(site)
        if k is None:
            print('0x%x: 命令境界が合わない' % site)
            continue
        s = func_start(insns, k)
        if s is None:
            print('0x%x: 関数先頭を特定できない' % site)
            continue
        starts.add(insns[s].address)
        print('== 呼出元 0x%x の関数先頭 0x%x (先頭から call 位置まで %d 命令)' % (site, insns[s].address, k - s))
        for j in range(s, k + 1):
            i = insns[j]
            if any(t in i.op_str for t in TARGETS):
                print('  0x%x %s %s' % (i.address, i.mnemonic, i.op_str))
    print('== 呼出元の関数先頭を直接 call する箇所 (.text 0x1000000..0x1400000)')
    allins = W.scan(rd, 0x1000000, 0x1400000)
    for i in allins:
        if i.mnemonic == 'call' and i.op_str.startswith('0x'):
            try:
                tgt = int(i.op_str, 16)
            except ValueError:
                continue
            if tgt in starts:
                print('  0x%x call 0x%x' % (i.address, tgt))


if __name__ == '__main__':
    main()
