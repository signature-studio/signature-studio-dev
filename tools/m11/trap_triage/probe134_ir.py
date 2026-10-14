#!/usr/bin/env python3
# #134 計測専用 (M11_PROBE_134=1 のとき m11_build.sh から呼ぶ): function_8c5eb0 の本体に 3 点の観測呼出しを入れる.
#   f=0: 入口の arg2 (dl と bit 7)  f=1: 410320 の戻り (guard の R)  f=2: 8c67a0(R) の戻り (list)
# 既定 off では呼ばない (m11_build.sh が M11_PROBE_134=1 のときだけ通す)。冪等: 既に入っていれば何もしない。
# 使い方: python3 trap_triage/probe134_ir.py work/boot_final3.ll   (in-place)
import re
import sys

src = sys.argv[1]
s = open(src).read()
if 'm11_p134_put' in s:
    print('[probe134_ir] already patched: ' + src)
    sys.exit(0)
m = re.search(r'^define [^\n]*@function_8c5eb0\(.*?^}\n', s, re.S | re.M)
if not m:
    sys.exit('[probe134_ir] function_8c5eb0 が無い: ' + src)
body = m.group(0)
anchors = [
    (r'^  %1 = trunc i64 %arg2 to i8\n', '  call void @m11_p134_put(i32 0, i64 %arg2)\n'),
    (r'^  %5 = call i64 @function_410320\(i64 %0, i8 %4\)\n', '  call void @m11_p134_put(i32 1, i64 %5)\n'),
    (r'^  %6 = call i64 @function_8c67a0\(i64 %stack_var_8\.0\.reload\)\n', '  call void @m11_p134_put(i32 2, i64 %6)\n'),
]
for pat, ins in anchors:
    n = len(re.findall(pat, body, re.M))
    if n != 1:
        sys.exit('[probe134_ir] anchor は 1 回だけのはず (%d 回): %s' % (n, pat))
    body = re.sub(pat, lambda mm, ins=ins: mm.group(0) + ins, body, flags=re.M)
s = s[:m.start()] + body + s[m.end():]
s = s.rstrip('\n') + '\ndeclare void @m11_p134_put(i32, i64)\n'
open(src, 'w').write(s)
print('[probe134_ir] patched 3 sites in function_8c5eb0: ' + src)
