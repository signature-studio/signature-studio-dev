#!/usr/bin/env python3
"""lift の欠落監査: ranges (全 .pdata 関数 / 閉包) と final.ll の `function_<VA>` define を突き合わせる。
  missing      = ranges の開始 VA に対応する define が無い range 数 (bytes はその range 長の合計)
  missing_ref  = そのうち final.ll 内で参照 (call 等) されている数 = link 時に未解決になる
  extra_inside = range の開始 VA でない define のうち、いずれかの range の内部に入るもの (RetDec が range 内部に切り出した関数)
usage: engine_defs.py <ranges.txt> <final.ll>   → stdout 1 行: missing,missing_bytes,missing_ref,extra_inside,function_defines
final.ll が無い場合は -1,-1,-1,-1,-1 (judge は -1 を不合格とする)。
"""
import os, re, sys
if not os.path.exists(sys.argv[2]):
    print('-1,-1,-1,-1,-1')
    sys.exit(0)
rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(sys.argv[1]).read().strip().split(',')]
ll = open(sys.argv[2]).read()
defs = {int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M)}
refs = {int(x, 16) for x in re.findall(r'@function_([0-9a-f]+)\b', ll)}
starts = {a for a, _ in rg}
miss = [(a, e) for a, e in rg if a not in defs]
extra = [x for x in defs - starts if any(a <= x <= e for a, e in rg)]
print('%d,%d,%d,%d,%d' % (len(miss), sum(e - a + 1 for a, e in miss), sum(1 for a, _ in miss if a in refs), len(extra), len(defs)))
