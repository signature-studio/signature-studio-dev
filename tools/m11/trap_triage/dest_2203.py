#!/usr/bin/env python3
"""dest_2203.py (#2203): OFF (lift 版 function_413060) の IR に dest/len と j=12 の 412c20 呼出し前後の観測を入れる (計測専用・読取りのみ).
  usage: dest_2203.py <src.ll> <out.ll>
  観測関数は m11_ov.c の m11_pd2118_{in,pre,post} (M11_PRINT_DEST_2118=1 のときだけ定義) を呼ぶ。ON (C 版) と同じ書式を出す。
  挿入は function_413060 の本体内だけ。値・分岐は変えない。"""
import sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
head = 'define weak i64 @function_413060(i64 %arg1, ptr %arg2, i64 %arg3) local_unnamed_addr {\n'
assert s.count(head) == 1, 'function_413060 の定義が一意でない'
i = s.index(head)
j = s.index('\n}\n', i) + 3
body = s[i:j]
lab = 'dec_label_pc_413060:\n'
assert body.count(lab) == 1
body = body.replace(lab, lab + '  call void @m11_pd2118_in(i64 %arg1, i64 %arg3)\n', 1)
call = '  %4 = call i64 @function_412c20(i64 %3)\n'
assert body.count(call) == 1, '412c20 呼出しが一意でない'
body = body.replace(call, '  call void @m11_pd2118_pre(i64 %3)\n' + call + '  call void @m11_pd2118_post()\n', 1)
decl = ('declare void @m11_pd2118_in(i64, i64)\n'
        'declare void @m11_pd2118_pre(i64)\n'
        'declare void @m11_pd2118_post()\n')
open(dst, 'w').write(s[:i] + decl + body + s[j:])
print('[dest_2203] wrote', dst)
