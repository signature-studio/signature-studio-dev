/* ott_x87.h — ia32 x87 FPU の lowering runtime (tools/ott/lift/x64c.py の IA32 経路だけが使う)。
 * 方針 (docs/DECISIONS.md の x87 ADR): f80 を持たず、スタック要素は double (f80→f64 lowering)。
 * 制限 (ADR): (1) 精度制御 PC は f64 固定 (2) fst m32 の丸めは C の cast (nearest) 固定
 * (3) fild m64 で |v|>2^53 は丸まる (4) スタック over/underflow と x87 例外は模型化しない
 * (5) RC (FCW bits 10-11) は fist/fistp の丸めにだけ適用する。
 * (6) C1 は fxam (符号) と比較命令 (0) の後だけ模型化する。 他の命令の C1 は native では丸めの上向きフラグになるが、
 *     f64 は丸め方向を持たないので模型化しない (C1 は直前の fxam/比較の値を persist する)。
 * (7) タグ (TW) は物理レジスタごとの 2 bit (00 valid / 01 zero / 10 special / 11 empty)。 値の書込みで分類し直し、
 *     FLDENV/FRSTOR で読んだタグはそのまま残す (#3688)。 f80 の非正規・指数域外は f64 で表せないので分類が native と違う (ADR 制限)。 */
#ifndef OTT_X87_H
#define OTT_X87_H
#include "ott_cpu.h"

static double ott_fst[8];          /* 物理 8 本。ST(i) = ott_fst[(ott_ftop + i) & 7] */
static unsigned ott_ftop;          /* TOP */
static uint16_t ott_fcw = 0x037f;  /* FCW (既定値) */
static uint16_t ott_fsw;           /* C0 (bit 8) / C2 (bit 10) / C3 (bit 14) のみ。TOP は ott_ftop から合成 */
static uint8_t ott_tag[8] = {3, 3, 3, 3, 3, 3, 3, 3};   /* 物理レジスタごとの TW 2 bit (3 = empty) */

#define OTT_X87_CMASK 0x4700u      /* C3|C2|C1|C0 */

static inline unsigned x87_cls(double v) { return v == 0 ? 1u : (isnan(v) || isinf(v)) ? 2u : 0u; }

static inline double x87_st(unsigned i) { return ott_fst[(ott_ftop + i) & 7]; }
static inline void x87_set(unsigned i, double v) {
    unsigned p = (ott_ftop + i) & 7;
    ott_fst[p] = v; ott_tag[p] = (uint8_t)x87_cls(v);
}
static inline void x87_push(double v) {
    ott_ftop = (ott_ftop - 1) & 7;
    ott_fst[ott_ftop] = v; ott_tag[ott_ftop] = (uint8_t)x87_cls(v);
}
static inline void x87_pop(void) { ott_tag[ott_ftop] = 3; ott_ftop = (ott_ftop + 1) & 7; }
static inline uint16_t x87_fsw(void) { return (uint16_t)((ott_fsw & OTT_X87_CMASK) | (ott_ftop << 11)); }
/* FXCH ST(i): 物理レジスタの値とタグを入れ替える */
static inline void x87_fxch(unsigned i) {
    unsigned a = ott_ftop & 7, b = (ott_ftop + i) & 7;
    double t = ott_fst[a]; ott_fst[a] = ott_fst[b]; ott_fst[b] = t;
    uint8_t u = ott_tag[a]; ott_tag[a] = ott_tag[b]; ott_tag[b] = u;
}

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

/* 比較 → C3/C2/C0 (SDM: > は 000、< は 001、= は 100、unordered は 111)。 C1 は 0 (native 実測: 比較命令の後の C1 は常に 0) */
static inline void x87_fcom(double a, double b) {
    uint16_t c;
    if (a != a || b != b) c = 0x4500;
    else if (a > b) c = 0;
    else if (a < b) c = 0x0100;
    else c = 0x4000;
    ott_fsw = (uint16_t)((ott_fsw & ~OTT_X87_CMASK) | c);
}

/* FXAM: 分類を C3/C2/C0 へ (SDM: NaN 001・有限 010・inf 011・zero 100)、符号を C1 へ。
 * double の非正規は f80 では正規値なので 010 にする */
static inline void x87_fxam(void) {
    double v = x87_st(0);
    uint16_t c;
    if (v != v) c = 0x0100;
    else if (isinf(v)) c = 0x0500;
    else if (v == 0) c = 0x4000;
    else c = 0x0400;
    if (signbit(v)) c |= 0x0200;
    ott_fsw = (uint16_t)((ott_fsw & ~OTT_X87_CMASK) | c);
}

/* FSCALE: ST(0) *= 2^trunc(ST(1))。 指数は ±65536 に丸める (double の指数域外は inf / 0 になる: ADR 制限) */
static inline void x87_fscale(void) {
    double n = x87_st(1);
    if (n != n) { x87_set(0, n); return; }
    n = trunc(n);
    if (n > 65536.0) n = 65536.0;
    if (n < -65536.0) n = -65536.0;
    x87_set(0, ldexp(x87_st(0), (int)n));
}

/* x87 の default NaN (負の quiet NaN。 f80 の 0xFFFF C000… に対応する) */
static inline double x87_indef(void) {
    uint64_t b = 0xfff8000000000000ULL; double d;
    memcpy(&d, &b, 8);
    return d;
}

/* FSIN/FCOS: |ST(0)| < 2^63 のときだけ計算して C2 = 0。 有限の範囲外は ST(0) を変えず C2 = 1。 ±inf は C2 = 0 で default NaN (native 実測) */
static inline void x87_trig(int cosine) {
    double v = x87_st(0);
    if (isinf(v)) { ott_fsw = (uint16_t)(ott_fsw & ~0x0400u); x87_set(0, x87_indef()); return; }
    if (fabs(v) >= 9223372036854775808.0) { ott_fsw |= 0x0400; return; }
    ott_fsw = (uint16_t)(ott_fsw & ~0x0400u);
    x87_set(0, cosine ? cos(v) : sin(v));
}

/* F2XM1: ST(0) = 2^ST(0) - 1 (|ST(0)| <= 1)。 expm1 で小さい値の桁落ちを避ける。 ln2 は hi/lo に分けて引数の丸めを抑える */
static inline void x87_f2xm1(void) {
    double x = x87_st(0);
    x87_set(0, expm1(x * 0.693147180559945286226764 + x * 2.319046813846299558e-17));
}

/* 生成 C の入口 (x64c が呼ぶ)。 検証した定義域の外は計算値を返さず fail-fast (ott_unsup) する。
 * 定義域外の数値は x87_trig / x87_f2xm1 (数値核) だけが持つ。 差分試験 (OTT_X87_DOMAIN_SOFT) は定義域外の呼び出しを数えて計算を続ける。 */
#ifdef OTT_X87_DOMAIN_SOFT
extern unsigned long ott_x87_dom_hits;
#define X87_DOM_FAIL(addr, what) (ott_x87_dom_hits++)
#else
#define X87_DOM_FAIL(addr, what) ott_unsup((addr), (what))
#endif
#define X87_TRIG_DOM 0.7853981633974483   /* fsin/fcos の計算域 |ST0| <= pi/4 (定義域の上限は PM 判断待ち・既定案) */
static inline void x87_trig_at(int cosine, uint64_t addr) {
    double v = x87_st(0);
    if (isfinite(v) && fabs(v) > X87_TRIG_DOM && fabs(v) < 9223372036854775808.0)
        X87_DOM_FAIL(addr, "fsin/fcos: |arg| > pi/4 outside the verified domain (66-bit pi reduction not modeled)");
    x87_trig(cosine);
}
static inline void x87_f2xm1_at(uint64_t addr) {
    if (fabs(x87_st(0)) > 1.0) X87_DOM_FAIL(addr, "f2xm1: |arg| > 1 outside the verified domain");
    x87_f2xm1();
}

/* FYL2X: ST(1) = ST(1) * log2(ST(0)) を計算してから pop。 ST(0) < 0 は default NaN */
static inline void x87_fyl2x(void) {
    double x = x87_st(0), y = x87_st(1), r;
    if (x != x) r = x;
    else if (y != y) r = y;
    else if (x < 0) r = x87_indef();
    else r = y * log2(x);
    x87_set(1, r);
    x87_pop();
}

/* FPREM: 指数差 e < 64 なら完全 (C2 = 0)。 商の下位 3 bit (|Q|) を C0 (Q2)・C3 (Q1)・C1 (Q0) に入れる。
 * e >= 64 は部分剰余 (C2 = 1・商のビットは 0): 除数を 2^s 倍 (s = 32・(floor(e/32) - 1)、native 実測) して 1 回だけ減らし、
 * 残りの指数差は [32, 64) になる。 ST(1) = 0・ST(0) = inf は default NaN */
static inline void x87_fprem(void) {
    double a = x87_st(0), b = x87_st(1), r;
    uint16_t c = 0;
    if (a != a || b != b) r = a != a ? a : b;
    else if (isinf(a) || b == 0) r = x87_indef();
    else if (isinf(b) || a == 0) r = a;
    else {
        int e = ilogb(a) - ilogb(b), q;
        double m = fabs(b), aa = fabs(a), rr;
        if (e >= 64) { m = ldexp(m, 32 * ((e >> 5) - 1)); c = 0x0400; }
        rr = fmod(aa, m);
        if (!(c & 0x0400)) {
            q = (int)nearbyint((fmod(aa, 8.0 * m) - rr) / m) & 7;
            c |= ((q & 4) ? 0x0100 : 0) | ((q & 2) ? 0x4000 : 0) | ((q & 1) ? 0x0200 : 0);
        }
        r = copysign(rr, a);
    }
    x87_set(0, r);
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

/* ---- 状態の保存・復元 (#3688)。 環境 28 B (32bit 保護): CW @0・SW @4・TW @8。 FIP/FCS/FOO/FOS (12..27) は未モデル (0) ---- */
static inline uint16_t x87_tw(void) {
    uint16_t tw = 0;
    for (unsigned p = 0; p < 8; p++) tw |= (uint16_t)(ott_tag[p] << (2 * p));
    return tw;
}

/* FNSTENV: 格納後は全例外をマスクする (FCW |= 0x3f) */
static inline void x87_fnstenv(uint8_t* e) {
    uint16_t cw = ott_fcw, sw = x87_fsw(), tw = x87_tw();
    memset(e, 0, 28);
    memcpy(e, &cw, 2); memcpy(e + 4, &sw, 2); memcpy(e + 8, &tw, 2);
    ott_fcw |= 0x3f;
}

/* FLDENV: CW・TOP・C0/C2/C3 を戻し、タグは読んだ TW をそのまま使う (値は書き換えない) */
static inline void x87_load_env(const uint8_t* e) {
    uint16_t cw, sw, tw;
    memcpy(&cw, e, 2); memcpy(&sw, e + 4, 2); memcpy(&tw, e + 8, 2);
    ott_fcw = cw;
    ott_ftop = (sw >> 11) & 7;
    ott_fsw = sw & OTT_X87_CMASK;
    for (unsigned p = 0; p < 8; p++) ott_tag[p] = (uint8_t)((tw >> (2 * p)) & 3);
}
static inline void x87_fldenv(const uint8_t* e) { x87_load_env(e); }

/* FNSAVE: 環境 28 B + ST(0..7) 各 80bit (f64 → f80 で書く。 empty は 0)。 格納後は FINIT (FCW=037f・FSW=0・TOP=0・全 empty) */
static inline void x87_fnsave(uint8_t* b) {
    x87_fnstenv(b);
    for (unsigned i = 0; i < 8; i++) {
        unsigned p = (ott_ftop + i) & 7;
        if (ott_tag[p] != 3) x87_f64_to_f80(ott_fst[p], b + 28 + 10 * i);
        else memset(b + 28 + 10 * i, 0, 10);
    }
    ott_fcw = 0x037f; ott_fsw = 0; ott_ftop = 0;
    for (unsigned p = 0; p < 8; p++) ott_tag[p] = 3;
}

/* FRSTOR: 環境を読み、ST(0..7) を物理レジスタへ戻す (f80 → f64)。 タグは TW のまま */
static inline void x87_frstor(const uint8_t* b) {
    x87_load_env(b);
    for (unsigned i = 0; i < 8; i++) ott_fst[(ott_ftop + i) & 7] = x87_f80_to_f64(b + 28 + 10 * i);
}

#endif
