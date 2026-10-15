#!/usr/bin/env python3
"""#4272 / #4670: D11 の文字列窓 (--rdata-str) の影響を測る。lic_config.json は書き換えない (読み取りのみ)。

  python3 scripts/kh656_window_measure.py lift8|set313 on|off

  lift8  : 測定 commit 091c68915 の lift 8 件 (LIFT8 に固定。現行 lic_config の lift 集合 (1305 件) は使わない)
  set313 : 313 集合 = scripts/kh656_set313.json (commit cd26429ed。閉包 4 ラウンドの new_lift から再生成・#4670 参照)。
           ファイルが無ければ停止する。
on : rdata_str=True、rdata_raw_allow は modules.F の値 / off : rdata_str=False
出力は license/work/m4670_<set>_<mode>/ (gitignore)。stat (JSON 1 行) を stdout に出す。
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
sys.path.insert(0, LIC)
os.chdir(LIC)
import lic_build as L

LIFT8 = ['180ef7fc0', '18004c780', '180045130', '1800b4ac0', '1800b4ae0', '180054bd0', '1800524e0', '1800b4b10']

if len(sys.argv) < 3 or sys.argv[1] not in ('lift8', 'set313') or sys.argv[2] not in ('on', 'off'):
    sys.exit(__doc__)
sset, mode = sys.argv[1], sys.argv[2]
mod = L.CFG['modules']['F']
if sset == 'lift8':
    vas = {int(v, 16) for v in LIFT8}
    shims = dict(mod.get('shims') or {})
else:
    p = os.path.join(HERE, 'kh656_set313.json')
    if not os.path.exists(p):
        sys.exit('set313: %s が無い (313 集合の VA 一覧が未 commit)' % p)
    vas = {int(v, 16) for v in json.load(open(p))}
    shims = dict(mod.get('shims') or {})
tag = 'm4670_%s_%s' % (sset, mode)
stat = L.build(vas, os.path.join(LIC, 'work', tag), tag, apply_stub=True, module='F', abi=mod.get('abi'),
               shims=shims, raw_va=mod.get('raw_va', False), volatile_ret=mod.get('volatile_ret', False),
               emcc_opt=mod.get('emcc_opt', '-O1'), rdata_str=(mode == 'on'),
               rdata_raw_allow=(mod.get('rdata_raw_allow', '') if mode == 'on' else ''))
print(json.dumps({k: v for k, v in stat.items() if k != 'ranges'}, ensure_ascii=False))
