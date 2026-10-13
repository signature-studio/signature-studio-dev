#!/usr/bin/env python3
"""再計算した値が PLUGIN_MATRIX.json の記録と一致するか。 不一致が 1 つでもあれば exit 1。
  1. 閉包 6 項目 (closure_funcs / closure_bytes / frontier_funcs / frontier_bytes / vcall / ptr) : facts.json の shells × PLUGIN_MATRIX `lift`
  2. batch 4 項目 (lift_rc / emcc_c_rc / f80_funcs / unimpl_helpers) : status.csv × PLUGIN_MATRIX `lift.batch` (記録がある plugin のみ。 PLUGIN_MATRIX と突合しない block (matrix_name=None) は対象外)
usage: matrix_check.py [--facts work/distortion/facts.json] [--status work/distortion/status.csv]
"""
import argparse, csv, json, os, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ap = argparse.ArgumentParser()
ap.add_argument('--facts', default=os.path.join(P, 'work', 'distortion', 'facts.json'))
ap.add_argument('--status', default=os.path.join(P, 'work', 'distortion', 'status.csv'))
a = ap.parse_args()
M = {p['name']: p for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']}
F = json.load(open(a.facts))['shells']
S = {r['block']: r for r in csv.DictReader(open(a.status))}
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bkeys = [('lift_rc', 'lift_rc'), ('emcc_c_rc', 'emcc_c_rc'), ('f80_funcs', 'f80_funcs'), ('unimpl_helpers', 'declares_unimpl')]
bad = n = nb = 0
for blk, f in F.items():
    name = f['matrix_name']
    if name is None:
        continue
    lift = M[name]['lift']
    for mk, fk in keys:
        n += 1
        if lift[mk] != f[fk]:
            bad += 1
            print('MISMATCH', name, mk, lift[mk], f[fk])
    if 'batch' in lift:
        for mk, sk in bkeys:
            n += 1
            nb += 1
            if sk not in S.get(blk, {}) or lift['batch'][mk] != int(S[blk][sk]):
                bad += 1
                print('MISMATCH batch', name, mk, lift['batch'][mk], S.get(blk, {}).get(sk))
print('matrix_check: %d/%d 項目一致 (うち batch %d 項目)' % (n - bad, n, nb))
sys.exit(1 if bad or n == 0 else 0)
