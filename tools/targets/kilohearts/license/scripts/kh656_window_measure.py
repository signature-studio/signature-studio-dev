#!/usr/bin/env python3
"""#4272: D11 の文字列窓 (--rdata-str) の影響を測る。lic_config.json は書き換えない (読み取りのみ)。

  python3 scripts/kh656_window_measure.py lift8|set313 on|off [--rounds-json work/kh656_rounds.json]

  lift8  : module F の lift 8 件 (lift-8)
  set313 : 313 集合 = F の初期 lift 8 件 + kh656_rounds.json の new_lift (全ラウンド) - 1813846e0
           (kh656_closure.py の 4 ラウンド記録から復元。1813846e0 は memset shim)
出力は license/work/m4272_<set>_<mode>/ (gitignore)。stat (JSON 1 行) を stdout に出す。
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.dirname(HERE)
sys.path.insert(0, LIC)
os.chdir(LIC)
import lic_build as L

if len(sys.argv) < 3 or sys.argv[1] not in ('lift8', 'set313') or sys.argv[2] not in ('on', 'off'):
    sys.exit(__doc__)
sset, mode = sys.argv[1], sys.argv[2]
mod = L.CFG['modules']['F']
vas = {int(v, 16) for v in mod['lift']}
shims = dict(mod.get('shims') or {})
if sset == 'set313':
    rounds = json.load(open(os.path.join(LIC, 'work', 'kh656_rounds.json')))
    for rr in rounds:
        vas |= {int(v, 16) for v in rr['new_lift']}
    vas.discard(0x1813846e0)
    shims['1813846e0'] = 'memset'
tag = 'm4272_%s_%s' % (sset, mode)
stat = L.build(vas, os.path.join(LIC, 'work', tag), tag, apply_stub=True, module='F', abi=mod.get('abi'),
               shims=shims, raw_va=mod.get('raw_va', False), volatile_ret=mod.get('volatile_ret', False),
               emcc_opt=mod.get('emcc_opt', '-O1'), rdata_str=(mode == 'on'))
print(json.dumps({k: v for k, v in stat.items() if k != 'ranges'}, ensure_ascii=False))
