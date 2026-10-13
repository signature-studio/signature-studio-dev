#!/usr/bin/env python3
"""再計算した閉包 (facts.json) が PLUGIN_MATRIX.json と一致するか。 28 本 × 6 項目 + (block / Tier) の突合。 不一致が 1 つでもあれば exit 1。
  usage: matrix_check.py [facts.json] [PLUGIN_MATRIX.json]
  - 閉包 6 項目: closure_funcs / closure_bytes / frontier 関数 / frontier バイト / vcall / ptr  (PLUGIN_MATRIX.json の `lift` 欄)
  - targets.py の block が、同名 plugin の win モジュールに存在し、Tier が #205 本文の表記と一致すること
  - facts.json が targets.py の 28 本と過不足なく一致すること (欠けた本を黙って数えないため)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from targets import TARGETS  # noqa: E402
P = os.path.join(HERE, '..')
fpath = sys.argv[1] if len(sys.argv) > 1 else os.path.join(P, 'work', 'ctlvfx', 'facts.json')
mpath = sys.argv[2] if len(sys.argv) > 2 else os.path.join(P, 'PLUGIN_MATRIX.json')
M = {p['name']: p for p in json.load(open(mpath))['plugins']}
F = json.load(open(fpath))
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bad = n = 0
want = [t[0] for t in TARGETS]
n += 1
if sorted(F) != sorted(want):
    bad += 1
    print('MISMATCH facts の plugin 集合が targets.py と違う: 欠け=%s 余り=%s' % (sorted(set(want) - set(F)), sorted(set(F) - set(want))))
for name, blk, tier, _eng in TARGETS:
    m = M.get(name)
    n += 2
    if m is None:
        bad += 2
        print('MISMATCH', name, 'PLUGIN_MATRIX.json に無い')
        continue
    blocks = [x['block'] for x in m['win']['modules']]
    for what, ok, got in (('block', blk in blocks, blocks), ('tier', tier == m['tier'], m['tier'])):
        if not ok:
            bad += 1
            print('MISMATCH', name, what, '期待', blk if what == 'block' else tier, '実際', got)
    f = F.get(name)
    for mk, fk in keys:
        n += 1
        if f is None or f['block'] != blk or M[name]['lift'][mk] != f[fk]:
            bad += 1
            print('MISMATCH', name, mk, M[name]['lift'][mk], None if f is None else f[fk])
print('matrix_check: %d/%d 項目一致' % (n - bad, n))
sys.exit(1 if bad else 0)
