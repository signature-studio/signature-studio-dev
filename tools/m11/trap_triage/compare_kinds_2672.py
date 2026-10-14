#!/usr/bin/env python3
# #2672: 計装版 (watch_store_2672.mjs の出力) と基準 (survey_units.mjs の出力) を unit 単位で比べ、kind の差分数・0〜477 の kind 集計・hit を出す。
# 使い方: python3 compare_kinds_2672.py <base.json> <watch.json>
import collections, json, sys

base = json.load(open(sys.argv[1]))
watch = json.load(open(sys.argv[2]))
bk = {r['unit']: r['kind'] for r in base}
wk = {r['unit']: r['kind'] for r in watch['per']}
units = sorted(wk)
diff = [u for u in units if bk.get(u) != wk[u]]
print('compared_units=%d kind_diff=%d %s' % (len(units), len(diff), diff[:10]))
for name, m in (('base', {u: bk[u] for u in units}), ('watch', wk)):
    c = collections.Counter(k for u, k in m.items() if u <= 477)
    print('0-477 %s: %s' % (name, ' '.join('%s %d' % kv for kv in sorted(c.items()))))
print('hitN=%d' % watch['hitN'])
for h in watch['hits']:
    print('hit unit=%s id=%s addr=%s bytes=%s val=%s frames=%s' % (h['unit'], h['id'], h['addr'], h['bytes'], h.get('val'), ' > '.join(h['frames'][:6])))
