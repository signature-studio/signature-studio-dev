#!/usr/bin/env python3
"""fn3_diff.py FN_VA [--n N] [--seed S] [--fma 0|1] [--wide]
関数単位の 3 者比較: native 実機械語 / RetDec route wasm (icall/work/route) / x64c wasm (ott/work/lift)。
入力 = xmm0 に乱数 double (+ 任意で xmm1)、rcx..r9 = 0。出力 = xmm0 raw 64bit と rax。
1 関数ごとに別プロセスで実行するため native が SIGSEGV しても他関数に影響しない。
前提: bash tools/ott/ott_e2e.sh と bash tools/icall/icall_e2e.sh が実行済み (work/ が存在)。"""
import sys, os, json, struct, random, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(T, 'ott', 'native'))
ROUTE = os.path.join(T, 'icall', 'work', 'route', 'ott_route.cjs')
X64C = os.path.join(T, 'ott', 'work', 'lift', 'ottl.cjs')
FMA_FLAG = 0x18026c50c
NEG = '--neg' in sys.argv    # 入力の符号を半数反転 (tan の符号復元 = vmovapd [rsp+0x40] の再読込経路を踏む)
KERNEL = '--kernel' in sys.argv  # 入力 = xmm0..3 + r8 (1801aa1a0 の呼出し規約: x, corr, ?, n, parity)


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def gen_inputs(n, seed, wide):
    random.seed(seed)
    f = lambda d: struct.unpack('<Q', struct.pack('<d', d))[0]
    out = []
    for _ in range(n):
        if wide:
            k = random.random()
            x = random.uniform(-4, 4) if k < .4 else random.uniform(0, 60000) if k < .8 else random.uniform(-1e-3, 1e-3)
        else:
            x = random.choice([random.uniform(0.01, 4), random.uniform(0.0001, 100), random.uniform(1, 30000)])
        if NEG and random.random() < .5:
            x = -x
        if KERNEL:
            n = random.choice([0.0, 1.0, 2.0, 3.0])
            out.append((f(random.uniform(-0.8, 0.8)), f(random.uniform(-1e-16, 1e-16)), f(random.uniform(-1e-16, 1e-16)), f(n), random.getrandbits(1)))
        else:
            out.append((f(x), f(random.uniform(0.01, 4)), 0, 0, 0))
    return out


def run_wasm(mod, va, cases, fma=None):
    js = tempfile.NamedTemporaryFile('w', suffix='.mjs', delete=False, dir=os.environ.get('TMPDIR'))
    js.write("import { load } from '%s/ott/diff/api.mjs';\n"
             "const api = await load(process.env.MOD);\n"
             "if (process.env.FMA) api.mod.HEAPU32[(0x30000000 + 0x26c50c) >> 2] = Number(process.env.FMA);\n"
             "const cs = JSON.parse(process.env.CASES), va = Number(process.env.VA), out = [];\n"
             "for (const [a, b, c, d, r] of cs) { try { const rax = api.run(va, [0,0,BigInt(r),0], [BigInt(a), BigInt(b), BigInt(c), BigInt(d)]);\n"
             "  out.push([rax.toString(), BigInt.asUintN(64, api.mod._ott_xmm0()).toString()]); } catch (e) { out.push(['ERR:' + String(e).slice(0, 80)]); break; } }\n"
             "console.log(JSON.stringify(out));\n" % T)
    js.close()
    env = dict(os.environ, MOD=mod, VA=str(va), **({'FMA': str(fma)} if fma is not None else {}), CASES=json.dumps([[str(v) for v in c] for c in cases]))
    r = subprocess.run([os.environ.get('NODE') or 'node', js.name], env=env, capture_output=True, text=True)
    os.unlink(js.name)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return [['ERR:run-failed ' + r.stderr[-120:].replace('\n', ' ')]]


def run_native(va, cases, fma):
    import ottnat as N
    N.load()
    if fma is not None:
        N.wr(FMA_FLAG, struct.pack('<I', fma))
    res = []
    for a, b, c, d, r in cases:
        rax, x0 = N.call(va, (0, 0, r, 0), (a, b, c, d))
        res.append([str(rax), str(x0)])
    return res


def ulp(a, b):
    fa, fb = (struct.unpack('<d', struct.pack('<Q', v))[0] for v in (a, b))
    if fa == fb or (fa != fa and fb != fb):
        return 0
    key = lambda v: v if v < 1 << 63 else -(v & ((1 << 63) - 1))
    return abs(key(a) - key(b))


def main():
    va = int(sys.argv[1], 16)
    n, seed, wide = arg('--n', 120), arg('--seed', 3), '--wide' in sys.argv
    fma = arg('--fma', -1)
    fma = None if fma < 0 else fma
    cases = gen_inputs(n, seed, wide)
    if '--native-child' in sys.argv:
        print(json.dumps(run_native(va, cases, fma)))
        return
    ch = subprocess.run([sys.executable, __file__] + sys.argv[1:] + ['--native-child'], capture_output=True, text=True)
    try:
        nat = json.loads(ch.stdout.strip().splitlines()[-1])
    except Exception:
        nat = None
    w = {'route': run_wasm(ROUTE, va, cases, fma), 'x64c': run_wasm(X64C, va, cases, fma)}
    print('fn %x n=%d seed=%d fma=%s wide=%s' % (va, n, seed, fma, wide))
    if nat is None:
        print('  native: FAIL (SIGSEGV 等; 単独呼出し不能 = 隠れ入力あり)', ch.stderr.strip().splitlines()[0][:100] if ch.stderr.strip() else '')
        return
    for name, r in w.items():
        if r and r[0][0].startswith('ERR'):
            print('  %-5s: %s' % (name, r[0][0]))
            continue
        eq = sum(1 for x, y in zip(nat, r) if int(x[1]) == int(y[1]))
        ulps = [ulp(int(x[1]), int(y[1])) for x, y in zip(nat, r)]
        raxeq = sum(1 for x, y in zip(nat, r) if x[0] == y[0])
        first = next(((hex(cases[i][0]), x[1], y[1]) for i, (x, y) in enumerate(zip(nat, r)) if int(x[1]) != int(y[1])), None)
        print('  %-5s: xmm0 bit-equal %d/%d, rax equal %d/%d, max_ulp %d, first diff (x0, nat, wasm) %s' % (name, eq, n, raxeq, n, max(ulps), first))
        if '--dump' in sys.argv:
            d = lambda v: struct.unpack('<d', struct.pack('<Q', v))[0]
            bad = sorted(d(c[0]) for c, x, y in zip(cases, nat, r) if int(x[1]) != int(y[1]))
            print('    differing x0: %d, min %s max %s' % (len(bad), bad[0] if bad else None, bad[-1] if bad else None))
            print('    ', bad[:12])


main()
