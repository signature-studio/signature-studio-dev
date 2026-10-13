#!/usr/bin/env python3
"""gen_setter_scen.py <out> [N] [seed] — FA-8 シナリオ: Filter model ctor → setter 0x1803debc0(M,id,v) 列 → process。
全トークン hex。形式: sidx type nset {id val_bits}* ncalls seed32
ID 母集団: DSP 実読出し {1,2,3,4,416} / FA-7 対象 {0x156..0x15b} / 汎用バンク 311..410 / 別バンク 155..254 / 全域 0..416。
先頭 8 本は固定 (type 0..7 × 対象 ID 0x157,0x158,0x15a 同時) で、型別実測 (#648 項目 3) を必ず含める。"""
import random, struct, sys
out = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 200; seed = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0xFA8
rnd = random.Random(seed)
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
def val():
    r = rnd.random()
    if r < 0.5: return fb(rnd.uniform(0, 1))
    if r < 0.8: return fb(rnd.uniform(0, 100))
    if r < 0.9: return fb(rnd.uniform(-1, 1))
    return fb(10 ** rnd.uniform(1.3, 4.3))
pool_dsp = [1, 2, 3, 4, 416]; pool_fa7 = [0x156, 0x157, 0x158, 0x159, 0x15a, 0x15b]
def pick_id():
    r = rnd.random()
    if r < 0.30: return rnd.choice(pool_dsp)
    if r < 0.55: return rnd.choice(pool_fa7)
    if r < 0.75: return rnd.randrange(311, 411)
    if r < 0.85: return rnd.randrange(155, 255)
    return rnd.randrange(0, 417)
def sets_fix(sets):
    # ID 416 (0x1a0) は整数 enum (descriptor def=1, DSP は x2 して使う)。float bits を渡すと process が範囲外で落ちる (実測: 40 本中 4 本が native/wasm とも PROCERR)
    return [(a, rnd.choice([0, 1, 2, 3, 4]) if a == 416 else v) for a, v in sets]
lines = []
for i in range(N):
    if i < 8:
        typ = i; sets = [(0x157, fb(0.7819324)), (0x158, fb(0.8366389)), (0x15a, fb(0.0))]
    else:
        typ = rnd.choice([0, 1, 2, 3, 4, 5, 6, 7]); sets = [(pick_id(), val()) for _ in range(rnd.choice([1, 1, 2, 3, 5, 8]))]
    sets = sets_fix(sets)
    tok = [i, typ, len(sets)]
    for a, v in sets: tok += [a, v]
    tok += [rnd.choice([1, 2, 3]), rnd.randrange(1, 1 << 32)]
    lines.append(' '.join('%x' % x for x in tok))
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', len(lines))
