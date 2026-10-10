#!/usr/bin/env python3
"""gen_ctl_scen.py <out> <mode> [N] [seed] — FA-2c FreshAirDsp 制御層 検証シナリオ生成。

mode:
  epf    — factory .epf 8 本 (実測 macro bits) × 実チェーン (FRAR/DUMP: F,C,F,C,G,C,G,G) × audio 変化
  fuzz   — 構造化 + 乱数 (chain / macro / 制御パラメータ注入: latency, active, bypass, sr, host float)
  e2e    — epf + fuzz の合成 (lift2_e2e.sh 用)

scenario 行: sidx ncalls chain mid high trim nP (rg off val)*  | per call: n (L R)* nP2 (rg off val)*
  rg: 0=F 1=PH 2+i=CH[i] 0xa+i=D[i]S 0x12+i=P[i], 0x20 bit = 1byte 書込
子 DspModel の初期パラメタは FA-2b の語彙 (gen_comp_scen / gen_filter_scen) を per-child で注入。
"""
import random, struct, sys

out = sys.argv[1]; mode = sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 8
seed = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0xFACADE
rnd = random.Random(seed)
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]

# factory .epf 8 本 (実測): Mid Air / High Air / Trim
EPF = [
    ("Mixbus Polish", 0x3e9c28f2, 0x3e4f5c24, 0xbf6e1540),
    ("Shiny", 0x3f2c28f6, 0x3f400003, 0x00000000),
    ("Mixbus Sparkle", 0x3e999995, 0x3ece1474, 0xbfb47ae0),
    ("Vocal Bus Presence", 0x3eccb0a5, 0x3e9ac51d, 0x00000000),
    ("Presence Pop", 0x3f31eb85, 0x3e4cccc7, 0x00000000),
    ("Hat Lifter", 0x3ecb8519, 0x3f0d709a, 0x00000000),
    ("Vocal Air", 0x3f0cccc6, 0x3eb33326, 0x00000000),
    ("Clap Lifter", 0x3ee6666a, 0x3f3f5c21, 0x00000000),
]
# FRAR/DUMP 実チェーン (出現順): Filter, Compressor, Filter, Compressor, Gain, Compressor, Gain, Gain
# encode: comp=0 filter=1 gain=2, child i → 2i bit
CHAIN_REAL = [1, 0, 1, 0, 2, 0, 2, 2]
def chain_val(ch):
    v = 0
    for i, t in enumerate(ch): v |= (t & 3) << (2 * i)
    return v

R_F, R_PH, R_CH, R_DS, R_DP, R_BYTE = 0, 1, 2, 0xa, 0x12, 0x20
SR = lambda: rnd.choice([44100.0, 48000.0, 96000.0, 22050.0])
def sample():
    r = rnd.random()
    if r < 0.05: return 0.0
    if r < 0.08: return struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    if r < 0.11: return -struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    return rnd.choice([-1, 1]) * (10 ** rnd.uniform(-5, 0.8))
def lg(lo, hi): return 10 ** rnd.uniform(lo, hi)
def rf(lo, hi): return rnd.uniform(lo, hi)

def child_pokes(t, i, first):
    """子 DspModel (type t) の FA-2b 語彙パラメタ (reg codes: DS=0xa+i, DP=0x12+i)"""
    w = []
    if first:
        w.append((R_DS + i, 0x98, fb(SR())))
    if t == 0:      # Compressor
        w += [(R_DS + i, o, fb(x)) for o, x in (
            (0xa4, rf(0, 1)), (0xa8, lg(-4, 0.3)), (0xac, lg(-1, 1)), (0xb0, lg(-4, -1)),
            (0xb8, rf(0, 1)), (0xbc, rf(0, 1)), (0xc0, lg(-3, 0.3)), (0xc4, lg(-3, 0.3)),
            (0xd4, rf(0, 1)), (0xd8, rf(0, 1)), (0xe0, lg(-3, 0.3)), (0xe4, lg(-3, 0.3)),
            (0xf0, rf(0, 1)), (0xf4, lg(-2, 0.3)), (0xf8, rf(0, 1)), (0x100, rf(0, 1)),
            (0xec, rf(0, 1)), (0xe8, rf(0, 8)))]
        w += [(R_DP + i, o, fb(x)) for o, x in (
            (0x9dc4, lg(-4, 0)), (0x9e0c, lg(-3, 0.3)), (0x9ea8, rnd.choice([0.0, rf(0, 2), 1.0, 1.5])),
            (0x9ee4, lg(-0.3, 1)), (0x9f2c, lg(-1, 0.5)), (0x9fb8, lg(-3, 0.3)), (0x9fbc, lg(-3, 0.3)),
            (0x9f70, lg(-3, 0.3)), (0x9f74, lg(-3, 0.3)), (0xa000, lg(-3, 0.3)), (0xa004, lg(-3, 0.3)),
            (0xa0a0, lg(-1, 1.2)))]
        w += [(R_BYTE + R_DP + i, o, rnd.choice([0, 1])) for o in (0x9ffb, 0x9fb3, 0xa043)]
        w.append((R_DP + i, 0x9e54, rnd.choice([0, 1, 2])))
    elif t == 1:    # Filter
        w += [(R_DP + i, o, v) for o, v in (
            (0x9dc4, rnd.choice([0, 1, 2, 3, 4, 5, 6, 7])),
            (0x9ee4, rnd.choice([0, 1, 1, 2, 3, 4])),
            (0x9e0c, fb(lg(1.3, 4.3))), (0x9e54, fb(lg(-1, 1))), (0x9e9c, fb(lg(-1, 1))))]
        w.append((R_DP + i, 0xa0a0, fb(lg(-1, 1.2))))
    else:           # Gain
        w += [(R_DP + i, o, fb(x)) for o, x in (
            (0x9dc4, lg(-2, 0.5)), (0x9e0c, fb(rf(0, 1))), (0xa0a0, lg(-1, 1.2)))]
    return w

def ctl_pokes():
    """制御パラメータ注入 (F/CH/D の制御フィールド)"""
    w = []
    if rnd.random() < 0.5:
        i = rnd.randrange(8)
        w.append((R_DS + i, 0x58, rnd.choice([0, 0, 1, 3, 7, 64, 512])))       # latency
    if rnd.random() < 0.4:
        i = rnd.randrange(8)
        w.append((R_BYTE + R_DS + i, 0x60, rnd.choice([0, 0, 1])))             # active flag
    if rnd.random() < 0.4:
        i = rnd.randrange(8)
        w.append((R_BYTE + R_DS + i, 0x10, rnd.choice([0, 1])))                # dirty
    if rnd.random() < 0.3:
        i = rnd.randrange(8)
        w.append((R_DS + i, 0x5c, rnd.choice([0x7fffffff, 0, 1, 128])))        # countdown
    if rnd.random() < 0.3:
        w.append((R_BYTE + R_F, 0x10, rnd.choice([0, 1])))                     # F dirty
    return w

def emit(out_lines, sidx, ncalls, ch, mid, high, trim, inject):
    pokes = child_pokes(ch[0], 0, True) if inject else []
    for i in range(1, 8):
        if inject or rnd.random() < 0.5:
            pokes += child_pokes(ch[i], i, True)
    if inject:
        pokes += ctl_pokes()
    tok = [sidx, ncalls, chain_val(ch), mid, high, trim, len(pokes)]
    for rg, o, v in pokes: tok += [rg, o, v]
    for c in range(ncalls):
        n = rnd.choice([0, 1, 2, 3, 7, 16, 31, 64, 100]) if rnd.random() < .6 else rnd.randrange(1, 129)
        tok += [n] + [fb(sample()) for _ in range(2 * n)]
        p2 = []
        if inject and rnd.random() < 0.4:
            i = rnd.randrange(8)
            t = ch[i]
            if t == 0: p2.append((R_DP + i, 0x9dc4, fb(lg(-4, 0))))
            elif t == 1: p2.append((R_DP + i, 0x9dc4, rnd.choice([0, 1, 2, 3, 4, 5, 6])))
            else: p2.append((R_DP + i, 0x9dc4, fb(lg(-2, 0.5))))
            if rnd.random() < 0.4: p2.append((R_DS + i, 0x58, rnd.choice([0, 1, 5, 31])))
            if rnd.random() < 0.3: p2.append((R_DP + i, 0xa0a0, fb(lg(-1, 1.2))))
        tok += [len(p2)]
        for rg, o, v in p2: tok += [rg, o, v]
    out_lines.append(' '.join('%x' % t for t in tok))

lines = []
if mode in ('epf', 'e2e'):
    for k, (nm, mid, high, trim) in enumerate(EPF):
        for rep in range(max(1, N // 8)):
            nc = rnd.choice([1, 2, 3])
            emit(lines, 0x100 + k * 10 + rep, nc, CHAIN_REAL, mid, high, trim, inject=False)
if mode in ('fuzz', 'e2e'):
    nf = N if mode == 'fuzz' else N * 4
    for j in range(nf):
        ch = [rnd.choice([0, 1, 2]) for _ in range(8)]
        mid = fb(rnd.choice([0.0, rf(0, 1), rf(0, 1), 1.0, lg(-3, 0.3)]))
        high = fb(rnd.choice([0.0, rf(0, 1), rf(0, 1), 1.0, lg(-3, 0.3)]))
        trim = fb(rnd.choice([0.0, rf(-2, 2), rf(-1, 1), lg(-2, 0.5)]))
        nc = rnd.choice([1, 1, 2, 2, 3, 4])
        emit(lines, 0x200 + j, nc, ch, mid, high, trim, inject=True)
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', out, len(lines), 'scenarios')
