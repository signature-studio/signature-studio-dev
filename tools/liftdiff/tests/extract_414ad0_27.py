#!/usr/bin/env python3
"""LD-18 (#865): trace_head 外の function_414ad0 系 OOB 関数 (27 件) の入力リストを batch jsonl から作る。

抽出条件 (tests/oob_414ad0.py の 68 件のうち、wasm trace_head に 0x414ad0 が現れないもの):
  最初の wasm_trap case の wasm_detail が 'memory access out of bounds @ ld_wasm.wasm.function_414ad0' で始まり、
  その case の wasm trace_head に 0x414ad0 が無い。出力は "<va> <pattern>" (1 行 1 関数・va 昇順ではなく jsonl 順)。

  mkdir -p work/m11_414ad0_27 && python3 tools/liftdiff/tests/extract_414ad0_27.py > work/m11_414ad0_27/list.txt
  入力既定: work/m11/batch_closure.jsonl (cwd 非依存)。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BATCH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'work/m11/batch_closure.jsonl')
PREFIX = 'memory access out of bounds @ ld_wasm.wasm.function_414ad0'
VA = '0x414ad0'

for line in open(BATCH):
    r = json.loads(line)
    cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
    if not cs:
        continue
    c = cs[0]
    if not (c.get('wasm_detail') or '').startswith(PREFIX):
        continue
    if any(t[0] == VA for t in c['raw']['wasm']['trace_head']):
        continue
    print('%s %s' % (r['function']['va'], c['pattern']))
