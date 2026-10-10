#!/usr/bin/env python3
"""ablate.py — 修復 pass を 1 本ずつ外した時の bit-exact 件数 (負の対照 / ablation) を測る。
  Path B (stage-0 lowering): skip ∈ {flags, mov128, store, merge, callret, rdata, jumptable} のうち当該 snap-in で発火する pass
  Path A (RetDec 最終 IR + kh_passes): skip ∈ {flags, branches, f7, f2, mov128, storelow}
usage: ablate.py [names...]  → work/ablation.json"""
import json, os, subprocess, sys, re
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, 'lift', 'build.py')
names = sys.argv[1:] or ['matrix', 'gain', 'haas', 'clipper', 'gate', 'quickeq']

def run(name, path, skip, tag):
    cmd = ['python3', B, name, '--path', {'A': 'a', 'B': 's0'}[path], '--tag', tag] + (['--skip', skip] if skip else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    st = os.path.join(ROOT, 'work', name, tag, 'stat.json')
    if os.path.exists(st):
        s = json.load(open(st))
        return {'trials_ok': s.get('trials_ok'), 'trials': s.get('trials'), 'calls_ok': s.get('calls_ok'), 'calls': s.get('calls'), 'compare': s.get('compare', '')[:160]}
    return {'error': (r.stdout + r.stderr)[-300:]}

jobs = []
for n in names:
    base = os.path.join(ROOT, 'work', n, 's0', 'stat.json')
    if not os.path.exists(base):
        continue
    passes = json.loads(re.search(r'\{.*?\}', json.load(open(base))['passes']).group(0))
    fired = [k for k in passes if k in ('flags', 'mov128', 'merge', 'callret', 'jumptable')]
    if 'store128' in passes or 'storelow' in passes:
        fired.append('store')
    jobs.append((n, 'B', ','.join(fired), 'abl_B_all'))
    for p in fired:
        jobs.append((n, 'B', p, 'abl_B_' + p))
    jobs.append((n, 'B', 'rdata', 'abl_B_rdata'))
    for p in ('flags', 'branches', 'f7', 'f2', 'mov128', 'storelow'):
        if n in ('matrix', 'gain', 'haas', 'clipper'):
            jobs.append((n, 'A', p, 'abl_A_' + p))
    if n in ('matrix', 'gain', 'haas', 'clipper'):
        jobs.append((n, 'A', '', 'main'))
        jobs.append((n, 'A', 'flags,branches,f7,f2,mov128,storelow', 'abl_A_all'))
res = {}
with ThreadPoolExecutor(4) as ex:
    futs = {ex.submit(run, *j): j for j in jobs}
    for f, j in futs.items():
        res['%s|%s|%s' % (j[0], j[1], j[2] or 'none')] = f.result()
json.dump(res, open(os.path.join(ROOT, 'work', 'ablation.json'), 'w'), indent=1)
for k, v in sorted(res.items()):
    print(k, v.get('trials_ok'), '/', v.get('trials'), v.get('error', '')[:100])
