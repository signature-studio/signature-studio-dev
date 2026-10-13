/* liftlib_simd.h — RetDec `__asm_*` pseudo-asm helper 用の共通 C 基盤 (liftlib simd/gen.py が include)。
 * 方針: x86 SSE/AVX の *命令意味* を C で定義 (scalar 基本; SIMD 化は任意)。
 *   - 入出力は LLVM IR の i128 (= xmm 128 bit) を u128, GPR を u32/u64 で受ける
 *   - コンパイルは `-ffp-contract=off -frounding-math -fno-fast-math` 前提 (FMA 融合/再結合の禁止)
 *   - min/max は x86 規約 (どちらか NaN or 両者 0 のとき第 2 オペランド), 変換は x86 の "integer indefinite" 規約
 */
#ifndef LIFTLIB_SIMD_H
#define LIFTLIB_SIMD_H
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>

typedef unsigned __int128 u128;
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;

typedef union {
    u128 q;
    u64 d[2];
    u32 w[4];
    u16 h[8];
    u8 b[16];
    float f[4];
    double g[2];
    int32_t i[4];
    int64_t l[2];
    int16_t s[8];
    int8_t c[16];
} V;

#define LL_EXPORT __attribute__((used, visibility("default")))

static inline V   VQ(u128 x) { V v; v.q = x; return v; }
#define F32L(x) (VQ(x).f[0])
#define F64L(x) (VQ(x).g[0])
static inline float  ASF(u32 x) { float f; memcpy(&f, &x, 4); return f; }
static inline double ASD(u64 x) { double f; memcpy(&f, &x, 8); return f; }
static inline u32 FBITS(float f) { u32 x; memcpy(&x, &f, 4); return x; }
static inline u64 DBITS(double f) { u64 x; memcpy(&x, &f, 8); return x; }
static inline u128 MK128(u64 lo, u64 hi) { return ((u128)hi << 64) | lo; }

/* ---- x86 規約の min/max (第 2 オペランドを返す) ---- */
static inline float  x86_minf(float a, float b)   { return (a < b) ? a : b; }
static inline float  x86_maxf(float a, float b)   { return (a > b) ? a : b; }
static inline double x86_mind(double a, double b) { return (a < b) ? a : b; }
static inline double x86_maxd(double a, double b) { return (a > b) ? a : b; }

/* ---- 変換: x86 の integer indefinite (0x80000000 / 0x8000000000000000) ---- */
static inline int32_t x86_cvtt_f2i32(double x) {
    if (!(x > -2147483649.0 && x < 2147483648.0)) return INT32_MIN;
    return (int32_t)x;
}
static inline int64_t x86_cvtt_f2i64(double x) {
    if (!(x >= -9223372036854775808.0 && x < 9223372036854775808.0)) return INT64_MIN;
    return (int64_t)x;
}
static inline int32_t x86_cvt_f2i32(double x) {      /* MXCSR RN-even */
    if (!(x > -2147483649.0 && x < 2147483648.0)) return INT32_MIN;
    double r = __builtin_rint(x);
    if (!(r >= -2147483648.0 && r <= 2147483647.0)) return INT32_MIN;
    return (int32_t)r;
}
static inline int64_t x86_cvt_f2i64(double x) {
    if (!(x >= -9223372036854775808.0 && x < 9223372036854775808.0)) return INT64_MIN;
    return (int64_t)__builtin_rint(x);
}
/* 非正規数/NaN 等で x86 と一致させるため float→double は C のキャスト (NaN は quiet 化) */

/* ---- 飽和 pack ---- */
static inline int16_t sat_i32_i16(int32_t x) { return x > 32767 ? 32767 : (x < -32768 ? -32768 : (int16_t)x); }
static inline int8_t  sat_i16_i8(int16_t x)  { return x > 127 ? 127 : (x < -128 ? -128 : (int8_t)x); }
static inline uint8_t sat_i16_u8(int16_t x)  { return x > 255 ? 255 : (x < 0 ? 0 : (uint8_t)x); }
static inline uint16_t sat_i32_u16(int32_t x){ return x > 65535 ? 65535 : (x < 0 ? 0 : (uint16_t)x); }

/* ---- cmpps/cmpss 述語 (imm 0..7) ---- */
static inline int cmp_pred_f(float a, float b, int p) {
    int un = (a != a) || (b != b);
    switch (p & 7) {
        case 0: return !un && a == b;
        case 1: return !un && a < b;
        case 2: return !un && a <= b;
        case 3: return un;
        case 4: return un || a != b;
        case 5: return un || !(a < b);
        case 6: return un || !(a <= b);
        default: return !un;
    }
}
static inline int cmp_pred_d(double a, double b, int p) {
    int un = (a != a) || (b != b);
    switch (p & 7) {
        case 0: return !un && a == b;
        case 1: return !un && a < b;
        case 2: return !un && a <= b;
        case 3: return un;
        case 4: return un || a != b;
        case 5: return un || !(a < b);
        case 6: return un || !(a <= b);
        default: return !un;
    }
}

/* ---- roundss/sd (imm8): bit2=1 は MXCSR (RN-even 既定), それ以外 bits[1:0] ---- */
static inline double x86_round_d(double x, int imm) {
    int mode = (imm & 4) ? 0 : (imm & 3);
    switch (mode) {
        case 0: return __builtin_rint(x);
        case 1: return __builtin_floor(x);
        case 2: return __builtin_ceil(x);
        default: return __builtin_trunc(x);
    }
}
static inline float x86_round_f(float x, int imm) {
    int mode = (imm & 4) ? 0 : (imm & 3);
    switch (mode) {
        case 0: return __builtin_rintf(x);
        case 1: return __builtin_floorf(x);
        case 2: return __builtin_ceilf(x);
        default: return __builtin_truncf(x);
    }
}

/* ---- 近似命令 (rcpps/rsqrtps): 実機は 12bit 近似テーブル。ここは相対誤差 < 1.5*2^-12 の近似 (非 bit-exact) ---- */
static inline float approx_rcp(float x) {
    float ax = __builtin_fabsf(x);
    if (ax < 1.17549435e-38f) return __builtin_copysignf(__builtin_inff(), x);    /* 非正規数は 0 扱い */
    float r = 1.0f / x;
    if (__builtin_fabsf(r) < 1.17549435e-38f) return __builtin_copysignf(0.0f, x);
    return r;
}
static inline float approx_rsqrt(float x) {
    float ax = __builtin_fabsf(x);
    if (ax < 1.17549435e-38f) return __builtin_copysignf(__builtin_inff(), x);
    if (x < 0.0f) { u32 b = 0xFFC00000u; float f; memcpy(&f, &b, 4); return f; }
    return 1.0f / __builtin_sqrtf(x);
}

/* ---- ymm (i256) ABI (LIFTLIB #241) ----
 * wasm32 の LLVM IR `i256` は 引数 = 4 × i64 に分割, 戻り値 = sret ポインタ (先頭 i32 引数) に lower される。
 * C 側は 引数を u64 ×4 に平坦化し, 戻り値は struct Y (= sret) で受ける (gen.py が prologue で Y に束ねる)。
 * 下位 128bit = q[0..1], 上位 128bit = q[2..3]。 */
typedef struct { u64 q[4]; } Y;
static inline u128 YLO(Y y) { return MK128(y.q[0], y.q[1]); }
static inline u128 YHI(Y y) { return MK128(y.q[2], y.q[3]); }
static inline Y MKY(u128 lo, u128 hi) {
    Y y; y.q[0] = (u64)lo; y.q[1] = (u64)(lo >> 64); y.q[2] = (u64)hi; y.q[3] = (u64)(hi >> 64); return y;
}

/* ---- pcmpistri (SSE4.2 文字列比較, implicit length) ----
 * a = Intel 第 1 operand, b = 第 2 operand。返値 = ECX。*fl = 実機 EFLAGS 位置 (CF bit0 / ZF bit6 / SF bit7 / OF bit11, AF=PF=0)。
 * imm8: [1:0] 要素 (00 ub / 01 uw / 10 sb / 11 sw), [3:2] 集約 (equal-any / ranges / equal-each / equal-ordered),
 *       [5:4] 極性 (00,10 = positive / 01 = negative / 11 = masked-negative), [6] 出力 (0 = LSB / 1 = MSB)。 */
static inline u32 ll_pcmpistr(u128 a128, u128 b128, int imm, u32* fl) {
    V a = VQ(a128), b = VQ(b128);
    int w = imm & 1, sg = (imm >> 1) & 1, agg = (imm >> 2) & 3, pol = (imm >> 4) & 3, msb = (imm >> 6) & 1;
    int n = w ? 8 : 16, la = n, lb = n;
    int32_t A[16], B[16];
    for (int i = 0; i < n; i++) {
        A[i] = w ? (sg ? (int32_t)a.s[i] : (int32_t)a.h[i]) : (sg ? (int32_t)a.c[i] : (int32_t)a.b[i]);
        B[i] = w ? (sg ? (int32_t)b.s[i] : (int32_t)b.h[i]) : (sg ? (int32_t)b.c[i] : (int32_t)b.b[i]);
    }
    for (int i = 0; i < n; i++) if (!(w ? a.h[i] : a.b[i])) { la = i; break; }
    for (int i = 0; i < n; i++) if (!(w ? b.h[i] : b.b[i])) { lb = i; break; }
    int br[16][16];                                   /* br[i][j]: op1 要素 i と op2 要素 j の比較 (無効要素 override 済み) */
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            int ri = i < la, rj = j < lb, v;
            if (ri && rj) v = (agg == 1) ? ((i & 1) ? (A[i] >= B[j]) : (A[i] <= B[j])) : (A[i] == B[j]);
            else if (agg == 2) v = !ri && !rj;
            else if (agg == 3) v = !ri;
            else v = 0;
            br[i][j] = v;
        }
    u32 m = (n == 16) ? 0xffffu : 0xffu, r1 = 0;
    for (int j = 0; j < n; j++) {
        int v = 0;
        if (agg == 0) { for (int i = 0; i < n; i++) v |= br[i][j]; }
        else if (agg == 1) { for (int i = 0; i + 1 < n; i += 2) v |= br[i][j] & br[i + 1][j]; }
        else if (agg == 2) v = br[j][j];
        else { v = 1; for (int k = 0; k + j < n; k++) v &= br[k][j + k]; }
        r1 |= (u32)v << j;
    }
    u32 r2 = r1;
    if (pol == 1) r2 = ~r1 & m;
    else if (pol == 3) r2 = r1 ^ (((1u << lb) - 1u) & m);
    u32 ecx = r2 ? (msb ? 31u - (u32)__builtin_clz(r2) : (u32)__builtin_ctz(r2)) : (u32)n;
    *fl = (r2 != 0) | ((u32)(lb < n) << 6) | ((u32)(la < n) << 7) | ((r2 & 1u) << 11);
    return ecx;
}
/* RetDec は pcmpistri を `void(i128,i128,i8)` と lift し ECX/フラグを落とす。void 形はこの shadow に結果を残す。 */
extern u32 ll_pcmpistr_ecx, ll_pcmpistr_fl;

#endif
