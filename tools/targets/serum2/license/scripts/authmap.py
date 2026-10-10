#!/usr/bin/env python3
"""CAB-71: authorization call-site map builder.
Builds a static call/data graph over .pdata functions and dumps, for a set of
seed functions, the reverse-reachable "authorization zone" with string/IAT
annotations.

usage: authmap.py <pe> <outdir>
outputs:
  work/graph.pkl        funcs, adj(direct+jmp), iat, drefs(strings/globals)
  out/seeds_callers.txt reverse BFS from seeds (depth 4)
"""
import sys, os, struct, bisect, re, collections, pickle, multiprocessing as mp
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

PE = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

pe = pefile.PE(PE, fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
IMG = pe.OPTIONAL_HEADER.ImageBase
S = {s.Name.rstrip(b'\0').decode(): s for s in pe.sections}
T = S['.text']; TB, TVA = T.get_data(), T.VirtualAddress
pd = S['.pdata'].get_data()
funcs = []
for i in range(0, len(pd) - 11, 12):
    b, e, u = struct.unpack_from('<III', pd, i)
    if b and TVA <= b < TVA + len(TB):
        funcs.append((b, e))
funcs.sort()
n = len(funcs)
starts = [b for b, e in funcs]
def fidx(rva):
    i = bisect.bisect_right(starts, rva) - 1
    if i >= 0 and funcs[i][0] <= rva < funcs[i][1]:
        return i
    return -1

iat = {}
for d in pe.DIRECTORY_ENTRY_IMPORT:
    for i in d.imports:
        if i.name:
            iat[i.address - IMG] = i.name.decode()

dm = pe.get_memory_mapped_image()
def cstr(rva):
    if not (0 <= rva < len(dm) - 4):
        return None
    s = dm[rva:rva + 96].split(b'\0')[0]
    if len(s) >= 4 and all(32 <= c < 127 for c in s):
        return s.decode('latin1')
    return None

def worker(rng):
    md = Cs(CS_ARCH_X86, CS_MODE_64); md.detail = True
    res = []
    for fi in rng:
        b, e = funcs[fi]
        calls, drefs, daddrs = set(), {}, set()
        for i in md.disasm(TB[b - TVA:e - TVA], IMG + b):
            m = i.mnemonic
            if m in ('call', 'jmp'):
                ops = i.operands
                if ops and ops[0].type == X86_OP_IMM:
                    t = ops[0].imm - IMG
                    if TVA <= t < TVA + len(TB):
                        calls.add(t)
            for o in i.operands:
                if o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP:
                    t = i.address + i.size + o.mem.disp - IMG
                    if t in iat:
                        drefs[t] = 'IAT:' + iat[t]
                    else:
                        daddrs.add(t)
                        if not (TVA <= t < TVA + len(TB)):
                            s = cstr(t)
                            if s:
                                drefs[t] = '"' + s[:80] + '"'
        res.append((fi, calls, drefs, daddrs))
    return res

if __name__ == '__main__':
    nw = 14
    chunks = [list(range(i, n, nw * 8)) for i in range(nw * 8)]
    with mp.Pool(nw) as p:
        res = p.map(worker, chunks)
    calls = [None] * n; drefs = [None] * n; daddrs = [None] * n
    for r in res:
        for fi, c, d, a in r:
            calls[fi] = c; drefs[fi] = d; daddrs[fi] = a
    adj = [[] for _ in range(n)]
    for fi in range(n):
        for t in calls[fi]:
            j = fidx(t)
            if j >= 0:
                adj[fi].append(j)
    adj = [sorted(set(a)) for a in adj]
    # vtable slots: consecutive qwords in .rdata/.data(raw) pointing at pdata function starts
    RB = S['.rdata'].get_data(); RVA = S['.rdata'].VirtualAddress
    DB = S['.data'].get_data(); DVA = S['.data'].VirtualAddress
    vt_of = collections.defaultdict(list)   # func idx -> [(vt_start_rva, slot)]
    vt_start_refs = collections.defaultdict(set)  # vt_start_rva -> func idxs referencing it
    for buf, va in ((RB, RVA), (DB, DVA)):
        for off in range(0, len(buf) - 8, 8):
            q = int.from_bytes(buf[off:off + 8], 'little')
            r = q - IMG
            if TVA <= r < TVA + len(TB):
                j = fidx(r)
                if j >= 0 and funcs[j][0] == r:
                    # vtable run start: previous qword not a text ptr
                    prev_ok = True
                    if off >= 8:
                        pq = int.from_bytes(buf[off - 8:off], 'little')
                        pr = pq - IMG
                        prev_ok = not (TVA <= pr < TVA + len(TB) and fidx(pr) >= 0 and funcs[fidx(pr)][0] == pr)
                    st = off if prev_ok else None
                    if st is not None:
                        vt_of[j].append((va + off, 0))
    # compute run starts properly: a slot belongs to a run; record run start by walking back
    vt_of = collections.defaultdict(list)
    allslots = []  # (rva, func_idx) sorted
    for buf, va in ((RB, RVA), (DB, DVA)):
        for off in range(0, len(buf) - 8, 8):
            q = int.from_bytes(buf[off:off + 8], 'little')
            r = q - IMG
            if TVA <= r < TVA + len(TB):
                j = fidx(r)
                if j >= 0 and funcs[j][0] == r:
                    allslots.append((va + off, j))
    allslots.sort()
    # group consecutive slots into runs (stride 8)
    runs = []
    cur = [allslots[0]] if allslots else []
    for prev, curitem in zip(allslots, allslots[1:]):
        if curitem[0] == prev[0] + 8:
            cur.append(curitem)
        else:
            runs.append(cur); cur = [curitem]
    if cur:
        runs.append(cur)
    for run in runs:
        st = run[0][0]
        for k, (_, j) in enumerate(run):
            vt_of[j].append((st, k))
    vt_starts = set(r[0][0] for r in runs)
    pickle.dump({'funcs': funcs, 'adj': adj, 'drefs': drefs, 'daddrs': daddrs,
                 'vt_of': dict(vt_of), 'vt_starts': vt_starts, 'IMG': IMG},
                open(os.path.join(OUT, 'graph.pkl'), 'wb'))
    print(f"funcs={n} edges={sum(len(a) for a in adj)} vtable_slots={len(allslots)} runs={len(runs)}")
