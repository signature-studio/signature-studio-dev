#!/usr/bin/env python3
"""gen_sc_smoke_scen.py <out> [N] [seed] — Stereo / VocalFilter の smoke 用シナリオ (判定はしない)。

形式は gen_filter_scen.py と同じ (sidx ncalls { nW {region off val}* n L[n] R[n] }*)。
パラメータの offset は未対応のため、書くのはサンプルレート (S+0x98) だけ。
入力は乱数の音声。nW=0 の call を 1 つ以上入れ、状態の遷移も通す。n<=64。
"""
import random, struct, sys
out = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 20; seed = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x5C5C
rnd = random.Random(seed)
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
def sample():
    return rnd.choice([-1, 1]) * (10 ** rnd.uniform(-4, 0.2))
lines = []
for i in range(N):
    nc = rnd.choice([1, 2, 3])
    tok = [i, nc]
    for c in range(nc):
        w = [(0, 0x98, fb(rnd.choice([44100.0, 48000.0, 96000.0])))] if c == 0 else []
        n = rnd.randrange(1, 65)
        tok += [len(w)]
        for r, o, v in w: tok += [r, o, v]
        tok += [n] + [fb(sample()) for _ in range(2 * n)]
    lines.append(' '.join('%x' % t for t in tok))
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', out, len(lines), 'scenarios')
