#!/usr/bin/env python3
"""SR-3 step 3: boundary-window scan.  For a seed set of function VAs, report for every candidate window [lo,hi]
(in function-index space) the number of distinct *entry* functions (callee inside window, caller outside) and
the number of distinct window->outside callees.  A statically linked library laid out contiguously by lld shows
a sharp minimum of entries.  usage: sr3_window.py <index.npz> <lib> <seedVA,seedVA,...> [--grow N]"""
import sys, bisect
import numpy as np

IMG = 0x180000000
z = np.load(sys.argv[1]); funcs = z['funcs']; refs = z['refs']
lib = sys.argv[2]; seeds = [int(x, 16) - IMG for x in sys.argv[3].split(',')]
grow = int(sys.argv[sys.argv.index('--grow') + 1]) if '--grow' in sys.argv else 400
fs = funcs[:, 0].tolist(); n = len(fs)


def fi(rva):
    i = bisect.bisect_right(fs, rva) - 1
    return i if i >= 0 and funcs[i][0] <= rva < funcs[i][1] else -1


ed = refs[(refs[:, 2] == 1) | (refs[:, 2] == 2)]  # call + tail jmp
src = np.array([fi(int(s)) for s in ed[:, 0]]); dst = np.array([fi(int(t)) for t in ed[:, 1]])
m = (src >= 0) & (dst >= 0) & (src != dst)
src, dst = src[m], dst[m]
rip = refs[refs[:, 2] == 0]  # address-taken functions (vtable/fnptr targets appear as lea)
lea_dst = np.array([fi(int(t)) for t in rip[:, 1]]); lea_src = np.array([fi(int(s)) for s in rip[:, 0]])
mm = (lea_dst >= 0) & (lea_src >= 0) & (lea_src != lea_dst)
lsrc, ldst = lea_src[mm], lea_dst[mm]

si = sorted({fi(s) for s in seeds} - {-1})
lo0, hi0 = si[0], si[-1]


def stats(lo, hi):
    inside_dst = (dst >= lo) & (dst <= hi); inside_src = (src >= lo) & (src <= hi)
    entries = len(set(dst[inside_dst & ~inside_src].tolist()))
    exits = len(set(dst[inside_src & ~inside_dst].tolist()))
    ie = int((inside_dst & inside_src).sum())
    lent = len(set(ldst[(ldst >= lo) & (ldst <= hi) & ~((lsrc >= lo) & (lsrc <= hi))].tolist()))
    return entries, exits, ie, lent


print(f"# {lib}: seeds idx {lo0}..{hi0} (VA {hex(IMG+fs[lo0])}..{hex(IMG+int(funcs[hi0][1]))}), n_funcs={n}")
print("lo_ext hi_ext  window_funcs window_bytes  entries exits internal_edges leaFnEntries   lo_VA hi_VA_end")
best = []
step = max(1, grow // 40)
for dl in range(0, grow + 1, step):
    for dh in range(0, grow + 1, step):
        lo, hi = max(0, lo0 - dl), min(n - 1, hi0 + dh)
        e, x, ie, le = stats(lo, hi)
        w = hi - lo + 1; by = int(funcs[hi][1] - funcs[lo][0])
        best.append((e + le, e, x, ie, le, dl, dh, w, by, lo, hi))
best.sort(key=lambda r: (r[0], -r[8]))
for r in best[:12]:
    tot, e, x, ie, le, dl, dh, w, by, lo, hi = r
    print(f"{dl:>6} {dh:>6}  {w:>11} {by:>12}  {e:>7} {x:>5} {ie:>14} {le:>12}   {hex(IMG+fs[lo])} {hex(IMG+int(funcs[hi][1]))}")
