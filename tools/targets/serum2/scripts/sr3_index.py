#!/usr/bin/env python3
"""SR-3 step 1: one-pass reference index of Serum2 Win64 .text.
Output (npz, work/): funcs (pdata begin,end RVA), refs (src_rva, target_rva, kind) where kind 0=rip-rel data/lea/mov,
1=direct call, 2=direct jmp, 3=jcc.  Also gap blocks outside .pdata are indexed (src is raw RVA).
usage: sr3_index.py <pe> <out.npz> [--workers N]"""
import sys, struct, multiprocessing as mp
import numpy as np
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

PATH = sys.argv[1]; OUT = sys.argv[2]
NW = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else mp.cpu_count()
pe = pefile.PE(PATH, fast_load=True)
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
text = S['.text']; TB = text.get_data(); TVA = text.VirtualAddress
TEND = TVA + len(TB)
IMG = pe.OPTIONAL_HEADER.ImageBase
pd = S['.pdata'].get_data()
funcs = sorted({(b, e) for b, e, _ in struct.iter_unpack('<III', pd[:len(pd) // 12 * 12]) if b and TVA <= b < TEND})


def chunks():
    """Split .text into windows aligned to function starts (so that decode is in sync)."""
    n = max(1, len(funcs) // (NW * 8))
    out = []
    for i in range(0, len(funcs), n):
        out.append((funcs[i][0], funcs[min(i + n, len(funcs)) - 1][1]))
    return out


def work(rng):
    b, e = rng
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    rows = []
    for i in md.disasm(TB[b - TVA:e - TVA], b):
        g = i.id
        m = i.mnemonic
        for op in i.operands:
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                rows.append((i.address, i.address + i.size + op.mem.disp, 0))
            elif op.type == X86_OP_IMM and (m == 'call' or m.startswith('j')):
                kind = 1 if m == 'call' else 2 if m == 'jmp' else 3
                rows.append((i.address, op.imm, kind))
    return rows


if __name__ == '__main__':
    with mp.Pool(NW) as p:
        res = p.map(work, chunks())
    rows = [r for c in res for r in c]
    refs = np.array(rows, dtype=np.int64).reshape(-1, 3)
    np.savez_compressed(OUT, funcs=np.array(funcs, dtype=np.int64), refs=refs)
    print(f"funcs={len(funcs)} refs={len(refs)} rip={int((refs[:,2]==0).sum())} call={int((refs[:,2]==1).sum())} jmp={int((refs[:,2]==2).sum())} jcc={int((refs[:,2]==3).sum())}")
