#!/usr/bin/env python3
"""k80_hand_bodies.py — 修復後 IR の一部 kernel を機械語どおりの本体に差し替える (#2182 / P0c-17)。

  python3 k80_hand_bodies.py <in.ll> <out.ll> [--report <json>]

RetDec 由来の x87 鎖 (fld/fadd/fmul/fstp の stack 参照) が機械語とずれる kernel、または
x87 の拡張精度 (80-bit 中間値) を f64 に落とすと丸めが変わる kernel は、関数単位で
機械語どおりの本体を書く。関数のシグネチャ (引数順) は変えない。
差し替え対象は BODIES の関数本体のみ。BODIES が呼ぶ declare の補完を除き、他の行は変えない。
global の初期値 (@global_var_6fffb0 の PE 値など) は k80_pe_globals.py が PE の .data から入れる (#3281)。

差し替えの根拠 (REPORT_APPENDIX_H §19):
  0x5dfff0  : 引数 a(xmm2)/b(xmm3) の参照が入れ替わる + (1±a)*b を 80-bit で丸める
  (0x5e12c0 は #3281 残件 B で k80_ucomi_br.py の一般 pass に置換し、本体を外した)
  0x5dee20  : out[2k+j] += in[k] (f32 加算)。RetDec の fstp 参照先がずれる
  0x5e0300  : out[k] = f32((in[2k]+in[2k+1]) * c)。80-bit 中間値
  0x5e0350  : out[2k+j] = f32((in[..]+in[..]) * c)。80-bit 中間値
"""
import json
import re
import sys

BODIES = {
    'function_5dfff0': '''define i64 @function_5dfff0(i64 %arg1, i64 %arg2, i64 %in.xmm2.bits, i64 %in.xmm3.bits) local_unnamed_addr {
dec_label_pc_5dfff0:
  %a32 = trunc i64 %in.xmm2.bits to i32
  %b32 = trunc i64 %in.xmm3.bits to i32
  %a = bitcast i32 %a32 to float
  %b = bitcast i32 %b32 to float
  %ae = fpext float %a to x86_fp80
  %be = fpext float %b to x86_fp80
  %p0 = inttoptr i64 %arg1 to ptr
  %p1 = inttoptr i64 %arg2 to ptr
  %neg = icmp slt i32 %a32, 0
  br i1 %neg, label %dec_label_pc_5e000d, label %dec_label_pc_5e001b
dec_label_pc_5e000d:
  store i32 %b32, ptr %p0, align 4
  %s0 = fadd x86_fp80 0xK3FFF8000000000000000, %ae
  %m0 = fmul x86_fp80 %s0, %be
  %r0 = fptrunc x86_fp80 %m0 to float
  store float %r0, ptr %p1, align 4
  br label %dec_label_pc_5e0027
dec_label_pc_5e001b:
  store i32 %b32, ptr %p1, align 4
  %s1 = fsub x86_fp80 0xK3FFF8000000000000000, %ae
  %m1 = fmul x86_fp80 %s1, %be
  %r1 = fptrunc x86_fp80 %m1 to float
  store float %r1, ptr %p0, align 4
  br label %dec_label_pc_5e0027
dec_label_pc_5e0027:
  ret i64 0
}
''',
    'function_5dee20': '''define i64 @function_5dee20(i64 %arg1, i64 %arg2, i64 %arg3) local_unnamed_addr {
dec_label_pc_5dee20:
  br label %dec_label_pc_5dee2b
dec_label_pc_5dee2b:
  %k = phi i64 [ 0, %dec_label_pc_5dee20 ], [ %k1, %dec_label_pc_5dee2b ]
  %xa = mul i64 %k, 4
  %xp = add i64 %arg1, %xa
  %xptr = inttoptr i64 %xp to float*
  %x = load float, float* %xptr, align 4
  %oa = mul i64 %k, 8
  %op = add i64 %arg2, %oa
  %o0 = inttoptr i64 %op to float*
  %op1 = add i64 %op, 4
  %o1 = inttoptr i64 %op1 to float*
  %v0 = load float, float* %o0, align 4
  %s0 = fadd float %v0, %x
  store float %s0, float* %o0, align 4
  %v1 = load float, float* %o1, align 4
  %s1 = fadd float %v1, %x
  store float %s1, float* %o1, align 4
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %arg3
  br i1 %c, label %dec_label_pc_5dee2b, label %dec_label_pc_5dee48
dec_label_pc_5dee48:
  ret i64 0
}
''',
    'function_5e0300': '''define i64 @function_5e0300(i64 %arg1, i64 %arg2, i64 %arg3) local_unnamed_addr {
dec_label_pc_5e0300:
  %c32 = load float, float* @global_var_6fc200, align 4
  %ce = fpext float %c32 to x86_fp80
  br label %dec_label_pc_5e0311
dec_label_pc_5e0311:
  %k = phi i64 [ 0, %dec_label_pc_5e0300 ], [ %k1, %dec_label_pc_5e0311 ]
  %ka = mul i64 %k, 8
  %xp = add i64 %arg1, %ka
  %x0p = inttoptr i64 %xp to float*
  %x0 = load float, float* %x0p, align 4
  %xp1 = add i64 %xp, 4
  %x1p = inttoptr i64 %xp1 to float*
  %x1 = load float, float* %x1p, align 4
  %a = fpext float %x0 to x86_fp80
  %b = fpext float %x1 to x86_fp80
  %s = fadd x86_fp80 %a, %b
  %m = fmul x86_fp80 %s, %ce
  %r = fptrunc x86_fp80 %m to float
  %ko = mul i64 %k, 4
  %op = add i64 %arg2, %ko
  %opp = inttoptr i64 %op to float*
  store float %r, float* %opp, align 4
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %arg3
  br i1 %c, label %dec_label_pc_5e0311, label %dec_label_pc_5e0325
dec_label_pc_5e0325:
  ret i64 0
}
''',
    'function_5dee50': '''define i64 @function_5dee50(i64 %arg1, i64 %arg2, i64 %arg3) local_unnamed_addr {
dec_label_pc_5dee50:
  br label %dec_label_pc_5dee5b
dec_label_pc_5dee5b:
  %k = phi i64 [ 0, %dec_label_pc_5dee50 ], [ %k1, %dec_label_pc_5dee5b ]
  %xa = mul i64 %k, 8
  %xp = add i64 %arg1, %xa
  %x0p = inttoptr i64 %xp to float*
  %x0 = load float, float* %x0p, align 4
  %xp4 = add i64 %xp, 4
  %x1p = inttoptr i64 %xp4 to float*
  %x1 = load float, float* %x1p, align 4
  %op = add i64 %arg2, %xa
  %o0 = inttoptr i64 %op to float*
  %v0 = load float, float* %o0, align 4
  %s0 = fadd float %x0, %v0
  store float %s0, float* %o0, align 4
  %op4 = add i64 %op, 4
  %o1 = inttoptr i64 %op4 to float*
  %v1 = load float, float* %o1, align 4
  %s1 = fadd float %x1, %v1
  store float %s1, float* %o1, align 4
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %arg3
  br i1 %c, label %dec_label_pc_5dee5b, label %dec_label_pc_5dee7f
dec_label_pc_5dee7f:
  ret i64 0
}
''',
    'function_5de620': '''define i64 @function_5de620(i64 %arg1, i64 %arg2, i64 %arg3, i64 %in.xmm3.bits) local_unnamed_addr {
dec_label_pc_5de620:
  %t3 = trunc i64 %in.xmm3.bits to i32
  %bf = bitcast i32 %t3 to float
  %be = fpext float %bf to x86_fp80
  br label %dec_label_pc_5de63b
dec_label_pc_5de63b:
  %k = phi i64 [ 0, %dec_label_pc_5de620 ], [ %k1, %dec_label_pc_5de63b ]
  %ia = mul i64 %k, 4
  %ip = add i64 %arg1, %ia
  %ipt = inttoptr i64 %ip to float*
  %x = load float, float* %ipt, align 4
  %xe = fpext float %x to x86_fp80
  %m = fmul x86_fp80 %xe, %be
  %v = call x86_fp80 @llvm.rint.f80(x86_fp80 %m)
  %lo = fcmp oge x86_fp80 %v, 0xKC00E8000000000000000
  %hi = fcmp ole x86_fp80 %v, 0xK400DFFFE000000000000
  %ok = and i1 %lo, %hi
  %vs = select i1 %ok, x86_fp80 %v, x86_fp80 0xK00000000000000000000
  %iv = fptosi x86_fp80 %vs to i32
  %t = trunc i32 %iv to i16
  %r = select i1 %ok, i16 %t, i16 -32768
  %oa = mul i64 %k, 2
  %op = add i64 %arg2, %oa
  %opt = inttoptr i64 %op to ptr
  store i16 %r, ptr %opt, align 2
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %arg3
  br i1 %c, label %dec_label_pc_5de63b, label %dec_label_pc_5de64b
dec_label_pc_5de64b:
  ret i64 0
}
''',
    'function_5dedb0': '''define i64 @function_5dedb0(i64 %arg1, i64 %arg2, i64 %arg3, float %arg4, i64 %in.xmm3.bits) local_unnamed_addr {
dec_label_pc_5dedb0:
  %t3 = trunc i64 %in.xmm3.bits to i32
  %bf = bitcast i32 %t3 to float
  %be = fpext float %bf to x86_fp80
  %se = fpext float %arg4 to x86_fp80
  br label %dec_label_pc_5dedce
dec_label_pc_5dedce:
  %k = phi i64 [ 0, %dec_label_pc_5dedb0 ], [ %k1, %dec_label_pc_5dedce ]
  %sc = phi x86_fp80 [ %be, %dec_label_pc_5dedb0 ], [ %sc1, %dec_label_pc_5dedce ]
  %ia = mul i64 %k, 4
  %ip = add i64 %arg1, %ia
  %ipt = inttoptr i64 %ip to float*
  %x = load float, float* %ipt, align 4
  %xe = fpext float %x to x86_fp80
  %p = fmul x86_fp80 %xe, %sc
  %op = add i64 %arg2, %ia
  %opt = inttoptr i64 %op to float*
  %ov = load float, float* %opt, align 4
  %oe = fpext float %ov to x86_fp80
  %s = fadd x86_fp80 %p, %oe
  %r = fptrunc x86_fp80 %s to float
  store float %r, float* %opt, align 4
  %sc1 = fadd x86_fp80 %sc, %se
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %arg3
  br i1 %c, label %dec_label_pc_5dedce, label %dec_label_pc_5dede3
dec_label_pc_5dede3:
  ret i64 0
}
''',
    'function_5dea40': '''define i64 @function_5dea40(i64 %arg1, i64 %arg2, i64 %arg3, float %arg4, i64 %in.xmm3.bits) local_unnamed_addr {
dec_label_pc_5dea40:
  %t3 = trunc i64 %in.xmm3.bits to i32
  %bf = bitcast i32 %t3 to float
  %be = fpext float %bf to x86_fp80
  %se = fpext float %arg4 to x86_fp80
  br label %dec_label_pc_5dea61
dec_label_pc_5dea61:
  %k = phi i64 [ 0, %dec_label_pc_5dea40 ], [ %k1, %dec_label_pc_5dea61 ]
  %sc = phi x86_fp80 [ %be, %dec_label_pc_5dea40 ], [ %sc1, %dec_label_pc_5dea61 ]
  %ia = mul i64 %k, 8
  %ip = add i64 %arg1, %ia
  %x0p = inttoptr i64 %ip to float*
  %x0 = load float, float* %x0p, align 4
  %ip4 = add i64 %ip, 4
  %x1p = inttoptr i64 %ip4 to float*
  %x1 = load float, float* %x1p, align 4
  %x0e = fpext float %x0 to x86_fp80
  %x1e = fpext float %x1 to x86_fp80
  %p0 = fmul x86_fp80 %x0e, %sc
  %p1 = fmul x86_fp80 %x1e, %sc
  %op = add i64 %arg2, %ia
  %o0p = inttoptr i64 %op to float*
  %o0 = load float, float* %o0p, align 4
  %o0e = fpext float %o0 to x86_fp80
  %s0 = fadd x86_fp80 %p0, %o0e
  %r0 = fptrunc x86_fp80 %s0 to float
  store float %r0, float* %o0p, align 4
  %op4 = add i64 %op, 4
  %o1p = inttoptr i64 %op4 to float*
  %o1 = load float, float* %o1p, align 4
  %o1e = fpext float %o1 to x86_fp80
  %s1 = fadd x86_fp80 %p1, %o1e
  %r1 = fptrunc x86_fp80 %s1 to float
  store float %r1, float* %o1p, align 4
  %sc1 = fadd x86_fp80 %sc, %se
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %arg3
  br i1 %c, label %dec_label_pc_5dea61, label %dec_label_pc_5dea8d
dec_label_pc_5dea8d:
  ret i64 0
}
''',
    'function_5dec40': '''define i64 @function_5dec40(i64 %arg1, i64 %arg2, i64 %arg3, i32 %arg4, float %arg5, float %arg6, i64 %in.xmm3.bits) local_unnamed_addr {
dec_label_pc_5dec40:
  %t3 = trunc i64 %in.xmm3.bits to i32
  %cf = bitcast i32 %t3 to float
  %ce = fpext float %cf to x86_fp80
  %ff = bitcast i32 %arg4 to float
  %fe = fpext float %ff to x86_fp80
  %ae = fpext float %arg5 to x86_fp80
  %be = fpext float %arg6 to x86_fp80
  br label %dec_label_pc_5dec6a
dec_label_pc_5dec6a:
  %k = phi i64 [ 0, %dec_label_pc_5dec40 ], [ %k1, %dec_label_pc_5dec6a ]
  %cs = phi x86_fp80 [ %ce, %dec_label_pc_5dec40 ], [ %cs1, %dec_label_pc_5dec6a ]
  %fs = phi x86_fp80 [ %fe, %dec_label_pc_5dec40 ], [ %fs1, %dec_label_pc_5dec6a ]
  %ia = mul i64 %k, 4
  %ip = add i64 %arg1, %ia
  %ipt = inttoptr i64 %ip to float*
  %x = load float, float* %ipt, align 4
  %xe = fpext float %x to x86_fp80
  %pc = fmul x86_fp80 %xe, %cs
  %pf = fmul x86_fp80 %xe, %fs
  %oa = mul i64 %k, 8
  %op = add i64 %arg2, %oa
  %o0p = inttoptr i64 %op to float*
  %o0 = load float, float* %o0p, align 4
  %o0e = fpext float %o0 to x86_fp80
  %s0 = fadd x86_fp80 %pc, %o0e
  %r0 = fptrunc x86_fp80 %s0 to float
  store float %r0, float* %o0p, align 4
  %op4 = add i64 %op, 4
  %o1p = inttoptr i64 %op4 to float*
  %o1 = load float, float* %o1p, align 4
  %o1e = fpext float %o1 to x86_fp80
  %s1 = fadd x86_fp80 %pf, %o1e
  %r1 = fptrunc x86_fp80 %s1 to float
  store float %r1, float* %o1p, align 4
  %cs1 = fadd x86_fp80 %cs, %ae
  %fs1 = fadd x86_fp80 %fs, %be
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %arg3
  br i1 %c, label %dec_label_pc_5dec6a, label %dec_label_pc_5decaf
dec_label_pc_5decaf:
  ret i64 0
}
''',
    'function_5dffc0': '''define i64 @function_5dffc0(i64 %arg1, i64 %arg2, i64 %in.xmm2.bits, i64 %in.xmm3.bits) local_unnamed_addr {
dec_label_pc_5dffc0:
  %a32 = trunc i64 %in.xmm2.bits to i32
  %b32 = trunc i64 %in.xmm3.bits to i32
  %a = bitcast i32 %a32 to float
  %b = bitcast i32 %b32 to float
  %ae = fpext float %a to x86_fp80
  %be = fpext float %b to x86_fp80
  %kd = load double, double* @global_var_6fc1f8, align 8
  %ke = fpext double %kd to x86_fp80
  %s = fadd x86_fp80 0xK3FFF8000000000000000, %ae
  %t = fmul x86_fp80 %s, %ke
  %at = call x86_fp80 @llvm.fabs.f80(x86_fp80 %t)
  %p0 = inttoptr i64 %arg1 to float*
  %p1 = inttoptr i64 %arg2 to float*
  %inr = fcmp olt x86_fp80 %at, 0xK403E8000000000000000
  br i1 %inr, label %dec_label_pc_5dffe7, label %dec_label_pc_5dffef
dec_label_pc_5dffe7:
  ; x87 fsincos は 66-bit π で引数縮約する (REPORT_APPENDIX_H §22)。k·π/2 を 2 分割で引き、sin/cos を r に適用する
  %qf = fmul x86_fp80 %t, 0xK3FFEA2F9836E4E44152A
  %qr = call x86_fp80 @llvm.rint.f80(x86_fp80 %qf)
  %k = fptosi x86_fp80 %qr to i64
  %u1 = fmul x86_fp80 %qr, 0xK3FFFC90FDAA200000000
  %d1 = fsub x86_fp80 %t, %u1
  %u2 = fmul x86_fp80 %qr, 0xK3FDD85A308D300000000
  %r = fsub x86_fp80 %d1, %u2
  %sr = call x86_fp80 @llvm.sin.f80(x86_fp80 %r)
  %cr = call x86_fp80 @llvm.cos.f80(x86_fp80 %r)
  %q = and i64 %k, 3
  %qodd = and i64 %q, 1
  %even = icmp eq i64 %qodd, 0
  %sb = select i1 %even, x86_fp80 %sr, x86_fp80 %cr
  %cb = select i1 %even, x86_fp80 %cr, x86_fp80 %sr
  %sneg = icmp ugt i64 %q, 1
  %qm = sub i64 %q, 1
  %cneg = icmp ule i64 %qm, 1
  %sm = fmul x86_fp80 %sb, 0xKBFFF8000000000000000
  %sn = select i1 %sneg, x86_fp80 %sm, x86_fp80 %sb
  %cm = fmul x86_fp80 %cb, 0xKBFFF8000000000000000
  %cs = select i1 %cneg, x86_fp80 %cm, x86_fp80 %cb
  %c0 = fmul x86_fp80 %cs, %be
  %s0 = fmul x86_fp80 %sn, %be
  %f0 = fptrunc x86_fp80 %c0 to float
  store float %f0, float* %p0, align 4
  %f1 = fptrunc x86_fp80 %s0 to float
  store float %f1, float* %p1, align 4
  br label %dec_label_pc_5dfff8
dec_label_pc_5dffef:
  %o0 = fmul x86_fp80 %t, %be
  %g0 = fptrunc x86_fp80 %o0 to float
  store float %g0, float* %p0, align 4
  store float 0xFFF8000000000000, float* %p1, align 4
  br label %dec_label_pc_5dfff8
dec_label_pc_5dfff8:
  ret i64 0
}
''',
    'function_5e1490': '''define i64 @function_5e1490(i64 %arg1, i64 %arg2, i64 %arg3, i64 %arg4, i32 %arg5, i32 %arg6, i32 %arg7, i32 %arg8) local_unnamed_addr {
dec_label_pc_5e1490:
  %A = bitcast i32 %arg6 to float
  %X7 = bitcast i32 %arg7 to float
  %X8 = bitcast i32 %arg8 to float
  %k7 = fmul float %X7, 0x3F00000000000000
  %nf = sitofp i32 %arg5 to float
  %half = load float, float* @global_var_6fc200, align 4
  %c6 = fmul float %nf, %half
  %bp = fmul float %X8, %c6
  %Nq = sext i32 %arg5 to i64
  %n = trunc i64 %arg3 to i32
  %pos = icmp sgt i32 %n, 0
  %n64 = zext i32 %n to i64
  %tbase = inttoptr i64 %arg4 to i16*
  br i1 %pos, label %dec_label_pc_5e1507, label %dec_label_pc_5e1572
dec_label_pc_5e1507:
  %k = phi i64 [ 0, %dec_label_pc_5e1490 ], [ %k1, %dec_label_pc_5e1507 ]
  %ia = mul i64 %k, 4
  %ip = add i64 %arg1, %ia
  %xp = inttoptr i64 %ip to float*
  %x = load float, float* %xp, align 4
  %xb = fmul float %x, %bp
  %t = fadd float %xb, %c6
  %td = fpext float %t to double
  %rv = call double @llvm.rint.f64(double %td)
  %lt63 = fcmp olt double %rv, 0x43E0000000000000
  %ge0 = fcmp oge double %rv, 0.0
  %valid = and i1 %lt63, %ge0
  %safe = select i1 %valid, double %rv, double 0.0
  %idx0 = fptosi double %safe to i64
  %gtN = icmp sgt i64 %idx0, %Nq
  %idx1 = select i1 %gtN, i64 %Nq, i64 %idx0
  %idx = select i1 %valid, i64 %idx1, i64 0
  %tptr = getelementptr i16, i16* %tbase, i64 %idx
  %tv = load i16, i16* %tptr, align 2
  %tvs = sext i16 %tv to i32
  %fv = sitofp i32 %tvs to float
  %o = fmul float %fv, %k7
  %a = fmul float %x, %A
  %r = fadd float %o, %a
  %op = add i64 %arg2, %ia
  %opp = inttoptr i64 %op to float*
  store float %r, float* %opp, align 4
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %n64
  br i1 %c, label %dec_label_pc_5e1507, label %dec_label_pc_5e1572
dec_label_pc_5e1572:
  ret i64 0
}
''',
    'function_5df340': '''define i64 @function_5df340(i64 %arg1, i64 %arg2, i64 %arg3, i32 %arg4, i64 %in.xmm3.bits) local_unnamed_addr {
dec_label_pc_5df340:
  %dr = bitcast i32 %arg4 to float
  %t3 = trunc i64 %in.xmm3.bits to i32
  %B = bitcast i32 %t3 to float
  %d = fmul float %dr, 0x4010000000000000
  %L0 = fmul float %d, 0.0
  %L1 = fmul float %d, 0x3FD0000000000000
  %L2 = fmul float %d, 0x3FE0000000000000
  %L3 = fmul float %d, 0x3FE8000000000000
  %M0i = fadd float %B, %L0
  %M1i = fadd float %B, %L1
  %M2i = fadd float %B, %L2
  %M3i = fadd float %B, %L3
  %nb = lshr i64 %arg3, 4
  %rem = and i64 %arg3, 15
  %J4 = mul i64 %nb, 4
  %pos = icmp ne i64 %J4, 0
  br i1 %pos, label %dec_label_pc_5df3d9, label %dec_label_pc_5df41c
dec_label_pc_5df3d9:
  %J = phi i64 [ 0, %dec_label_pc_5df340 ], [ %J1, %dec_label_pc_5df3d9 ]
  %M0 = phi float [ %M0i, %dec_label_pc_5df340 ], [ %M0n, %dec_label_pc_5df3d9 ]
  %M1 = phi float [ %M1i, %dec_label_pc_5df340 ], [ %M1n, %dec_label_pc_5df3d9 ]
  %M2 = phi float [ %M2i, %dec_label_pc_5df340 ], [ %M2n, %dec_label_pc_5df3d9 ]
  %M3 = phi float [ %M3i, %dec_label_pc_5df340 ], [ %M3n, %dec_label_pc_5df3d9 ]
  %vb = mul i64 %J, 16
  %ip = add i64 %arg1, %vb
  %op = add i64 %arg2, %vb
  %ip0 = inttoptr i64 %ip to float*
  %x0 = load float, float* %ip0, align 4
  %y0 = fmul float %x0, %M0
  %op0 = inttoptr i64 %op to float*
  store float %y0, float* %op0, align 4
  %ip1 = add i64 %ip, 4
  %x1p = inttoptr i64 %ip1 to float*
  %x1 = load float, float* %x1p, align 4
  %y1 = fmul float %x1, %M1
  %op1a = add i64 %op, 4
  %op1 = inttoptr i64 %op1a to float*
  store float %y1, float* %op1, align 4
  %ip2 = add i64 %ip, 8
  %x2p = inttoptr i64 %ip2 to float*
  %x2 = load float, float* %x2p, align 4
  %y2 = fmul float %x2, %M2
  %op2a = add i64 %op, 8
  %op2 = inttoptr i64 %op2a to float*
  store float %y2, float* %op2, align 4
  %ip3 = add i64 %ip, 12
  %x3p = inttoptr i64 %ip3 to float*
  %x3 = load float, float* %x3p, align 4
  %y3 = fmul float %x3, %M3
  %op3a = add i64 %op, 12
  %op3 = inttoptr i64 %op3a to float*
  store float %y3, float* %op3, align 4
  %M0n = fadd float %M0, %d
  %M1n = fadd float %M1, %d
  %M2n = fadd float %M2, %d
  %M3n = fadd float %M3, %d
  %J1 = add i64 %J, 1
  %cj = icmp ult i64 %J1, %J4
  br i1 %cj, label %dec_label_pc_5df3d9, label %dec_label_pc_5df41c
dec_label_pc_5df41c:
  %tm = phi float [ %M0i, %dec_label_pc_5df340 ], [ %M0n, %dec_label_pc_5df3d9 ]
  %tb = mul i64 %nb, 64
  %tn = icmp ne i64 %rem, 0
  br i1 %tn, label %dec_label_pc_5df429, label %dec_label_pc_5df446
dec_label_pc_5df429:
  %t = phi i64 [ 0, %dec_label_pc_5df41c ], [ %t1, %dec_label_pc_5df429 ]
  %m = phi float [ %tm, %dec_label_pc_5df41c ], [ %mn, %dec_label_pc_5df429 ]
  %t4 = mul i64 %t, 4
  %toff = add i64 %tb, %t4
  %tip = add i64 %arg1, %toff
  %tipp = inttoptr i64 %tip to float*
  %tx = load float, float* %tipp, align 4
  %ty = fmul float %tx, %m
  %top = add i64 %arg2, %toff
  %toppp = inttoptr i64 %top to float*
  store float %ty, float* %toppp, align 4
  %mn = fadd float %m, %dr
  %t1 = add i64 %t, 1
  %ct = icmp ult i64 %t1, %rem
  br i1 %ct, label %dec_label_pc_5df429, label %dec_label_pc_5df446
dec_label_pc_5df446:
  ret i64 0
}
''',
    'function_5dfae0': '''define i64 @function_5dfae0(i64 %arg1, i64 %arg2, i64 %arg3) local_unnamed_addr {
dec_label_pc_5dfae0:
  %pp = inttoptr i64 %arg3 to float*
  %Pf = load float, float* %pp, align 4
  %qa = add i64 %arg3, 4
  %qpp = inttoptr i64 %qa to float*
  %Qf = load float, float* %qpp, align 4
  %ra = add i64 %arg3, 8
  %rpp = inttoptr i64 %ra to float*
  %Rf = load float, float* %rpp, align 4
  %Pe = fpext float %Pf to x86_fp80
  %Qe = fpext float %Qf to x86_fp80
  %Re = fpext float %Rf to x86_fp80
  %Tb = bitcast float %Pf to i32
  %cnt = trunc i64 %arg2 to i32
  %n64 = zext i32 %cnt to i64
  %pos = icmp sgt i32 %cnt, 0
  br i1 %pos, label %dec_label_pc_5dfafe, label %dec_label_pc_5dfb4b
dec_label_pc_5dfafe:
  %k = phi i64 [ 0, %dec_label_pc_5dfae0 ], [ %k1, %dec_label_pc_5dfb43 ]
  %ia = mul i64 %k, 4
  %ip = add i64 %arg1, %ia
  %xpt = inttoptr i64 %ip to i32*
  %xb = load i32, i32* %xpt, align 4
  %ab = and i32 %xb, 2147483647
  %gt = icmp sgt i32 %ab, %Tb
  br i1 %gt, label %dec_label_pc_5dfb0b, label %dec_label_pc_5dfb43
dec_label_pc_5dfb0b:
  %absf = bitcast i32 %ab to float
  %absE = fpext float %absf to x86_fp80
  %s1 = fsub x86_fp80 %Pe, %absE
  %s2 = fmul x86_fp80 %s1, %Re
  %s3 = fmul x86_fp80 %s2, 0xK3FFFB8AA3B295C17F0BC
  %E = call x86_fp80 @llvm.exp2.f80(x86_fp80 %s3)
  %om = fsub x86_fp80 0xK3FFF8000000000000000, %E
  %m = fmul x86_fp80 %om, %Qe
  %v = fadd x86_fp80 %m, %Pe
  %vf = fptrunc x86_fp80 %v to float
  %vb = bitcast float %vf to i32
  %sg = and i32 %xb, -2147483648
  %ob = or i32 %vb, %sg
  store i32 %ob, i32* %xpt, align 4
  br label %dec_label_pc_5dfb43
dec_label_pc_5dfb43:
  %k1 = add i64 %k, 1
  %c = icmp ult i64 %k1, %n64
  br i1 %c, label %dec_label_pc_5dfafe, label %dec_label_pc_5dfb4b
dec_label_pc_5dfb4b:
  ret i64 0
}
''',
    'function_5e0350': '''define i64 @function_5e0350(i64 %in.r8, i64 %in.rdx, i64 %in.rcx) local_unnamed_addr {
dec_label_pc_5e0350:
  %c32 = load float, float* @global_var_6fc200, align 4
  %ce = fpext float %c32 to x86_fp80
  br label %dec_label_pc_5e0356
dec_label_pc_5e0356:
  %n = phi i64 [ %in.r8, %dec_label_pc_5e0350 ], [ %n1, %dec_label_pc_5e0356 ]
  %pi = phi i64 [ %in.rcx, %dec_label_pc_5e0350 ], [ %pi1, %dec_label_pc_5e0356 ]
  %po = phi i64 [ %in.rdx, %dec_label_pc_5e0350 ], [ %po1, %dec_label_pc_5e0356 ]
  %x0p = inttoptr i64 %pi to float*
  %x0 = load float, float* %x0p, align 4
  %pi8 = add i64 %pi, 8
  %y0p = inttoptr i64 %pi8 to float*
  %y0 = load float, float* %y0p, align 4
  %a0 = fpext float %x0 to x86_fp80
  %b0 = fpext float %y0 to x86_fp80
  %s0 = fadd x86_fp80 %a0, %b0
  %m0 = fmul x86_fp80 %s0, %ce
  %r0 = fptrunc x86_fp80 %m0 to float
  %o0p = inttoptr i64 %po to float*
  store float %r0, float* %o0p, align 4
  %pi4 = add i64 %pi, 4
  %x1p = inttoptr i64 %pi4 to float*
  %x1 = load float, float* %x1p, align 4
  %pi12 = add i64 %pi, 12
  %y1p = inttoptr i64 %pi12 to float*
  %y1 = load float, float* %y1p, align 4
  %a1 = fpext float %x1 to x86_fp80
  %b1 = fpext float %y1 to x86_fp80
  %s1 = fadd x86_fp80 %a1, %b1
  %m1 = fmul x86_fp80 %s1, %ce
  %r1 = fptrunc x86_fp80 %m1 to float
  %po4 = add i64 %po, 4
  %o1p = inttoptr i64 %po4 to float*
  store float %r1, float* %o1p, align 4
  %pi1 = add i64 %pi, 16
  %po1 = add i64 %po, 8
  %n1 = sub i64 %n, 1
  %c = icmp ne i64 %n1, 0
  br i1 %c, label %dec_label_pc_5e0356, label %dec_label_pc_5e0377
dec_label_pc_5e0377:
  ret i64 0
}
''',
}


def replace_bodies(text, bodies):
    done = []
    for name, new in bodies.items():
        key = 'define i64 @%s(' % name
        if key not in text:
            raise SystemExit('[hand_bodies] %s not found' % name)
        start = text.index(key)
        end = text.index('\n}\n', start) + 3
        text = text[:start] + new + text[end:]
        done.append(name)
    decls = sorted(set(re.findall(r'@(llvm\.\w+\.f80)\(', ''.join(BODIES.values()))))
    for name in decls:
        line = 'declare x86_fp80 @%s(x86_fp80)' % name
        if line not in text:
            i = text.index('\ndefine ')
            text = text[:i + 1] + line + '\n' + text[i + 1:]
    return text, done


def main():
    args = sys.argv[1:]
    report = None
    if '--report' in args:
        i = args.index('--report')
        report = args[i + 1]
        del args[i:i + 2]
    src, dst = args[0], args[1]
    text, done = replace_bodies(open(src).read(), BODIES)
    open(dst, 'w').write(text)
    if report:
        json.dump({'replaced': done}, open(report, 'w'), indent=1)
    print('hand_bodies: replaced %d (%s)' % (len(done), ' '.join(x for x in done)))


if __name__ == '__main__':
    main()
