#!/usr/bin/env python3
"""PLG-F2: work/batch/status.csv を PLUGIN_MATRIX.json の lift 欄と突合する (closure_funcs / closure_bytes / lift_rc / emcc_c_rc)。
  cd tools/plugins && python3 f2/matrix_check.py <block> ...      DIFF が 1 つでもあれば exit 1
"""
import csv, json, sys
M = json.load(open('PLUGIN_MATRIX.json'))['plugins']
by = {m['block']: p for p in M for m in p['win']['modules']}
rows = {int(r['block']): r for r in csv.DictReader(open('work/batch/status.csv'))}
bad = 0
for b in map(int, sys.argv[1:]):
    r, p = rows[b], by[b]
    d = p['lift']
    bt = d.get('batch')   # T3 (Frequency Splitter) は matrix に batch 欄が無い = emcc/lift_rc は比較対象外
    ok = int(r['closure_funcs']) == d['closure_funcs'] and int(r['closure_bytes']) == d['closure_bytes']
    if bt:
        ok = ok and int(r['lift_rc']) == bt['lift_rc'] and int(r['emcc_c_rc']) == bt['emcc_c_rc']
    bad += not ok
    print('%d %-24s funcs=%s bytes=%s lift_rc=%s emcc_c_rc=%s -> %s%s' % (
        b, p['name'], r['closure_funcs'], r['closure_bytes'], r['lift_rc'], r['emcc_c_rc'],
        'MATCH' if ok else 'DIFF', '' if bt else ' (matrix に batch 欄なし: closure のみ比較)'))
print('DIFF count =', bad)
sys.exit(1 if bad else 0)
