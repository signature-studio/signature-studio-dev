#!/usr/bin/env python3
"""block_manifest.json / インストーラが無い環境 (Actions の fl-win64 tarball) 用に、
PLUGIN_MATRIX.json の win modules から work/nsis_blockmap.json の最小互換版を作る。

win_funcs.py が使うのは idx / kind / outdir だけ (Plugins\\Fruity\\{Effects,Generators} 配下の PE の選別)。
nsis_names.py の出力 (25,164 件) の代替ではない: 141 プラグイン 181 PE の部分集合のみ。
  usage: python3 inventory/blockmap_from_matrix.py
"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, '..', 'PLUGIN_MATRIX.json')))['plugins']
out, seen = [], set()
for p in M:
    sub = 'Effects' if p['kind'].lower().startswith('eff') else 'Generators'
    for m in p['win']['modules']:
        if m['block'] in seen:
            continue
        seen.add(m['block'])
        out.append({'idx': m['block'], 'kind': 'PE', 'outdir': '$V31\\Plugins\\Fruity\\%s\\%s' % (sub, p['name']),
                    'name': os.path.basename(m['file'])})
os.makedirs(os.path.join(HERE, '..', 'work'), exist_ok=True)
json.dump(out, open(os.path.join(HERE, '..', 'work', 'nsis_blockmap.json'), 'w'))
print('blockmap entries', len(out))
