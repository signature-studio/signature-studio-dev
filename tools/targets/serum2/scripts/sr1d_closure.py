#!/usr/bin/env python3
"""SR-1d (#340): direct-call closure sizes of the XferJson reader/writer, split by the SR-3 cut table (out/sr3_cut_table.tsv)
and by the nlohmann binary_reader/writer region REGION. Indirect calls (vtable / fn-ptr) are invisible -> lower bound.
usage: sr1d_closure.py <index.npz> <sr3_cut_table.tsv>"""
import sys, bisect
import numpy as np

IMG = 0x180000000
REGION = (0x180256000, 0x180264000)   # contiguous run of binary_reader/binary_writer/lexer instantiations (estimate, see REPORT)
z = np.load(sys.argv[1]); f = z['funcs']; refs = z['refs']
st = f[:, 0].tolist()
fi = lambda r: (lambda i: i if i >= 0 and f[i][0] <= r < f[i][1] else -1)(bisect.bisect_right(st, r) - 1)
adj = {}
for s, t, k in refs.tolist():
    if k in (1, 2):
        a, b = fi(s), fi(t)
        if a >= 0 and b >= 0 and a != b:
            adj.setdefault(a, set()).add(b)
cut = {}
for l in open(sys.argv[2]).read().split('\n')[1:]:
    if l:
        a, b, lib, tag = l.split('\t'); cut[int(a, 16)] = lib
size = lambda S: sum(int(f[i][1] - f[i][0]) for i in S)
va = lambda i: int(f[i][0]) + IMG


def closure(root):
    r = fi(root - IMG); seen = {r}; fr = [r]
    while fr:
        n = []
        for x in fr:
            for y in adj.get(x, ()):
                if y not in seen:
                    seen.add(y); n.append(y)
        fr = n
    return seen


inreg = lambda i: REGION[0] <= va(i) < REGION[1]
print(f'REGION {REGION[0]:#x}-{REGION[1]:#x}: funcs={sum(inreg(i) for i in range(len(f)))} bytes={size([i for i in range(len(f)) if inreg(i)])}  (.pdata funcs in range)')
print('root\tclosure_funcs\tclosure_B\tin_REGION_funcs\tin_REGION_B\tin_SR3_cut(other)_funcs\tin_SR3_cut(other)_B\tremaining_Xfer_funcs\tremaining_Xfer_B')
for nm, root in [('writer 0x1801be2e0', 0x1801be2e0), ('reader 0x1801bf1c0', 0x1801bf1c0), ('from_cbor 0x1801bfb00', 0x1801bfb00), ('from_ubjson 0x1801bf5f0', 0x1801bf5f0),
                 ('to_cbor 0x1801bea90', 0x1801bea90)]:
    c = closure(root)
    R = {i for i in c if inreg(i)}
    C = {i for i in c - R if va(i) in cut}
    X = c - R - C
    print(f'{nm}\t{len(c)}\t{size(c)}\t{len(R)}\t{size(R)}\t{len(C)}\t{size(C)}\t{len(X)}\t{size(X)}')
# Xfer-owned entry functions (not in REGION, not in SR-3 cut) that hold the XferJson container logic
print('\nXferJson container functions (own code, stay in lift):')
for a in (0x1801be2e0, 0x1801bea90, 0x1801bf1c0, 0x1801bf5f0, 0x1801bfb00):
    i = fi(a - IMG); print(f'  {a:#x}\t{int(f[i][1]-f[i][0])} B\tin_cut={va(i) in cut}')

# REGION members reachable by direct calls from the 3 verified entries (write_cbor / sax_parse / lexer-ish 0x180263a20) staying inside REGION
reg = {i for i in range(len(f)) if inreg(i)}
seen = {fi(a - IMG) for a in (0x180256250, 0x180256dc0, 0x180263a20)}; fr = list(seen)
while fr:
    n = []
    for x in fr:
        for y in adj.get(x, ()):
            if y in reg and y not in seen:
                seen.add(y); n.append(y)
    fr = n
print(f'\nREGION funcs reachable from 0x180256250/0x180256dc0/0x180263a20 inside REGION: {len(seen)} funcs / {size(seen)} B; unreached by direct call: {len(reg - seen)} funcs / {size(reg - seen)} B')
print(f'REGION funcs already in SR-3 cut table: {sum(va(i) in cut for i in reg)} funcs / {size([i for i in reg if va(i) in cut])} B')
