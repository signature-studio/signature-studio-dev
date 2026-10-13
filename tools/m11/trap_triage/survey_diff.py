#!/usr/bin/env python3
"""survey_diff.py A.json B.json : survey_units.mjs の 2 出力を unit 単位で突合し, 種別の遷移表と ok 退行 unit を出す (#474).
trap = oob + halt0 + abort + other (miss/noproc は含まない). 使い方: survey_diff.py base.json new.json [unit ...]
kind 以外の差分 (#482): frames は wasm module hash / 関数 index が build ごとに変わるため深さ (行数) だけ比べ, 他の欄 (stubs/err/msg/va_mb) は完全一致を見る"""
import json, sys, collections
a = {r['unit']: r for r in json.load(open(sys.argv[1]))}
b = {r['unit']: r for r in json.load(open(sys.argv[2]))}
if set(a) != set(b): sys.exit('unit 集合が異なる: %d vs %d' % (len(a), len(b)))
TRAP = ('oob', 'halt0', 'abort', 'other')
for name, d in (('A', a), ('B', b)):
    c = collections.Counter(r['kind'] for r in d.values())
    print('%s: %s  trap=%d' % (name, dict(sorted(c.items())), sum(c[k] for k in TRAP)))
print('遷移 (A -> B):')
for k, v in sorted(collections.Counter((a[u]['kind'], b[u]['kind']) for u in a).items()): print('  %-7s -> %-7s %d' % (k[0], k[1], v))
reg = [u for u in sorted(a) if a[u]['kind'] == 'ok' and b[u]['kind'] != 'ok']
print('ok 退行 unit: %d %s' % (len(reg), reg))
for u in map(int, sys.argv[3:]): print('unit %d: %s -> %s %s' % (u, a[u]['kind'], b[u]['kind'], b[u].get('msg', '')))
def norm(r): return {k: (len(v) if k == 'frames' else v) for k, v in r.items()}
diff = [u for u in sorted(a) if norm(a[u]) != norm(b[u])]
print('kind 以外も含めた差分 unit (frames は深さのみ比較): %d %s' % (len(diff), diff))
