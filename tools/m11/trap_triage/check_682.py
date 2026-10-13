#!/usr/bin/env python3
"""check_682.py (#682): M11_SURVEY_UNITS の unit 別ラベル JSON (m11_survey.mjs 出力) で指定 unit が全て ok かを判定する.
  usage: check_682.py <units.json> [--units 291,296,304,555,923]   (既定 = 5 unit)
  全て ok → exit 0 / 1 つでも非 ok → exit 1 (ネガコン用に非 0 を返す。exit 0 固定にしない)。
  unit 45 / 144 の現在ラベルも併記する (受入条件 2 の参照用)。"""
import json, sys

args = sys.argv[1:]
if not args or args[0].startswith('-'):
    print(__doc__, file=sys.stderr)
    sys.exit(2)
labels = json.load(open(args[0]))
units = [291, 296, 304, 555, 923]
if '--units' in args:
    units = [int(x) for x in args[args.index('--units') + 1].split(',')]
bad = [(u, labels[u]) for u in units if labels[u] != 'ok']
print('units ok %d / %d: %s' % (len(units) - len(bad), len(units), ' '.join('%d=%s' % (u, labels[u]) for u in units)))
print('ref unit 45=%s 144=%s' % (labels[45], labels[144]))
if bad:
    print('NG: not ok -> %s' % ' '.join('%d(%s)' % b for b in bad))
    sys.exit(1)
print('OK: all listed units are ok')
sys.exit(0)
