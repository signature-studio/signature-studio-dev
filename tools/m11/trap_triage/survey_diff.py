#!/usr/bin/env python3
"""survey_diff.py A.json B.json : survey_units.mjs の 2 出力を unit 単位で突合し, 種別の遷移表と ok 退行 unit を出す (#474).
trap = oob + halt0 + abort + other (miss/noproc は含まない). 使い方: survey_diff.py base.json new.json [unit ...]
kind 以外の差分 (#482): frames は wasm module hash / 関数 index が build ごとに変わるため深さ (行数) だけ比べ, 他の欄 (stubs/err/msg/va_mb) は完全一致を見る
icall 欄 (#494, 間接 call hit) は上の比較から外し, 両方に icall 欄がある時だけ site / target ごとの総数 [ok, miss] の差を別に出す (片方が旧形式なら省略)"""
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
def norm(r): return {k: (len(v) if k == 'frames' else v) for k, v in r.items() if k != 'icall'}
diff = [u for u in sorted(a) if norm(a[u]) != norm(b[u])]
print('kind 以外も含めた差分 unit (frames は深さのみ比較): %d %s' % (len(diff), diff))
def icall_total(d):
    t = {'sites': collections.defaultdict(lambda: [0, 0]), 'targets': collections.defaultdict(lambda: [0, 0])}
    for r in d.values():
        for kind, m in r.get('icall', {}).items():
            for k, (ok, miss) in m.items(): t[kind][k][0] += ok; t[kind][k][1] += miss
    return t
if any('icall' in r for r in a.values()) and any('icall' in r for r in b.values()):
    ta, tb = icall_total(a), icall_total(b)
    for kind in ('sites', 'targets'):
        ks = sorted(set(ta[kind]) | set(tb[kind]), key=lambda k: (k != 'ext', int(k, 16) if k != 'ext' else 0))
        dd = [k for k in ks if ta[kind][k] != tb[kind][k]]
        print('icall %s の総数 [ok, miss] 差 (A -> B): %d 件 %s' % (kind, len(dd), ' '.join('%s:%s->%s' % (k, ta[kind][k], tb[kind][k]) for k in dd)))
