#!/usr/bin/env python3
"""fa_fix_gain.py — SlateCore.core_64 の gain::GainDsp::process (0x180afe090) lift IR 修復.
入力: ir5_patch 済み IR (gain_lift.ll)  出力: 修復済み IR (gain_fixed.ll)

RetDec lift の欠陥 3 類型 (いずれも tools/m6..m10 の OTT で既知のクラス) を機械的に修復:
 [P1'] comisd 後の分岐 (jbe/jae) が lift 時に脱落 (no_branch 型; m6 ir6_pass [P1] 対象外)
       → 機械語 0x180afe0fb..0x180afe115 の判定を IR に再構成:
         ramp = (Δ <= -1e-15 || unordered) || (Δ >= +1e-15)   (else: xmm2=0, xmm3=target)
 [F7'] `mov rax,[rdx]` (L ch ポインタ deref) の脱落 → load i64 [arg2] を挿入
 [F2'] callee の xmm1 引数落ち (meter level) → (i64, i32 xmm1bits) に 2-arg 化
 [D]   重複 declare 除去
"""
import re, sys, os
SKIP = set(filter(None, os.environ.get("FA_SKIP", "").split(",")))   # 対照実験用: P1,F7,F2 を個別に無効化

src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()
rep = {}

def sub1(pat, new, flags=0, count=1):
    global t
    t2, n = re.subn(pat, new, t, count=count, flags=flags)
    assert n == count, (pat, n)
    t = t2
    return n

# [P1'] comisd 以降の分岐再構成
if "P1" not in SKIP: sub1(r"  %37 = call i128 @__asm_cvtps2pd\(i128 %36\)\n  %38 = load i128, ptr @global_var_1810cac18, align 8\n  call void @__asm_comisd\(i128 %37, i128 %38\)\n",
     "  %fa_lo = trunc i128 %36 to i32\n  %fa_f = bitcast i32 %fa_lo to float\n  %fa_d = fpext float %fa_f to double\n"
     "  %fa_c0 = fcmp ule double %fa_d, 0xBCD203AF9EE75616\n  %fa_c1 = fcmp oge double %fa_d, 0x3CD203AF9EE75616\n  %fa_ramp = or i1 %fa_c0, %fa_c1\n")
if "P1" not in SKIP: sub1(r"  store i128 %42, ptr %xmm2\.0\.reg2mem\n  store i128 %34, ptr %xmm3\.0\.reg2mem\n",
     "  %fa_x2 = select i1 %fa_ramp, i128 %42, i128 0\n  %fa_x3 = select i1 %fa_ramp, i128 %34, i128 %35\n"
     "  store i128 %fa_x2, ptr %xmm2.0.reg2mem\n  store i128 %fa_x3, ptr %xmm3.0.reg2mem\n")
rep['P1'] = 1

# [F7'] ch0 ポインタ deref
if "F7" not in SKIP: sub1(r"  %87 = add i64 %r8\.0\.reload, %arg2\n",
     "  %fa_a2 = inttoptr i64 %arg2 to ptr\n  %fa_ch0 = load i64, ptr %fa_a2, align 8\n  %87 = add i64 %r8.0.reload, %fa_ch0\n")
rep['F7'] = 1

# [F2'] xmm1 引数
if "F2" not in SKIP: sub1(r"call i64 @function_180afe3a0\(i64 %127\)", "call i64 @function_180afe3a0(i64 %127, i32 %125)")
if "F2" not in SKIP: sub1(r"call i64 @function_180afe420\(i64 %131\)", "call i64 @function_180afe420(i64 %131, i32 %129)")
for fn in (() if "F2" in SKIP else ("180afe3a0", "180afe420")):
    m = re.search(r"define i64 @function_%s\(i64 %%arg1\) local_unnamed_addr \{.*?\n\}\n" % fn, t, re.S)
    body = m.group(0)
    nb = body.replace("define i64 @function_%s(i64 %%arg1)" % fn, "define i64 @function_%s(i64 %%arg1, i32 %%fa_x1)" % fn)
    assert nb.count("  %2 = xor i128 0, 0\n") == 1
    nb = nb.replace("  %2 = xor i128 0, 0\n", "  %2 = zext i32 %fa_x1 to i128\n")
    t = t.replace(body, nb)
rep['F2'] = 2

# [D] 重複 declare
decl = "declare i64 @function_1803ded20(i64, i64, ptr) local_unnamed_addr\n"
assert t.count(decl) == 2
i = t.rfind(decl)
t = t[:i] + t[i + len(decl):]
# 未使用になった extern constant
if "P1" not in SKIP:
    t = t.replace("@global_var_1810cac18 = external local_unnamed_addr constant i128\n", "")
    t = t.replace("declare i128 @__asm_cvtps2pd(i128) local_unnamed_addr\n", "")
    t = t.replace("declare void @__asm_comisd(i128, i128) local_unnamed_addr\n", "")
open(dst, "w").write(t)
print("[fa_fix_gain] repairs:", rep, "->", dst)
