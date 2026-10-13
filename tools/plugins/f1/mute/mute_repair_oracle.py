#!/usr/bin/env python3
"""試験専用の oracle 修復: lift 済み function_6baaf0 (Mute 2 Eff_Render) の脱落した IPP 呼出 2 件を手で書き戻す。
     mode1 (0x6bab3e):          ippsZero_8u(dst, Length << 3)
     無効 かつ src != dst (0x6bab7d): ippsCopy_64s(src, dst, Length)
   fade 分岐 (mode0/mode2 → function_5df490 の float 引数 xmm3 + スタック) は直さない (ARG pass の領分)。
   lift pass ではない。 usage: mute_repair_oracle.py <in.final.ll> <out.final.ll> <in_simd.c> <out_simd.c>
   MU_NEGCTL=1: 書き戻す Zero の長さを 4 byte 短くする陰性対照。
"""
import os, sys
src, dst, csrc, cdst = sys.argv[1:5]
s = open(src).read()
neg = '4' if os.environ.get('MU_NEGCTL') == '1' else '0'
a_old = """  %ce2n11_function_6baaf0 = inttoptr i64 7378312 to ptr
  %19 = load i64, ptr %ce2n11_function_6baaf0, align 8
"""
a_new = """  %f1_n = and i64 %arg4, 4294967295
  %f1_l8 = shl i64 %f1_n, 3
  %f1_l9 = and i64 %f1_l8, 4294967295
  %f1_z = icmp eq i64 %f1_l9, 0
  %f1_d = select i1 %f1_z, i64 0, i64 """ + neg + """
  %f1_l = sub i64 %f1_l9, %f1_d
  %19 = call i64 @f1_ipps_zero_8u(i64 %arg3, i64 %f1_l)
"""
b_old = """  %ce5n11_function_6baaf0 = inttoptr i64 7381768 to ptr
  %29 = load i64, ptr %ce5n11_function_6baaf0, align 8
"""
b_new = """  %f1_cn = and i64 %arg4, 4294967295
  %29 = call i64 @f1_ipps_copy_64s(i64 %arg2, i64 %arg3, i64 %f1_cn)
"""
assert a_old in s and b_old in s, 'function_6baaf0 の脱落ブロックの形が想定と違う'
s = s.replace(a_old, a_new, 1).replace(b_old, b_new, 1)
s += "\ndeclare i64 @f1_ipps_zero_8u(i64, i64)\ndeclare i64 @f1_ipps_copy_64s(i64, i64, i64)\n"
open(dst, 'w').write(s)
c = open(csrc).read()
c += """
#include <string.h>
/* dsp_ippv2!ippsZero_8u(pDst, len) / ippsCopy_64s(pSrc, pDst, len) の意味を持つ試験用 stub。 LVA = VA-0x400000 なので pointer はそのまま線形アドレス。 */
long long f1_ipps_zero_8u(long long dst, long long len) { memset((void*)(unsigned)dst, 0, (unsigned)len); return 0; }
long long f1_ipps_copy_64s(long long src, long long dst, long long len) { memmove((void*)(unsigned)dst, (void*)(unsigned)src, (size_t)(unsigned)len * 8); return 0; }
"""
open(cdst, 'w').write(c)
