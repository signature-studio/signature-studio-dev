/* pffft 単体プローブ: 最小サイズ / ordered レイアウト / スケール / unordered 往復 を素朴 DFT で確認 (CAB-139) */
#include "../pffft/pffft.h"
#include "../pffft/pffft_double.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
static void naive_dft(const double *x, int N, double *re, double *im) {
  for (int k = 0; k <= N/2; k++) { double sr = 0, si = 0;
    for (int n = 0; n < N; n++) { double a = -2.0*M_PI*k*n/N; sr += x[n]*cos(a); si += x[n]*sin(a); }
    re[k] = sr; im[k] = si; }
}
int main(void) {
  printf("float: simd=%d arch=%s minReal=%d minCplx=%d valid32=%d valid16=%d\n", pffft_simd_size(), pffft_simd_arch(),
    pffft_min_fft_size(PFFFT_REAL), pffft_min_fft_size(PFFFT_COMPLEX), pffft_is_valid_size(32,PFFFT_REAL), pffft_is_valid_size(16,PFFFT_REAL));
  printf("double: simd=%d arch=%s minReal=%d valid32=%d\n", pffftd_simd_size(), pffftd_simd_arch(),
    pffftd_min_fft_size(PFFFT_REAL), pffftd_is_valid_size(32,PFFFT_REAL));
  int fails = 0;
  for (int N = 32; N <= 4096; N *= 8) {
    PFFFT_Setup *s = pffft_new_setup(N, PFFFT_REAL);
    float *x = pffft_aligned_malloc(N*4), *un = pffft_aligned_malloc(N*4), *ord = pffft_aligned_malloc(N*4), *y = pffft_aligned_malloc(N*4), *work = pffft_aligned_malloc(N*4);
    double *xr = malloc(8*N); for (int i = 0; i < N; i++) { x[i] = (float)((i*2654435761u % 4096)/4096.0*2-1); xr[i] = x[i]; }
    double *re = malloc(8*(N/2+1)), *im = malloc(8*(N/2+1)); naive_dft(xr, N, re, im);
    pffft_transform_ordered(s, x, ord, work, PFFFT_FORWARD);
    /* 仮説: ord[0]=F0, ord[1]=F_{N/2}, ord[2k]=Fk.re, ord[2k+1]=Fk.im (k=1..) */
    double e = fabs(ord[0]-re[0]) + fabs(ord[1]-re[N/2]);
    for (int k = 1; k < N/2; k++) e += fabs(ord[2*k]-re[k]) + fabs(ord[2*k+1]-im[k]);
    e /= (N+2); printf("N=%d fwd-ordered hyp-err/elt=%.3g", N, e); if (e > 1e-4) fails++;
    /* unordered -> zreorder が ordered と一致するか */
    pffft_transform(s, x, un, work, PFFFT_FORWARD);
    pffft_zreorder(s, un, y, PFFFT_FORWARD);
    double ez = 0; for (int i = 0; i < N; i++) ez += fabs(y[i]-ord[i]); ez /= N;
    printf(" zreorder-match=%.3g", ez); if (ez > 1e-6) fails++;
    /* backward ordered: 仮説 入力=ordered レイアウト -> 出力=N*x (無スケール) */
    float *xin = pffft_aligned_malloc(N*4); for (int i = 0; i < N; i++) xin[i] = ord[i];
    pffft_transform_ordered(s, xin, y, work, PFFFT_BACKWARD);
    double eb = 0; for (int i = 0; i < N; i++) eb += fabs(y[i] - N*xr[i]); eb /= N;
    printf(" inv-ord-err=%.3g", eb); if (eb > 1e-3) fails++;
    /* unordered backward (PermToR 相当): un -> y2 == N*x */
    pffft_transform(s, un, y, work, PFFFT_BACKWARD);
    double eu = 0; for (int i = 0; i < N; i++) eu += fabs(y[i] - N*xr[i]); eu /= N;
    printf(" inv-unord-err=%.3g\n", eu); if (eu > 1e-3) fails++;
    pffft_aligned_free(x); pffft_aligned_free(un); pffft_aligned_free(ord); pffft_aligned_free(y); pffft_aligned_free(work); pffft_aligned_free(xin); free(xr); free(re); free(im);
  }
  /* double 版も 1 ケース確認 */
  { int N = 1024; PFFFTD_Setup *s = pffftd_new_setup(N, PFFFT_REAL);
    double *x = pffftd_aligned_malloc(N*8), *ord = pffftd_aligned_malloc(N*8), *work = pffftd_aligned_malloc(N*8);
    for (int i = 0; i < N; i++) x[i] = (i%7)*0.125-0.5;
    pffftd_transform_ordered(s, x, ord, work, PFFFT_FORWARD);
    double *xr = malloc(8*N); for (int i = 0; i < N; i++) xr[i] = x[i];
    double *re = malloc(8*(N/2+1)), *im = malloc(8*(N/2+1)); naive_dft(xr, N, re, im);
    double e = fabs(ord[0]-re[0]) + fabs(ord[1]-re[N/2]); for (int k = 1; k < N/2; k++) e += fabs(ord[2*k]-re[k]) + fabs(ord[2*k+1]-im[k]);
    e /= (N+2); printf("double N=%d fwd-ordered hyp-err/elt=%.3g\n", N, e); if (e > 1e-12) fails++;
    pffftd_aligned_free(x); pffftd_aligned_free(ord); pffftd_aligned_free(work); free(xr); free(re); free(im); }
  printf("probe_pffft: fails=%d\n", fails);
  return fails != 0;
}
