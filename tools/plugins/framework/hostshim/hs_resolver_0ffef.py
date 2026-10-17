#!/usr/bin/env python3
"""hs_resolver_0ffef.py — 0x1313220 の call rax 先 (関数ポインタ源 0x40ff70) を機械語から示す (#5421 / PLG-P0b-58)。

0x1313220 は 0x40ffe0 (resolver) を呼び、dx=0xffef をキーに関数ポインタを得てから call rax する。
resolver は 0x40ff70 を呼び、0x40ff70 は [rcx] の実行時オブジェクトを線形探索する。
このスクリプトは、そのキー照合と表の形を機械語から読み出す。静的な表の中身は出さない
(オブジェクトは実行時に作られるため、値は未確定のまま)。

使い方: FL_WIN64_DIR=<展開先> PYTHONPATH=<unicorn,pefile,capstone,tools/shared> python3 hs_resolver_0ffef.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E

KEY = 0xffef
CALLER = 0x1313220
RESOLVER = 0x40ffe0
WALKER = 0x40ff70


def lin(rd, lo, hi):
    return [i for i in S.md.disasm(rd(lo, hi - lo), lo) if i.address < hi]


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)

    print('== 1. caller 0x%x: キー設定と call rax' % CALLER)
    for i in lin(rd, CALLER, CALLER + 0x40):
        if i.address in range(0x131324c, 0x1313263):
            print('  0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))
    print('  キー dx = 0x%x (0x131324f の mov dx, imm16)' % KEY)

    print('== 2. resolver 0x%x: 0x%x を呼ぶ' % (RESOLVER, WALKER))
    calls = [i for i in lin(rd, RESOLVER, RESOLVER + 0x20) if i.mnemonic == 'call']
    print('  call: %s' % ['0x%x %s' % (c.address, c.op_str) for c in calls])

    print('== 3. walker 0x%x: 照合ロジック (キーは dx)' % WALKER)
    ws = lin(rd, WALKER, WALKER + 0x60)
    cmp_key = [i for i in ws if i.mnemonic == 'cmp' and 'dx' in i.op_str]
    print('  キー照合: %s' % ['0x%x %s %s' % (i.address, i.mnemonic, i.op_str) for i in cmp_key])
    print('  一致時の取り出し: 0x40ffa4〜0x40ffb7 (一致した添字 r8 で qword 配列 [rcx+rax+2+r8*8] を読む)')

    print('== 4. walker の連結リスト辿り: [rax-0x90] (先頭) と [rax-0x78] (次)')
    for i in ws:
        if i.mnemonic == 'mov' and ('0x90' in i.op_str or '0x78' in i.op_str):
            print('  0x%x: %s %s' % (i.address, i.mnemonic, i.op_str))

    print('== 5. 結論 (機械語のみ)')
    print('  キー 0x%x は caller 内の定数。表の中身は [rcx] の実行時オブジェクトに依る。' % KEY)
    print('  静的な表は本スクリプトでは確定しない (値は未確定)。')


if __name__ == '__main__':
    main()
