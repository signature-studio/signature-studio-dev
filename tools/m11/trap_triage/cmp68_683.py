#!/usr/bin/env python3
"""cmp68_683.py A.jsonl B.jsonl FN68.txt : #307 (LD-7) の 68 関数 (最初の wasm_trap が 414ad0 の OOB) について,
414ad0 IR 修復の A/B を関数単位で突合する (#683)。A = IR 無変更 (ネガコン), B = function_414ad0 を機械語どおりに修復した IR。

定義 (tests/oob_414ad0.py と同じ): 関数の「最初の wasm_trap case」の wasm_detail が
`memory access out of bounds @ ld_wasm.wasm.function_414ad0` で始まるもの = OOB414。
数え方: 関数数 (VA 単位, FN68 の行数)。verdict = jsonl の verdict (match = 一致)。
"""
import collections
import json
import sys

NAME = 'function_414ad0'


def load(path):
    out = {}
    for line in open(path):
        r = json.loads(line)
        out[r['function']['va'].lower()] = r
    return out


def first_trap(r):
    cs = [c for c in r['cases'] if c['outcome'] == 'wasm_trap']
    if not cs:
        return None, 0
    return (cs[0].get('wasm_detail') or ''), len(cs)


def oob414(r):
    d, _ = first_trap(r)
    return d is not None and d.startswith('memory access out of bounds @ ld_wasm.wasm.%s' % NAME)


def main():
    a = load(sys.argv[1])
    b = load(sys.argv[2])
    vas = [l.split()[0].lower() for l in open(sys.argv[3]) if l.strip()]
    ca = collections.Counter()
    cb = collections.Counter()
    trans = collections.Counter()
    rows = []
    for va in vas:
        ra, rb = a.get(va), b.get(va)
        if ra is None or rb is None:
            sys.exit('VA %s が jsonl に無い (A=%s B=%s)' % (va, ra is not None, rb is not None))
        oa, ob = oob414(ra), oob414(rb)
        ca['verdict:' + ra['verdict']] += 1
        cb['verdict:' + rb['verdict']] += 1
        ca['oob414'] += oa
        cb['oob414'] += ob
        trans[('oob414' if oa else 'other', 'oob414' if ob else 'other', ra['verdict'], rb['verdict'])] += 1
        if ra['verdict'] == 'match' and rb['verdict'] != 'match':
            ca['regress_match_to_nonmatch'] += 1
        ta, na = first_trap(ra)
        tb, nb = first_trap(rb)
        rows.append((va, ra['verdict'], rb['verdict'], oa, ob, na, nb, (tb or '')[:90]))
    print('関数数 %d (FN68)' % len(vas))
    for k in sorted(ca):
        print('A(IR 無変更) %-28s %d' % (k, ca[k]))
    for k in sorted(cb):
        print('B(414ad0 修復) %-26s %d' % (k, cb[k]))
    print('遷移 (最初の wasm_trap が OOB414 か / verdict): A -> B')
    for k, v in sorted(trans.items()):
        print('  %-7s -> %-7s  verdict %-9s -> %-9s  %d' % (k[0], k[1], k[2], k[3], v))
    print('関数別 (va, verdict A, verdict B, OOB414 A, OOB414 B, wasm_trap 件数 A, B, B の最初の trap detail)')
    for r in rows:
        print('  %s %s %s %s %s %d %d %s' % r)


if __name__ == '__main__':
    main()
