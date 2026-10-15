#!/usr/bin/env python3
# M11: 全 .text 直索引 (call graph + rip 相対 data 参照) — closure 選定の唯一の索引
# 実行: python3 m11_scan.py            (索引生成, work/scan_index.json)
import sys, struct, json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'm6'))
from ottlib import Bin, Dis

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared'))
from paths import FL_WIN64_DIR
WINF = os.environ.get('M11_PE') or os.path.join(FL_WIN64_DIR, 'extracted', 'block00031_PE.bin')
OUT = os.path.join(HERE, 'work', 'scan_index.json')

b = Bin(WINF)
d = Dis(b)
fns = b.fns
print('[scan] fns:', len(fns))

calls = {}       # rva -> [target_rva...]
riprefs = defaultdict(list)   # target_rva -> [src_rva...] ,'call_rva']
indirect = {}
size, i = 0, 0
for (va, sz) in fns:
    code = b.read_at(va, sz)
    if code is None:
        continue
    cs = []
    for ins in d.cs.disasm(code, va):
        m = ins.mnemonic
        if m == 'call':
            ops = ins.operands
            if ops and ops[0].type == 2:
                t = ops[0].imm
                if op_ok := (b.read_at(t, 1) is not None):
                    cs.append(t)
            else:
                indirect[va] = indirect.get(va, 0) + 1
        # rip 相対参照
        for op in ins.operands:
            t = d.rip_target(ins, op)
            if t is not None:
                riprefs[t].append(va)
    calls[va] = cs
    size += sz
    i += 1
    if i % 10000 == 0:
        print('[scan] %d fns done (bytes=%d)' % (i, size))

json.dump({
    'calls': {hex(k): [hex(x) for x in v] for k, v in calls.items()},
    'riprefs': {hex(k): [hex(x) for x in sorted(set(v))][:8] for k, v in riprefs.items()},
    'indirect_count': {hex(k): v for k, v in indirect.items()},
}, open(OUT, 'w'))
print('[scan] wrote', OUT, 'text bytes', size)
