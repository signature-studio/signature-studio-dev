#!/usr/bin/env python3
"""SR-4: sr4/pilots.tsv の各 pilot を liftlib (RetDec → 修復 pass → emcc → 実機 vs wasm 差分) で実行し結果 JSON を書く。
usage: sr4_pilots.py <pe> <workroot> <out.json> [--only name,..] [--raw-ll-override name=path ...]
結果欄: result (bit-exact|mismatch|error)・match/steps・p1_unsupported(= P1 が直せなかった comis 分岐数。警告扱い)・simd_unsupported_called(最終 IR に呼びが残る未対応 helper)・fp_alu_cov(sr4_cov.py)・rc。
exit code は常に 0 (判定は sr4_gate.py)。"""
import sys, os, re, json, subprocess, shutil, time
HERE = os.path.dirname(os.path.abspath(__file__))
SR3 = os.path.abspath(os.path.join(HERE, '..'))
REPO = os.path.abspath(os.path.join(SR3, '..', '..', '..'))
LIFTLIB = os.path.join(REPO, 'tools', 'liftlib')
pe, workroot, outp = sys.argv[1:4]
only = None
ovr = {}
a = sys.argv[4:]
while a:
    k = a.pop(0)
    if k == '--only': only = set(a.pop(0).split(','))
    elif k == '--raw-ll-override': nm, pth = a.pop(0).split('=', 1); ovr[nm] = pth
os.makedirs(workroot, exist_ok=True)
rows = [ln.rstrip('\n').split('\t') for ln in open(os.path.join(SR3, 'sr4', 'pilots.tsv'))][1:]
res = []
for name, b, e, expect, role in rows:
    if only and name not in only: continue
    wd = os.path.join(workroot, name)
    cfg = os.path.join(SR3, 'sr4', 'targets', name + '.json')
    if name in ovr:
        c = json.load(open(cfg)); c['raw_ll'] = ovr[name]; c['name'] = name
        cfg = os.path.join(workroot, name + '.override.json'); json.dump(c, open(cfg, 'w'))
    shutil.rmtree(wd, ignore_errors=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, '-m', 'liftlib', 'lift', cfg, '--workdir', wd], cwd=LIFTLIB, capture_output=True, text=True)
    dt = time.time() - t0
    out = r.stdout
    m = re.search(r'\[diff\] \S+: scenarios=(\d+) steps=(\d+) match=(\d+) mismatch=(\d+) native_crash=(\d+) wasm_trap=(\d+)', out)
    d = dict(name=name, begin=b, end=e, bytes=int(e, 16) - int(b, 16), expect=expect, role=role, rc=r.returncode)
    if m:
        sc, st, ma, mi, nc, wt = map(int, m.groups())
        d.update(scenarios=sc, steps=st, match=ma, mismatch=mi, native_crash=nc, wasm_trap=wt)
        d['result'] = 'bit-exact' if (mi == 0 and nc == 0 and wt == 0 and ma > 0) else 'mismatch'
    else:
        d['result'] = 'error'
        d['error'] = (r.stderr.strip().splitlines() or ['?'])[-1][:300]
    try:
        rep = json.load(open(os.path.join(wd, 'pipeline_report.json')))
        d['p1_unsupported'] = int(rep['stats'].get('p1', {}).get('unsupported', 0))
        d['p1_sites'] = int(rep['stats'].get('p1', {}).get('sites', 0))
        un = rep['stats'].get('simd', {}).get('unsupported', [])
        fx = open(os.path.join(wd, name + '_fixed.ll')).read()
        d['simd_unsupported_declared'] = un
        d['simd_unsupported_called'] = [u for u in un if re.search(r'call [^\n]*@%s\(' % re.escape(u), fx)]
    except Exception:
        d['p1_unsupported'] = None
    raw = os.path.join(wd, name + '.drc.ll') if name not in ovr else ovr[name]
    try:
        cov = json.loads(subprocess.run([sys.executable, os.path.join(HERE, 'sr4_cov.py'), pe, raw, b, e], capture_output=True, text=True, check=True).stdout)
        d.update({k: cov[k] for k in ('machine_insn', 'fp_alu', 'fp_alu_in_ir', 'fp_alu_cov')})
    except Exception as ex:
        d['fp_alu_cov'] = None
    res.append(d)
    print('%-18s %-9s match=%s/%s p1_unsupported=%s fp_alu_cov=%s (%.1fs)' % (name, d['result'], d.get('match'), d.get('steps'), d.get('p1_unsupported'), d.get('fp_alu_cov'), dt), flush=True)
json.dump(res, open(outp, 'w'), indent=1)
