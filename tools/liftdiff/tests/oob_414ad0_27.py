#!/usr/bin/env python3
"""LD-18 (#865): trace_head 外の 27 件 (function_414ad0 系 OOB) の単体再走結果を集計する。

入力: tests/rerun_414ad0_27.sh の出力 work/m11_414ad0_27/<va>.json と list.txt (既定)。
  python3 tools/liftdiff/tests/oob_414ad0_27.py > tools/liftdiff/results/m11_oob_414ad0_27.md
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'work/m11_414ad0_27')
VA = '0x414ad0'

rows = []
for line in open(os.path.join(OUT, 'list.txt')):
    va, pat = line.split()
    path = os.path.join(OUT, va + '.json')
    if not os.path.exists(path):
        rows.append((va, pat, 'NO_RUN', None))
        continue
    r = json.load(open(path))
    cs = [c for c in r['cases'] if c['outcome'] in ('wasm_trap', 'both_fault')]
    if not cs:
        rows.append((va, pat, 'NO_TRAP:' + ','.join(c['outcome'] for c in r['cases']), None))
        continue
    c = cs[0]
    det = c.get('wasm_detail') or ''
    top = det.split(' @ ')[1].split(' < ')[0].replace('ld_wasm.wasm.', '') if ' @ ' in det else '?'
    W = [t[0] for t in c['raw']['wasm']['trace_head']]
    rows.append((va, pat, top, (VA in W, c['raw']['wasm'].get('trace_len'))))

print('<!-- 自動生成: python3 tools/liftdiff/tests/oob_414ad0_27.py > tools/liftdiff/results/m11_oob_414ad0_27.md (入力 = work/m11_414ad0_27/, tests/rerun_414ad0_27.sh の出力) (LD-18, #865) -->')
print('# m11 OOB: trace_head 外 27 件の単体再走 (LD-18, #865)')
print('')
print('trace_head=200 (-v) で単体再走。`wasm 414ad0 有` = wasm trace に 0x414ad0 が現れた (= 到達)。')
print('')
print('| 関数 | pattern | 最上位 trap frame | wasm trace 中の 0x414ad0 | wasm trace_len |')
print('|---|---|---|---|---|')
for va, pat, top, info in rows:
    if info is None:
        print('| %s | %s | %s | - | - |' % (va, pat, top))
    else:
        print('| %s | %s | %s | %s | %s |' % (va, pat, top, '有' if info[0] else '無', info[1]))
n_reach = sum(1 for _, _, _, i in rows if i and i[0])
n_top = sum(1 for _, _, t, _ in rows if t == 'function_414ad0')
print('')
print('集計: 27 件中、wasm trace に 0x414ad0 が現れる = %d、最上位 frame が function_414ad0 = %d。' % (n_reach, n_top))
