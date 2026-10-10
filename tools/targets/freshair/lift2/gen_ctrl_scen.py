#!/usr/bin/env python3
"""gen_ctrl_scen.py <out> [Nstructured] [Nrandom] [seed] — FA-2c FreshAirDsp 制御層の検証シナリオ。
先頭 8 本 = factory .epf 8 本の macro 値 (0x10/0x14 f32 = Mid Air / High Air, Trim=0) で駆動する固定シナリオ。
以降 = 構造化 (制御層状態注入: macro/子 meter/子 model param/wrapper fade 状態/ctx 拡張フィールド) + 乱数。
書式: sidx ncalls vcap { nW {rg off val}* n L[n] R[n] op [oparg] }*
  rg: bit0x100=1byte / region 0=F 1=M 2=ctx 0x10|k=W_k 0x20|k=P_k 0x30|k=C_k
  op: 0=process 1=slot4(f32) 2=slot3 3=slot13 4=slot7 5=slot9 6=slot8 7=slot16 8=slot5 9=slot10"""
import random, struct, sys, glob, os
out = sys.argv[1]
NS = int(sys.argv[2]) if len(sys.argv) > 2 else 200
NR = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
seed = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0xFA2C0001
rnd = random.Random(seed)
fb = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
def sample():
    r = rnd.random()
    if r < 0.05: return 0.0
    if r < 0.08: return struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    if r < 0.11: return -struct.unpack('<f', struct.pack('<I', rnd.randrange(1, 0x7fffff)))[0]
    return rnd.choice([-1, 1]) * (10 ** rnd.uniform(-5, 0.8))
def rf(lo, hi): return rnd.uniform(lo, hi)
def lg(lo, hi): return 10 ** rnd.uniform(lo, hi)

# 子 k の型 (FRAR/DUMP: Filter, Compressor, Filter, Compressor, Gain, Compressor, Gain, Gain)
CHAIN = [1, 0, 1, 0, 2, 0, 2, 2]  # 0=comp 1=filter 2=gain

def child_params(k, heavy):
    """子 k の model (P) / wrapper (W) 状態注入。全型で共通の意味領域 + 型別既知領域。"""
    w = []
    def P(o, v): w.append((0x20 | k, o, fb(v) & 0xffffffff))
    def W(o, v): w.append((0x10 | k, o, fb(v) & 0xffffffff))
    def PB(o, v): w.append((0x100 | 0x10 | k, o, v))
    # wrapper 状態 (fade/meter/first フラグ/tail)
    if heavy:
        PB(0x10, rnd.choice([0, 1])); PB(0x60, rnd.choice([0, 1])); PB(0xfc, rnd.choice([0, 1]))
        W(0x58, fb(float(rnd.randrange(0, 0x7fffffff)))); w.append((0x10 | k, 0x70, rnd.randrange(0, 4)))
        W(0x8c, fb(rf(0, 1))); W(0x84, fb(rnd.choice([0.0, 0.25, 0.5, 1.0])))
        W(0x98, fb(rf(0, 2))); W(0xa0, fb(rf(0, 1))); W(0xb0, fb(rf(0, 1))); W(0xbc, fb(rf(0, 1)))
        W(0xc0, fb(rf(0, 1))); W(0xcc, fb(rf(0, 1))); W(0xd0, fb(rf(0, 1))); W(0xdc, fb(rf(0, 1))); W(0xe0, fb(rf(0, 1)))
    # model 共通 (comp 実績の意味領域。フィルタ/gain で未使用の offset は単なるメモリとして両側同一に作用)
    P(0x9dc4, lg(-4, 0)); P(0x9e0c, lg(-3, 0.3)); P(0x9e50, fb(rf(0, 1))); P(0x9e60, fb(rf(0, 1)))
    P(0x9e98, fb(rf(0, 2))); P(0x9ea8, rnd.choice([0.0, rf(0, 2), 1.0, 1.5])); P(0x9ee4, lg(-0.3, 1))
    P(0x9f2c, lg(-1, 0.5)); P(0x9f70, lg(-3, 0.3)); P(0x9f74, lg(-3, 0.3))
    P(0x9fb8, lg(-3, 0.3)); P(0x9fbc, lg(-3, 0.3)); P(0xa000, lg(-3, 0.3)); P(0xa004, lg(-3, 0.3))
    P(0xa0a0, lg(-1, 1.2))   # host vtable fn (this+8) が返す値
    for o in (0x9ffb, 0x9fb3, 0xa043): w.append((0x100 | 0x20 | k, o, rnd.choice([0, 1])))
    w.append((0x20 | k, 0x9e54, rnd.choice([0, 1, 2, 3])))
    # 子インスタンス状態 (meter tail / tail-active flag)
    w.append((0x30 | k, 0x5e8, rnd.randrange(0, 0x400) if heavy else 0))
    w.append((0x100 | 0x30 | k, 0x5d0, rnd.choice([0, 1])))
    return w

def params():
    """F/M 制御層状態 + 全子の状態。"""
    w = [(1, 0x9dc4, fb(lg(-4, 0))), (1, 0x9e0c, fb(lg(-3, 0.3))), (1, 0x9e60, fb(lg(-3, 0.3)))]
    for o in (0x9ba4, 0x9bec, 0x9cc4): w.append((0x100 | 1, o, rnd.choice([0, 0, 0, 1])))
    for k in range(8): w += child_params(k, heavy=rnd.random() < 0.35)
    return w

def change():
    w = []
    for _ in range(rnd.randrange(0, 4)):
        c = rnd.choice(['mid', 'high', 'trim', 'flag', 'host', 'cmeter'])
        if c == 'mid': w.append((1, 0x9dc4, fb(lg(-4, 0))))
        elif c == 'high': w.append((1, 0x9e0c, fb(lg(-3, 0.3))))
        elif c == 'trim': w.append((1, 0x9e60, fb(lg(-3, 0.3))))
        elif c == 'flag': w.append((0x100 | 1, rnd.choice([0x9ba4, 0x9bec, 0x9cc4]), rnd.choice([0, 1])))
        elif c == 'host': w.append((0x20 | rnd.randrange(8), 0xa0a0, fb(lg(-1, 1.2))))
        else: w.append((0x30 | rnd.randrange(8), 0x5e8, rnd.randrange(0, 0x800)))
    return w

def emit_call(w, n, op=0, oparg=None):
    tok = [len(w)]
    for r, o, v in w: tok += [r, o, v]
    tok += [n] + [fb(sample()) for _ in range(2 * n)] + [op]
    if op == 1: tok += [oparg if oparg is not None else fb(rnd.choice([44100.0, 48000.0, 96000.0, 22050.0, float(rnd.randrange(8000, 192001))]))]
    return tok

def op_slice():
    """1 op 分 (書込 + 音声 + op)。"""
    r = rnd.random()
    if r < 0.72: return emit_call(params() if rnd.random() < 0.4 else change(), rnd.choice([0, 1, 2, 3, 7, 16, 31, 64, 96]) if rnd.random() < .5 else rnd.randrange(1, 97), 0)
    if r < 0.80: return emit_call([], 0, 1)
    if r < 0.85: return emit_call([], 0, rnd.choice([2, 3]))
    if r < 0.93: return emit_call([], 0, rnd.choice([4, 5, 6]))
    return emit_call([], 0, rnd.choice([7, 8, 9]))

lines = []
# ---- 先頭 8 本: factory .epf 駆動 (macro 値は .epf +0x10/+0x14 の f32, Trim=0) ----
epfdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'work', 'win', 'Fresh Air', 'C__ProgramData_Slate Digital', 'Fresh Air', 'FACTORY Presets', 'Factory Bank')
epfs = sorted(glob.glob(os.path.join(epfdir, '*.epf')))
names = []
for i, f in enumerate(epfs[:8]):
    d = open(f, 'rb').read()
    mid, high = struct.unpack_from('<2f', d, 0x10)
    names.append((os.path.basename(f)[:-4], mid, high))
    w = [(1, 0x9dc4, fb(mid)), (1, 0x9e0c, fb(high)), (1, 0x9e60, fb(0.0))]
    tok = [900 + i, 5, 64]
    tok += emit_call(w, 64, 0)
    tok += emit_call([], 0, 1, fb(48000.0))          # slot4 sr 変更 → slot13 への間接 tail-jmp 経路
    tok += emit_call(change(), 17, 0)
    tok += emit_call([], 0, 2)                        # slot3 → slot13 間接 tail-jmp
    tok += emit_call(change(), 5, 0)
    tok += emit_call([], 0, 4)                        # slot7 meter 読み
    lines.append(' '.join('%x' % t for t in tok))
for i in range(NS):
    nc = rnd.choice([1, 2, 2, 3, 4])
    tok = [1000 + i, nc, rnd.choice([64, 64, 64, 12, 8, 4, 0, 16])]
    for c in range(nc): tok += op_slice()
    lines.append(' '.join('%x' % t for t in tok))
for i in range(NR):
    nc = rnd.choice([1, 2, 3, 5])
    tok = [2000 + i, nc, rnd.choice([64, 12, 8, 0, 16, 4])]
    for c in range(nc): tok += op_slice()
    lines.append(' '.join('%x' % t for t in tok))
open(out, 'w').write('\n'.join(lines) + '\n')
print('wrote', out, len(lines), 'scenarios (epf %d: %s)' % (len(names), ', '.join(n for n, _, _ in names)))
