#!/usr/bin/env python3
"""vex_gen.py IR.ll OUT.c — IR の declare から AVX/FMA3 (VEX.128) の __asm_v* helper を署名駆動で生成する。
m11_simd2.py (SSE のみ) が未実装 stub にする VEX 命令を実装する。`__N` suffix は build ごとに変わるため、名前でなく
(base 名, 返り型, 引数型) で意味を決める。VEX 3 operand は dst を落とした (src1, src2[, src3]) で、dst 上位 lane は src1 を保持。
FMA は fma() (単一丸め = FMA3 hardware 等価)。mxcsr 操作は software shadow (round-nearest 固定) のため no-op。
意味を決められない名前は生成せず stdout に列挙する (simd_merge.py が fail-fast stub のまま残す)。"""
import json, re, sys

ll = open(sys.argv[1]).read()
DECL = re.findall(r'^declare (\S+) @(__asm_v[\w.$-]+)\((.*?)\)', ll, re.M)
CT = {'i128': 'u128', 'i64': 'u64', 'i32': 'u32', 'i8': 'u32', 'void': 'void'}
HEAD = '''#include <stdint.h>
#include <string.h>
#include <math.h>
typedef unsigned __int128 u128; typedef unsigned long long u64; typedef uint32_t u32;
static double D_(u64 b) { double d; memcpy(&d, &b, 8); return d; }
static u64 B_(double d) { u64 b; memcpy(&b, &d, 8); return b; }
static float F_(u32 b) { float f; memcpy(&f, &b, 4); return f; }
static u32 FB_(float f) { u32 b; memcpy(&b, &f, 4); return b; }
static u128 setlo64(u128 a, u64 v) { return (a & ~(u128)0xFFFFFFFFFFFFFFFFull) | v; }
static u128 setlo32(u128 a, u32 v) { return (a & ~(u128)0xFFFFFFFFull) | v; }
#define LO(a) ((u64)(a))
#define HI(a) ((u64)((a) >> 64))
#define MK(lo, hi) (((u128)(hi) << 64) | (u128)(lo))
static u32 tt_(double d) { if (d != d || d >= 2147483648.0 || d < -2147483648.0) return 0x80000000u; return (u32)(int32_t)d; }
static u32 rn_(double d) { if (d != d || d >= 2147483647.5 || d <= -2147483648.5) return 0x80000000u; return (u32)(int32_t)nearbyint(d); }
'''
FMA_RE = re.compile(r'^vf(n?)m(add|sub)(132|213|231)sd$')


def body(base, R, A):
    n = len(A)
    d1 = lambda i: ('D_(LO(%s))' if A[i] == 'i128' else 'D_(%s)') % 'abc'[i]   # double 値 (i128=lane0 / i64=bits)
    f1 = lambda i: ('F_((u32)%s)' if A[i] == 'i128' else 'F_(%s)') % 'abc'[i]
    m = FMA_RE.match(base)
    if m and n == 3 and R == 'i128':
        neg, sub, order = m.group(1) == 'n', m.group(2) == 'sub', m.group(3)
        a_, b_, c_ = 'D_(LO(a))', d1(1), d1(2)
        x, y, z = {'132': (a_, c_, b_), '213': (b_, a_, c_), '231': (b_, c_, a_)}[order]
        return 'return setlo64(a, B_(fma(%s%s, %s, %s%s)));' % ('-' if neg else '', x, y, '-' if sub else '', z)
    sm = re.match(r'^v(add|sub|mul|div)(sd|ss)$', base)
    if sm and n == 2 and R == 'i128':
        op = {'add': '+', 'sub': '-', 'mul': '*', 'div': '/'}[sm.group(1)]
        if sm.group(2) == 'sd':
            return 'return setlo64(a, B_(D_(LO(a)) %s %s));' % (op, d1(1))
        return 'return setlo32(a, FB_(F_((u32)a) %s %s));' % (op, f1(1))
    if base in ('vmovapd', 'vmovaps', 'vmovdqa', 'vmovdqu', 'vmovups', 'vmovupd'):
        if n == 1 and R == 'i128' and A[0] == 'i128': return 'return a;'
        if R == 'void': return '(void)a; (void)b;'
    if base == 'vmovd':
        if R == 'i32': return 'return (u32)a;'
        if R == 'i128' and n == 1: return 'return (u128)a;'
    if base == 'vmovq':
        if R == 'i64': return 'return LO(a);'
        if R == 'i128' and n == 1: return 'return (u128)a;'
    if base == 'vmovsd':
        if n == 1 and R == 'i128': return 'return (u128)a;'
        if n == 2 and R == 'i128': return 'return setlo64(a, LO(b));'
    if base == 'vmovss' and n == 1 and R == 'i128': return 'return (u128)a;'
    if base in ('vcmplesd', 'vcmpnltsd') and n == 2:
        cond = 'D_(LO(a)) <= %s' % d1(1) if base == 'vcmplesd' else '!(D_(LO(a)) < %s)' % d1(1)
        return 'return setlo64(a, (%s) ? ~0ull : 0ull);' % cond
    if base == 'vcvtsd2ss' and n == 2: return 'return setlo32(a, FB_((float)D_(LO(b))));'
    if base == 'vcvtss2sd' and n == 2: return 'return setlo64(a, B_((double)F_((u32)b)));'
    if base == 'vcvtsi2ss' and n == 2: return 'return setlo32(a, FB_((float)(int32_t)b));'
    if base == 'vcvtss2si' and R == 'i32': return 'double v = nearbyint((double)F_((u32)a)); if (!(v > -2147483649.0 && v < 2147483648.0)) return 0x80000000u; return (u32)(int32_t)v;'
    if base == 'vcvttsd2si' and R == 'i32': return 'double v = trunc(D_(LO(a))); if (!(v > -2147483649.0 && v < 2147483648.0)) return 0x80000000u; return (u32)(int32_t)v;'
    if base == 'vcvttpd2dq' and n == 1: return 'return (u128)(((u64)tt_(D_(HI(a))) << 32) | tt_(D_(LO(a))));'
    if base == 'vcvtpd2dq' and n == 1: return 'return (u128)(((u64)rn_(D_(HI(a))) << 32) | rn_(D_(LO(a))));'
    if base == 'vcvtdq2pd': return 'return MK(B_((double)(int32_t)(u32)a), B_((double)(int32_t)(u32)(a >> 32)));'
    if base == 'vcvtps2pd': return 'return MK(B_((double)F_((u32)a)), B_((double)F_((u32)(a >> 32))));'
    if base == 'vroundsd' and n == 3:
        return 'double x = D_(LO(b)); unsigned m = (c & 4) ? 0 : (c & 3); double r = m == 0 ? nearbyint(x) : m == 1 ? floor(x) : m == 2 ? ceil(x) : trunc(x); return setlo64(a, B_(r));'
    if base in ('vaddpd', 'vmulpd'):
        op = '+' if base == 'vaddpd' else '*'
        return 'return MK(B_(D_(LO(a)) %s D_(LO(b))), B_(D_(HI(a)) %s D_(HI(b))));' % (op, op)
    if base in ('vandpd', 'vandps', 'vpand'): return 'return a & b;'
    if base in ('vorps', 'vorpd', 'vpor'): return 'return a | b;'
    if base in ('vxorpd', 'vxorps', 'vpxor'): return 'return a ^ b;'
    if base == 'vpaddq': return 'return MK(LO(a) + LO(b), HI(a) + HI(b));'
    if base == 'vpsubq': return 'return MK(LO(a) - LO(b), HI(a) - HI(b));'
    if base == 'vpsubd': return 'u32 x[4], y[4], r[4]; memcpy(x, &a, 16); memcpy(y, &b, 16); for (int i = 0; i < 4; i++) r[i] = x[i] - y[i]; u128 o; memcpy(&o, r, 16); return o;'
    if base == 'vpunpckldq': return 'return MK(((u64)(u32)b << 32) | (u32)a, ((u64)(u32)(b >> 32) << 32) | (u32)(a >> 32));'
    if base == 'vpshufd': return 'u32 x[4], r[4]; memcpy(x, &a, 16); for (int i = 0; i < 4; i++) r[i] = x[(b >> (2 * i)) & 3]; u128 o; memcpy(&o, r, 16); return o;'
    if base == 'vpsrldq': return 'return b > 15 ? 0 : a >> (8 * b);'
    if base == 'vpsrlq': return 'return b > 63 ? 0 : MK(LO(a) >> b, HI(a) >> b);'
    if base == 'vpsllq': return 'return b > 63 ? 0 : MK(LO(a) << b, HI(a) << b);'
    if base == 'vpsrad': return 'int32_t x[4]; memcpy(x, &a, 16); unsigned s = b > 31 ? 31 : b; for (int i = 0; i < 4; i++) x[i] >>= s; u128 o; memcpy(&o, x, 16); return o;'
    if base == 'vpmovsxdq': return 'return MK((u64)(int64_t)(int32_t)(u32)a, (u64)(int64_t)(int32_t)(u32)(a >> 32));'
    if base == 'vshufps': return 'u32 x[4], y[4], r[4]; memcpy(x, &a, 16); memcpy(y, &b, 16); r[0] = x[c & 3]; r[1] = x[(c >> 2) & 3]; r[2] = y[(c >> 4) & 3]; r[3] = y[(c >> 6) & 3]; u128 o; memcpy(&o, r, 16); return o;'
    if base == 'vunpcklpd': return 'return MK(LO(a), LO(b));'
    if base in ('vldmxcsr', 'vstmxcsr'): return '(void)a;'
    return None


out, skipped, done = [HEAD], [], []
for R, name, args in sorted(set(DECL), key=lambda t: t[1]):
    A = [x.strip().split()[0] for x in args.split(',') if x.strip()]
    base = re.sub(r'(__\d+)+$', '', name[len('__asm_'):])
    if 'i256' in A or R == 'i256' or base in ('vzeroupper', 'vcomisd', 'vucomisd', 'vcomiss', 'vucomiss'):
        continue   # i256 は m11_simd2 が trap 化済み / vzeroupper・comis は m11_simd2 の no-op で足りる (flag は icall_rewrite の comis 経路)
    b = body(base, R, A)
    if b is None:
        skipped.append(name)
        continue
    ps = ', '.join('%s %s' % (CT.get(t, 'u64'), 'abc'[i]) for i, t in enumerate(A)) or 'void'
    out.append('EMSCRIPTEN_KEEPALIVE %s %s(%s) { %s }' % (CT[R], name, ps, b))
    done.append(name)
open(sys.argv[2], 'w').write('#include <emscripten.h>\n' + '\n'.join(out) + '\n')
print(json.dumps({'vex_generated': len(done), 'vex_unresolved': skipped}))
