#!/usr/bin/env python3
"""engine lift の欠落監査: ranges.txt (全 .pdata 関数) と final.ll の `function_<VA>` define を突き合わせる。
  missing      = ranges の開始 VA に対応する define が無い range 数 (bytes はその range 長の合計)
  missing_ref  = そのうち final.ll 内で参照 (call 等) されている数 = link 時に未解決になる
  extra_inside = range の開始 VA でない define のうち、いずれかの range の内部に入るもの (RetDec が range 内部に切り出した関数)
usage: engine_defs.py <outdir>                  (<outdir>/ranges.txt と <outdir>/e.final.ll)
       engine_defs.py --ranges R.txt --ll F.ll  (殻の閉包: work/closure/block*.ranges.txt と work/batch/<block>/p.final.ll)
   → stdout 1 行: missing,missing_bytes,missing_ref,extra_inside,function_defines
"""
import os, re, sys
if sys.argv[1] == '--ranges':
    rpath, lpath = sys.argv[2], sys.argv[4]
else:
    rpath, lpath = os.path.join(sys.argv[1], 'ranges.txt'), os.path.join(sys.argv[1], 'e.final.ll')
rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(rpath).read().strip().split(',')]
ll = open(lpath).read()
defs = {int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M)}
refs = {int(x, 16) for x in re.findall(r'@function_([0-9a-f]+)\b', ll)}
starts = {a for a, _ in rg}
miss = [(a, e) for a, e in rg if a not in defs]
extra = [x for x in defs - starts if any(a <= x <= e for a, e in rg)]
print('%d,%d,%d,%d,%d' % (len(miss), sum(e - a + 1 for a, e in miss), sum(1 for a, _ in miss if a in refs), len(extra), len(defs)))
