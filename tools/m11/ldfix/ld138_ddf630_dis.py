#!/usr/bin/env python3
"""ld138_ddf630_dis.py — #2921 (LD-138) ddf630 の spill 宛 4 site の根拠 (機械語 2 段参照・複写・消費者) を表示する。

使い方: python3 ld138_ddf630_dis.py   (要 work-m11 を展開済み: tools/m11/work/)
出力: 4 site の機械語 (ddf6ab-ddf6c6・ddff2f-ddff5a・de0bf7-de0bfe)、消費者行 (rbp+0x80/0xb8/0xa0/0xc0 の読み出し)、
      対応する IR 行 (boot_final3.ll の行番号)。判定の根拠は results/candidate_verdicts_2921.jsonl。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ldmach_img import ImageMachine  # noqa: E402

W = os.path.join(HERE, '..', 'work')
m = ImageMachine(os.path.join(W, 'm11_image.bin'), os.path.join(W, 'boot*.drc.config.json'))
FN = 0xddf630
ins = m.disasm_fn(FN)
print('[1] 機械語 (4 site の 2 段参照と複写)')
for i in ins:
    if 0xddf6ab <= i.address <= 0xddf6c6 or 0xddff2f <= i.address <= 0xddff5a or 0xde0bf7 <= i.address <= 0xde0bfe:
        print('  %x  %-7s %s' % (i.address, i.mnemonic, i.op_str))
print('[2] 消費者 (rbp+0x80・0xa0・0xb8・0xc0 の読み出しと、rbp 相対の call this 引数)')
pat = re.compile(r'\[rbp \+ 0x(80|a0|b8|c0)\]')
for i in ins:
    if pat.search(i.op_str) and i.mnemonic == 'mov' and i.op_str.startswith(('r', 'e')) and not i.op_str.startswith('qword ptr [rbp'):
        print('  %x  %-7s %s' % (i.address, i.mnemonic, i.op_str))
    elif pat.search(i.op_str) and i.mnemonic == 'lea':
        print('  %x  %-7s %s' % (i.address, i.mnemonic, i.op_str))
print('[3] IR 対応行 (tools/m11/work/boot_final3.ll の行番号)')
ll = os.path.join(W, 'boot_final3.ll')
want = [429019, 429020, 429850, 429862, 429877, 429907, 430128, 430139, 430849, 430185, 430250]
with open(ll) as f:
    for n, line in enumerate(f, 1):
        if n in want:
            print('  %d: %s' % (n, line.rstrip()[:120]))
        if n > max(want):
            break
