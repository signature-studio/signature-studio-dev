#!/usr/bin/env python3
"""hs_store5_src.py — 応答スロット格納 5 行 (#5421 / PLG-P0b-58) の格納直前の命令列と、
格納の手前の分岐 (ゲート) が基準 run で訪問されたかを出す。

入力: hs_disp_emu.py を HS_DISP_PATH=1 で全 256 ID 実行した JSON (基準)。
出力: 各格納 VA の直前 N 命令、call 先の先頭命令列、ゲート VA の訪問 ID 数。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store5_src.py base.json
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E

STORES = [0x13218c1, 0x13219b0, 0x1321966, 0x1321b6c, 0x132257d]
CALLEES = [0x1313220, 0xf5b190, 0xf5ae50, 0x41d110, 0xfdd2c0]
GATES = [0x1321854, 0x1321b19, 0x1322550]  # je (store 1 の手前) / call [rax] (store 4 の手前) / je (store 5 の手前)
BEFORE = 60


def main():
    run = json.load(open(sys.argv[1]))
    visited = {}
    for k, v in run.items():
        for a in v.get('path') or []:
            visited[a] = visited.get(a, 0) + 1
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)
    for st in STORES:
        lo = st - BEFORE
        print('== store 0x%x (visited by %d IDs)' % (st, visited.get(st, 0)))
        for ins in S.md.disasm(rd(lo, BEFORE + 16), lo):
            if ins.address > st:
                break
            print('  0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
    for fn in CALLEES:
        print('== callee 0x%x head (12 insns)' % fn)
        for i, ins in enumerate(S.md.disasm(rd(fn, 64), fn)):
            if i >= 12:
                break
            print('  0x%x: %s %s' % (ins.address, ins.mnemonic, ins.op_str))
    for g in GATES:
        print('gate 0x%x visited by %d IDs' % (g, visited.get(g, 0)))


if __name__ == '__main__':
    main()
