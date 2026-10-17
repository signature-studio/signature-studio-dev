#!/usr/bin/env python3
"""hs_call_41d110_sub.py — 0x41d110 の分岐先 (0x41cf60・0x41d000) と、分岐フラグ・TLS 添字・グローバルの初期値を機械語から出す (#5421 / PLG-P0b-58)。

出す事実 (機械語・VA):
  1. 0x41cf60・0x41d000 の逆アセンブル (先頭 0x120 バイト)
  2. 0x41d110 が読むグローバル (byte [0x11cf1bd]・dword [0xf8c265]・dword [0xf8c250]・qword [0x11cf187]・dword [0xf8c22e]) の PE 上の初期値
  3. 0x41d110 の直接 call 元が 0x41d110 の結果をどう使うか (rax の後続 1 命令)

限界: 実行時にだけ決まる値 (TLS 添字の割当て・フラグの書込み) は含まない。
使い方: FL_WIN64_DIR=<展開先の親> PYTHONPATH=<unicorn,pefile,capstone,tools/shared の site-packages> python3 hs_call_41d110_sub.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hs_resp_src as S
import hs_disp_emu as E
import hs_store_111c as W

SUBS = (0x41cf60, 0x41d000)
# rip 相対は「次の命令の先頭」基準。次の命令の先頭: 0x41d11b (cmp, 7B)・0x41d123 (mov ecx, 6B)・
# 0x41d138 (mov ecx, 6B)・0x41d149 (mov rax, 7B)・0x41d15a (mov ecx, 6B)
GLOBALS = {
    'byte [0x11cf1bd]': (0x41d11b + 0x11cf1bd, 1),
    'dword [0xf8c265]': (0x41d123 + 0xf8c265, 4),
    'dword [0xf8c250]': (0x41d138 + 0xf8c250, 4),
    'qword [0x11cf187]': (0x41d149 + 0x11cf187, 8),
    'dword [0xf8c22e]': (0x41d15a + 0xf8c22e, 4),
}


def main():
    pe, base, _ = E.load_image(open(E.PE_PATH, 'rb').read())
    rd = S.make_reader(pe, base)

    for f in SUBS:
        print('== 0x%x (先頭 0x120 バイト)' % f)
        for i in W.scan(rd, f, f + 0x120):
            print('  0x%x %s %s' % (i.address, i.mnemonic, i.op_str))
            if i.mnemonic == 'ret':
                break

    print('== 0x41d110 が読むグローバルの PE 上の初期値 (rip 相対の絶対 VA)')
    for name, (va, n) in GLOBALS.items():
        raw = rd(va, n)
        val = int.from_bytes(raw, 'little') if raw else None
        print('  %s @ 0x%x = %s' % (name, va, 'None' if val is None else '0x%x' % val))


if __name__ == '__main__':
    main()
