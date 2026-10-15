#!/usr/bin/env python3
"""hs_store_src11.py — 応答スロット格納 11 行 (#5422 / PLG-P0b-59) の rax 供給元のメモリ読み元を関数内で列挙する。

入力: 格納 VA (既定は #5422 の 11 行)。
出力: 格納ごとに
  * 供給命令 (rax を最後に書いた命令) と、そのメモリ読み元の式
  * 読み元が [rbp+disp] / [global] なら、関数 [FN_LO, FN_HI) 内で同じ式へ書く命令の VA 一覧
  * 読み元が [rax+...] / call / 比較なら『未確定 (理由)』

結論の判定は REPORT_DISPATCHER_APPENDIX_4849.md §8 が行う。本スクリプトは出力を作るだけ。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_src11.py [VA...]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pefile
import hs_resp_src as S
import hs_disp_emu as E
import hs_store_supplier as SU
from hs_store_src27 import last_rax_writer

TARGETS11 = [0x132206e, 0x13220b2, 0x13221be, 0x1321fc2, 0x1321225, 0x1321f0e,
             0x1321f34, 0x1321f6c, 0x1320fc4, 0x1320ff9, 0x1319f13]

MEM = re.compile(r'\[(rbp|rsp) ?\+ ?(0x[0-9a-f]+)\]')


def main():
    vas = [int(a, 0) for a in sys.argv[1:]] or TARGETS11
    pe = pefile.PE(E.PE_PATH, fast_load=True)
    rd = S.make_reader(pe, pe.OPTIONAL_HEADER.ImageBase)
    code = rd(E.FN_LO, E.FN_HI - E.FN_LO)
    fn = list(S.md.disasm(code, E.FN_LO))
    for site in vas:
        win = SU.aligned_window(rd, site, back=0x60, n=14)
        print('==== 0x%x' % site)
        if not win:
            print('  未確定: 命令境界に揃わない')
            continue
        w = last_rax_writer(win)
        if w is None:
            print('  未確定: 窓内に rax の書込みなし')
            continue
        if w.mnemonic == 'call':
            print('  供給: 0x%x call %s (戻り値)' % (w.address, w.op_str))
            continue
        print('  供給: 0x%x %s %s' % (w.address, w.mnemonic, w.op_str))
        m = MEM.search(w.op_str)
        if not m:
            print('  未確定: 読み元がレジスタ・比較結果 (メモリ式なし)')
            continue
        disp = m.group(2)
        expr = '[%s + %s]' % (m.group(1), disp)
        writers = []
        for ins in fn:
            if ins.address >= w.address:
                break
            if ins.mnemonic in ('mov', 'and', 'or', 'lea') and ins.op_str.split(',')[0].strip().startswith(
                    ('dword ptr ', 'qword ptr ', 'byte ptr ', 'word ptr ')) and expr in ins.op_str.split(',')[0]:
                writers.append(ins)
        if writers:
            print('  読み元 %s の書込み (関数内・手前): %s' % (expr, ' / '.join(
                '0x%x %s %s' % (x.address, x.mnemonic, x.op_str) for x in writers[-3:])))
        else:
            print('  読み元 %s: 関数内・手前に書込みなし (引数・初期化前の値の可能性)' % expr)


if __name__ == '__main__':
    main()
