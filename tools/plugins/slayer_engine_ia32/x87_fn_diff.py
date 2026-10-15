#!/usr/bin/env python3
"""x87_fn_diff.py: x87 を含む Slayer_Engine.dll (block22434) の関数を native (実 x87 命令) と wasm (ia32 x64c lift・ott_x87.h の double) で実行し、
戻り値 eax・ST(0)・x87 の深さ・書込み先メモリ (OBJ 窓 0x540 B) を突合する (#2989 PLG-G2-25)。

  python3 x87_fn_diff.py          実行 + 突合 (行数・eax・x87 深さの不一致と、有効な実行でないときは exit 1)
                                  float 語 (ST(0)・OBJ 窓) の bit 差分は落とさず、ulp の分布として実測する (ADR D28: f80→f64)
  python3 x87_fn_diff.py --nega   ネガコン: 突合済みの wasm 出力で bit 一致の行の ST(0) の最下位 bit を壊し、
                                  bit 一致件数がちょうど 1 減ることを確かめる (減れば検出 = exit 0)
  python3 x87_fn_diff.py --nega-lower  意味のネガコン: lowering の 1 演算 (f_10002ee0 の fsubp の SUB→SUBR) を取り違えた wasm を作り、
                                  float32 結果が一致しない行が出ることを確かめる (出れば検出 = exit 0)。 先に通常の実行が要る

入力: $FL_WIN64_DIR/extracted/block22434_PE.bin (既定 $RUNNER_TEMP/fl-win64)、 work/lift_text/ott_lifted.c (lift_text.py が作る)。
出力: work/x87fn/ (gitignore)。
native: x87_fn_native.c (freestanding i386 ELF)。 wasm: x87_fn_glue.c (ott_lifted.c を同じ翻訳単位に取り込む) + ott_cpu.c → emcc。
"""
import os, random, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..'))
RT = os.path.join(ROOT, 'tools', 'ott', 'rt')
WORK = os.path.join(HERE, 'work', 'x87fn')
LIFT = os.path.join(HERE, 'work', 'lift_text', 'ott_lifted.c')
IMG_BASE = 0x10000000
OBJ = 0x10F80000
# #4147: ecx 相対の読みを持つ関数の基底。 窓 (ECX_HI..+0x540) は image の外・16MB 内 (ecx+0x821700 < 0x11000000)。 ecx 基底のゼロ埋め領域。
ECX_HI = 0x10700000
OBJ_WIN = 0x540
N_PER_TARGET = 4000
N_PER_MIXED = 200
SEED = 2989

# va: 入口 VA。 gen: 引数と OBJ 窓の初期値の作り方 (ecx = OBJ)。 どちらも leaf で x87 を含み、import・未 lift の call が無い。
#   fn_10002ee0: thiscall (ecx = this、float a0、int a1 = 添字 0..15) ret 8。 [ecx+a1*4+0xb0..0x1f4] を読み書きし、ST(0) を残して返る。
#   fn_10005400: thiscall (ecx = this、float a0..a2) ret 0xc。 fcomp・fnstsw・fdivr を含み、[ecx+0x4fc..0x518] を更新する。 gen が積む a3・a4 (と a5 = 0) は本体が読まない余りの引数。
#   fn_1000b6c1・fn_1000b936: OBJ 窓を書かず、ebp 相対のスタック (STK_LO..STK_LO+STK_WIN) だけを書く leaf (#4146)。 引数は gen_rows の既定を使う。
#     どちらも入口で空の ST(0) を読まない (fstp st(0) で捨てるだけ) ので、空スタックの underflow に依らない。
#   fn_1000b8a2 は TARGETS に入れない (#4146): 入口の fstp TBYTE が空の ST(0) を読み、native は -qNaN 不定値・wasm は 0 を返す (underflow 類型)。
TARGETS = [
    {'va': 0x10002EE0, 'name': 'fn_10002ee0', 'gen': 'idx_store'},
    {'va': 0x10005400, 'name': 'fn_10005400', 'gen': 'state_update'},
    {'va': 0x1000B6C1, 'name': 'fn_1000b6c1', 'gen': 'state_update'},
    {'va': 0x1000B936, 'name': 'fn_1000b936', 'gen': 'state_update'},
    # #3715 (PLG-G2-31): lift 済みの残り leaf x87 関数 (call・間接分岐・未対応命令を含まず、x87 を含む)。
    # 引数の型は関数ごとに分からないので、a0 は float、a1..a5 は 0..15 の整数 (gen 'mixed')。 行数は N_PER_MIXED。
    # 1000b3a2・10001290 は OBJ 窓もスタックも書かず ST(0) だけを返すため、main の非自明性の判定 (effect) を通らず、範囲から外した (REPORT_APPENDIX_3715.md §5)。
    {'va': 0x10005D20, 'name': 'fn_10005d20', 'gen': 'mixed'},
    # #4080 (PLG-G2-43): 独立入口 (direct call 先) のうち突合が通る 2 本。 thiscall (ecx = this、float a0..a2、ret 0xc)。
    # 100052d0・10005550 の float64 差は 1 ulp (f80→f64。 D28)。 float32 と構造は全行一致。
    {'va': 0x100052D0, 'name': 'fn_100052d0', 'gen': 'state_update'},
    {'va': 0x10005550, 'name': 'fn_10005550', 'gen': 'state_update'},
]
# ebp = 0x10F00000 - 0x1000 (x87_fn_native.c・x87_fn_glue.c)。 窓は ebp-0x100 から ebp+0xE0 (旧 ebp 0x10EFFF00 と同じ相対位置)。
STK_LO = 0x10F00000 - 0x1100
STK_WIN = 0x1E0
# #4064: 3 本の測定専用 (X87_PROBE=1 で TARGETS に加える)。 ゲートは通さない: 3 本 (0x10009eb5・0x1000b526 は eax が模型の限界で不一致、0x1000bf60 は ST(0) の NaN・ゼロが不一致)。 付録 §1 を参照。
PROBE = [
    {'va': 0x10009EB5, 'name': 'fn_10009eb5', 'gen': 'generic'},
    {'va': 0x1000B526, 'name': 'fn_1000b526', 'gen': 'generic'},
    # #4105: 0x1000bf60 は fld tbyte [esp+0x10] (a3..a5) と [esp+4] (a0..a2) の 2 つの f80 を割る。 generic は a5 = 0 のため X の指数が常に 0 (非 normal)。
    # f80pair は両オペランドを種類 (normal・zero・denorm・unnorm) つきで作り、normal×normal の行を含める。
    {'va': 0x1000BF60, 'name': 'fn_1000bf60', 'gen': 'f80pair'},
    # #4080: double 引数の 1 本 (cdecl・a0 = double)。 1000bf1e は OBJ 窓を書かないので effect 判定が 0 になる (構造は全行一致・float 全行一致)。
    {'va': 0x1000BF1E, 'name': 'fn_1000bf1e', 'gen': 'double1'},
    # #4840: 空スタックで呼ぶ基準線 (ST(0) の入力を積まない)。 入力は X87_PUSH64=1 で測る (付録 REPORT_APPENDIX_4840.md)。
    # 同じ name を PROBE に 2 つ置くと agg が混ざるため、#4080 の 10009bc4 (double1) 行はここでは外す。
    {'va': 0x10009BC4, 'name': 'fn_10009bc4', 'gen': 'generic'},
]
# #4147 (PLG-G2-50): ecx 相対の読みが 0x80174〜0x821700 に及ぶ関数。 ecx = OBJ (0x10F80000) では 16MB の窓の外に出て native が segfault した (rc 139)。
# ecx を ECX_HI に置くと segfault は消える。 ただし判定 (非自明性 = OBJ 窓が変わること) は通らない: 書込みが窓の外 (0x10003fe0・0x100051f0)・
# 窓を読むだけ (0x1000a95a) のため。 測定専用 (X87_PROBE=1)。 0x100085a0・0x100096d0 は窓の中身をポインタとして辿り、0x1000ba05 は edx 経由の引数のため、入力の設計が別に要る (子 issue)。
PROBE_ECX = [
    {'va': 0x10003FE0, 'name': 'fn_10003fe0', 'gen': 'mixed', 'ecx': ECX_HI},
    {'va': 0x100051F0, 'name': 'fn_100051f0', 'gen': 'mixed', 'ecx': ECX_HI},
    {'va': 0x1000A95A, 'name': 'fn_1000a95a', 'gen': 'ptr_win', 'ecx': ECX_HI},
]
if os.environ.get('X87_PROBE'):
    TARGETS = TARGETS + PROBE + PROBE_ECX
# #4840: double 入力の測定専用 (X87_PUSH64=1)。 呼出し前に double 1 個を x87 に積む (a0 = 下位 dword・a1 = 上位 dword)。
#   native・glue を -DX87_PUSH64 で作る。 ゲートには入れない (既存の TARGETS の入口状態は変えない)。
PUSH64 = bool(os.environ.get('X87_PUSH64'))
if PUSH64:
    TARGETS = [
        {'va': 0x10009BC4, 'name': 'fn_10009bc4', 'gen': 'f64'},
    ]
    WORK_NAME = 'x87fn_push64'
else:
    WORK_NAME = 'x87fn'
PUSH64_FLAGS = ['-DX87_PUSH64'] if PUSH64 else []
for _t in TARGETS:
    _t.setdefault('ecx', OBJ)


def pe_image():
    import pefile
    d = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
    p = os.path.join(d, 'extracted', 'block22434_PE.bin')
    if not os.path.isfile(p):
        sys.exit('[x87_fn_diff] FAIL: %s が無い (素材 fl-win64 を展開すること)' % p)
    pe = pefile.PE(p)
    if pe.OPTIONAL_HEADER.ImageBase != IMG_BASE:
        sys.exit('[x87_fn_diff] FAIL: ImageBase 0x%x != 0x%x' % (pe.OPTIONAL_HEADER.ImageBase, IMG_BASE))
    img = bytearray(pe.OPTIONAL_HEADER.SizeOfImage)
    for s in pe.sections:
        raw = s.get_data()[:s.Misc_VirtualSize or len(s.get_data())]
        img[s.VirtualAddress:s.VirtualAddress + len(raw)] = raw
    return bytes(img)


def f32(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def gen_rows(seed, n):
    """(target, 行の文字列, OBJ 窓の初期値 bytes) の列。 入力は乱数 (一様な有限の float32 と添字)。"""
    rng = random.Random(seed)
    rows = []
    for t in TARGETS:
        for _ in range(n if t['gen'] != 'mixed' else N_PER_MIXED):
            init = b''.join(struct.pack('<f', rng.uniform(-1000, 1000)) for _ in range(OBJ_WIN // 4))
            if t['gen'] == 'idx_store':
                a = [f32(rng.uniform(-1000, 1000)), rng.randrange(16), 0, 0, 0, 0]
            elif t['gen'] == 'mixed':
                a = [f32(rng.uniform(-100, 100))] + [rng.randrange(16) for _ in range(5)]
            elif t['gen'] == 'ptr_win':
                a = [t['ecx']] + [0] * 5
            elif t['gen'] == 'f80pair':
                a = f80_args(rng)
            elif t['gen'] == 'f64':
                d = struct.unpack('<Q', struct.pack('<d', rng.uniform(-1000, 1000)))[0]
                a = [d & 0xFFFFFFFF, d >> 32, 0, 0, 0, 0]
            elif t['gen'] == 'double1':
                d = struct.unpack('<Q', struct.pack('<d', rng.uniform(-100, 100)))[0]
                a = [d & 0xFFFFFFFF, d >> 32, rng.randrange(16), 0, 0, 0]
            else:
                a = [f32(rng.uniform(-100, 100)) for _ in range(5)] + [0]
            line = '%08x %08x %s %s' % (t['va'], t['ecx'], ' '.join('%08x' % v for v in a), init.hex())
            rows.append((t, line, init))
    return rows


F80_KINDS = ['norm', 'norm', 'denorm', 'unnorm', 'zero']


def f80_one(rng, kind):
    """f80 (mantissa 64bit・指数 16bit 符号付き) を (lo32, hi32, se16) で返す。 kind: norm・denorm・unnorm・zero。"""
    sign = rng.randrange(2)
    if kind == 'zero':
        return 0, 0, sign << 15
    if kind == 'denorm':
        mant = rng.randrange(1, 1 << 63)
        return mant & 0xFFFFFFFF, mant >> 32, sign << 15
    if kind == 'unnorm':
        mant = rng.randrange(1, 1 << 63)
        e = rng.randrange(1, 0x7FFE)
        return mant & 0xFFFFFFFF, mant >> 32, (sign << 15) | e
    mant = (1 << 63) | rng.randrange(1 << 63)
    e = rng.randrange(0x3F80, 0x4080)
    return mant & 0xFFFFFFFF, mant >> 32, (sign << 15) | e


def f80_args(rng):
    """a = [X.lo, X.hi, X.se, Y.lo, Y.hi, Y.se] (X は [esp+0x10] 側 = a3..a5、Y は [esp+4] 側 = a0..a2)。 gen_rows の既定 (a0..a5 の 6 語) を満たす。"""
    yk = rng.choice(F80_KINDS)
    xk = rng.choice(F80_KINDS)
    yl, yh, ys = f80_one(rng, yk)
    xl, xh, xs = f80_one(rng, xk)
    return [yl, yh, ys, xl, xh, xs]


SPECIAL_F32 = [
    0x7FC00000,  # qNaN
    0xFFC00000,  # -qNaN
    0x7F800001,  # sNaN
    0x7F800000,  # +inf
    0xFF800000,  # -inf
    0x00000001,  # 最小の正の非正規数
    0x807FFFFF,  # 最大の負の非正規数
    0x00000000,  # +0
    0x80000000,  # -0
]


SPECIAL_F64 = [
    0x7FF8000000000000,  # qNaN
    0xFFF8000000000000,  # -qNaN
    0x7FF0000000000000,  # +inf
    0xFFF0000000000000,  # -inf
    0x0000000000000001,  # 最小の正の非正規数
    0x0000000000000000,  # +0
    0x8000000000000000,  # -0
    0x41DFFFFFFFC00000,  # 2^31 - 1 (int32 の上限付近)
    0xC1E0000000000000,  # -2^31
    0x41E0000000000000,  # 2^31 (int32 を超える)
]


def gen_special_rows(seed, n):
    """例外的な値 (NaN・±inf・非正規・±0 = 除算の除数) を含む行。 通常行と別の乱数系列を使う (通常行の列は変えない)。
    a0 は SPECIAL_F32 を巡回させて全種を必ず通す。 OBJ 窓の各語は 1/4 で例外値にする (除数の位置を含めるため)。"""
    rng = random.Random(seed + 1)
    rows = []
    for t in TARGETS:
        for i in range(n):
            words = [rng.choice(SPECIAL_F32) if rng.random() < 0.25 else f32(rng.uniform(-1000, 1000))
                     for _ in range(OBJ_WIN // 4)]
            init = b''.join(struct.pack('<I', w) for w in words)
            sp = SPECIAL_F32[i % len(SPECIAL_F32)]
            if t['gen'] == 'f64':
                d = SPECIAL_F64[i % len(SPECIAL_F64)] if i % 2 == 0 else struct.unpack('<Q', struct.pack('<d', rng.uniform(-1e12, 1e12)))[0]
                a = [d & 0xFFFFFFFF, d >> 32, 0, 0, 0, 0]
            elif t['gen'] == 'idx_store':
                a = [sp, rng.randrange(16), 0, 0, 0, 0]
            elif t['gen'] == 'double1':
                d = struct.unpack('<Q', struct.pack('<d', rng.uniform(-100, 100)))[0]
                a = [d & 0xFFFFFFFF, d >> 32, rng.randrange(16), 0, 0, 0]
            else:
                a = [sp] + [rng.choice(SPECIAL_F32) if rng.random() < 0.5 else f32(rng.uniform(-100, 100))
                            for _ in range(2)] + [f32(rng.uniform(-100, 100)) for _ in range(2)] + [0]
            line = '%08x %08x %s %s' % (t['va'], t['ecx'], ' '.join('%08x' % v for v in a), init.hex())
            rows.append((t, line, init))
    return rows


def run(cmd, what, timeout=900):
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-1500:] + r.stderr[-1500:])
        sys.exit('[x87_fn_diff] FAIL: %s rc %d' % (what, r.returncode))
    return time.time() - t0


CHUNK = 8000
# #4775: 二つの NaN どうしの add/mul は、V8 の tier (Liftoff と TurboFan) で返す NaN の選び方が違う (仕様で未規定)。
# 既定の tier 切替はタイミングで変わるため、wasm 側は tier を固定して実行し、NaN ビットを再現可能にする。
WASM_TIER = '--liftoff-only'


def run_chunked(scen_path, out_path, cmd_for, what, timeout):
    """native の入出力バッファ (32 MiB) に収まるよう、シナリオを CHUNK 行ずつ実行して出力を連結する。"""
    lines = [ln for ln in open(scen_path).read().split('\n') if ln.strip()]
    t, parts = 0.0, []
    for k in range(0, len(lines), CHUNK):
        cp = os.path.join(WORK, 'chunk_%s_%d.txt' % (what.split()[0], k))
        co = cp + '.out'
        open(cp, 'w').write('\n'.join(lines[k:k + CHUNK]) + '\n')
        t += run(cmd_for(cp, co), what, timeout=timeout)
        parts.append(open(co).read())
    open(out_path, 'w').write(''.join(parts))
    return t


def parse(path):
    out = []
    for ln in open(path):
        p = ln.split()
        if not p:
            continue
        out.append(dict(tok.split('=', 1) for tok in p[1:] if '=' in tok))
    return out


def is_nan(u):
    return (u & 0x7F800000) == 0x7F800000 and (u & 0x007FFFFF) != 0


def ord_key(u):
    return -(u & 0x7FFFFFFF) if u & 0x80000000 else u


def word_class(a, b):
    """float32 語の差の分類: 'eq' (一致) / 1 / 2 / '3+' (ulp) / 'nan' / 'zero' (+0 と -0 の符号のみ)。"""
    if a == b:
        return 'eq'
    if is_nan(a) or is_nan(b):
        return 'nan' if is_nan(a) and is_nan(b) else 'nan-num'
    d = abs(ord_key(a) - ord_key(b))
    if d == 0:
        return 'zero'
    return d if d <= 2 else '3+'


def dword_class(a, b):
    """float64 の差の分類 (word_class の 64bit 版)。"""
    if a == b:
        return 'eq'
    m52 = (1 << 52) - 1
    na = ((a >> 52) & 0x7FF) == 0x7FF and (a & m52) != 0
    nb = ((b >> 52) & 0x7FF) == 0x7FF and (b & m52) != 0
    if na or nb:
        return 'nan' if na and nb else 'nan-num'
    def key(u):
        return -(u & ((1 << 63) - 1)) if u >> 63 else u
    d = abs(key(a) - key(b))
    if d == 0:
        return 'zero'
    return d if d <= 2 else '3+'


def words(hexstr):
    b = bytes.fromhex(hexstr)
    return [int.from_bytes(b[i:i + 4], 'little') for i in range(0, len(b), 4)]


def mismatch_classes(nat, act, scen):
    """#4743: 行の不一致を原因別に数える。 'nan' = NaN どうしのビット差のみ / 'f80' = float64 のみ 1-2 ulp (float32 は一致) / 'other' = それ以外 (0 件が期待)。"""
    h = {}
    for i, (t, line, init) in enumerate(scen):
        e, w = nat[i], act[i]
        if e == w:
            continue
        kinds = set()
        for k in ('eax', 'd', 'st0', 'st0d', 'mem', 'stk'):
            if e[k] == w[k]:
                continue
            if k == 'st0d':
                c = dword_class(int(e[k], 16), int(w[k], 16))
                kinds.add('f80' if c in (1, 2) else ('nan' if c == 'nan' else 'other'))
            elif k in ('mem', 'stk'):
                for x, y in zip(words(e[k]), words(w[k])):
                    if x != y:
                        c = word_class(x, y)
                        kinds.add('nan' if c == 'nan' else 'other')
            else:
                c = word_class(int(e[k], 16), int(w[k], 16))
                kinds.add('nan' if c == 'nan' else 'other')
        if kinds == {'f80'}:
            cls = 'f80 (float64 のみ 1-2 ulp)'
        elif kinds == {'nan'}:
            cls = 'NaN どうしのビット差'
        else:
            cls = '/'.join(sorted(kinds))
        key = (t['name'], cls)
        h[key] = h.get(key, 0) + 1
    for (name, cls), n in sorted(h.items()):
        print('[mismatch] %s: %s %d 行' % (name, cls, n))
    return h


def compare(nat, act, scen, quiet=False):
    """行ごとに突合する。 戻り値 (ok, 集計 dict)。 ok は構造の判定 (行数・eax・x87 深さ・非自明性) のみ。 float 語は分布を集計する。"""
    if len(nat) != len(scen) or len(act) != len(scen):
        print('[compare] FAIL: 件数 native %d / wasm %d / 期待 %d' % (len(nat), len(act), len(scen)))
        return False, None
    ok = True
    agg = {}
    for t in TARGETS:
        agg[t['name']] = {'rows': 0, 'eq': 0, 'f32_eq': 0, 'eax_bad': 0, 'eax_nan': 0, 'd_bad': 0, 'effect': 0,
                          'eaxs': set(), 'st0': {}, 'st0d': {}, 'mem': {}}
    for i, (t, line, init) in enumerate(scen):
        a = agg[t['name']]
        e, w = nat[i], act[i]
        a['rows'] += 1
        if e['eax'] != w['eax']:
            if word_class(int(e['eax'], 16), int(w['eax'], 16)) == 'nan':
                a['eax_nan'] += 1
            else:
                a['eax_bad'] += 1
        if e['d'] != w['d']:
            a['d_bad'] += 1
        if e['mem'] != init.hex() or e['stk'] != '00' * STK_WIN:
            a['effect'] += 1
        a['eaxs'].add(e['eax'])
        if e == w:
            a['eq'] += 1
        if e['st0'] == w['st0'] and e['mem'] == w['mem'] and e['stk'] == w['stk'] and e['eax'] == w['eax']:
            a['f32_eq'] += 1
        for key, x, y in (('st0', int(e['st0'], 16), int(w['st0'], 16)),
                          ('st0d', int(e['st0d'], 16), int(w['st0d'], 16))):
            c = dword_class(x, y) if key == 'st0d' else word_class(x, y)
            a[key][c] = a[key].get(c, 0) + 1
        for x, y in zip(words(e['mem']) + words(e['stk']), words(w['mem']) + words(w['stk'])):
            c = word_class(x, y)
            a['mem'][c] = a['mem'].get(c, 0) + 1
    for t in TARGETS:
        a = agg[t['name']]
        n = a['rows']
        mixed = sum(a[k].get('nan-num', 0) for k in ('st0', 'st0d', 'mem'))
        # 非自明性: 窓が変わった行があるか、PUSH64 (窓を書かない関数) では戻り値 eax の種類が 2 以上あること。
        nontrivial = a['effect'] > 0 or (PUSH64 and len(a['eaxs']) >= 2)
        if a['eax_bad'] or a['d_bad'] or not nontrivial or n == 0 or mixed:
            ok = False
        if quiet:
            continue
        print('[compare] %s (0x%x): %d 行、行の全項目が bit 一致 %d / %d (%.2f%%)、float32 結果 (ST(0)・OBJ 窓) のみ一致 %d / %d' % (
            t['name'], t['va'], n, a['eq'], n, 100.0 * a['eq'] / max(n, 1), a['f32_eq'], n))
        print('[compare]   構造: eax 不一致 %d 行 (NaN どうし %d 行は別計上)・x87 深さ不一致 %d 行 (期待 0)・OBJ 窓が変わった行 %d / %d (非自明性)' % (
            a['eax_bad'], a['eax_nan'], a['d_bad'], a['effect'], n))
        for key, label in (('st0d', 'ST(0) (float64。 80bit→double 丸め後)'), ('st0', 'ST(0) (float32)'),
                           ('mem', 'OBJ 窓 (float32 語)')):
            h = a[key]
            tot = sum(h.values())
            parts = ' / '.join('%s %d' % (c, h.get(c, 0)) for c in ('eq', 1, 2, '3+', 'zero', 'nan', 'nan-num'))
            print('[compare]   %s: %d 語 → %s' % (label, tot, parts))
    return ok, agg


def nega_lower(scen_path, nat_out):
    """意味のネガコン: lowering の 1 演算 (f_10002ee0 の最初の fsubp: X87_SUB → X87_SUBR) を取り違えた lift で wasm を作り直す。
    float32 結果が一致しない行が出れば、この試験は lowering の意味の誤りを検出できる (exit 0)。"""
    src = open(LIFT).read()
    start = src.index('void f_10002ee0(void) {')
    end = src.index('\n}\n', start)
    key = 'x87_arith(2, 1, x87_st(0), 1);'
    body = src[start:end]
    if key not in body:
        sys.exit('[nega-lower] FAIL: f_10002ee0 に %s が無い' % key)
    mut_dir = os.path.join(WORK, 'mut')
    os.makedirs(mut_dir, exist_ok=True)
    mut_lift = os.path.join(mut_dir, 'ott_lifted_mut.c')
    open(mut_lift, 'w').write(src[:start] + body.replace(key, key.replace('(2, 1', '(3, 1'), 1) + src[end:])
    mut_mjs = os.path.join(mut_dir, 'wasm_mut.cjs')
    run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', RT,
         '-DLIFT_C="%s"' % mut_lift, os.path.join(HERE, 'x87_fn_glue.c'), os.path.join(RT, 'ott_cpu.c'),
         '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
         '-sEXPORTED_FUNCTIONS=_ott_call32x,_ott_x87_st0,_ott_x87_st0d_hi,_ott_x87_st0d_lo,_ott_x87_depth',
         '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
         '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
         '-sALLOW_MEMORY_GROWTH=0', '-o', mut_mjs], 'mutant wasm build (emcc)', timeout=900)
    mut_out = os.path.join(mut_dir, 'wasm_out.txt')
    run(['node', WASM_TIER, os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mut_mjs, os.path.join(WORK, 'image.bin'), scen_path, mut_out],
        'mutant wasm run (node)', timeout=900)
    _, agg = compare(parse(nat_out), parse(mut_out), scen_for_compare(scen_path))
    return agg[TARGETS[0]['name']]


def scen_for_compare(scen_path):
    rows = []
    for ln in open(scen_path):
        p = ln.split()
        if not p:
            continue
        va = int(p[0], 16)
        t = next(t for t in TARGETS if t['va'] == va)
        rows.append((t, ln, bytes.fromhex(p[8])))
    return rows


CLASSIFY_ENTRIES = [
    0x100052D0, 0x10005550, 0x10009BC4, 0x1000BF1E, 0x1000C084,
    0x1000C08F, 0x1000C09A, 0x1000C0A0, 0x1000C0A6, 0x1000C0AC,
]


def classify():
    """#4066: 入口候補の判定規則 (機械的)。 PE 全体の code section を走査する。
    - 'callee': 直接の call (E8 rel32) の先。 独立した入口として扱える (TARGETS 候補)。
    - 'switch-arm': direct call が無く、間接ジャンプテーブル (ff 24 85 disp32) のエントリとして現れる。
      断片。 テーブルを引く ff 24 85 の位置を詳細に出す。 親関数の入口は規則では決めない (手で確認する)。
    - 'tail-jmp-only': direct call が無く、直接の jmp (E9) の先だけ。 規則では判定しない (手で確認する)。
    - 'unreferenced': どの参照も無い。
    戻り値は {va: (verdict, 詳細)}。 同じ入力で同じ結果を返す。"""
    img = pe_image()
    import pefile
    d = os.environ.get('FL_WIN64_DIR') or os.path.join(os.environ.get('RUNNER_TEMP', ''), 'fl-win64')
    pe = pefile.PE(os.path.join(d, 'extracted', 'block22434_PE.bin'))
    code = [(s.VirtualAddress, s.Misc_VirtualSize or s.SizeOfRawData) for s in pe.sections
            if s.Characteristics & 0x20000000]
    call_tgts = {}
    jmp_tgts = {}
    switch_sites = []
    for rva0, size in code:
        for i in range(rva0, min(rva0 + size, len(img) - 5)):
            op = img[i]
            if op in (0xE8, 0xE9):
                dst = (IMG_BASE + i + 5 + struct.unpack_from('<i', img, i + 1)[0]) & 0xFFFFFFFF
                (call_tgts if op == 0xE8 else jmp_tgts).setdefault(dst, []).append(IMG_BASE + i)
            elif op == 0xFF and img[i + 1] == 0x24 and img[i + 2] == 0x85:
                switch_sites.append((IMG_BASE + i, struct.unpack_from('<I', img, i + 3)[0]))
    out = {}
    for va in CLASSIFY_ENTRIES:
        if va in call_tgts:
            out[va] = ('callee', 'call from %s' % ', '.join('0x%x' % x for x in call_tgts[va]))
            continue
        sites = [s for s, tbl in switch_sites if any(
            img[tbl - IMG_BASE + 4 * k:tbl - IMG_BASE + 4 * k + 4] == struct.pack('<I', va) for k in range(256))]
        if sites:
            out[va] = ('switch-arm', 'table at ff24 0x%x' % sites[0])
            continue
        if va in jmp_tgts:
            out[va] = ('tail-jmp-only', 'jmp from %s' % ', '.join('0x%x' % x for x in jmp_tgts[va]))
            continue
        out[va] = ('unreferenced', '')
    return out


def main():
    global WORK
    if '--classify' in sys.argv:
        for va, (verdict, detail) in classify().items():
            print('[classify] 0x%x %s %s' % (va, verdict, detail))
        sys.exit(0)
    if PUSH64:
        WORK = os.path.join(HERE, 'work', WORK_NAME)
    nega = '--nega' in sys.argv
    special = '--special' in sys.argv
    if special:
        WORK = os.path.join(HERE, 'work', 'x87fn_special')
    if '--nega-lower' in sys.argv:
        scen_path = os.path.join(WORK, 'scen.txt')
        if not os.path.isfile(os.path.join(WORK, 'native_out.txt')):
            sys.exit('[nega-lower] FAIL: 先に python3 x87_fn_diff.py を実行して native_out.txt を作る')
        a = nega_lower(scen_path, os.path.join(WORK, 'native_out.txt'))
        f32_bad = a['rows'] - a['f32_eq']
        print('[nega-lower] fn_10002ee0: float32 結果が一致しない行 %d / %d (lowering の 1 演算の取り違え)' % (f32_bad, a['rows']))
        if f32_bad == 0:
            print('[nega-lower] FAIL: 取り違えを検出できない')
            sys.exit(1)
        print('[nega-lower] 演算の取り違えを検出。 ネガコン OK')
        sys.exit(0)
    if not os.path.isfile(LIFT):
        sys.exit('[x87_fn_diff] FAIL: %s が無い (lift_text.py を先に実行)' % LIFT)
    os.makedirs(WORK, exist_ok=True)
    img = pe_image()
    open(os.path.join(WORK, 'image.bin'), 'wb').write(img)
    rows = gen_special_rows(SEED, N_PER_TARGET) if special else gen_rows(SEED, N_PER_TARGET)
    scen = os.path.join(WORK, 'scen.txt')
    open(scen, 'w').write('\n'.join(r[1] for r in rows) + '\n')
    print('[scen] %d 関数 x %d = %d 行 (seed %d, OBJ 窓 %d B)' % (len(TARGETS), N_PER_TARGET, len(rows), SEED, OBJ_WIN))
    nat = os.path.join(WORK, 'native_x87')
    nat_out = os.path.join(WORK, 'native_out.txt')
    wasm_out = os.path.join(WORK, 'wasm_out.txt')
    mjs = os.path.join(WORK, 'wasm_x87.cjs')
    if '--nega-nan' in sys.argv:
        nat_p, wasm_p = parse(nat_out), parse(wasm_out)
        ok0, agg0 = compare(nat_p, wasm_p, rows, quiet=True)
        pick = next(i for i in range(len(rows)) if is_nan(int(nat_p[i]['st0'], 16)) and is_nan(int(wasm_p[i]['st0'], 16)))
        fn = rows[pick][0]['name']
        before = sum(agg0[fn][k].get('nan-num', 0) for k in ('st0', 'st0d', 'mem'))
        wasm_p[pick]['st0'] = '%08x' % f32(1.0)
        ok1, agg1 = compare(nat_p, wasm_p, rows, quiet=True)
        after = sum(agg1[fn][k].get('nan-num', 0) for k in ('st0', 'st0d', 'mem'))
        print('[nega-nan] 行 %d (%s) の wasm ST(0) の NaN を 3f800000 に置換: nan-num %d → %d、 突合の判定 ok=%s' % (
            pick, fn, before, after, ok1))
        if after != before + 1 or ok1:
            print('[nega-nan] FAIL: nan-num が 1 件増えず、判定が FAIL しなかった')
            sys.exit(1)
        print('[nega-nan] 判定 FAIL (本体の gate は exit 1) を検出。 ネガコン OK')
        sys.exit(0)
    if not nega:
        t_nat_build = run(['gcc', '-m32', '-O1', '-fno-pic', '-fno-pie', '-fno-stack-protector', '-fcf-protection=none',
                           '-fno-asynchronous-unwind-tables', '-ffreestanding', '-nostdlib', '-static', '-no-pie',
                           *PUSH64_FLAGS, '-o', nat, os.path.join(HERE, 'x87_fn_native.c')], 'native build')
        t_wasm_build = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', RT,
                            '-DLIFT_C="%s"' % LIFT, *PUSH64_FLAGS, os.path.join(HERE, 'x87_fn_glue.c'), os.path.join(RT, 'ott_cpu.c'),
                            '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                            '-sEXPORTED_FUNCTIONS=_ott_call32x,_ott_x87_st0,_ott_x87_st0d_hi,_ott_x87_st0d_lo,_ott_x87_depth',
                            '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                            '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                            '-sALLOW_MEMORY_GROWTH=0', '-o', mjs], 'wasm build (emcc)', timeout=900)
        load = os.getloadavg()[0]
        img_p = os.path.join(WORK, 'image.bin')
        t_nat = run_chunked(scen, nat_out, lambda cp, co: [nat, img_p, cp, co], 'native run', 600)
        t_wasm = run_chunked(scen, wasm_out, lambda cp, co: ['node', WASM_TIER, os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mjs, img_p, cp, co],
                             'wasm run (node)', 900)
        print('[build] native %.2f s, wasm emcc %.2f s; [run] native %.3f s, wasm(node) %.3f s; load1 before run %.2f' % (
            t_nat_build, t_wasm_build, t_nat, t_wasm, load))
        ok, _ = compare(parse(nat_out), parse(wasm_out), rows)
        if special:
            mismatch_classes(parse(nat_out), parse(wasm_out), rows)
        if not ok:
            print('[x87_fn_diff] FAIL: 構造の不一致または非自明性なし')
            sys.exit(1)
        print('[x87_fn_diff] PASS (構造: 行数・eax・x87 深さが一致。 float 語の差分は上の分布)')
        sys.exit(0)
    # ネガコン: 既存の出力を使う。 bit 一致の行を 1 つ選び、その wasm 側の ST(0) の最下位 bit を壊す
    nat_p, wasm_p = parse(nat_out), parse(wasm_out)
    ok, _ = compare(nat_p, wasm_p, rows, quiet=True)
    base = sum(1 for i in range(len(rows)) if nat_p[i] == wasm_p[i])
    pick = next((i for i in range(len(rows)) if nat_p[i] == wasm_p[i] and nat_p[i]['d'] != '0'), None)
    if pick is None:
        print('[nega] FAIL: 対象になる bit 一致の行が無い')
        sys.exit(1)
    st = int(wasm_p[pick]['st0'], 16) ^ 0x1
    wasm_p[pick]['st0'] = '%08x' % st
    after = sum(1 for i in range(len(rows)) if nat_p[i] == wasm_p[i])
    print('[nega] bit 一致 %d → %d (行 %d の ST(0) の最下位 bit を反転)' % (base, after, pick))
    if after != base - 1:
        print('[nega] FAIL: 件数が 1 減らなかった (判定器が効いていない)')
        sys.exit(1)
    print('[nega] 1 bit 壊した出力を検出。 ネガコン OK')
    sys.exit(0)


if __name__ == '__main__':
    main()
