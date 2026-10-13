#!/usr/bin/env python3
"""SR-1d (#340): static call-graph path search over the sr3_index.py refs (direct call/jmp only; indirect calls invisible).
usage: sr1d_callpath.py <index.npz> region <lo_va> <hi_va>            # external callers INTO [lo,hi)
       sr1d_callpath.py <index.npz> path <from_va> <lo_va> <hi_va> [maxdepth]   # shortest direct-call path from_va -> any func in [lo,hi)
       sr1d_callpath.py <index.npz> callees <va>                     # direct callees of function containing va"""
import sys, bisect
import numpy as np

IMG = 0x180000000
z = np.load(sys.argv[1]); funcs = z['funcs']; refs = z['refs']
fstarts = funcs[:, 0].tolist()


def fi(rva):
    i = bisect.bisect_right(fstarts, rva) - 1
    return i if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else -1


adj = {}; radj = {}
for s, t, k in refs.tolist():
    if k not in (1, 2):
        continue
    a, b = fi(s), fi(t)
    if a < 0 or b < 0 or a == b:
        continue
    adj.setdefault(a, set()).add(b); radj.setdefault(b, set()).add(a)
V = lambda i: hex(int(funcs[i][0]) + IMG)
mode = sys.argv[2]
if mode == 'region':
    lo, hi = int(sys.argv[3], 16) - IMG, int(sys.argv[4], 16) - IMG
    inside = {i for i in range(len(funcs)) if lo <= funcs[i][0] < hi}
    print(f'funcs_in_region={len(inside)}')
    ent = {}
    for b in inside:
        for a in radj.get(b, ()):
            if a not in inside:
                ent.setdefault(b, set()).add(a)
    for b in sorted(ent):
        print(f'entry {V(b)} <- ' + ','.join(sorted(V(a) for a in ent[b])))
elif mode == 'callees':
    i = fi(int(sys.argv[3], 16) - IMG)
    print(V(i), '->', ' '.join(sorted(V(c) for c in adj.get(i, ()))))
elif mode == 'path':
    src = fi(int(sys.argv[3], 16) - IMG)
    lo, hi = int(sys.argv[4], 16) - IMG, int(sys.argv[5], 16) - IMG
    md = int(sys.argv[6]) if len(sys.argv) > 6 else 6
    prev = {src: None}; front = [src]; found = None
    for d in range(md):
        nxt = []
        for x in front:
            for y in adj.get(x, ()):
                if y in prev:
                    continue
                prev[y] = x; nxt.append(y)
                if lo <= funcs[y][0] < hi and found is None:
                    found = y
        if found is not None:
            break
        front = nxt
    if found is None:
        print(f'NO PATH within depth {md} (reached {len(prev)} funcs)')
    else:
        p = []; x = found
        while x is not None:
            p.append(V(x)); x = prev[x]
        print(' -> '.join(reversed(p)))
