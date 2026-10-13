#!/usr/bin/env python3
"""x64c 一致→不一致 退行 7 件の verdict を複数 run で並べる (REPORT §9-2)。

使い方:
  python3 rerun_regression7.py --out results/x64c_regression7_rerun.tsv \
      NAME=PATH [NAME=PATH ...]

各 PATH は liftdiff batch の出力 jsonl (1 行 1 関数)。並べる対象 VA は固定の 7 件。
生の jsonl は tools/liftdiff/work/ (gitignore) に置き、commit しない。
"""
import argparse
import json

VAS = ['0x4090e0', '0x41cd70', '0x42d830', '0x44a590', '0x4511d0', '0x412020', '0x455650']


def load(path):
    rows = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            d = json.loads(line)
            rows[d['function']['va']] = d['verdict']
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('runs', nargs='+', metavar='NAME=PATH')
    a = ap.parse_args()
    names, data = [], {}
    for spec in a.runs:
        name, _, path = spec.partition('=')
        names.append(name)
        data[name] = load(path)
    lines = ['#va\t' + '\t'.join(names)]
    for va in VAS:
        lines.append(va + '\t' + '\t'.join(data[n].get(va, '-') for n in names))
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
