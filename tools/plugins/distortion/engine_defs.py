#!/usr/bin/env python3
"""engine lift の欠落監査: ranges.txt (全 .pdata 関数) と final.ll の `function_<VA>` define を突き合わせる。
  missing      = ranges の開始 VA に対応する define が無い range 数 (bytes はその range 長の合計)
  missing_ref  = そのうち final.ll 内で参照 (call 等) されている数 = link 時に未解決になる
  extra_inside = range の開始 VA でない define のうち、いずれかの range の内部に入るもの (RetDec が range 内部に切り出した関数)
usage: engine_defs.py <outdir>                  (<outdir>/ranges.txt と <outdir>/e.final.ll)
       engine_defs.py --ranges R.txt --ll F.ll [--also-ranges R2.txt]
         (殻の閉包: work/closure/block*.ranges.txt と work/batch/<block>/p.final.ll)
         --also-ranges: icall 書換え (batch_lift の既定 PLUG_ICALL=1) の range (work/batch/<block>/p.icall.map.json.ranges)。 開始 VA の define 名は元の VA に戻る一方、
           RetDec が range 内部で切り出した追加の define は書換え後 PE のアドレスで名前が付くので、extra_inside は両方の range で判定する (PLG-F6-2 #545)
   → stdout 1 行: missing,missing_bytes,missing_ref,extra_inside,function_defines
"""
import os, re, sys
also = None
if sys.argv[1] == '--ranges':
    rpath, lpath = sys.argv[2], sys.argv[4]
    if len(sys.argv) > 5 and sys.argv[5] == '--also-ranges':
        also = sys.argv[6]
else:
    rpath, lpath = os.path.join(sys.argv[1], 'ranges.txt'), os.path.join(sys.argv[1], 'e.final.ll')
rg = [tuple(int(x, 16) for x in r.split('-')) for r in open(rpath).read().strip().split(',')]
ll = open(lpath).read()
defs = {int(x, 16) for x in re.findall(r'^define [^@]*@function_([0-9a-f]+)\b', ll, re.M)}
# RetDec は PE のエントリ関数を `@entry_point` と名付ける (function_<VA> ではない)。 先頭ラベル `dec_label_pc_<VA>:` の VA で数える
# (MSVC の _DllMainCRTStartup 相当 61 B。 PLG-F6-2 #545 で、missing_define=1 の正体が名前だけの違いだったと判明)
defs |= {int(x, 16) for x in re.findall(r'^define [^@]*@entry_point\([^\n]*\n(?:dec_label_pc_)([0-9a-f]+):', ll, re.M)}
refs = {int(x, 16) for x in re.findall(r'@function_([0-9a-f]+)\b', ll)}
starts = {a for a, _ in rg}
miss = [(a, e) for a, e in rg if a not in defs]
rg2 = rg + ([tuple(int(x, 16) for x in r.split('-')) for r in open(also).read().strip().split(',')] if also else [])
extra = [x for x in defs - starts if any(a <= x <= e for a, e in rg2)]
print('%d,%d,%d,%d,%d' % (len(miss), sum(e - a + 1 for a, e in miss), sum(1 for a, _ in miss if a in refs), len(extra), len(defs)))
