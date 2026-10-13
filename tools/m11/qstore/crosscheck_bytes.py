#!/usr/bin/env python3
"""crosscheck_bytes.py — m11_qstore.py の機械語側カウントの別算法検算 (#516).

capstone を使わず、closure の各関数の .pdata 区間を **バイト列パターン**だけで走査する:
  REX.W C7 /0 imm32 で ModRM が [rbp+disp8] (48 C7 45 d8 imm32) / [rbp+disp32] (48 C7 85 d32 imm32) /
  [rsp+disp8] (48 C7 44 24 d8 imm32) / [rsp+disp32] (48 C7 84 24 d32 imm32)
命令境界を見ないので偽陽性 (命令の途中の一致) がありうる = **上限**。capstone 版 (m11_qstore.py の
machine_qword_imm_stack_stores) との差分が偽陽性 + prologue 未解決 (rbp 基準で frame 追跡できない関数) で説明できることを確認する。
使い方: crosscheck_bytes.py <boot_final.ll> --pe PE.bin
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ldfix'))
from ldmach import Machine  # noqa: E402

PATS = {
    'rbp+d8': re.compile(rb'\x48\xc7\x45.....', re.S),
    'rbp+d32': re.compile(rb'\x48\xc7\x85........', re.S),
    'rsp+d8': re.compile(rb'\x48\xc7\x44\x24......', re.S),
    'rsp+d32': re.compile(rb'\x48\xc7\x84\x24.........', re.S),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir')
    ap.add_argument('--pe', required=True)
    a = ap.parse_args()
    vas = [int(m.group(1), 16) for m in re.finditer(r'^define [^@]*@function_([0-9a-f]+)\(', open(a.ir, encoding='latin1').read(), re.M)]
    mach = Machine(a.pe)
    tot = {k: 0 for k in PATS}
    zero = 0
    nof = 0
    for va in vas:
        ent = mach.fns.get(va)
        if not ent:
            nof += 1
            continue
        data = mach.read(ent[0], ent[1])
        for k, p in PATS.items():
            for m in p.finditer(data):
                tot[k] += 1
                b = m.group(0)
                imm = struct.unpack('<i', b[-4:])[0]
                if imm == 0:
                    zero += 1
    print('closure functions=%d (no .pdata=%d)' % (len(vas), nof))
    print('byte-pattern mov qword [rbp|rsp+d], imm32: total=%d (imm==0: %d) %s' % (sum(tot.values()), zero, tot))


if __name__ == '__main__':
    main()
