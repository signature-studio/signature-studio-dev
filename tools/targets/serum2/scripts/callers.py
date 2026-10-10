#!/usr/bin/env python3
"""Callers (multi-level) from the pickled static graph. usage: callers.py <VA hex> [depth]"""
import pickle, sys, bisect
g = pickle.load(open('work/win64_closure_graph.pkl', 'rb'))
funcs, adj, IMG = g['funcs'], g['adj'], g['IMG']
n = len(funcs); starts = [b for b, e in funcs]
radj = [[] for _ in range(n)]
for i in range(n):
    for j in adj[i]:
        if j != i: radj[j].append(i)
fidx = lambda rva: bisect.bisect_right(starts, rva) - 1
t = fidx(int(sys.argv[1], 16) - IMG); depth = int(sys.argv[2]) if len(sys.argv) > 2 else 2
seen = {t}; front = [t]
for d in range(depth):
    nxt = []
    for x in front:
        cs = [c for c in radj[x] if c not in seen]
        print('  ' * d + f"{hex(IMG + funcs[x][0])} <- {[hex(IMG + funcs[c][0]) for c in cs[:10]]}{' ...' if len(cs) > 10 else ''}")
        for c in cs: seen.add(c); nxt.append(c)
    front = nxt[:30]
