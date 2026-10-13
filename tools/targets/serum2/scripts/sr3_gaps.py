#!/usr/bin/env python3
"""SR-3 step 6: split the code that lies in .text but outside every .pdata RUNTIME_FUNCTION into function-like blocks.
Gap = bytes between consecutive pdata ranges (and before the first / after the last).  Inside a gap, 0xCC/0x90/0x00 runs are padding;
a block = maximal run of non-padding bytes that decodes cleanly with capstone.  Block entry = block start.
For every block: size, instruction count, #ret, whether a direct call/jmp/lea from elsewhere targets its start (=> real function entry),
and which cut-table library window (if any) it lies in.
usage: sr3_gaps.py <pe> <index.npz> <cut_table.tsv> <out.tsv>"""
import sys, struct, bisect, collections
import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

PATH, IDX, CUT, OUT = sys.argv[1:5]
IMG = 0x180000000
pe = pefile.PE(PATH, fast_load=True)
t = [s for s in pe.sections if s.Name.startswith(b'.text')][0]
TB, TVA = t.get_data(), t.VirtualAddress
z = np.load(IDX); funcs = z['funcs']; refs = z['refs']
gaps = []; cur = TVA
for b, e in funcs.tolist():
    if b > cur: gaps.append((cur, b))
    cur = max(cur, e)
if cur < TVA + len(TB): gaps.append((cur, TVA + len(TB)))
md = Cs(CS_ARCH_X86, CS_MODE_64)
tgt = collections.defaultdict(set)
for s, d, k in refs.tolist(): tgt[d].add(k)
cutw = []  # (lo, hi, lib) from the cut table, using function VAs
fs = funcs[:, 0].tolist(); fe = funcs[:, 1].tolist()
for ln in list(open(CUT))[1:]:
    va, by, lib, tag = ln.rstrip('\n').split('\t'); b = int(va, 16) - IMG
    cutw.append((b, b + int(by), lib))
cutw.sort(); cstart = [c[0] for c in cutw]
cutwin = {}
# library windows (contiguous cut ranges per lib) -> coarse interval list for gap attribution
rng = []
for b, e, lib in cutw:
    if rng and rng[-1][2] == lib and b - rng[-1][1] <= 0x40: rng[-1][1] = max(rng[-1][1], e)
    else: rng.append([b, e, lib])
rs = [r[0] for r in rng]


def lib_of(rva):
    i = bisect.bisect_right(rs, rva) - 1
    return rng[i][2] if i >= 0 and rng[i][0] <= rva < rng[i][1] else '-'


rows = []; padbytes = 0
for g0, g1 in gaps:
    buf = TB[g0 - TVA:g1 - TVA]
    i = 0; n = len(buf)
    while i < n:
        if buf[i] in (0xCC, 0x90, 0x00) or buf[i] == 0x66 and False:
            i += 1; padbytes += 1; continue
        j = i
        while j < n and not (buf[j] in (0xCC,) and (j + 1 >= n or buf[j + 1] == 0xCC)):
            j += 1
        blk = buf[i:j]
        ninsn = nret = 0; last = 0
        for ins in md.disasm(blk, g0 + i):
            ninsn += 1; last = ins.address + ins.size - (g0 + i)
            if ins.mnemonic in ('ret', 'retf'): nret += 1
        rows.append((g0 + i, len(blk), ninsn, nret, 1 if last == len(blk) else 0, ''.join(sorted(str(k) for k in tgt.get(g0 + i, ()))) or '-'))
        i = j
with open(OUT, 'w') as f:
    f.write('block_va\tbytes\tinsns\tret\tclean_decode\tentry_ref_kinds\tcut_library\n')
    for b, sz, ni, nr, ok, k in rows: f.write(f'{hex(IMG + b)}\t{sz}\t{ni}\t{nr}\t{ok}\t{k}\t{lib_of(b)}\n')
tb = sum(r[1] for r in rows)
print(f"gaps={len(gaps)} gap_bytes={sum(b-a for a,b in gaps)} padding_bytes={padbytes} blocks={len(rows)} block_bytes={tb} insns={sum(r[2] for r in rows)} ret={sum(r[3] for r in rows)}")
ent = [r for r in rows if r[5] != '-']
print(f"blocks with a direct call/jmp/lea entry ref (kinds 0=rip,1=call,2=jmp,3=jcc): {len(ent)} bytes={sum(r[1] for r in ent)}")
print(f"clean-decode blocks: {sum(r[4] for r in rows)} bytes={sum(r[1] for r in rows if r[4])}")
byl = collections.Counter(); byb = collections.Counter()
for r in rows: byl[lib_of(r[0])] += 1; byb[lib_of(r[0])] += r[1]
print("blocks by cut-library window (outside .pdata):", {k: (byl[k], byb[k]) for k in byl})
