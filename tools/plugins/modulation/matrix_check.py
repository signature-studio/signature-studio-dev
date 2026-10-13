#!/usr/bin/env python3
"""再計算した閉包 (facts.json) と lift 結果 (status CSV) が PLUGIN_MATRIX.json の `lift` 欄と一致するか。
  - 閉包 6 項目 (関数数・バイト・frontier 関数・frontier バイト・vcall・ptr) × プラグイン
  - matrix に `lift.batch` がある プラグイン は lift_rc / emcc_c_rc / f80_funcs / unimpl_helpers も status と比較
不一致が 1 件でもあれば exit 1。 プラグイン数が --expect-n と違う / 入力が読めない場合は exit 2。
usage: matrix_check.py [--facts work/modulation/facts.json] [--status work/modulation/status8.csv] [--matrix PLUGIN_MATRIX.json] [--expect-n 8]
"""
import argparse, csv, json, os, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ap = argparse.ArgumentParser()
ap.add_argument('--facts', default=os.path.join(P, 'work', 'modulation', 'facts.json'))
ap.add_argument('--status', default=os.path.join(P, 'work', 'modulation', 'status8.csv'))
ap.add_argument('--matrix', default=os.path.join(P, 'PLUGIN_MATRIX.json'))
ap.add_argument('--expect-n', type=int, default=8)
a = ap.parse_args()
try:
    M = {p['name']: p for p in json.load(open(a.matrix))['plugins']}
    F = json.load(open(a.facts))
    S = {r['block']: r for r in csv.DictReader(open(a.status))}
except (OSError, ValueError, KeyError) as e:
    print('matrix_check: 入力が読めない:', e, file=sys.stderr)
    sys.exit(2)
if len(F) != a.expect_n:
    print('matrix_check: facts のプラグイン数 %d != %d' % (len(F), a.expect_n), file=sys.stderr)
    sys.exit(2)
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bkeys = [('lift_rc', 'lift_rc'), ('emcc_c_rc', 'emcc_c_rc'), ('f80_funcs', 'f80_funcs'), ('unimpl_helpers', 'declares_unimpl')]
bad = n = nb = 0
for name, f in F.items():
    if name not in M:
        print('matrix_check: matrix に無いプラグイン', name, file=sys.stderr)
        sys.exit(2)
    for mk, fk in keys:
        n += 1
        if M[name]['lift'][mk] != f[fk]:
            bad += 1
            print('MISMATCH', name, mk, M[name]['lift'][mk], f[fk])
    mb = M[name]['lift'].get('batch')
    if mb:
        row = S.get(str(f['block']))
        for mk, sk in bkeys:
            n += 1
            nb += 1
            if row is None or str(mb[mk]) != row[sk]:
                bad += 1
                print('MISMATCH', name, 'batch.' + mk, mb[mk], None if row is None else row[sk])
print('matrix_check: %d/%d 項目一致 (うち batch 項目 %d)' % (n - bad, n, nb))
sys.exit(1 if bad else 0)
