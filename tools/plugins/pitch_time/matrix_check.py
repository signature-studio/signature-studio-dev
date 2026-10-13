#!/usr/bin/env python3
"""再計算値が PLUGIN_MATRIX.json と一致するか。 不一致・欠落が 1 件でもあれば exit 1。
  (a) 閉包 6 項目 (closure_funcs / closure_bytes / frontier 関数 / frontier バイト / vcall / ptr) × 殻 7 本 (work/pitch_time/facts.json)
  (b) MATRIX に `lift.batch` がある殻は lift_rc / emcc_c_rc / f80_funcs / unimpl_helpers の 4 項目も (work/pitch_time/status7.csv の再測定値)
usage: matrix_check.py [--facts facts.json] [--status status7.csv]
"""
import csv, json, os, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
W = os.path.join(P, 'work', 'pitch_time')
a = sys.argv[1:]
facts = a[a.index('--facts') + 1] if '--facts' in a else os.path.join(W, 'facts.json')
status = a[a.index('--status') + 1] if '--status' in a else os.path.join(W, 'status7.csv')
M = {p['name']: p for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']}
F = json.load(open(facts))['shells']
S = {r['name']: r for r in csv.DictReader(open(status))}
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bkeys = [('lift_rc', 'lift_rc'), ('emcc_c_rc', 'emcc_c_rc'), ('f80_funcs', 'f80_funcs'), ('unimpl_helpers', 'declares_unimpl')]
bad = n = nb = 0
if not F:
    print('MISMATCH facts.json に殻が 0 本')
    sys.exit(1)
for name, f in F.items():
    for mk, fk in keys:
        n += 1
        if M[name]['lift'][mk] != f[fk]:
            bad += 1
            print('MISMATCH', name, mk, 'matrix=%s measured=%s' % (M[name]['lift'][mk], f[fk]))
    b = M[name]['lift'].get('batch')
    if b:
        for mk, sk in bkeys:
            nb += 1
            if name not in S:
                bad += 1
                print('MISMATCH', name, mk, 'status7.csv に行が無い')
            elif b[mk] != int(S[name][sk]):
                bad += 1
                print('MISMATCH', name, mk, 'matrix=%s measured=%s' % (b[mk], S[name][sk]))
print('matrix_check: %d/%d 項目一致 (閉包 %d + batch %d; 殻 %d 本)' % (n + nb - bad, n + nb, n, nb, len(F)))
sys.exit(1 if bad else 0)
