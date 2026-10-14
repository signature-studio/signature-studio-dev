#!/usr/bin/env python3
"""x87_crosscheck.py: x87_diff.py の不一致の原因を、有理数による独立算法で検算する (#1099)。

  python3 x87_crosscheck.py [seed-dir=work/x87/main]

(a) 不一致試行の中から fcomp 後の C0/C2/C3 が違う例 (trial 13317 のとき) を取り、
    有理数で「64bit 有効数字 (f80 の中間)」と「53bit (f64)」の 2 通りに丸めて再計算する。
    native (f80) と lowered (f64) がそれぞれ同じ結果になることを確かめる。
(b) 全試行で slot の不一致を含む試行が、fst/fstp m32 (ADR 制限 2) を含むかを数える。
"""
import importlib.util, os, struct, sys
from fractions import Fraction as F
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, 'work', 'x87', sys.argv[1] if len(sys.argv) > 1 else 'main')
spec = importlib.util.spec_from_file_location('x', os.path.join(HERE, 'x87_diff.py'))
x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)
byid = {o['id']: o for o in x.instances(x.templates())}


def rnd(v, p):
    """有理数 v を p bit の有効数字で丸める (round-to-nearest-even)。"""
    if v == 0:
        return F(0)
    s = -1 if v < 0 else 1
    v = abs(v)
    e = 0
    while v >= F(2) ** (e + 1):
        e += 1
    while v < F(2) ** e:
        e -= 1
    q = v / F(2) ** (e - p + 1)
    n = q.numerator // q.denominator
    r = q - n
    if r > F(1, 2) or (r == F(1, 2) and n % 2 == 1):
        n += 1
    return s * F(n) * F(2) ** (e - p + 1)


def dbl(h):
    return struct.unpack('<d', struct.pack('<Q', int(h, 16)))[0]


tr = open(os.path.join(W, 'trials.txt')).read().splitlines()
nat = open(os.path.join(W, 'native.out')).read().splitlines()
low = open(os.path.join(W, 'lowered.out')).read().splitlines()

print('[crosscheck] (a) 精度由来の C0/C2/C3 不一致 (native と lowered で C 値が違う試行)')
for i, (a, b) in enumerate(zip(nat, low)):
    fa = a.split(' V ')[0].split()[1:]
    fb = b.split(' V ')[0].split()[1:]
    if fa == fb:
        continue
    tk = tr[i].split()
    n = int(tk[8])
    ops = [(byid[int(tk[9 + 2 * j])], int(tk[10 + 2 * j])) for j in range(n)]
    names = [o['name'] for o, _ in ops]
    if names[:5] != ['fld', 'fsubr', 'fist', 'fsubr', 'fnstsw']:
        continue
    slots = [int(s, 16) for s in tk[:8]]
    d4, d2 = F(dbl('%016x' % slots[4])), F(dbl('%016x' % slots[2]))
    for p, tag in ((64, 'f80 (64bit 有効数字)'), (53, 'f64 (53bit)')):
        r1 = rnd(d2 - d4, p)
        r2 = rnd(d2 - r1, p)
        c = 'equal (C3)' if r2 == d4 else ('less (C0)' if r2 < d4 else 'greater')
        print('  trial %d %s: ST0 after 2 fsubr = %r -> compare with m64: %s' % (i, tag, float(r2), c))
    print('  native FSW C-bits %s, lowered %s' % (fa[5], fb[5]))
    break

print('[crosscheck] (b) slot 不一致の試行の内訳 (C0/C2/C3 と TOP のマスクを掛けた後)')
cnt = Counter()
for t, a, b in zip(tr, nat, low):
    tk = t.split()
    n = int(tk[8])
    ops = [(byid[int(tk[9 + 2 * j])], int(tk[10 + 2 * j])) for j in range(n)]
    Sa = a.split(' S ')[1].split()
    Sb = b.split(' S ')[1].split()
    for o, sl in ops:
        if o['name'] == 'fnstsw' and o['form'] == 'mem':
            for S in (Sa, Sb):
                v = int(S[sl], 16)
                S[sl] = '%016x' % ((v & ~0xffff) | (v & 0x7d00))
    if Sa != Sb:
        m32 = any(o['name'] in ('fst', 'fstp') and o['typ'] == 'w4' for o, _ in ops)
        cnt['fst/fstp m32 を含む' if m32 else 'fst/fstp m32 を含まない'] += 1
print('  ', dict(cnt) or '{}')
