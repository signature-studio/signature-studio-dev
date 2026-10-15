#!/usr/bin/env python3
"""x87_crosscheck.py: x87_diff.py の不一致を、試行の内訳で独立に数え直す (#1099・#2967)。

  python3 x87_crosscheck.py [mode-dir=main]    # 直前の x87_diff.py の結果 (work/x87/<mode-dir>) を読む

(a) FSW (C0/C2/C3) が違う試行を、含む op で分ける (fld/fstp m80 を含むか・比較 op を含むか)。
(b) slot の不一致の試行を、fst/fstp m32 (ADR 制限 2)・fstp m80 (#2967) を含むかで分ける。
    slot は 1 個 16 byte (lo・hi) なので、語の添字は 2 * slot 番号 (x87_diff_main.h の出力形式)。
(c) fld m80 の入力の類ごとに、V (ST 値) が不一致の試行を数える。
(d) work/x87/rcarith0..3 (RC 固定) の bit 一致を、含む op の組で分ける。
(a)(b)(c) の基準は、試行の入力 (trials.txt) と出力 (native.out / lowered.out) を直接読み、x87_diff.py の compare を使わない。 (d) の判定にだけ compare を使う。
"""
import importlib.util, os, struct, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, 'work', 'x87', sys.argv[1] if len(sys.argv) > 1 else 'main')
spec = importlib.util.spec_from_file_location('x', os.path.join(HERE, 'x87_diff.py'))
x = importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)
byid = {o['id']: o for o in x.instances(x.templates())}

tr = open(os.path.join(W, 'trials.txt')).read().splitlines()
nat = open(os.path.join(W, 'native.out')).read().splitlines()
low = open(os.path.join(W, 'lowered.out')).read().splitlines()

fa_cnt = Counter()
sl_cnt = Counter()
first = None
for i, (t, a, b) in enumerate(zip(tr, nat, low)):
    tk = t.split()
    n = int(tk[16])
    ops = [(byid[int(tk[17 + 2 * j])], int(tk[18 + 2 * j])) for j in range(n)]
    m80 = any(o['typ'] in ('e', 'w10') for o, _ in ops)
    fa = a.split(' V ')[0].split()[1:]
    fb = b.split(' V ')[0].split()[1:]
    if fa != fb:
        fa_cnt['FSW 不一致 (m80 を含む)' if m80 else 'FSW 不一致 (m80 を含まない)'] += 1
        if first is None:
            first = (i, [o['name'] for o, _ in ops], fa, fb)
    Sa = a.split(' S ')[1].split()
    Sb = b.split(' S ')[1].split()
    for o, sl in ops:
        if o['name'] == 'fnstsw' and o['form'] == 'mem':
            for S in (Sa, Sb):
                v = int(S[2 * sl], 16)
                S[2 * sl] = '%016x' % ((v & ~0xffff) | (v & 0x7d00))
    if Sa != Sb:
        m32 = any(o['name'] in ('fst', 'fstp') and o['typ'] == 'w4' for o, _ in ops)
        sl_cnt['slot 不一致: fst/fstp m32 を含む' if m32 else 'slot 不一致: fst/fstp m32 を含まない'] += 1
        if m80:
            sl_cnt['slot 不一致 (m80 を含む)'] += 1

print('[crosscheck] (a) FSW (C0/C2/C3, TOP マスク後) の不一致試行の内訳 (件数)')
for k in sorted(fa_cnt):
    print('  %s: %d' % (k, fa_cnt[k]))
if not fa_cnt:
    print('  なし')
if first is not None:
    i, names, fa, fb = first
    print('  最初の例: trial %d ops=%s native FSW=%s lowered FSW=%s' % (i, ' '.join(names), ' '.join(fa), ' '.join(fb)))
print('[crosscheck] (b) slot の不一致試行の内訳 (件数)')
for k in sorted(sl_cnt):
    print('  %s: %d' % (k, sl_cnt[k]))
if not sl_cnt:
    print('  なし')


def is_zero(h):
    return struct.unpack('<d', struct.pack('<Q', int(h, 16)))[0] == 0.0


def f80_class(lo, hi):
    """fld m80 が読む入力 (lo = 仮数, hi = 符号・指数) の類 (x87_f80_rt.c の類と同じ境界)。"""
    e, sig = hi & 0x7fff, lo
    if e == 0x7fff:
        return 'inf' if (sig & ((1 << 63) - 1)) == 0 else 'nan'
    if e == 0:
        return 'zero' if sig == 0 else 'denormal'
    if e > 16383 + 1023 or e < 16383 - 1022:
        return 'exp_out_of_f64'
    return 'exact53' if (sig & 0x7ff) == 0 else 'norm64'


print('[crosscheck] (c) fld m80 の入力の類ごとの V (ST 値) 不一致 (類を 1 つでも含む試行の件数)')
cls_n, cls_bad = Counter(), Counter()
for t, a, b in zip(tr, nat, low):
    tk = t.split()
    n = int(tk[16])
    ops = [(byid[int(tk[17 + 2 * j])], int(tk[18 + 2 * j])) for j in range(n)]
    cls = set()
    for o, sl in ops:
        if o['name'] == 'fld' and o['typ'] == 'e':
            cls.add(f80_class(int(tk[2 * sl], 16), int(tk[2 * sl + 1], 16)))
    va = a.split(' V ')[1].split(' S ')[0]
    vb = b.split(' V ')[1].split(' S ')[0]
    for c in cls:
        cls_n[c] += 1
        if va != vb:
            cls_bad[c] += 1
for c in sorted(cls_n):
    print('  %s: 試行 %d・V 不一致 %d' % (c, cls_n[c], cls_bad[c]))
if not cls_n:
    print('  なし')

print('[crosscheck] (d) RC 固定 (work/x87/rcarith0..3。同じ seed・同じ試行列) の bit 一致を、含む op の組で分ける')
runs = {}
for r in range(4):
    d = os.path.join(HERE, 'work', 'x87', 'rcarith%d' % r)
    runs[r] = (open(os.path.join(d, 'trials.txt')).read().splitlines(),
               open(os.path.join(d, 'native.out')).read().splitlines(),
               open(os.path.join(d, 'lowered.out')).read().splitlines())
combo_n = Counter()
combo_ok = {r: Counter() for r in range(4)}
for i, t in enumerate(runs[0][0]):
    tk = t.split()
    n = int(tk[16])
    ops = [(byid[int(tk[17 + 2 * j])], int(tk[18 + 2 * j])) for j in range(n)]
    ar = any(o['name'] in x.ARITH_NAMES for o, _ in ops)
    f32 = any(o['name'] in ('fst', 'fstp') and o['typ'] == 'w4' for o, _ in ops)
    f64 = any(o['name'] in ('fst', 'fstp') and o['typ'] == 'w8' for o, _ in ops)
    fist = any(o['name'] in ('fist', 'fistp') for o, _ in ops)
    key = ('算術' if ar else '-', 'fst m32' if f32 else '-', 'fst m64' if f64 else '-', 'fist' if fist else '-')
    combo_n[key] += 1
    for r in range(4):
        rt, rn, rl = runs[r]
        dep = int(rt[i].split()[-1])
        ok = x.compare([rn[i]], [rl[i]], [(ops, dep, r)])['identical']
        combo_ok[r][key] += ok
print('  %-40s %8s %8s %8s %8s %8s' % ('算術 / fst m32 / fst m64 / fist', '試行', 'RC=0', 'RC=1', 'RC=2', 'RC=3'))
for key in sorted(combo_n):
    print('  %-40s %8d %8d %8d %8d %8d' % (' / '.join(key), combo_n[key], combo_ok[0][key], combo_ok[1][key],
                                           combo_ok[2][key], combo_ok[3][key]))
print('  RC 固定の不一致試行のうち、F・S が同じで V の差が ±0 の符号だけのもの (数値の ulp は 0):')
for r in range(4):
    rt, rn, rl = runs[r]
    zs = 0
    for t, a, b in zip(rt, rn, rl):
        tk = t.split()
        n = int(tk[16])
        ops = [(byid[int(tk[17 + 2 * j])], int(tk[18 + 2 * j])) for j in range(n)]
        if x.compare([a], [b], [(ops, 0, r)])['identical']:
            continue
        if a.split(' V ')[0] != b.split(' V ')[0] or a.split(' S ')[1] != b.split(' S ')[1]:
            continue
        pairs = [(p, q) for p, q in zip(a.split(' V ')[1].split(' S ')[0].split(),
                                        b.split(' V ')[1].split(' S ')[0].split()) if p != q]
        if pairs and all(is_zero(p) and is_zero(q) for p, q in pairs):
            zs += 1
    print('    RC=%d: %d' % (r, zs))
