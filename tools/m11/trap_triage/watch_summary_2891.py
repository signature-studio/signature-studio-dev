#!/usr/bin/env python3
# #2891: watch_store_2891.mjs の出力 (watch.json) と survey (survey.json)・store 計装表 (sites.json) から REPORT_2891 の数値を出す。
# 入力: <watch.json> <survey.json> <sites.json>  出力: 標準出力 (work/ 以下の JSON を読み、commit しない)。
# 陰性対照: frame 先頭の wasm 関数 (V8 index) を wat index に直す差 (正 = 39、対照 = 38) で store_sites の関数と突き合わせる。
import json, re, sys

watch = json.load(open(sys.argv[1]))
survey = {r['unit']: r['kind'] for r in json.load(open(sys.argv[2]))}
sites = json.load(open(sys.argv[3]))['sites']

per = {r['unit']: r.get('hits', 0) for r in watch['per']}
kind_diff = [r['unit'] for r in watch['per'] if survey.get(r['unit']) != r['kind']]
print('hit total (all units %d): %d' % (len(watch['per']), watch['hitN']))
print('hit 0..492: %d / 493..941: %d / units with hit: %d' % (
    sum(h for u, h in per.items() if u <= 492), sum(h for u, h in per.items() if u >= 493),
    sum(1 for h in per.values() if h)))
print('unit 304: %d, 369: %d, 298: %d' % (per.get(304, 0), per.get(369, 0), per.get(298, 0)))
print('kind diff vs survey: %d' % len(kind_diff))
print('logged hits (frame recorded): %d, units %s' % (len(watch['hits']), sorted({r['unit'] for r in watch['hits']})))
ok = {39: 0, 38: 0}
for r in watch['hits']:
    f = int(re.search(r'wasm-function\[(\d+)\]', r['frames'][0]).group(1))
    fn = [x['func'] for x in sites[str(r['id'])]]
    print('unit %d id %d %s bytes %d old8 %s val %s -> wat %d (sites %s)' % (
        r['unit'], r['id'], r['addr'], r['bytes'], r['old8'], r['val'], f - 39, fn))
    for k in ok:
        if (f - k) in fn:
            ok[k] += 1
print('attribution: wat = V8 - 39 matches %d/%d; control V8 - 38 matches %d/%d' % (
    ok[39], len(watch['hits']), ok[38], len(watch['hits'])))
