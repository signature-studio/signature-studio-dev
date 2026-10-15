#!/usr/bin/env python3
"""x87_diff.py: x87 subset の lowering (x64c --arch ia32 → tools/ott/rt/ott_x87.h) と実 x87 の差分試験 (#1099)。

  python3 x87_diff.py [--n 100000] [--seed 1] [--nega] [--rc]

- op 表: 機械語 (.byte) を 1 命令ずつ持つ。 native 側はその機械語を実 FPU で実行 (中間値は 80bit)。
  lowered 側は同じ機械語を capstone で decode → x64c の FnLift.one() で C にして実行 (f80 は持たず double)。
- 試行: 入力 slot 6 個 (d/f/i/q の型) + 操作列 (2〜7 op)。 各 op の後に FSW (C0/C2/C3/TOP) を記録し、
  終了時に ST(0..d-1) と slot 8 個を記録する。 両者の一致を bit 単位で比べ、不一致は ulp 距離で数える。
- --nega: lowered 側の `fsub st(i), st(0)` (DC E8+i) を `fsubr` (DC E0+i) に取り違えて FAIL が出ることを確かめる。
- --rc: fldcw で RC を変え、fist/fistp の丸めだけを比べる (算術を含まない試行。ADR の制限 (5))。
生成物は work/x87/ (gitignore 対象)。 依存: gcc・capstone・x64c (tools/ott/lift)。
"""
import argparse, math, os, random, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
RT = os.path.join(ROOT, 'tools', 'ott', 'rt')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'ott', 'lift'))
import x64c  # noqa: E402
from capstone import Cs, CS_ARCH_X86, CS_MODE_32  # noqa: E402

WORK = os.path.join(HERE, 'work', 'x87')
CMASK = 0x7d00

# (名前, 機械語の先頭, 種別, delta(スタック深さの増減), 必要な深さ, 入力型 or 出力型, cmp か)
#   種別: 'reg' = 末尾バイトに i を足して ST(i) を取る / 'none' = オペランド無し / 'mem' = [eax] (入力 slot 型)
#   出力 (scratch) は型名が w2/w4/w8 (slot 6・7 に書く)
ARITH_REG = [('fadd', 0xC0, 0xC0, 0xC0), ('fmul', 0xC8, 0xC8, 0xC8),
             ('fsub', 0xE0, 0xE8, 0xE8), ('fsubr', 0xE8, 0xE0, 0xE0),
             ('fdiv', 0xF0, 0xF8, 0xF8), ('fdivr', 0xF8, 0xF0, 0xF0)]


def templates():
    T = []
    for name, d8, dc, de in ARITH_REG:   # D8: ST0 op= ST(i) / DC: ST(i) op= ST0 / DE: 同 + pop
        T.append(dict(name=name, bs=[0xD8, d8], form='reg', delta=0, need=1, cmp=False, typ=None))
        T.append(dict(name=name, bs=[0xDC, dc], form='reg', delta=0, need=1, cmp=False, typ=None))
        T.append(dict(name=name + 'p', bs=[0xDE, de], form='reg', delta=-1, need=1, cmp=False, typ=None))
    T += [dict(name='fcom', bs=[0xD8, 0xD0], form='reg', delta=0, need=1, cmp=True, typ=None),
          dict(name='fcomp', bs=[0xD8, 0xD8], form='reg', delta=-1, need=1, cmp=True, typ=None),
          dict(name='fcompp', bs=[0xDE, 0xD9], form='none', delta=-2, need=2, cmp=True, typ=None),
          dict(name='fld', bs=[0xD9, 0xC0], form='reg', delta=1, need=1, cmp=False, typ=None),
          dict(name='fst', bs=[0xDD, 0xD0], form='reg', delta=0, need=1, cmp=False, typ=None),
          dict(name='fstp', bs=[0xDD, 0xD8], form='reg', delta=-1, need=1, cmp=False, typ=None),
          dict(name='fxch', bs=[0xD9, 0xC8], form='reg', delta=0, need=1, cmp=False, typ=None),
          dict(name='fchs', bs=[0xD9, 0xE0], form='none', delta=0, need=1, cmp=False, typ=None),
          dict(name='fabs', bs=[0xD9, 0xE1], form='none', delta=0, need=1, cmp=False, typ=None),
          dict(name='fld1', bs=[0xD9, 0xE8], form='none', delta=1, need=0, cmp=False, typ=None),
          dict(name='fldz', bs=[0xD9, 0xEE], form='none', delta=1, need=0, cmp=False, typ=None),
          dict(name='fnstsw', bs=[0xDF, 0xE0], form='none', delta=0, need=0, cmp=False, typ=None)]
    # memory (mod=00 rm=[eax]): 算術・比較は入力 slot (f = float32, d = float64)
    for r, name in [(0, 'fadd'), (1, 'fmul'), (2, 'fcom'), (3, 'fcomp'), (4, 'fsub'), (5, 'fsubr'), (6, 'fdiv'), (7, 'fdivr')]:
        T.append(dict(name=name, bs=[0xD8, r << 3], form='mem', delta=-1 if name == 'fcomp' else 0, need=1,
                      cmp=name in ('fcom', 'fcomp'), typ='f'))
        T.append(dict(name=name, bs=[0xDC, r << 3], form='mem', delta=-1 if name == 'fcomp' else 0, need=1,
                      cmp=name in ('fcom', 'fcomp'), typ='d'))
    T += [dict(name='fld', bs=[0xD9, 0x00], form='mem', delta=1, need=0, cmp=False, typ='f'),
          dict(name='fld', bs=[0xDD, 0x00], form='mem', delta=1, need=0, cmp=False, typ='d'),
          dict(name='fild', bs=[0xDF, 0x00], form='mem', delta=1, need=0, cmp=False, typ='i2'),
          dict(name='fild', bs=[0xDB, 0x00], form='mem', delta=1, need=0, cmp=False, typ='i'),
          dict(name='fild', bs=[0xDF, 0x28], form='mem', delta=1, need=0, cmp=False, typ='q'),
          dict(name='fldcw', bs=[0xD9, 0x28], form='mem', delta=0, need=0, cmp=False, typ='c'),
          # 格納 (scratch slot 6・7): 型名は書く幅
          dict(name='fst', bs=[0xD9, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w4'),
          dict(name='fst', bs=[0xDD, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w8'),
          dict(name='fstp', bs=[0xD9, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w4'),
          dict(name='fstp', bs=[0xDD, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w8'),
          dict(name='fist', bs=[0xDF, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w2'),
          dict(name='fist', bs=[0xDB, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w4'),
          dict(name='fistp', bs=[0xDF, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w2'),
          dict(name='fistp', bs=[0xDB, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w4'),
          dict(name='fistp', bs=[0xDF, 0x38], form='mem', delta=-1, need=1, cmp=False, typ='w8'),
          dict(name='fnstsw', bs=[0xDD, 0x38], form='mem', delta=0, need=0, cmp=False, typ='w2'),
          dict(name='fnstcw', bs=[0xD9, 0x38], form='mem', delta=0, need=0, cmp=False, typ='w2')]
    return T


RC_NAMES = {'fld', 'fild', 'fld1', 'fldz', 'fst', 'fstp', 'fist', 'fistp', 'fnstcw', 'fnstsw'}


def slot_key(o):
    return 'i' if o['typ'] == 'i2' else o['typ']


def instances(T):
    """reg 形は i=0..7 に展開。id は通し番号。"""
    out = []
    for t in T:
        for i in (range(8) if t['form'] == 'reg' else [None]):
            bs = list(t['bs'])
            if i is not None:
                bs[-1] += i
            out.append(dict(t, i=i, bs=bs, id=len(out)))
    return out


def lower_lines(bs):
    """x64c の FnLift.one() で機械語 1 命令を C 文にする (ia32)。"""
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    md.detail = True
    ins = list(md.disasm(bytes(bs), 0x1000))
    if len(ins) != 1 or ins[0].size != len(bs):
        raise SystemExit('[x87_diff] decode 失敗: %s' % bs)
    fl = x64c.FnLift(None, 0x1000, set(), md, {})
    fl.one(ins[0])
    return fl.out, ins[0].mnemonic + ' ' + ins[0].op_str


def write_inc(insts, nega, path_n, path_l):
    x64c.IA32 = True
    x64c.PTR = 4
    with open(path_n, 'w') as fn, open(path_l, 'w') as fl:
        fn.write('static void ops_exec(int id, void* p) {\n  switch (id) {\n')
        fl.write('static void ops_exec(int id, void* p) {\n  R[0] = (uint64_t)(uintptr_t)p;\n  switch (id) {\n')
        for o in insts:
            hexb = ','.join('0x%02x' % b for b in o['bs'])
            if o['form'] == 'mem':
                fn.write('    case %d: __asm__ volatile("mov %%0, %%%%rax\\n\\t.byte %s" :: "r"(p) : "rax", "memory"); break;\n'
                         % (o['id'], hexb))
            else:
                fn.write('    case %d: __asm__ volatile(".byte %s" ::: "rax", "memory"); break;\n' % (o['id'], hexb))
            bs = o['bs']
            if nega and o['name'] == 'fsub' and bs[0] == 0xDC and o['i'] is not None:
                bs = [0xDC, 0xE0 + o['i']]   # 取り違え (negative control): fsub st(i),st(0) を fsubr として lower
            lines, dis = lower_lines(bs)
            fl.write('    case %d: { /* %s */\n' % (o['id'], dis.replace('*/', '* /')))
            for ln in lines:
                fl.write('  ' + ln + '\n')
            fl.write('    } break;\n')
        fn.write('  }\n}\n')
        fl.write('  }\n}\n')


def ulp_bits(a, b):
    if a != a or b != b:
        return 0 if (a != a and b != b) else 1 << 30
    def key(x):
        u = struct.unpack('<q', struct.pack('<d', x))[0]
        return u if u >= 0 else -(u & 0x7fffffffffffffff)
    return abs(key(a) - key(b))


def ulp_step(a, b, cap=3):
    """独立算法の検算: nextafter を最大 cap 歩進めて距離を数える (cap 超は cap)。"""
    if a == b or (a != a and b != b):
        return 0
    x = a
    for k in range(1, cap + 1):
        x = math.nextafter(x, b)
        if x == b:
            return k
    return cap


def rand_double(rng):
    r = rng.random()
    if r < 0.2:
        return float(rng.randint(-1000, 1000))
    if r < 0.3:
        return rng.randint(-1000, 1000) / 8.0
    m = rng.getrandbits(52)
    e = rng.randint(-20, 20)
    s = -1.0 if rng.random() < 0.5 else 1.0
    return s * (1.0 + m / 2.0 ** 52) * 2.0 ** e


def slot_value(rng, typ):
    if typ == 'd':
        return struct.unpack('<Q', struct.pack('<d', rand_double(rng)))[0]
    if typ == 'f':
        return struct.unpack('<I', struct.pack('<f', rand_double(rng)))[0]
    if typ == 'i':
        return rng.randint(-100000, 100000) & 0xffffffff
    if typ == 'q':
        return rng.randint(-(1 << 40), 1 << 40) & 0xffffffffffffffff
    if typ == 'c':
        return 0x037f | (rng.randint(0, 3) << 10)
    raise ValueError(typ)


def gen_trials(insts, n, seed, rc):
    rng = random.Random(seed)
    lines, metas = [], []
    kinds_pool = ['d', 'f', 'i', 'q']
    by_typ = {}
    for o in insts:
        if o['form'] == 'mem':
            by_typ.setdefault(o['typ'], []).append(o)
    for _ in range(n):
        if rc:
            kinds = ['c'] + [rng.choices(['d', 'i', 'q'], [6, 2, 2])[0] for _ in range(5)]
        else:
            kinds = [rng.choices(kinds_pool, [4, 2, 2, 2])[0] for _ in range(6)]
        vals = [slot_value(rng, k) for k in kinds] + [0, 0]
        slot_of = {k: [s for s in range(6) if kinds[s] == k] for k in set(kinds)}
        ops, depth = [], 0
        if rc:
            ops.append((next(o for o in insts if o['name'] == 'fldcw'), 0))
        nsteps = rng.randint(2, 7)
        for _ in range(nsteps):
            cand = []
            for o in insts:
                if rc and o['name'] not in RC_NAMES:   # RC 試行は丸め (fist/fistp) だけを見る: 算術を含めない
                    continue
                if not rc and o['typ'] == 'c':          # 通常試行は RC を動かさない
                    continue
                if o['form'] == 'reg' and o['i'] + 1 > depth:
                    continue
                if o['need'] > depth or not (0 <= depth + o['delta'] <= 8):
                    continue
                if o['form'] == 'mem' and not o['typ'].startswith('w') and not slot_of.get(slot_key(o)):
                    continue
                if o['form'] == 'reg' and o['name'] == 'fxch' and o['i'] == 0:
                    continue
                cand.append(o)
            if not cand:
                break
            o = rng.choice(cand)
            if o['form'] == 'mem':
                sl = rng.choice([6, 7]) if o['typ'].startswith('w') else rng.choice(slot_of[slot_key(o)])
            else:
                sl = -1
            ops.append((o, sl))
            depth += o['delta']
        if depth == 0:
            o = next(x for x in insts if x['name'] == 'fld1')
            ops.append((o, -1))
            depth = 1
        tok = ' '.join('%016x' % v for v in vals)
        body = ' '.join('%d %d' % (o['id'], sl) for o, sl in ops)
        lines.append('%s %d %s %d' % (tok, len(ops), body, depth))
        metas.append((ops, depth))
    return lines, metas


def compare(nat, low, metas):
    st = dict(trials=0, identical=0, ulp_hist=[0, 0, 0, 0], vals=0, vals_ulp_hist=[0, 0, 0, 0], cmp_ops=0, cmp_match=0,
              f_mismatch_trials=0, s_mismatch_trials=0, step_check_bad=0, ulp_step_bad=0, ulp_max=0)
    for a, b, (ops, d) in zip(nat, low, metas):
        ta, tb = a.split(), b.split()
        iv_a, is_a = ta.index('V'), ta.index('S')
        iv_b, is_b = tb.index('V'), tb.index('S')
        Fa, Va, Sa = ta[1:iv_a], ta[iv_a + 1:is_a], ta[is_a + 1:]
        Fb, Vb, Sb = tb[1:iv_b], tb[iv_b + 1:is_b], tb[is_b + 1:]
        st['trials'] += 1
        fok = Fa == Fb
        for o, sl in ops:   # fnstsw m16 の格納値は PE/C1 等の未モデル化の例外フラグを含むため、CMASK で比べる (ADR 制限 4)
            if o['name'] == 'fnstsw' and o['form'] == 'mem':
                for S in (Sa, Sb):
                    x = int(S[sl], 16)
                    S[sl] = '%016x' % ((x & ~0xffff) | (x & CMASK))
        sok = Sa == Sb
        if not fok:
            st['f_mismatch_trials'] += 1
        if not sok:
            st['s_mismatch_trials'] += 1
        for k, (o, _) in enumerate(ops):
            if o['cmp']:
                st['cmp_ops'] += 1
                if (int(Fa[k], 16) & 0x4500) == (int(Fb[k], 16) & 0x4500):
                    st['cmp_match'] += 1
        mx = 0
        for x, y in zip(Va, Vb):
            fx = struct.unpack('<d', struct.pack('<Q', int(x, 16)))[0]
            fy = struct.unpack('<d', struct.pack('<Q', int(y, 16)))[0]
            u = ulp_bits(fx, fy)
            if u != ulp_step(fx, fy, cap=3) and u < 3:
                st['ulp_step_bad'] += 1
            st['vals'] += 1
            st['vals_ulp_hist'][min(u, 3)] += 1
            mx = max(mx, u)
        st['ulp_max'] = max(st['ulp_max'], mx)
        st['ulp_hist'][min(mx, 3)] += 1
        if fok and sok and Va == Vb:
            st['identical'] += 1
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=100000)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--nega', action='store_true', help='lowered 側に fsub/fsubr の取り違えを入れる (negative control)')
    ap.add_argument('--rc', action='store_true', help='fldcw で RC を変え fist/fistp の丸めだけを比べる')
    ap.add_argument('--skip-build', action='store_true')
    a = ap.parse_args()
    tag = 'nega' if a.nega else ('rc' if a.rc else 'main')
    wd = os.path.join(WORK, tag)
    os.makedirs(wd, exist_ok=True)
    insts = instances(templates())
    inc_n = os.path.join(wd, 'x87_native_ops.inc')
    inc_l = os.path.join(wd, 'x87_lowered_ops.inc')
    write_inc(insts, a.nega, inc_n, inc_l)
    bn = os.path.join(wd, 'x87_native')
    bl = os.path.join(wd, 'x87_lowered')
    if not a.skip_build:
        src_n = os.path.join(HERE, 'x87_diff_native.c')
        src_l = os.path.join(HERE, 'x87_diff_lowered.c')
        subprocess.run(['gcc', '-O1', '-w', '-I', wd, '-o', bn, src_n, '-lm'], check=True)
        subprocess.run(['gcc', '-O1', '-w', '-I', RT, '-I', wd, '-o', bl, src_l, os.path.join(RT, 'ott_cpu.c'), '-lm'],
                       check=True)
    lines, metas = gen_trials(insts, a.n, a.seed, a.rc)
    tf = os.path.join(wd, 'trials.txt')
    with open(tf, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    res = {}
    for name, b in (('native', bn), ('lowered', bl)):
        of = os.path.join(wd, name + '.out')
        l0, t0 = os.getloadavg()[0], time.time()
        with open(tf) as fi, open(of, 'w') as fo:
            r = subprocess.run([b], stdin=fi, stdout=fo, timeout=900)
        dt = time.time() - t0
        if r.returncode != 0:
            raise SystemExit('[x87_diff] %s rc %d' % (name, r.returncode))
        res[name] = (of, dt, l0)
    nat = open(res['native'][0]).read().splitlines()
    low = open(res['lowered'][0]).read().splitlines()
    assert len(nat) == len(low) == len(metas) == a.n, (len(nat), len(low), len(metas), a.n)
    st = compare(nat, low, metas)
    print('[x87_diff] tag=%s n=%d seed=%d wall native %.2fs lowered %.2fs load1(start) %.2f cpu %d'
          % (tag, a.n, a.seed, res['native'][1], res['lowered'][1], res['native'][2], os.cpu_count()))
    print('[x87_diff] trials %d, bit-identical trials %d (%.2f%%)' % (
        st['trials'], st['identical'], 100.0 * st['identical'] / st['trials']))
    print('[x87_diff] per-trial max ulp: 0=%d 1=%d 2=%d >=3=%d (max %d)' % (
        st['ulp_hist'][0], st['ulp_hist'][1], st['ulp_hist'][2], st['ulp_hist'][3], st['ulp_max']))
    print('[x87_diff] per-value ulp: values %d; 0=%d 1=%d 2=%d >=3=%d' % (
        st['vals'], st['vals_ulp_hist'][0], st['vals_ulp_hist'][1], st['vals_ulp_hist'][2], st['vals_ulp_hist'][3]))
    print('[x87_diff] compare ops %d, C0/C2/C3 match %d' % (st['cmp_ops'], st['cmp_match']))
    print('[x87_diff] FSW(masked) mismatch trials %d, slot mismatch trials %d, ulp cross-check bad %d' % (
        st['f_mismatch_trials'], st['s_mismatch_trials'], st['ulp_step_bad']))


if __name__ == '__main__':
    main()
