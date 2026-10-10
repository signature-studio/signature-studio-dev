#!/usr/bin/env python3
"""gen_filter_scen.py <out> [N] [seed] — Filter process 検証シナリオ。型/次数 enum + 周波数/Q/ゲイン + 複数 call (crossfade 状態遷移)。n<=64。"""
import random, struct, sys
out = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 200; seed = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0xF117E4
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
    if first: w.append((0, 0x98, fb(rnd.choice([44100.0, 48000.0, 96000.0, 22050.0]))))
    w.append((1, 0x9dc4, rnd.choice([0, 1, 2, 3, 4, 5, 6, 7])))      # type enum (0..6 有効, 7 は default 経路)
    w.append((1, 0x9ee4, rnd.choice([0, 1, 1, 2, 3, 4])))             # order/slope (x2 して渡される)
    w.append((1, 0x9e0c, fb(lg(1.3, 4.3))))                            # 周波数 [Hz]
    w.append((1, 0x9e54, fb(lg(-1, 1))))                               # Q / resonance
    w.append((1, 0x9e9c, fb(lg(-1, 1))))                               # gain/他
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
