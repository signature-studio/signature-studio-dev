#!/usr/bin/env python3
"""再計算した閉包 (work/closure/block*.json) が PLUGIN_MATRIX.json の `lift` 欄と一致するか (7 本 × 6 項目)。 不一致なら exit 1。"""
import json, os, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
M = {p['name']: p for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']}
F = json.load(open(os.path.join(P, 'work', 'dynamics', 'facts.json')))
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bad = n = 0
for name, f in F.items():
    for mk, fk in keys:
        n += 1
        if M[name]['lift'][mk] != f[fk]:
            bad += 1
            print('MISMATCH', name, mk, M[name]['lift'][mk], f[fk])
print('matrix_check: %d/%d 項目一致' % (n - bad, n))
sys.exit(1 if bad else 0)
