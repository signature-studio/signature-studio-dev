#!/usr/bin/env python3
"""FP-arithmetic density per 256KB .text window + FP-heavy function totals (from work/win64_census.json)."""
import json, collections
d = json.load(open('work/win64_census.json'))['funcs']
tot = sum(s for _, s, _ in d)
for thr in (10, 30, 100):
    sel = [(a, s, f) for a, s, f in d if f.get('sse_scalar_fp', 0) + f.get('sse_packed_fp', 0) >= thr]
    print(f"FP-arith>={thr}: {len(sel)} funcs, {sum(s for _, s, _ in sel)} bytes ({100*sum(s for _, s, _ in sel)/tot:.1f}% of pdata func bytes)")
b = collections.defaultdict(lambda: [0, 0, 0])
for a, s, f in d:
    k = (int(a, 16) - 0x180000000) // 0x40000
    b[k][0] += s; b[k][1] += f.get('sse_scalar_fp', 0) + f.get('sse_packed_fp', 0); b[k][2] += 1
print("window(256KB)       bytes  fpops funcs  fp/KB")
for k in sorted(b):
    s, fp, n = b[k]
    print(f"0x{0x180000000 + k * 0x40000:x} {s:>8} {fp:>6} {n:>5}  {fp / (s / 1024) if s else 0:5.1f} " + '#' * int(fp / (s / 1024) * 2 if s else 0))
