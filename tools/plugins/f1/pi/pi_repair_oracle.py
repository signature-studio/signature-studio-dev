#!/usr/bin/env python3
"""試験専用の oracle 修復: lift 済み function_6ba930 (Phase Inverter Eff_Render) に、脱落した
   `if (src != dst) (*ippsMove_8u)(src, dst, Length << 3)` を手で書き戻す。
   これは lift pass ではない (indirect call 復元は tools/icall の binary pre-rewrite 路線が正)。
   目的: 「この経路の silent 差分は脱落 call 1 件だけ」を示す ablation (修復前 234/240 fail → 修復後 0)。
   usage: pi_repair_oracle.py <in.final.ll> <out.final.ll> <in_simd.c> <out_simd.c>
"""
import os, sys
src, dst, csrc, cdst = sys.argv[1:5]
s = open(src).read()
head = "define i64 @function_6ba930(i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4) local_unnamed_addr {\ndec_label_pc_6ba930:\n  %rax.0.reg2mem = alloca i64\n"
assert head in s, 'function_6ba930 の先頭形が想定と違う'
new = head + """  %f1_same = icmp eq i64 %arg2, %arg3
  br i1 %f1_same, label %f1_cont, label %f1_copy

f1_copy:
  %f1_n = and i64 %arg4, 4294967295
  %f1_l8 = shl i64 %f1_n, 3
  %f1_l9 = and i64 %f1_l8, 4294967295
  %f1_z = icmp eq i64 %f1_l9, 0
  %f1_d = select i1 %f1_z, i64 0, i64 NEGDELTA
  %f1_l = sub i64 %f1_l9, %f1_d
  %f1_r = call i64 @f1_ipps_move_8u(i64 %arg2, i64 %arg3, i64 %f1_l)
  br label %f1_cont

f1_cont:
"""
# 陰性対照 (PI_NEGCTL=1): コピー長を 4 byte 短くする → 試験が copy 経路の 1 word 欠落を検出できること
new = new.replace('NEGDELTA', '4' if os.environ.get('PI_NEGCTL') == '1' else '0')
s = s.replace(head, new, 1)
s += "\ndeclare i64 @f1_ipps_move_8u(i64, i64, i64)\n"
open(dst, 'w').write(s)
c = open(csrc).read()
c += """
#include <string.h>
/* dsp_ippv2!ippsMove_8u(pSrc, pDst, len) の意味 (memmove) を持つ試験用 stub。 VA 窓は PE と同じ LVA = VA-0x400000 なので pointer はそのまま線形アドレス。 */
long long f1_ipps_move_8u(long long src, long long dst, long long len) { memmove((void*)(unsigned)dst, (void*)(unsigned)src, (unsigned)len); return 0; }
"""
open(cdst, 'w').write(c)
