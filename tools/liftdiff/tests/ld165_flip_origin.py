"""同じ入力の batch JSONL を 2 本比べ、case 単位の揺れと shard ごとの起点を出す (LD-165 / #3585)。

使い方: python3 tests/ld165_flip_origin.py A.jsonl B.jsonl [--shards 12] [--chunk 400]
出力:
  - 判定 (verdict) の変化の件数
  - case 単位の揺れ (outcome・native_status・wasm_status のどれかが違う case)。timing の有無と elapsed を併記
  - 各 chunk・各 shard で最初に A と B が違った関数 (起点)。batch は chunk ごとに vas[i::shards] を shard に割り、
    shard 内は順に走らせるため、起点より前の関数は両 run で同じ順に走っている (shard の順序は cmd_batch と同じ)
判定ロジックは見ず、batch JSONL の cases だけを突き合わせる。
"""
import argparse
import json


def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def case_key(c):
    return c['pattern'] + ('#%s' % c['fvm_arg'] if 'fvm_arg' in c else '')


def status_of(c):
    return (c.get('outcome'), c.get('native_status'), c.get('wasm_status'))


def timing_of(c):
    t = c.get('timing')
    if not t:
        return '-'
    n, w = t.get('native', {}), t.get('wasm', {})
    return 'n=%s/%s w=%s/%s' % (n.get('cause', '-'), n.get('elapsed_s'), w.get('cause', '-'), w.get('elapsed_s'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--shards', type=int, default=12)
    ap.add_argument('--chunk', type=int, default=400)
    args = ap.parse_args()
    A, B = load(args.a), load(args.b)
    assert [r['function']['va'] for r in A] == [r['function']['va'] for r in B], 'function order differs'
    verdict_changes = [(a['function']['va'], a['verdict'], b['verdict']) for a, b in zip(A, B) if a['verdict'] != b['verdict']]
    print('verdict changes: %d %s' % (len(verdict_changes), verdict_changes))
    flips = []
    for j, (a, b) in enumerate(zip(A, B)):
        ca = {case_key(c): c for c in a.get('cases', [])}
        cb = {case_key(c): c for c in b.get('cases', [])}
        for k in sorted(set(ca) | set(cb)):
            x, y = ca.get(k), cb.get(k)
            if x is None or y is None or status_of(x) != status_of(y):
                flips.append((j, a['function']['va'], k, x, y))
    print('case-level flips: %d cases in %d functions' % (len(flips), len({f[1] for f in flips})))
    for j, va, k, x, y in flips:
        sa = '%s/%s/%s' % status_of(x) if x else '-'
        sb = '%s/%s/%s' % status_of(y) if y else '-'
        print('  idx %d %s %s  A=%s [%s]  B=%s [%s]' % (j, va, k, sa, timing_of(x) if x else '-', sb, timing_of(y) if y else '-'))
    print('shard origin (first function where A and B differ, per chunk and shard):')
    for c0 in range(0, len(A), args.chunk):
        for sh in range(args.shards):
            idx = [j for j in range(c0, min(c0 + args.chunk, len(A))) if (j - c0) % args.shards == sh]
            first = None
            for j in idx:
                ca = {case_key(c): status_of(c) for c in A[j].get('cases', [])}
                cb = {case_key(c): status_of(c) for c in B[j].get('cases', [])}
                if ca != cb or A[j]['verdict'] != B[j]['verdict']:
                    first = j
                    break
            if first is not None:
                ca = {case_key(c): status_of(c) for c in A[first].get('cases', [])}
                cb = {case_key(c): status_of(c) for c in B[first].get('cases', [])}
                d = sorted(k for k in set(ca) | set(cb) if ca.get(k) != cb.get(k))
                print('  chunk %d shard %2d idx %d %s verdict %s/%s cases %s' % (c0, sh, first, A[first]['function']['va'], A[first]['verdict'], B[first]['verdict'], d[:4]))


if __name__ == '__main__':
    main()
