#!/usr/bin/env python3
"""gen_fuzz_scen.py <target:comp|filter> <out> <N_structured> <N_fuzz> [seed]

ctx-fuzz シナリオ生成 (CAB-48 FA-2)。
- structured: 型/次数/周波数帯/Q/gain/n を計画的にスイープする 200 シナリオ (crossfade・多 call 含む)
- fuzz: 乱数試行。ctx (S/P/ctx 領域) への書き込み位置・パラメタ・サンプルを境界値 (±0, 非正規数, 巨大/極小,
  最大 n) から乱数選択。NaN/Inf 入力は除外 (x86 と wasm の NaN payload 差の切り分け, liftlib 制約と同一)。

シナリオ形式 (16進):
- filter: <sidx> <ncalls> { <nW> {<rg> <off> <val>}* <n> <L[n]> <R[n]> }*
- comp:   <sidx> <ncalls> <vcap> { <nW> {<rg> <off> <val>}* <n> <L[n]> <R[n]> <hasSC> [<SL[n]> <SR[n]>] }*
  (rg 0=S 1=P 2=ctx 3=Q, 0x10 bit=1 byte 書込。vcap < 12 で vector grow 経路に到達)
"""
import random, struct, sys

target = sys.argv[1]
out = sys.argv[2]
N_S = int(sys.argv[3]) if len(sys.argv) > 3 else 200
N_F = int(sys.argv[4]) if len(sys.argv) > 4 else 1000
seed = int(sys.argv[5], 0) if len(sys.argv) > 5 else 0xFA2C48

fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
rnd = random.Random(seed)


def sample(r=rnd):
    r6 = r.random()
    if r6 < 0.05:
        return 0.0
    if r6 < 0.09:      # 非正規数 / 最小通常数
        return struct.unpack('<f', struct.pack('<I', r.randrange(1, 0x00800001)))[0]
    if r6 < 0.12:      # 巨大 (有限)
        return struct.unpack('<f', struct.pack('<I', r.randrange(0x7f000000, 0x7f7fffff)))[0] * r.choice([-1, 1])
    return r.choice([-1, 1]) * (10 ** r.uniform(-9, 3))


def sample_comp(r=rnd):
    r6 = r.random()
    if r6 < 0.05:
        return 0.0
    if r6 < 0.09:
        return struct.unpack('<f', struct.pack('<I', r.randrange(1, 0x00800001)))[0] * r.choice([-1, 1])
    if r6 < 0.12:
        return struct.unpack('<f', struct.pack('<I', r.randrange(0x7f000000, 0x7f7fffff)))[0] * r.choice([-1, 1])
    return r.choice([-1, 1]) * (10 ** r.uniform(-6, 3))


def params_comp(first, r):
    """Compressor の観測パラメタ (gen_comp_scen の実使用域に準拠)。"""
    w = []
    if first:
        w.append((0, 0x98, fb(r.choice([44100.0, 48000.0, 96000.0, 22050.0, float(r.randrange(8000, 192001))]))))
        for o, lo, hi in ((0xa4, 0, 1), (0xa8, -4, 0.3), (0xac, -1, 1), (0xb0, -4, -1), (0xb8, 0, 1), (0xbc, 0, 1),
                          (0xc0, -3, 0.3), (0xc4, -3, 0.3), (0xd4, 0, 1), (0xd8, 0, 1), (0xe0, -3, 0.3), (0xe4, -3, 0.3),
                          (0xf0, 0, 1), (0xf4, -2, 0.3), (0xf8, 0, 1), (0x100, 0, 1), (0xec, 0, 1)):
            w.append((0, o, fb(10 ** r.uniform(lo, hi) if lo < 0 else r.uniform(lo, hi))))
        w.append((0, 0xe8, fb(r.uniform(0, 8))))
    slots = [0x9dc4, 0x9e0c, 0x9ea8, 0x9ee4, 0x9f2c, 0x9fb8, 0x9fbc, 0x9f70, 0x9f74, 0xa000, 0xa004, 0xa0a0]
    for _ in range(r.randint(1, 6)):
        s = r.choice(slots)
        kind = r.random()
        if kind < 0.25:
            v = fb(r.choice([0.0, 1.0, -1.0, 0.5, 1.5, 2.0]))
        elif kind < 0.6:
            v = fb(10 ** r.uniform(-3, 0.8))
        else:
            v = fb(r.uniform(-2, 2))
        w.append((1, s, v))
    for o in (0x9ffb, 0x9fb3, 0xa043):
        if r.random() < 0.4:
            w.append((0x11, o, r.choice([0, 1])))
    # 0xa118 (sidechain index) は harness が hasSC に応じて設定するため乱数書込しない
    # (sc 配列の entry1 以降は未初期化で, machine が NULL deref する)
    return w


def params_filter(first, r):
    w = []
    if first:
        w.append((0, 0x98, fb(r.choice([44100.0, 48000.0, 96000.0, 22050.0]))))
    w.append((1, 0x9dc4, r.randrange(0, 8)))                       # type enum (0..6 有効, 7 = default 経路)
    w.append((1, 0x9ee4, r.randrange(0, 6)))                       # order (×2 して渡される)
    w.append((1, 0x9e0c, fb(10 ** r.uniform(0.5, 4.4))))           # 周波数
    w.append((1, 0x9e54, fb(10 ** r.uniform(-2, 1.2))))            # Q
    w.append((1, 0x9e9c, fb(10 ** r.uniform(-2, 1.2))))            # gain
    return w


def emit_call_comp(tok, w, r):
    n = r.choice([0, 1, 2, 3, 7, 16, 31, 64]) if r.random() < .5 else r.randrange(1, 129)
    tok += [len(w)]
    for item in w:
        tok += [item[0], item[1], item[2]]
    tok += [n] + [fb(sample_comp(r)) for _ in range(2 * n)]
    sc = r.random() < 0.2
    tok += [1 if sc else 0]
    if sc:
        tok += [fb(sample_comp(r)) for _ in range(2 * n)]


def emit_call_filter(tok, w, r):
    n = r.choice([1, 2, 3, 7, 16, 31, 32, 64])
    tok += [len(w)]
    for item in w:
        tok += [item[0], item[1], item[2]]
    tok += [n] + [fb(sample(r)) for _ in range(2 * n)]


lines = []
idx = 0
# ---------- structured: 計画的スイープ ----------
if target == 'comp':
    types = [0, 1, 2, 3]
    freqs = [20.0, 100.0, 1000.0, 8000.0, 18000.0]
    for i in range(N_S):
        nc = 1 + (i % 4)
        tok = [idx, nc, 64]
        for c in range(nc):
            w = []
            if c == 0:
                w += [(0, 0x98, fb(48000.0))]
            w += [(1, 0x9dc4, fb(10 ** rnd.uniform(-4, 0)))]
            w += [(1, 0x9e0c, fb(freqs[(i + c) % len(freqs)]))]
            w += [(1, 0x9e54, rnd.choice([0, 1, 2, 3]))]
            w += [(1, 0x9e9c, fb(0.25 + 0.5 * ((i // 3) % 8)))]
            w += [(1, 0x9ea8, fb(rnd.choice([0.0, 1.0, 1.5])))]
            w += [(1, 0xa0a0, fb(rnd.uniform(-1, 1.2)))]
            emit_call_comp(tok, w, rnd)
        lines.append(' '.join('%x' % t for t in tok))
        idx += 1
else:
    for i in range(N_S):
        nc = 1 + (i % 5)
        tok = [idx, nc]
        for c in range(nc):
            w = []
            if c == 0:
                w += [(0, 0x98, fb(48000.0))]
            w += [(1, 0x9dc4, (i + c) % 8), (1, 0x9ee4, (i + c) % 6)]
            w += [(1, 0x9e0c, fb(10 ** (0.5 + 3.9 * ((i + c) % 20) / 19.0)))]
            w += [(1, 0x9e54, fb(10 ** (-2 + 3.2 * ((i // 2) % 15) / 14.0)))]
            w += [(1, 0x9e9c, fb(10 ** (-2 + 3.2 * ((i // 7) % 15) / 14.0)))]
            emit_call_filter(tok, w, rnd)
        lines.append(' '.join('%x' % t for t in tok))
        idx += 1

# ---------- fuzz: 乱数試行 ----------
r = random.Random(seed ^ 0xF00D)
for i in range(N_F):
    nc = r.choice([1, 1, 2, 2, 3, 4, 5])
    tok = [idx, nc] + ([64] if target == 'comp' else [])
    for c in range(nc):
        w = params_comp(c == 0, r) if target == 'comp' else params_filter(c == 0, r)
        if c > 0 and r.random() < 0.4:
            w = []                                    # パラメタ無変更 call (状態持越し)
        if target == 'comp':
            emit_call_comp(tok, w, r)
        else:
            emit_call_filter(tok, w, r)
    lines.append(' '.join('%x' % t for t in tok))
    idx += 1

open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote %s: %d scenarios (structured %d + fuzz %d)' % (out, len(lines), N_S, N_F))
