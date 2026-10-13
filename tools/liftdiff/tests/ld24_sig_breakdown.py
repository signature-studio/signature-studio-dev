#!/usr/bin/env python3
"""LD-24 (#976): m11 closure の unsupported_sig 件数の署名内訳を IR の define/declare 行から再計算する。

  python3 tools/liftdiff/tests/ld24_sig_breakdown.py [boot_final3.ll] > work/ld24_sig_breakdown.md

入力: results/m11_closure_verdicts.tsv の unexec_reason == unsupported_sig の行 (va / name)
      と IR (既定 tools/m11/work/boot_final3.ll。`bash tools/m11/m11_e2e.sh --full` で生成)。
出力: 署名形ごとの件数・関数ごとの va→ret/params・子 issue の振り分け (#1193 / #1194)。
振り分け: ret=i128 → #1193 (戻り値)。それ以外で params に i128 または %tagPOINT → #1194 (引数)。
"""
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from ldlib import irtool  # noqa: E402

TSV = os.path.join(ROOT, 'results/m11_closure_verdicts.tsv')
IR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '../m11/work/boot_final3.ll')


def bucket(sig):
    if sig['ret'] == 'i128':
        return '#1193'
    if 'i128' in sig['params'] or any('tagPOINT' in p or p == '{i32,i32}' for p in sig['params']):
        return '#1194'
    return 'その他'


def main():
    targets = []
    with open(TSV) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            c = line.rstrip('\n').split('\t')
            if len(c) >= 6 and c[5] == 'unsupported_sig':
                targets.append((c[0], c[1]))
    sigs = irtool.parse_sigs(IR)
    shape = collections.Counter()
    rows = []
    missing = []
    for va, name in targets:
        sig = sigs.get(name)
        if sig is None:
            missing.append((va, name))
            continue
        params = ','.join(sig['params']) or 'なし'
        shape[(sig['ret'], params)] += 1
        rows.append((va, name, sig['ret'], params, bucket(sig)))

    print(f'<!-- 自動生成: python3 tools/liftdiff/tests/ld24_sig_breakdown.py {IR} -->')
    print(f'# LD-24 署名内訳 (入力: {len(targets)} 件 / IR で解決 {len(rows)} 件 / 未解決 {len(missing)} 件)')
    print()
    print('| 署名形 (ret / params) | 関数数 | 振り分け |')
    print('|---|---|---|')
    for (ret, params), n in sorted(shape.items(), key=lambda kv: (-kv[1], kv[0])):
        b = collections.Counter(r[4] for r in rows if r[2] == ret and r[3] == params)
        print(f'| ret=`{ret}`, params=`{params}` | {n} | {"/".join(sorted(b))} |')
    print()
    print('| va | name | ret | params | 振り分け |')
    print('|---|---|---|---|---|')
    for va, name, ret, params, b in rows:
        print(f'| {va} | {name} | {ret} | {params} | {b} |')
    if missing:
        print()
        print('IR に define/declare が無い関数 (解決不能):')
        for va, name in missing:
            print(f'- {va} {name}')
    print()
    by = collections.Counter(r[4] for r in rows)
    print(f'集計: #1193 = {by["#1193"]} / #1194 = {by["#1194"]} / その他 = {by["その他"]}')
    return 0 if not missing else 1


if __name__ == '__main__':
    sys.exit(main())
