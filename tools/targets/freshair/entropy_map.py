#!/usr/bin/env python3
"""entropy_map.py <pe> — 64KB 窓エントロピーで高エントロピー(>7.5)領域を列挙 (暗号化/圧縮/ラッパ領域検出)"""
import sys, math, collections, pefile
pe = pefile.PE(sys.argv[1])
W = 65536
def ent(b):
    c = collections.Counter(b); n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values()) if n else 0
for s in pe.sections:
    nm = s.Name.rstrip(b'\0').decode()
    d = s.get_data()
    hi = []
    for o in range(0, len(d), W):
        e = ent(d[o:o + W])
        if e > 7.5: hi.append((o, round(e, 2)))
    tot = (len(d) + W - 1) // W
    print("%-8s windows=%4d  >7.5: %4d  %s" % (nm, tot, len(hi), (hi[:3] + ['...'] + hi[-2:]) if len(hi) > 6 else hi))
