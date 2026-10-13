#!/usr/bin/env python3
"""再計算した閉包 (work/hostx/facts.json) が PLUGIN_MATRIX.json の `lift` 欄と一致するか (Delphi 殻 9 本 × 6 項目)。 不一致なら exit 1。 引数 1 = facts.json のパス (省略時 work/hostx/facts.json; ネガティブコントロール用)。
ZGE 殻は matrix に lift 欄が無い (None) ため、matrix 側が無い本は「比較対象外」として数える。"""
import json, os, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
M = {}
for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']:
    for m in p['win']['modules']:
        M[m['block']] = p
F = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(P, 'work', 'hostx', 'facts.json')))['plugins']
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bad = n = skipped = 0
for name, f in F.items():
    L = M[f['block']].get('lift')
    if not L:
        skipped += 1
        print('SKIP', name, 'matrix に lift 欄なし (block %d)' % f['block'])
        continue
    for mk, fk in keys:
        n += 1
        if L[mk] != f[fk]:
            bad += 1
            print('MISMATCH', name, mk, L[mk], f[fk])
print('matrix_check: %d/%d 項目一致 (比較対象外 %d 本)' % (n - bad, n, skipped))
sys.exit(1 if bad else 0)
