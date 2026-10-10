/* IPP 差分テスト・ハーネス: 実 Intel IPP (win64 dsp_ippv2_x64.dll を最小 PE ローダでネイティブ実行) vs ipp_min.c。
   modes:
     cmp  <dll> <isaMask>            ref(実IPP) vs ours(ipp_min.c をネイティブ build) の統計 → stdout (json 行)
     isa  <dll> <maskA> <maskB>      実IPP の ISA 経路違い同士の差 (A11 等が経路依存かの確認)
     gen  <dll> <isaMask> <outdir>   wasm 比較用 golden (manifest.json + blob.bin) を生成
     err  <dll>                      エラー経路 (NULL/len) ステータスの格子比較 */
#define _GNU_SOURCE
#include "pe_load.h"
#include "../src/ipp_min.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

enum { A, B, C, D, E_, G, H, I, J, A8, B8 };
typedef struct { const char *name; int kind; int inclass; void *ours; } Fn;
#define F(n, k, c) { #n, k, c, (void *)n }
/* inclass: 0 audio, 1 wide, 2 positive wide, 3 exp range, 4 convert range */
static const Fn FN[] = {
  F(ippsMove_8u, A8, 0), F(ippsMove_32f, A, 0), F(ippsZero_8u, B8, 0), F(ippsZero_32f, B, 0), F(ippsAdd_32f_I, A, 0), F(ippsMulC_32f_I, D, 0),
  F(ippsCopy_32f, A, 0), F(ippsMul_32f_I, A, 0), F(ippsAddC_32f_I, D, 0), F(ippsSubCRev_32f_I, D, 0), F(ippsSet_32f, D, 0), F(ippsSet_32s, J, 0),
  F(ippsAddC_32f, C, 0), F(ippsMulC_32f, C, 0), F(ippsSubCRev_32f, C, 0), F(ippsMul_32f, E_, 0), F(ippsSqr_32f, A, 0), F(ippsSqr_32f_I, B, 0),
  F(ippsSqrt_32f_A11, A, 2), F(ippsExp_32f_A11, A, 3), F(ippsThreshold_GT_32f_I, G, 0), F(ippsThreshold_LT_32f_I, G, 0), F(ippsVectorSlope_32f, H, 0),
  F(ippsConvert_32f32s_Sfs, I, 4),
};
#define NFN (int)(sizeof FN / sizeof *FN)
static const int LENS[] = {1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33, 63, 64, 65, 127, 128, 129, 255, 256, 1000, 4097};
static const int OFFS[] = {0, 1, 3};

static uint64_t rs = 0x9E3779B97F4A7C15ULL;
static uint64_t rnd64(void) { rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27; return rs * 0x2545F4914F6CDD1DULL; }
static double urand(void) { return (rnd64() >> 11) * (1.0 / 9007199254740992.0); }
static float f_bits(uint32_t b) { float f; memcpy(&f, &b, 4); return f; }
static float gen_in(int cls, int special) {
  if (special) {
    switch (rnd64() % 12) { case 0: return 0.f; case 1: return -0.f; case 2: return f_bits(0x00000001); case 3: return f_bits(0x80000123); case 4: return INFINITY; case 5: return -INFINITY;
      case 6: return f_bits(0x7FC00000); case 7: return f_bits(0xFFC00001); case 8: return 3.4028234e38f; case 9: return -1.17549435e-38f; case 10: return 1.f; default: return -1.f; }
  }
  double u = urand();
  switch (cls) {
    case 0: return (float)(u * 2 - 1);
    case 1: { double m = pow(10.0, urand() * 60 - 30); return (float)((urand() < .5 ? -m : m)); }
    case 2: return (float)pow(10.0, urand() * 76 - 38);
    case 3: return (float)(u * 190 - 100);
    default: return (float)((u * 2 - 1) * (urand() < .1 ? 4e9 : 3000.0));
  }
}
static float SV[] = {0.f, 1.f, -1.f, 0.5f, 1.2345678f, -3.75e-3f, 1e30f, 1e-40f, -0.f, 65536.f, 0.3f, -2.5f, 0, 0, 0, 0};
#define NSV (int)(sizeof SV / sizeof *SV)
static int g_spec;

typedef struct { float *a, *b, *d; int32_t *di; int n; float v, v2; int ival, rnd, sfs; } Args;
#define BODY(CC, f) \
  switch (k) { \
    case A: case A8: return ((int (CC *)(const void *, void *, int))f)(x->a, x->d, x->n); \
    case B: case B8: return ((int (CC *)(void *, int))f)(x->d, x->n); \
    case C: return ((int (CC *)(const float *, float, float *, int))f)(x->a, x->v, x->d, x->n); \
    case D: return ((int (CC *)(float, float *, int))f)(x->v, x->d, x->n); \
    case E_: return ((int (CC *)(const float *, const float *, float *, int))f)(x->a, x->b, x->d, x->n); \
    case G: return ((int (CC *)(float *, int, float))f)(x->d, x->n, x->v); \
    case H: return ((int (CC *)(float *, int, float, float))f)(x->d, x->n, x->v, x->v2); \
    case I: return ((int (CC *)(const float *, int32_t *, int, int, int))f)(x->a, x->di, x->n, x->rnd, x->sfs); \
    case J: return ((int (CC *)(int, int32_t *, int))f)(x->ival, x->di, x->n); \
  } return -999;
static int call_ms(int k, void *f, Args *x) { BODY(MS, f) }
static int call_sv(int k, void *f, Args *x) { BODY(, f) }

static PE g_pe; static void *g_set; static int *g_idx;
static void setisa(uint64_t m) { ((int (MS *)(uint64_t))g_set)(m); }

typedef struct { long cases, elems, exact, nan_diff, diff, st_mis, case_diff; double max_ulp, max_rel; unsigned first_bits[2]; int first_case; } Stat;
static int64_t ordered(uint32_t b) { return (b & 0x80000000u) ? -(int64_t)(b & 0x7fffffffu) : (int64_t)b; }
static void cmpbuf(Stat *s, const uint32_t *r, const uint32_t *o, int n, int isf, int caseno) {
  int bad = 0;
  for (int i = 0; i < n; i++) {
    s->elems++;
    if (r[i] == o[i]) { s->exact++; continue; }
    float fr = f_bits(r[i]), fo = f_bits(o[i]);
    if (isf && fr != fr && fo != fo) { s->nan_diff++; continue; }
    s->diff++; bad = 1;
    if (isf && fr == fr && fo == fo && !isinf(fr) && !isinf(fo)) {
      double u = fabs((double)(ordered(r[i]) - ordered(o[i]))); if (u > s->max_ulp) s->max_ulp = u;
      double rel = fabs((double)fr - (double)fo) / (fabs((double)fr) + 1e-45); if (rel > s->max_rel) s->max_rel = rel;
    } else if (isf) { s->max_ulp = INFINITY; }
    if (!s->first_bits[0] && !s->first_bits[1]) { s->first_bits[0] = r[i]; s->first_bits[1] = o[i]; s->first_case = caseno; }
  }
  s->case_diff += bad;
}

typedef struct { int fi; Args a; int cap; } Case;
static void fill_case(const Fn *fn, int li, int oi, int ci, Args *x, float *pool, int cap) {
  int n = LENS[li], off = OFFS[oi];
  x->n = n; x->v = SV[(ci * 5 + li) % NSV]; x->v2 = SV[(ci * 3 + li + 1) % NSV]; x->ival = (int)(rnd64()); x->rnd = (ci + li) % 3; x->sfs = ((int)((ci * 7 + li) % 9)) - 4;
  if (fn->kind == G) { static const float L[] = {0.f, 0.5f, -0.25f, 1e-3f, INFINITY, -0.f, NAN}; x->v = L[(ci + li) % 7]; }
  if (fn->kind == A8 || fn->kind == B8) x->n = n * 4 - (ci % 4);
  float *p = pool; /* 4 buffers of cap floats */
  x->a = p + off; x->b = p + cap + off; x->d = p + 2 * cap + off; x->di = (int32_t *)x->d;
  int cls = fn->inclass; int sp = (ci % 3 == 2) || g_spec;
  double pr = g_spec ? 1.0 : .3; for (int i = 0; i < cap; i++) { p[i] = gen_in(cls, sp && urand() < pr); p[cap + i] = gen_in(cls, sp && urand() < pr); p[2 * cap + i] = gen_in(0, g_spec); }
  if (fn->kind == E_) { /* b を第二入力 */ }
}

static int isf_of(int kind) { return kind != I && kind != J && kind != A8 && kind != B8; }

int main(int argc, char **argv) {
  if (argc < 3) { fprintf(stderr, "usage\n"); return 2; }
  const char *mode = argv[1]; g_spec = getenv("SPEC") != NULL;
  SV[12] = INFINITY; SV[13] = -INFINITY; SV[14] = f_bits(0x7FC00000); SV[15] = f_bits(0xFFC00001);
  if (pe_load(argv[2], &g_pe)) return 1;
  g_set = pe_export(&g_pe, "ippSetCpuFeatures");
  g_idx = (int *)(g_pe.base + 0x2541000);
  int cap = 4097 + 16;
  if (!strcmp(mode, "err")) {
    setisa(~0ULL);
    float s[8] = {1, 2, 3, 4, 5, 6, 7, 8}, d[8] = {0};
    int mism = 0, tot = 0;
    for (int fi = 0; fi < NFN; fi++) {
      const Fn *fn = &FN[fi];
      for (int pa = 0; pa < 2; pa++) for (int pb = 0; pb < 2; pb++) for (int ln = -1; ln < 2; ln++) {
        Args x = {0}; x.a = pa ? NULL : s; x.b = s; x.d = pb ? NULL : d; x.di = (int32_t *)(pb ? NULL : d); x.n = ln; x.v = 1.f; x.v2 = 1.f; x.ival = 1; x.rnd = 1; x.sfs = 0;
        if (fn->kind == B || fn->kind == B8 || fn->kind == D || fn->kind == G || fn->kind == H || fn->kind == J) { if (pa) continue; }
        Args y = x; float tmp[8]; (void)tmp;
        void *rf = pe_export(&g_pe, fn->name);
        int r = call_ms(fn->kind, rf, &x), o = call_sv(fn->kind, fn->ours, &y); tot++;
        if (r != o) { mism++; printf("{\"fn\":\"%s\",\"srcNull\":%d,\"dstNull\":%d,\"len\":%d,\"ref\":%d,\"ours\":%d}\n", fn->name, pa, pb, ln, r, o); }
      }
    }
    printf("{\"err_grid_total\":%d,\"err_grid_mismatch\":%d}\n", tot, mism);
    return 0;
  }
  uint64_t m1 = strtoull(argv[3], 0, 0), m2 = (!strcmp(mode, "isa")) ? strtoull(argv[4], 0, 0) : 0;
  FILE *man = NULL, *blob = NULL; long boff = 0;
  if (!strcmp(mode, "gen")) {
    char p[512]; snprintf(p, sizeof p, "%s/manifest.json", argv[4]); man = fopen(p, "w");
    snprintf(p, sizeof p, "%s/blob.bin", argv[4]); blob = fopen(p, "wb"); fprintf(man, "{\"isa\":\"%s\",\"cases\":[\n", argv[3]);
  }
  setisa(m1); fprintf(stderr, "dispatch idx for mask %s = %d\n", argv[3], *g_idx);
  float *pool = aligned_alloc(64, sizeof(float) * cap * 3 + 256), *poolr = aligned_alloc(64, sizeof(float) * cap * 3 + 256), *poolo = aligned_alloc(64, sizeof(float) * cap * 3 + 256);
  int firstcase = 1;
  printf("[\n");
  for (int fi = 0; fi < NFN; fi++) {
    const Fn *fn = &FN[fi]; Stat st = {0}; void *rf = pe_export(&g_pe, fn->name);
    if (!rf) { fprintf(stderr, "no export %s\n", fn->name); return 3; }
    int ci = 0;
    for (int li = 0; li < (int)(sizeof LENS / sizeof *LENS); li++) for (int oi = 0; oi < 3; oi++) for (int rep = 0; rep < 3; rep++, ci++) {
      if (rep && fn->kind != G && fn->kind != I && fn->kind != H && fn->inclass == 0 && 0) continue;
      Args x; fill_case(fn, li, oi, ci + rep, &x, pool, cap);
      memcpy(poolr, pool, sizeof(float) * cap * 3); memcpy(poolo, pool, sizeof(float) * cap * 3);
      Args xr = x, xo = x; long d0 = (char *)x.a - (char *)pool; (void)d0;
      xr.a = poolr + (x.a - pool); xr.b = poolr + (x.b - pool); xr.d = poolr + (x.d - pool); xr.di = (int32_t *)xr.d;
      xo.a = poolo + (x.a - pool); xo.b = poolo + (x.b - pool); xo.d = poolo + (x.d - pool); xo.di = (int32_t *)xo.d;
      setisa(m1); int sr = call_ms(fn->kind, rf, &xr), so;
      if (!strcmp(mode, "isa")) { setisa(m2); so = call_ms(fn->kind, rf, &xo); } else so = call_sv(fn->kind, fn->ours, &xo);
      st.cases++; if (sr != so) st.st_mis++;
      cmpbuf(&st, (uint32_t *)poolr, (uint32_t *)poolo, cap * 3, isf_of(fn->kind), ci);
      static int shown; const char *dt = getenv("DETAIL");
      if (dt && !strcmp(dt, fn->name)) for (int i = 0; i < cap * 3 && shown < 12; i++) if (((uint32_t *)poolr)[i] != ((uint32_t *)poolo)[i]) {
        float fr = f_bits(((uint32_t *)poolr)[i]), fo = f_bits(((uint32_t *)poolo)[i]); if (fr != fr && fo != fo) continue;
        long j = i - 2L * cap; long ai = (x.a - pool) + (j - (x.d - pool - 2L * cap));
        fprintf(stderr, "  [%s] case n=%d off=%ld i=%d v=%g(%08x) v2=%g rnd=%d sfs=%d  in_a=%08x in_d=%08x ref=%08x ours=%08x (ref %g ours %g) st ref/ours %d/%d\n", fn->name, x.n, (long)(x.a - pool), i,
          x.v, *(uint32_t *)&x.v, x.v2, x.rnd, x.sfs, (ai >= 0 && ai < 3L * cap) ? ((uint32_t *)pool)[ai] : 0, ((uint32_t *)pool)[i], ((uint32_t *)poolr)[i], ((uint32_t *)poolo)[i], fr, fo, sr, so);
        shown++;
      }
      if (man) {
        /* golden: 使用範囲 u = n(+8 guard) のみ a|b|d_in|d_ref_out を blob に格納 */
        int u = ((fn->kind == A8 || fn->kind == B8) ? (x.n + 3) / 4 : x.n) + 8; long ao = x.a - pool, bo = x.b - pool, dof = x.d - pool - 2L * cap;
        (void)ao; (void)bo; (void)dof;
        fprintf(man, "%s{\"fn\":\"%s\",\"kind\":%d,\"n\":%d,\"u\":%d,\"v\":%u,\"v2\":%u,\"ival\":%d,\"rnd\":%d,\"sfs\":%d,\"st\":%d,\"blob\":%ld}\n",
          firstcase ? "" : ",", fn->name, fn->kind, x.n, u, *(uint32_t *)&x.v, *(uint32_t *)&x.v2, x.ival, x.rnd, x.sfs, sr, boff);
        firstcase = 0;
        fwrite(x.a, 4, u, blob); fwrite(x.b, 4, u, blob); fwrite(x.d, 4, u, blob); fwrite(xr.d, 4, u, blob); boff += 16L * u;
      }
    }
    char ub[32], rb[32]; if (isinf(st.max_ulp)) strcpy(ub, "null"); else snprintf(ub, 32, "%.1f", st.max_ulp); snprintf(rb, 32, "%.3g", st.max_rel);
    printf("%s{\"fn\":\"%s\",\"cases\":%ld,\"elems\":%ld,\"bit_exact\":%ld,\"nan_payload_diff\":%ld,\"differ\":%ld,\"cases_differ\":%ld,\"status_mismatch\":%ld,\"max_ulp\":%s,\"max_rel\":%s,\"first_ref_bits\":\"%08x\",\"first_ours_bits\":\"%08x\"}\n",
      fi ? "," : "", fn->name, st.cases, st.elems, st.exact, st.nan_diff, st.diff, st.case_diff, st.st_mis, ub, rb, st.first_bits[0], st.first_bits[1]);
  }
  printf("]\n");
  if (man) { fprintf(man, "]}\n"); fclose(man); fclose(blob); }
  return 0;
}
