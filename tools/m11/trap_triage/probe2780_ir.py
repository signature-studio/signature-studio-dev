#!/usr/bin/env python3
# #2780 計測専用 (M11_PROBE_2780=1 のとき m11_build.sh から呼ぶ): function_4473f0 の各反復の値を m11_p2780_put で記録する.
#   tag=0: i (rbx, 1..7)  tag=1: ecx (= i+5)  tag=2: esi (0x92492493 乗算で求めた ecx % 7)
#   tag=3: 1 回目の function_447df0 後の slot ([rbp+0x48])  tag=4: 2 回目の function_447df0 後の slot ([rbp+0x40])
#   tag=5: 4473f0 の入口 arg2 (rdx)  tag=6: 4473f0 の入口 arg1 (ecx)
#   tag=7/8: 1 回目の function_4133f0 の dest (rcx) と呼出し直前の *dest (旧値)
#   tag=9/10: 2 回目の function_4133f0 の dest と呼出し直前の *dest (旧値)
#   注: function_4133f0 は m11_ov.c の C 版 (System._UStrAsg) で置き換わる (IR 版は使われない) ので、IR 側の呼出し直前で読む
# 既定 off では呼ばない (m11_build.sh が M11_PROBE_2780=1 のときだけ通す)。冪等: 既に入っていれば何もしない。
# 使い方: python3 trap_triage/probe2780_ir.py work/boot_final3.ll   (in-place)
import re
import sys

src = sys.argv[1]
s = open(src).read()
if 'm11_p2780_put' in s:
    print('[probe2780_ir] already patched: ' + src)
    sys.exit(0)


def patch(fn, anchors):
    m = re.search(r'^define [^\n]*@' + fn + r'\(.*?^}\n', s, re.S | re.M)
    if not m:
        sys.exit('[probe2780_ir] %s が無い: %s' % (fn, src))
    body = m.group(0)
    for pat, ins in anchors:
        n = len(re.findall(pat, body, re.M))
        if n != 1:
            sys.exit('[probe2780_ir] anchor は 1 回だけのはず (%d 回): %s' % (n, pat))
        body = re.sub(pat, lambda mm, ins=ins: mm.group(0) + ins, body, flags=re.M)
    return m, body


m, body = patch('function_4473f0', [
    (r'^  store i64 0, ptr %stack_var_-48, align 8\n',
     '  call void @m11_p2780_put(i32 5, i64 %arg2)\n'
     '  %p2780.a1 = zext i32 %arg1 to i64\n'
     '  call void @m11_p2780_put(i32 6, i64 %p2780.a1)\n'),
    (r'^  %12 = add i32 %11, %2\n',
     '  call void @m11_p2780_put(i32 0, i64 %rbx.0.reload)\n'
     '  %p2780.ecx = zext i32 %2 to i64\n'
     '  call void @m11_p2780_put(i32 1, i64 %p2780.ecx)\n'
     '  %p2780.esi = zext i32 %12 to i64\n'
     '  call void @m11_p2780_put(i32 2, i64 %p2780.esi)\n'),
    (r'^  %17 = load i64, ptr %stack_var_-48, align 8\n',
     '  call void @m11_p2780_put(i32 3, i64 %17)\n'
     '  %p2780.d1 = inttoptr i64 %rdi.0.reload to ptr\n'
     '  %p2780.o1 = load i64, ptr %p2780.d1, align 8\n'
     '  call void @m11_p2780_put(i32 7, i64 %rdi.0.reload)\n'
     '  call void @m11_p2780_put(i32 8, i64 %p2780.o1)\n'),
    (r'^  %22 = load i64, ptr %stack_var_-56, align 8\n',
     '  call void @m11_p2780_put(i32 4, i64 %22)\n'
     '  %p2780.d2 = inttoptr i64 %21 to ptr\n'
     '  %p2780.o2 = load i64, ptr %p2780.d2, align 8\n'
     '  call void @m11_p2780_put(i32 9, i64 %21)\n'
     '  call void @m11_p2780_put(i32 10, i64 %p2780.o2)\n'),
])
s = s[:m.start()] + body + s[m.end():]
s = s.rstrip('\n') + '\ndeclare void @m11_p2780_put(i32, i64)\n'
open(src, 'w').write(s)
print('[probe2780_ir] patched function_4473f0: ' + src)
