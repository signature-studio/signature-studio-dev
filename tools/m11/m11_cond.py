#!/usr/bin/env python3
"""m11_cond.py: IR 生成条件 (ldfix / qstore の適用有無・PE) を work/ir_conditions.json に記録する (#680).
使い方:
  python3 m11_cond.py --reset K=V ...   ファイルを作り直して K=V を書く (m11_gen_ir2.sh 冒頭)
  python3 m11_cond.py K=V ...           既存ファイルに K=V を上書き (m11_gen_ir2.sh / m11_build.sh)
  python3 m11_cond.py --get K           K の値を印字 (無ければ空行)
"""
import json, os, sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work', 'ir_conditions.json')


def load():
    if not os.path.exists(P):
        return {}
    with open(P) as f:
        return json.load(f)


args = sys.argv[1:]
if args[:1] == ['--get']:
    print(load().get(args[1], ''))
    sys.exit(0)
d = {} if args[:1] == ['--reset'] else load()
for a in args[1:] if args[:1] == ['--reset'] else args:
    k, _, v = a.partition('=')
    d[k] = v
os.makedirs(os.path.dirname(P), exist_ok=True)
with open(P, 'w') as f:
    json.dump(d, f, ensure_ascii=False, indent=1)
    f.write('\n')
