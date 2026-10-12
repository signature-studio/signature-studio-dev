#!/usr/bin/env python3
"""make_table.py — work/<name>/<tag>/stat.json から一覧表 (markdown) を生成。usage: make_table.py [tag=s0]"""
import json, os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from fnscan import extent
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tag = sys.argv[1] if len(sys.argv) > 1 else 's0'


def judge(s):
    """判定列を stat.json の実測から決める (CAB-273)。

    数え方の定義 (規則 36):
      - PASS = trials_ok == trials かつ calls_ok == calls (compare.mjs の strict 判定の集計)。
      - legacy tol 統計 = compare 文字列の `tol(1.6*2^-12 gate): approx A, maxrel R, maxabs B, exceed E`。
        tol gate 撤去後の compare.mjs はこの文字列を出力しない (常に bit-exact)。
        撤去前に取得した snapshot を食わせたとき approx>0 / exceed>0 を bit-exact と誤表示しないための経路。
    """
    if s.get('trials_ok') is None or s.get('calls_ok') is None:
        return '(no compare)'
    if s['trials_ok'] != s['trials'] or s['calls_ok'] != s['calls']:
        return 'FAIL'
    m = re.search(r'approx (\d+) / diff-words.*?exceed (\d+)', s.get('compare', ''))
    if m and (int(m.group(1)) or int(m.group(2))):
        return '許容誤差(legacy)'
    return 'bit-exact'

cfg = json.load(open(os.path.join(ROOT, 'snapins.json')))
rows = []
ORDER = ['matrix', 'gain', 'haas', 'clipper', 'gate', 'quickeq', 'resonator', 'stereo', 'disperser', 'formant', 'phaser', 'delay', 'limiter', 'khbase']
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
    # 判定列 = 実測から決める (CAB-273)。cfg['tol'] の有無は見ない。
    #   1) trials/calls が全て PASS → 完全一致候補
    #   2) compare 文字列に legacy tol 統計 (approx/exceed) が残る snapshot では
    #      approx>0 / exceed>0 を許容誤差として表示する (bit-exact と誤表示しない)
    tol = judge(s)
    rows.append(dict(name=c['title'], id=c['id'], proc='0x%x' % proc, psz=psz, nfn=len(vas), tot=tot, wasm=s['wasm_bytes'], und=len(s.get('undefined_imports', [])),
                     trials='%s/%s' % (s.get('trials_ok'), s.get('trials')), calls='%s/%s' % (s.get('calls_ok'), s.get('calls')),
                     rep=', '.join('%s×%d' % (k, v) for k, v in rep.items()), nshim=len(shims), nstub=len(stubs), stubs=stubs, tol=tol))
print('| snap-in (id) | process VA | process B | lift fn数 / 合計B | wasm B | undefined import | trial | call | 判定 | 必要な修復 (発火数) | shim / 未lift stub |')
print('|---|---|--:|--:|--:|--:|--:|--:|---|---|---|')
for r in rows:
    print('| %s (%s) | %s | %d | %d / %d | %d | %d | %s | %s | %s | %s | %d / %d |' % (r['name'], r['id'], r['proc'], r['psz'], r['nfn'], r['tot'], r['wasm'], r['und'], r['trials'], r['calls'], r['tol'], r['rep'], r['nshim'], r['nstub']))
json.dump(rows, open(os.path.join(ROOT, 'work', 'table_%s.json' % tag), 'w'), indent=1)
