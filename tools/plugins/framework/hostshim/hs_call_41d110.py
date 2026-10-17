#!/usr/bin/env python3
"""hs_call_41d110.py — 格納 0x1321b6c の直前 `call 0x41d110` の戻り値 (rax) の由来を機械語から出す (#5421 / PLG-P0b-58)。

出す事実 (機械語・VA):
  1. 0x41d110 の逆アセンブル全体
  2. 0x41d110 を直接 `call rel32` する箇所 (.text 0x1000000..0x1400000)
  3. 0x1321b6c の直前 (同じ関数内) の rax の設定元

限界: 間接 call・関数外からの書込みは含まない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared の site-packages> python3 hs_call_41d110.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E
import hs_store_111c as W

FUNC = 0x41d110
SITE = 0x1321b6c


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)

    body = W.scan(rd, FUNC, FUNC + 0x200)
    print('== 0x%x の先頭 0x200 バイト (命令 %d 件)' % (FUNC, len(body)))
    for i in body:
        print('  0x%x %s %s' % (i.address, i.mnemonic, i.op_str))
        if i.mnemonic == 'ret':
            break

    print('== 0x%x を直接 call する箇所 (.text 0x1000000..0x1400000)' % FUNC)
    allins = W.scan(rd, 0x1000000, 0x1400000)
    for i in allins:
        if i.mnemonic == 'call' and i.op_str.startswith('0x'):
            try:
                tgt = int(i.op_str, 16)
            except ValueError:
                continue
            if tgt == FUNC:
                print('  0x%x call 0x%x' % (i.address, tgt))

    print('== 格納 0x%x の直前 24 命令' % SITE)
    pos = {i.address: k for k, i in enumerate(allins)}
    k = pos.get(SITE)
    if k is None:
        print('  命令境界が合わない')
        return
    for j in range(max(0, k - 24), k + 1):
        i = allins[j]
        print('  0x%x %s %s' % (i.address, i.mnemonic, i.op_str))


if __name__ == '__main__':
    main()
