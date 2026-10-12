#!/usr/bin/env python3
"""LD-5 (#236): m11 closure の wasm_trap タグ付き関数のトリアージ集計。

入力: batch jsonl (`liftdiff.py batch targets/m11.json --set closure` の出力) と
      results/m11_closure_verdicts.tsv (tags 列に wasm_trap を含む行 = 対象集合)。
出力: Markdown (stdout)。先頭行は自動生成コメント。

  python3 tests/triage_wasm_trap.py [batch.jsonl] [verdicts.tsv] > results/m11_wasm_trap_triage.md

種別は各関数の「最初の wasm_trap case」の wasm_detail から ldlib.classify.trap_kind と同じ規則で決める
(= タグ evidence の先頭語と同じ基準)。unreachable は trap frame 列で連鎖を畳む。
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from ldlib.classify import trap_kind  # noqa: E402

BATCH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'work/m11/batch_closure.jsonl')
TSV = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'results/m11_closure_verdicts.tsv')


def frames(detail):
    m = re.match(r'.*? @ (.*)$', detail or '')
    if not m:
        return []
    return [f.replace('ld_wasm.wasm.', '') for f in m.group(1).split(' < ')]


def call_names(raw, side):
    return [c['n'] for c in (raw.get(side) or {}).get('calls') or []]


def main():
    rows = {}
    for line in open(BATCH):
        r = json.loads(line)
        rows[r['function']['va']] = r
    tsv = {}
    for line in open(TSV):
        p = line.rstrip('\n').split('\t')
        if p[0].startswith('#'):
            continue
        tsv[p[0]] = p
    target = [va for va, p in tsv.items() if 'wasm_trap' in p[4].split(',')]
    primary = [va for va, p in tsv.items() if p[3] == 'wasm_trap']

    kind = {}
    first = {}
    no_trap_case = []
    for va in target:
        r = rows.get(va)
        cs = [c for c in (r or {}).get('cases', []) if c['outcome'] == 'wasm_trap']
        if not cs:
            no_trap_case.append(va)
            continue
        first[va] = cs[0]
        kind[va] = trap_kind(cs[0].get('wasm_detail'))
        if cs[0].get('wasm_status') == 'badjson':
            kind[va] = 'badjson'

    out = []
    w = out.append
    w('<!-- 自動生成: python3 tools/liftdiff/tests/triage_wasm_trap.py work/m11/batch_closure.jsonl results/m11_closure_verdicts.tsv -->')
    w('# m11 wasm_trap トリアージ (LD-5, #236)')
    w('')
    w('対象 = verdicts.tsv の tags 列に `wasm_trap` を含む行 **%d** (primary_tag が wasm_trap は %d)。' % (len(target), len(primary)))
    w('batch jsonl: %d 行。' % len(rows))
    w('')
    w('## 1. 種別内訳 (関数単位・最初の wasm_trap case 基準)')
    w('')
    w('| 種別 | 関数数 |')
    w('|---|---:|')
    for k, n in collections.Counter(kind.values()).most_common():
        w('| %s | %d |' % (k, n))
    w('| (jsonl に wasm_trap case なし) | %d |' % len(no_trap_case))
    w('| 合計 | %d |' % (len(kind) + len(no_trap_case)))
    w('')

    un = [va for va, k in kind.items() if k == 'unreachable']
    w('## 2. unreachable (%d)' % len(un))
    w('')
    top = collections.Counter(frames(first[v]['wasm_detail'])[0] for v in un)
    chain = collections.Counter(tuple(frames(first[v]['wasm_detail'])[:5]) for v in un)
    thunk = sum(1 for v in un if any('signature' in f or 'thunk' in f for f in frames(first[v]['wasm_detail'])))
    w('- trap した最上位 frame: ' + ', '.join('`%s` × %d' % kv for kv in top.most_common()))
    w('- 上位 5 frame の連鎖 (trap 側 → 呼出元): ' + ', '.join('`%s` × %d' % (' < '.join(k), n) for k, n in chain.most_common(3)))
    w('- frame 名に signature / thunk を含むもの: **%d**' % thunk)
    callers = collections.Counter(frames(first[v]['wasm_detail'])[3] if len(frames(first[v]['wasm_detail'])) > 3 else None for v in un)
    w('- `function_412a60` の呼出元: ' + ', '.join('`%s` × %d' % kv for kv in callers.most_common()))
    wexit = sum(1 for v in un if 'ExitProcess' in call_names(first[v]['raw'], 'wasm'))
    nexit = sum(1 for v in un if 'ExitProcess' in call_names(first[v]['raw'], 'native'))
    w('- wasm 側 import 呼出列に `ExitProcess` を含む: %d / %d。native 側に含む: %d / %d' % (wexit, len(un), nexit, len(un)))
    pairs = collections.Counter((tuple(call_names(first[v]['raw'], 'native')[:2]), tuple(call_names(first[v]['raw'], 'wasm')[:2])) for v in un)
    w('- 先頭 2 import の (native → wasm) 上位:')
    for (a, b), n in pairs.most_common(5):
        w('  - %s → %s × %d' % (list(a), list(b), n))
    w('')

    oob = [va for va, k in kind.items() if k == 'oob']
    w('## 3. OOB (%d)' % len(oob))
    w('')
    top = collections.Counter(frames(first[v]['wasm_detail'])[0] for v in oob)
    w('- trap した最上位 frame の異なり数: %d。上位: ' % len(top) + ', '.join('`%s` × %d' % kv for kv in top.most_common(8)))
    tg = collections.Counter(tuple(t['tag'] for t in rows[v].get('tags', [])) for v in oob)
    w('- タグ組合せ上位: ' + ', '.join('`%s` × %d' % (','.join(k), n) for k, n in tg.most_common(5)))
    pat = collections.Counter(c.get('pattern') for v in oob for c in rows[v]['cases'] if c['outcome'] == 'wasm_trap')
    w('- OOB が出た case の pattern 内訳 (case 単位): ' + ', '.join('%s=%d' % kv for kv in sorted(pat.items())))
    w('')

    hang = [va for va, k in kind.items() if k == 'hang']
    w('## 4. hang (%d) / その他' % len(hang))
    w('')
    tg = collections.Counter(tuple(t['tag'] for t in rows[v].get('tags', [])) for v in hang)
    w('- hang のタグ組合せ: ' + ', '.join('`%s` × %d' % (','.join(k), n) for k, n in tg.most_common(5)))
    for k in ('badjson', 'indirect_sig', 'arith', 'stack_overflow', 'other'):
        vs = [v for v, kk in kind.items() if kk == k]
        if vs:
            ex = collections.Counter((first[v].get('wasm_detail') or '')[:40] for v in vs)
            w('- %s (%d): ' % (k, len(vs)) + ', '.join('`%s` × %d' % kv for kv in ex.most_common(4)))
    w('')

    w('## 5. verdicts.tsv と jsonl の差')
    w('')
    j = [va for va, r in rows.items() if any(t['tag'] == 'wasm_trap' for t in r.get('tags', []))]
    w('- jsonl で wasm_trap タグを持つ関数: %d。TSV 側 %d との共通: %d (TSV のみ %d / jsonl のみ %d)。' % (
        len(j), len(target), len(set(j) & set(target)), len(set(target) - set(j)), len(set(j) - set(target))))
    diff = sum(1 for v in rows if v in tsv and rows[v]['verdict'] != tsv[v][2])
    w('- verdict が TSV と jsonl で食い違う関数: %d / %d (batch 再走間の揺らぎ・§6.2 の負荷依存と整合)。' % (diff, len(rows)))
    print('\n'.join(out))


if __name__ == '__main__':
    main()
