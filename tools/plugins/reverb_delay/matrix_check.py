#!/usr/bin/env python3
"""再計算した値が PLUGIN_MATRIX.json の `lift` 欄と一致するか。 1 項目でも不一致 / 欠落なら exit 1。

usage: matrix_check.py [--facts F] [--status S] [--matrix M]
  閉包 6 項目 (closure_funcs / closure_bytes / frontier_funcs / frontier_bytes / vcall / ptr_or_vt0): facts.json ⟷ matrix.lift
  batch 4 項目 (lift_rc / emcc_c_rc / f80_funcs / unimpl_helpers): status.csv ⟷ matrix.lift.batch (matrix に batch 欄がある plugin のみ。 無い plugin は件数を表示)
  facts / status に無い plugin、matrix に無い plugin は不一致として数える。
"""
import csv, json, os, sys
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def main(argv):
    arg = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    facts = arg('--facts', os.path.join(P, 'work', 'reverb_delay', 'facts.json'))
    status = arg('--status', os.path.join(P, 'work', 'reverb_delay', 'status9.csv'))
    mpath = arg('--matrix', os.path.join(P, 'PLUGIN_MATRIX.json'))
    M = {p['name']: p for p in json.load(open(mpath))['plugins']}
    F = json.load(open(facts))
    S = {}
    for r in csv.DictReader(open(status)):
        S[int(r['block'])] = r
    keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
            ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
    bkeys = [('lift_rc', 'lift_rc'), ('emcc_c_rc', 'emcc_c_rc'), ('f80_funcs', 'f80_funcs'), ('unimpl_helpers', 'declares_unimpl')]
    bad = n = no_batch = 0
    for name, f in F.items():
        if name not in M:
            bad += 1
            n += 1
            print('MISMATCH', name, 'PLUGIN_MATRIX.json に無い')
            continue
        lf = M[name]['lift']
        for mk, fk in keys:
            n += 1
            if mk not in lf or lf[mk] != f[fk]:
                bad += 1
                print('MISMATCH', name, mk, 'matrix=', lf.get(mk), 'measured=', f[fk])
        if 'batch' not in lf:
            no_batch += 1
            continue
        row = S.get(f['block'])
        for mk, sk in bkeys:
            n += 1
            if row is None or mk not in lf['batch'] or int(lf['batch'][mk]) != int(row[sk]):
                bad += 1
                print('MISMATCH', name, 'batch.' + mk, 'matrix=', lf['batch'].get(mk), 'measured=', None if row is None else row[sk])
    print('matrix_check: %d/%d 項目一致 (plugin %d 本。 matrix に batch 欄が無く batch 4 項目を比較していない plugin: %d)' % (n - bad, n, len(F), no_batch))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
