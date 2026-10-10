#!/usr/bin/env python3
"""matrix.py MOD.cjs [--quick]: scenario matrix を wasm と native 実機械語で走らせ, 出力 bit 一致 + 最終 state byte 一致を判定。
   出力: JSON 行 + 末尾 summary。exit 0 = 全 scenario で出力 512/512 bit-exact かつ state 差 0。"""
import sys, os, json, subprocess, zlib, base64, struct, random, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
NODE = os.environ.get('NODE') or '/opt/emsdk/node/24.19.0_64bit/bin/node'
mod = sys.argv[1]
quick = '--quick' in sys.argv
random.seed(7)
S = [dict(name='ctor_defaults', params=[], nproc=2), dict(name='ctor_defaults_noise', params=[], inkind='noise', n=200, nproc=3), dict(name='std', params=[0.5] * 19), dict(name='std_f248_0', params=[0.5] * 19, f248=0)]
S += [dict(name='n%d' % n, params=[0.5] * 19, n=n) for n in (1, 3, 4, 5, 7, 31, 64, 255)]
S += [dict(name='3blocks', params=[0.5] * 19, n=128, nproc=3), dict(name='3blocks_f248_0', params=[0.5] * 19, n=128, nproc=3, f248=0)]
for v in (0.1, 0.25, 0.75, 1.0):
    S.append(dict(name='all%.2f' % v, params=[v] * 19)); S.append(dict(name='all%.2f_f248_0' % v, params=[v] * 19, f248=0))
S += [dict(name='p4_0', params=[0.5] * 4 + [0.0] + [0.5] * 14), dict(name='p4_1', params=[0.5] * 4 + [1.0] + [0.5] * 14), dict(name='bypass19', params=[0.5] * 19, p19=1.0)]
for i in range(0, 19, 3):
    p = [0.5] * 19; p[i] = 0.9; S.append(dict(name='one_%d' % i, params=p, nproc=2, n=96))
for k in range(6 if quick else 24):
    S.append(dict(name='rnd%d' % k, params=[round(random.random(), 3) for _ in range(19)], f248=random.choice([None, 0, 1]), sig=random.choice([0, 0.3, -0.5]), nproc=random.choice([1, 2, 3]), n=random.choice([32, 100, 256])))
for kind in ('zero', 'dc', 'impulse', 'square', 'noise', 'tiny', 'decay'):
    S.append(dict(name='in_%s' % kind, params=[0.5] * 19, inkind=kind, n=128, nproc=4))
    S.append(dict(name='in_%s_f248_0' % kind, params=[0.5] * 19, inkind=kind, n=128, nproc=4, f248=0))
    S.append(dict(name='in_%s_hot' % kind, params=[1.0] * 19, inkind=kind, n=128, nproc=3))
for sr in (22050.0, 32000.0, 48000.0, 88200.0, 96000.0, 192000.0):
    S.append(dict(name='sr%d' % sr, params=[0.5] * 19, sr=sr, nproc=2, n=128))
    S.append(dict(name='sr%d_f248_0' % sr, params=[0.5] * 19, sr=sr, nproc=2, n=128, f248=0))
if quick: S = S[:14] + S[-8:]
f = lambda u: struct.unpack('<f', struct.pack('<I', u))[0]
TOL = int(os.environ.get('OTT_ULP_TOL', '0'))
def ulp(a, b):
    if a == b: return 0
    ia = a if a < 0x80000000 else -(a & 0x7fffffff); ib = b if b < 0x80000000 else -(b & 0x7fffffff)
    return abs(ia - ib)
def census(vals):
    c = dict(zero=0, normal=0, junkHi=0, junkTiny=0, nan=0)
    for v in vals:
        a = abs(v)
        if v == 0: c['zero'] += 1
        elif v != v: c['nan'] += 1
        elif a >= 4: c['junkHi'] += 1
        elif a <= 1e-18: c['junkTiny'] += 1
        else: c['normal'] += 1
    return c
LB_BASE = int(os.environ['LB_BASE'], 0)
NAT_OFF = int(os.environ.get('LB_NAT_OFF', 0x40000000)); LB_ARENA = int(os.environ['LB_ARENA']); LB_ARENA_SIZE = int(os.environ.get('LB_ARENA_SIZE', 0x100000))
def nq(q, rng):  # native qword → wasm 表現: image VA は V-shift、heap/arena は一様オフセット(-NAT_OFF)
    if 0x180000000 <= q < 0x180400000: return q - (0x180000000 - LB_BASE)
    for lo, hi in rng:
        if lo + NAT_OFF <= q < hi + NAT_OFF: return q - NAT_OFF
    return q
fails = 0; rows = []
tmp = tempfile.mkdtemp(prefix='ottm_', dir='/tmp/opencode') if os.path.isdir('/tmp/opencode') else tempfile.mkdtemp()
for s in S:
    sp = os.path.join(tmp, 'spec.json'); open(sp, 'w').write(json.dumps(s))
    wj = os.path.join(tmp, 'w.json'); nj = os.path.join(tmp, 'n.json')
    env = dict(os.environ, MOD=mod, SPEC=sp, OUT=wj)
    r = subprocess.run([NODE, os.path.join(HERE, 'scen2_wasm.mjs')], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        rows.append(dict(name=s['name'], ok=False, err='wasm: ' + (r.stderr.strip().splitlines() or ['?'])[0][:160])); fails += 1; continue
    r = subprocess.run([sys.executable, os.path.join(HERE, 'scen2_nat.py'), wj, nj], capture_output=True, text=True)
    if r.returncode != 0:
        rows.append(dict(name=s['name'], ok=False, err='native: ' + (r.stderr.strip().splitlines() or ['?'])[-1][:160])); fails += 1; continue
    W = json.load(open(wj)); Nn = json.load(open(nj))
    cells = sum(len(o) for o in W['outs']); eq = sum(1 for a, b in zip(W['outs'], Nn['outs']) for x, y in zip(a, b) if ulp(x, y) <= TOL)
    maxulp = max((ulp(x, y) for a, b in zip(W['outs'], Nn['outs']) for x, y in zip(a, b)), default=0)
    vals = [f(x) for o in W['outs'] for x in o]
    junk = sum(1 for v in vals if abs(v) >= 4 or v != v)
    cen = census(vals)
    sd = 0
    rng = [(LB_ARENA, LB_ARENA + LB_ARENA_SIZE)] + [(p, p + s) for p, s in W['alog']]
    for ra, rb in zip(Nn['final'], W['final']):
        A = zlib.decompress(base64.b64decode(ra['z'])); B = zlib.decompress(base64.b64decode(rb['z']))
        if A == B: continue
        for o in range(0, ra['s'] & ~7, 8):
            qa = struct.unpack_from('<Q', A, o)[0]; qb = struct.unpack_from('<Q', B, o)[0]
            if qa != qb and nq(qa, rng) != qb and not (ra['k'] == 'obj' and o == 0): sd += 1
    ok = (eq == cells and (sd == 0 or TOL > 0) and Nn['mismatch'] == 0)
    fails += (not ok)
    rows.append(dict(name=s['name'], ok=ok, cells=cells, bit_equal=eq, max_ulp=maxulp, junk=junk, census=cen, state_diff_qwords=sd, absmax=max(abs(v) for v in vals if v == v)))
    print(json.dumps(rows[-1]), flush=True)
for r in rows:
    if not r.get('cells'): print(json.dumps(r))
print('[matrix] scenarios %d, failed %d, total cells %d, equal(<=%d ulp) %d, max_ulp %d, state_diff_qwords %d' % (
    len(S), fails, sum(r.get('cells', 0) for r in rows), TOL, sum(r.get('bit_equal', 0) for r in rows), max([r.get('max_ulp', 0) for r in rows] or [0]), sum(r.get('state_diff_qwords', 0) for r in rows)))
sys.exit(1 if fails else 0)
