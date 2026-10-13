#!/usr/bin/env python3
"""icall_hits.py survey.json [--expect KIND:KEY=OK[/MISS] ...] [--sidecar] [--units] : survey_units.mjs の icall 欄 (#494) を集計して検収する.
  KIND = site (元バイナリの call 命令 VA, 'ext' = 外部 TU からの m11_icall) | target (解決先 VA). OK / MISS = unit 全部を足した hit 数 (MISS 省略時は ok だけ検査).
  例: icall_hits.py work/after.json --expect site:0x5c0437=4/0 target:0x5c0e70=4/0   (期待と違えば exit 1)
  --sidecar : <survey>.icall.json (boot 段階 + 全体累計) も表示 / --units : KEY ごとに hit した unit 番号を出す"""
import argparse, json, sys, collections
ap = argparse.ArgumentParser()
ap.add_argument('survey'); ap.add_argument('--expect', nargs='*', default=[]); ap.add_argument('--sidecar', action='store_true'); ap.add_argument('--units', action='store_true')
a = ap.parse_args()
per = json.load(open(a.survey))
KINDS = {'site': 'sites', 'target': 'targets'}
tot = {k: collections.defaultdict(lambda: [0, 0]) for k in KINDS.values()}
units = {k: collections.defaultdict(list) for k in KINDS.values()}
for r in per:
    for kind, m in r.get('icall', {}).items():
        for key, (ok, miss) in m.items(): tot[kind][key][0] += ok; tot[kind][key][1] += miss; units[kind][key].append(r['unit'])
def order(k): return (k != 'ext', int(k, 16) if k != 'ext' else 0)
for kind in ('sites', 'targets'):
    print('%s (unit 合計 [ok, miss], %d 種):' % (kind, len(tot[kind])))
    for k in sorted(tot[kind], key=order): print('  %-9s ok=%-6d miss=%-4d units=%d%s' % (k, tot[kind][k][0], tot[kind][k][1], len(units[kind][k]), ' ' + str(units[kind][k]) if a.units else ''))
if a.sidecar:
    sc = json.load(open(a.survey.rsplit('.json', 1)[0] + '.icall.json'))
    print('sidecar boot: %s\nsidecar total: %s\nsidecar drop: %d' % (json.dumps(sc['boot']), json.dumps(sc['total']), sc['drop']))
bad = 0
for e in a.expect:
    lhs, rhs = e.split('=', 1); kind, key = lhs.split(':', 1)
    want = [int(x) for x in rhs.split('/')]
    key = key if key == 'ext' else '0x%x' % int(key, 16)
    got = tot[KINDS[kind]].get(key, [0, 0]) if key in tot[KINDS[kind]] else [0, 0]
    okk = got[0] == want[0] and (len(want) < 2 or got[1] == want[1])
    bad += not okk
    print('%s %s: got ok=%d miss=%d, want ok=%d%s' % ('PASS' if okk else 'FAIL', lhs, got[0], got[1], want[0], '' if len(want) < 2 else ' miss=%d' % want[1]))
sys.exit(1 if bad else 0)
