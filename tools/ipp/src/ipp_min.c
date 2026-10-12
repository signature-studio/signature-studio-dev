/* 最小 IPP 互換実装 (PoC)。IEEE 単精度の素直なループ。-ffp-contract=off 必須 (FMA 融合は bit 差を生む)。
   戻り値は実 IPP (win64 dsp_ippv2_x64.dll) のオラクル観測に合わせる: NULL→-8, len<1→-6 (NULL 優先は ref 比較で確認)。 */
#include "ipp_min.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define NP1(a) if (!(a)) return ippStsNullPtrErr
#define LEN(n) if ((n) < 1) return ippStsSizeErr

IppStatus ippsMove_8u(const Ipp8u *s, Ipp8u *d, int n) { NP1(s); NP1(d); LEN(n); memmove(d, s, (size_t)n); return 0; }
IppStatus ippsMove_32f(const Ipp32f *s, Ipp32f *d, int n) { NP1(s); NP1(d); LEN(n); memmove(d, s, (size_t)n * 4); return 0; }
IppStatus ippsZero_8u(Ipp8u *d, int n) { NP1(d); LEN(n); memset(d, 0, (size_t)n); return 0; }
IppStatus ippsZero_32f(Ipp32f *d, int n) { NP1(d); LEN(n); memset(d, 0, (size_t)n * 4); return 0; }
IppStatus ippsCopy_32f(const Ipp32f *s, Ipp32f *d, int n) { NP1(s); NP1(d); LEN(n); memmove(d, s, (size_t)n * 4); return 0; }
IppStatus ippsSet_32f(Ipp32f v, Ipp32f *d, int n) { NP1(d); LEN(n); for (int i = 0; i < n; i++) d[i] = v; return 0; }
IppStatus ippsSet_32s(Ipp32s v, Ipp32s *d, int n) { NP1(d); LEN(n); for (int i = 0; i < n; i++) d[i] = v; return 0; }

IppStatus ippsAdd_32f_I(const Ipp32f *s, Ipp32f *sd, int n) { NP1(s); NP1(sd); LEN(n); for (int i = 0; i < n; i++) sd[i] = sd[i] + s[i]; return 0; }
IppStatus ippsMul_32f_I(const Ipp32f *s, Ipp32f *sd, int n) { NP1(s); NP1(sd); LEN(n); for (int i = 0; i < n; i++) sd[i] = sd[i] * s[i]; return 0; }
IppStatus ippsMul_32f(const Ipp32f *a, const Ipp32f *b, Ipp32f *d, int n) { NP1(a); NP1(b); NP1(d); LEN(n); for (int i = 0; i < n; i++) d[i] = a[i] * b[i]; return 0; }
/* 実 IPP は val==±0 を "+0 で全埋め" に短絡する (x が inf/NaN/負でも +0)。ref 観測 */
IppStatus ippsMulC_32f_I(Ipp32f v, Ipp32f *sd, int n) { NP1(sd); LEN(n); if (v == 0.f) { memset(sd, 0, (size_t)n * 4); return 0; } for (int i = 0; i < n; i++) sd[i] = sd[i] * v; return 0; }
IppStatus ippsMulC_32f(const Ipp32f *s, Ipp32f v, Ipp32f *d, int n) { NP1(s); NP1(d); LEN(n); if (v == 0.f) { memset(d, 0, (size_t)n * 4); return 0; } for (int i = 0; i < n; i++) d[i] = s[i] * v; return 0; }
/* v==0 は copy に短絡 (x=-0 が -0 のまま残る。IEEE の -0+0=+0 とは異なる) */
IppStatus ippsAddC_32f(const Ipp32f *s, Ipp32f v, Ipp32f *d, int n) { NP1(s); NP1(d); LEN(n); if (v == 0.f) { memmove(d, s, (size_t)n * 4); return 0; } for (int i = 0; i < n; i++) d[i] = s[i] + v; return 0; }
IppStatus ippsAddC_32f_I(Ipp32f v, Ipp32f *sd, int n) { NP1(sd); LEN(n); if (v == 0.f) return 0; for (int i = 0; i < n; i++) sd[i] = sd[i] + v; return 0; }
IppStatus ippsSubCRev_32f(const Ipp32f *s, Ipp32f v, Ipp32f *d, int n) { NP1(s); NP1(d); LEN(n); for (int i = 0; i < n; i++) d[i] = v - s[i]; return 0; }
IppStatus ippsSubCRev_32f_I(Ipp32f v, Ipp32f *sd, int n) { NP1(sd); LEN(n); for (int i = 0; i < n; i++) sd[i] = v - sd[i]; return 0; }
IppStatus ippsSqr_32f(const Ipp32f *s, Ipp32f *d, int n) { NP1(s); NP1(d); LEN(n); for (int i = 0; i < n; i++) d[i] = s[i] * s[i]; return 0; }
IppStatus ippsSqr_32f_I(Ipp32f *sd, int n) { NP1(sd); LEN(n); for (int i = 0; i < n; i++) sd[i] = sd[i] * sd[i]; return 0; }

/* ippvm 系 (Sqrt/Exp) は len 検査が NULL 検査より先 (ref 観測) */
IppStatus ippsSqrt_32f_A11(const Ipp32f *s, Ipp32f *d, int n) {
  LEN(n); NP1(s); NP1(d); IppStatus st = 0;
  for (int i = 0; i < n; i++) { if (s[i] < 0.f) st = ippStsSqrtNegArg; d[i] = sqrtf(s[i]); }
  return st;
}
IppStatus ippsExp_32f_A11(const Ipp32f *s, Ipp32f *d, int n) {
  LEN(n); NP1(s); NP1(d); IppStatus st = 0;
  for (int i = 0; i < n; i++) {
    float r = expf(s[i]);
    if (isfinite(s[i])) { if (isinf(r)) st = ippStsOverflow; else if (r < 1.17549435e-38f && st != ippStsOverflow) st = ippStsUnderflow; }
    d[i] = r;
  }
  return st;
}
IppStatus ippsThreshold_GT_32f_I(Ipp32f *sd, int n, Ipp32f lv) { NP1(sd); LEN(n); for (int i = 0; i < n; i++) if (sd[i] > lv) sd[i] = lv; return 0; }
IppStatus ippsThreshold_LT_32f_I(Ipp32f *sd, int n, Ipp32f lv) { NP1(sd); LEN(n); for (int i = 0; i < n; i++) if (sd[i] < lv) sd[i] = lv; return 0; }

#ifndef VSLOPE
#define VSLOPE 0
#endif
IppStatus ippsVectorSlope_32f(Ipp32f *d, int n, Ipp32f off, Ipp32f slope) {
  NP1(d); LEN(n);
#if VSLOPE == 0
  /* IPP-9 (#276): 実 DLL の算法 (全 ISA 経路同一)。幅 16 ブロックの累積。
     レーン k=4g+j の初期値 = off + (j*s に 4s を g 回加算)、以降 step=16*s を加算。
     端数は先頭 = 次ブロックのレーン0、以降は直前要素 + s の直列加算。FMA 融合禁止。 */
  {
    const float s4 = 4.0f * slope, step = 16.0f * slope;
    float lane[16];
    for (int k = 0; k < 16; k++) {
      float v = (float)(k & 3) * slope;
      for (int g = 0; g < (k >> 2); g++) v = v + s4;
      lane[k] = off + v;
    }
    int i = 0;
    for (; i + 16 <= n; i += 16)
      for (int k = 0; k < 16; k++) { d[i + k] = lane[k]; lane[k] += step; }
    if (i < n) {
      d[i] = lane[0];
      for (i++; i < n; i++) d[i] = d[i - 1] + slope;
    }
  }
#else
  for (int i = 0; i < n; i++) {
#if VSLOPE == 1
    d[i] = (float)((double)off + (double)slope * (double)i);
#else
    d[i] = fmaf(slope, (float)i, off);
#endif
  }
#endif
  return 0;
}

IppStatus ippsConvert_32f32s_Sfs(const Ipp32f *s, Ipp32s *d, int n, int rnd, int sfs) {
  NP1(s); NP1(d); LEN(n);
  double k = ldexp(1.0, -sfs);
  for (int i = 0; i < n; i++) {
    double v = (double)s[i] * k;
    if (v != v) { d[i] = signbit(s[i]) ? INT32_MIN : INT32_MAX; continue; }  /* NaN は符号で飽和方向が決まる (ref 観測) */
    v = rnd == ippRndNear ? nearbyint(v) : rnd == ippRndFinancial ? round(v) : trunc(v);
    d[i] = v >= 2147483647.0 ? INT32_MAX : v <= -2147483648.0 ? INT32_MIN : (Ipp32s)v;
  }
  return 0;
}

void *ippMalloc(int len) { void *p = NULL; if (len <= 0) return NULL; return posix_memalign(&p, 64, (size_t)len) ? NULL : p; }
void  ippFree(void *p) { free(p); }
IppStatus ippSetFlushToZero(int v, unsigned int *m) { (void)v; if (m) *m = 0; return 0; }
IppStatus ippSetDenormAreZeros(int v) { (void)v; return 0; }
IppStatus ippSetNumThreads(int n) { (void)n; return 0; }
