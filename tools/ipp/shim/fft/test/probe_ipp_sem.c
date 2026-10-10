/* 実 IPP (win64 dsp_ippv2_x64.dll をネイティブ実行) の FFT 関数の「意味」を採取するプローブ (CAB-139)。
   - GetSize/Init/Run の status コード (order/flag/NULL の格子)
   - Run の読み書き長 (Pack/CCS/Perm, in-place / 非 in-place; 呼出前後の diff 語数)
   出力: 事実一覧。実装 (ipp_fft_pffft.c) のエラーコード鏡像化の根拠。 */
#define _GNU_SOURCE
#include "../../../ref/pe_load.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>

typedef int (MS *getsz_t)(int, int, int, int *, int *, int *);
typedef int (MS *init_t)(void **, int, int, int, uint8_t *, uint8_t *);
typedef int (MS *tr_t)(const void *, void *, const void *, uint8_t *);
typedef int (MS *tri_t)(void *, const void *, uint8_t *);

static PE pe;
static void *expf_(const char *fmt, ...) {
  char nm[64]; va_list ap; va_start(ap, fmt); vsnprintf(nm, 64, fmt, ap); va_end(ap);
  void *p = pe_export(&pe, nm); if (!p) { fprintf(stderr, "no export %s\n", nm); exit(1); } return p;
}
/* 呼出前後で一致しない語数 (es=element size, cap=検査語数) */
static int g_maxidx;
static int words_changed(const void *before, const void *after, int es, int cap) {
  const unsigned char *b = before, *a = after; int n = 0; g_maxidx = -1;
  for (int i = 0; i < cap * es; i++) if (b[i] != a[i]) { n++; g_maxidx = i; }
  return (n + es - 1) / es;
}

int main(int argc, char **argv) {
  if (argc < 2) { printf("usage: probe_ipp_sem <dll> [32f|64f]\n"); return 2; }
  if (pe_load(argv[1], &pe)) { printf("pe_load failed\n"); return 1; }
  setvbuf(stdout, NULL, _IONBF, 0);
  ((int (MS *)(uint64_t))expf_("ippSetCpuFeatures"))(~0ULL);
  const char *sfx = (argc > 2 && !strcmp(argv[2], "64f")) ? "64f" : "32f";
  int dbl = sfx[0] == '6', es = dbl ? 8 : 4;
  getsz_t gs = expf_("ippsFFTGetSize_R_%s", sfx);
  init_t in = expf_("ippsFFTInit_R_%s", sfx);
  tr_t fwpack = expf_("ippsFFTFwd_RToPack_%s", sfx), fwccs = expf_("ippsFFTFwd_RToCCS_%s", sfx), fwperm = expf_("ippsFFTFwd_RToPerm_%s", sfx);
  tri_t fwpackI = expf_("ippsFFTFwd_RToPack_%s_I", sfx), fwccsI = expf_("ippsFFTFwd_RToCCS_%s_I", sfx), fwpermI = expf_("ippsFFTFwd_RToPerm_%s_I", sfx);
  tr_t ivccs = expf_("ippsFFTInv_CCSToR_%s", sfx), ivperm = expf_("ippsFFTInv_PermToR_%s", sfx);
  tri_t ivccsI = expf_("ippsFFTInv_CCSToR_%s_I", sfx), ivpermI = expf_("ippsFFTInv_PermToR_%s_I", sfx);

  printf("== %s ==\n", sfx);
  printf("-- GetSize(order,flag,hint=0) -> status / spec / initbuf / work --\n");
  int orders[] = {-2, -1, 0, 1, 2, 3, 4, 5, 12, 16, 17, 20};
  int flags[] = {0, 1, 2, 3, 4, 5, 7, 8, 9, 12, 15, 16, 32, -1};
  for (unsigned oi = 0; oi < sizeof orders / sizeof *orders; oi++) {
    printf("  order=%3d:", orders[oi]);
    for (unsigned fi = 0; fi < sizeof flags / sizeof *flags; fi++) {
      int a = -77, b = -77, c = -77;
      int st = gs(orders[oi], flags[fi], 0, &a, &b, &c);
      printf(" [f%d:s%d:%d/%d/%d]", flags[fi], st, a, b, c);
    }
    printf("\n");
  }
  printf("-- hint (order=8, flag=1): status / spec / initbuf / work --\n");
  for (int hint = 0; hint <= 2; hint++) { int a = -1, b = -1, c = -1; int st = gs(8, 1, hint, &a, &b, &c); printf("  hint=%d: s%d spec=%d init=%d work=%d\n", hint, st, a, b, c); }

  printf("-- Init エラー系 --\n");
  { /* 各 order の必要サイズをその都度 gs で取り, バッファを過小にしない */
    void *spec = (void *)1; int st;
    for (int oi = 0; oi < 4; oi++) {
      int o = (int)(int[]){0, 1, 8, 17}[oi];
      int a = 0, b = 0, c = 0, stg = gs(o, 1, 0, &a, &b, &c);
      if (stg != 0) { printf("  Init(order=%d): GetSize=%d (スキップ)\n", o, stg); if (o == 8) o = 8; continue; }
      uint8_t *sp = malloc((size_t)a + 64), *sb = malloc((size_t)(b > 0 ? b : 64) + 64);
      if (o == 0) { st = in(&spec, o, 1, 0, sp, sb); printf("  Init(order=0):              %d\n", st); }
      if (o == 17) {
        st = in(&spec, o, 1, 0, sp, sb); printf("  Init(order=17):             %d\n", st);
        st = in(&spec, o, 0, 0, sp, sb); printf("  Init(order=17,flag=0):      %d\n", st);
      }
      if (o == 8) {
        st = in(NULL, 8, 1, 0, sp, sb); printf("  Init(ppSpec=NULL):          %d\n", st);
        st = in(&spec, 8, 1, 0, NULL, sb); printf("  Init(pSpec=NULL):           %d\n", st);
        st = in(&spec, 8, 0, 0, sp, sb); printf("  Init(flag=0):               %d\n", st);
        st = in(&spec, 8, 16, 0, sp, sb); printf("  Init(flag=16):              %d\n", st);
        st = in(&spec, 8, 1, 0, sp, NULL); printf("  Init(pSpecBuffer=NULL):     %d (b=%d)\n", st, b);
        st = in(&spec, 8, 1, 0, sp, sb); printf("  Init(正常):                 %d\n", st);
      }
      free(sp); free(sb);
    }
  }

  printf("-- Run NULL 系 (order=8 Init 済) --\n");
  { int a = 0, b = 0, c = 0; gs(8, 1, 0, &a, &b, &c);
    uint8_t *sp = malloc((size_t)a + 64); void *spec = 0; in(&spec, 8, 1, 0, sp, 0);
    int N = 256; uint8_t *x = malloc(es * (N + 8)), *y = malloc(es * (N + 8));
    int st;
    st = fwpack(x, y, NULL, NULL); printf("  Fwd_RToPack(spec=NULL): %d\n", st);
    st = fwpack(NULL, y, spec, NULL); printf("  Fwd_RToPack(src=NULL):  %d\n", st);
    st = fwpack(x, NULL, spec, NULL); printf("  Fwd_RToPack(dst=NULL):  %d\n", st);
    st = fwpack(x, y, spec, NULL); printf("  Fwd_RToPack(buf=NULL):  %d\n", st);
    free(sp); free(x); free(y);
  }

  printf("-- Run 読み書き長 (order=8 => N=256, flag=8, 呼出前後 diff) --\n");
  { int N = 256, flag = 8; int a = 0, b = 0, c = 0; gs(8, flag, 0, &a, &b, &c);
    uint8_t *sp = malloc((size_t)a + 64); void *spec = 0; in(&spec, 8, flag, 0, sp, 0);
    uint8_t *bf = c > 0 ? malloc((size_t)c + 64) : NULL;
    uint8_t *x = malloc(es * (N + 8)), *xb = malloc(es * (N + 8)), *y = malloc(es * (N + 8)), *yb = malloc(es * (N + 8));
#define SETX(nwords) for (int i = 0; i < (nwords); i++) { double v = 0.25 * (i % 11) - 1; if (dbl) ((double *)x)[i] = v; else ((float *)x)[i] = (float)v; }
#define SETY(nwords) for (int i = 0; i < (nwords); i++) { double v = -7.5; if (dbl) ((double *)y)[i] = v; else ((float *)y)[i] = (float)v; }
#define RUNO(label, fn, outCap) { SETX(N); SETY(outCap); memcpy(xb, x, es * (N + 8)); memcpy(yb, y, es * (N + 8)); \
      int st_ = fn(x, y, spec, bf); \
      printf("  %-22s st=%d srcChanged=%d dstChanged=%d dstMaxWords=%d (dstCap=%d)\n", label, st_, words_changed(xb, x, es, N + 4), (words_changed(yb, y, es, outCap + 4), g_maxidx / es + 1), outCap); }
#define RUNI(label, fn, cap) { SETX(cap + 2); memcpy(xb, x, es * (cap + 4)); \
      int st_ = fn(x, spec, bf); \
      printf("  %-22s st=%d bufChanged=%d bufMaxWords=%d (bufCap=%d, in=N 語)\n", label, st_, words_changed(xb, x, es, cap + 4), g_maxidx / es + 1, cap); }
    RUNO("Fwd_RToPack", fwpack, N);
    RUNO("Fwd_RToCCS", fwccs, N);
    RUNO("Fwd_RToPerm", fwperm, N);
    RUNI("Fwd_RToPack_I", fwpackI, N);
    RUNI("Fwd_RToCCS_I", fwccsI, N);
    RUNI("Fwd_RToPerm_I", fwpermI, N);
    /* 逆変換: CCS 入力は N+2 語 / Perm 入力は N 語を想定して書き換え語数を見る */
    for (int i = 0; i < N + 2; i++) { double v = (i == 0 || i == N) ? 100 : (i % 2 ? 0.5 : -0.25); if (dbl) ((double *)x)[i] = v; else ((float *)x)[i] = (float)v; }
    SETY(N + 4); memcpy(yb, y, es * (N + 8));
    { int st_ = ivccs(x, y, spec, bf); { int w_ = words_changed(yb, y, es, N + 4); printf("  Inv_CCSToR             st=%d dstChanged=%d dstMaxWords=%d\n", st_, w_, g_maxidx / es + 1); }; }
    { int st_ = ivperm(x, y, spec, bf); { int w_ = words_changed(yb, y, es, N + 4); printf("  Inv_PermToR            st=%d dstChanged=%d dstMaxWords=%d\n", st_, w_, g_maxidx / es + 1); }; }
    /* in-place 逆: バッファに CCS N+2 語を置いて呼ぶ */
    for (int i = 0; i < N + 2; i++) { double v = (i == 0 || i == N) ? 100 : (i % 2 ? 0.5 : -0.25); if (dbl) ((double *)x)[i] = v; else ((float *)x)[i] = (float)v; }
    memcpy(xb, x, es * (N + 8));
    { int st_ = ivccsI(x, spec, bf); { int w_ = words_changed(xb, x, es, N + 4); printf("  Inv_CCSToR_I           st=%d bufChanged=%d bufMaxWords=%d\n", st_, w_, g_maxidx / es + 1); }; }
    free(sp); if (bf) free(bf); free(x); free(xb); free(y); free(yb);
  }
  printf("probe_ipp_sem done\n");
  return 0;
}
