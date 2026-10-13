#!/usr/bin/env python3
"""IPP-11 (#473): VectorSlope_64f/_32f の独立検算。実 DLL (vslope64_probe 経由) の出力 bit を、実 DLL の SSE2 カーネル
(逆アセ結果) を Python で書き直したモデル (float32 は struct で丸めてエミュレート。C 実装とは別言語・別実装) と突合する。
usage: FL_WIN64_DIR=<fl-win64> python3 vslope_model_check.py   (gcc 必須。probe は work/vslope_model/ にビルド)
NEG=1: モデルに head 処理 (K) を無視させるネガティブコントロール (bad > 0 で exit 1 を期待)。
対象: 64f/32f × cpu mask 6 通り × K=0..7 (K = 16B 境界からのずれ要素数) × 40 ケース (n=1..257、o/s は乱数)。期待: total bad 0。"""
import struct, subprocess, os, sys, random
HERE = os.path.dirname(os.path.abspath(__file__)); IPP = os.path.abspath(os.path.join(HERE, '..', '..'))
W = os.path.join(IPP, 'work', 'vslope_model'); os.makedirs(W, exist_ok=True)
DLL = os.path.join(os.environ['FL_WIN64_DIR'], 'extracted', 'block24356_PE.bin')
PROBE = os.path.join(W, 'probe')
subprocess.check_call(['gcc', '-O1', '-w', '-I', os.path.join(IPP, 'src'), '-I', HERE, '-o', PROBE, os.path.join(HERE, 'vslope64_probe.c'), os.path.join(IPP, 'ref', 'pe_load.c'), '-lm'])
def f32(x): return struct.unpack('<f', struct.pack('<f', x))[0]
def f32b(x): return struct.unpack('<I', struct.pack('<f', x))[0]
def d64b(x): return struct.unpack('<Q', struct.pack('<d', x))[0]
def real(bits, o, s, n, mis=0, mask='0x3f'):
    out = subprocess.run([PROBE, DLL, mask, str(bits), repr(o), repr(s), str(n), str(mis)], capture_output=True, text=True).stdout.split('\n')
    return [int(l.split()[1], 16) for l in out[1:] if l]
def model32(o,s,n,mis):
    o,s=f32(o),f32(s)
    lanes=[f32(float(j)*s) for j in range(4)]
    out=[]; rem=n
    # head loop: runs while (addr&15)!=0
    addr=(mis*4)%16
    while addr%16!=0:
        out.append(f32(lanes[0]+o)); addr+=4; rem-=1
        if rem<=0: return out
        lanes=[f32(l+s) for l in lanes]
    nb=rem//16; tail=rem%16
    v0=[f32(l+o) for l in lanes]
    if nb:
        s4=f32(f32(s+s)*2); s4=f32(4*s)
        x1=[f32(l+s4) for l in lanes]; x2=[f32(l+s4) for l in x1]; x3=[f32(l+s4) for l in x2]
        v=[v0,[f32(l+o) for l in x1],[f32(l+o) for l in x2],[f32(l+o) for l in x3]]
        step=f32(16*s)
        for _ in range(nb):
            for vv in v: out+=vv
            v=[[f32(l+step) for l in vv] for vv in v]
        v0=v[0]
    x=v0[0]
    for _ in range(tail):
        out.append(x); x=f32(x+s)
    return out
def model64(o,s,n,mis):
    lanes=[0.0*s,1.0*s]; idx=[0.0,1.0]
    out=[]; rem=n
    addr=(mis*8)%16
    while addr%16!=0:
        out.append(idx[0]*s+o); addr+=8; rem-=1
        if rem<=0: return out
        idx=[i+1.0 for i in idx]
    lanes=[i*s for i in idx]
    nb=rem//8; tail=rem%8
    v0=[l+o for l in lanes]
    if nb:
        s2=2.0*s
        x1=[l+s2 for l in lanes]; x2=[l+s2 for l in x1]; x3=[l+s2 for l in x2]
        v=[v0,[l+o for l in x1],[l+o for l in x2],[l+o for l in x3]]
        step=8.0*s
        for _ in range(nb):
            for vv in v: out+=vv
            v=[[l+step for l in vv] for vv in v]
        v0=v[0]
    x=v0[0]
    for _ in range(tail):
        out.append(x); x=x+s
    return out
def bits(vals,b):
    return [f32b(x) if b==32 else d64b(x) for x in vals]

if __name__ == '__main__':
    random.seed(7)
    masks = ['0x1', '0x3', '0x7', '0xf', '0x1f', '0x3f']
    cases = []
    for _ in range(40):
        o = random.choice([0.0, 1.0, -1.0, 0.1, random.uniform(-2, 2), random.uniform(-1e3, 1e3)])
        s = random.choice([-1 / 3, 0.3, random.uniform(-1, 1) * 10 ** random.randint(-3, 2)])
        n = random.choice([1, 2, 3, 4, 5, 7, 8, 9, 12, 15, 16, 17, 24, 31, 32, 33, 48, 64, 100, 257])
        cases.append((o, s, n))
    bad = 0; tot = 0
    for b in (64, 32):
        for m in masks:
            for mis in range(8):
                for o, s, n in cases:
                    r = real(b, f32(o) if b == 32 else o, f32(s) if b == 32 else s, n, mis, m)
                    mo = bits((model32 if b == 32 else model64)(o, s, n, 0 if os.environ.get('NEG') else mis), b)
                    tot += 1; bad += r != mo
    print('vslope_model_check: cases', tot, 'bad', bad)
    sys.exit(1 if bad else 0)
