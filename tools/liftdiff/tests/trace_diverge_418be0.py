#!/usr/bin/env python3
"""LD-28 (#1035): 0x418be0 (型 D・P2 20 件) の食い違いを trace_head の範囲で分解する。

batch jsonl のみを読む (PE・IR は使わない・再走なし)。
native は 0x418be0 の直後に LoadStringW の thunk 0x407030 を踏むが、wasm の import 呼出しは trace に現れない。
そこで thunk を除いた native 列と wasm 列を比べ、最初の食い違いを求める。

  python3 tools/liftdiff/tests/trace_diverge_418be0.py > tools/liftdiff/results/m11_418be0_thunk.md

入力既定 = tools/liftdiff/work/m11/batch_closure.jsonl (`work-liftdiff` の展開先)。
"""
import argparse
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THUNK = 0x407030
ENTRY = 0x418be0

ap = argparse.ArgumentParser()
ap.add_argument('batch', nargs='?', default=os.path.join(ROOT, 'work/m11/batch_closure.jsonl'))
A = ap.parse_args()


def first_diff(a, b):
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return i


def parse_trace(head, cnt):
    out = []
    for t in head:
        try:
            out.append(int(t[0], 16))
        except (TypeError, ValueError, IndexError):
            cnt['bad_trace_entry'] += 1
    return out


def main():
    rows = [json.loads(l) for l in open(A.batch)]
    cnt = collections.Counter()
    nxt = collections.Counter()
    for r in rows:
        cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
        if not cs:
            continue
        c = cs[0]
        if not (c.get('wasm_detail') or '').startswith('unreachable') or c.get('wasm_status') == 'badjson':
            continue
        N = parse_trace(c['raw']['native']['trace_head'], cnt)
        W = parse_trace(c['raw']['wasm']['trace_head'], cnt)
        i = first_diff(N, W)
        if i == 0 or (i == len(N) == len(W)) or N[i - 1] != ENTRY:
            continue
        cnt['total'] += 1
        N2 = [x for x in N if x != THUNK]
        j = first_diff(N2, W)
        if j == len(N2) or j == len(W):
            cnt['cap_limited'] += 1
            continue
        cnt['diverge_after_thunk'] += 1
        nxt[(N2[j - 1], N2[j], W[j])] += 1
    f = lambda v: '0x%x' % v
    print('<!-- 自動生成: python3 tools/liftdiff/tests/trace_diverge_418be0.py > tools/liftdiff/results/m11_418be0_thunk.md (LD-28 / #1035) -->')
    print('# m11 0x418be0 (型 D・P2) の食い違い分解 (LD-28, #1035)')
    print('')
    print('対象 = batch の unreachable case のうち、最初の食い違い直前の共通 entry が 0x418be0 のもの %d 件。' % cnt['total'])
    print('最初の食い違いは 0x407030 (LoadStringW thunk) の有無 (native のみ)。thunk を除いた列で再比較した。')
    print('')
    print('| 項目 | 件数 |')
    print('|---|---:|')
    print('| thunk 除去後も trace_head 内で食い違う | %d |' % cnt['diverge_after_thunk'])
    print('| trace_head (最大 12 件) の上限で判定不能 | %d |' % cnt['cap_limited'])
    print('| 解析不能として除外した trace_head 要素 | %d |' % cnt['bad_trace_entry'])
    print('')
    print('| 直前の共通 entry (L2) | native 次 entry | wasm 次 entry | 件数 |')
    print('|---|---|---|---:|')
    for (l2, n, w), m in sorted(nxt.items(), key=lambda kv: -kv[1]):
        print('| %s | %s | %s | %d |' % (f(l2), f(n), f(w), m))


if __name__ == '__main__':
    main()
