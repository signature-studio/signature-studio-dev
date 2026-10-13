#!/usr/bin/env python3
"""再計算した閉包 (facts.json) が PLUGIN_MATRIX.json の `lift` 欄と一致するか。 不一致・欠落・空入力は exit 1。

  matrix_check.py [--facts PATH] [--status PATH]
  - 閉包 6 項目 (closure_funcs / closure_bytes / fw_frontier_funcs / fw_frontier_bytes / vcalls / ptr_calls) × Delphi 殻 7 本
  - PLUGIN_MATRIX が `lift.batch` を持つ殻 (FL Keys・Granulizer・Slicer) は、判定済み status.csv の lift_rc / emcc_c_rc / f80_funcs / 未実装 helper 数 4 項目も照合
  - 期待項目数 (6×殻数 + 4×batch 持ち殻数) と実照合数が一致しなければ不合格 (facts が空・欠けた時に vacuous に通さない)
"""
import argparse, csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
sys.path.insert(0, HERE)
import targets

ap = argparse.ArgumentParser()
ap.add_argument('--facts', default=os.path.join(P, 'work', 'sampler', 'facts.json'))
ap.add_argument('--status', default=os.path.join(P, 'work', 'sampler', 'status.csv'))
a = ap.parse_args()
M = {p['name']: p for p in json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']}
F = json.load(open(a.facts))
rows = list(csv.DictReader(open(a.status)))
S = {int(r['block']): r for r in rows}
keys = [('closure_funcs', 'closure_funcs'), ('closure_bytes', 'closure_bytes'), ('fw_frontier_funcs', 'frontier_funcs'),
        ('fw_frontier_bytes', 'frontier_bytes'), ('vcalls', 'vcall'), ('ptr_calls', 'ptr_or_vt0')]
bkeys = [('lift_rc', 'lift_rc'), ('emcc_c_rc', 'emcc_c_rc'), ('f80_funcs', 'f80_funcs'), ('unimpl_helpers', 'declares_unimpl')]
bad = n = want = mism = 0
for name, blk, _ in targets.SHELLS:
    want += len(keys)
    mb = (M[name]['lift'] or {}).get('batch')
    want += len(bkeys) if mb else 0
    f = F.get(name)
    if f is None:
        bad += 1
        print('MISSING facts', name)
        continue
    for mk, fk in keys:
        n += 1
        if M[name]['lift'][mk] != f[fk]:
            bad += 1
            mism += 1
            print('MISMATCH', name, mk, M[name]['lift'][mk], f[fk])
    if mb:
        s = S.get(blk)
        for mk, sk in bkeys:
            n += 1
            if s is None or int(s[sk]) != mb[mk]:
                bad += 1
                mism += 1
                print('MISMATCH batch', name, mk, mb[mk], None if s is None else s[sk])
if n != want:
    bad += 1
    print('COUNT 照合 %d 項目 != 期待 %d 項目' % (n, want))
print('matrix_check: %d/%d 項目一致' % (n - mism, want))
sys.exit(1 if bad or n == 0 else 0)
