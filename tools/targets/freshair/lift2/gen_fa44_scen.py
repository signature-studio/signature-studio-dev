#!/usr/bin/env python3
"""gen_fa44_scen.py <out> [N] [seed] — FA-44 (Delay / Disperser / Phaser / QuickEq の SC process) の smoke 用シナリオ。
判定はしない。1 call 目に S+0x98 へ sample rate を書き、各 call で n 個の L/R サンプルを入れる。
param の offset→意味は未確定のため、S/P への追加書込は入れない (REPORT_APPENDIX_FA44.md §4)。"""
import random, struct, sys
out = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 20; seed = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0xFA44
rnd = random.Random(seed)
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
def sample():
    r = rnd.random()
    if r < 0.04: return 0.0
    if r < 0.07: return struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    return rnd.choice([-1, 1]) * (10 ** rnd.uniform(-5, 0.5))
lines = []
for i in range(N):
    nc = rnd.choice([1, 2, 3])
    tok = [i, nc]
    for c in range(nc):
        w = [(0, 0x98, fb(rnd.choice([44100.0, 48000.0, 96000.0, 22050.0])))] if c == 0 else []
        n = rnd.choice([1, 2, 3, 7, 16, 31, 32, 64]) if rnd.random() < .5 else rnd.randrange(1, 65)
        tok += [len(w)]
        for r, o, v in w: tok += [r, o, v]
        tok += [n] + [fb(sample()) for _ in range(2 * n)]
    lines.append(' '.join('%x' % t for t in tok))
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', out, len(lines), 'scenarios')
