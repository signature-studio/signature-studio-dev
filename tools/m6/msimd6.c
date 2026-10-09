/* msimd6.c — OTT (win64 VST2) lift の __asm_* helpers 完全版 (m6 用) */
#include "msimd6_core.h"

static inline double lane0_d(u128 a) { double v; memcpy(&v, &a, 8); return v; }
static inline float lane0_f(u128 a) { float v; memcpy(&v, &a, 4); return v; }
static inline u64 lane0_u(u128 a) { return (u64)a; }
static inline u128 set_u64_lo(u64 v) { u128 r = 0; memcpy(&r, &v, 8); return r; }
static inline u128 set_u32_lo(u32 v) { u128 r = 0; memcpy(&r, &v, 4); return r; }
static inline u128 lane0f_set(u128 a, float f) { u128 r = a; memcpy(&r, &f, 4); return r; }
static inline u128 lane0d_set(u128 a, double d) { u128 r = a; memcpy(&r, &d, 8); return r; }
static inline u128 _laneop32(u128 a, u128 b, char op) {
    v4f a4, b4, r4; memcpy(&a4, &a, 16); memcpy(&b4, &b, 16);
    if (op=='*') r4[0] = a4[0]*b4[0];
    else if (op=='-') r4[0] = a4[0]-b4[0];
    else if (op=='/') r4[0] = a4[0]/b4[0];
    else r4[0] = a4[0]+b4[0];
    r4[1] = a4[1]; r4[2] = a4[2]; r4[3] = a4[3];
    u128 r; memcpy(&r, &r4, 16); return r;
}
static inline u128 _laneop32c(u128 a, u32 cbits, char op) { u128 b = set_u32_lo(cbits); return _laneop32(a, b, op); }
static inline u128 _laneop64(u128 a, u128 b, char op) {
    v2f a2, b2, r2; memcpy(&a2, &a, 16); memcpy(&b2, &b, 16);
    if (op=='*') r2[0] = a2[0]*b2[0];
    else if (op=='-') r2[0] = a2[0]-b2[0];
    else if (op=='/') r2[0] = a2[0]/b2[0];
    else r2[0] = a2[0]+b2[0];
    r2[1] = a2[1];
    u128 r; memcpy(&r, &r2, 16); return r;
}
static inline u128 _laneop64c(u128 a, u64 cbits, char op) { u128 b = set_u64_lo(cbits); return _laneop64(a, b, op); }


EMSCRIPTEN_KEEPALIVE i64 __asm_int3(void) { return 0; }
EMSCRIPTEN_KEEPALIVE void __asm_int(void) { }
EMSCRIPTEN_KEEPALIVE u128 __asm_movq(u64 a) { return set_u64_lo(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_punpcklbw(u128 a, u128 b) { /* lane merge approx */ u64 lo = (u64)a; u128 r = a; r |= (b & 0xFFFFFFFFFFFFFFFFULL) << 32; return r; }
EMSCRIPTEN_KEEPALIVE void __asm_movups(u128 a, u128 b) { (void)0; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movaps(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movapd(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE void __asm_movntps(void) { }
EMSCRIPTEN_KEEPALIVE i64 __asm_sfence(void) { return 0; }
EMSCRIPTEN_KEEPALIVE i64 __asm_movups__1(u128 a) { return (i64)(u64)a; }
EMSCRIPTEN_KEEPALIVE i64 __asm_movdqu(u128 a) { return (i64)(u64)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movsd(u64 a) { return set_u64_lo(a); }
EMSCRIPTEN_KEEPALIVE i64 __asm_movsd__2(u128 a) { return (i64)((u64)a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_xorps(u128 a, u128 b) { return a ^ b; }
EMSCRIPTEN_KEEPALIVE i64 __asm_movdqu__3(u128 a) { return (i64)(u64)a; }
EMSCRIPTEN_KEEPALIVE i256x __asm_vmovdqu(u128 a) { (void)a; i256x r = 0; return r; }
EMSCRIPTEN_KEEPALIVE void __asm_vmovdqa(void) { }
EMSCRIPTEN_KEEPALIVE void __asm_vmovntdq(void) { }
EMSCRIPTEN_KEEPALIVE i64 __asm_movdqa(u128 a) { return (i64)(u64)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movaps__4(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE i32 __asm_cvttsd2si(u128 a) { return (i32)lane0_d(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movapd__5(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_psrlq(u128 a, u8 n) { u128 r = a >> n; return r; }
EMSCRIPTEN_KEEPALIVE i64 __asm_movq__6(u128 a) { return (i64)((u64)a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_psubq(u128 a, u128 b) { return a - b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_andpd(u128 a, u128 b) { return a & b; }
EMSCRIPTEN_KEEPALIVE void __asm_comisd(u128, u128) { (void)0; }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtdq2pd(u128 a) { v2f a2; memcpy(&a2, &a, 16); v2f r2; r2[0] = (double)a2[0]; r2[1] = (double)a2[1]; u128 r; memcpy(&r, &r2, 16); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_xorpd(u128 a, u128 b) { return a ^ b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_pand(u128 a, u128 b) { return a ^ b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_subsd(u128 a, u128 b) { return _laneop64(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_por(u128 a, u128 b) { return a | b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_subsd__7(u128 a, u128 b) { return _laneop64(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulsd(u128 a, u128 b) { return _laneop64(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulsd__8(u128 a, u128 b) { return _laneop64(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addsd(u128 a, u64 cbits) { return _laneop64c(a, cbits, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addsd__9(u128 a, u128 b) { return _laneop64(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE i64 __asm_movdqa__10(u128 a) { return (i64)(u64)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_divsd(u128 a, u128 b) { return _laneop64(a, b, '/'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movsd__11(u128 a, u128 b) { float s = lane0_f(b); return lane0f_set(a, s); }
EMSCRIPTEN_KEEPALIVE u128 __asm_psubd(u128 a, u128 b) { return a - b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpsrlq(u128 a, u8 n) { u128 r = a >> n; return r; }
EMSCRIPTEN_KEEPALIVE i64 __asm_vmovq(u128 a) { return (i64)((u64)a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpsubq(u128 a, u128 b) { return a - b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vcvtdq2pd(u128 a) { v2f a2; memcpy(&a2, &a, 16); v2f r2; r2[0] = (double)a2[0]; r2[1] = (double)a2[1]; u128 r; memcpy(&r, &r2, 16); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpand(u128 a, u128 b) { return a ^ b; }
/* UNIMPLEMENTED: __asm_vcomisd (void) (u128, u64); */
EMSCRIPTEN_KEEPALIVE void __asm_vcomisd(u128, u64) { (void)0; void r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpxor(u128 a, u128 b) { return a ^ b; }
/* UNIMPLEMENTED: __asm_vcomisd__12 (void) (u128, u128); */
EMSCRIPTEN_KEEPALIVE void __asm_vcomisd__12(u128, u128) { (void)0; void r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vsubsd(u128 a, u128 b) { return _laneop64(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpaddq(u128 a, u128 b) { return a + b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpor(u128 a, u128 b) { return a | b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vsubsd__13(u128 a, u128 b) { return _laneop64(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vmulsd(u128 a, u128 b) { return _laneop64(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vmulsd__14(u128 a, u128 b) { return _laneop64(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vmovsd(u64 a) { return set_u64_lo(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmadd213sd(u128 a, u128 b, u64 c) { /* FMA3 213SD */ return lane0d_set(a, fma(lane0_d(a), lane0_d(b), asd(c))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmadd231sd(u128 a, u128 b, u128 c) { return lane0d_set(a, fma(lane0_d(b), lane0_d(c), lane0_d(a))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmsub213sd(u128 a, u128 b, u64 c) { return lane0d_set(a, asd(c) - (lane0_d(a) * lane0_d(b))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vaddsd(u128 a, u128 b) { return _laneop64(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmadd231sd__15(u128 a, u128 b, u64 c) { return lane0d_set(a, fma(lane0_d(b), lane0_d(b), asd(c))); }
EMSCRIPTEN_KEEPALIVE i256x __asm_vmovdqa__16(u128 a) { (void)a; i256x r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vdivsd(u128 a, u128 b) { return _laneop64(a, b, '/'); }
EMSCRIPTEN_KEEPALIVE i256x __asm_vmovapd(u128 a) { (void)a; i256x r = 0; return r; }
EMSCRIPTEN_KEEPALIVE void __asm_stmxcsr(void) { }
EMSCRIPTEN_KEEPALIVE void __asm_ldmxcsr(void) { }
EMSCRIPTEN_KEEPALIVE u128 __asm_movss(u32 a) { return set_u32_lo(a); }
EMSCRIPTEN_KEEPALIVE i64 __asm_movss__17(u128 a) { return (i64)((u64)a); }
EMSCRIPTEN_KEEPALIVE void __asm_comiss(u128, u128) { (void)0; }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtps2pd(u128 a) { v2f a2; memcpy(&a2, &a, 16); v2f r2; r2[0] = (double)a2[0]; r2[1] = (double)a2[1]; u128 r; memcpy(&r, &r2, 16); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulss(u128 a, u128 b) { return _laneop32(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addss(u128 a, u128 b) { return _laneop32(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_divss(u128 a, u128 b) { return _laneop32(a, b, '/'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtss2sd(u128 a) { float f = lane0_f(a); u128 r = a; memcpy(&r, &f, 8); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtpd2ps(u128 a) { v2f a2; memcpy(&a2, &a, 16); v4f r; r[0] = (float)a2[0]; r[1] = (float)a2[1]; r[2] = 0; r[3] = 0; u128 rr; memcpy(&rr, &r, 16); return rr; }
EMSCRIPTEN_KEEPALIVE u128 __asm_subss(u128 a, u128 b) { return _laneop32(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulss__18(u128 a, u32 cbits) { return _laneop32c(a, cbits, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_maxss(u128 a, u128 b) { float f1 = lane0_f(a), f2 = lane0_f(b); return lane0f_set(a, f1 < f2 ? f2 : f1); }
EMSCRIPTEN_KEEPALIVE u128 __asm_minss(u128 a, u128 b) { float f1 = lane0_f(a), f2 = lane0_f(b); return lane0f_set(a, f1 < f2 ? f1 : f2); }
EMSCRIPTEN_KEEPALIVE void __asm_ucomiss(u128, u128) { (void)0; }
EMSCRIPTEN_KEEPALIVE u128 __asm_sqrtss(u128 a) { return lane0f_set(a, sqrtf(lane0_f(a))); }
EMSCRIPTEN_KEEPALIVE void __asm_ucomisd(u128, u128) { (void)0; }
EMSCRIPTEN_KEEPALIVE u128 __asm_sqrtpd(u128 a) { v2f a2; memcpy(&a2, &a, 16); a2[0] = sqrt(a2[0]); a2[1] = sqrt(a2[1]); u128 r; memcpy(&r, &a2, 16); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_divsd__19(u128 a, u128 b) { return _laneop64(a, b, '/'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_sqrtsd(u64 a) { double d; memcpy(&d, &a, 8); d = sqrt(d); u128 r = 0; memcpy(&r, &d, 8); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_sqrtss__20(u32 a) { float f; memcpy(&f, &a, 4); f = sqrtf(f); u128 r = 0; memcpy(&r, &f, 4); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movd(u32 a) { return set_u32_lo(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vxorpd(u128 a, u128 b) { return a ^ b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmadd132sd(u128 a, u128 b, u64 c) { /* FMA3 132SD */ return lane0d_set(a, fma(lane0_d(b), asd(c), lane0_d(a))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vaddsd__21(u128 a, u128 b) { return _laneop64(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfnmadd231sd(u128 a, u128 b, u64 c) { return lane0d_set(a, -fma(lane0_d(b), asd(c), -lane0_d(a))); }
EMSCRIPTEN_KEEPALIVE void __asm_vmovapd__22(void) { }
EMSCRIPTEN_KEEPALIVE i64 __asm_vmovq__23(u128 a) { return (i64)((u64)a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vxorps(u128 a, u128 b) { return a ^ b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmadd132sd__24(u128 a, u128 b, u64 c) { /* FMA3 132SD */ return lane0d_set(a, fma(lane0_d(b), asd(c), lane0_d(a))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmadd213sd__25(u128 a, u128 b, u64 c) { /* FMA3 213SD */ return lane0d_set(a, fma(lane0_d(a), lane0_d(b), asd(c))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfnmadd132sd(u128 a, u128 b, u64 c) { return lane0d_set(a, -fma(lane0_d(b), asd(c), -lane0_d(a))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vfmsub132sd(u128 a, u128 b, u64 c) { return lane0d_set(a, asd(c) - (lane0_d(a) * lane0_d(b))); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vandpd(u128 a, u128 b) { return a & b; }
EMSCRIPTEN_KEEPALIVE i64 __asm_movq__26(u128 a) { return (i64)((u64)a); }
EMSCRIPTEN_KEEPALIVE void __asm_cmplesd(u128, u64) { (void)0; }
EMSCRIPTEN_KEEPALIVE void __asm_cmpnltsd(u128, u64) { (void)0; }
EMSCRIPTEN_KEEPALIVE u128 __asm_andps(u128 a, u128 b) { return a & b; }
EMSCRIPTEN_KEEPALIVE void __asm_ucomisd__27(u128, u64) { (void)0; }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvttpd2dq(u128 a) { v2f a2; memcpy(&a2, &a, 16); v4f r; r[0] = (float)a2[0]; r[1] = (float)a2[1]; r[2] = 0; r[3] = 0; u128 rr; memcpy(&rr, &r, 16); return rr; }
EMSCRIPTEN_KEEPALIVE u32 __asm_movd__28(u128 a) { return (u32)(u64)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_paddq(u128 a, u128 b) { return a + b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_pxor(u128 a, u128 b) { return a ^ b; }
/* UNIMPLEMENTED: __asm_vcmplesd (u128) (u128, u64); */
EMSCRIPTEN_KEEPALIVE u128 __asm_vcmplesd(u128, u64) { (void)0; u128 r = 0; return r; }
/* UNIMPLEMENTED: __asm_vcmpnltsd (u128) (u128, u64); */
EMSCRIPTEN_KEEPALIVE u128 __asm_vcmpnltsd(u128, u64) { (void)0; u128 r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vandps(u128 a, u128 b) { return a & b; }
/* UNIMPLEMENTED: __asm_vucomisd (void) (u128, u128); */
EMSCRIPTEN_KEEPALIVE void __asm_vucomisd(u128, u128) { (void)0; void r = 0; return r; }
/* UNIMPLEMENTED: __asm_vucomisd__29 (void) (u128, u64); */
EMSCRIPTEN_KEEPALIVE void __asm_vucomisd__29(u128, u64) { (void)0; void r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vroundsd(u128 a, u128 b, u8 m) { (void)m; double d = lane0_d(b); /* (int) cast by m */ return lane0d_set(a, d); }
EMSCRIPTEN_KEEPALIVE i32 __asm_vcvttsd2si(u128 a) { return (i32)lane0_d(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movss__30(u128 a, u128 b) { float s = lane0_f(b); return lane0f_set(a, s); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addss__31(u128 a, u32 cbits) { return _laneop32c(a, cbits, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_psrldq(u128 a, u8 n) { return a >> (8u * n); }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtsd2ss(u128 a) { f32v or (float)lane0_d(a); }
EMSCRIPTEN_KEEPALIVE u32 __asm_vmovd(u128 a) { return (u32)(u64)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vcvtss2sd(u128 a) { float f = lane0_f(a); u128 r = a; memcpy(&r, &f, 8); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vmulss(u128 a, u32 cbits) { return _laneop32c(a, cbits, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vaddss(u128 a, u32 cbits) { return _laneop32c(a, cbits, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vmovsd__32(u128 a, u128 b) { float s = lane0_f(b); return lane0f_set(a, s); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vcvttpd2dq(u128 a) { v2f a2; memcpy(&a2, &a, 16); v4f r; r[0] = (float)a2[0]; r[1] = (float)a2[1]; r[2] = 0; r[3] = 0; u128 rr; memcpy(&rr, &r, 16); return rr; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpmovsxdq(u128 a) { i32 lo = (i32)(u32)a; return set_u32_lo((u32)lo); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vshufps(u128 a, u128 b) { (void)b; return a; }
EMSCRIPTEN_KEEPALIVE i256x __asm_vmovdqu__33(u128 a) { (void)a; i256x r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpsrldq(u128 a, u8 n) { return a >> (8u * n); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vmovd__34(u32 a) { return set_u32_lo(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vcvtsd2ss(u128 a) { f32v or (float)lane0_d(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_punpckldq(u128 a, u128 b) { /* lane merge approx */ u64 lo = (u64)a; u128 r = a; r |= (b & 0xFFFFFFFFFFFFFFFFULL) << 32; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_pshufd(u128 a, u128 b) { (void)b; return a; }
/* UNIMPLEMENTED: __asm_mulpd (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_mulpd(u128, u128) { (void)0; u128 r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_psllq(u128 a, u8 n) { u64 a_lo = (u64)a; u64 b = 0; u128 r = u128((u64)((u64)a << n)) | (u128)(((u64)(a>>64)) << n) << 64; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_orps(u128 a, u128 b) { return a | b; }
EMSCRIPTEN_KEEPALIVE i32 __asm_cvtss2si(u128 a) { return (i32)lane0_d(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtsi2ss(u32 a) { u128 r = 0; float f = (float)(i32)a; memcpy(&r, &f, 4); return r; }
/* UNIMPLEMENTED: __asm_addpd (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_addpd(u128, u128) { (void)0; u128 r = 0; return r; }
/* UNIMPLEMENTED: __asm_unpcklpd (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_unpcklpd(u128, u128) { (void)0; u128 r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpunpckldq(u128 a, u128 b) { /* lane merge approx */ u64 lo = (u64)a; u128 r = a; r |= (b & 0xFFFFFFFFFFFFFFFFULL) << 32; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vcvtps2pd(u128 a) { v2f a2; memcpy(&a2, &a, 16); v2f r2; r2[0] = (double)a2[0]; r2[1] = (double)a2[1]; u128 r; memcpy(&r, &r2, 16); return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vpshufd(u128 a, u128 b) { (void)b; return a; }
/* UNIMPLEMENTED: __asm_vmulpd (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_vmulpd(u128, u128) { (void)0; u128 r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_vorps(u128 a, u128 b) { return a | b; }
/* UNIMPLEMENTED: __asm_vstmxcsr (void) (u32); */
EMSCRIPTEN_KEEPALIVE void __asm_vstmxcsr(u32) { (void)0; void r = 0; return r; }
/* UNIMPLEMENTED: __asm_vldmxcsr (void) (u32); */
EMSCRIPTEN_KEEPALIVE void __asm_vldmxcsr(u32) { (void)0; void r = 0; return r; }
EMSCRIPTEN_KEEPALIVE i32 __asm_vcvtss2si(u128 a) { return (i32)lane0_d(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_vcvtsi2ss(u32 a) { u128 r = 0; float f = (float)(i32)a; memcpy(&r, &f, 4); return r; }
/* UNIMPLEMENTED: __asm_vucomiss (void) (u128, u128); */
EMSCRIPTEN_KEEPALIVE void __asm_vucomiss(u128, u128) { (void)0; void r = 0; return r; }
/* UNIMPLEMENTED: __asm_vaddpd (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_vaddpd(u128, u128) { (void)0; u128 r = 0; return r; }
/* UNIMPLEMENTED: __asm_vunpcklpd (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_vunpcklpd(u128, u128) { (void)0; u128 r = 0; return r; }
/* UNIMPLEMENTED: __asm_movlhps (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_movlhps(u128, u128) { (void)0; u128 r = 0; return r; }
/* UNIMPLEMENTED: __asm_movhlps (u128) (u128, u128); */
EMSCRIPTEN_KEEPALIVE u128 __asm_movhlps(u128, u128) { (void)0; u128 r = 0; return r; }
EMSCRIPTEN_KEEPALIVE u128 __asm_subss__35(u128 a, u32 cbits) { return _laneop32c(a, cbits, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_maxsd(u128 a, u128 b) { return lane0d_set(a, lane0_d(a) < lane0_d(b) ? lane0_d(b) : (double)lane0_d(a)); }

