#!/usr/bin/env python3
"""同一入力 (RTL 帯 VA 集合) の liftdiff batch を n 回走らせた結果の min-max と run 間変動を出す (#129 REPORT §7)。

usage: rtl_runs_summary.py <m11_run1.jsonl,run2,...> <flelift_run1.jsonl,run2,...>
"""
import collections, json, sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from rtl_compare import load, norm


def counts(d):
    c = collections.Counter(norm(v) for v, _ in d.values())
    return [c['match'], c['mismatch'], c['unexec']]


def reasons(d):
    return collections.Counter(r.get('unexec_reason') for v, r in d.values() if norm(v) == 'unexec')


def rng(vals):
    return str(vals[0]) if min(vals) == max(vals) else '%d–%d' % (min(vals), max(vals))


def main():
    runs = {k: [load(p) for p in sys.argv[i].split(',')] for k, i in (('m11', 1), ('x64c', 2))}
    for k, ds in runs.items():
        cs = [counts(d) for d in ds]
        print('%s n=%d 一致/不一致/実行不能: ' % (k, len(ds)) + ' / '.join(rng([c[i] for c in cs]) for i in range(3)),
              ' 各 run: ' + ', '.join('%d/%d/%d' % tuple(c) for c in cs))
        vas = sorted(set.intersection(*[set(d) for d in ds]))
        moved = [va for va in vas if len({norm(d[va][0]) for d in ds}) > 1]
        print('  run 間で verdict が動いた関数: %d / %d (VA 共通)' % (len(moved), len(vas)))
        rs = [reasons(d) for d in ds]
        for key in sorted(set().union(*rs), key=str):
            print('  unexec_reason %-22s %s' % (key, rng([r[key] for r in rs])))
    m, x = runs['m11'], runs['x64c']
    for i in range(min(len(m), len(x))):
        common = sorted(set(m[i]) & set(x[i]))
        both = [a for a in common if norm(m[i][a][0]) != 'unexec' and norm(x[i][a][0]) != 'unexec']
        t = collections.Counter((norm(m[i][a][0]), norm(x[i][a][0])) for a in both)
        print('run%d 両 route 採点可 %d: m11 不一致 %d → x64c 不一致 %d, 不一致→一致 %d / 一致→不一致 %d' % (
            i + 1, len(both), sum(v for (a, b), v in t.items() if a == 'mismatch'),
            sum(v for (a, b), v in t.items() if b == 'mismatch'), t[('mismatch', 'match')], t[('match', 'mismatch')]))


if __name__ == '__main__':
    main()
