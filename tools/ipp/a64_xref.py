#!/usr/bin/env python3
"""arm64 .dis (llvm-objdump) から adrp+add の対象 VA 参照を探す。usage: a64_xref.py dis VA..."""
import sys, re
dis = sys.argv[1]; targets = {int(x, 0): [] for x in sys.argv[2:]}
rx_adrp = re.compile(r'^\s*([0-9a-f]+):\s+adrp\s+(x\d+), (0x[0-9a-f]+)')
rx_add = re.compile(r'^\s*([0-9a-f]+):\s+add\s+(x\d+), (x\d+), #(0x[0-9a-f]+)')
pend = {}
with open(dis) as f:
    for ln in f:
        m = rx_adrp.match(ln)
        if m: pend[m.group(2)] = (int(m.group(1), 16), int(m.group(3), 16)); continue
        m = rx_add.match(ln)
        if m and m.group(3) in pend:
            a, base = pend[m.group(3)]
            t = base + int(m.group(4), 16)
            if t in targets: targets[t].append(int(m.group(1), 16))
            pend[m.group(2)] = (a, t)
for t, l in targets.items(): print(hex(t), [hex(x) for x in l])
