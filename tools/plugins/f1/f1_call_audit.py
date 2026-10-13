#!/usr/bin/env python3
"""f1_call_audit.py — lift 済み閉包の「脱落 call」静的監査 (PLG-F1 #198, 既知類型 D15 (DEFECTS.md) / D1 (icall §4) の検出信号)。

  python3 f1_call_audit.py <block> [<block> ...]     (前提: batch_lift.sh 済み = work/closure/ と work/batch/<block>/p.final.ll)

機械語: 閉包の各関数 (.pdata 境界) の call 命令を 3 種に数える。
  direct   = `call rel32` / `call imm`
  mem      = `call qword ptr [..]` (rip 相対 = IAT / 関数ポインタ変数、reg 相対 = vtable・関数ポインタ)
  reg      = `call reg`
IR: `define @function_<VA>` 本体の call 命令数 (llvm.* 組み込みと __asm_* helper は除外)。
  dropped_est = (direct + mem + reg) - IR call 数   (> 0 の関数は少なくとも dropped_est 個の call が IR から消えている。
                                                      IAT 呼出は RetDec が名前付き call に直すので mem に含めても過小評価側)
注意: tail-jmp の call 化・RetDec の関数分割は考慮しない。 dropped_est は下限の目安であって等式ではない。
"""
import json
import os
import re
import struct
import sys

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, '..', 'shared'))
from paths import FL_WIN64_DIR  # noqa: E402
WORK = os.path.join(ROOT, 'work')


def machine_calls(block):
    fn = 'block%05d_PE.bin' % block
    d = open(os.path.join(FL_WIN64_DIR, 'extracted', fn), 'rb').read()
    pe = pefile.PE(data=d, fast_load=True)
    base = pe.OPTIONAL_HEADER.ImageBase
    text = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
    tb, tv = text.get_data(), text.VirtualAddress
    clo = json.load(open(os.path.join(WORK, 'closure', 'block%05d.json' % block)))
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    out = {}
    for r in clo['ranges']:
        a, b = [int(x, 16) for x in r.split('-')]
        c = {'direct': 0, 'mem': 0, 'reg': 0}
        for i in md.disasm(tb[a - base - tv: b + 1 - base - tv], a):
            if i.mnemonic != 'call' or not i.operands:
                continue
            o = i.operands[0]
            if o.type == X86_OP_IMM:
                c['direct'] += 1
            elif o.type == X86_OP_MEM:
                c['mem'] += 1
            else:
                c['reg'] += 1
        out[a] = c
    return out


CALL = re.compile(r'\bcall\b[^\n]*?(?:@([A-Za-z0-9_.$]+)|(%[A-Za-z0-9_.]+))\(')


def ir_calls(block):
    s = open(os.path.join(WORK, 'batch', str(block), 'p.final.ll')).read()
    out = {}
    for f in re.split(r'\n(?=define )', s):
        m = re.match(r'define [^@]*@function_([0-9a-f]+)\(', f)
        if not m:
            continue
        n = 0
        for line in f.split('\n'):
            if ' call ' not in line and not line.lstrip().startswith('call '):
                continue
            cm = CALL.search(line)
            if cm and cm.group(1) and (cm.group(1).startswith('llvm.') or cm.group(1).startswith('__asm_')):
                continue
            n += 1
        out[int(m.group(1), 16)] = n
    return out


def main():
    tot = {}
    for b in sys.argv[1:]:
        b = int(b)
        mc, ic = machine_calls(b), ir_calls(b)
        rows, T = [], {'funcs': 0, 'direct': 0, 'mem': 0, 'reg': 0, 'ir': 0, 'dropped_est': 0, 'funcs_dropped': 0}
        for va in sorted(mc):
            c = mc[va]
            tm = c['direct'] + c['mem'] + c['reg']
            ir = ic.get(va)
            if ir is None:
                rows.append((hex(va), 'NO-IR-DEFINE'))
                continue
            dr = max(0, tm - ir)
            T['funcs'] += 1
            T['direct'] += c['direct']; T['mem'] += c['mem']; T['reg'] += c['reg']
            T['ir'] += ir; T['dropped_est'] += dr
            T['funcs_dropped'] += 1 if dr else 0
            rows.append((hex(va), c, ir, dr))
        tot[b] = T
        print('block', b, json.dumps(T))
        for r in rows:
            if len(r) == 2 or r[3]:
                print('   ', r)
    json.dump(tot, open(os.path.join(WORK, 'f1', 'call_audit.json'), 'w'), indent=1)


if __name__ == '__main__':
    os.makedirs(os.path.join(WORK, 'f1'), exist_ok=True)
    main()
