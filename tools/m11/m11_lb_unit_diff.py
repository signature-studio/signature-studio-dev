#!/usr/bin/env python3
"""#3160: 寛容起動の unit 別結果 (M11_TOLERANT_OUT の units[]) を 2 つの記録で比べる。
  usage: m11_lb_unit_diff.py A_units.json B_units.json
  units[] の要素 = [i, va, kind, va_bytes, getmem, freemem, oom, clobber]. kind が違う unit を列挙する (VA は A 側の表示)。
  同一記録どうし (A と A の再実行) は差 0、LB=0 と LB=0x10000 は差あり (ネガティブ側の確認)。"""
import json
import sys

a = json.load(open(sys.argv[1]))['units']
b = json.load(open(sys.argv[2]))['units']
assert len(a) == len(b), 'unit 数が違う: %d vs %d' % (len(a), len(b))
d = [(x[0], x[1], x[2], y[2]) for x, y in zip(a, b) if x[2] != y[2]]
print(json.dumps({'units': len(a), 'kind_diff': len(d), 'diff': [{'i': i, 'va': va, 'a': ka, 'b': kb} for i, va, ka, kb in d]}, ensure_ascii=False))
