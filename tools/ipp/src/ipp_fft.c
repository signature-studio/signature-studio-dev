/* 実数 FFT (ippsFFT*_R_32f/64f) の PoC。倍精度の素直な基数2 複素 FFT (N 点, 虚部0) → Pack/CCS 形式で出力。
   正確さ優先・速度は後回し (本番は pffft 等の upstream SIMD 実装へ差し替え可)。flag 意味は実 IPP と一致を ref 比較で確認。 */
#include "ipp_min.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

typedef struct { int order, N, flag, pad; } FftHdr;           /* 直後に cos[N/2], sin[N/2] (double) */
#define HDR_SZ 16
static double *tw_c(const FftHdr *h) { return (double *)((char *)h + HDR_SZ); }
static double *tw_s(const FftHdr *h) { return tw_c(h) + h->N / 2; }

static void cfft(double *re, double *im, int N, const double *c, const double *s, int sign) {   /* sign=-1: e^{-i} */
  for (int i = 1, j = 0; i < N; i++) { int bit = N >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit; if (i < j) { double t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; } }
  for (int len = 2; len <= N; len <<= 1) {
    int half = len >> 1, step = N / len;
    for (int i = 0; i < N; i += len) for (int k = 0; k < half; k++) {
      double wr = c[k * step], wi = sign * s[k * step];
      double xr = re[i + k + half] * wr - im[i + k + half] * wi, xi = re[i + k + half] * wi + im[i + k + half] * wr;
      re[i + k + half] = re[i + k] - xr; im[i + k + half] = im[i + k] - xi; re[i + k] += xr; im[i + k] += xi;
    }
  }
}
static double scale_of(const FftHdr *h, int inverse) {
  if (h->flag & 8) return 1.0;
  if (h->flag & 4) return 1.0 / sqrt((double)h->N);
  if (inverse) return (h->flag & 2) ? 1.0 / h->N : 1.0;
  return (h->flag & 1) ? 1.0 / h->N : 1.0;
}
static FftHdr *spec_init(void *pSpec, int order, int flag) {
  FftHdr *h = (FftHdr *)(((uintptr_t)pSpec + 15) & ~(uintptr_t)15);
  h->order = order; h->N = 1 << order; h->flag = flag;
  for (int k = 0; k < h->N / 2; k++) { tw_c(h)[k] = cos(2 * M_PI * k / h->N); tw_s(h)[k] = sin(2 * M_PI * k / h->N); }
  return h;
}
static int spec_size(int order) { return 16 + HDR_SZ + (1 << order) * 8; }

/* fmt: 0=Pack, 1=CCS。src/dst は double に載せ替えて計算 */
static void fwd_real(const FftHdr *h, const double *x, double *out, int fmt) {
  int N = h->N; double sc = scale_of(h, 0);
  if (N == 1) { out[0] = x[0] * sc; if (fmt) out[1] = 0; return; }
  double *re = malloc(sizeof(double) * N * 2), *im = re + N;
  for (int i = 0; i < N; i++) { re[i] = x[i]; im[i] = 0; }
  cfft(re, im, N, tw_c(h), tw_s(h), -1);
  if (fmt == 0) {
    out[0] = re[0] * sc;
    if (N == 2) out[1] = re[1] * sc;
    else { for (int k = 1; k < N / 2; k++) { out[2 * k - 1] = re[k] * sc; out[2 * k] = im[k] * sc; } out[N - 1] = re[N / 2] * sc; }
  } else {
    out[0] = re[0] * sc; out[1] = 0;
    for (int k = 1; k < N / 2; k++) { out[2 * k] = re[k] * sc; out[2 * k + 1] = im[k] * sc; }
    out[N] = re[N / 2] * sc; out[N + 1] = 0;
  }
  free(re);
}
static void inv_real(const FftHdr *h, const double *in, double *x, int fmt) {
  int N = h->N; double sc = scale_of(h, 1);
  if (N == 1) { x[0] = in[0] * sc; return; }
  double *re = malloc(sizeof(double) * N * 2), *im = re + N;
  re[0] = in[0]; im[0] = 0;
  if (fmt == 0) {
    if (N == 2) { re[1] = in[1]; im[1] = 0; }
    else { for (int k = 1; k < N / 2; k++) { re[k] = in[2 * k - 1]; im[k] = in[2 * k]; } re[N / 2] = in[N - 1]; im[N / 2] = 0; }
  } else { for (int k = 1; k < N / 2; k++) { re[k] = in[2 * k]; im[k] = in[2 * k + 1]; } re[N / 2] = in[N]; im[N / 2] = 0; }
  for (int k = 1; k < N / 2; k++) { re[N - k] = re[k]; im[N - k] = -im[k]; }
  cfft(re, im, N, tw_c(h), tw_s(h), +1);
  for (int i = 0; i < N; i++) x[i] = re[i] * sc;
  free(re);
}

#define FFT_FAMILY(SFX, T) \
IppStatus ippsFFTGetSize_R_##SFX(int order, int flag, int hint, int *pSpecSize, int *pSpecBufSize, int *pBufSize) { \
  (void)flag; (void)hint; if (!pSpecSize || !pSpecBufSize || !pBufSize) return ippStsNullPtrErr; if (order < 0 || order > 30) return -2 /*ippStsFftOrderErr*/; \
  *pSpecSize = spec_size(order); *pSpecBufSize = 0; *pBufSize = 0; return 0; } \
IppStatus ippsFFTInit_R_##SFX(void **ppSpec, int order, int flag, int hint, uint8_t *pSpec, uint8_t *pSpecBuf) { \
  (void)hint; (void)pSpecBuf; if (!ppSpec || !pSpec) return ippStsNullPtrErr; if (order < 0 || order > 30) return -2; *ppSpec = spec_init(pSpec, order, flag); return 0; } \
static IppStatus fwd_##SFX(const T *s, T *d, const void *spec, int fmt) { \
  if (!s || !d || !spec) { return ippStsNullPtrErr; } const FftHdr *h = spec; int n = h->N, m = fmt ? n + 2 : n; \
  double *in = malloc(sizeof(double) * (n + m)); if (!in) { return -9; } double *out = in + n; for (int i = 0; i < n; i++) in[i] = s[i]; fwd_real(h, in, out, fmt); for (int i = 0; i < m; i++) d[i] = (T)out[i]; free(in); return 0; } \
static IppStatus inv_##SFX(const T *s, T *d, const void *spec, int fmt) { \
  if (!s || !d || !spec) { return ippStsNullPtrErr; } const FftHdr *h = spec; int n = h->N, m = fmt ? n + 2 : n; \
  double *in = malloc(sizeof(double) * (n + m)); if (!in) { return -9; } double *out = in + m; for (int i = 0; i < m; i++) in[i] = s[i]; inv_real(h, in, out, fmt); for (int i = 0; i < n; i++) d[i] = (T)out[i]; free(in); return 0; } \
IppStatus ippsFFTFwd_RToPack_##SFX(const T *s, T *d, const void *spec, uint8_t *b) { (void)b; return fwd_##SFX(s, d, spec, 0); } \
IppStatus ippsFFTInv_PackToR_##SFX(const T *s, T *d, const void *spec, uint8_t *b) { (void)b; return inv_##SFX(s, d, spec, 0); } \
IppStatus ippsFFTFwd_RToPack_##SFX##_I(T *sd, const void *spec, uint8_t *b) { (void)b; return fwd_##SFX(sd, sd, spec, 0); } \
IppStatus ippsFFTInv_PackToR_##SFX##_I(T *sd, const void *spec, uint8_t *b) { (void)b; return inv_##SFX(sd, sd, spec, 0); }
FFT_FAMILY(32f, float)
FFT_FAMILY(64f, double)
IppStatus ippsFFTFwd_RToCCS_32f_I(float *sd, const void *spec, uint8_t *b) { (void)b; return fwd_32f(sd, sd, spec, 1); }
IppStatus ippsFFTInv_CCSToR_32f_I(float *sd, const void *spec, uint8_t *b) { (void)b; return inv_32f(sd, sd, spec, 1); }
