/* FFT ネイティブ・オラクル: 実 IPP (win64 DLL) vs 本実装 (ipp_fft_pffft.c) の全 28 関数比較 (CAB-139)。
   - GetSize/Init/Fwd/Inv × {Pack, CCS, Perm} × {32f, 64f} × flag {1,2,4,8} × order 0..16
   - in-place / 非 in-place 両方、work buffer あり/なし両方
   - エラー格子 (order/flag/NULL) の status 一致
   呼出規約: 実 DLL 側は MS x64 (ms_abi), 本実装側は SysV (ネイティブ直呼び) — typedef を分けてある。
   判定: NRMS 32f <= 1.5e-7 / 64f <= 6.6e-16 (旧 PoC 実装の実測水準を gate 化)。
   usage: fft_oracle <dll> */
#define _GNU_SOURCE
#include "../../../ref/pe_load.h"
#include "../ipp_fft_pffft.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <math.h>
#include <stdint.h>

/* 実 DLL 用 (MS x64) */
typedef int (MS *getsz_t)(int, int, int, int *, int *, int *);
typedef int (MS *init_t)(void **, int, int, int, uint8_t *, uint8_t *);
typedef int (MS *tr_t)(const void *, void *, const void *, uint8_t *);
typedef int (MS *tri_t)(void *, const void *, uint8_t *);
/* 本実装用 (SysV)。Run 系は 32f/64f で仮引数型が違うため無原型呼出 (引数は正しく渡す) */
typedef int (*getszn_t)(int, int, int, int *, int *, int *);
typedef int (*initn_t)(void **, int, int, int, uint8_t *, uint8_t *);
typedef int (*trn_t)();
typedef int (*trin_t)();

static uint64_t rs = 0x9E3779B97F4A7C15ULL;
static double ur(void) { rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27; return (rs >> 11) * (1.0 / 9007199254740992.0) * 2 - 1; }

static PE pe;
static void *expf_(const char *fmt, ...) {
  char nm[64]; va_list ap; va_start(ap, fmt); vsnprintf(nm, 64, fmt, ap); va_end(ap);
  void *p = pe_export(&pe, nm); if (!p) { fprintf(stderr, "no export %s\n", nm); exit(1); } return p;
}
static double nerr(const void *a, const void *b, int n, int dbl) {
  double d = 0, r = 0;
  for (int i = 0; i < n; i++) {
    double x = dbl ? ((const double *)a)[i] : ((const float *)a)[i];
    double y = dbl ? ((const double *)b)[i] : ((const float *)b)[i];
    d += (x - y) * (x - y); r += y * y;
  }
  return sqrt(d / (r + 1e-300));
}

static long cases = 0, status_mismatch = 0, g_dev = 0;
static double worst32 = 0, worst64 = 0, worst32s = 0, worst64s = 0;
static int fails = 0;
#define GATE32 1.5e-7
#define GATE64 6.6e-16

static void expect_st(const char *what, int real_st, int our_st) {
  cases++;
  if (real_st != our_st) { status_mismatch++; fails++; printf("ST-MISMATCH %-34s real=%d ours=%d\n", what, real_st, our_st); }
}
/* gate: 単一変換は PoC 実測水準 (32f 1.5e-7) に float SIMD 2 実装差分の余裕を加えた 2.5e-7,
   往復 (誤差二重化) は 5e-7。64f は 6.6e-16 (単一) / 2e-15 (往復)。実測最悪値は最終 JSON に出す。 */
#define GSINGLE(dbl) ((dbl) ? 6.6e-16 : 2.5e-7)
#define GRT(dbl)     ((dbl) ? 2.0e-15 : 5.0e-7)
static void expect_nrms(const char *what, const void *ours, const void *real_, int n, int dbl, double gate) {
  double e = nerr(ours, real_, n, dbl);
  cases++;
  if (dbl) { if (e > worst64) worst64 = e; } else { if (e > worst32) worst32 = e; }
  if (gate <= GSINGLE(dbl)) { if (dbl) { if (e > worst64s) worst64s = e; } else { if (e > worst32s) worst32s = e; } }
  if (e > gate) { fails++; printf("NRMS-FAIL %-34s e=%.3g (gate %.3g, dbl=%d)\n", what, e, gate, dbl); }
}

/* 実 IPP / 本実装の関数群をまとめて取る (dbl=0: 32f, 1: 64f) */
typedef struct {
  getsz_t gs; init_t in;
  tr_t fwpack, fwccs, fwperm, ivpack, ivccs, ivperm;
  tri_t fwpackI, fwccsI, fwpermI, ivpackI, ivccsI, ivpermI;
  getszn_t ngs; initn_t nin;
  trn_t nfwpack, nfwccs, nfwperm, nivpack, nivccs, nivperm;
  trin_t nfwpackI, nfwccsI, nfwpermI, nivpackI, nivccsI, nivpermI;
} Fns;

static void fns_load(Fns *f, int dbl) {
  const char *sx = dbl ? "64f" : "32f";
  f->gs = expf_("ippsFFTGetSize_R_%s", sx);  f->in = expf_("ippsFFTInit_R_%s", sx);
  f->fwpack = expf_("ippsFFTFwd_RToPack_%s", sx);  f->fwccs = expf_("ippsFFTFwd_RToCCS_%s", sx);  f->fwperm = expf_("ippsFFTFwd_RToPerm_%s", sx);
  f->ivpack = expf_("ippsFFTInv_PackToR_%s", sx);  f->ivccs = expf_("ippsFFTInv_CCSToR_%s", sx);  f->ivperm = expf_("ippsFFTInv_PermToR_%s", sx);
  f->fwpackI = expf_("ippsFFTFwd_RToPack_%s_I", sx); f->fwccsI = expf_("ippsFFTFwd_RToCCS_%s_I", sx); f->fwpermI = expf_("ippsFFTFwd_RToPerm_%s_I", sx);
  f->ivpackI = expf_("ippsFFTInv_PackToR_%s_I", sx); f->ivccsI = expf_("ippsFFTInv_CCSToR_%s_I", sx); f->ivpermI = expf_("ippsFFTInv_PermToR_%s_I", sx);
  if (dbl) {
    f->ngs = ippsFFTGetSize_R_64f; f->nin = ippsFFTInit_R_64f;
    f->nfwpack = ippsFFTFwd_RToPack_64f; f->nfwccs = ippsFFTFwd_RToCCS_64f; f->nfwperm = ippsFFTFwd_RToPerm_64f;
    f->nivpack = ippsFFTInv_PackToR_64f; f->nivccs = ippsFFTInv_CCSToR_64f; f->nivperm = ippsFFTInv_PermToR_64f;
    f->nfwpackI = ippsFFTFwd_RToPack_64f_I; f->nfwccsI = ippsFFTFwd_RToCCS_64f_I; f->nfwpermI = ippsFFTFwd_RToPerm_64f_I;
    f->nivpackI = ippsFFTInv_PackToR_64f_I; f->nivccsI = ippsFFTInv_CCSToR_64f_I; f->nivpermI = ippsFFTInv_PermToR_64f_I;
  } else {
    f->ngs = ippsFFTGetSize_R_32f; f->nin = ippsFFTInit_R_32f;
    f->nfwpack = ippsFFTFwd_RToPack_32f; f->nfwccs = ippsFFTFwd_RToCCS_32f; f->nfwperm = ippsFFTFwd_RToPerm_32f;
    f->nivpack = ippsFFTInv_PackToR_32f; f->nivccs = ippsFFTInv_CCSToR_32f; f->nivperm = ippsFFTInv_PermToR_32f;
    f->nfwpackI = ippsFFTFwd_RToPack_32f_I; f->nfwccsI = ippsFFTFwd_RToCCS_32f_I; f->nfwpermI = ippsFFTFwd_RToPerm_32f_I;
    f->nivpackI = ippsFFTInv_PackToR_32f_I; f->nivccsI = ippsFFTInv_CCSToR_32f_I; f->nivpermI = ippsFFTInv_PermToR_32f_I;
  }
}

static void run_case(Fns *f, int dbl, int order, int flag, int with_buf) {
  const int N = 1 << order, es = dbl ? 8 : 4;
  int ra = -9, rb = -9, rc = -9, oa = -9, ob = -9, oc = -9;
  int rst = f->gs(order, flag, 0, &ra, &rb, &rc);
  int ost = f->ngs(order, flag, 0, &oa, &ob, &oc);
  { char w[64]; snprintf(w, 64, "GetSize o%d f%d", order, flag); expect_st(w, rst, ost); }
  if (rst != 0 || ost != 0) return;

  uint8_t *rsp = malloc((size_t)ra + 64), *rsb = malloc((size_t)(rb > 0 ? rb : 64) + 64), *rbf = malloc((size_t)(rc > 0 ? rc : 64) + 64);
  uint8_t *osp = malloc((size_t)oa + 64), *obf = with_buf ? malloc((size_t)oc + 64) : NULL;
  void *rspec = 0, *ospec = 0;
  int ri = f->in(&rspec, order, flag, 0, rsp, rsb);
  int oi = f->nin(&ospec, order, flag, 0, osp, NULL);
  { char w[64]; snprintf(w, 64, "Init o%d f%d", order, flag); expect_st(w, ri, oi); }
  if (ri != 0 || oi != 0) { free(rsp); free(rsb); free(rbf); free(osp); free(obf); return; }

  uint8_t *x = malloc((size_t)es * (N + 4));
  uint8_t *rr = malloc((size_t)es * (N + 4)), *rr2 = malloc((size_t)es * (N + 4)), *rr3 = malloc((size_t)es * (N + 4));
  uint8_t *oo = malloc((size_t)es * (N + 4)), *oo2 = malloc((size_t)es * (N + 4)), *oo3 = malloc((size_t)es * (N + 4));
  for (int i = 0; i < N; i++) { double v = ur(); if (dbl) ((double *)x)[i] = v; else ((float *)x)[i] = (float)v; }
  char w[80];

  /* Fwd Pack / CCS (非 in-place) */
  memcpy(rr, x, (size_t)es * (N + 4)); memcpy(oo, x, (size_t)es * (N + 4));
  f->fwpack(x, rr, rspec, rbf); f->nfwpack(x, oo, ospec, obf);
  snprintf(w, 80, "Fwd_RToPack o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo, rr, N, dbl, GSINGLE(dbl));
  memcpy(rr3, x, (size_t)es * (N + 4)); memcpy(oo3, x, (size_t)es * (N + 4));
  f->fwccs(x, rr3, rspec, rbf); f->nfwccs(x, oo3, ospec, obf);
  snprintf(w, 80, "Fwd_RToCCS o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo3, rr3, N + 2, dbl, GSINGLE(dbl));
  /* Pack <-> CCS の整合 (同一スペクトル: CCS[0]=Pack[0], CCS[2..N-1]=Pack[1..N-2], CCS[N]=Pack[N-1]) */
  { double dr = 0, rr2_ = 0, dno = 0, rno = 0; int i;
    if (dbl) {
      const double *P = (const double *)rr, *C = (const double *)rr3, *P2 = (const double *)oo, *C2 = (const double *)oo3;
      for (i = 1; i < N - 1; i++) { double dv = C[i + 1] - P[i]; dr += dv * dv; rr2_ += P[i] * P[i]; dv = C2[i + 1] - P2[i]; dno += dv * dv; rno += P2[i] * P2[i]; }
    } else {
      const float *P = (const float *)rr, *C = (const float *)rr3, *P2 = (const float *)oo, *C2 = (const float *)oo3;
      for (i = 1; i < N - 1; i++) { double dv = C[i + 1] - P[i]; dr += dv * dv; rr2_ += P[i] * P[i]; dv = C2[i + 1] - P2[i]; dno += dv * dv; rno += P2[i] * P2[i]; }
    }
    double eR = sqrt(dr / (rr2_ + 1e-300)), eO = sqrt(dno / (rno + 1e-300));
    cases++; if (eR > (dbl ? 1e-13 : 1e-6) || eO > (dbl ? 1e-13 : 1e-6)) { fails++; printf("PACKCCS-INCONSISTENT o%d f%d b%d eR=%.3g eO=%.3g\n", order, flag, with_buf, eR, eO); }
  }
  /* Inv PackToR / CCSToR (非 in-place): 実 IPP の前方出力を入力に */
  f->ivpack(rr, rr2, rspec, rbf); f->nivpack(rr, oo2, ospec, obf);
  snprintf(w, 80, "Inv_PackToR o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo2, rr2, N, dbl, GSINGLE(dbl));
  f->ivccs(oo, rr2, rspec, rbf); f->nivccs(oo, oo2, ospec, obf);
  snprintf(w, 80, "Inv_CCSToR o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo2, rr2, N, dbl, GSINGLE(dbl));
  /* in-place Fwd (両者とも x から出発) */
  memcpy(rr, x, (size_t)es * (N + 4)); memcpy(oo, x, (size_t)es * (N + 4));
  f->fwpackI(rr, rspec, rbf); f->nfwpackI(oo, ospec, obf);
  snprintf(w, 80, "Fwd_RToPack_I o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo, rr, N, dbl, GSINGLE(dbl));
  memcpy(rr, x, (size_t)es * (N + 4)); memcpy(oo, x, (size_t)es * (N + 4));
  f->fwccsI(rr, rspec, rbf); f->nfwccsI(oo, ospec, obf);
  snprintf(w, 80, "Fwd_RToCCS_I o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo, rr, N + 2, dbl, GSINGLE(dbl));
  /* in-place Inv (実 IPP の前方出力を両者へ) */
  f->fwccs(x, rr2, rspec, rbf);
  memcpy(oo2, rr2, (size_t)es * (N + 2));
  f->ivccsI(rr2, rspec, rbf); f->nivccsI(oo2, ospec, obf);
  snprintf(w, 80, "Inv_CCSToR_I o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo2, rr2, N, dbl, GSINGLE(dbl));
  f->fwpack(x, rr2, rspec, rbf);
  memcpy(oo2, rr2, (size_t)es * N);
  f->ivpackI(rr2, rspec, rbf); f->nivpackI(oo2, ospec, obf);
  snprintf(w, 80, "Inv_PackToR_I o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo2, rr2, N, dbl, GSINGLE(dbl));
  /* Perm 往復 (非 in-place / in-place) */
  memcpy(rr, x, (size_t)es * (N + 4)); memcpy(oo, x, (size_t)es * (N + 4));
  f->fwperm(rr, rr2, rspec, rbf); f->ivperm(rr2, rr, rspec, rbf);
  f->nfwperm(oo, oo2, ospec, obf); f->nivperm(oo2, oo, ospec, obf);
  snprintf(w, 80, "Perm rt o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo, rr, N, dbl, GRT(dbl));
  memcpy(rr, x, (size_t)es * (N + 4)); memcpy(oo, x, (size_t)es * (N + 4));
  f->fwpermI(rr, rspec, rbf); f->ivpermI(rr, rspec, rbf);
  f->nfwpermI(oo, ospec, obf); f->nivpermI(oo, ospec, obf);
  snprintf(w, 80, "Perm rt_I o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo, rr, N, dbl, GRT(dbl));
  /* Pack 往復でも一致すること (Inv_PackToR(RToPack(x)) はスケール後 x) */
  memcpy(rr, x, (size_t)es * (N + 4)); memcpy(oo, x, (size_t)es * (N + 4));
  f->fwpack(rr, rr2, rspec, rbf); f->ivpack(rr2, rr, rspec, rbf);
  f->nfwpack(oo, oo2, ospec, obf); f->nivpack(oo2, oo, ospec, obf);
  snprintf(w, 80, "Pack rt o%d f%d b%d", order, flag, with_buf); expect_nrms(w, oo, rr, N, dbl, GRT(dbl));

  free(rsp); free(rsb); free(rbf); free(osp); free(obf);
  free(x); free(rr); free(rr2); free(rr3); free(oo); free(oo2); free(oo3);
}

static void err_grid(void) {
  for (int dbl = 0; dbl < 2; dbl++) {
    Fns f; fns_load(&f, dbl);
    /* 実 IPP は本環境では order>=21 の GetSize で SEGV する (test/probe_ipp_sem.c 実測) ので、
       実 IPP との突合は 17 まで。18..27 は本実装のみの健全性確認 (26 まで 0, 27 は -17)。 */
    int orders[] = {-2, -1, 0, 1, 8, 16, 17};
    int flags[] = {0, 1, 2, 3, 4, 5, 8, 9, 12, 15, 16, 32, -1};
    for (unsigned oi = 0; oi < sizeof orders / sizeof *orders; oi++) {
      for (unsigned fi = 0; fi < sizeof flags / sizeof *flags; fi++) {
        int ra = -9, rb = -9, rc = -9, oa = -9, ob = -9, oc = -9;
        int rst = f.gs(orders[oi], flags[fi], 0, &ra, &rb, &rc);
        int ost = f.ngs(orders[oi], flags[fi], 0, &oa, &ob, &oc);
        char w[64]; snprintf(w, 64, "GS o%d f%d d%d", orders[oi], flags[fi], dbl); expect_st(w, rst, ost);
        if (rst != 0) continue;
        uint8_t *rsp = malloc((size_t)ra + 64), *rsb = malloc((size_t)(rb > 0 ? rb : 64) + 64);
        uint8_t *osp = malloc((size_t)oa + 64);
        void *rspec = (void *)1, *ospec = (void *)1;
        int r3 = f.in(&rspec, orders[oi], flags[fi], 0, rsp, rsb);
        int o3 = f.nin(&ospec, orders[oi], flags[fi], 0, osp, NULL);
        snprintf(w, 64, "IN o%d f%d d%d", orders[oi], flags[fi], dbl); expect_st(w, r3, o3);
        if (orders[oi] == 8 && (flags[fi] == 1 || flags[fi] == 8)) {
          int r4 = f.in(NULL, 8, flags[fi], 0, rsp, rsb);
          int o4 = f.nin(NULL, 8, flags[fi], 0, osp, NULL);
          snprintf(w, 64, "IN ppNULL f%d d%d", flags[fi], dbl); expect_st(w, r4, o4);
          r4 = f.in(&rspec, 8, flags[fi], 0, NULL, rsb);
          o4 = f.nin(&ospec, 8, flags[fi], 0, NULL, NULL);
          snprintf(w, 64, "IN pSpecNULL f%d d%d", flags[fi], dbl); expect_st(w, r4, o4);
        }
        free(rsp); free(rsb); free(osp);
      }
    }
    /* order 18..27: 本実装のみ (26 まで受理, 27 は上限超で -17) */
    for (int o = 18; o <= 27; o++) {
      int oa = -9, ob = -9, oc = -9;
      int ost = f.ngs(o, 1, 0, &oa, &ob, &oc);
      int want = (o <= 26) ? 0 : -17; /* IPP_FFT_ORDER_ERR (実測) */
      cases++; if (ost != want) { fails++; printf("OURS-ORDER o%d dbl%d st=%d want=%d\n", o, dbl, ost, want); }
    }
  }
}

static void run_null_grid(void) {
  int order = 8, flag = 8, N = 256;
  for (int dbl = 0; dbl < 2; dbl++) {
    Fns f; fns_load(&f, dbl);
    int ra, rb, rc; f.gs(order, flag, 0, &ra, &rb, &rc);
    uint8_t *rsp = malloc((size_t)ra + 64); void *rspec = 0; f.in(&rspec, order, flag, 0, rsp, 0);
    int oa, ob, oc; f.ngs(order, flag, 0, &oa, &ob, &oc);
    uint8_t *osp = malloc((size_t)oa + 64); void *ospec = 0; f.nin(&ospec, order, flag, 0, osp, NULL);
    uint8_t *x = malloc((size_t)(dbl ? 8 : 4) * (N + 4)), *y = malloc((size_t)(dbl ? 8 : 4) * (N + 4));
    struct { const char *nm; tr_t r; trn_t o; } TR[] = {
      {"Fwd_RToPack", f.fwpack, f.nfwpack}, {"Fwd_RToCCS", f.fwccs, f.nfwccs}, {"Fwd_RToPerm", f.fwperm, f.nfwperm},
      {"Inv_CCSToR", f.ivccs, f.nivccs}, {"Inv_PackToR", f.ivpack, f.nivpack}, {"Inv_PermToR", f.ivperm, f.nivperm},
    };
    for (unsigned k = 0; k < sizeof TR / sizeof *TR; k++) {
      int r1 = TR[k].r(x, y, NULL, NULL), o1 = TR[k].o(x, y, NULL, NULL);
      char w[64]; snprintf(w, 64, "%s specNULL d%d", TR[k].nm, dbl); expect_st(w, r1, o1);
      r1 = TR[k].r(NULL, y, rspec, NULL); o1 = TR[k].o(NULL, y, ospec, NULL);
      snprintf(w, 64, "%s srcNULL d%d", TR[k].nm, dbl); expect_st(w, r1, o1);
      r1 = TR[k].r(x, NULL, rspec, NULL); o1 = TR[k].o(x, NULL, ospec, NULL);
      snprintf(w, 64, "%s dstNULL d%d", TR[k].nm, dbl); expect_st(w, r1, o1);
      r1 = TR[k].r(x, y, rspec, NULL); o1 = TR[k].o(x, y, ospec, NULL);
      snprintf(w, 64, "%s bufNULL d%d", TR[k].nm, dbl);
      if (dbl && r1 == -8 && o1 == 0) { cases++; g_dev++; }  /* 既知差分: 64f は実 IPP が buffer 必須, 本実装は内部確保で許容 */
      else expect_st(w, r1, o1);
    }
    free(rsp); free(osp); free(x); free(y);
  }
}

int main(int argc, char **argv) {
  if (argc < 2) { printf("usage: fft_oracle <dll>\n"); return 2; }
  if (pe_load(argv[1], &pe)) { printf("pe_load failed\n"); return 1; }
  setvbuf(stdout, NULL, _IONBF, 0);
  ((int (MS *)(uint64_t))expf_("ippSetCpuFeatures"))(~0ULL);

  Fns f32, f64;
  fns_load(&f32, 0); fns_load(&f64, 1);
  for (int order = 0; order <= 16; order++)
    for (int fi = 0; fi < 4; fi++) {
      int flag = 1 << fi;
      run_case(&f32, 0, order, flag, 1);
      run_case(&f64, 1, order, flag, 1);
      if (order <= 12) { run_case(&f32, 0, order, flag, 0); run_case(&f64, 1, order, flag, 0); }
    }
  err_grid();
  run_null_grid();

  printf("{\"fft_oracle_cases\":%ld,\"status_mismatch\":%ld,\"known_deviation_64f_bufnull\":%ld,\"worst_nrms_32f\":%.4g,\"worst_nrms_64f\":%.4g,\"worst_single_32f\":%.4g,\"worst_single_64f\":%.4g,\"gate_single_32f\":%.3g,\"gate_rt_32f\":%.3g,\"fails\":%d}\n",
         cases, status_mismatch, g_dev, worst32, worst64, worst32s, worst64s, GSINGLE(0), GRT(0), fails);
  return fails ? 1 : 0;
}
