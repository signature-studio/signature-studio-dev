#!/usr/bin/env python3
"""再計算した値が PLUGIN_MATRIX.json の記録と一致するか。 不一致が 1 件でもあれば exit 1。
  - shell: 閉包 6 項目 (closure_funcs / closure_bytes / fw_frontier_funcs / fw_frontier_bytes / vcalls / ptr_calls)
           と、PLUGIN_MATRIX に `lift.batch` があるものは batch の 4 項目 (lift_rc / emcc_c_rc / f80_funcs / unimpl_helpers) も
  - cpp  : .pdata 関数数
  PLUGIN_MATRIX に `lift` 欄が無い shell は「初測定」として別掲する (比較項目数には数えない)。 比較項目が 0 なら exit 1。
usage: matrix_check.py [--facts work/synth/facts.json] [--status work/synth/status.csv]
"""
import argparse, csv, json, os, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ap = argparse.ArgumentParser()
ap.add_argument('--facts', default=os.path.join(P, 'work', 'synth', 'facts.json'))
ap.add_argument('--status', default=os.path.join(P, 'work', 'synth', 'status.csv'))
a = ap.parse_args()
M = {p['name']: p for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']}
F = json.load(open(a.facts))
S = {r['block']: r for r in csv.DictReader(open(a.status))}
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bkeys = [('lift_rc', 'lift_rc'), ('emcc_c_rc', 'emcc_c_rc'), ('f80_funcs', 'f80_funcs'), ('unimpl_helpers', 'declares_unimpl')]
bad = n = 0
first = []
for name, e in F.items():
    sh = e['shell']
    if sh:
        lift = M[name]['lift']
        if not lift:
            first.append(name)
        else:
            for mk, fk in keys:
                n += 1
                if lift[mk] != sh[fk]:
                    bad += 1
                    print('MISMATCH', name, mk, lift[mk], sh[fk])
            for mk, sk in bkeys:
                if 'batch' in lift:
                    n += 1
                    got = int(S[str(sh['block'])][sk])
                    if lift['batch'][mk] != got:
                        bad += 1
                        print('MISMATCH', name, 'batch.' + mk, lift['batch'][mk], got)
    for c in e['cpp']:
        n += 1
        if c['matrix_pdata_funcs'] != c['pdata_funcs']:
            bad += 1
            print('MISMATCH', name, 'pdata_funcs block', c['block'], c['matrix_pdata_funcs'], c['pdata_funcs'])
print('matrix_check: %d/%d 項目一致; PLUGIN_MATRIX に lift 欄が無い (初測定): %s' % (n - bad, n, first or 'なし'))
sys.exit(1 if bad or n == 0 else 0)
