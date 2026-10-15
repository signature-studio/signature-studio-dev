"""同じ入力の batch を 2 回実行したときの case 単位の揺れを数える (LD-182 / #3881)。

使い方: python3 tests/ld182_casediff.py A.jsonl B.jsonl [--tsv out.tsv]
出力: 両 run に共通の case (関数 va・pattern・fvm_arg で一致) のうち、(outcome, native_status, wasm_status) が
      異なる case の件数、その遷移の種類 (wasm の status 対)、wasm 側の実測秒。
判定ロジック・timing の値は見ず、batch JSONL の cases だけを突き合わせる (ld154_repeat.py と同じ読み方)。
"""
import collections
import json
import sys


def load(path):
    d = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                d[r['function']['va']] = r
    return d


def case_key(c):
    return c['pattern'] + ('#%s' % c['fvm_arg'] if 'fvm_arg' in c else '')


def sig(c):
    return (c['outcome'], c.get('native_status'), c.get('wasm_status'))


def wasm_elapsed(c):
    t = c.get('timing') or c.get('refine_timing')
    if not t or 'wasm' not in t:
        return None
    return t['wasm'].get('elapsed_s')


def main(argv):
    tsv = None
    if '--tsv' in argv:
        i = argv.index('--tsv')
        tsv = argv[i + 1]
        del argv[i:i + 2]
    a, b = load(argv[0]), load(argv[1])
    common = 0
    diff_rows = []
    kinds = collections.Counter()
    for va in sorted(set(a) & set(b)):
        ca = {case_key(c): c for c in a[va].get('cases', [])}
        cb = {case_key(c): c for c in b[va].get('cases', [])}
        for k in sorted(set(ca) & set(cb)):
            common += 1
            x, y = ca[k], cb[k]
            if sig(x) == sig(y):
                continue
            kind = '%s -> %s' % (x.get('wasm_status'), y.get('wasm_status'))
            kinds[kind] += 1
            diff_rows.append((va, k, sig(x), sig(y), wasm_elapsed(x), wasm_elapsed(y)))
    print('== A=%s  B=%s' % (argv[0], argv[1]))
    print('  共通 case %d / 判定 (outcome/native/wasm) の差 %d case / 差のある関数 %d' % (
        common, len(diff_rows), len({r[0] for r in diff_rows})))
    for kind, n in kinds.most_common():
        print('      wasm %-32s %4d' % (kind, n))
    for r in diff_rows:
        ea = '%.3f' % r[4] if r[4] is not None else '-'
        eb = '%.3f' % r[5] if r[5] is not None else '-'
        print('      %s %-14s A=%s B=%s  wasm_s %s -> %s' % (r[0], r[1], '/'.join(map(str, r[2])), '/'.join(map(str, r[3])), ea, eb))
    if tsv:
        with open(tsv, 'w') as f:
            f.write('va\tcase\tA\tB\tA_wasm_s\tB_wasm_s\n')
            for r in diff_rows:
                f.write('%s\t%s\t%s\t%s\t%s\t%s\n' % (r[0], r[1], '/'.join(map(str, r[2])), '/'.join(map(str, r[3])), r[4], r[5]))


if __name__ == '__main__':
    main(sys.argv[1:])
