#!/usr/bin/env python3
"""site_check.py: 親 function_448490 の mov rcx,rbp 渡し site ごとに、call 直前の引数 (rdx 等) と callee の読み先を機械語で並べる (#4189 / SHX-T44)。

使い方:
  FL_WIN64_DIR=<展開先> python3 frame_share/site_check.py [--parent 448490] [--pe PE]
出力: site ごとの call VA・callee・call 直前 6 命令・callee の rbp 基準アクセス (off:size:kind)。
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M11 = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(M11, 'ldfix'))
sys.path.insert(0, HERE)
from ldmach import Machine  # noqa: E402
import detect  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parent', default='448490')
    ap.add_argument('--pe', default=os.path.join(os.environ.get('FL_WIN64_DIR', ''), 'extracted', 'block00031_PE.bin'))
    a = ap.parse_args()
    mach = Machine(a.pe)
    cs = mach.cs
    pva = int(a.parent, 16)
    pins = mach.disasm_fn(pva)
    for i, ins in enumerate(pins):
        if ins.mnemonic != 'call' or not ins.operands or ins.operands[0].type != detect.capstone.CS_OP_IMM:
            continue
        got = detect.call_site_base(cs, pins, i)
        if got is None or got[1] != 'mov':
            continue
        cva = ins.operands[0].imm
        cins = mach.disasm_fn(cva)
        hits = detect.walk_callee(cs, cins, got[0]) if cins else []
        acc = sorted(set((h['off'], h['size'], h['kind']) for h in hits))
        print('site 0x%x call 0x%x callee 0x%x' % (ins.address, ins.address, cva))
        for j in pins[max(0, i - 6):i + 1]:
            print('   0x%x %s %s' % (j.address, j.mnemonic, j.op_str))
        print('   callee rbp 基準: ' + ', '.join('0x%x:%d:%s' % x for x in acc))


if __name__ == '__main__':
    main()
