#!/usr/bin/env python3
"""Which functions reference the 4.5MB high-entropy .rdata blob (rip-relative)? usage: blob_refs.py <pe> <lo_va> <hi_va>"""
import sys, struct, bisect, collections
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP
pe = pefile.PE(sys.argv[1]); IMG = pe.OPTIONAL_HEADER.ImageBase
lo, hi = int(sys.argv[2], 16), int(sys.argv[3], 16)
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
T = S['.text']; TB = T.get_data(); TVA = T.VirtualAddress
pd = S['.pdata'].get_data(); funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, u = struct.unpack_from('<III', pd, i)
    if b and TVA <= b < TVA + len(TB): funcs.append((b, e))
funcs.sort()
md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
hits = collections.defaultdict(set)
for b, e in funcs:
    for i in md.disasm(TB[b - TVA:e - TVA], IMG + b):
        for o in i.operands:
            if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                t = i.address + i.size + o.mem.disp
                if lo <= t < hi: hits[t].add(IMG + b)
for t in sorted(hits): print(hex(t), [hex(x) for x in sorted(hits[t])])
print('distinct targets', len(hits))
