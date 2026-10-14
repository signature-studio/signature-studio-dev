#!/usr/bin/env python3
# M11 寛容起動の skip unit が trap までに書いた heap の範囲 (#2768) を集計する.
# 入力: work/tolerant_heap.json (M11_HEAP_FROM=<寛容起動の記録> M11_HEAP_OUT=... node m11_tolerant.mjs の出力)
# 出力: 領域別 (c_static = wasm の静的領域, heap = malloc 領域 (VirtualAlloc 含む), gap, stack) の差分 B を unit ごとに表で出す.
#   stack は表に含めず合計だけ書く (unit 内の関数フレームで、状態ではない)。
# 使い方: python3 m11_tolerant_heap.py [work/tolerant_heap.json] [--top N]
import json, sys, os

path = next((a for a in sys.argv[1:] if not a.startswith('--')), os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work', 'tolerant_heap.json'))
top = int(sys.argv[sys.argv.index('--top') + 1]) if '--top' in sys.argv else 0
d = json.load(open(path))
REG = ('c_static', 'heap', 'gap', 'stack_gap', 'stack')
rows = []
tot = {r: 0 for r in REG}
kinds = {}
for u in d['units']:
    by = {r: 0 for r in REG}
    n = {r: 0 for r in REG}
    for s, e, r in u['ranges']:
        by[r] += e - s
        n[r] += 1
    for r in REG:
        tot[r] += by[r]
    kinds[u['kind']] = kinds.get(u['kind'], 0) + 1
    hr = sorted((r for r in u['ranges'] if r[2] in ('heap', 'c_static')), key=lambda r: -(r[1] - r[0]))
    rows.append((by, n, u, hr))
rows.sort(key=lambda x: -(x[0]['heap'] + x[0]['c_static'] + x[0]['gap']))
print('| 順位 | i | VA | 種類 | c_static B | heap B | gap B | 区間数 (heap+c_static) | 最大の区間 (領域・先頭 VA 相当の offset・長さ B) |')
print('|---:|---:|---|---|---:|---:|---:|---:|---|')
for k, (by, n, u, hr) in enumerate(rows, 1):
    big = ', '.join('%s 0x%x +%d' % (r[2], r[0], r[1] - r[0]) for r in hr[:2]) or '-'
    print('| %d | %d | %s | %s | %d | %d | %d | %d | %s |' % (k, u['i'], u['va'], u['kind'], by['c_static'], by['heap'], by['gap'], n['heap'] + n['c_static'], big))
print()
print('合計 (B): ' + ', '.join('%s=%d' % (r, tot[r]) for r in REG) + ' / 種類: ' + json.dumps(kinds, ensure_ascii=False) + ' / units=%d match=%s' % (len(d['units']), d['match']))
print('layout: ' + json.dumps(d['layout']) + ' img_len=%d' % d['img_len'])
if top:
    print()
    print('上位 %d unit の heap / c_static 区間 (先頭 20 件):' % top)
    for by, n, u, hr in rows[:top]:
        print('- i=%d %s (%s): ' % (u['i'], u['va'], u['kind']) + ', '.join('[0x%x,0x%x) %s' % (r[0], r[1], r[2]) for r in sorted(u['ranges'], key=lambda r: r[0]) if r[2] in ('heap', 'c_static'))[:900])
