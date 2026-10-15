"""同じ batch を 2 回実行した jsonl の関数単位の揺れを切り分ける (LD-157 / #3423)。

使い方: python3 tests/ld157_batch_diff.py <run1.jsonl> <run2.jsonl> [--chunk 400] [--shards 12]
batch の割り当ては liftdiff.py cmd_batch に従う (chunk ごとに part を part[k::shards] へ割り、shard 内は順に実行)。
shard 内の wasm instance は関数をまたいで持ち越されるため、先に実行された関数の差分は後続の関数へ伝わり得る。
出力: 判定の件数、判定が変わった関数、case 単位で変わった関数。各関数に、同じ shard で先行する関数に差分が
あったか (chain) と、自分の case で wasm の打切り/hang/crash が変わったか (own) を付ける。
"""
import argparse, collections, json, sys


def load(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def sig(r):
    return [(c['pattern'], c['outcome'], c.get('native_status'), c.get('wasm_status')) for c in r['cases']]


def wasm_to(r):
    return [c['pattern'] for c in r['cases'] if c.get('wasm_status') in ('timeout', 'hang', 'crash')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run1')
    ap.add_argument('run2')
    ap.add_argument('--chunk', type=int, default=400)
    ap.add_argument('--shards', type=int, default=12)
    a = ap.parse_args()
    A, B = load(a.run1), load(a.run2)
    if [r['function']['va'] for r in A] != [r['function']['va'] for r in B]:
        sys.exit('function list differs between the two runs')
    print('functions %d' % len(A))
    for name, R in (('run1', A), ('run2', B)):
        c = collections.Counter(r['verdict'] for r in R)
        print('%s verdict match %d / mismatch %d / unexec %d' % (name, c['match'], c['mismatch'], c['unexec']))
        print('%s wasm timeout/hang/crash cases %d (functions %d)' % (
            name, sum(len(wasm_to(r)) for r in R), sum(1 for r in R if wasm_to(r))))
    vchg = [(a_['function']['va'], a_['verdict'], b_['verdict']) for a_, b_ in zip(A, B) if a_['verdict'] != b_['verdict']]
    print('verdict changes %d: %s' % (len(vchg), ', '.join('%s %s->%s' % x for x in vchg) or '-'))
    diff = [i for i in range(len(A)) if sig(A[i]) != sig(B[i])]
    print('case-level changes %d functions' % len(diff))
    for i in diff:
        ca = (i // a.chunk) * a.chunk
        pos = i - ca
        mates = list(range(ca + pos % a.shards, ca + pos, a.shards))
        chain = [A[j]['function']['va'] for j in mates if sig(A[j]) != sig(B[j])]
        own = (wasm_to(A[i]), wasm_to(B[i]))
        print('- %s chunk %d shard %d pos %d | verdict %s->%s | chain(先行の差分) %s | own wasm-to r1 %s r2 %s' % (
            A[i]['function']['va'], i // a.chunk, pos % a.shards, pos, A[i]['verdict'], B[i]['verdict'],
            ','.join(chain) or '-', own[0] or '-', own[1] or '-'))


if __name__ == '__main__':
    main()
