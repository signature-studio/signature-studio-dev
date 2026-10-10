/* IPP FFT (ippsFFT*_R_32f/64f, 28 関数) の pffft 実装 — CAB-139。
   取得元・パッチ・ライセンスは PROVENANCE.md / pffft/LICENSE.pffft.txt 参照。

   設計:
   - エンジン選択 (Init 時に確定, spec に記録):
       N >= pffft 最小サイズ (REAL = 2*simd^2 = 32) -> pffft (32f) / pffft_double (64f)
       それ未満 (N = 1,2,4,8,16)                   -> 内製 倍精度基数2 (旧 PoC 実装の移植; pffft は N<32 非対応)
   - spec は IPP 契約どおり呼出し側バッファ内に構築 (pffft_new_setup_into パッチ; 隠し malloc 無し)。
   - 形式 (実 IPP 実測: test/probe_ipp_sem.c + 旧 ref/ipp_fft_ref.c 検証):
       Pack: N 語   [X0, X1.re, X1.im, ..., X_{N/2-1}.re, X_{N/2-1}.im, X_{N/2}]
       CCS : N+2 語 [X0, 0, X1.re, X1.im, ..., X_{N/2}, 0]  (in-place も N+2 語書込)
       Perm: N 語   pffft unordered (RToPerm <-> PermToR の対で使用する不透明形式)
   - スケール flag (1=fwd/N, 2=inv/N, 4=1/sqrtN, 8=無除算): pffft は forward/backward とも無スケール
     (backward 生値 = N*IDFT) なので旧実装の scale_of をそのまま適用できる。
   - エラーコードは実 IPP 実測に鏡像: order<0 -> -17, flag 不正 (1/2/4/8 以外) -> -18,
     NULL ポインタ -> -8 (ippStsNullPtrErr), pBuffer=NULL は許容 (内部 scratch を確保)。
     実 IPP 未確認の差分: order>26 は -17 (pffft パッチの上限 N<=2^26。実 IPP は order 20 まで正常確認)。
     spec の magic 不一致も -8 (防御; 実 IPP は未定義動作)。
   - hint (0/1/2) は受理するが単一実装のため同一動作 (実 IPP も order=8 では 3 種同サイズ)。

   単一 TU にはしない (pffft.c と pffft_double.c は vsfscalar typedef 等が競合するため別 TU)。
   ビルド経路: build_native.sh / build_wasm.sh / shim_e2e.sh / gen_shim.py が fft と fft/pffft の
   両 .c を明示的に拾う (CAB-139 で追記済み)。 */
#include "ipp_fft_pffft.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

/* ---- spec header (pSpec 内 64B アライメント先頭に置く) ---- */
#define FFT_HDR_MAGIC 0x53464649  /* 'IFFS' (LE) */
#define FFT_ALIGN 64
enum { ENG_NAIVE = 0, ENG_PFFFT = 1, ENG_PFFFTD = 2 };
typedef struct {
  int32_t magic;
  int32_t order;
  int32_t N;
  int32_t flag;
  int32_t engine;
  int32_t rsv;
} FftHdr;  /* 24B。+FFT_ALIGN からエンジン固有データ (PFFFT_Setup 本体 or naive の cos/sin double 表) */

/* 実 IPP 実測の status (test/probe_ipp_sem.c)。ippStsFftOrderErr / ippStsFftFlagErr に相当 */
enum { IPP_FFT_ORDER_ERR = -17, IPP_FFT_FLAG_ERR = -18 };
enum { FFT_MAX_ORDER = 26 };      /* pffft パッチの上限 (N <= 1<<26) */

static int fft_flag_ok(int flag) { return flag == 1 || flag == 2 || flag == 4 || flag == 8; }

static const FftHdr *hdr_of(const void *spec) {
  return (const FftHdr *)(((uintptr_t)spec + (FFT_ALIGN - 1)) & ~(uintptr_t)(FFT_ALIGN - 1));
}
static FftHdr *hdr_of_mut(uint8_t *pSpec) {
  return (FftHdr *)(((uintptr_t)pSpec + (FFT_ALIGN - 1)) & ~(uintptr_t)(FFT_ALIGN - 1));
}

/* スケール (旧 ipp_fft.c と同一。実 IPP との一致は PoC 128 ケース + golden 48 ケースで検証済み) */
static double scale_of(const FftHdr *h, int inverse) {
  if (h->flag & 8) return 1.0;
  if (h->flag & 4) return 1.0 / sqrt((double)h->N);
  if (inverse) return (h->flag & 2) ? 1.0 / h->N : 1.0;
  return (h->flag & 1) ? 1.0 / h->N : 1.0;
}

/* ---- naive engine (N < pffft 最小サイズのときのみ。倍精度基数2, 旧 PoC 実装の移植) ----
   pffft は N<32 を扱えないためのフォールバック。規模が小さいため内部 malloc 許容 (旧実装と同じ)。 */
static double *naive_cos(const FftHdr *h) { return (double *)((const char *)h + FFT_ALIGN); }
static double *naive_sin(const FftHdr *h) { return naive_cos(h) + h->N / 2; }

static void cfft(double *re, double *im, int N, const double *c, const double *s, int sign) {
  for (int i = 1, j = 0; i < N; i++) {
    int bit = N >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { double t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (int len = 2; len <= N; len <<= 1) {
    int half = len >> 1, step = N / len;
    for (int i = 0; i < N; i += len) for (int k = 0; k < half; k++) {
      double wr = c[k * step], wi = sign * s[k * step];
      double xr = re[i + k + half] * wr - im[i + k + half] * wi, xi = re[i + k + half] * wi + im[i + k + half] * wr;
      re[i + k + half] = re[i + k] - xr; im[i + k + half] = im[i + k] - xi; re[i + k] += xr; im[i + k] += xi;
    }
  }
}

static void naive_init(FftHdr *h) {
  h->N = 1 << h->order;
  for (int k = 0; k < h->N / 2; k++) { naive_cos(h)[k] = cos(2 * M_PI * k / h->N); naive_sin(h)[k] = sin(2 * M_PI * k / h->N); }
}

/* fmt: 0=Pack (N 語) / 1=CCS (N+2 語) */
static void naive_fwd(const FftHdr *h, const double *x, double *out, int fmt) {
  int N = h->N; double sc = scale_of(h, 0);
  if (N == 1) { out[0] = x[0] * sc; if (fmt) { out[1] = 0; out[2] = 0; } return; }  /* CCS は N+2 語 */
  double *re = malloc(sizeof(double) * N * 2), *im = re + N;
  for (int i = 0; i < N; i++) { re[i] = x[i]; im[i] = 0; }
  cfft(re, im, N, naive_cos(h), naive_sin(h), -1);
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
static void naive_inv(const FftHdr *h, const double *in, double *x, int fmt) {
  int N = h->N; double sc = scale_of(h, 1);
  if (N == 1) { x[0] = in[0] * sc; return; }
  double *re = malloc(sizeof(double) * N * 2), *im = re + N;
  re[0] = in[0]; im[0] = 0;
  if (fmt == 0) {
    if (N == 2) { re[1] = in[1]; im[1] = 0; }
    else { for (int k = 1; k < N / 2; k++) { re[k] = in[2 * k - 1]; im[k] = in[2 * k]; } re[N / 2] = in[N - 1]; im[N / 2] = 0; }
  } else { for (int k = 1; k < N / 2; k++) { re[k] = in[2 * k]; im[k] = in[2 * k + 1]; } re[N / 2] = in[N]; im[N / 2] = 0; }
  for (int k = 1; k < N / 2; k++) { re[N - k] = re[k]; im[N - k] = -im[k]; }
  cfft(re, im, N, naive_cos(h), naive_sin(h), +1);
  for (int i = 0; i < N; i++) x[i] = re[i] * sc;
  free(re);
}

/* ---- GetSize / Init (32f/64f 共用。dbl=0: float / 1: double) ---- */
static IppStatus fft_getsize_impl(int order, int flag, int dbl, int *pSpecSize, int *pSpecBufSize, int *pBufSize) {
  if (!pSpecSize || !pSpecBufSize || !pBufSize) return -8;
  *pSpecSize = *pSpecBufSize = *pBufSize = 0;
  if (order < 0) return IPP_FFT_ORDER_ERR;
  if (!fft_flag_ok(flag)) return IPP_FFT_FLAG_ERR;
  if (order > FFT_MAX_ORDER) return IPP_FFT_ORDER_ERR;
  const int N = 1 << order, es = dbl ? 8 : 4;
  const int minN = dbl ? pffftd_min_fft_size(PFFFT_REAL) : pffft_min_fft_size(PFFFT_REAL);
  if (N >= minN) {
    const int sb = dbl ? pffftd_setup_bytes(N, PFFFT_REAL) : pffft_setup_bytes(N, PFFFT_REAL);
    if (sb > 0) {
      *pSpecSize = FFT_ALIGN + sb;
      /* Run 用 scratch:
         32f: pffft work N 語 + pffft-ordered 転置 tmp N 語 (入力は 16B 整列を IPP 契約として直読み)
         64f: pffft_double は 32B 整列を要求するためユーザーポインタを渡さず, pBuffer 内でも
              32B 切り上げして staging する (in/tmp/out 各 N 語 + 整列 slack) */
      *pBufSize = 2 * N * es;
      if (dbl) *pBufSize = FFT_ALIGN + 3 * N * es;
      return 0;
    }
  }
  /* naive (小サイズ): cos/sin (double) N/2 本ずつ */
  *pSpecSize = FFT_ALIGN + (N / 2) * 8 * 2;
  *pBufSize = 2 * N * 8;
  return 0;
}

/* 32B 以上への切り上げ (pffft_double の VALIGNED 要求) */
static void *fft_align32(void *p) { return (void *)(((uintptr_t)p + 31) & ~(uintptr_t)31); }

static IppStatus fft_init_impl(void **ppSpec, int order, int flag, int hint, uint8_t *pSpec, uint8_t *pSpecBuf, int dbl) {
  (void)hint; (void)pSpecBuf;
  if (!ppSpec) return -8;
  if (!pSpec) return -8;
  if (order < 0) return IPP_FFT_ORDER_ERR;
  if (!fft_flag_ok(flag)) return IPP_FFT_FLAG_ERR;
  if (order > FFT_MAX_ORDER) return IPP_FFT_ORDER_ERR;
  FftHdr *h = hdr_of_mut(pSpec);
  h->magic = FFT_HDR_MAGIC; h->order = order; h->N = 1 << order; h->flag = flag; h->rsv = 0;
  const int N = h->N;
  const int minN = dbl ? pffftd_min_fft_size(PFFFT_REAL) : pffft_min_fft_size(PFFFT_REAL);
  if (N >= minN) {
    void *setup = dbl ? (void *)pffftd_new_setup_into((char *)h + FFT_ALIGN, N, PFFFT_REAL)
                      : (void *)pffft_new_setup_into((char *)h + FFT_ALIGN, N, PFFFT_REAL);
    if (setup) { h->engine = dbl ? ENG_PFFFTD : ENG_PFFFT; *ppSpec = h; return 0; }
    /* pffft がサイズを拒否した場合は naive に落とす (2の冪では起らない保険) */
  }
  h->engine = ENG_NAIVE;
  naive_init(h);
  *ppSpec = h;
  return 0;
}

/* ---- Run 共通 ---- */
static IppStatus fft_check_spec(const void *spec) {
  if (!spec) return -8;
  if (hdr_of(spec)->magic != FFT_HDR_MAGIC) return -8;
  return 0;
}

/* ============================ 32f (pffft, SIMD float) ============================ */

/* scratch: pBuffer (GetSize の pBufSize = 2N 語) or 内部確保。work=N 語, tmp=N 語。 */
static float *f_scratch(int N, Ipp8u *b, float **ptmp, int *pheap) {
  if (b) { *pheap = 0; *ptmp = (float *)b + N; return (float *)b; }
  float *p = (float *)pffft_aligned_malloc((size_t)2 * N * sizeof(float));
  *pheap = 1; *ptmp = p ? p + N : NULL;
  return p;
}

/* fwd: s ->[pffft-ordered: tmp] -> d (fmt 0=Pack: N 語 / 1=CCS: N+2 語) */
static IppStatus f_fwd_fmt(const float *s, float *d, const void *spec, Ipp8u *b, int fmt) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 0);
  if (h->engine == ENG_NAIVE) {
    double *x = malloc(sizeof(double) * N), *out = malloc(sizeof(double) * (N + 2));
    if (!x || !out) { free(x); free(out); return -8; }
    for (int i = 0; i < N; i++) x[i] = (double)s[i];
    naive_fwd(h, x, out, fmt);
    const int m = fmt ? N + 2 : N;
    for (int i = 0; i < m; i++) d[i] = (float)out[i];
    free(x); free(out); return 0;
  }
  PFFFT_Setup *st = (PFFFT_Setup *)((const char *)h + FFT_ALIGN);
  float *tmp; int heap;
  float *work = f_scratch(N, b, &tmp, &heap);
  if (!work) return -8;
  pffft_transform_ordered(st, s, tmp, work, PFFFT_FORWARD);
  if (fmt == 0) {
    d[0] = (float)(tmp[0] * sc); d[N - 1] = (float)(tmp[1] * sc);
    for (int k = 1; k < N / 2; k++) { d[2 * k - 1] = (float)(tmp[2 * k] * sc); d[2 * k] = (float)(tmp[2 * k + 1] * sc); }
  } else {
    d[0] = (float)(tmp[0] * sc); d[1] = 0; d[N] = (float)(tmp[1] * sc); d[N + 1] = 0;
    for (int k = 1; k < N / 2; k++) { d[2 * k] = (float)(tmp[2 * k] * sc); d[2 * k + 1] = (float)(tmp[2 * k + 1] * sc); }
  }
  if (heap) pffft_aligned_free(work);
  return 0;
}

/* inv: s (Pack/CCS) ->[pffft-ordered: tmp] -> d (N 語) */
static IppStatus f_inv_fmt(const float *s, float *d, const void *spec, Ipp8u *b, int fmt) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 1);
  if (h->engine == ENG_NAIVE) {
    double *in = malloc(sizeof(double) * (N + 2)), *x = malloc(sizeof(double) * N);
    if (!in || !x) { free(in); free(x); return -8; }
    const int m = fmt ? N + 2 : N;
    for (int i = 0; i < m; i++) in[i] = (double)s[i];
    naive_inv(h, in, x, fmt);
    for (int i = 0; i < N; i++) d[i] = (float)x[i];
    free(in); free(x); return 0;
  }
  PFFFT_Setup *st = (PFFFT_Setup *)((const char *)h + FFT_ALIGN);
  float *tmp; int heap;
  float *work = f_scratch(N, b, &tmp, &heap);
  if (!work) return -8;
  tmp[0] = s[0];
  tmp[1] = (fmt == 0) ? s[N - 1] : s[N];
  for (int k = 1; k < N / 2; k++) {
    if (fmt == 0) { tmp[2 * k] = s[2 * k - 1]; tmp[2 * k + 1] = s[2 * k]; }
    else          { tmp[2 * k] = s[2 * k];     tmp[2 * k + 1] = s[2 * k + 1]; }
  }
  pffft_transform_ordered(st, tmp, d, work, PFFFT_BACKWARD);
  for (int i = 0; i < N; i++) d[i] = (float)(d[i] * sc);
  if (heap) pffft_aligned_free(work);
  return 0;
}

/* Perm: pffft unordered をそのまま出し入れする (往復で使用)。naive では Pack 布局と同じ。 */
static IppStatus f_fwd_perm(const float *s, float *d, const void *spec, Ipp8u *b) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 0);
  if (h->engine == ENG_NAIVE) return f_fwd_fmt(s, d, spec, b, 0);
  PFFFT_Setup *st = (PFFFT_Setup *)((const char *)h + FFT_ALIGN);
  float *tmp; int heap;
  float *work = f_scratch(N, b, &tmp, &heap);
  if (!work) return -8;
  pffft_transform(st, s, d, work, PFFFT_FORWARD);   /* in/out alias 可 (pffft.h) */
  for (int i = 0; i < N; i++) d[i] = (float)(d[i] * sc);
  if (heap) pffft_aligned_free(work);
  return 0;
}
static IppStatus f_inv_perm(const float *s, float *d, const void *spec, Ipp8u *b) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 1);
  if (h->engine == ENG_NAIVE) return f_inv_fmt(s, d, spec, b, 0);
  PFFFT_Setup *st = (PFFFT_Setup *)((const char *)h + FFT_ALIGN);
  float *tmp; int heap;
  float *work = f_scratch(N, b, &tmp, &heap);
  if (!work) return -8;
  pffft_transform(st, s, d, work, PFFFT_BACKWARD);
  for (int i = 0; i < N; i++) d[i] = (float)(d[i] * sc);
  if (heap) pffft_aligned_free(work);
  return 0;
}

IppStatus ippsFFTFwd_RToPack_32f(const Ipp32f *pSrc, Ipp32f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_fwd_fmt(pSrc, pDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTFwd_RToPack_32f_I(Ipp32f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_fwd_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTInv_PackToR_32f(const Ipp32f *pSrc, Ipp32f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_inv_fmt(pSrc, pDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTInv_PackToR_32f_I(Ipp32f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_inv_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTFwd_RToCCS_32f(const Ipp32f *pSrc, Ipp32f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_fwd_fmt(pSrc, pDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTFwd_RToCCS_32f_I(Ipp32f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_fwd_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTInv_CCSToR_32f(const Ipp32f *pSrc, Ipp32f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_inv_fmt(pSrc, pDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTInv_CCSToR_32f_I(Ipp32f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_inv_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTFwd_RToPerm_32f(const Ipp32f *pSrc, Ipp32f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_fwd_perm(pSrc, pDst, pFFTSpec, pBuffer);
}
IppStatus ippsFFTFwd_RToPerm_32f_I(Ipp32f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_fwd_perm(pSrcDst, pSrcDst, pFFTSpec, pBuffer);
}
IppStatus ippsFFTInv_PermToR_32f(const Ipp32f *pSrc, Ipp32f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_inv_perm(pSrc, pDst, pFFTSpec, pBuffer);
}
IppStatus ippsFFTInv_PermToR_32f_I(Ipp32f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return f_inv_perm(pSrcDst, pSrcDst, pFFTSpec, pBuffer);
}

/* ============================ 64f (pffft_double, SIMD double) ============================
   pffft_double はバッファに 32B 整列を要求する (AVX 由来; IPP の保証は 16B) ため、
   ユーザーポインタは pffftd_* に直接渡さない。scratch 布局 (3N 語):
   [0..N) 入力 or 中間の複素スペクトル / [N..2N) pffft work / [2N..3N) pffft 出力 ] */

static double *d_scratch(int N, Ipp8u *b, int *pheap) {
  if (b) { *pheap = 0; double *base = (double *)fft_align32(b); return base; }
  double *p = (double *)pffftd_aligned_malloc((size_t)3 * N * sizeof(double) + FFT_ALIGN);
  *pheap = 1;
  return p;
}

static IppStatus d_fwd_fmt(const double *s, double *d, const void *spec, Ipp8u *b, int fmt) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 0);
  if (h->engine == ENG_NAIVE) {
    double *x = malloc(sizeof(double) * N), *out = malloc(sizeof(double) * (N + 2));
    if (!x || !out) { free(x); free(out); return -8; }
    for (int i = 0; i < N; i++) x[i] = s[i];
    naive_fwd(h, x, out, fmt);
    const int m = fmt ? N + 2 : N;
    for (int i = 0; i < m; i++) d[i] = out[i];
    free(x); free(out); return 0;
  }
  PFFFTD_Setup *st = (PFFFTD_Setup *)((const char *)h + FFT_ALIGN);
  int heap;
  double *scratch = d_scratch(N, b, &heap);
  if (!scratch) return -8;
  double *in = scratch, *work = scratch + N, *out = scratch + 2 * N;
  for (int i = 0; i < N; i++) in[i] = s[i];
  pffftd_transform_ordered(st, in, out, work, PFFFT_FORWARD);
  /* out 領域に pffft-ordered %[X0, X_{N/2}, X1.re, X1.im, ...] が入る */
  const double *tmp = out;
  if (fmt == 0) {
    d[0] = tmp[0] * sc; d[N - 1] = tmp[1] * sc;
    for (int k = 1; k < N / 2; k++) { d[2 * k - 1] = tmp[2 * k] * sc; d[2 * k] = tmp[2 * k + 1] * sc; }
  } else {
    d[0] = tmp[0] * sc; d[1] = 0; d[N] = tmp[1] * sc; d[N + 1] = 0;
    for (int k = 1; k < N / 2; k++) { d[2 * k] = tmp[2 * k] * sc; d[2 * k + 1] = tmp[2 * k + 1] * sc; }
  }
  if (heap) pffftd_aligned_free(scratch);
  return 0;
}

static IppStatus d_inv_fmt(const double *s, double *d, const void *spec, Ipp8u *b, int fmt) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 1);
  if (h->engine == ENG_NAIVE) {
    double *in = malloc(sizeof(double) * (N + 2)), *x = malloc(sizeof(double) * N);
    if (!in || !x) { free(in); free(x); return -8; }
    const int m = fmt ? N + 2 : N;
    for (int i = 0; i < m; i++) in[i] = s[i];
    naive_inv(h, in, x, fmt);
    for (int i = 0; i < N; i++) d[i] = x[i];
    free(in); free(x); return 0;
  }
  PFFFTD_Setup *st = (PFFFTD_Setup *)((const char *)h + FFT_ALIGN);
  int heap;
  double *scratch = d_scratch(N, b, &heap);
  if (!scratch) return -8;
  double *tmp = scratch, *work = scratch + N, *out = scratch + 2 * N;
  tmp[0] = s[0];
  tmp[1] = (fmt == 0) ? s[N - 1] : s[N];
  for (int k = 1; k < N / 2; k++) {
    if (fmt == 0) { tmp[2 * k] = s[2 * k - 1]; tmp[2 * k + 1] = s[2 * k]; }
    else          { tmp[2 * k] = s[2 * k];     tmp[2 * k + 1] = s[2 * k + 1]; }
  }
  pffftd_transform_ordered(st, tmp, out, work, PFFFT_BACKWARD);
  for (int i = 0; i < N; i++) d[i] = out[i] * sc;
  if (heap) pffftd_aligned_free(scratch);
  return 0;
}

static IppStatus d_fwd_perm(const double *s, double *d, const void *spec, Ipp8u *b) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 0);
  if (h->engine == ENG_NAIVE) return d_fwd_fmt(s, d, spec, b, 0);
  PFFFTD_Setup *st = (PFFFTD_Setup *)((const char *)h + FFT_ALIGN);
  int heap;
  double *scratch = d_scratch(N, b, &heap);
  if (!scratch) return -8;
  double *in = scratch, *work = scratch + N, *out = scratch + 2 * N;
  for (int i = 0; i < N; i++) in[i] = s[i];
  pffftd_transform(st, in, out, work, PFFFT_FORWARD);
  for (int i = 0; i < N; i++) d[i] = out[i] * sc;
  if (heap) pffftd_aligned_free(scratch);
  return 0;
}
static IppStatus d_inv_perm(const double *s, double *d, const void *spec, Ipp8u *b) {
  IppStatus cst = fft_check_spec(spec); if (cst) return cst;
  if (!s || !d) return -8;
  const FftHdr *h = hdr_of(spec);
  const int N = h->N; const double sc = scale_of(h, 1);
  if (h->engine == ENG_NAIVE) return d_inv_fmt(s, d, spec, b, 0);
  PFFFTD_Setup *st = (PFFFTD_Setup *)((const char *)h + FFT_ALIGN);
  int heap;
  double *scratch = d_scratch(N, b, &heap);
  if (!scratch) return -8;
  double *in = scratch, *work = scratch + N, *out = scratch + 2 * N;
  for (int i = 0; i < N; i++) in[i] = s[i];
  pffftd_transform(st, in, out, work, PFFFT_BACKWARD);
  for (int i = 0; i < N; i++) d[i] = out[i] * sc;
  if (heap) pffftd_aligned_free(scratch);
  return 0;
}

IppStatus ippsFFTFwd_RToPack_64f(const Ipp64f *pSrc, Ipp64f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_fwd_fmt(pSrc, pDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTFwd_RToPack_64f_I(Ipp64f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_fwd_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTInv_PackToR_64f(const Ipp64f *pSrc, Ipp64f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_inv_fmt(pSrc, pDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTInv_PackToR_64f_I(Ipp64f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_inv_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 0);
}
IppStatus ippsFFTFwd_RToCCS_64f(const Ipp64f *pSrc, Ipp64f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_fwd_fmt(pSrc, pDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTFwd_RToCCS_64f_I(Ipp64f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_fwd_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTInv_CCSToR_64f(const Ipp64f *pSrc, Ipp64f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_inv_fmt(pSrc, pDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTInv_CCSToR_64f_I(Ipp64f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_inv_fmt(pSrcDst, pSrcDst, pFFTSpec, pBuffer, 1);
}
IppStatus ippsFFTFwd_RToPerm_64f(const Ipp64f *pSrc, Ipp64f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_fwd_perm(pSrc, pDst, pFFTSpec, pBuffer);
}
IppStatus ippsFFTFwd_RToPerm_64f_I(Ipp64f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_fwd_perm(pSrcDst, pSrcDst, pFFTSpec, pBuffer);
}
IppStatus ippsFFTInv_PermToR_64f(const Ipp64f *pSrc, Ipp64f *pDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_inv_perm(pSrc, pDst, pFFTSpec, pBuffer);
}
IppStatus ippsFFTInv_PermToR_64f_I(Ipp64f *pSrcDst, const void *pFFTSpec, Ipp8u *pBuffer) {
  return d_inv_perm(pSrcDst, pSrcDst, pFFTSpec, pBuffer);
}

/* ============================ GetSize / Init (公開) ============================ */

IppStatus ippsFFTGetSize_R_32f(int order, int flag, int hint, int *pSpecSize, int *pSpecBufSize, int *pBufSize) {
  return fft_getsize_impl(order, flag, 0, pSpecSize, pSpecBufSize, pBufSize);
}
IppStatus ippsFFTGetSize_R_64f(int order, int flag, int hint, int *pSpecSize, int *pSpecBufSize, int *pBufSize) {
  return fft_getsize_impl(order, flag, 1, pSpecSize, pSpecBufSize, pBufSize);
}
IppStatus ippsFFTInit_R_32f(void **ppFFTSpec, int order, int flag, int hint, Ipp8u *pSpec, Ipp8u *pSpecBuffer) {
  return fft_init_impl(ppFFTSpec, order, flag, hint, pSpec, pSpecBuffer, 0);
}
IppStatus ippsFFTInit_R_64f(void **ppFFTSpec, int order, int flag, int hint, Ipp8u *pSpec, Ipp8u *pSpecBuffer) {
  return fft_init_impl(ppFFTSpec, order, flag, hint, pSpec, pSpecBuffer, 1);
}
