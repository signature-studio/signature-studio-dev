#!/usr/bin/env python3
"""block_manifest.json が無い環境 (Actions) 用: PLUGIN_MATRIX.json の win modules から
work/nsis_blockmap.json (win_funcs.py / win_unique.py が読む kind=PE の行のみ) を再構成する。
nsis_names.py の出力と同じキー (idx/kind/outdir/name) だけを埋める。"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']
rows = []
for p in M:
    for m in p['win']['modules']:
        sub = ('\\' + m['subdir']) if m['subdir'] else ''
        rows.append({'idx': m['block'], 'kind': 'PE', 'name': m['file'],
                     'outdir': '$V31\\Plugins\\Fruity\\%s\\%s%s' % (p['kind'], p['name'], sub)})
os.makedirs(os.path.join(HERE, '..', 'work'), exist_ok=True)
json.dump(rows, open(os.path.join(HERE, '..', 'work', 'nsis_blockmap.json'), 'w'))
print('rows', len(rows))
