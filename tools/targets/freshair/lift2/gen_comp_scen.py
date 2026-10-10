#!/usr/bin/env python3
"""gen_comp_scen.py <out> [N] [seed] — Compressor process 検証シナリオ (決定的 seed, NaN/Inf 入力は生成しない)。
S/P 内の意味不明フィールドは実使用域の乱数 + 複数 call で状態遷移 (Δ=0 no-ramp / ramp / first フラグ / モード 0-2 / sidechain)。"""
import random, struct, sys
out = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 400; seed = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0xC0FFEE
rnd = random.Random(seed)
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
def sample():
    r = rnd.random()
    if r < 0.04: return 0.0
    if r < 0.07: return struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    if r < 0.10: return -struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    return rnd.choice([-1, 1]) * (10 ** rnd.uniform(-5, 0.8))
def rf(lo, hi): return rnd.uniform(lo, hi)
def lg(lo, hi): return 10 ** rnd.uniform(lo, hi)
def params():
    w = []
    def S(o, v): w.append((0, o, fb(v)))
    def P(o, v): w.append((1, o, fb(v)))
    S(0x98, rnd.choice([44100.0, 48000.0, 96000.0, 22050.0, float(rnd.randrange(8000, 192001))]))
    S(0xa4, rf(0, 1)); S(0xa8, lg(-4, 0.3)); S(0xac, lg(-1, 1)); S(0xb0, lg(-4, -1)); S(0xb8, rf(0, 1)); S(0xbc, rf(0, 1))
    S(0xc0, lg(-3, 0.3)); S(0xc4, lg(-3, 0.3)); S(0xd4, rf(0, 1)); S(0xd8, rf(0, 1)); S(0xe0, lg(-3, 0.3)); S(0xe4, lg(-3, 0.3))
    S(0xf0, rf(0, 1)); S(0xf4, lg(-2, 0.3)); S(0xf8, rf(0, 1)); S(0x100, rf(0, 1)); S(0xec, rf(0, 1)); S(0xe8, rf(0, 8))
    w.append((0x10, 0xfc, rnd.choice([0, 1])))
    P(0x9dc4, lg(-4, 0)); P(0x9e0c, lg(-3, 0.3)); w.append((1, 0x9e54, rnd.choice([0, 1, 2, 0, 1, 2, 3])))
    P(0x9ea8, rnd.choice([0.0, rf(0, 2), rf(0, 2), 1.0, 1.5])); P(0x9ee4, lg(-0.3, 1)); P(0x9f2c, lg(-1, 0.5))
    P(0x9fb8, lg(-3, 0.3)); P(0x9fbc, lg(-3, 0.3)); P(0x9f70, lg(-3, 0.3)); P(0x9f74, lg(-3, 0.3)); P(0xa000, lg(-3, 0.3)); P(0xa004, lg(-3, 0.3))
    for o in (0x9ffb, 0x9fb3, 0xa043): w.append((0x11, o, rnd.choice([0, 1])))
    P(0xa0a0, lg(-1, 1.2))        # host vtable fn が返す値 (this+8)
    return w
def change():
    w = []
    for _ in range(rnd.randrange(0, 4)):
        c = rnd.choice(['pa', 'pb', 'host', 'sr', 'mode', 'flag'])
        if c == 'pa': w.append((1, 0x9dc4, fb(lg(-4, 0))))
        elif c == 'pb': w.append((1, 0x9e0c, fb(lg(-3, 0.3))))
        elif c == 'host': w.append((1, 0xa0a0, fb(lg(-1, 1.2))))
        elif c == 'sr': w.append((0, 0x98, fb(rnd.choice([44100.0, 48000.0, 96000.0]))))
        elif c == 'mode': w.append((1, 0x9e54, rnd.choice([0, 1, 2])))
        else: w.append((0x11, rnd.choice([0x9ffb, 0x9fb3, 0xa043]), rnd.choice([0, 1])))
    return w
lines = []
for i in range(N):
    nc = rnd.choice([1, 2, 2, 3, 4])
    tok = [i, nc, rnd.choice([64, 64, 64, 12, 8, 4, 0, 16])]    # vector 初期容量 (bytes): <12 で grow 経路 (lift した realloc) に到達
    for c in range(nc):
        w = params() if c == 0 else change()
        n = rnd.choice([0, 1, 2, 3, 7, 16, 31, 64]) if rnd.random() < .5 else rnd.randrange(1, 129)
        tok += [len(w)]
        for r, o, v in w: tok += [r, o, v]
        tok += [n] + [fb(sample()) for _ in range(2 * n)]
        sc = rnd.random() < 0.2
        tok += [1 if sc else 0]
        if sc: tok += [fb(sample()) for _ in range(2 * n)]
    lines.append(' '.join('%x' % t for t in tok))
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', out, len(lines), 'scenarios')
