/* FFT 差分: 実 IPP (win dll) vs ipp_fft.c。正規化 RMS 誤差 = ||ours-ref||_2 / ||ref||_2 を order×flag×{32f,64f}×{Pack,CCS,I} で測る */
#define _GNU_SOURCE
#include "pe_load.h"
#include "../src/ipp_min.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
typedef int (MS *getsz_t)(int, int, int, int *, int *, int *);
typedef int (MS *init_t)(void **, int, int, int, uint8_t *, uint8_t *);
typedef int (MS *tr_t)(const void *, void *, const void *, uint8_t *);
typedef int (MS *tri_t)(void *, const void *, uint8_t *);
static uint64_t rs = 12345; static double ur(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (rs >> 11) * (1.0 / 9007199254740992.0) * 2 - 1; }
static double nerr(const void *a, const void *b, int n, int dbl) {
  double d = 0, r = 0; for (int i = 0; i < n; i++) { double x = dbl ? ((double *)a)[i] : ((float *)a)[i], y = dbl ? ((double *)b)[i] : ((float *)b)[i]; d += (x - y) * (x - y); r += y * y; }
  return sqrt(d / (r + 1e-300)); }
int main(int argc, char **argv) {
  PE pe; pe_load(argv[1], &pe); ((int (MS *)(uint64_t))pe_export(&pe, "ippSetCpuFeatures"))(~0ULL);
  FILE *gj = NULL, *gb = NULL; long goff = 0; int gfirst = 1;
  if (argc > 2) { char pth[512]; snprintf(pth, 512, "%s/fft_golden.json", argv[2]); gj = fopen(pth, "w"); snprintf(pth, 512, "%s/fft_golden.bin", argv[2]); gb = fopen(pth, "wb"); fprintf(gj, "[\n"); }
  double worst32 = 0, worst64 = 0, worstCcs = 0, worstSize = 0; int bad = 0, cases = 0;
  for (int dbl = 0; dbl < 2; dbl++) {
    getsz_t gs = pe_export(&pe, dbl ? "ippsFFTGetSize_R_64f" : "ippsFFTGetSize_R_32f"); init_t in = pe_export(&pe, dbl ? "ippsFFTInit_R_64f" : "ippsFFTInit_R_32f");
    tr_t fw = pe_export(&pe, dbl ? "ippsFFTFwd_RToPack_64f" : "ippsFFTFwd_RToPack_32f"), iv = pe_export(&pe, dbl ? "ippsFFTInv_PackToR_64f" : "ippsFFTInv_PackToR_32f");
    tri_t fwi = pe_export(&pe, dbl ? "ippsFFTFwd_RToPack_64f_I" : "ippsFFTFwd_RToPack_32f_I");
    for (int order = 1; order <= 16; order++) for (int fi = 0; fi < 4; fi++) {
      int flag = 1 << fi, N = 1 << order, a, b, c, a2, b2, c2;
      gs(order, flag, 0, &a, &b, &c); if (dbl) ippsFFTGetSize_R_64f(order, flag, 0, &a2, &b2, &c2); else ippsFFTGetSize_R_32f(order, flag, 0, &a2, &b2, &c2);
      uint8_t *sp = aligned_alloc(64, a + 64), *sb = aligned_alloc(64, b + 64), *bf = aligned_alloc(64, c + 64), *sp2 = aligned_alloc(64, a2 + 64), *bf2 = aligned_alloc(64, c2 + 64); void *spec = 0, *spec2 = 0;
      in(&spec, order, flag, 0, sp, sb); if (dbl) ippsFFTInit_R_64f(&spec2, order, flag, 0, sp2, 0); else ippsFFTInit_R_32f(&spec2, order, flag, 0, sp2, 0);
      int es = dbl ? 8 : 4; void *x = malloc(es * N), *r1 = malloc(es * (N + 2)), *o1 = malloc(es * (N + 2)), *r2 = malloc(es * (N + 2)), *o2 = malloc(es * (N + 2));
      for (int i = 0; i < N; i++) { double v = ur(); if (dbl) ((double *)x)[i] = v; else ((float *)x)[i] = (float)v; }
      fw(x, r1, spec, bf); if (dbl) ippsFFTFwd_RToPack_64f(x, o1, spec2, bf2); else ippsFFTFwd_RToPack_32f(x, o1, spec2, bf2);
      double e1 = nerr(o1, r1, N, dbl);
      iv(r1, r2, spec, bf); if (dbl) ippsFFTInv_PackToR_64f(r1, o2, spec2, bf2); else ippsFFTInv_PackToR_32f(r1, o2, spec2, bf2);
      double e2 = nerr(o2, r2, N, dbl);
      memcpy(r2, x, es * N); memcpy(o2, x, es * N); fwi(r2, spec, bf); if (dbl) ippsFFTFwd_RToPack_64f_I(o2, spec2, bf2); else ippsFFTFwd_RToPack_32f_I(o2, spec2, bf2);
      double e3 = nerr(o2, r2, N, dbl);
      double e = fmax(e1, fmax(e2, e3)); cases++;
      if (gj && (order == 2 || order == 5 || order == 8 || order == 10 || order == 12 || order == 14)) {
        fprintf(gj, "%s{\"dbl\":%d,\"order\":%d,\"flag\":%d,\"off\":%ld}\n", gfirst ? "" : ",", dbl, order, flag, goff); gfirst = 0;
        fwrite(x, es, N, gb); fwrite(r1, es, N, gb);
        { void *rinv = malloc(es * N); iv(r1, rinv, spec, bf); fwrite(rinv, es, N, gb); free(rinv); }
        goff += (long)es * N * 3;
      }
      if (dbl) { if (e > worst64) worst64 = e; } else { if (e > worst32) worst32 = e; }
      if (a != a2 || c != c2) worstSize = 1;      /* spec サイズが実 IPP と違うのは問題ではない (不透明) が記録 */
      if (e > (dbl ? 1e-12 : 5e-6)) { bad++; fprintf(stderr, "BAD dbl=%d order=%d flag=%d e=%g/%g/%g\n", dbl, order, flag, e1, e2, e3); }
      free(x); free(r1); free(o1); free(r2); free(o2); free(sp); free(sb); free(bf); free(sp2); free(bf2);
    }
  }
  /* CCS in-place 32f */
  { int order = 10, N = 1024, a, b, c; ippsFFTGetSize_R_32f(order, 8, 0, &a, &b, &c); void *spec = 0; uint8_t *sp = aligned_alloc(64, a + 64); void *specr = 0;
    getsz_t gs = pe_export(&pe, "ippsFFTGetSize_R_32f"); int ra, rb, rc; gs(order, 8, 0, &ra, &rb, &rc); uint8_t *spr = aligned_alloc(64, ra + 64), *sbr = aligned_alloc(64, rb + 64 + 1), *bfr = aligned_alloc(64, rc + 64);
    ((init_t)pe_export(&pe, "ippsFFTInit_R_32f"))(&specr, order, 8, 0, spr, sbr); ippsFFTInit_R_32f(&spec, order, 8, 0, sp, 0);
    float *x = malloc(4 * (N + 2)), *y = malloc(4 * (N + 2)); for (int i = 0; i < N; i++) x[i] = y[i] = (float)ur(); x[N] = x[N + 1] = y[N] = y[N + 1] = 0;
    ((tri_t)pe_export(&pe, "ippsFFTFwd_RToCCS_32f_I"))(x, specr, bfr); ippsFFTFwd_RToCCS_32f_I(y, spec, 0); double e = nerr(y, x, N + 2, 0);
    ((tri_t)pe_export(&pe, "ippsFFTInv_CCSToR_32f_I"))(x, specr, bfr); ippsFFTInv_CCSToR_32f_I(y, spec, 0); double e2 = nerr(y, x, N, 0); worstCcs = fmax(e, e2); }
  if (gj) { fprintf(gj, "]\n"); fclose(gj); fclose(gb); }
  printf("{\"fft_cases\":%d,\"worst_nrms_32f\":%.3g,\"worst_nrms_64f\":%.3g,\"ccs_32f_nrms\":%.3g,\"bad\":%d,\"spec_size_differs_from_ipp\":%d}\n", cases, worst32, worst64, worstCcs, bad, worstSize > 0);
  return 0; }
