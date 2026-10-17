#!/usr/bin/env python3
"""hs_store_111c.py — 応答スロット格納 0x13217c3 の入力 [rbp+0x111c] の書込み元 (#5421 / PLG-P0b-58)。

出す事実 (機械語・VA):
  1. [rbp+0x111c] の書込み (0x13217c3) の値の作り: ([rbp+0x1878] >> 16) & 0xffff
  2. [rbp+0x1878] の実書込み (範囲内の mov 形式のみ)
  3. 0x132178c (その値の書込み先の分岐) への飛び込み元
  4. 0xf5b190 が出力 word [rsi] (= [rbp+0x111c]) へ書く命令 (0x11d06e0 経由を含む)

限界: 直接の mov 形式だけを数える。間接書込み・未走査の範囲は含まない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared> python3 hs_store_111c.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E

LO, HI = 0x1200000, 0x1321000
CHUNK = 0x4000


def scan(rd, lo, hi):
    """線形 disasm を 0x4000 ずつ区切って全命令を返す (分割境界の誤読を避けるため末尾 16B を捨てる)。"""
    out = []
    va = lo
    while va < hi:
        try:
            chunk = rd(va, min(CHUNK, hi - va))
        except Exception:
            va += CHUNK
            continue
        n = 0
        for i in S.md.disasm(chunk, va):
            if i.address >= va + CHUNK - 16:
                break
            n = i.address + i.size - va
            out.append(i)
        va += max(n, 1)
    return out


def lin(rd, lo, hi):
    return [i for i in S.md.disasm(rd(lo, hi - lo), lo) if i.address < hi]


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)

    print('== 1. [rbp+0x111c] の書込み (0x13217c3) の値の作り')
    for i in lin(rd, 0x13217b4, 0x13217ca):
        print('  0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))

    insns = scan(rd, LO, HI)

    print('== 2. [rbp+0x1878] の実書込み (0x%x..0x%x, mov 形式)' % (LO, HI))
    for i in insns:
        if i.mnemonic == 'mov' and i.op_str.split(',')[0].strip().endswith('[rbp + 0x1878]'):
            print('  0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))

    print('== 3. 0x132178c への飛び込み元 (0x%x..0x%x)' % (LO, HI))
    target = 0x132178c
    for i in insns:
        if i.mnemonic.startswith('j'):
            for op in i.op_str.split():
                try:
                    if int(op, 16) == target:
                        print('  0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))
                except ValueError:
                    pass

    print('== 4. 0xf5b190 の出力 word [rsi] への書込み (0xf5b190..0xf5b202)')
    for i in lin(rd, 0xf5b190, 0xf5b202):
        if i.mnemonic in ('mov', 'movzx', 'movsx', 'movsxd') and i.op_str.split(',')[0].strip().startswith('word ptr [rsi'):
            print('  0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))
    print('  0xf5b190 の出力 word は r8 = rsi として 0x11d06e0 に渡る:')
    for i in lin(rd, 0x11d06e0, 0x11d073b):
        if i.mnemonic == 'mov' and i.op_str.startswith('word ptr [rbx]'):
            print('    0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))


if __name__ == '__main__':
    main()
