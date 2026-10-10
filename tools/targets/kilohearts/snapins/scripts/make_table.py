#!/usr/bin/env python3
"""make_table.py — work/<name>/<tag>/stat.json から一覧表 (markdown) を生成。usage: make_table.py [tag=s0]"""
import json, os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from fnscan import extent
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tag = sys.argv[1] if len(sys.argv) > 1 else 's0'
cfg = json.load(open(os.path.join(ROOT, 'snapins.json')))
rows = []
ORDER = ['matrix', 'gain', 'haas', 'clipper', 'gate', 'quickeq', 'resonator', 'stereo', 'disperser']
for n in ORDER:
    sp = os.path.join(ROOT, 'work', n, tag, 'stat.json')
    if not os.path.exists(sp):
        continue
    s = json.load(open(sp))
    c = cfg[n]
    vas = sorted({int(v, 16) for v in c['lift'].values()})
    proc = int(c['lift']['proc'], 16)
    psz = extent(proc)[0] - proc
    tot = sum(extent(v)[0] - v for v in vas)
    passes = re.search(r'(\{.*?\})', s.get('passes', '{}'))
    rep = json.loads(passes.group(1)) if passes else {}
    shims = c.get('shims', {})
    unl = re.search(r"unlifted callees (\[.*?\])", s.get('passes', ''))
    unl = eval(unl.group(1)) if unl else []
    stubs = [u for u in unl if u not in shims]
    tol = '許容誤差' if c.get('tol') else 'bit-exact'
    rows.append(dict(name=c['title'], id=c['id'], proc='0x%x' % proc, psz=psz, nfn=len(vas), tot=tot, wasm=s['wasm_bytes'], und=len(s.get('undefined_imports', [])),
                     trials='%s/%s' % (s.get('trials_ok'), s.get('trials')), calls='%s/%s' % (s.get('calls_ok'), s.get('calls')),
                     rep=', '.join('%s×%d' % (k, v) for k, v in rep.items()), nshim=len(shims), nstub=len(stubs), stubs=stubs, tol=tol))
print('| snap-in (id) | process VA | process B | lift fn数 / 合計B | wasm B | undefined import | trial | call | 判定 | 必要な修復 (発火数) | shim / 未lift stub |')
print('|---|---|--:|--:|--:|--:|--:|--:|---|---|---|')
for r in rows:
    print('| %s (%s) | %s | %d | %d / %d | %d | %d | %s | %s | %s | %s | %d / %d |' % (r['name'], r['id'], r['proc'], r['psz'], r['nfn'], r['tot'], r['wasm'], r['und'], r['trials'], r['calls'], r['tol'], r['rep'], r['nshim'], r['nstub']))
json.dump(rows, open(os.path.join(ROOT, 'work', 'table_%s.json' % tag), 'w'), indent=1)
