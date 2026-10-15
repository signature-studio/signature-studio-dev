#!/usr/bin/env python3
"""fn_diff.py MOD.cjs [--max N] : 数値関数単位の native(実機械語) vs route-wasm 差分.
対象 = ott_route.cjs の dispatch 表にある関数のうち、メモリ参照が rip 相対 / rsp 相対のみの「数値 leaf 風」関数 (capstone で選別).
入力 = xmm0/xmm1 に乱数 double (広域 + 小値 + 特殊値)、rcx..r9 = 0。出力 = rax と xmm0 の raw 64bit を bit 比較。"""
import sys, os, json, struct, random, subprocess, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'ott', 'native'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import capstone
from capstone import x86
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from paths import PLUGINS_DIR
import audit_icall as A
DLL = os.path.join(PLUGINS_DIR, 'ott', 'binaries', 'OTT_vst2_win64.dll')
mod = sys.argv[1]
F = os.path.join(os.path.dirname(mod), 'F.txt')
img = A.Image(DLL)
rg = {}
for t in open(F).read().replace(',', '\n').split():
    lo, hi = t.split('-'); rg[int(lo, 16)] = int(hi, 16)
dis = A.Disasm(img)
cand = []
for f, e in sorted(rg.items()):
    sites = {}
    ins = dis.scan_function(f, e, sites)
    ok = True; nsse = 0
    for i in ins.values():
        if i.mnemonic in ('call', 'syscall', 'int3') and False: ok = False
        for op in i.operands:
            if op.type == x86.X86_OP_MEM:
                b = i.reg_name(op.mem.base) if op.mem.base else None
                if b not in ('rip', 'rsp') and i.mnemonic != 'lea':
                    ok = False
        if i.mnemonic.endswith(('sd', 'ss')) or i.mnemonic.startswith(('cvt', 'sqrt')): nsse += 1
        if x86.X86_GRP_CALL in i.groups and i.operands and i.operands[0].type != x86.X86_OP_IMM: ok = False
    if ok and nsse >= 3: cand.append(f)
print('candidates', len(cand), [hex(c) for c in cand][:40], file=sys.stderr)
mx = int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else 100000
cand = cand[:mx]
random.seed(3)
def rd():
    if os.environ.get('SAFE', '1') == '1':
        return random.choice([random.uniform(0.01, 4), random.uniform(0.01, 4), random.uniform(0.0001, 100), random.uniform(1, 30000)])
    k = random.random()
    if k < 0.15: return random.choice([0.0, 1.0, -1.0, 0.5, 2.0, 10.0, 1e-300, 1e300, float('inf'), float('nan'), 3.141592653589793])
    if k < 0.5: return random.uniform(-4, 4)
    if k < 0.8: return random.uniform(0, 60000)
    return random.uniform(-1e-3, 1e-3)
cases = [(random.getrandbits(1) and 0, struct.unpack('<Q', struct.pack('<d', rd()))[0], struct.unpack('<Q', struct.pack('<d', rd()))[0]) for _ in range(120)]
# wasm side
js = tempfile.NamedTemporaryFile('w', suffix='.mjs', delete=False, dir='/tmp/opencode' if os.path.isdir('/tmp/opencode') else None)
js.write('''import { load } from '%s/ott/diff/api.mjs';
const api = await load(process.env.MOD); const mod = api.mod;
const cand = JSON.parse(process.env.CAND), cases = JSON.parse(process.env.CASES);
const out = {};
for (const va of cand) { out[va] = [];
  for (const [g, x0, x1] of cases) { try { const rax = api.run(va, [0,0,0,0], [BigInt(x0), BigInt(x1), 0n, 0n]); out[va].push([rax.toString(), mod._ott_xmm0 ? BigInt.asUintN(64, mod._ott_xmm0()).toString() : '0']); } catch (e) { out[va].push(['ERR:' + String(e).slice(0, 60)]); break; } } }
console.log(JSON.stringify(out));''' % os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
js.close()
NODE = os.environ.get('NODE') or '/opt/emsdk/node/24.19.0_64bit/bin/node'
env = dict(os.environ, MOD=mod, CAND=json.dumps([c - 0x180000000 + 0x30000000 + 0x150000000 - 0x150000000 for c in cand]), CASES=json.dumps([[c[0], str(c[1]), str(c[2])] for c in cases]))
# api.run は 0x180000000+rva 形式の va を取る: そのまま渡す
env['CAND'] = json.dumps(cand)
r = subprocess.run([NODE, js.name], env=env, capture_output=True, text=True)
try:
    W = json.loads(r.stdout.strip().splitlines()[-1])
except Exception:
    print('wasm run failed:', r.stderr[-400:]); sys.exit(1)
import ottnat as N
N.load()
rows = []
for va in cand:
    w = W[str(va)]
    if w and w[0][0].startswith('ERR'):
        rows.append((va, 'wasm-trap', w[0][0])); continue
    eq = 0; n = 0; first = None
    for (g, x0, x1), wr in zip(cases, w):
        try:
            rax, x0r = N.call(va, (0, 0, 0, 0), (x0, x1, 0, 0))
        except Exception as e:
            rows.append((va, 'native-fail', str(e))); break
        n += 1
        if len(wr) < 2:
            first = first or ('wasm', wr[0]); continue
        if int(wr[1]) == x0r: eq += 1
        elif first is None: first = (hex(x0), hex(x1), hex(x0r), hex(int(wr[1])))
    else:
        rows.append((va, 'xmm0-bit-equal %d/%d' % (eq, n), first))
for r_ in rows: print('%x' % r_[0], r_[1], r_[2] if r_[2] else '')
