#!/usr/bin/env python3
# SHX-T9c (#1255): shimx 版 survey と baseline (m11_boot) の unit 単位の kind 差分を集計する。
#   python3 unit_diff.py <baseline.survey.json> <shimx.survey.json>
# 入力は survey_trace.mjs の出力 (<dir>/<tag>.survey.json)。出力は標準出力に集計、詳細は同ディレクトリの unit_diff_out.txt に保存。
import json
import sys
import collections

base = {u['unit']: u for u in json.load(open(sys.argv[1]))['per_unit']}
sx = {u['unit']: u for u in json.load(open(sys.argv[2]))['per_unit']}
N = sorted(base)

diff = [n for n in N if base[n]['kind'] != sx[n]['kind']]
pairs = collections.Counter((base[n]['kind'], sx[n]['kind']) for n in diff)
oob_b = {n for n in N if base[n]['kind'] == 'oob'}
oob_s = {n for n in N if sx[n]['kind'] == 'oob'}
gain = sorted(oob_s - oob_b)
lost = sorted(oob_b - oob_s)
blocks = collections.Counter(((n - 1) // 100) * 100 for n in diff)

lines = []
lines.append('units %d / kind 差分 %d' % (len(N), len(diff)))
lines.append('kind 遷移 (baseline -> shimx): ' + ', '.join('%s->%s %d' % (a, b, c) for (a, b), c in pairs.most_common()))
lines.append('oob: baseline %d / shimx %d (増 %d・減 %d)' % (len(oob_b), len(oob_s), len(gain), len(lost)))
lines.append('oob 増の baseline kind: ' + str(dict(collections.Counter(base[n]['kind'] for n in gain))))
lines.append('oob 減の shimx kind: ' + str(dict(collections.Counter(sx[n]['kind'] for n in lost))))
lines.append('差分の 100 unit 区分別: ' + str(sorted(blocks.items())))
lines.append('最初の差分 unit: %d (%s -> %s)' % (diff[0], base[diff[0]]['kind'], sx[diff[0]]['kind']))
lines.append('unit 115: baseline %s (%s) / shimx %s' % (base[115]['kind'], base[115].get('detail'), sx[115]['kind']))
lines.append('')
lines.append('unit 別 (unit, lva, baseline, shimx):')
for n in diff:
    lines.append('%d %s %s %s' % (n, base[n]['lva'], base[n]['kind'], sx[n]['kind']))

out = '\n'.join(lines) + '\n'
print(out, end='')
open(__file__.rsplit('/', 1)[0] + '/unit_diff_out.txt', 'w').write(out)
