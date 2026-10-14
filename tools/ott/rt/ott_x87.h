/* ott_x87.h — ia32 x87 FPU の lowering runtime (tools/ott/lift/x64c.py の IA32 経路だけが使う)。
 * 方針 (docs/DECISIONS.md の x87 ADR): f80 を持たず、スタック要素は double (f80→f64 lowering)。
 * 制限 (ADR): (1) 精度制御 PC は f64 固定 (2) fst m32 の丸めは C の cast (nearest) 固定
 * (3) fild m64 で |v|>2^53 は丸まる (4) スタック over/underflow と x87 例外は模型化しない
 * (5) RC (FCW bits 10-11) は fist/fistp の丸めにだけ適用する。 */
#ifndef OTT_X87_H
#define OTT_X87_H
#include "ott_cpu.h"

static double ott_fst[8];          /* 物理 8 本。ST(i) = ott_fst[(ott_ftop + i) & 7] */
static unsigned ott_ftop;          /* TOP */
static uint16_t ott_fcw = 0x037f;  /* FCW (既定値) */
static uint16_t ott_fsw;           /* C0 (bit 8) / C2 (bit 10) / C3 (bit 14) のみ。TOP は ott_ftop から合成 */

#define OTT_X87_CMASK 0x4500u      /* C3|C2|C0 */

static inline double x87_st(unsigned i) { return ott_fst[(ott_ftop + i) & 7]; }
static inline void x87_set(unsigned i, double v) { ott_fst[(ott_ftop + i) & 7] = v; }
static inline void x87_push(double v) { ott_ftop = (ott_ftop - 1) & 7; ott_fst[ott_ftop] = v; }
static inline void x87_pop(void) { ott_ftop = (ott_ftop + 1) & 7; }
static inline uint16_t x87_fsw(void) { return (uint16_t)((ott_fsw & OTT_X87_CMASK) | (ott_ftop << 11)); }

/* f80 (10 B, little endian) → double。範囲外 (f64 の指数域を超える) は 0 / inf に丸まる */
static inline double x87_f80_to_f64(const uint8_t* p) {
    uint64_t sig; uint16_t se; memcpy(&sig, p, 8); memcpy(&se, p + 8, 2);
    int neg = se >> 15, e = se & 0x7fff;
    double r;
    if (e == 0x7fff) {   /* inf / NaN (NaN は上位 52bit の payload を残し quiet 化) */
        uint64_t b = ((uint64_t)neg << 63) | (0x7ffULL << 52);
        if ((sig << 1) != 0) b |= ((sig >> 11) & 0xfffffffffffffULL) | (1ULL << 51);
        memcpy(&r, &b, 8);
        return r;
    }
    if (sig == 0) return neg ? -0.0 : 0.0;
    r = ldexp((double)sig, (e == 0 ? 1 : e) - 16383 - 63);
    return neg ? -r : r;
}

/* double → f80 (10 B)。f64 の値は f80 で正確に表せる (指数域内) */
static inline void x87_f64_to_f80(double v, uint8_t* p) {
    uint64_t bits, sig = 0, m; uint16_t se; int ex;
    memcpy(&bits, &v, 8);
    se = (uint16_t)((bits >> 63) << 15);
    ex = (int)((bits >> 52) & 0x7ff);
    m = bits & 0xfffffffffffffULL;
    if (ex == 0x7ff) {
        se |= 0x7fff;
        sig = 0x8000000000000000ULL | (m << 11);
    } else if (ex == 0 && m == 0) {
        sig = 0;
    } else {
        int fe;
        double fr = frexp(fabs(v), &fe);
        sig = (uint64_t)ldexp(fr, 64);
        se |= (uint16_t)(fe - 1 + 16383);
    }
    memcpy(p, &sig, 8); memcpy(p + 8, &se, 2);
}

enum { X87_ADD, X87_MUL, X87_SUB, X87_SUBR, X87_DIV, X87_DIVR };
/* a = 宛先 (旧値), b = 元。SUBR/DIVR は b op a */
static inline double x87_bin(int op, double a, double b) {
    switch (op) {
    case X87_ADD: return a + b;
    case X87_MUL: return a * b;
    case X87_SUB: return a - b;
    case X87_SUBR: return b - a;
    case X87_DIV: return a / b;
    default: return b / a;
    }
}
/* ST(di) = ST(di) op b、続けて pop なら pop (Intel SDM: FSUB ST(i),ST(0) 等の p 形と同じ) */
static inline void x87_arith(int op, unsigned di, double b, int pop) {
    x87_set(di, x87_bin(op, x87_st(di), b));
    if (pop) x87_pop();
}

/* 比較 → C3/C2/C0 (SDM: > は 000、< は 001、= は 100、unordered は 111) */
static inline void x87_fcom(double a, double b) {
    uint16_t c;
    if (a != a || b != b) c = 0x4500;
    else if (a > b) c = 0;
    else if (a < b) c = 0x0100;
    else c = 0x4000;
    ott_fsw = (uint16_t)((ott_fsw & ~OTT_X87_CMASK) | c);
}

/* fist/fistp の丸め (FCW.RC: 00 nearest / 01 down / 10 up / 11 truncate) */
static inline double x87_rc(double v) {
    switch ((ott_fcw >> 10) & 3) {
    case 0: return nearbyint(v);
    case 1: return floor(v);
    case 2: return ceil(v);
    default: return trunc(v);
    }
}
/* 範囲外・NaN は integer indefinite (0x8000… 相当) */
static inline int16_t x87_fist16(double v) { double r = x87_rc(v); return (r >= -32768.0 && r <= 32767.0) ? (int16_t)r : INT16_MIN; }
static inline int32_t x87_fist32(double v) { double r = x87_rc(v); return (r >= -2147483648.0 && r <= 2147483647.0) ? (int32_t)r : INT32_MIN; }
static inline int64_t x87_fist64(double v) { double r = x87_rc(v); return (r >= -9223372036854775808.0 && r < 9223372036854775808.0) ? (int64_t)r : INT64_MIN; }

#endif
