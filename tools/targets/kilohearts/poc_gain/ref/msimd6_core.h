/* msimd6_core.h — msimd6.c (__asm_* helper 完全版) の共通型定義 + inline 素材.
 * M6b (2026-10): gen_msimd6.py が msimd6.c を生成する際に要求する型 (u128/u64/u32/
 * u8/i32/i64/i256x) と lane 操作 inline をここで提供する (旧 msimd6_core.h は空
 * 0 byte で, これが m6_build.sh が m5/msimd.c にフォールバックしていた直接原因)。
 *
 * 型対応 (RetDec lift IR 宣言型 → C 型; 符号は bit 転写専用のため符号なし統一):
 *   i128 → u128 (unsigned __int128), i64 → u64, i32 → u32, i8 → u8, i32s → i32,
 *   i256 → i256x (*)。
 *
 * (*): i256 は C に正体型がない (_BitInt(256) は emcc 6 clang で >128bit 非対応)。
 *     IR 側 (m6_memfix.py) が function_1801a2a20 (=CRT memmove) の define 全体を
 *     C 実装へ置換するため, i256 系 __asm_vmovdqu/vmovdqa/vmovntdq の呼出 site は
 *     build IR から消滅する。よって i256 系の関数定義は生成しない。
 *
 * bit-exact 規約: f32/f64 演算は IEEE round-to-nearest (wasm f32/f64 と同精度),
 * FMA は fma() (単一丸め; FMA3 hardware 等価)。MXCSR 系 (stmxcsr/ldmxcsr) は
 * wasm で rounding mode 制御不可のため no-op (native 側は DLL 実機のまま)。
 * comis/ucomis 系は void (CF/ZF/PF は ir6_pass.py [P1] が IR level で解決)。
 */
#ifndef MSIMD6_CORE_H
#define MSIMD6_CORE_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#if defined(__EMSCRIPTEN__)
#include <emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

typedef unsigned __int128  u128;
typedef unsigned long long u64;
typedef long long          i64;
typedef unsigned int       u32;
typedef unsigned char      u8;
typedef int                i32;

/* 32 byte 疑似 vector — msimd6.c 単体コンパイルのための純粋 placeholder。
 * (IR 側 m6_memfix.py が i256 呼出 site を消すため, この型は定義に現れない) */
typedef struct { u128 lo, hi; } i256x;

typedef float  v4f __attribute__((vector_size(16)));
typedef double v2d __attribute__((vector_size(16)));
typedef int    v4i __attribute__((vector_size(16)));
typedef unsigned char v16b __attribute__((vector_size(16)));

/* ---- bit 転写素材 ---- */
static inline double lane0_d(u128 a) { double v; memcpy(&v, &a, 8); return v; }
static inline float  lane0_f(u128 a) { float  v; memcpy(&v, &a, 4); return v; }
static inline u64    lane0_u(u128 a) { return (u64)a; }
static inline u64    lane1_u(u128 a) { return (u64)(a >> 64); }
static inline double asd(u64 bits)   { double v; memcpy(&v, &bits, 8); return v; }
static inline float  asf(u32 bits)   { float  v; memcpy(&v, &bits, 4); return v; }
static inline u64    das(double d)   { u64 v; memcpy(&v, &d, 8); return v; }
static inline u32    fas(float f)    { u32 v; memcpy(&v, &f, 4); return v; }
static inline u128 set_u64_lo(u64 v) { u128 r = 0; memcpy(&r, &v, 8); return r; }
static inline u128 set_u32_lo(u32 v) { u128 r = 0; memcpy(&r, &v, 4); return r; }
static inline u128 lane0f_set(u128 a, float f)  { u128 r = a; memcpy(&r, &f, 4); return r; }
static inline u128 lane0d_set(u128 a, double d) { u128 r = a; memcpy(&r, &d, 8); return r; }
static inline u128 lane1f_set(u128 a, float f)  { u128 r = a; memcpy((char*)&r + 4, &f, 4); return r; }
static inline u128 lane1d_set(u128 a, double d) { u128 r = a; memcpy((char*)&r + 8, &d, 8); return r; }

/* ---- lane-wise f32/f64 op (SSE scalar 系: 上位 lane は dst 保持) ---- */
static inline u128 _laneop32(u128 a, u128 b, char op) {
    v4f a4, b4, r4; memcpy(&a4, &a, 16); memcpy(&b4, &b, 16);
    if (op == '*') r4[0] = a4[0] * b4[0];
    else if (op == '-') r4[0] = a4[0] - b4[0];
    else if (op == '/') r4[0] = a4[0] / b4[0];
    else r4[0] = a4[0] + b4[0];
    r4[1] = a4[1]; r4[2] = a4[2]; r4[3] = a4[3];
    u128 r; memcpy(&r, &r4, 16); return r;
}
static inline u128 _laneop32c(u128 a, float b0, char op) {
    v4f a4, r4; memcpy(&a4, &a, 16);
    if (op == '*') r4[0] = a4[0] * b0;
    else if (op == '-') r4[0] = a4[0] - b0;
    else if (op == '/') r4[0] = a4[0] / b0;
    else r4[0] = a4[0] + b0;
    r4[1] = a4[1]; r4[2] = a4[2]; r4[3] = a4[3];
    u128 r; memcpy(&r, &r4, 16); return r;
}
static inline u128 _laneop64(u128 a, u128 b, char op) {
    v2d a2, b2, r2; memcpy(&a2, &a, 16); memcpy(&b2, &b, 16);
    if (op == '*') r2[0] = a2[0] * b2[0];
    else if (op == '-') r2[0] = a2[0] - b2[0];
    else if (op == '/') r2[0] = a2[0] / b2[0];
    else r2[0] = a2[0] + b2[0];
    r2[1] = a2[1];
    u128 r; memcpy(&r, &r2, 16); return r;
}
static inline u128 _laneop64c2(u128 a, double b0, char op) {
    v2d a2, r2; memcpy(&a2, &a, 16);
    if (op == '*') r2[0] = a2[0] * b0;
    else if (op == '-') r2[0] = a2[0] - b0;
    else if (op == '/') r2[0] = a2[0] / b0;
    else r2[0] = a2[0] + b0;
    r2[1] = a2[1];
    u128 r; memcpy(&r, &r2, 16); return r;
}
static inline u128 _lanepd(u128 a, u128 b, char op) {
    v2d a2, b2, r2; memcpy(&a2, &a, 16); memcpy(&b2, &b, 16);
    if (op == '*') r2 = a2 * b2;
    else if (op == '-') r2 = a2 - b2;
    else if (op == '/') r2 = a2 / b2;
    else r2 = a2 + b2;
    u128 r; memcpy(&r, &r2, 16); return r;
}

/* ---- 整数 lane (q: 2x64 / d: 4x32; 桁上げは lane 内 wrap) ---- */
static inline u128 _laneaddq(u128 a, u128 b) {
    return (u128)((lane0_u(a) + lane0_u(b)) & 0xFFFFFFFFFFFFFFFFULL)
         | (((u128)(lane1_u(a) + lane1_u(b))) << 64);
}
static inline u128 _lanesubq(u128 a, u128 b) {
    return (u128)((lane0_u(a) - lane0_u(b)) & 0xFFFFFFFFFFFFFFFFULL)
         | (((u128)(lane1_u(a) - lane1_u(b))) << 64);
}
static inline u128 _lanesubd(u128 a, u128 b) {
    v4i a4, b4, r4; memcpy(&a4, &a, 16); memcpy(&b4, &b, 16);
    r4 = a4 - b4;
    u128 r; memcpy(&r, &r4, 16); return r;
}
static inline u128 _overwrite_lo64(u128 a, u64 v) { return (a & ((u128)0xFFFFFFFFFFFFFFFFULL << 64)) | (u128)v; }
static inline u128 _overwrite_hi64(u128 a, u64 v) { return (a & 0xFFFFFFFFFFFFFFFFULL) | ((u128)v << 64); }

/* ---- FMA3 132/213/231 (dst = 第1引数 a; 第3引数 c2 は double 値)。
 * fma() は単一丸めで FMA3 hardware 等価。固有特殊 (fnm: 積を負, fnm/fms 差分…) -
 * Intel 規約: 132: dst = dst*c + src2 / 213: dst = src2*dst + src3 /
 * 231: dst = src2*src3 + dst (それぞれ全 addend の +,- 変種)。 */
static inline u128 _fma132sd (u128 a, u128 b, double c) { return lane0d_set(a,  fma(lane0_d(a), c,  lane0_d(b))); }
static inline u128 _fms132sd (u128 a, u128 b, double c) { return lane0d_set(a,  fma(lane0_d(a), c, -lane0_d(b))); }
static inline u128 _fnm132sd (u128 a, u128 b, double c) { return lane0d_set(a, -fma(lane0_d(a), c, -lane0_d(b))); }
static inline u128 _fnms132sd(u128 a, u128 b, double c) { return lane0d_set(a, -fma(lane0_d(a), c,  lane0_d(b))); }
static inline u128 _fma213sd (u128 a, u128 b, double c) { return lane0d_set(a,  fma(lane0_d(b), lane0_d(a),  c)); }
static inline u128 _fms213sd (u128 a, u128 b, double c) { return lane0d_set(a,  fma(lane0_d(b), lane0_d(a), -c)); }
static inline u128 _fnm213sd (u128 a, u128 b, double c) { return lane0d_set(a, -fma(lane0_d(b), lane0_d(a), -c)); }
static inline u128 _fnms213sd(u128 a, u128 b, double c) { return lane0d_set(a, -fma(lane0_d(b), lane0_d(a),  c)); }
static inline u128 _fma231sd (u128 a, u128 b, double c) { return lane0d_set(a,  fma(lane0_d(b), c,  lane0_d(a))); }
static inline u128 _fms231sd (u128 a, u128 b, double c) { return lane0d_set(a,  fma(lane0_d(b), c, -lane0_d(a))); }
static inline u128 _fnm231sd (u128 a, u128 b, double c) { return lane0d_set(a, -fma(lane0_d(b), c, -lane0_d(a))); }
static inline u128 _fnms231sd(u128 a, u128 b, double c) { return lane0d_set(a, -fma(lane0_d(b), c,  lane0_d(a))); }

/* ---- max/min (SSE 規約: NaN はどちらか一方なら SRC2 (=b) を返す) ---- */
static inline u128 _dmax_sd(u128 a, u128 b) {
    double x = lane0_d(a), y = lane0_d(b);
    double r = (!(x == x) || !(y == y)) ? y : (x > y ? x : y);
    return lane0d_set(a, r);
}
static inline u128 _fmax_ss(u128 a, u128 b) {
    float x = lane0_f(a), y = lane0_f(b);
    float r = (x != x || y != y) ? y : (x > y ? x : y);
    return lane0f_set(a, r);
}
static inline u128 _fmin_ss(u128 a, u128 b) {
    float x = lane0_f(a), y = lane0_f(b);
    float r = (x != x || y != y) ? y : (x < y ? x : y);
    return lane0f_set(a, r);
}

/* ---- vroundsd の丸めモード (imm 低 2bit) ---- */
static inline double _round_pd(double d, int mode) {
    if (mode == 1) return floor(d);
    if (mode == 2) return ceil(d);
    if (mode == 3) return trunc(d);
    return d;   /* 0: round-to-nearest (wasm 既定 = no-op) */
}

/* ---- CMPSD (name = 'cmp<pred>sd' / 'vcmp<pred>sd'; SRC2 = m64 operand bits) ----
 * SSE predicate (RetDec は predicate を名前で分離, imm は渡さない):
 *   eq=oeq  lt=olt  le=ole  unord=uno  neq=une  nlt=uge  nle=ugt  ord=ord
 * lane0 のみ演算, 上位 lane は dst (=a) 保持, mask 64bit all-1/0。 */
static inline u128 _cmpsd_mask(u128 a, u64 cbits, int pred) {
    double x = lane0_d(a), y = asd(cbits);
    int r;
    if (pred == 0)      r = (x == y);                       /* EQ    oeq */
    else if (pred == 1) r = (x < y);                        /* LT    olt */
    else if (pred == 2) r = (x <= y);                       /* LE    ole */
    else if (pred == 3) r = (x != x || y != y);             /* UNORD uno */
    else if (pred == 4) r = (x != y);                       /* NEQ   une */
    else if (pred == 5) r = !(x < y);                       /* NLT   uge */
    else if (pred == 6) r = !(x <= y);                      /* NLE   ugt */
    else                r = (x == x && y == y);             /* ORD   ord */
    u64 m = r ? ~(u64)0 : (u64)0;
    return _overwrite_hi64(_overwrite_lo64(a, m), lane1_u(a));
}

/* 'cmplesd', 'cmpnltsd' 等の name → SSE predicate index。 */
static inline int _cmpsd_pred(const char* nm, int len) {
    const struct { char suf[8]; int p; } tbl[] = {
        {"eq", 0}, {"lt", 1}, {"le", 2}, {"unord", 3},
        {"neq", 4}, {"nlt", 5}, {"nle", 6}, {"ord", 7},
    };
    /* nm = "cmp<pred>sd": 中段 (cmp と sd の間) を切り出す。*/
    int start = 3, end = len;
    if (end > 2 && nm[end - 2] == 's' && nm[end - 1] == 'd') end -= 2;
    for (int i = 0; i < 8; i++) {
        int sl = 0; while (tbl[i].suf[sl]) sl++;
        if (end - start == sl) {
            int ok = 1;
            for (int j = 0; j < sl; j++) if (nm[start + j] != tbl[i].suf[j]) { ok = 0; break; }
            if (ok) return tbl[i].p;
        }
    }
    return 2;   /* 既知外は le (cmplesd) 相当 — 生成器が到達しない形状 */
}

#endif /* MSIMD6_CORE_H */
