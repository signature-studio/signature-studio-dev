#!/usr/bin/env python3
"""kh249_product_index.py — Kilohearts installer の index.json から product_index.json を生成する (#249).

入力: plugins-kilohearts 素材 (Kilohearts Offline Installer.zip) 内の payload.dat → index.json
      (素材の所在は $KH_SRC、既定 $HOME/ダウンロード。extract_installer.sh と同じ既定)
出力: work/winpkg/product_index.json  ({"plugins": [...]} = index.json の releases[0].plugins を
      bank のみの製品 (snapin 形式を持たない) を除いて列挙したもの。core を含む)

usage: python3 scripts/kh249_product_index.py [--out PATH]
"""
import json, os, sys, zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # license/
KILO = os.path.dirname(HERE)  # tools/targets/kilohearts
arg = lambda k, d=None: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
SRC = os.environ.get('KH_SRC') or os.path.join(os.path.expanduser('~'), 'ダウンロード')
ZIP = os.path.join(SRC, 'Kilohearts Offline Installer.zip')
OUT = arg('--out', os.path.join(KILO, 'work', 'winpkg', 'product_index.json'))

if not os.path.isfile(ZIP):
    sys.exit('FAIL: 素材が無い: %s (plugins-kilohearts を展開するか KH_SRC を指定)' % ZIP)
TMP = os.path.join(KILO, 'work', 'win')  # extract_installer.sh と同じ展開先 (payload.dat は数 GB のため読み込まず展開する)
os.makedirs(TMP, exist_ok=True)
with zipfile.ZipFile(ZIP) as z:
    payload = z.extract('payload.dat', TMP)
with zipfile.ZipFile(payload) as p:
    index = json.loads(p.read('index.json'))
plugins = index['releases'][0]['plugins']
plugins = [x for x in plugins if set(x['formats']) - {'bank'}]
assert len(plugins) == 46, 'product_index 件数が 46 でない: %d' % len(plugins)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({'plugins': plugins}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('wrote %s (%d plugins)' % (OUT, len(plugins)))
