/* kh_simd_gain.c — gain::GainDsp::process lift (poc_gain) 用 __asm_* helper。
 * signature は lift IR の declare を正本とする (work/gain_p1.ll)。
 * 意味は x86 SSE 仕様準拠 (lane0 f32/f64 スカラ演算, 上位 lane は第 1 オペランドから保持)。
 * ucomisd は ir_kh_p1.py が IR 内で fcmp 化済み → no-op。
 */
#include "ref/msimd6_core.h"
#include <emscripten.h>

typedef union { u128 q; u32 w[4]; u64 d[2]; float f[4]; double dd[2]; } L128;

static inline u128 mk(L128 x) { return x.q; }

EMSCRIPTEN_KEEPALIVE u128 __asm_movss(u32 a)            { L128 r; r.q = 0; r.w[0] = a; return r.q; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movaps(u128 a)          { return a; }
EMSCRIPTEN_KEEPALIVE u64  __asm_movss__1(u128 a)        { return (u32)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movq(u128 a)            { return (u128)(u64)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_andps(u128 a, u128 b)   { return a & b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_xorps(u128 a, u128 b)   { return a ^ b; }
EMSCRIPTEN_KEEPALIVE void __asm_ucomisd(u128 a, u64 b)  { (void)a; (void)b; }
EMSCRIPTEN_KEEPALIVE void __asm_movups(u128 a, u128 b)  { (void)a; (void)b; }

#define SS_RR(NAME, OP) \
EMSCRIPTEN_KEEPALIVE u128 NAME(u128 a, u128 b) { L128 x, y; x.q = a; y.q = b; x.f[0] = x.f[0] OP y.f[0]; return x.q; }
SS_RR(__asm_addss, +)
SS_RR(__asm_subss, -)
SS_RR(__asm_mulss__2, *)
SS_RR(__asm_divss, /)

EMSCRIPTEN_KEEPALIVE u128 __asm_mulss(u128 a, u32 m) { L128 x; x.q = a; x.f[0] = x.f[0] * asf(m); return x.q; }

EMSCRIPTEN_KEEPALIVE u128 __asm_cvtss2sd(u128 a) { L128 x; x.q = a; x.dd[0] = (double)x.f[0]; return x.q; }

EMSCRIPTEN_KEEPALIVE u128 __asm_cvtsi2ss(u32 a) { L128 r; r.q = 0; r.f[0] = (float)(int)a; return r.q; }

EMSCRIPTEN_KEEPALIVE u128 __asm_shufps(u128 a, u128 b, u8 imm) {
    L128 x, y, r; x.q = a; y.q = b;
    r.w[0] = x.w[imm & 3]; r.w[1] = x.w[(imm >> 2) & 3];
    r.w[2] = y.w[(imm >> 4) & 3]; r.w[3] = y.w[(imm >> 6) & 3];
    return r.q;
}

/* DLL .rdata 実データ (HeartCore.core_64): 0x1813d6fc0 = abs mask 0x7fffffff x4 */
const u128 global_var_1813d6fc0 = ((u128)0x7fffffff7fffffffULL << 64) | 0x7fffffff7fffffffULL;

/* 未リフト callee: std::vector<int> 再確保 (0x18004cf20)。本 PoC のテストは踏まない → fail-fast */
EMSCRIPTEN_KEEPALIVE i64 function_18004cf20(i64 a, i64 b, void* c, i64 d, i64 e) { (void)a; (void)b; (void)c; (void)d; (void)e; abort(); return 0; }
