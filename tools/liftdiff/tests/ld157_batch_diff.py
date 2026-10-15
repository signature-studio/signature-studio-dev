"""同じ batch を 2 回実行した jsonl の関数単位の揺れを切り分ける (LD-157 / #3423)。

使い方: python3 tests/ld157_batch_diff.py <run1.jsonl> <run2.jsonl> [--chunk 400] [--shards 12]
batch の割り当ては liftdiff.py cmd_batch に従う (400 件 chunk ごとに run_functions を呼び、chunk 内の関数を
part[k::shards] へ割り、shard 内は順に実行)。shard 内の wasm instance は関数をまたいで持ち越されるため、
先に実行された関数の差分は後続の関数へ伝わり得る。
出力: 判定の件数、判定が変わった関数、case 単位で変わった関数。wasm 側の打切りは 3 種に分ける:
  vm     = wasm の vm timeout (wasm_status=timeout)
  noresp = wasm の無応答 (wasm_status=hang/crash)
  native = native が timeout/hang/crash で wasm を実行していない case (wasm_status は合成の hang)
各関数に、同じ shard で先行する関数に差分があったか (chain) と、自分の case の 3 種の内訳 (own) を付ける。
chain は同じ shard の先行 case との同時性を示す相関で、因果ではない。
"""
import argparse, collections, json, sys

KINDS = (('vm', 'wasm vm timeout (status=timeout)'),
         ('noresp', 'wasm 無応答 (hang/crash)'),
         ('native', 'native timeout/hang/crash (wasm 未実行)'))


def load(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def sig(r):
    return [(c['pattern'], c['outcome'], c.get('native_status'), c.get('wasm_status')) for c in r['cases']]


def kind(c):
    if c.get('native_status') in ('timeout', 'hang', 'crash'):
        return 'native'
    if c.get('wasm_status') == 'timeout':
        return 'vm'
    if c.get('wasm_status') in ('hang', 'crash'):
        return 'noresp'
    return None


def own(r, k):
    return [c['pattern'] for c in r['cases'] if kind(c) == k]


def own_str(r):
    s = ['%s[%s]' % (k, ','.join(own(r, k))) for k, _ in KINDS if own(r, k)]
    return ' '.join(s) or '-'


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
        for k, label in KINDS:
            print('%s %s cases %d (functions %d)' % (
                name, label, sum(len(own(r, k)) for r in R), sum(1 for r in R if own(r, k))))
    vchg = [(a_['function']['va'], a_['verdict'], b_['verdict']) for a_, b_ in zip(A, B) if a_['verdict'] != b_['verdict']]
    print('verdict changes %d: %s' % (len(vchg), ', '.join('%s %s->%s' % x for x in vchg) or '-'))
    diff = [i for i in range(len(A)) if sig(A[i]) != sig(B[i])]
    print('case-level changes %d functions' % len(diff))
    for i in diff:
        ca = (i // a.chunk) * a.chunk
        pos = i - ca
        mates = list(range(ca + pos % a.shards, ca + pos, a.shards))
        chain = [A[j]['function']['va'] for j in mates if sig(A[j]) != sig(B[j])]
        print('- %s chunk %d shard %d pos %d | verdict %s->%s | chain(同 shard の先行に差分) %s | own r1 %s | r2 %s' % (
            A[i]['function']['va'], i // a.chunk, pos % a.shards, pos, A[i]['verdict'], B[i]['verdict'],
            ','.join(chain) or '-', own_str(A[i]), own_str(B[i])))


if __name__ == '__main__':
    main()
