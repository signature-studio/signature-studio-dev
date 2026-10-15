#!/usr/bin/env python3
"""hs_store_src27.py — 応答スロット [rbp+0x11a0] への 27 行の格納値の種別と直近の供給命令を出す (#4849 / PLG-P0b-54)。

入力: 格納 VA (既定は #4075 の 27 行)。出力: 格納ごとに
  * 格納値の種別: 即値 (mov/or の即値)・rax (直前の命令列から供給元を辿る)
  * rax の場合: 格納直前の窓 (命令 14 個) で rax を最後に書いた命令 (供給元の VA)。
    その命令が call なら呼出先 VA、メモリ読みなら読み元の式。
  * 供給元を窓内で確定できない場合は『未確定』と書く (理由つき)。
結論の判定は REPORT_DISPATCHER_APPENDIX_4849.md が行う。本スクリプトは出力を作るだけ。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone> python3 hs_store_src27.py [VA...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pefile
import hs_resp_src as S
import hs_disp_emu as E
import hs_store_supplier as SU
from hs_store_branch import STORES27


def last_rax_writer(win):
    """窓 (store を含む) で rax を最後に書いた命令。store 自身は除く。"""
    for x in reversed(win[:-1]):
        if x.mnemonic == 'call':
            if x.op_str.startswith('qword ptr') or x.op_str.startswith('rax'):
                return x
            return x
        if x.mnemonic in ('cmp', 'test', 'jmp', 'push') or x.mnemonic.startswith('j'):
            continue
        ops = x.op_str.split(',')
        if ops and ops[0].strip() in ('rax', 'eax', 'al', 'ax'):
            return x
    return None


def main():
    vas = [int(a, 0) for a in sys.argv[1:]] or STORES27
    pe = pefile.PE(E.PE_PATH, fast_load=True)
    rd = S.make_reader(pe, pe.OPTIONAL_HEADER.ImageBase)
    for site in vas:
        win = SU.aligned_window(rd, site, back=0x60, n=14)
        print('==== 0x%x' % site)
        if not win:
            print('  (命令境界に揃わない)')
            continue
        store = win[-1]
        src = store.op_str.split(',')[-1].strip()
        if src == 'rax':
            w = last_rax_writer(win)
            if w is None:
                print('  kind: rax / 供給元: 未確定 (窓内に rax の書込みなし)')
            elif w.mnemonic == 'call':
                print('  kind: rax / 供給元: call 0x%x (%s) の戻り値' % (w.address, w.op_str))
            else:
                print('  kind: rax / 供給元: 0x%x %s %s' % (w.address, w.mnemonic, w.op_str))
        elif src.startswith('0x') or src.lstrip('-').isdigit():
            print('  kind: 即値 %s' % src)
        else:
            print('  kind: %s' % src)
        print('  store: 0x%x %s %s' % (store.address, store.mnemonic, store.op_str))


if __name__ == '__main__':
    main()
