#!/usr/bin/env python3
"""gen_helpers.py IN.ll OUT.c [--break OP] — lift IR の `declare @__asm_*` から SSE/AVX scalar・packed helper の C 実装を生成する。
規約は tools/m6..m11 の msimd と同じ: i128 = xmm 全体 (lane0 = 下位 32bit / 64bit)、IEEE round-to-nearest。
RetDec は同名・異シグネチャの declare に `.NNN` を付けるので、C 側は asm label で記号名を一致させる。
未知の op / 想定外のシグネチャは exit 1 (黙って no-op にしない)。
EFLAGS・MXCSR を書く命令 (comiss/ucomisd/ldmxcsr/stmxcsr) と int は no-op にせず __builtin_trap() にする (flags が IR に繋がらない。D1a 変種)。
--break OP : ネガティブコントロール用。addss/subss/mulss のどれか 1 種の演算を意図的に誤らせる (add→sub, sub→add, mul→add)。"""
import re, sys

args = sys.argv[1:]
brk = None
if "--break" in args:
    i = args.index("--break"); brk = args[i + 1]; del args[i:i + 2]
assert brk in (None, "addss", "subss", "mulss"), brk
src = open(args[0]).read()
decls = re.findall(r"^declare (\S+) @(__asm_[A-Za-z0-9_.]+)\(([^)]*)\)", src, re.M)
T = {"i128": "u128", "i64": "uint64_t", "i32": "uint32_t", "i8": "uint8_t", "void": "void"}
out = ['#include <stdint.h>', '#include <string.h>', '#include <math.h>', 'typedef unsigned __int128 u128;',
       'static float f0(u128 a){uint32_t u=(uint32_t)a;float f;memcpy(&f,&u,4);return f;}',
       'static float fb(uint32_t u){float f;memcpy(&f,&u,4);return f;}',
       'static u128 setl(u128 a,float f){uint32_t u;memcpy(&u,&f,4);return (a&~(u128)0xffffffffu)|u;}',
       'static double d0(u128 a){uint64_t u=(uint64_t)a;double d;memcpy(&d,&u,8);return d;}',
       'static double db(uint64_t u){double d;memcpy(&d,&u,8);return d;}',
       'static u128 setd(u128 a,double d){uint64_t u;memcpy(&u,&d,8);return (a&~(u128)0xffffffffffffffffull)|u;}',
       'static uint32_t cvt_i32(double x){if(!(x>=-2147483648.0&&x<2147483648.0))return 0x80000000u;return (uint32_t)(int32_t)x;}',
       'static u128 cvt_pd2dq(u128 a){u128 r=0;for(int k=0;k<2;k++)r|=(u128)cvt_i32(db((uint64_t)(a>>(64*k))))<<(32*k);return r;}',
       'static u128 cvt_dq2ps(u128 a){u128 r=0;for(int k=0;k<4;k++){float f=(float)(int32_t)(uint32_t)(a>>(32*k));uint32_t u;memcpy(&u,&f,4);r|=(u128)u<<(32*k);}return r;}',
       'static u128 cvt_dq2pd(u128 a){u128 r=0;for(int k=0;k<2;k++){double d=(double)(int32_t)(uint32_t)(a>>(32*k));uint64_t u;memcpy(&u,&d,8);r|=(u128)u<<(64*k);}return r;}',
       'static u128 cvt_ps2pd(u128 a){u128 r=0;for(int k=0;k<2;k++){double d=(double)fb((uint32_t)(a>>(32*k)));uint64_t u;memcpy(&u,&d,8);r|=(u128)u<<(64*k);}return r;}']
ARITH = {"addss": "+", "subss": "-", "mulss": "*", "divss": "/"}
BROKEN = {"addss": "-", "subss": "+", "mulss": "+"}
SD = {"addsd": "+", "subsd": "-", "mulsd": "*", "divsd": "/"}
FMA = {"vfmadd132sd": "fma(x,z,y)", "vfmadd213sd": "fma(y,x,z)", "vfmadd231sd": "fma(y,z,x)",
       "vfnmadd132sd": "fma(-x,z,y)", "vfnmadd213sd": "fma(-y,x,z)", "vfnmadd231sd": "fma(-y,z,x)",
       "vfmsub213sd": "fma(y,x,-z)"}
TRAP = {"comiss", "ucomisd", "ldmxcsr", "stmxcsr", "int"}
LO64 = "(p0&~(u128)0xffffffffffffffffull)"

def body_of(op, a, ret, brk):
    if op in TRAP:
        return "__builtin_trap();"
    if op == "movss" and a == ["i32"] and ret == "i128": return "return (u128)p0;"
    if op == "movss" and a == ["i128"] and ret in ("i64", "i32"): return f"return ({T[ret]})(uint32_t)p0;"
    if op == "movaps" and a == ["i128"] and ret == "i128": return "return p0;"
    if op in ("movaps", "movapd") and a == ["i128"] and ret in ("i64", "i32"): return f"return ({T[ret]})p0;"
    if op in ("movapd", "vmovapd", "movdqa", "movdqu", "vmovdqu") and a == ["i128"] and ret == "i128": return "return p0;"
    if op == "movq" and a == ["i64"] and ret == "i128": return "return (u128)p0;"
    if op in ("movsd", "vmovsd", "vmovq") and a == ["i64"] and ret == "i128": return "return (u128)p0;"
    if op in ("movq", "vmovq", "movsd") and a == ["i128"] and ret == "i64": return "return (uint64_t)p0;"
    if op == "movd" and a == ["i32"] and ret == "i128": return "return (u128)p0;"
    if op == "movd" and a == ["i128"] and ret == "i32": return "return (uint32_t)p0;"
    if op == "movsd" and a == ["i128", "i128"] and ret == "i128": return f"return {LO64}|(u128)(uint64_t)p1;"
    if op == "movlhps" and a == ["i128", "i128"] and ret == "i128": return "return (p0&(u128)0xffffffffffffffffull)|((u128)(uint64_t)p1<<64);"
    if op == "movhlps" and a == ["i128", "i128"] and ret == "i128": return f"return {LO64}|(p1>>64);"
    if op == "punpcklbw" and a == ["i128", "i128"] and ret == "i128":
        return "u128 r=0; for(int k=0;k<8;k++){ r|=((p0>>(8*k))&0xff)<<(16*k); r|=((p1>>(8*k))&0xff)<<(16*k+8); } return r;"
    if op == "int3" and a == [] and ret == "i64": return "__builtin_trap(); return 0;"
    if op == "sfence" and a == [] and ret == "i64": return "return 0;"
    if op in ARITH and len(a) == 2 and a[0] == "i128" and ret == "i128" and a[1] in ("i128", "i32"):
        y = "f0(p1)" if a[1] == "i128" else "fb(p1)"
        sym = BROKEN[op] if brk == op else ARITH[op]
        return f"float x=f0(p0),y={y}; return setl(p0,x{sym}y);"
    base = op[1:] if op[:1] == "v" and op[1:] in SD else op
    if base in SD and len(a) == 2 and a[0] == "i128" and ret == "i128" and a[1] in ("i128", "i64"):
        y = "d0(p1)" if a[1] == "i128" else "db(p1)"
        return f"double x=d0(p0),y={y}; return setd(p0,x{SD[base]}y);"
    if op in FMA and a[:2] == ["i128", "i128"] and len(a) == 3 and a[2] in ("i128", "i64") and ret == "i128":
        z = "d0(p2)" if a[2] == "i128" else "db(p2)"
        return f"double x=d0(p0),y=d0(p1),z={z}; return setd(p0,{FMA[op]});"
    if op == "cvtsd2ss" and a == ["i128"] and ret == "i128": return "return setl(p0,(float)d0(p0));"
    if op in ("cvttss2si",) and a == ["i128"] and ret == "i32":
        return "float x=f0(p0); if(!(x>=-2147483648.0f&&x<2147483648.0f)) return 0x80000000u; return (uint32_t)(int32_t)x;"
    if op == "cvttsd2si" and a == ["i128"] and ret == "i32": return "return cvt_i32(d0(p0));"
    if op in ("cvttpd2dq", "vcvttpd2dq") and a == ["i128"] and ret == "i128": return "return cvt_pd2dq(p0);"
    if op == "cvtdq2ps" and a == ["i128"] and ret == "i128": return "return cvt_dq2ps(p0);"
    if op == "cvtdq2pd" and a == ["i128"] and ret == "i128": return "return cvt_dq2pd(p0);"
    if op == "cvtps2pd" and a == ["i128"] and ret == "i128": return "return cvt_ps2pd(p0);"
    if op == "mulpd" and a == ["i128", "i128"] and ret == "i128":
        return "u128 r=0; for(int k=0;k<2;k++){ double z=db((uint64_t)(p0>>(64*k)))*db((uint64_t)(p1>>(64*k))); uint64_t u; memcpy(&u,&z,8); r|=(u128)u<<(64*k); } return r;"
    if op in ("psrldq", "vpsrldq") and a == ["i128", "i8"] and ret == "i128": return "unsigned c=p1; return c>15?0:(p0>>(8*c));"
    if op == "psrlq" and a == ["i128", "i8"] and ret == "i128":
        return "unsigned c=p1; u128 r=0; if(c<64) for(int k=0;k<2;k++){ uint64_t l=(uint64_t)(p0>>(64*k)); r|=(u128)(l>>c)<<(64*k); } return r;"
    if op == "psllq" and a == ["i128", "i8"] and ret == "i128":
        return "unsigned c=p1; u128 r=0; if(c<64) for(int k=0;k<2;k++){ uint64_t l=(uint64_t)(p0>>(64*k)); r|=(u128)(l<<c)<<(64*k); } return r;"
    if op == "xorps" and a == ["i128", "i128"] and ret == "i128": return "return p0^p1;"
    if op in ("xorpd", "vxorpd") and a == ["i128", "i128"] and ret == "i128": return "return p0^p1;"
    if op == "vandpd" and a == ["i128", "i128"] and ret == "i128": return "return p0&p1;"
    if op == "ucomiss" and a == ["i128", "i128"] and ret == "void": return ""
    return None

nh = {}
unsup = []
for i, (ret, name, a_) in enumerate(decls):
    op = re.match(r"__asm_([a-z0-9]+)", name).group(1)
    a = [x.strip() for x in a_.split(",") if x.strip()]
    params = ", ".join(f"{T[t]} p{j}" for j, t in enumerate(a))
    head = f"{T[ret]} h{i}({params})"
    body = body_of(op, a, ret, brk)
    if body is None:
        unsup.append(f"declare {ret} @{name}({a_})")
        continue
    out.append(f'{head} __asm__("{name}");')
    out.append(f"{head} {{ {body} }}")
    nh[op] = nh.get(op, 0) + 1
if unsup:
    print(f"[gen_helpers] {len(unsup)} unsupported helper signatures (全数):", file=sys.stderr)
    for u in unsup: print(f"  {u}", file=sys.stderr)
    sys.exit(1)
open(args[1], "w").write("\n".join(out) + "\n")
print(f"[gen_helpers] {len(decls)} helpers ({', '.join(f'{k}:{v}' for k, v in sorted(nh.items()))})" + (f" BREAK={brk}" if brk else "") + f" -> {args[1]}")
