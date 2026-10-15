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
OBJ_WIN = 0x540
N_PER_TARGET = 4000
N_PER_MIXED = 200
SEED = 2989

# va: 入口 VA。 gen: 引数と OBJ 窓の初期値の作り方 (ecx = OBJ)。 どちらも leaf で x87 を含み、import・未 lift の call が無い。
#   fn_10002ee0: thiscall (ecx = this、float a0、int a1 = 添字 0..15) ret 8。 [ecx+a1*4+0xb0..0x1f4] を読み書きし、ST(0) を残して返る。
#   fn_10005400: thiscall (ecx = this、float a0..a2) ret 0xc。 fcomp・fnstsw・fdivr を含み、[ecx+0x4fc..0x518] を更新する。 gen が積む a3・a4 (と a5 = 0) は本体が読まない余りの引数。
TARGETS = [
    {'va': 0x10002EE0, 'name': 'fn_10002ee0', 'gen': 'idx_store'},
    {'va': 0x10005400, 'name': 'fn_10005400', 'gen': 'state_update'},
    # #3715 (PLG-G2-31): lift 済みの残り leaf x87 関数 (call・間接分岐・未対応命令を含まず、x87 を含む)。
    # 引数の型は関数ごとに分からないので、a0 は float、a1..a5 は 0..15 の整数 (gen 'mixed')。 行数は N_PER_MIXED。
    # 除外の理由は REPORT_APPENDIX_3715.md §2 (構造不一致・ランナーの異常終了・入口にできない断片・非自明性なしの定数関数)。
    {'va': 0x10005D20, 'name': 'fn_10005d20', 'gen': 'mixed'},
    {'va': 0x1000B3A2, 'name': 'fn_1000b3a2', 'gen': 'mixed'},
    {'va': 0x10001290, 'name': 'fn_10001290', 'gen': 'mixed'},
]


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
            else:
                a = [f32(rng.uniform(-100, 100)) for _ in range(5)] + [0]
            line = '%08x %08x %s %s' % (t['va'], OBJ, ' '.join('%08x' % v for v in a), init.hex())
            rows.append((t, line, init))
    return rows


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
            if t['gen'] == 'idx_store':
                a = [sp, rng.randrange(16), 0, 0, 0, 0]
            else:
                a = [sp] + [rng.choice(SPECIAL_F32) if rng.random() < 0.5 else f32(rng.uniform(-100, 100))
                            for _ in range(2)] + [f32(rng.uniform(-100, 100)) for _ in range(2)] + [0]
            line = '%08x %08x %s %s' % (t['va'], OBJ, ' '.join('%08x' % v for v in a), init.hex())
            rows.append((t, line, init))
    return rows


def run(cmd, what, timeout=900):
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        sys.stderr.write(r.stdout[-1500:] + r.stderr[-1500:])
        sys.exit('[x87_fn_diff] FAIL: %s rc %d' % (what, r.returncode))
    return time.time() - t0


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


def compare(nat, act, scen, quiet=False):
    """行ごとに突合する。 戻り値 (ok, 集計 dict)。 ok は構造の判定 (行数・eax・x87 深さ・非自明性) のみ。 float 語は分布を集計する。"""
    if len(nat) != len(scen) or len(act) != len(scen):
        print('[compare] FAIL: 件数 native %d / wasm %d / 期待 %d' % (len(nat), len(act), len(scen)))
        return False, None
    ok = True
    agg = {}
    for t in TARGETS:
        agg[t['name']] = {'rows': 0, 'eq': 0, 'f32_eq': 0, 'eax_bad': 0, 'eax_nan': 0, 'd_bad': 0, 'effect': 0, 'nontrivial': 0,
                          'st0': {}, 'st0d': {}, 'mem': {}}
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
        if e['mem'] != init.hex():
            a['effect'] += 1
        if e['mem'] != init.hex() or (e['st0'] != '00000000' and e['st0'] != '80000000'):
            a['nontrivial'] += 1
        if e == w:
            a['eq'] += 1
        if e['st0'] == w['st0'] and e['mem'] == w['mem'] and e['eax'] == w['eax']:
            a['f32_eq'] += 1
        for key, x, y in (('st0', int(e['st0'], 16), int(w['st0'], 16)),
                          ('st0d', int(e['st0d'], 16), int(w['st0d'], 16))):
            c = dword_class(x, y) if key == 'st0d' else word_class(x, y)
            a[key][c] = a[key].get(c, 0) + 1
        for x, y in zip(words(e['mem']), words(w['mem'])):
            c = word_class(x, y)
            a['mem'][c] = a['mem'].get(c, 0) + 1
    for t in TARGETS:
        a = agg[t['name']]
        n = a['rows']
        mixed = sum(a[k].get('nan-num', 0) for k in ('st0', 'st0d', 'mem'))
        if a['eax_bad'] or a['d_bad'] or a['nontrivial'] == 0 or n == 0 or mixed:
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
    run(['node', os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mut_mjs, os.path.join(WORK, 'image.bin'), scen_path, mut_out],
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


def main():
    global WORK
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
                           '-o', nat, os.path.join(HERE, 'x87_fn_native.c')], 'native build')
        t_wasm_build = run(['emcc', '-O1', '-ffp-contract=off', '-fno-fast-math', '-w', '-I', RT,
                            '-DLIFT_C="%s"' % LIFT, os.path.join(HERE, 'x87_fn_glue.c'), os.path.join(RT, 'ott_cpu.c'),
                            '-sENVIRONMENT=node', '-sMODULARIZE=1', '-sEXPORT_NAME=createModule', '-sEXIT_RUNTIME=0',
                            '-sEXPORTED_FUNCTIONS=_ott_call32x,_ott_x87_st0,_ott_x87_st0d_hi,_ott_x87_st0d_lo,_ott_x87_depth',
                            '-sEXPORTED_RUNTIME_METHODS=HEAPU8',
                            '-sGLOBAL_BASE=%d' % 0x11000000, '-sSTACK_SIZE=2097152', '-sINITIAL_MEMORY=%d' % 0x14000000,
                            '-sALLOW_MEMORY_GROWTH=0', '-o', mjs], 'wasm build (emcc)', timeout=900)
        load = os.getloadavg()[0]
        t_nat = run([nat, os.path.join(WORK, 'image.bin'), scen, nat_out], 'native run', timeout=600)
        t_wasm = run(['node', os.path.join(HERE, 'x87_fn_entry_wasm.mjs'), mjs, os.path.join(WORK, 'image.bin'), scen, wasm_out],
                     'wasm run (node)', timeout=900)
        print('[build] native %.2f s, wasm emcc %.2f s; [run] native %.3f s, wasm(node) %.3f s; load1 before run %.2f' % (
            t_nat_build, t_wasm_build, t_nat, t_wasm, load))
        ok, _ = compare(parse(nat_out), parse(wasm_out), rows)
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
