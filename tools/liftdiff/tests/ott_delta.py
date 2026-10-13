#!/usr/bin/env python3
"""OTT 旧 chain の 2 つの batch.jsonl を関数単位で突き合わせ、集計差分と判定変化を列挙する (LD-16 / #825)。

使い方: python3 tests/ott_delta.py <旧 batch.jsonl> <新 batch.jsonl>
数え方 (check_ott.py と同一): 件数 = 関数 (212) の verdict 別件数。D1〜D6 は tag 別の関数数 (複数タグの重複あり)。
D4_D5 は C 定義 (sig.c) かつ mismatch の関数数。tag 変化は両側の tags の集合差。
"""
import collections
import json
import sys


def load(path):
    out = {}
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            out[r['function']['name']] = r
    return out


def tags(r):
    return sorted(t['tag'] for t in r.get('tags', []))


def summary(d):
    cnt = collections.Counter(r['verdict'] for r in d.values())
    return f"match {cnt['match']} / mismatch {cnt['mismatch']} / unexec {cnt['unexec']} (functions {len(d)})"


def main():
    a, b = load(sys.argv[1]), load(sys.argv[2])
    if set(a) != set(b):
        sys.exit('function set differs')
    print('old:', summary(a))
    print('new:', summary(b))
    trans = collections.Counter()
    rows = []
    for k in sorted(a):
        ra, rb = a[k], b[k]
        if ra['verdict'] == rb['verdict'] and tags(ra) == tags(rb) and ra.get('unexec_reason') == rb.get('unexec_reason'):
            continue
        trans[(ra['verdict'], rb['verdict'])] += 1
        rows.append((k, ra, rb))
    print('verdict transitions (old -> new):', dict(trans))
    print('changed functions:', len(rows))
    for k, ra, rb in rows:
        ta, tb = set(tags(ra)), set(tags(rb))
        print(f"{k} {ra['verdict']} -> {rb['verdict']} | unexec {ra.get('unexec_reason')} -> {rb.get('unexec_reason')}"
              f" | tags- {sorted(ta - tb)} tags+ {sorted(tb - ta)} | C {(ra['function'].get('sig') or {}).get('c')}")


if __name__ == '__main__':
    main()
