#!/usr/bin/env python3
"""work/nsis_blockmap.json の代替を PLUGIN_MATRIX.json から合成する。

inventory/nsis_names.py は block_manifest.json (fl-win64 tarball に含まれない) を要するため Actions 上で実行できない。
win_funcs.py / kernel_matrix.py が使うのは {kind, outdir, idx} のみ。PLUGIN_MATRIX.json の win モジュール (block 番号付き) から
同じ選択規則 (`$V31\\Plugins\\Fruity\\(Effects|Generators)\\`) を満たす記録を作る。既存ファイルは上書きしない。
"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '..')
out = os.path.join(P, 'work', 'nsis_blockmap.json')
if os.path.exists(out):
    print('exists:', out)
    raise SystemExit(0)
M = json.load(open(os.path.join(P, 'PLUGIN_MATRIX.json')))['plugins']
recs = []
for p in M:
    for m in p['win']['modules']:
        recs.append({'idx': m['block'], 'kind': 'PE', 'name': m['file'],
                     'outdir': '$V31\\Plugins\\Fruity\\%s\\%s' % (p['kind'], p['name'])})
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(recs, open(out, 'w'))
print('wrote', len(recs), 'records ->', out)
