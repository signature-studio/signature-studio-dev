#!/usr/bin/env python3
"""slot653660_exp.py (#3083): function_653660 の末尾 call function_412e40(&-24, 2) に関する IR 実験 (probe を入れない)。
  usage: slot653660_exp.py <zero32|split> <in.ll> <out.ll>
  zero32: 653660 の入口で stack_var_-32 (wasm frame+128) を 0 埋めする。
  split : 412e40(&-24, 2) を 412e40(&-24, 1) + 412e40(&-16, 1) に分ける。
  どちらも IR を直接 compile する (probe_entry.sh と同じ手順)。REPORT_1463.md §10 参照。"""
import re, sys

mode, src_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(src_path).read()
m = re.search(r'^define [^\n]*@function_653660\(.*?(?=^define )', src, re.M | re.S)
body = m.group(0)
if mode == 'zero32':
    old = '  store i64 0, ptr %stack_var_-24, align 8\n'
    new = old + '  store i64 0, ptr %stack_var_-32, align 8\n'
elif mode == 'split':
    old = '  %94 = call i64 @function_412e40(i64 %__m11c_1300, i64 2)\n'
    new = ('  %94 = call i64 @function_412e40(i64 %__m11c_1300, i64 1)\n'
           '  %__m11c_1301 = ptrtoint ptr %stack_var_-16 to i64\n'
           '  %__m11c_1302 = call i64 @function_412e40(i64 %__m11c_1301, i64 1)\n')
else:
    sys.exit('mode must be zero32 or split')
assert body.count(old) == 1, body.count(old)
open(out_path, 'w').write(src[:m.start()] + body.replace(old, new, 1) + src[m.end():])
print('wrote', out_path, 'mode', mode)
