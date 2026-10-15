#!/usr/bin/env python3
"""gen_vf_scen.py <out> [N] [seed] — VocalFilter の SC/KH 同一入力シナリオ (#4071)。形式は gen_filter_scen.py と同じ。
P の書込み先 (SC 側 offset): 0x9dc4 = 周波数 A, 0x9e0c = 周波数 B, 0x9e54 = Q, 0x9e9c = flag1 (0/1), 0x9ee4 = flag2 (0/1)。
S+0x98 = サンプルレート。flag は 0/1 のみ (SC は非 0 判定、KH は &1 で読むため、2 以上は両側で一致しない)。
"""
import random, struct, sys
out = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 200; seed = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x5F17E4
rnd = random.Random(seed)
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
def sample():
    r = rnd.random()
    if r < 0.04: return 0.0
    if r < 0.07: return struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    return rnd.choice([-1, 1]) * (10 ** rnd.uniform(-5, 0.5))
def lg(lo, hi): return 10 ** rnd.uniform(lo, hi)
def params(first=False):
    w = []
    if first: w.append((0, 0x98, fb(rnd.choice([44100.0, 48000.0, 96000.0, 88200.0]))))
    w.append((1, 0x9dc4, fb(lg(1.3, 4.3))))
    w.append((1, 0x9e0c, fb(lg(1.3, 4.3))))
    w.append((1, 0x9e54, fb(lg(-1, 1.5))))
    w.append((1, 0x9e9c, rnd.choice([0, 1])))
    w.append((1, 0x9ee4, rnd.choice([0, 1])))
    return w
lines = []
for i in range(N):
    nc = rnd.choice([1, 2, 3, 3, 4, 5])
    tok = [i, nc]
    for c in range(nc):
        w = params(c == 0) if (c == 0 or rnd.random() < 0.6) else []
        n = rnd.choice([1, 2, 3, 7, 16, 31, 32, 64]) if rnd.random() < .5 else rnd.randrange(1, 65)
        tok += [len(w)]
        for r, o, v in w: tok += [r, o, v]
        tok += [n] + [fb(sample()) for _ in range(2 * n)]
    lines.append(' '.join('%x' % t for t in tok))
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', out, len(lines), 'scenarios')
