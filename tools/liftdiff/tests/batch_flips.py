#!/usr/bin/env python3
"""2 本の liftdiff batch.jsonl を関数の va で突き合わせ、case outcome と verdict の変化を数える (WIN-34 / #3557)。
使い方: python3 tests/batch_flips.py <基準の batch.jsonl> <新の batch.jsonl>
"""
import json, sys


def load(path):
    d = {}
    for line in open(path):
        r = json.loads(line)
        d[r['function']['va']] = r
    return d


def main():
    a, b = load(sys.argv[1]), load(sys.argv[2])
    common = sorted(set(a) & set(b))
    outcome_flips = verdict_flips = 0
    for k in common:
        if [c.get('outcome') for c in a[k]['cases']] != [c.get('outcome') for c in b[k]['cases']]:
            outcome_flips += 1
        if a[k]['verdict'] != b[k]['verdict']:
            verdict_flips += 1
    print('functions: %d (base %d / new %d)' % (len(common), len(a), len(b)))
    print('case outcome flips (functions): %d' % outcome_flips)
    print('verdict flips (functions): %d' % verdict_flips)


if __name__ == '__main__':
    main()
