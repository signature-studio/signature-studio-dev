#!/usr/bin/env python3
"""gen_scen.py <out> [N] — gain::process 検証シナリオ (決定的 seed)。NaN/Inf を生まない値域のみ。
1 行 = hex トークン列:
 mode ga gb n first prev cur g0 c1 mL c2 mR f93 fdb v50 v98 | L[n] | R[n]   (float は bits, 他は整数)"""
import random, struct, sys
out, N = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400
rnd = random.Random(0xFA1E)
def fb(x): return struct.unpack('<I', struct.pack('<f', x))[0]
def rf(lo, hi): return rnd.uniform(lo, hi)
def sample():
    r = rnd.random()
    if r < 0.05: return 0.0
    if r < 0.10: return struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]  # denormal
    if r < 0.15: return -struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    return rnd.choice([-1, 1]) * 10 ** rnd.uniform(-4, 4)
lines = []
for i in range(N):
    mode = rnd.choice([0, 1]); ga = rf(0, 4); gb = rf(0, 4)
    k = rnd.random()
    n = rnd.choice([0, 1, 2, 3, 7, 16, 31, 64]) if k < .5 else rnd.randrange(1, 129)
    first = 1 if rnd.random() < .25 else 0
    tgt = gb * 2 if mode == 1 else ga          # 実効 target (gb*2 は addss と同値)
    kind = rnd.random()
    if kind < .2: prev = struct.unpack('<f', struct.pack('<f', tgt))[0]          # Δ=0 (no-ramp)
    elif kind < .3: prev = tgt + 1e-40                                           # |Δ|<1e-15 (denormal差)
    else: prev = rf(0, 4)
    cur = rf(0, 4); g0 = rf(0, 4); c1 = rf(0, 1); c2 = rf(0, 1); mL = rf(0, 2); mR = rf(0, 2)
    f93 = int(rnd.random() < .4); fdb = int(rnd.random() < .4)
    v50 = fb(rf(-2, 2)); v98 = fb(rf(-2, 2))
    L = [fb(sample()) for _ in range(n)]; R = [fb(sample()) for _ in range(n)]
    tok = [mode, fb(ga), fb(gb), n, first, fb(prev), fb(cur), fb(g0), fb(c1), fb(mL), fb(c2), fb(mR), f93, fdb, v50, v98] + L + R
    lines.append(' '.join('%x' % t for t in tok))
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', out, len(lines), 'scenarios')
