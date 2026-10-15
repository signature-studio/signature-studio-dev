#!/usr/bin/env python3
"""x87_diff.py: x87 subset の lowering (x64c --arch ia32 → tools/ott/rt/ott_x87.h) と実 x87 の差分試験 (#1099・#2967)。

  python3 x87_diff.py [--n 100000] [--seed 1] [--nega] [--nega80] [--nega-c1] [--nega-trig] [--rc] [--rc-arith RC] [--roundtrip] [--skip NAME,...] [--only NAME,...] [--no-e]

- op 表: 機械語 (.byte) を 1 命令ずつ持つ。 native 側はその機械語を実 FPU で実行 (中間値は 80bit)。
  lowered 側は同じ機械語を capstone で decode → x64c の FnLift.one() で C にして実行 (f80 は持たず double)。
- 試行: 入力 slot 6 個 (d/f/i/q/e の型。e は 80bit: fld m80) + 操作列 (2〜7 op)。 各 op の後に FSW (C0/C2/C3/TOP) を記録し、
  終了時に ST(0..d-1) と slot 8 個を記録する。 両者の一致を bit 単位で比べ、不一致は ulp 距離で数える。
  slot は 16 byte (lo・hi)。 80bit 値は lo = 仮数、hi の下位 16bit = 符号・指数。
- --nega: lowered 側の `fsub st(i), st(0)` (DC E8+i) を `fsubr` (DC E0+i) に取り違えて FAIL が出ることを確かめる。
- --nega80: lowered 側の `fstp m80` (DB /7) を `fstp m64` (DD /3) に取り違える (m80 経路のネガティブコントロール・#2967)。
- --nega-c1: lowered 側の fxam の直後に C1 を反転させ、C1 の比較で FAIL が出ることを確かめる (negative control・#2966)。
- C1: native では丸めの上向きフラグ等になるため、比べるのは fxam と比較命令 (cmp=True) の直後だけ (ott_x87.h の制限 (6))。
- --skip: 試行の op 表から指定の名前を外す (寄与の切り分け用。例: --skip fldpi,fldlg2,fldl2e)。 機械語の id は変えない (#2966)。
- --rc: fldcw で RC を変え、fist/fistp の丸めだけを比べる (算術を含まない試行。ADR の制限 (5))。
- --rc-arith RC: fldcw で RC を RC (0 nearest / 1 down / 2 up / 3 truncate) に固定し、算術・fst m32 を含む全 op で比べる (#2967)。
  同じ seed の試行は RC の値だけが違うので、RC=0 の結果との差を RC 由来として読む。
- --nega-trig: lowered 側の fyl2x を log2 でなく自然対数にする (negative control・超越 #3687)。
- --only: 試行の op 表をこの名前だけにする (例: fld,fld1,fscale)。 --no-e: 入力を d/f/i/q だけにし、m80 の命令を外す (f80 の入力丸めを除く)。
- --roundtrip: f80↔f64 変換 (ott_x87.h の x87_f80_to_f64 / x87_f64_to_f80) の往復試験。 参照は実 x87 (x87_f80_rt.c)。
- 命令単体 (fsin/fcos/f2xm1/fyl2x/fprem/fscale の 1 命令ずつ・定義域の類ごと) は x87_trans_direct.c (#3687)。
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
CMASK = 0x7d00      # 比べる FSW bit: C3/C2/C0/TOP (C1 は cmp 命令の直後だけ C1BIT で比べる)
C1BIT = 0x0200
KINDS = ['d', 'f', 'i', 'q', 'e']
KIND_W = [4, 2, 2, 2, 2]
ARITH_NAMES = {'fadd', 'fmul', 'fsub', 'fsubr', 'fdiv', 'fdivr',
               'faddp', 'fmulp', 'fsubp', 'fsubrp', 'fdivp', 'fdivrp'}
CLASSES = ('arith', 'fst32', 'both', 'neither')

# (名前, 機械語の先頭, 種別, delta(スタック深さの増減), 必要な深さ, 入力型 or 出力型, cmp か)
#   種別: 'reg' = 末尾バイトに i を足して ST(i) を取る / 'none' = オペランド無し / 'mem' = [eax] (入力 slot 型)
#   出力 (scratch) は型名が w2/w4/w8/w10 (slot 6・7 に書く)
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
          dict(name='fnstsw', bs=[0xDF, 0xE0], form='none', delta=0, need=0, cmp=False, typ=None),
          dict(name='ftst', bs=[0xD9, 0xE4], form='none', delta=0, need=1, cmp=True, typ=None),
          dict(name='fxam', bs=[0xD9, 0xE5], form='none', delta=0, need=1, cmp=True, typ=None),
          dict(name='fnclex', bs=[0xDB, 0xE2], form='none', delta=0, need=0, cmp=False, typ=None),
          dict(name='fsqrt', bs=[0xD9, 0xFA], form='none', delta=0, need=1, cmp=False, typ=None),
          dict(name='frndint', bs=[0xD9, 0xFC], form='none', delta=0, need=1, cmp=False, typ=None),
          dict(name='fscale', bs=[0xD9, 0xFD], form='none', delta=0, need=2, cmp=False, typ=None),
          dict(name='fldl2e', bs=[0xD9, 0xEA], form='none', delta=1, need=0, cmp=False, typ=None),
          dict(name='fldlg2', bs=[0xD9, 0xEC], form='none', delta=1, need=0, cmp=False, typ=None),
          dict(name='fldpi', bs=[0xD9, 0xEB], form='none', delta=1, need=0, cmp=False, typ=None),
          dict(name='fsin', bs=[0xD9, 0xFE], form='none', delta=0, need=1, cmp=False, typ=None),
          dict(name='fcos', bs=[0xD9, 0xFF], form='none', delta=0, need=1, cmp=False, typ=None),
          dict(name='f2xm1', bs=[0xD9, 0xF0], form='none', delta=0, need=1, cmp=False, typ=None),
          dict(name='fyl2x', bs=[0xD9, 0xF1], form='none', delta=-1, need=2, cmp=False, typ=None),
          dict(name='fprem', bs=[0xD9, 0xF8], form='none', delta=0, need=2, cmp=False, typ=None)]
    # memory (mod=00 rm=[eax]): 算術・比較は入力 slot (f = float32, d = float64)
    for r, name in [(0, 'fadd'), (1, 'fmul'), (2, 'fcom'), (3, 'fcomp'), (4, 'fsub'), (5, 'fsubr'), (6, 'fdiv'), (7, 'fdivr')]:
        T.append(dict(name=name, bs=[0xD8, r << 3], form='mem', delta=-1 if name == 'fcomp' else 0, need=1,
                      cmp=name in ('fcom', 'fcomp'), typ='f'))
        T.append(dict(name=name, bs=[0xDC, r << 3], form='mem', delta=-1 if name == 'fcomp' else 0, need=1,
                      cmp=name in ('fcom', 'fcomp'), typ='d'))
    T += [dict(name='fld', bs=[0xD9, 0x00], form='mem', delta=1, need=0, cmp=False, typ='f'),
          dict(name='fld', bs=[0xDD, 0x00], form='mem', delta=1, need=0, cmp=False, typ='d'),
          dict(name='fld', bs=[0xDB, 0x28], form='mem', delta=1, need=0, cmp=False, typ='e'),
          dict(name='fild', bs=[0xDF, 0x00], form='mem', delta=1, need=0, cmp=False, typ='i2'),
          dict(name='fild', bs=[0xDB, 0x00], form='mem', delta=1, need=0, cmp=False, typ='i'),
          dict(name='fild', bs=[0xDF, 0x28], form='mem', delta=1, need=0, cmp=False, typ='q'),
          dict(name='fldcw', bs=[0xD9, 0x28], form='mem', delta=0, need=0, cmp=False, typ='c'),
          # 格納 (scratch slot 6・7): 型名は書く幅
          dict(name='fst', bs=[0xD9, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w4'),
          dict(name='fst', bs=[0xDD, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w8'),
          dict(name='fstp', bs=[0xD9, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w4'),
          dict(name='fstp', bs=[0xDD, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w8'),
          dict(name='fstp', bs=[0xDB, 0x38], form='mem', delta=-1, need=1, cmp=False, typ='w10'),
          dict(name='fist', bs=[0xDF, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w2'),
          dict(name='fist', bs=[0xDB, 0x10], form='mem', delta=0, need=1, cmp=False, typ='w4'),
          dict(name='fistp', bs=[0xDF, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w2'),
          dict(name='fistp', bs=[0xDB, 0x18], form='mem', delta=-1, need=1, cmp=False, typ='w4'),
          dict(name='fistp', bs=[0xDF, 0x38], form='mem', delta=-1, need=1, cmp=False, typ='w8'),
          dict(name='fnstsw', bs=[0xDD, 0x38], form='mem', delta=0, need=0, cmp=False, typ='w2'),
          dict(name='fnstcw', bs=[0xD9, 0x38], form='mem', delta=0, need=0, cmp=False, typ='w2'),
          dict(name='fiadd', bs=[0xDA, 0x00], form='mem', delta=0, need=1, cmp=False, typ='i'),
          dict(name='fiadd', bs=[0xDE, 0x00], form='mem', delta=0, need=1, cmp=False, typ='i2'),
          dict(name='fimul', bs=[0xDA, 0x08], form='mem', delta=0, need=1, cmp=False, typ='i'),
          dict(name='fimul', bs=[0xDE, 0x08], form='mem', delta=0, need=1, cmp=False, typ='i2')]
    # 状態の保存・復元 (#3688・末尾に追加: 既存の id と主試行列は変えない)。 操作先は envbuf (slot 番号 8)
    T += [dict(name='fnstenv', bs=[0xD9, 0x30], form='mem', delta=0, need=0, cmp=False, typ='env'),
          dict(name='fldenv', bs=[0xD9, 0x20], form='mem', delta=0, need=0, cmp=False, typ='envld'),
          dict(name='fnsave', bs=[0xDD, 0x30], form='mem', delta=0, need=0, cmp=False, typ='save'),
          dict(name='frstor', bs=[0xDD, 0x20], form='mem', delta=0, need=0, cmp=False, typ='saveld')]
    return T


RC_NAMES = {'fld', 'fild', 'fld1', 'fldz', 'fst', 'fstp', 'fist', 'fistp', 'fnstcw', 'fnstsw', 'frndint'}
ENV_TYPS = {'env', 'envld', 'save', 'saveld'}   # 型名 (typ): fnstenv / fldenv / fnsave / frstor (#3688)
# env 試行で使う op。 算術と丸め (fst m32・fist 系) は含めない: 値の丸めの差を、環境・タグの一致から分けるため
ENV_NAMES = {'fld', 'fild', 'fld1', 'fldz', 'fchs', 'fabs', 'fxch', 'fst', 'fstp', 'fcom', 'fcomp', 'fcompp',
             'ftst', 'fxam', 'fnclex', 'fnstenv', 'fldenv', 'fnsave', 'frstor'}


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


def write_inc(insts, nega, nega80, path_n, path_l, nega_c1=False, nega_trig=False, nega_env=False):
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
            if nega80 and bs == [0xDB, 0x38]:
                bs = [0xDD, 0x18]            # 取り違え (negative control・m80): fstp tbyte を fstp qword として lower
            lines, dis = lower_lines(bs)
            if nega_trig and o['name'] == 'fyl2x':   # 取り違え (negative control・超越): log2 を自然対数にする
                lines = ['x87_set(1, x87_st(1) * log(x87_st(0)));', 'x87_pop();']
            fl.write('    case %d: { /* %s */\n' % (o['id'], dis.replace('*/', '* /')))
            for ln in lines:
                fl.write('  ' + ln + '\n')
            if nega_c1 and o['name'] == 'fxam':
                fl.write('  ott_fsw ^= 0x0200u;   /* negative control: C1 (符号) を反転 */\n')
            if nega_env and o['typ'] in ('env', 'save'):
                fl.write('  ((uint8_t*)p)[8] ^= 0x55;   /* negative control: 格納した環境の TW を壊す (#3688) */\n')
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


def f80_value(rng):
    """80bit の値 (lo = 仮数 64bit, hi = 符号・指数 16bit)。 double に丸まる仮数・double に正確に入る値・±0・±inf・
    qNaN・sNaN・非正規・f64 の指数域外を混ぜる (有効な符号化だけを作る: 非正規の指数は 0、正規の指数は bit63 = 1)。"""
    sign = rng.getrandbits(1) << 15
    r = rng.random()
    if r < 0.40 or r >= 0.92:      # 64bit 仮数の通常値 (double に丸まる)
        return (1 << 63) | rng.getrandbits(63), sign | rng.randint(16383 - 40, 16383 + 40)
    if r < 0.55:                   # double の正規値をそのまま f80 にしたもの (仮数 53bit)
        b = struct.unpack('<Q', struct.pack('<d', rand_double(rng)))[0]
        ex = (b >> 52) & 0x7ff
        if ex == 0:
            return 0, sign
        return (1 << 63) | ((b & ((1 << 52) - 1)) << 11), ((b >> 63) << 15) | (ex - 1023 + 16383)
    if r < 0.60:                   # ±0
        return 0, sign
    if r < 0.66:                   # ±inf
        return 1 << 63, sign | 0x7fff
    if r < 0.72:                   # qNaN
        return (1 << 63) | (1 << 62) | rng.getrandbits(62), sign | 0x7fff
    if r < 0.76:                   # sNaN (bit62 = 0・仮数の下位が非零)
        return (1 << 63) | (rng.getrandbits(62) | 1), sign | 0x7fff
    if r < 0.82:                   # 非正規 (指数 0・bit63 = 0・仮数 ≠ 0)
        return rng.getrandbits(63) | 1, sign
    # f64 の指数域の外 (大きい指数は inf、小さい指数は非正規の double に丸まる)
    e = rng.randint(17408, 0x7ffe) if rng.random() < 0.5 else rng.randint(1, 15360)
    return (1 << 63) | rng.getrandbits(63), sign | e


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


def slot_pair(rng, typ, rc=None):
    """slot の (lo, hi) 語。 rc を与えた 'c' は乱数を消費せず固定値を返す (RC 試行の RC 間で試行列を揃える)。"""
    if typ == 'e':
        return f80_value(rng)
    if typ == 'c' and rc is not None:
        return 0x037f | (rc << 10), 0
    return slot_value(rng, typ), 0


def gen_trials(insts, n, seed, mode, rc_fixed=None):
    rng = random.Random(seed)
    lines, metas = [], []
    fldcw = next((o for o in insts if o['name'] == 'fldcw'), None)
    for _ in range(n):
        if mode == 'rc':
            kinds = ['c'] + [rng.choices(['d', 'i', 'q'], [6, 2, 2])[0] for _ in range(5)]
        elif mode == 'rcarith':
            kinds = ['c'] + [rng.choices(KINDS, KIND_W)[0] for _ in range(5)]
        elif mode == 'env':   # 状態の保存・復元 (#3688): f80 の入力 (e) は外す (f80 の値は f64 に乗らない: ADR D28)
            kinds = [rng.choices(['d', 'f', 'i', 'q'], [6, 2, 2, 2])[0] for _ in range(6)]
        else:
            kinds = [rng.choices(KINDS, KIND_W)[0] for _ in range(6)]
        pairs = [slot_pair(rng, k, rc_fixed if mode == 'rcarith' else None) for k in kinds] + [(0, 0), (0, 0)]
        slot_of = {k: [s for s in range(6) if kinds[s] == k] for k in set(kinds)}
        ops, depth = [], 0
        last = None    # env 試行: 直近の環境格納 (typ, 格納時の深さ)。 fldenv / frstor はこれを読む
        if mode in ('rc', 'rcarith'):
            ops.append((fldcw, 0))
        nsteps = rng.randint(2, 7)
        for _ in range(nsteps):
            cand = []
            for o in insts:
                if mode != 'env' and o['typ'] in ENV_TYPS:       # 既存モードの試行列は変えない
                    continue
                if mode == 'rc' and o['name'] not in RC_NAMES:   # RC 試行は丸め (fist/fistp) だけを見る: 算術を含めない
                    continue
                if mode != 'rc' and o['typ'] == 'c':              # 通常試行・RC 固定試行は RC を動かさない
                    continue
                if mode == 'env':
                    if o['name'] not in ENV_NAMES or o['typ'] in ('c', 'w4'):   # fst m32 は丸めを含むので外す
                        continue
                    if o['typ'] == 'envld' and (last is None):
                        continue
                    if o['typ'] == 'saveld' and (last is None or last[0] != 'save'):   # frstor は fnsave の直後の格納だけ
                        continue
                    if o['typ'] in ENV_TYPS and rng.random() < 0.5:
                        continue                                  # 環境 op の比率を抑える
                if o['form'] == 'reg' and o['i'] + 1 > depth:
                    continue
                if o['need'] > depth or not (0 <= depth + o['delta'] <= 8):
                    continue
                if o['form'] == 'mem' and not o['typ'].startswith('w') and o['typ'] not in ENV_TYPS \
                        and not slot_of.get(slot_key(o)):
                    continue
                if o['form'] == 'reg' and o['name'] == 'fxch' and o['i'] == 0:
                    continue
                cand.append(o)
            if not cand:
                break
            o = rng.choice(cand)
            if o['typ'] in ENV_TYPS:
                sl = 8
            elif o['form'] == 'mem':
                sl = rng.choice([6, 7]) if o['typ'].startswith('w') else rng.choice(slot_of[slot_key(o)])
            else:
                sl = -1
            ops.append((o, sl))
            if o['typ'] in ('env', 'save'):
                last = (o['typ'], depth)
                depth = 0 if o['typ'] == 'save' else depth   # fnsave は FINIT (深さ 0)
            elif o['typ'] in ('envld', 'saveld'):             # 復元: 格納時の深さに戻る
                depth = last[1]
            else:
                depth += o['delta']
        if depth == 0:
            o = next(x for x in insts if x['name'] == 'fld1')
            ops.append((o, -1))
            depth = 1
        if mode == 'env':   # 末尾の環境格納: 最終の CW・SW (CMASK)・TW を比べる (#3688)
            ops.append((next(x for x in insts if x['name'] == 'fnstenv'), 8))
        tok = ' '.join('%016x %016x' % p for p in pairs)
        body = ' '.join('%d %d' % (o['id'], sl) for o, sl in ops)
        lines.append('%s %d %s %d' % (tok, len(ops), body, depth))
        metas.append((ops, depth, rc_fixed if mode == 'rcarith' else None))
    return lines, metas


def op_class(ops):
    ar = any(o['name'] in ARITH_NAMES for o, _ in ops)
    f32 = any(o['name'] in ('fst', 'fstp') and o['typ'] == 'w4' for o, _ in ops)
    if ar and f32:
        return 'both'
    if ar:
        return 'arith'
    return 'fst32' if f32 else 'neither'


def has_m80(ops):
    return any(o['typ'] in ('e', 'w10') for o, _ in ops)


def compare(nat, low, metas):
    st = dict(trials=0, identical=0, ulp_hist=[0, 0, 0, 0], vals=0, vals_ulp_hist=[0, 0, 0, 0], cmp_ops=0, cmp_match=0,
              f_mismatch_trials=0, s_mismatch_trials=0, ulp_step_bad=0, ulp_max=0,
              m80_trials=0, m80_identical=0, cls={c: [0, 0] for c in CLASSES}, op={}, f_first={}, f_mis_nom80=0)
    for a, b, (ops, d, _) in zip(nat, low, metas):
        ta, tb = a.split(), b.split()
        iv_a, is_a = ta.index('V'), ta.index('S')
        iv_b, is_b = tb.index('V'), tb.index('S')
        # S の後ろに環境の欄 (E) が付く (env 試行)。 S は E の手前まで
        ea_, eb_ = (ta.index('E') if 'E' in ta else len(ta)), (tb.index('E') if 'E' in tb else len(tb))
        Fa, Va, Sa = ta[1:iv_a], ta[iv_a + 1:is_a], ta[is_a + 1:ea_]
        Fb, Vb, Sb = tb[1:iv_b], tb[iv_b + 1:is_b], tb[is_b + 1:eb_]
        st['trials'] += 1
        fm = [CMASK | (C1BIT if o['cmp'] else 0) for o, _ in ops]
        fok = all((int(x, 16) & m) == (int(y, 16) & m) for x, y, m in zip(Fa, Fb, fm))
        for o, sl in ops:   # fnstsw m16 の格納値は PE/C1 等の未モデル化の例外フラグを含むため、CMASK で比べる (ADR 制限 4)
            if o['name'] == 'fnstsw' and o['form'] == 'mem':
                for S in (Sa, Sb):
                    x = int(S[2 * sl], 16)
                    S[2 * sl] = '%016x' % ((x & ~0xffff) | (x & CMASK))
        sok = Sa == Sb
        # env 試行: 格納した環境 (CW・SW の CMASK・TW) を比べる。 比べる欄は E の後ろ (driver が書く)
        Ea, Eb = ta[ea_:], tb[eb_:]
        if Ea != Eb:
            sok = False
        if not fok:
            st['f_mismatch_trials'] += 1
            if not has_m80(ops):
                st['f_mis_nom80'] += 1
            for k, (o, _) in enumerate(ops):
                if (int(Fa[k], 16) & (CMASK | (C1BIT if o['cmp'] else 0))) != (int(Fb[k], 16) & (CMASK | (C1BIT if o['cmp'] else 0))):
                    st['f_first'][o['name']] = st['f_first'].get(o['name'], 0) + 1
                    break
        if not sok:
            st['s_mismatch_trials'] += 1
        for k, (o, _) in enumerate(ops):
            if o['cmp']:
                st['cmp_ops'] += 1
                if (int(Fa[k], 16) & 0x4700) == (int(Fb[k], 16) & 0x4700):
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
        ident = fok and sok and Va == Vb
        if ident:
            st['identical'] += 1
        for nm in set(o['name'] for o, _ in ops):
            st['op'].setdefault(nm, [0, 0])
            st['op'][nm][0] += 1
            st['op'][nm][1] += int(ident)
        c = op_class(ops)
        st['cls'][c][0] += 1
        st['cls'][c][1] += int(ident)
        if has_m80(ops):
            st['m80_trials'] += 1
            st['m80_identical'] += int(ident)
    return st


def build_ref(wd, skip_build):
    bn = os.path.join(wd, 'x87_native')
    bl = os.path.join(wd, 'x87_lowered')
    if not skip_build:
        src_n = os.path.join(HERE, 'x87_diff_native.c')
        src_l = os.path.join(HERE, 'x87_diff_lowered.c')
        subprocess.run(['gcc', '-O1', '-w', '-I', wd, '-o', bn, src_n, '-lm'], check=True)
        subprocess.run(['gcc', '-O1', '-w', '-DOTT_X87_DOMAIN_SOFT', '-I', RT, '-I', wd, '-o', bl, src_l,
                        os.path.join(RT, 'ott_cpu.c'), '-lm'], check=True)
    return bn, bl


def roundtrip(n, skip_build):
    """f80↔f64 変換の往復試験 (x87_f80_rt.c)。 出力は類ごとの件数 (bad = 不一致の件数)。"""
    wd = os.path.join(WORK, 'roundtrip')
    os.makedirs(wd, exist_ok=True)
    b = os.path.join(wd, 'x87_f80_rt')
    if not skip_build:
        subprocess.run(['gcc', '-O1', '-w', '-I', RT, '-o', b, os.path.join(HERE, 'x87_f80_rt.c'), '-lm'], check=True)
    r = subprocess.run([b, str(n)], stdout=subprocess.PIPE, text=True, timeout=900)
    if r.returncode != 0:
        raise SystemExit('[x87_diff] roundtrip rc %d' % r.returncode)
    print('[x87_diff] roundtrip n=%d per class (R1 f64->f80 native, R2 f80->f64 native, R3 f64->f80->f64 lowered, '
          'R4 f80->f64->f80 lowered)' % n)
    for ln in r.stdout.splitlines():
        print('[x87_diff] ' + ln)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=100000)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--nega', action='store_true', help='lowered 側に fsub/fsubr の取り違えを入れる (negative control)')
    ap.add_argument('--nega80', action='store_true', help='lowered 側の fstp m80 を fstp m64 に取り違える (negative control・m80)')
    ap.add_argument('--rc', action='store_true', help='fldcw で RC を変え fist/fistp の丸めだけを比べる')
    ap.add_argument('--rc-arith', type=int, choices=(0, 1, 2, 3), default=None,
                    help='fldcw で RC を固定 (0 nearest / 1 down / 2 up / 3 trunc)。 算術・fst m32 を含む全 op で比べる')
    ap.add_argument('--nega-c1', action='store_true', help='lowered 側の fxam の直後に C1 を反転させる (negative control・#2966)')
    ap.add_argument('--env', action='store_true', help='状態の保存・復元 (fnstenv/fldenv/fnsave/frstor) の試行 (#3688)')
    ap.add_argument('--nega-env', action='store_true', help='lowered 側で格納した環境の TW を壊す (negative control・#3688)')
    ap.add_argument('--nega-trig', action='store_true', help='lowered 側の fyl2x を log2 でなく自然対数にする (negative control・#3687)')
    ap.add_argument('--skip', default='', help='試行の op 表から外す名前 (カンマ区切り。例: fldpi,fldlg2,fldl2e・#2966)')
    ap.add_argument('--only', default='', help='試行の op 表をこの名前だけにする (カンマ区切り。例: fld,fld1,fscale・#3687)')
    ap.add_argument('--no-e', action='store_true', help='入力を double で正確に表せる型 (d/f/i/q) だけにし、m80 の命令を外す (f80 の入力丸めを除く・#3687)')
    ap.add_argument('--roundtrip', action='store_true', help='f80↔f64 変換の往復試験 (--n はクラスごとの件数)')
    ap.add_argument('--skip-build', action='store_true')
    a = ap.parse_args()
    if a.roundtrip:
        roundtrip(a.n, a.skip_build)
        return
    mode = 'rcarith' if a.rc_arith is not None else ('rc' if a.rc else ('env' if (a.env or a.nega_env) else 'main'))
    if a.nega80:
        tag = 'nega80'
    elif a.nega:
        tag = 'nega'
    elif mode == 'rcarith':
        tag = 'rcarith%d' % a.rc_arith
    else:
        tag = mode
    skip = set(x for x in a.skip.split(',') if x)
    if skip:
        tag += '_skip'
    if a.nega_c1:
        tag = 'nega_c1'
    if a.nega_env:
        tag = 'nega_env'
    if a.nega_trig:
        tag = 'nega_trig'
    only = set(x for x in a.only.split(',') if x)
    if only:
        tag += '_only_' + '_'.join(sorted(only))
    if a.no_e:
        tag += '_no_e'
        KINDS[:] = ['d', 'f', 'i', 'q']
        KIND_W[:] = [4, 2, 2, 2]
    wd = os.path.join(WORK, tag)
    os.makedirs(wd, exist_ok=True)
    insts = instances(templates())
    trial_insts = [o for o in insts if o['name'] not in skip and (not only or o['name'] in only)
                   and not (a.no_e and o['typ'] in ('e', 'w10'))]
    inc_n = os.path.join(wd, 'x87_native_ops.inc')
    inc_l = os.path.join(wd, 'x87_lowered_ops.inc')
    write_inc(insts, a.nega, a.nega80, inc_n, inc_l, a.nega_c1, a.nega_trig, a.nega_env)
    bn, bl = build_ref(wd, a.skip_build)
    lines, metas = gen_trials(trial_insts, a.n, a.seed, mode, a.rc_arith)
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
    print('[x87_diff] compare ops %d, C0-C3 match %d' % (st['cmp_ops'], st['cmp_match']))
    print('[x87_diff] FSW(masked) mismatch trials %d, slot mismatch trials %d, ulp cross-check bad %d' % (
        st['f_mismatch_trials'], st['s_mismatch_trials'], st['ulp_step_bad']))
    print('[x87_diff] m80 trials (fld/fstp m80 を含む) %d, bit-identical %d (%.2f%%)' % (
        st['m80_trials'], st['m80_identical'], 100.0 * st['m80_identical'] / max(1, st['m80_trials'])))
    print('[x87_diff] class (bit-identical/trials): ' + ', '.join(
        '%s %d/%d' % (c, st['cls'][c][1], st['cls'][c][0]) for c in CLASSES))
    print('[x87_diff] FSW mismatch trials without m80 input %d' % st['f_mis_nom80'])
    print('[x87_diff] FSW first mismatch op: ' + ', '.join('%s %d' % kv for kv in sorted(st['f_first'].items())))
    print('[x87_diff] op (bit-identical/trials containing op): ' + ', '.join(
        '%s %d/%d' % (k, v[1], v[0]) for k, v in sorted(st['op'].items())))


if __name__ == '__main__':
    main()
