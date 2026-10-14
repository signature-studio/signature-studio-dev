#!/usr/bin/env python3
"""spill37_1169.py — #1169 (LD-37): spill 宛 CELL_COLLAPSED site の判定対応表。

集合の定義は audit_lsf_ssa.py の --json 出力 (修復前) で frame=true かつ cell.verdict=CELL_COLLAPSED の site。
その全 site を results/spill178_1161.tsv (#1161 の全数分類) の判定と site 単位で対応付け、判定表を出す。
引数の 2 本目 (修復後の audit JSON) を渡すと、修復前後で同じ集合になることも確かめる。

使い方: python3 spill37_1169.py OUT.tsv AUDIT.json [AUDIT_AFTER.json]
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPILL = os.path.join(HERE, 'results', 'spill178_1161.tsv')


def rows(path):
    with open(path) as f:
        next(f)
        for line in f:
            yield line.rstrip('\n').split('\t')


def frame_collapsed(audit_path):
    audit = json.load(open(audit_path))
    out = set()
    for va, v in audit['functions'].items():
        for s in v['sites']:
            c = s.get('cell')
            if c and c.get('verdict') == 'CELL_COLLAPSED' and s.get('frame'):
                out.add((va, s['addr']))
    return out


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    out_path, audits = sys.argv[1], sys.argv[2:]
    sites = frame_collapsed(audits[0])
    for a in audits[1:]:
        if frame_collapsed(a) != sites:
            print('FAIL: 修復後の audit の spill 宛 CELL_COLLAPSED 集合が修復前と不一致 (%s)' % a, file=sys.stderr)
            sys.exit(1)
    spill = {(r[0], r[1]): r for r in rows(SPILL)}
    missing = sorted(k for k in sites if k not in spill)
    if missing:
        print('FAIL: spill178 に無い site %d 件: %s' % (len(missing), missing[:5]), file=sys.stderr)
        sys.exit(1)
    body = sorted(spill[k] for k in sites)
    lines = ['fn\tsite\tsource\tverdict\tstatus\toracle\ttext']
    cnt = collections.Counter()
    fns = collections.defaultdict(set)
    for r in body:
        lines.append('\t'.join(r[:7]))
        cnt[(r[3], r[4])] += 1
        fns[(r[3], r[4])].add(r[0])
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('spill 宛 CELL_COLLAPSED site %d / 関数 %d (audit %d 本で一致)'
          % (len(sites), len({k[0] for k in sites}), len(audits)))
    for k, n in sorted(cnt.items(), key=lambda x: -x[1]):
        print('%s %s: site %d / 関数 %d' % (k[0], k[1], n, len(fns[k])))


if __name__ == '__main__':
    main()
