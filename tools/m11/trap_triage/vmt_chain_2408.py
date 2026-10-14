#!/usr/bin/env python3
"""vmt_chain_2408.py VMT_LVA... : TObject.InitInstance (40fb40) の親鎖走査を PE の静的データで再現し、
flag (tkMRecord InitTable が chain に有るか) と 40fac0 の 417150 呼出しの有無を表示する (#2408)。
LVA == RVA (ImageBase 0x400000)。ポインタ値は raw VA から IB を引いて LVA にして辿る (m11_ov.c の Q/B/D と同じ)。"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))
import pefile
from paths import FL_WIN64_DIR  # docs/REFERENCES.md [WIN64]
PE = os.environ.get('LD_M11_PE', f'{FL_WIN64_DIR}/extracted/block00031_PE.bin')
pef = pefile.PE(PE, fast_load=True)
IB = pef.OPTIONAL_HEADER.ImageBase
def rd(a, n): return pef.get_data(a, n)
def Q(a):
    v = int.from_bytes(rd(a, 8), 'little')
    return v - IB if v else 0
def B(a): return rd(a, 1)[0]
def D(a): return int.from_bytes(rd(a, 4), 'little')
def nested(cls, inst, calls):
    while True:
        ti = Q(cls - 0xb0)
        p = Q(cls - 0x78)
        if p: p = Q(p)
        if not p: break
        if not ti or B(ti) != 0x16:
            cls = p
            continue
        nested(p, inst, calls)
        break
    if ti and B(ti) == 0x16:
        n = ti + B(ti + 1)
        ops = n + 0xa + (D(n + 6) << 4)
        if B(ops) > 0 and (Q(ops + 1) & 1):
            calls.append(ti)
def flag_of(self_):
    flag = 0
    cls = self_
    while True:
        ti = Q(cls - 0xb0)
        if ti and B(ti) == 0x16: flag = 1
        cls = Q(cls - 0x78)
        if cls: cls = Q(cls)
        if not cls: break
    return flag
for a in sys.argv[1:]:
    self_ = int(a, 16)
    ti = Q(self_ - 0xb0)
    print('vmt=0x%x InitTable(ti)=0x%x kind=0x%x flag(40fb40)=%d' % (self_, ti, B(ti) if ti else -1, flag_of(self_)))
    calls = []
    if flag_of(self_): nested(self_, 0, calls)
    print('  40fac0 -> 417150 calls: %d %s' % (len(calls), ['ti=0x%x' % c for c in calls]))
