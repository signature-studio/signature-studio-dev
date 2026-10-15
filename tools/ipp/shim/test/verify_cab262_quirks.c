/* CAB-262 (IPP-7) 検収の独立再計算: quirk を**実装 (impl/ipp_sig_fill3.c) を参照せず**に
   win64 実 DLL だけに対して確認する probe。
   usage: gcc -O1 -I ../../src -I ../../ref -o /tmp/vq test/verify_cab262_quirks.c ../../ref/pe_load.c -lm
          FL_WIN64_DIR=<fl-win64 展開先> /tmp/vq [path/to/block24356_PE.bin]   (省略時 $FL_WIN64_DIR/extracted/block24356_PE.bin)
   出力 (検収実測 2026-10-11, AVX-512 経路 = ippSetCpuFeatures(~0)):
     quirk1 RealToCplx_32f : dst=NULL が最優先 (-8)、len<1 は -6、片方 src NULL は書込のみ
     quirk2 AddProductC_32f : double で 1 回丸め (判別入力 180 組合せのうち DLL と一致は double 側)
     quirk3 Round_32f       : half-away-from-zero (0.5→1, -0.5→-1, 2.5→3)、±0 は符号保存、|x|>=2^31 は不変
     quirk4 WinKaiser_32f_I : I0 級数は 60 項が必要 (24 項は beta=30 で 2.6e-04)、beta>=38 は -39 */
#include "pe_load.h"
#include "fl_dll_path.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
typedef struct { float re, im; } fc;
static float fb(uint32_t b) { float f; memcpy(&f, &b, 4); return f; }
static uint32_t bf(float f) { uint32_t b; memcpy(&b, &f, 4); return b; }
static double i0_series(double x, int T) {
  double s = 0, t = 1;
  for (int k = 0; k < T; k++) { if (k) t *= (x / 2) * (x / 2) / ((double)k * k); s += t; }
  return s;
}

int main(int argc, char **argv) {
  PE pe;
  if (pe_load(argc > 1 ? argv[1] : fl_ipp_dll_path(), &pe)) return 1;
  ((int (MS *)(uint64_t))pe_export(&pe, "ippSetCpuFeatures"))(~0ULL);

  /* ============ quirk 1: ippsRealToCplx_32f のエラー優先順 ============ */
  int (MS *r2c)(const float *, const float *, fc *, int) = pe_export(&pe, "ippsRealToCplx_32f");
  float re[8], im[8]; fc d[8];
  for (int i = 0; i < 8; i++) { re[i] = (float)(i + 1); im[i] = -(float)(i + 1); d[i].re = d[i].im = -77.f; }
  printf("== quirk1 RealToCplx_32f: エラー優先順 ==\n");
  int st1 = r2c(re, im, NULL, 0), st2 = r2c(re, im, NULL, 4), st3 = r2c(re, im, NULL, -1);
  printf("  dst=NULL len= 0 -> %3d | dst=NULL len= 4 -> %3d | dst=NULL len=-1 -> %3d\n", st1, st2, st3);
  int st4 = r2c(re, im, d, 0), st5 = r2c(re, im, d, 4);
  printf("  dst=ok   len= 0 -> %3d | dst=ok   len= 4 -> %3d (d[0].re=%g im=%g)\n", st4, st5, d[0].re, d[0].im);
  d[0].re = d[0].im = -77.f;
  int st6 = r2c(NULL, im, d, 4);
  printf("  re=NULL len= 4 -> %3d (d[0].re=%g は書込まれない, im=%g)\n", st6, d[0].re, d[0].im);
  d[0].re = d[0].im = -77.f;
  int st7 = r2c(re, NULL, d, 4);
  printf("  im=NULL len= 4 -> %3d (re=%g, im=%g)\n", st7, d[0].re, d[0].im);
  int st8 = r2c(NULL, NULL, d, 4);
  printf("  両NULL  len= 4 -> %3d\n", st8);

  /* ============ quirk 2: ippsAddProductC_32f の演算精度 ============ */
  int (MS *apc)(const float *, float, float *, int) = pe_export(&pe, "ippsAddProductC_32f");
  printf("== quirk2 AddProductC_32f: float 2 段丸め vs double 1 段丸め ==\n");
  {
    static const uint32_t V[] = { 0x3f800000, 0x40400000, 0x3f000000, 0x4b000000, 0x33800000, 0x3f7fffff };
    static const uint32_t S[] = { 0x3f800000, 0x40000000, 0x3f000000, 0x4b800001, 0x3eaaaaab };
    static const uint32_t D[] = { 0x3f800000, 0xbf800000, 0x4b000000, 0x3f000000, 0x00000000, 0x3f800001 };
    int disc = 0, hit_f = 0, hit_d = 0, both = 0, neither = 0;
    for (unsigned v = 0; v < sizeof V / sizeof *V; v++)
    for (unsigned s = 0; s < sizeof S / sizeof *S; s++)
    for (unsigned w = 0; w < sizeof D / sizeof *D; w++) {
      float val = fb(V[v]), src = fb(S[s]), dst = fb(D[w]);
      float fm = dst + val * src;                            /* float のまま (2 段丸め) */
      float dm = (float)((double)dst + (double)val * (double)src); /* double 経由 (1 段丸め) */
      if (bf(fm) != bf(dm)) disc++;
      float out = dst;
      int st = apc(&src, val, &out, 1);
      if (st != 0) { printf("  status=%d (0 以外)\n", st); continue; }
      if (bf(out) == bf(fm) && bf(out) == bf(dm)) both++;
      else if (bf(out) == bf(dm)) hit_d++;
      else if (bf(out) == bf(fm)) hit_f++;
      else neither++;
    }
    printf("  %d 組合せ (判別するのは %d) → DLL 一致: double 経由 %d / float 直和 %d / 両方 %d / どちらでもない %d\n",
           (int)(sizeof V / sizeof *V * sizeof S / sizeof *S * sizeof D / sizeof *D), disc, hit_d, hit_f, both, neither);
  }

  /* ============ quirk 3: ippsRound_32f は half-away-from-zero ============ */
  int (MS *rnd)(const float *, float *, int) = pe_export(&pe, "ippsRound_32f");
  static const uint32_t XS[] = { 0x3f000000, 0xbf000000, 0x3fc00000, 0xbfc00000, 0x40200000, 0xc0200000,
                                 0x40600000, 0xc0600000, 0x4f000000, 0xcf000000, 0x4effffff, 0x80000000, 0x00000000 };
  printf("== quirk3 Round_32f: half-away-from-zero ==\n");
  for (unsigned i = 0; i < sizeof XS / sizeof *XS; i++) {
    float x = fb(XS[i]), o = -77.f;
    int st = rnd(&x, &o, 1);
    printf("  x=%14.9g (%08x) -> %12.9g (%08x) status=%d\n", x, bf(x), o, bf(o), st);
  }

  /* ============ quirk 4: ippsWinKaiser_32f_I ============ */
  int (MS *kais)(float *, int, float) = pe_export(&pe, "ippsWinKaiser_32f_I");
  printf("== quirk4 WinKaiser_32f_I: I0 級数の項数と beta 上限 ==\n");
  {
    static const int LN[] = { 8, 16, 17, 32, 33, 64, 256, 1000 };
    static const float AL[] = { 0.5f, 1.0f, 1.5f, 2.0f, 2.5f, 3.0f, 3.5f, 4.0f };
    static float out[1000];
    for (unsigned li = 0; li < sizeof LN / sizeof *LN; li++)
    for (unsigned ai = 0; ai < sizeof AL / sizeof *AL; ai++) {
      int N = LN[li]; float a = AL[ai];
      double beta = (double)a * (N - 1) / 2.0;
      if (beta > 37.9) continue;
      for (int i = 0; i < N; i++) out[i] = 1.f;
      int st = kais(out, N, a);
      if (st != 0) { printf("  N=%4d a=%.2f beta=%6.3f -> status=%d\n", N, a, beta, st); continue; }
      double e24 = 0, e60 = 0;
      double i0b24 = i0_series(beta, 24), i0b60 = i0_series(beta, 60);
      for (int i = 0; i < N; i++) {
        double r = (N == 1) ? 0 : 2.0 * i / (N - 1) - 1.0, t = 1 - r * r;
        if (t < 0) t = 0;
        double x = beta * sqrt(t);
        double p24 = i0_series(x, 24) / i0b24, p60 = i0_series(x, 60) / i0b60;
        if (fabs(p24 - out[i]) > e24) e24 = fabs(p24 - out[i]);
        if (fabs(p60 - out[i]) > e60) e60 = fabs(p60 - out[i]);
      }
      printf("  N=%4d a=%.2f beta=%6.3f st=%d  maxerr: I0 24 項=%.3e  60 項=%.3e\n", N, a, beta, st, e24, e60);
    }
    /* beta >= 38 の境界 (N=256, a を細かく) */
    for (double a = 0.2970; a < 0.2985; a += 0.00005) {
      double b = a * 255 / 2.0;
      if (b < 37.98 || b > 38.03) continue;
      for (int i = 0; i < 256; i++) out[i] = 1.f;
      printf("  N= 256 a=%.5f beta=%.5f -> status=%d\n", a, b, kais(out, 256, (float)a));
    }
  }
  return 0;
}
