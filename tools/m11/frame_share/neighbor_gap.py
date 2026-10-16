#!/usr/bin/env python3
"""ir_truncated 組の拡幅余地を判定する (#5588 / SHX-T51)。

REPORT_SHX-T48.md §4 の表 (unmatched 53 site・18 組) を読み、親 IR の同じ関数内で
X (= 機械語の rbp 位置) より上にある次の stack_var との間隔 (gap) を求める。
alloca 拡幅 (R8) は次の stack_var までしか広げられないため、E <= gap なら拡幅で覆える。

使い方 (repo 直下・work/ は gitignore のため素材から生成した IR が要る):
  python3 tools/m11/frame_share/neighbor_gap.py --ir tools/m11/work/boot_final3.ll --report tools/m11/REPORT_SHX-T48.md
"""
import argparse
import re


def parse_pairs(report):
    pairs = []
    for line in open(report, encoding='utf-8'):
        m = re.match(r'\| `(function_[0-9a-f]+)` \| `(function_[0-9a-f]+)` \| \d+ \| `stack_var_(-?\d+)` \| -?\d+ \| \d+ \| (\d+) \|', line)
        if m:
            pairs.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4))))
    return pairs


def function_ranges(lines):
    rng = {}
    cur = None
    for i, line in enumerate(lines):
        m = re.match(r'define [^@]*@(function_[0-9a-f]+)\(', line)
        if m:
            cur = m.group(1)
            rng[cur] = [i, None]
        elif cur and line.startswith('}'):
            rng[cur][1] = i
            cur = None
    return rng


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ir', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()
    pairs = parse_pairs(args.report)
    lines = open(args.ir, encoding='utf-8', errors='replace').read().split('\n')
    rng = function_ranges(lines)
    print('組: %d' % len(pairs))
    for parent, callee, X, E in pairs:
        if parent not in rng:
            print('%s -> %s: 親が IR に無い' % (parent, callee))
            continue
        a, b = rng[parent]
        svs = set()
        for line in lines[a:b]:
            for m in re.finditer(r'%stack_var_(-?\d+) = alloca', line):
                svs.add(int(m.group(1)))
        above = [s for s in svs if s > X]
        if above:
            nxt = min(above)
            gap = nxt - X
            verdict = 'R8 で覆える' if E <= gap else 'R8 では覆えない (次の stack_var が間隔を狭める)'
            print('%s -> %s: X=%d E=%d 次の stack_var=%d gap=%d -> %s' % (parent, callee, X, E, nxt, gap, verdict))
        else:
            print('%s -> %s: X=%d E=%d 次の stack_var 無し (上限は親の frame 境界で決まる。未測定)' % (parent, callee, X, E))


if __name__ == '__main__':
    main()
