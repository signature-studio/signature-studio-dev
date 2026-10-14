#!/usr/bin/env python3
"""engine lift の欠落監査: ranges.txt (全 .pdata 関数) と final.ll の `function_<VA>` define を突き合わせる。
  missing      = ranges の開始 VA に対応する define が無い range 数 (bytes はその range 長の合計)
  missing_ref  = そのうち final.ll 内で参照 (call 等) されている数 = link 時に未解決になる
  extra_inside = range の開始 VA でない define のうち、いずれかの range の内部に入るもの (RetDec が range 内部に切り出した関数)
usage: engine_defs.py <outdir>   → stdout 1 行: missing,missing_bytes,missing_ref,extra_inside,function_defines
"""
import os, re, sys
d = sys.argv[1]
rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(os.path.join(d, 'ranges.txt')).read().strip().split(',')]
ll = open(os.path.join(d, 'e.final.ll')).read()
defs = {int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M)}
refs = {int(x, 16) for x in re.findall(r'@function_([0-9a-f]+)\b', ll)}
starts = {a for a, _ in rg}
# RetDec が名前付き (function: NAME at VA) で出した関数は define @NAME で存在する (偽陽性の除外)
names = {int(a, 16): n for n, a in re.findall(r'^; function: (\S+) at 0x([0-9a-f]+) --', open(os.path.join(d, 'e.drc.dsm')).read(), re.M)}
named = {a for a, n in names.items() if re.search(r'^define [^@]*@%s\(' % re.escape(n), ll, re.M)}
miss = [(a, e) for a, e in rg if a not in defs and a not in named]
extra = [x for x in defs - starts if any(a <= x <= e for a, e in rg)]
print('%d,%d,%d,%d,%d' % (len(miss), sum(e - a + 1 for a, e in miss), sum(1 for a, _ in miss if a in refs), len(extra), len(defs)))
