#!/usr/bin/env python3
"""cov_summary.py <rep.json> <hit.json> — 関数別の命令カバレッジ集計 (mlift --cov の bitmap 由来)"""
import json, sys
rep = json.load(open(sys.argv[1])); hit = json.load(open(sys.argv[2]))
funcs = rep['funcs']
begins = sorted(int(k, 16) for k in funcs)
import bisect
agg = {}
for va, h in hit.items():
    v = int(va, 16); i = bisect.bisect_right(begins, v) - 1
    f = begins[i]; a = agg.setdefault(f, [0, 0]); a[0] += 1; a[1] += 1 if h else 0
tot = [0, 0]
rows = []
for f, (n, c) in sorted(agg.items(), key=lambda x: -x[1][0]):
    rows.append((f, funcs['%x' % f]['size'], n, c)); tot[0] += n; tot[1] += c
for f, sz, n, c in rows[:int(sys.argv[3]) if len(sys.argv) > 3 else 12]:
    print('  f_%x %5dB insns %4d covered %4d (%.1f%%)' % (f, sz, n, c, 100.0 * c / n))
print('TOTAL closure insns %d covered %d (%.1f%%)' % (tot[0], tot[1], 100.0 * tot[1] / tot[0]))
