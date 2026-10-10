/* m9_boot.c (M9): 起動経路 [F3][F4][F5] と CRT 数学 [F6] の C 忠実 port.
 * すべて dsm (tools/m9/work/*.dsm) に基づき op 順/丸めを保持:
 *   - float/double 演算は op 単位 f32/f64 丸め (emcc 既定: -msse2 相当の f32 op)。
 *   - const 値は実行モジュール rdata (m9_dumpconsts.mjs) と dsm byte 突合済み。
 *
 * 注意: linear メモリ上の object pointer は u32 (< 0x10000000) で表現される
 * (wasm linear address)。qword 読みは下位 32bit を pointer として扱う (native で
 * は 64bit heap address だが wasm では upper 32 = 0 の値が入る)。
 */

#include <math.h>
#include <stdint.h>
#include <string.h>

typedef union { uint64_t u; double d; } u64f;
typedef union { uint32_t u; float f; } u32f;

static inline double b2d(uint64_t b) { u64f x; x.u = b; return x.d; }
static inline uint64_t d2b(double d) { u64f x; x.d = d; return x.u; }
static inline float b2f(uint32_t b) { u32f x; x.u = b; return x.f; }
static inline uint32_t f2b(float f) { u32f x; x.f = f; return x.u; }

/* ---------------------------------------------------------------- [F6] CRT */

/* fail-fast 追跡用: 固定 scratch メモリに書く (probe から CUDA HEAPU8 で読む)。
 * SCRATCH = 0x35e00000 (linear 直書; どこにも使われていないこと確認済) */
#define MSCR ((volatile uint32_t *)0x35e00000)
#define MTRACE(n) do { MSCR[(n)] = 0x9a5f0000u | (uint32_t)__LINE__; } while (0)

uint64_t m9_dexp(uint64_t xb) { return d2b(exp(b2d(xb))); }   /* 1801b4220 (IR: i64(i64)) */
uint64_t m9_dlog(uint64_t xb) { return d2b(log(b2d(xb))); }   /* 1801b4900 */
uint64_t m9_dlog2(uint64_t xb) { return d2b(log2(b2d(xb))); }
uint64_t m9_dtan(uint64_t xb) { return (uint64_t)f2b((float)tan(b2d(xb))); } /* 1801ba860 */
uint64_t m9_datan(uint64_t xb) { return d2b(atan(b2d(xb))); }

/* 1801bc890 = powf(f32 xmm0, f32 xmm1) — f32 bits pair の i64 (upper=a, lower=b) */
uint64_t m9_fpow2(uint64_t x) {
  uint32_t ab = (uint32_t)(x >> 32), bb = (uint32_t)(x & 0xffffffffu);
  return (uint64_t)f2b(powf(b2f(ab), b2f(bb)));
}

/* ----------------------------------------------------------- [F5] gate box graph
 * box (0xc0): [0x00]=outer vt (0x1802055f8), [0x18]/[0x38]=sub1/sub2 (vt 0x1802055c0),
 *   [0x98]=sub3 (同 vt)。sub 内: [8]/[0x10] f64 param ×2, [0x18] = exp 重み,
 *   [x+8] 読みは [x+0x18] の exp 計算に効く。
 */

/* function_180126590 忠実: [sub+0x18] = exp( f64@[rip const](= -1000.0) / ([0x10]*[8]) ) */
static void m9_sub_recalc(uint32_t subp) {
  MTRACE(20);
  double a = b2d(*(uint64_t *)(uintptr_t)(subp + 0x10));
  double b = b2d(*(uint64_t *)(uintptr_t)(subp + 8));
  MTRACE(21);
  double r = exp(-1000.0 / (a * b));
  MTRACE(22);
  *(uint64_t *)(uintptr_t)(subp + 0x18) = d2b(r);
  MTRACE(23);
}

/* [rax+0x38] = function_180126370 composite:
 *   call 126610 (rcx) → sub1 (+0x18) に [sub+8] = xmm1 (126650) → 126590
 *   → sub2 (+0x38) に同 xmm6 → 126650 → 126590
 */
static void m9_gbox_cfg1(uint32_t boxp, double v) {
  MTRACE(30);
  uint32_t sub1 = boxp + 0x18;
  uint32_t sub2 = boxp + 0x38;
  MTRACE(31);
  *(uint64_t *)(uintptr_t)(sub1 + 8) = d2b(v);
  MTRACE(32);
  m9_sub_recalc(sub1);
  MTRACE(33);
  *(uint64_t *)(uintptr_t)(sub2 + 8) = d2b(v);
  MTRACE(34);
  m9_sub_recalc(sub2);
  MTRACE(35);
}

/* [rax+0x88] = function_1801263e0 → rcx += 0x98; [sub3+0x10] = xmm1; jmp [vt+0x28] (=126590) */
static void m9_gbox_cfg2(uint32_t boxp, double v) {
  MTRACE(40);
  uint32_t sub3 = boxp + 0x98;
  MTRACE(41);
  *(uint64_t *)(uintptr_t)(sub3 + 0x10) = d2b(v);
  MTRACE(42);
  m9_sub_recalc(sub3);
  MTRACE(43);
}

/* [rax+0x80] = function_180126340: [box+0x90] = 0; [box+0xb8] = 0x3abef2d0f5da7dd9 */
static void m9_gbox_reset(uint32_t boxp) {
  *(uint64_t *)(uintptr_t)(boxp + 0x90) = 0;
  *(uint64_t *)(uintptr_t)(boxp + 0xb8) = 0x3abef2d0f5da7dd9ULL;
}

/* function_1801263f0 (rcx, xmm1, xmm2, xmm3) 忠実 C port; dsm 0x1801263f0..4d7:
 *   rax 都座標: [0x00] = 0x1802055f8 (vt); [0x18]/[0x38] = 0x1802055c0
 *   [0x28] = xmm1 (a1)
 *   xmm0 = -1000.0 (0x1801f3ac0); xmm1 *= xmm3 (a3); xmm0 /= xmm1; exp → [0x30]
 *   [0x48] = xmm2 (a2); xmm7 = xmm2 * xmm3; [0x40] = xmm3 (a3); [0x10] = xmm3
 *   [0x50] = exp(-1000.0 / (xmm2 * xmm3))
 *   f32 系: [0x08] = powf(10.0f, f32@(0x1802056e0 = -0.0202))
 *           [0x0c] = 1.0f - powf(10.0f, f32@(0x1802056e4 = -3.5))
 *  */
void m9_box1263f0bits(uint64_t boxp64, uint64_t b1, uint64_t b2, uint64_t b3) {
  uint32_t boxp = (uint32_t)boxp64;
  double a1 = b2d(b1), a2 = b2d(b2), a3 = b2d(b3);
  *(uint64_t *)(uintptr_t)(boxp + 0x00) = 0x1802055f8ULL;
  *(uint64_t *)(uintptr_t)(boxp + 0x18) = 0x1802055c0ULL;
  *(uint64_t *)(uintptr_t)(boxp + 0x38) = 0x1802055c0ULL;
  *(uint64_t *)(uintptr_t)(boxp + 0x28) = d2b(a1);
  double d0 = -1000.0 / (a1 * a3);
  double r0 = exp(d0);
  *(uint64_t *)(uintptr_t)(boxp + 0x30) = d2b(r0);
  *(uint64_t *)(uintptr_t)(boxp + 0x48) = d2b(a2);
  double xmm7 = a2 * a3;                                   /* mulsd xmm7, xmm8 */
  *(uint64_t *)(uintptr_t)(boxp + 0x40) = d2b(a3);
  *(uint64_t *)(uintptr_t)(boxp + 0x10) = d2b(a3);
  double d1 = -1000.0 / xmm7;
  double r1 = exp(d1);
  *(uint64_t *)(uintptr_t)(boxp + 0x50) = d2b(r1);
  float fA = 10.0f;                     /* dsm 0x180126470 [rip+0xd0cb8] → 0x1801f7130 */
  /* xmm1 const 実測: [rip+0xdf260]→0x1802056e0 実測 f32 bits 0xbca57a78 */
  float fB = b2f(0xbca57a78U);
  float fC = b2f(0xc0600000U);          /* [rip+0xdf249] → 0x1802056e4 */
  float fD = 1.0f;                      /* [rip+0xc8368] → 0x1801ee818 */
  float p1 = powf(fA, fB);
  *(uint32_t *)(uintptr_t)(boxp + 8) = f2b(p1);
  float p2 = fD - powf(fA, fC);
  *(uint32_t *)(uintptr_t)(boxp + 0xc) = f2b(p2);
}

/* function_1801264e0 (rcx, xmm1, xmm2) 忠実: [0x10]=xmm1; [8]=xmm2; [0x18]=exp(-1000/(b1*b2)) */
void m9_box1264e0bits(uint64_t boxp64, uint64_t b1, uint64_t b2) {
  uint32_t boxp = (uint32_t)boxp64;
  double a1 = b2d(b1), a2 = b2d(b2);
  *(uint64_t *)(uintptr_t)(boxp + 0x10) = d2b(a1);
  *(uint64_t *)(uintptr_t)(boxp + 8) = d2b(a2);
  double r = exp(-1000.0 / (a1 * a2));
  *(uint64_t *)(uintptr_t)(boxp + 0x18) = d2b(r);
}

/* [F5] ctor の gate box vcall cluster の統合呼出. dsm 順袈:
 *   cluster1 (0x18011d546 + 0x18011d58a): cfg1((double)[obj+0x268]) + cfg2(10.0 f64@0x1801f3a88)
 *   cluster2 (0x18011d9f0):               cfg1(44100.0 f64@0x1801ee890)
 *   cluster3 (0x18011da60):               reset
 * 呼出位置 = ctor の setParameter defaults loop 直前 (anchor in ir9).
 */
uint64_t m9_gbox_ctor_setup(uint64_t objp64) {
  uint32_t objp = (uint32_t)objp64;
  MTRACE(1);
  float srr = *(float *)(uintptr_t)(objp + 0x268);   /* ctor clamp 後の値 ([obj+0x18] を clamped) */
  double sd = (double)srr;
  for (int k = 0; k < 3; k++) {
    uint32_t boxp = (uint32_t)(*(uint64_t *)(uintptr_t)(objp + 0x200 + 8 * k));
    MTRACE(2);
    m9_gbox_cfg1(boxp, sd);
    MTRACE(3);
    m9_gbox_cfg2(boxp, 10.0);    /* dsm xmm6 const (0x1801f3a88) */
  }
  MTRACE(4);
  for (int k = 0; k < 3; k++) {
    uint32_t boxp = (uint32_t)(*(uint64_t *)(uintptr_t)(objp + 0x200 + 8 * k));
    m9_gbox_cfg1(boxp, 44100.0); /* dsm cluster2 (44100.0 f64@0x1801ee890) */
    m9_gbox_reset(boxp);         /* cluster3 */
  }
  MTRACE(5);
  return 0;
}

/* ---------------------------------------------------------------- [F4] SVF set */

void m9_svf_reset(uint64_t svfpr, uint64_t f0bits, uint64_t qbits) {
  uint32_t svfp = (uint32_t)svfpr;
  /* function_180126040 忠実: xmm1 = f0 (f32), xmm2 = Q (f32), SVF.SR = [rcx+0x2c] */
  float srr = *(float *)(uintptr_t)(svfp + 0x2c);
  double srd = (double)srr;
  double f0d = (double)b2f((uint32_t)f0bits);
  double ang = f0d * 3.14159265358979323846264338327950288;
  ang = ang / srd;
  float T = (float)tan(ang);       /* 1801ba860 戻値は f32 (vcvtsd2ss) */
  float Q = b2f((uint32_t)qbits);
  *(float *)(uintptr_t)(svfp + 0) = T;
  float iq = 1.0f / Q;
  *(float *)(uintptr_t)(svfp + 4) = iq;
  float denom = (iq + T) * T + 1.0f;
  float a = 1.0f / denom;
  *(float *)(uintptr_t)(svfp + 0x10) = a;
  *(float *)(uintptr_t)(svfp + 0x14) = a * T;
  *(float *)(uintptr_t)(svfp + 0x18) = a * T * T;
}

/* ---------- [F8] band filter setup (function_180126670, dsm 0x180126670..91e) ----------
 * (rcx = band state, xmm1 = f0 f32): 4th-order butterworth 等価の 多項式係数計算。
 * 全 f64 op を dsm 頤通りトレース。定数実測 (m9_const3):
 *   π̂ = 22/7 = 3.1428571428571427937, 2π̂ = 44/7 = 6.2857142857142855874,
 *   6.0 / 4.0 / 8.0 / -4.0 / √2 = sqrtpd。
 * tan は native poly (0x1801a9be0) の C tan() 代替 (ulp 差あり → REPORT tolerance)。
 * SR = f64[st+0xb8] (ctor 0x18011d635 で f32[obj+0x268] を cvtps2pd し格納済み)。 */
void m9_band_filter_setup(uint64_t stp64, uint64_t f0bits) {
  uint32_t st = (uint32_t)stp64;
  double srr = *(double *)(uintptr_t)(st + 0xb8);
  MTRACE(50);
  double v0 = b2f((uint32_t)f0bits);                   /* f0d */
  double W = v0 * 3.1428571428571427937;               /* xmm0 = f0d·π̂ */
  double W2 = v0 * 6.2857142857142855874;              /* xmm6 = f0d·2π̂ */
  double v1, v2, v8, v13, v5, v4, v3, v9, v6, v11, v14, v10 = 4.0, v12;
  v9 = sqrt(2.0);                                      /* sqrtpd(2.0) */
  v11 = W2; v11 = v11 * W2;                            /* W2² */
  v14 = v11; v14 = v14 * v11;                          /* W2⁴ */
  v0 = tan(W / srr);                                   /* tan(ω); ω = f0d·π̂/SR */
  v1 = W2 / v0;                                        /* C1 = W2 / tan(ω) */
  v2 = v14;                                            /* xmm2 = W2⁴ (0x18012671f) */
  v8 = v11; v8 = v8 * W2;                              /* W2³ */
  v6 = W2 * v9;                                        /* W2√2 */
  v13 = v1 * v1;                                       /* C1² */
  v5 = v13; v5 = v5 * v1;                              /* C1³ */
  v8 = v8 * v9;                                        /* W2³√2 */
  v9 = v11;                                            /* v9 = W2² */
  v11 = v11 * 8.0;                                     /* 8W2² */
  v5 = v5 * v6;                                        /* C1³W2√2 */
  v8 = v8 * v1;                                        /* W2³√2C1 */
  v1 = v14; v1 = v1 * v10;                             /* 4W2⁴ */
  v4 = v5;
  v3 = v8;
  v11 = v11 * v13;                                     /* 8W2²C1² */
  v3 = v3 + v8;                                        /* 2W2³√2C1 */
  v0 = v8; v0 = v0 + v14;                              /* W2³√2C1 + W2⁴ */
  v9 = v9 * v13;                                       /* 4W2²C1² */
  v4 = v4 + v5;                                        /* 2C1³W2√2 */
  v6 = v13; v6 = v6 * 6.0;                             /* 6C1⁴ */
  v1 = v1 - v8;                                        /* 4W2⁴ - W2³√2C1 */
  v0 = v0 - v13;                                       /* ... - C1⁴ */
  v12 = v3;
  v12 = v12 + v9;                                      /* K a */
  v1 = v1 + v5;                                        /* + C1³W2√2 */
  v0 = v0 - v5;                                        /* ... - C1³W2√2 */
  v12 = v12 + v13;                                     /* + C1⁴ */
  v1 = v1 - v13;                                       /* ... - C1⁴ */
  v0 = v0 * v10;                                       /* v0 = 4(...) */
  v12 = v12 + v4;                                      /* + 2C1³W2√2 */
  v1 = v1 * v10;                                       /* v1 = 4(...) */
  v12 = v12 + v14;                                     /* + W2⁴ → K */
  v0 = v0 / v12;                                       /* A16 */
  v1 = v1 / v12;                                       /* B16 */
  *(double *)(uintptr_t)(st + 0x98) = v0;
  v0 = v2; v0 = v0 - v11;                              /* 6W2⁴ - 8W2²C1² */
  *(double *)(uintptr_t)(st + 0xa8) = v1;
  v2 = v2 / v12;                                       /* C16 = 6W2⁴/K */
  v0 = v0 + v6;                                        /* + 6C1⁴ */
  *(double *)(uintptr_t)(st + 0x78) = v2;
  v0 = v0 / v12;                                       /* A32 */
  *(double *)(uintptr_t)(st + 0xa0) = v0;
  v0 = v13; v0 = v0 - v3;                              /* C1⁴ - 2W2³√2C1 */
  v0 = v0 + v14;                                       /* + W2⁴ */
  v0 = v0 - v4;                                        /* - 2C1³W2√2 */
  v0 = v0 + v9;                                        /* + 4W2²C1² */
  v0 = v0 / v12;                                       /* B32 */
  *(double *)(uintptr_t)(st + 0xb0) = v0;
  v0 = v14; v0 = v14 / v12;                            /* D1 = W2⁴/K */
  v14 = v14 * v10;                                     /* 4W2⁴ */
  *(double *)(uintptr_t)(st + 0x68) = v0;
  *(double *)(uintptr_t)(st + 0xc8) = v0;
  v0 = v13;
  v14 = v14 / v12;                                     /* C1c = 4W2⁴/K */
  *(double *)(uintptr_t)(st + 0x70) = v14;
  *(double *)(uintptr_t)(st + 0xc0) = v14;
  v13 = v13 * (-4.0);                                  /* -4C1⁴ */
  for (int k = 8; k <= 0x60; k += 8) *(uint64_t *)(uintptr_t)(st + k) = 0;  /* 履歴 0x8..0x60 = 0 */
  v13 = v13 / v12;                                     /* D2 = -4C1⁴/K */
  v6 = v6 / v12;                                       /* E2 = 6C1⁴/K */
  v0 = v0 / v12;                                       /* C1⁴/K (0x853 の分) */
  *(double *)(uintptr_t)(st + 0x88) = v13;
  *(double *)(uintptr_t)(st + 0xd0) = v13;
  *(double *)(uintptr_t)(st + 0x90) = v6;
  *(double *)(uintptr_t)(st + 0x80) = v0;
  *(double *)(uintptr_t)(st + 0xd8) = v0;
  MTRACE(51);
}

void m9_resume_reinit(uint64_t objpr) {
  uint32_t objp = (uint32_t)objpr;
  MTRACE(10);
  /* dsm 0x180120814..947 忠実:
   *  SRraw = f32[obj+0x18] (native VT+0xf8 = 18011ebb0 は [rcx+0x18] 読み)
   *  comiss 44000.0 vs SRraw: jbe (44000 <= SR) 取 → 0x268 は raw のまま
   *  非 take (= 44000 > SR) → store 44100
   */
  float srr = *(float *)(uintptr_t)(objp + 0x18);
  float sre = (44000.0f <= srr) ? srr : 44100.0f;
  *(uint32_t *)(uintptr_t)(objp + 0x268) = f2b(sre);
  *(uint32_t *)(uintptr_t)(objp + 0x304) = 2;
  *(uint32_t *)(uintptr_t)(objp + 0x308) = 2;
  *(uint32_t *)(uintptr_t)(objp + 0x30c) = 1;
  *(uint32_t *)(uintptr_t)(objp + 0x310) = 1;
  *(uint64_t *)(uintptr_t)(objp + 252) = 0;   /* 0xfc */
  *(uint64_t *)(uintptr_t)(objp + 244) = 0;   /* 0xf4 */
  *(uint64_t *)(uintptr_t)(objp + 260) = 0;   /* 0x104 */
  *(uint64_t *)(uintptr_t)(objp + 272) = 0;   /* 0x110 */
  *(uint32_t *)(uintptr_t)(objp + 284) = 0;   /* 0x11c (dsm 0x1801208d1 0x118) */
  *(uint32_t *)(uintptr_t)(objp + 268) = 0;   /* 0x10c */
  *(uint32_t *)(uintptr_t)(objp + 0x2ac) = 2; /* dsm 0x180120953 (脱落分) */
  /* 4 ramp gains: gain = 44100/(SR_eff*300 + 44100) — dsm 0x1801208bf..947 */
  float g = 44100.0f / (sre * 300.0f + 44100.0f);
  for (int k = 0; k < 4; k++) {
    uint32_t p = (uint32_t)(*(uint64_t *)(uintptr_t)(objp + 648 + 8 * k));
    *(float *)(uintptr_t)(p + 4) = g;
  }
  MTRACE(11);
  /* gate box cluster 再構成 (dsm 0x18012096b..9ab):
   *   for 3 boxes [obj+0x200+8k]: [vt+0x38] (xmm1 = SR_eff f64) = cfg1,
   *                              [vt+0x88] (xmm6 = 10.0 f64 @0x1801f3a88) = cfg2
   *   (native は ramp gain 直後, SVF init の前に走る) */
  for (int k = 0; k < 3; k++) {
    uint32_t boxp = (uint32_t)(*(uint64_t *)(uintptr_t)(objp + 0x200 + 8 * k));
    m9_gbox_cfg1(boxp, (double)sre);
    m9_gbox_cfg2(boxp, 10.0);
  }
  /* SVF init (0x180120a00..a35) */
  MTRACE(12);
  for (int k = 0; k < 16; k++) {
    uint32_t s = (uint32_t)(*(uint64_t *)(uintptr_t)(objp + 0x180 + 8 * k));
    *(uint32_t *)(uintptr_t)(s + 0x2c) = f2b(sre);
    *(uint64_t *)(uintptr_t)(s + 8) = 0;
    float f = (k < 8) ? b2f(0x42b0999aU) : b2f(0x451c4000U);
    m9_svf_reset(s, f2b(f), f2b(1.0f / sqrtf(2.0f)));   /* xmm6 = 1.0f/sqrt(2.0f) */
  }
  MTRACE(13);
  *(uint32_t *)(uintptr_t)(objp + 0x2a8) = 0;   /* dsm 0x180120a37 */
  /* ring memset (0x180120a37..a92) — [0x250]/[0x258] は array pointer 経由 (dsm 0x180120a4f: [rsi+rcx]) */
  MTRACE(14);
  {
    uint32_t arr = (uint32_t)(*(uint64_t *)(uintptr_t)(objp + 0x250));
    for (int k = 0; k < 6; k++) {
      uint32_t p = (uint32_t)(*(uint64_t *)(uintptr_t)(arr + 8 * k));
      memset((void *)(uintptr_t)p, 0, 0x40000);
    }
  }
  MTRACE(15);
  {
    uint32_t arr = (uint32_t)(*(uint64_t *)(uintptr_t)(objp + 0x258));
    for (int k = 0; k < 8; k++) {
      uint32_t p = (uint32_t)(*(uint64_t *)(uintptr_t)(arr + 8 * k));
      memset((void *)(uintptr_t)p, 0, 0x40000);
    }
  }
  MTRACE(16);
}
