#!/usr/bin/env python3
"""LD-18 (#865): m11 wasm_trap OOB 222 件の最上位 trap frame を集計し、上位 5 種の原因候補を IR から分類する。

分類 (IR 側の構造のみ・機械語との突合なし。候補であり原因の確定ではない):
  ptr_arg  : 関数本体で %arg を値のまま inttoptr せず使う load/store がある (ldfix F3 型の疑い)
  arg_val  : %arg を icmp/add で使うのみで inttoptr 経由の deref が無い
  no_arg   : %arg を使わない (呼出先に依存して落ちている可能性)

  python3 tools/liftdiff/tests/oob_top_frames.py > tools/liftdiff/results/m11_oob_top_frames.md
入力: work/m11/batch_closure.jsonl・tools/m11/work/boot_final3.ll (cwd 非依存)。
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BATCH = os.path.join(ROOT, 'work/m11/batch_closure.jsonl')
IR = os.path.join(ROOT, '../m11/work/boot_final3.ll')


def top_of(detail):
    m = re.match(r'.*? @ (.*)$', detail or '')
    if not m:
        return None, None
    fs = [f.replace('ld_wasm.wasm.', '') for f in m.group(1).split(' < ')]
    return fs[0], fs


def ir_funcs(path):
    out = {}
    name = None
    buf = []
    for line in open(path, errors='replace'):
        if line.startswith('define'):
            m = re.search(r'@([\w.$]+)\(', line)
            name = m.group(1) if m else None
            buf = []
        if name is not None:
            buf.append(line)
            if line.startswith('}'):
                out[name] = ''.join(buf)
                name = None
    return out


def classify(body):
    if body is None:
        return 'IR なし'
    ptr = re.search(r'(load|store) [^\n]*ptr %arg1\b|(load|store) [^\n]*ptr %\w+', body)
    arg_ptr = re.search(r'inttoptr i64 %arg\d', body)
    if arg_ptr:
        return 'ptr_arg (inttoptr %arg 経由の deref あり)'
    if '%arg' in body:
        return 'arg_val (%arg を値として使用のみ)'
    return 'no_arg'


def main():
    funcs = ir_funcs(IR)
    cnt = collections.Counter()
    chain = {}
    n = 0
    for line in open(BATCH):
        r = json.loads(line)
        cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
        if not cs:
            continue
        d = cs[0].get('wasm_detail') or ''
        if 'memory access out of bounds' not in d:
            continue
        top, fs = top_of(d)
        if top is None:
            continue
        n += 1
        cnt[top] += 1
        chain.setdefault(top, fs[:4])
    print('<!-- 自動生成: python3 tools/liftdiff/tests/oob_top_frames.py > tools/liftdiff/results/m11_oob_top_frames.md (入力 = work/m11/batch_closure.jsonl・tools/m11/work/boot_final3.ll) (LD-18, #865) -->')
    print('# m11 OOB: 最上位 trap frame 上位 5 種の原因候補 (LD-18, #865)')
    print('')
    print('対象 = wasm_trap のうち detail が "memory access out of bounds" の関数 %d 件 (batch jsonl)。' % n)
    print('IR 分類は候補。機械語との突合・単体再走は行っていない (未確定)。')
    print('')
    print('| 最上位 frame | 件数 | IR 分類 | 呼出連鎖 (先頭 4) |')
    print('|---|---:|---|---|')
    for top, k in cnt.most_common(5):
        key = top
        body = funcs.get(key)
        print('| %s | %d | %s | %s |' % (top, k, classify(body), ' < '.join(chain[top])))


if __name__ == '__main__':
    main()
