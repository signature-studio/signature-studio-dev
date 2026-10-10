#!/usr/bin/env python3
"""Query the pickled graph: who calls top scalar-FP functions, which vtable class owns them."""
import pickle, json, collections, bisect
g = pickle.load(open('work/win64_closure_graph.pkl', 'rb'))
funcs, adj, vtables, IMG, cd, cg = g['funcs'], g['adj'], g['vtables'], g['IMG'], g['cd'], g['cg']
n = len(funcs); starts = [b for b, e in funcs]
radj = [[] for _ in range(n)]
for i in range(n):
    for j in adj[i]: radj[j].append(i)
fidx = lambda rva: bisect.bisect_right(starts, rva) - 1
m2c = collections.defaultdict(set)
for v, (nm, o, ms) in vtables.items():
    for m in ms: m2c[m].add(nm)
cen = {int(a, 16) - IMG: (sz, f) for a, sz, f in json.load(open('work/win64_census.json'))['funcs']}
top = sorted(cen.items(), key=lambda x: -x[1][1].get('sse_scalar_fp', 0))[:16]
for rva, (sz, f) in top:
    i = fidx(rva)
    print(hex(rva + IMG), sz, 'sc', f.get('sse_scalar_fp'), 'DSP' if i in cd else '-', 'GUI' if i in cg else '-', 'ncallers', len(radj[i]), list(m2c.get(rva, []))[:2], [hex(funcs[c][0] + IMG) for c in radj[i][:3]])
