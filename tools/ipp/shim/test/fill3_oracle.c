/* CAB-262 (IPP-7) オラクル検証: 実 IPP DLL (win64 dsp_ippv2_x64.dll を pe_load でネイティブ実行)
   vs 自前実装 (shim/impl/ipp_sig_fill3.c)。
   各ケース: 入力を一度だけ生成 → real 用/ours 用バッファに複写 → 両者実行 →
   ステータス + 出力全語を比較。--dump <file> で ours の結果ハッシュを記録 (wasm 突合用)。
   build: gcc -O1 -g -I ../../src -o fill3_oracle fill3_oracle.c ../../ref/pe_load.c \
            ../../shim/impl/ipp_sig_fill3.c -lm
   usage: ./fill3_oracle [dll] [--dump <file>] */
#define _GNU_SOURCE
#include "../../ref/pe_load.h"
#include "fl_dll_path.h"
#include "../../src/ipp_min.h"
#include "../../shim/gen/ipp_proto.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static PE pe;
static int g_dump = 0;
static FILE *g_dumpf = NULL;
static long g_rec = 0;
static char g_ctx[64];
static long g_cases, g_st, g_case, g_byte, g_fns;

static int MS stub0(void) { return 0; }
static void *ex(const char *n) {
#ifdef WASM_REPLAY
  (void)n; return (void *)stub0;
#else
  void *p = pe_export(&pe, n);
  if (!p) { fprintf(stderr, "no export %s\n", n); exit(1); }
  return p;
#endif
}
static uint64_t fnv(const void *p, size_t n, uint64_t h) {
  const unsigned char *b = p;
  for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 0x100000001b3ULL; }
  return h;
}
static long g_wasmrec = 0, g_wasmbad = 0;
static void record(IppStatus st, const void *buf, size_t n) {
  uint64_t h = fnv(&st, sizeof st, 0xcbf29ce484222325ULL);
  h = fnv(buf, n, h);
#ifdef WASM_REPLAY
  if (g_dumpf) {
    uint64_t e;
    if (fread(&e, 8, 1, g_dumpf) != 1) { fprintf(stderr, "dump EOF\n"); exit(4); }
    g_wasmrec++;
    if (e != h) { g_wasmbad++; printf("  WASM MISMATCH rec=%ld ctx=%s hash=%016llx want=%016llx\n", g_wasmrec, g_ctx, (unsigned long long)h, (unsigned long long)e); }
  }
#else
  if (g_dumpf) { fwrite(&h, 8, 1, g_dumpf); g_rec++; }
#endif
}
static uint64_t rs = 0xCAB262CAB262ULL;
static uint64_t rnd64(void) { rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27; return rs * 0x2545F4914F6CDD1DULL; }
static double urand(void) { return (rnd64() >> 11) * (1.0 / 9007199254740992.0); }
static float f_rand(void) { return (float)(urand() * 2.0 - 1.0); }

#define N 8192
static uint8_t s8[N], d8r[N], d8o[N];
static int16_t s16[N], d16r[N], d16o[N];
static int32_t s32s[N], d32sr[N], d32so[N];
static int64_t s64s[N], d64sr[N], d64so[N];
static float s32f[N], d32fr[N], d32fo[N], t32f[N];
static double s64f[N], d64fr[N], d64fo[N];
typedef Ipp32fc C2;
static C2 sc[N], dcr[N], dco[N];

static void gen8u(void)  { for (int i = 0; i < N; i++) s8[i] = (uint8_t)rnd64(); }
static void gen16s(void) { for (int i = 0; i < N; i++) s16[i] = (int16_t)rnd64(); }
static void gen32s(void) { for (int i = 0; i < N; i++) s32s[i] = (int32_t)rnd64(); }
static void gen64s(void) { for (int i = 0; i < N; i++) s64s[i] = (int64_t)rnd64(); }
static void gen32f(int sp) {
  for (int i = 0; i < N; i++) {
    s32f[i] = f_rand() * 1000.0f;
    if (sp) switch (rnd64() % 12) {
      case 0: s32f[i] = 0.0f; break;  case 1: s32f[i] = -0.0f; break;
      case 2: s32f[i] = 0.5f; break;  case 3: s32f[i] = -0.5f; break;
      case 4: s32f[i] = 1.5f; break;  case 5: s32f[i] = -1.5f; break;
      case 6: s32f[i] = 2.5f; break;  case 7: s32f[i] = -2.5f; break;
      case 8: s32f[i] = 3.4028234e38f; break; case 9: s32f[i] = 1e-40f; break;
      case 10: s32f[i] = 7.5f; break; default: s32f[i] = -7.5f; break;
    }
  }
}
static void gen64f(void) { for (int i = 0; i < N; i++) s64f[i] = (urand() * 2.0 - 1.0) * 1000.0; }
static void gen32fc(void) {
  for (int i = 0; i < N; i++) { sc[i].re = f_rand() * 50.0f; sc[i].im = f_rand() * 50.0f; }
}

static const int L[] = {1, 2, 3, 7, 16, 17, 33, 1000, 4097};
#define NL (int)(sizeof L / sizeof *L)
/* reorder は n*nch がバッファ (N=8192) を超えないよう n を制限する */
static const int LR[] = {1, 2, 3, 7, 16, 17, 33, 200, 680};
#define NLR (int)(sizeof LR / sizeof *LR)

/* ======== (src, dst, len) 家族 ======== */
static void fam2(const char *nm, int kind) {
  static const char *tag = "fam2";
  long bd_tot = 0, stmis = 0, casediff = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    IppStatus sr_ = 0, so_ = 0;
    size_t sz; const void *R; const void *O;
    if (kind == 0) { /* 32f -> 32f */
      gen32f(1); memcpy(d32fr, s32f, sizeof(float) * (size_t)n); memcpy(d32fo, s32f, sizeof(float) * (size_t)n);
      sr_ = ((IppStatus (MS *)(const Ipp32f *, Ipp32f *, int))ex(nm))(s32f, d32fr, n);
      if (!strcmp(nm, "ippsRound_32f")) so_ = ippsRound_32f(s32f, d32fo, n);
      else if (!strcmp(nm, "ippsAbs_32f")) so_ = ippsAbs_32f(s32f, d32fo, n);
      else { printf("  ??? %s kind0\n", nm); return; }
      sz = 4; R = d32fr; O = d32fo;
    } else if (kind == 1) { /* 16s -> 32f (Convert_16s32f) */
      gen16s(); memcpy(d32fr, s32f, 0); memcpy(d32fo, s32f, 0);
      for (int i = 0; i < n; i++) { d32fr[i] = 0.f; d32fo[i] = 0.f; }
      sr_ = ((IppStatus (MS *)(const Ipp16s *, Ipp32f *, int))ex(nm))(s16, d32fr, n);
      so_ = ippsConvert_16s32f(s16, d32fo, n);
      sz = 4; R = d32fr; O = d32fo;
    } else if (kind == 2) { /* 32fc -> 32f (PowerSpectr) */
      gen32fc(); for (int i = 0; i < n; i++) { d32fr[i] = 0.f; d32fo[i] = 0.f; }
      sr_ = ((IppStatus (MS *)(const Ipp32fc *, Ipp32f *, int))ex(nm))(sc, d32fr, n);
      so_ = ippsPowerSpectr_32fc(sc, d32fo, n);
      sz = 4; R = d32fr; O = d32fo;
    } else { printf("  ??? kind\n"); return; }
    long bd = 0;
    for (int i = 0; i < n; i++) if (memcmp((const char *)R + (size_t)i * sz, (const char *)O + (size_t)i * sz, sz)) bd++;
    bd_tot += bd; if (bd) casediff++; if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
    if (bd && bd_tot <= 6) printf("  DIFF %-24s n=%d byte_diff=%ld/%d\n", nm, n, bd, n);
    snprintf(g_ctx, sizeof g_ctx, "%s n=%d", nm, n);
    record(so_, O, sz * (size_t)n);
  }
  printf("  %-26s cases=%ld st_mis=%ld case_diff=%ld\n", nm, (long)NL, stmis, casediff);
  g_cases += NL; g_st += stmis; g_case += casediff; g_byte += bd_tot; g_fns++;
  (void)tag;
}

/* ======== in-place (dst, len) 家族 ======== */
static void famI(const char *nm, int kind) {
  long bd_tot = 0, stmis = 0, casediff = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    IppStatus sr_ = 0, so_ = 0;
    size_t sz; const void *R; const void *O;
    if (kind == 0) { /* 32s flip */
      gen32s(); memcpy(d32sr, s32s, sizeof(int32_t) * (size_t)n); memcpy(d32so, s32s, sizeof(int32_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp32s *, int))ex(nm))(d32sr, n);
      if (!strcmp(nm, "ippsFlip_32s_I")) so_ = 0 /* stub: not implemented */;
      else { printf("  ??? %s kindI0\n", nm); return; }
      sz = 4; R = d32sr; O = d32so;
    } else if (kind == 1) { /* 32f flip */
      gen32f(0); memcpy(d32fr, s32f, sizeof(float) * (size_t)n); memcpy(d32fo, s32f, sizeof(float) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp32f *, int))ex(nm))(d32fr, n);
      so_ = ippsFlip_32f_I(d32fo, n);
      sz = 4; R = d32fr; O = d32fo;
    } else if (kind == 2) { /* 16u flip */
      gen16s(); memcpy(d16r, s16, sizeof(int16_t) * (size_t)n); memcpy(d16o, s16, sizeof(int16_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp16u *, int))ex(nm))(d16r, n);
      so_ = ippsFlip_16u_I(d16o, n);
      sz = 2; R = d16r; O = d16o;
    } else if (kind == 3) { /* 32u swapbytes */
      gen32s(); memcpy(d32sr, s32s, sizeof(int32_t) * (size_t)n); memcpy(d32so, s32s, sizeof(int32_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp32u *, int))ex(nm))(d32sr, n);
      so_ = ippsSwapBytes_32u_I(d32so, n);
      sz = 4; R = d32sr; O = d32so;
    } else if (kind == 4) { /* 16u swapbytes */
      gen16s(); memcpy(d16r, s16, sizeof(int16_t) * (size_t)n); memcpy(d16o, s16, sizeof(int16_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp16u *, int))ex(nm))(d16r, n);
      so_ = ippsSwapBytes_16u_I(d16o, n);
      sz = 2; R = d16r; O = d16o;
    } else if (kind == 5) { /* 64f threshold LT */
      gen64f(); memcpy(d64fr, s64f, sizeof(double) * (size_t)n); memcpy(d64fo, s64f, sizeof(double) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp64f *, int, Ipp64f))ex(nm))(d64fr, n, 0.0);
      so_ = ippsThreshold_LT_64f_I(d64fo, n, 0.0);
      sz = 8; R = d64fr; O = d64fo;
    } else if (kind == 6) { /* 32s threshold LT */
      gen32s(); memcpy(d32sr, s32s, sizeof(int32_t) * (size_t)n); memcpy(d32so, s32s, sizeof(int32_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp32s *, int, Ipp32s))ex(nm))(d32sr, n, 0);
      so_ = ippsThreshold_LT_32s_I(d32so, n, 0);
      sz = 4; R = d32sr; O = d32so;
    } else if (kind == 7) { /* 32f threshold LTValGTVal */
      gen32f(0); memcpy(d32fr, s32f, sizeof(float) * (size_t)n); memcpy(d32fo, s32f, sizeof(float) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp32f *, int, Ipp32f, Ipp32f, Ipp32f, Ipp32f))ex(nm))(d32fr, n, -10.f, -99.f, 10.f, 99.f);
      so_ = ippsThreshold_LTValGTVal_32f_I(d32fo, n, -10.f, -99.f, 10.f, 99.f);
      sz = 4; R = d32fr; O = d32fo;
    } else { printf("  ??? kindI\n"); return; }
    long bd = 0;
    for (int i = 0; i < n; i++) if (memcmp((const char *)R + (size_t)i * sz, (const char *)O + (size_t)i * sz, sz)) bd++;
    bd_tot += bd; if (bd) casediff++;
    if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
    if (bd && bd_tot <= 6) printf("  DIFF %-30s n=%d byte_diff=%ld/%d\n", nm, n, bd, n);
    snprintf(g_ctx, sizeof g_ctx, "%s n=%d", nm, n);
    record(so_, O, sz * (size_t)n);
  }
  printf("  %-30s cases=%ld st_mis=%ld case_diff=%ld\n", nm, (long)NL, stmis, casediff);
  g_cases += NL; g_st += stmis; g_case += casediff; g_byte += bd_tot; g_fns++;
}

/* ======== 単純コピー/充填 ======== */
static void chk_copy(const char *nm, int kind) {
  long stmis = 0, casediff = 0, bd_tot = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    IppStatus sr_ = 0, so_ = 0;
    if (kind == 0) { /* Copy_8u */
      gen8u(); memcpy(d8r, s8, (size_t)n); memcpy(d8o, s8, (size_t)n);
      sr_ = ((IppStatus (MS *)(const Ipp8u *, Ipp8u *, int))ex(nm))(s8, d8r, n);
      so_ = ippsCopy_8u(s8, d8o, n);
    } else if (kind == 1) { /* Zero_32s */
      gen32s(); memcpy(d32sr, s32s, sizeof(int32_t) * (size_t)n); memcpy(d32so, s32s, sizeof(int32_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp32s *, int))ex(nm))(d32sr, n);
      so_ = ippsZero_32s(d32so, n);
    } else if (kind == 2) { /* Zero_64s */
      gen64s(); memcpy(d64sr, s64s, sizeof(int64_t) * (size_t)n); memcpy(d64so, s64s, sizeof(int64_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(Ipp64s *, int))ex(nm))(d64sr, n);
      so_ = ippsZero_64s(d64so, n);
    } else if (kind == 3) { /* Copy_64s */
      gen64s(); memcpy(d64sr, s64s, sizeof(int64_t) * (size_t)n); memcpy(d64so, s64s, sizeof(int64_t) * (size_t)n);
      sr_ = ((IppStatus (MS *)(const Ipp64s *, Ipp64s *, int))ex(nm))(s64s, d64sr, n);
      so_ = ippsCopy_64s(s64s, d64so, n);
    }
    long bd = 0;
    const void *R = (kind == 0) ? (const void *)d8r : (kind == 3 ? (const void *)d64sr : (kind == 1 ? (const void *)d32sr : (const void *)d64sr));
    const void *O = (kind == 0) ? (const void *)d8o : (kind == 3 ? (const void *)d64so : (kind == 1 ? (const void *)d32so : (const void *)d64so));
    size_t sz = (kind == 0) ? 1 : (kind == 1 ? 4 : 8);
    for (int i = 0; i < n; i++) if (memcmp((const char *)R + (size_t)i * sz, (const char *)O + (size_t)i * sz, sz)) bd++;
    bd_tot += bd; if (bd) casediff++;
    if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
    if (bd) printf("  DIFF %s n=%d bd=%ld\n", nm, n, bd);
    snprintf(g_ctx, sizeof g_ctx, "%s n=%d", nm, n);
    record(so_, O, sz * (size_t)n);
  }
  printf("  %-26s cases=%ld st_mis=%ld case_diff=%ld\n", nm, (long)NL, stmis, casediff);
  g_cases += NL; g_st += stmis; g_case += casediff; g_byte += bd_tot; g_fns++;
}

/* ======== RealToCplx / CplxToReal ======== */
static void chk_r2c(void) {
  long stmis = 0, casediff = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    gen32f(0); for (int i = 0; i < n; i++) t32f[i] = f_rand() * 30.0f;
    memcpy(dcr, sc, sizeof(C2) * (size_t)n); memcpy(dco, sc, sizeof(C2) * (size_t)n);
    for (int i = 0; i < n; i++) { dcr[i].re = dco[i].re = 0.f; dcr[i].im = dco[i].im = 0.f; }
    IppStatus sr_ = ((IppStatus (MS *)(const Ipp32f *, const Ipp32f *, Ipp32fc *, int))ex("ippsRealToCplx_32f"))(s32f, t32f, dcr, n);
    IppStatus so_ = ippsRealToCplx_32f(s32f, t32f, dco, n);
    long bd = 0; for (int i = 0; i < n; i++) if (memcmp(&dcr[i], &dco[i], sizeof(C2))) bd++;
    if (bd) casediff++;
    if (sr_ != so_) { stmis++; printf("  ST-MIS R2C n=%d R=%d O=%d\n", n, sr_, so_); }
    if (bd) printf("  DIFF R2C n=%d bd=%ld\n", n, bd);
    record(so_, dco, sizeof(C2) * (size_t)n);
  }
  printf("  %-26s cases=%ld st_mis=%ld case_diff=%ld\n", "ippsRealToCplx_32f", (long)NL, stmis, casediff);
  g_cases += NL; g_st += stmis; g_case += casediff; g_fns++;
}
/* ======== MinMax / Min / Max ======== */
static void chk_minmax(const char *nm, int kind) {
  long stmis = 0, casediff = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    if (kind == 0) { /* 32f */
      gen32f(0);
      float mr1 = 0, mr2 = 0, mo1 = 0, mo2 = 0;
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp32f *, int, Ipp32f *, Ipp32f *))ex(nm))(s32f, n, &mr1, &mr2);
      IppStatus so_ = ippsMinMax_32f(s32f, n, &mo1, &mo2);
      if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
      if (memcmp(&mr1, &mo1, 4) || memcmp(&mr2, &mo2, 4)) { casediff++; printf("  DIFF %s n=%d R=(%g,%g) O=(%g,%g)\n", nm, n, mr1, mr2, mo1, mo2); }
      record(so_, &mo1, 4); record(so_, &mo2, 4);
    } else if (kind == 1) { /* 16s */
      gen16s();
      int16_t mr1 = 0, mr2 = 0, mo1 = 0, mo2 = 0;
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp16s *, int, Ipp16s *, Ipp16s *))ex(nm))(s16, n, &mr1, &mr2);
      IppStatus so_ = ippsMinMax_16s(s16, n, &mo1, &mo2);
      if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
      if (memcmp(&mr1, &mo1, 2) || memcmp(&mr2, &mo2, 2)) { casediff++; printf("  DIFF %s n=%d R=(%d,%d) O=(%d,%d)\n", nm, n, mr1, mr2, mo1, mo2); }
      record(so_, &mo1, 2); record(so_, &mo2, 2);
    } else if (kind == 2) { /* Min_16s */
      gen16s(); int16_t mr = 0, mo = 0;
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp16s *, int, Ipp16s *))ex("ippsMin_16s"))(s16, n, &mr);
      IppStatus so_ = ippsMin_16s(s16, n, &mo);
      if (sr_ != so_) { stmis++; printf("  ST-MIS Min_16s n=%d R=%d O=%d\n", n, sr_, so_); }
      if (memcmp(&mr, &mo, 2)) { casediff++; printf("  DIFF Min_16s n=%d R=%d O=%d\n", n, mr, mo); }
      record(so_, &mo, 2);
    } else if (kind == 3) { /* Max_16s */
      gen16s(); int16_t mr = 0, mo = 0;
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp16s *, int, Ipp16s *))ex("ippsMax_16s"))(s16, n, &mr);
      IppStatus so_ = ippsMax_16s(s16, n, &mo);
      if (sr_ != so_) { stmis++; printf("  ST-MIS Max_16s n=%d R=%d O=%d\n", n, sr_, so_); }
      if (memcmp(&mr, &mo, 2)) { casediff++; printf("  DIFF Max_16s n=%d R=%d O=%d\n", n, mr, mo); }
      record(so_, &mo, 2);
    }
  }
  printf("  %-26s cases=%ld st_mis=%ld case_diff=%ld\n", nm, (long)NL, stmis, casediff);
  g_cases += NL; g_st += stmis; g_case += casediff; g_fns++;
}

/* ======== Set_64f / AddProductC / VectorSlope ======== */
static void chk_set64f(void) {
  long stmis = 0, casediff = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    gen64f();
    for (int i = 0; i < n; i++) { d64fr[i] = 0.0; d64fo[i] = 0.0; }
    IppStatus sr_ = ((IppStatus (MS *)(Ipp64f, Ipp64f *, int))ex("ippsSet_64f"))(2.5, d64fr, n);
    IppStatus so_ = ippsSet_64f(2.5, d64fo, n);
    if (sr_ != so_) { stmis++; printf("  ST-MIS Set_64f n=%d R=%d O=%d\n", n, sr_, so_); }
    long bd = 0; for (int i = 0; i < n; i++) if (memcmp(&d64fr[i], &d64fo[i], 8)) bd++;
    if (bd) { casediff++; printf("  DIFF Set_64f n=%d bd=%ld\n", n, bd); }
    record(so_, d64fo, sizeof(double) * (size_t)n);
  }
  printf("  %-26s cases=%ld st_mis=%ld case_diff=%ld\n", "ippsSet_64f", (long)NL, stmis, casediff);
  g_cases += NL; g_st += stmis; g_case += casediff; g_fns++;
}
static void chk_addproductc(void) {
  long stmis = 0, casediff = 0, bd_tot = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    gen32f(0); for (int i = 0; i < N; i++) t32f[i] = f_rand() * 10.0f;
    memcpy(d32fr, t32f, sizeof(float) * (size_t)n); memcpy(d32fo, t32f, sizeof(float) * (size_t)n);
    IppStatus sr_ = ((IppStatus (MS *)(const Ipp32f *, float, Ipp32f *, int))ex("ippsAddProductC_32f"))(s32f, 3.0f, d32fr, n);
    IppStatus so_ = ippsAddProductC_32f(s32f, 3.0f, d32fo, n);
    if (sr_ != so_) { stmis++; printf("  ST-MIS AddProductC n=%d R=%d O=%d\n", n, sr_, so_); }
    long bd = 0; for (int i = 0; i < n; i++) if (memcmp(&d32fr[i], &d32fo[i], 4)) bd++;
    bd_tot += bd; if (bd) { casediff++; for (int i = 0; i < n; i++) if (memcmp(&d32fr[i], &d32fo[i], 4)) { printf("  APC n=%d i=%d src=%a d0=%a real=%a ours=%a\n", n, i, (double)s32f[i], (double)t32f[i], (double)d32fr[i], (double)d32fo[i]); break; } }
    record(so_, d32fo, sizeof(float) * (size_t)n);
  }
  printf("  %-26s cases=%ld st_mis=%ld case_diff=%ld byte_diff=%ld\n", "ippsAddProductC_32f", (long)NL, stmis, casediff, bd_tot);
  g_cases += NL; g_st += stmis; g_case += casediff; g_byte += bd_tot; g_fns++;
}
static void chk_slope64(void) {
  long stmis = 0, casediff = 0, bd_tot = 0;
  for (int li = 0; li < NL; li++) {
    int n = L[li];
    for (int i = 0; i < n; i++) { d64fr[i] = 0.0; d64fo[i] = 0.0; }
    IppStatus sr_ = ((IppStatus (MS *)(Ipp64f *, int, Ipp64f, Ipp64f))ex("ippsVectorSlope_64f"))(d64fr, n, 1.0, -1.0 / 3.0);
    IppStatus so_ = ippsVectorSlope_64f(d64fo, n, 1.0, -1.0 / 3.0);
    if (sr_ != so_) { stmis++; printf("  ST-MIS Slope64 n=%d R=%d O=%d\n", n, sr_, so_); }
    long bd = 0; for (int i = 0; i < n; i++) if (memcmp(&d64fr[i], &d64fo[i], 8)) bd++;
    bd_tot += bd; if (bd) { casediff++; if (casediff <= 3) printf("  DIFF Slope64 n=%d bd=%ld\n", n, bd); }
    record(so_, d64fo, sizeof(double) * (size_t)n);
  }
  printf("  %-26s cases=%ld st_mis=%ld case_diff=%ld byte_diff=%ld\n", "ippsVectorSlope_64f", (long)NL, stmis, casediff, bd_tot);
  g_cases += NL; g_st += stmis; g_case += casediff; g_byte += bd_tot; g_fns++;
}

/* ======== Interleave / Deinterleave ======== */
static float ch_a[4][N], ch_o[4][N];
static int16_t ch_a16[4][N], ch_o16[4][N];
static void chk_il(const char *nm, int kind, int nch) {
  long stmis = 0, casediff = 0;
  for (int li = 0; li < NLR; li++) {
    int n = LR[li];
    const void **srcp = (const void **)malloc(sizeof(void *) * (size_t)nch);
    void **dstp = (void **)malloc(sizeof(void *) * (size_t)nch);
    if (kind == 0) {
      for (int c = 0; c < nch; c++) for (int i = 0; i < n; i++) ch_a[c][i] = f_rand();
      for (int c = 0; c < nch; c++) srcp[c] = ch_a[c];
      for (int i = 0; i < n * nch; i++) { d32fr[i] = 0.f; d32fo[i] = 0.f; }
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp32f *const *, int, int, Ipp32f *))ex(nm))((const Ipp32f *const *)srcp, nch, n, d32fr);
      IppStatus so_ = ippsInterleave_32f((const Ipp32f *const *)srcp, nch, n, d32fo);
      long bd = 0; for (int i = 0; i < n * nch; i++) if (memcmp(&d32fr[i], &d32fo[i], 4)) bd++;
      if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
      if (bd) { casediff++; printf("  DIFF %s n=%d bd=%ld\n", nm, n, bd); }
      record(so_, d32fo, sizeof(float) * (size_t)n * (size_t)nch);
    } else {
      for (int c = 0; c < nch; c++) for (int i = 0; i < n; i++) ch_a16[c][i] = (int16_t)rnd64();
      for (int c = 0; c < nch; c++) srcp[c] = ch_a16[c];
      for (int i = 0; i < n * nch; i++) { d16r[i] = 0; d16o[i] = 0; }
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp16s *const *, int, int, Ipp16s *))ex(nm))((const Ipp16s *const *)srcp, nch, n, d16r);
      IppStatus so_ = ippsInterleave_16s((const Ipp16s *const *)srcp, nch, n, d16o);
      long bd = 0; for (int i = 0; i < n * nch; i++) if (d16r[i] != d16o[i]) bd++;
      if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
      if (bd) { casediff++; printf("  DIFF %s n=%d bd=%ld\n", nm, n, bd); }
      record(so_, d16o, sizeof(int16_t) * (size_t)n * (size_t)nch);
    }
    free((void *)srcp); free(dstp);
  }
  printf("  %-26s(nch=%d) cases=%ld st_mis=%ld case_diff=%ld\n", nm, nch, (long)NLR, stmis, casediff);
  g_cases += NLR; g_st += stmis; g_case += casediff; g_fns++;
}
static void chk_de(const char *nm, int kind, int nch) {
  long stmis = 0, casediff = 0;
  for (int li = 0; li < NLR; li++) {
    int n = LR[li];
    if (kind == 0) {
      for (int i = 0; i < n * nch; i++) d32fr[i] = f_rand();
      for (int c = 0; c < nch; c++) for (int i = 0; i < n; i++) { ch_o[c][i] = 0.f; }
      void *dstp[4]; for (int c = 0; c < nch; c++) dstp[c] = ch_o[c];
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp32f *, int, int, Ipp32f *const *))ex(nm))(d32fr, nch, n, (Ipp32f *const *)dstp);
      IppStatus so_ = ippsDeinterleave_32f(d32fr, nch, n, (Ipp32f *const *)dstp);
      long bd = 0;
      for (int c = 0; c < nch; c++) for (int i = 0; i < n; i++) if (memcmp(&ch_o[c][i], &d32fr[i * nch + c], 4)) bd++;
      if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
      if (bd) { casediff++; printf("  DIFF %s n=%d bd=%ld\n", nm, n, bd); }
    } else {
      for (int i = 0; i < n * nch; i++) d16r[i] = (int16_t)rnd64();
      for (int c = 0; c < nch; c++) for (int i = 0; i < n; i++) { ch_o16[c][i] = 0; }
      void *dstp[4]; for (int c = 0; c < nch; c++) dstp[c] = ch_o16[c];
      IppStatus sr_ = ((IppStatus (MS *)(const Ipp16s *, int, int, Ipp16s *const *))ex(nm))(d16r, nch, n, (Ipp16s *const *)dstp);
      IppStatus so_ = ippsDeinterleave_16s(d16r, nch, n, (Ipp16s *const *)dstp);
      long bd = 0;
      for (int c = 0; c < nch; c++) for (int i = 0; i < n; i++) if (ch_o16[c][i] != d16r[i * nch + c]) bd++;
      if (sr_ != so_) { stmis++; printf("  ST-MIS %s n=%d R=%d O=%d\n", nm, n, sr_, so_); }
      if (bd) { casediff++; printf("  DIFF %s n=%d bd=%ld\n", nm, n, bd); }
    }
  }
  printf("  %-26s(nch=%d) cases=%ld st_mis=%ld case_diff=%ld\n", nm, nch, (long)NLR, stmis, casediff);
  g_cases += NL; g_st += stmis; g_case += casediff; g_fns++;
}

/* ======== WinKaiser (許容差: float 出力で max abs err) ======== */
static void chk_kaiser(void) {
  long stmis = 0, casediff = 0; double worst = 0.0; long tot = 0;
  static const int LN[] = {1, 2, 3, 4, 8, 16, 17, 32, 33, 64, 100, 255, 256, 1000};
  static const float AL[] = {0.5f, 1.0f, 1.5f, 2.0f, 2.5f, 3.0f, 3.5f, 4.0f, 4.5f, 5.0f};
  for (size_t li = 0; li < sizeof LN / sizeof *LN; li++) {
    int n = LN[li];
    for (size_t ai = 0; ai < sizeof AL / sizeof *AL; ai++) {
      float a = AL[ai];
      for (int i = 0; i < n; i++) { d32fr[i] = 1.0f; d32fo[i] = 1.0f; }
      IppStatus sr_ = ((IppStatus (MS *)(Ipp32f *, int, Ipp32f))ex("ippsWinKaiser_32f_I"))(d32fr, n, a);
      IppStatus so_ = ippsWinKaiser_32f_I(d32fo, n, a);
      tot++;
      if (sr_ != so_) { stmis++; if (stmis <= 5) printf("  ST-MIS Kaiser n=%d a=%g R=%d O=%d\n", n, a, sr_, so_); continue; }
      for (int i = 0; i < n; i++) { double d = fabs((double)d32fr[i] - (double)d32fo[i]); if (d > worst) worst = d; }
    }
  }
  printf("  %-26s cases=%ld st_mis=%ld max_abs_err=%.3e\n", "ippsWinKaiser_32f_I", tot, stmis, worst);
  g_cases += tot; g_st += stmis; g_fns++;
  (void)casediff;
}

/* ======== エラー格子 (NULL × len) ======== */
static void err_grid_1(const char *nm, int kind) {
  long stmis = 0, tot = 0;
  int lens[] = {-2, -1, 0, 1, 4};
  for (int b = 0; b < 2; b++) for (int li = 0; li < 5; li++) {
    int n = lens[li];
    IppStatus sr_ = 0, so_ = 0;
    if (kind == 1) { /* Copy_8u (src, dst) */
      gen8u();
      sr_ = ((IppStatus (MS *)(const Ipp8u *, Ipp8u *, int))ex(nm))(b ? NULL : s8, b ? NULL : d8r, n);
      so_ = ippsCopy_8u(b ? NULL : s8, b ? NULL : d8o, n);
    } else if (kind == 2) { /* Zero_32s */
      gen32s();
      sr_ = ((IppStatus (MS *)(Ipp32s *, int))ex(nm))(b ? NULL : d32sr, n);
      so_ = ippsZero_32s(b ? NULL : d32so, n);
    } else if (kind == 3) { /* Zero_64s */
      gen64s();
      sr_ = ((IppStatus (MS *)(Ipp64s *, int))ex(nm))(b ? NULL : d64sr, n);
      so_ = ippsZero_64s(b ? NULL : d64so, n);
    } else if (kind == 4) { /* Copy_64s */
      gen64s();
      sr_ = ((IppStatus (MS *)(const Ipp64s *, Ipp64s *, int))ex(nm))(b ? NULL : s64s, b ? NULL : d64sr, n);
      so_ = ippsCopy_64s(b ? NULL : s64s, b ? NULL : d64so, n);
    } else if (kind == 0) { /* 32f src/dst */
      gen32f(0);
      sr_ = ((IppStatus (MS *)(const Ipp32f *, Ipp32f *, int))ex(nm))(b ? NULL : s32f, b ? NULL : d32fr, n);
      if (!strcmp(nm, "ippsRound_32f")) so_ = ippsRound_32f(b ? NULL : s32f, b ? NULL : d32fo, n);
      else if (!strcmp(nm, "ippsAbs_32f")) so_ = ippsAbs_32f(b ? NULL : s32f, b ? NULL : d32fo, n);
      else if (!strcmp(nm, "ippsConvert_16s32f")) so_ = ippsConvert_16s32f(b ? NULL : s16, b ? NULL : d32fo, n);
      else if (!strcmp(nm, "ippsPowerSpectr_32fc")) so_ = ippsPowerSpectr_32fc(b ? NULL : (Ipp32fc *)sc, b ? NULL : d32fo, n);
      else { printf("  (skip %s)\n", nm); return; }
    } else if (kind == 5) { /* Flip_32f_I */
      sr_ = ((IppStatus (MS *)(Ipp32f *, int))ex(nm))(b ? NULL : d32fr, n);
      so_ = ippsFlip_32f_I(b ? NULL : d32fo, n);
    } else if (kind == 6) { /* Flip_16u_I */
      sr_ = ((IppStatus (MS *)(Ipp16u *, int))ex(nm))(b ? NULL : d16r, n);
      so_ = ippsFlip_16u_I(b ? NULL : d16o, n);
    } else if (kind == 7) { /* SwapBytes_32u_I */
      sr_ = ((IppStatus (MS *)(Ipp32u *, int))ex(nm))(b ? NULL : d32sr, n);
      so_ = ippsSwapBytes_32u_I(b ? NULL : d32so, n);
    } else if (kind == 8) { /* SwapBytes_16u_I */
      sr_ = ((IppStatus (MS *)(Ipp16u *, int))ex(nm))(b ? NULL : d16r, n);
      so_ = ippsSwapBytes_16u_I(b ? NULL : d16o, n);
    } else if (kind == 9) { /* Set_64f */
      sr_ = ((IppStatus (MS *)(Ipp64f, Ipp64f *, int))ex(nm))(2.5, b ? NULL : d64fr, n);
      so_ = ippsSet_64f(2.5, b ? NULL : d64fo, n);
    } else if (kind == 10) { /* WinKaiser_32f_I */
      sr_ = ((IppStatus (MS *)(Ipp32f *, int, Ipp32f))ex(nm))(b ? NULL : d32fr, n, 2.0f);
      so_ = ippsWinKaiser_32f_I(b ? NULL : d32fo, n, 2.0f);
    } else if (kind == 11) { /* VectorSlope_64f */
      sr_ = ((IppStatus (MS *)(Ipp64f *, int, Ipp64f, Ipp64f))ex(nm))(b ? NULL : d64fr, n, 1.0, -1.0 / 3.0);
      so_ = ippsVectorSlope_64f(b ? NULL : d64fo, n, 1.0, -1.0 / 3.0);
    }
    tot++;
    if (sr_ != so_) { stmis++; if (stmis <= 6) printf("  ERR-MIS %-30s dstNull=%d len=%d R=%d O=%d\n", nm, b, n, sr_, so_); }
  }
  printf("  %-30s errgrid=%ld mismatch=%ld\n", nm, tot, stmis);
  g_cases += tot; g_st += stmis; g_fns++;
}
static void err_grid_thr(const char *nm, int kind) {
  long stmis = 0, tot = 0;
  int lens[] = {-1, 0, 1, 4};
  for (int b = 0; b < 2; b++) for (int li = 0; li < 4; li++) {
    int n = lens[li];
    IppStatus sr_ = 0, so_ = 0;
    if (kind == 0) { sr_ = ((IppStatus (MS *)(Ipp64f *, int, Ipp64f))ex(nm))(b ? NULL : d64fr, n, 0.0);
                     so_ = ippsThreshold_LT_64f_I(b ? NULL : d64fo, n, 0.0); }
    else if (kind == 1) { sr_ = ((IppStatus (MS *)(Ipp32s *, int, Ipp32s))ex(nm))(b ? NULL : d32sr, n, 0);
                          so_ = ippsThreshold_LT_32s_I(b ? NULL : d32so, n, 0); }
    else { sr_ = ((IppStatus (MS *)(Ipp32f *, int, Ipp32f, Ipp32f, Ipp32f, Ipp32f))ex(nm))(b ? NULL : d32fr, n, -1.f, -9.f, 1.f, 9.f);
           so_ = ippsThreshold_LTValGTVal_32f_I(b ? NULL : d32fo, n, -1.f, -9.f, 1.f, 9.f); }
    tot++;
    if (sr_ != so_) { stmis++; printf("  ERR-MIS %-30s dstNull=%d len=%d R=%d O=%d\n", nm, b, n, sr_, so_); }
  }
  printf("  %-30s errgrid=%ld mismatch=%ld\n", nm, tot, stmis);
  g_cases += tot; g_st += stmis; g_fns++;
}
static void err_grid_r2c(void) {
  long stmis = 0, tot = 0;
  int lens[] = {-1, 0, 1, 4};
  for (int a = 0; a < 2; a++) for (int b = 0; b < 2; b++) for (int d = 0; d < 2; d++) for (int li = 0; li < 4; li++) {
    int n = lens[li];
    IppStatus sr_ = ((IppStatus (MS *)(const Ipp32f *, const Ipp32f *, Ipp32fc *, int))ex("ippsRealToCplx_32f"))(a ? NULL : s32f, b ? NULL : t32f, d ? NULL : dcr, n);
    IppStatus so_ = ippsRealToCplx_32f(a ? NULL : s32f, b ? NULL : t32f, d ? NULL : dco, n);
    tot++;
    if (sr_ != so_) { stmis++; if (stmis <= 6) printf("  ERR-MIS RealToCplx reNull=%d imNull=%d dstNull=%d len=%d R=%d O=%d\n", a, b, d, n, sr_, so_); }
  }
  printf("  %-26s errgrid=%ld mismatch=%ld\n", "ippsRealToCplx_32f", tot, stmis);
  g_cases += tot; g_st += stmis; g_fns++;
}
static void err_grid_mm(const char *nm, int kind) {
  long stmis = 0, tot = 0;
  int lens[] = {-1, 0, 1, 4};
  for (int a = 0; a < 2; a++) for (int b = 0; b < 2; b++) for (int li = 0; li < 4; li++) {
    int n = lens[li];
    IppStatus sr_ = 0, so_ = 0;
    if (kind == 0) {
      float r1 = 0, r2 = 0, o1 = 0, o2 = 0;
      sr_ = ((IppStatus (MS *)(const Ipp32f *, int, Ipp32f *, Ipp32f *))ex(nm))(a ? NULL : s32f, n, b ? NULL : &r1, b ? NULL : &r2);
      so_ = ippsMinMax_32f(a ? NULL : s32f, n, b ? NULL : &o1, b ? NULL : &o2);
    } else {
      int16_t r1 = 0, r2 = 0, o1 = 0, o2 = 0;
      sr_ = ((IppStatus (MS *)(const Ipp16s *, int, Ipp16s *, Ipp16s *))ex(nm))(a ? NULL : s16, n, b ? NULL : &r1, b ? NULL : &r2);
      so_ = ippsMinMax_16s(a ? NULL : s16, n, b ? NULL : &o1, b ? NULL : &o2);
    }
    tot++;
    if (sr_ != so_) { stmis++; printf("  ERR-MIS %-24s srcNull=%d outNull=%d len=%d R=%d O=%d\n", nm, a, b, n, sr_, so_); }
  }
  printf("  %-24s errgrid=%ld mismatch=%ld\n", nm, tot, stmis);
  g_cases += tot; g_st += stmis; g_fns++;
}
static void err_grid_il(const char *nm, int kind, int nch) {
  long stmis = 0, tot = 0;
  int lens[] = {-1, 0, 1, 4};
  for (int snull = 0; snull < 2; snull++) for (int li = 0; li < 4; li++) {
    int n = lens[li];
    const void *sp[4];
    IppStatus sr_ = 0, so_ = 0;
    if (kind == 0) {
      for (int c = 0; c < nch; c++) sp[c] = ch_a[c];
      for (int i = 0; i < n * nch; i++) { d32fr[i] = 0.f; d32fo[i] = 0.f; }
      sr_ = ((IppStatus (MS *)(const Ipp32f *const *, int, int, Ipp32f *))ex(nm))(snull ? NULL : (const Ipp32f *const *)sp, nch, n, d32fr);
      so_ = ippsInterleave_32f(snull ? NULL : (const Ipp32f *const *)sp, nch, n, d32fo);
    } else {
      for (int c = 0; c < nch; c++) sp[c] = ch_a16[c];
      for (int i = 0; i < n * nch; i++) { d16r[i] = 0; d16o[i] = 0; }
      sr_ = ((IppStatus (MS *)(const Ipp16s *const *, int, int, Ipp16s *))ex(nm))(snull ? NULL : (const Ipp16s *const *)sp, nch, n, d16r);
      so_ = ippsInterleave_16s(snull ? NULL : (const Ipp16s *const *)sp, nch, n, d16o);
    }
    tot++;
    if (sr_ != so_) { stmis++; if (stmis <= 6) printf("  ERR-MIS %-24s srcNull=%d len=%d R=%d O=%d\n", nm, snull, n, sr_, so_); }
  }
  printf("  %-24s errgrid=%ld mismatch=%ld\n", nm, tot, stmis);
  g_cases += tot; g_st += stmis; g_fns++;
}

int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  const char *dll = NULL;
  const char *path = NULL;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--dump") && i + 1 < argc) path = argv[++i];
    else if (!strcmp(argv[i], "--replay") && i + 1 < argc) path = argv[++i];
    else dll = argv[i];
  }
  if (!dll) dll = fl_ipp_dll_path();
#ifndef WASM_REPLAY
  if (pe_load(dll, &pe)) return 1;
  ((int (MS *)(uint64_t))ex("ippSetCpuFeatures"))(~0ULL);
#endif
  if (path) {
#ifdef WASM_REPLAY
    g_dumpf = fopen(path, "rb"); if (!g_dumpf) return 2; printf("fill3_oracle WASM replay: %s\n", path);
#else
    g_dumpf = fopen(path, "wb"); if (!g_dumpf) return 2; printf("fill3_oracle: dump -> %s\n", path);
#endif
  } else printf("fill3_oracle: loaded %s\n", dll);
  printf("== copy/zero ==\n"); chk_copy("ippsCopy_8u", 0); chk_copy("ippsZero_32s", 1);
  chk_copy("ippsZero_64s", 2); chk_copy("ippsCopy_64s", 3);
  printf("== unary ==\n"); fam2("ippsRound_32f", 0); fam2("ippsAbs_32f", 0);
  fam2("ippsConvert_16s32f", 1); fam2("ippsPowerSpectr_32fc", 2);
  printf("== in-place ==\n"); famI("ippsFlip_32f_I", 1); famI("ippsFlip_16u_I", 2);
  famI("ippsSwapBytes_32u_I", 3); famI("ippsSwapBytes_16u_I", 4);
  famI("ippsThreshold_LT_64f_I", 5); famI("ippsThreshold_LT_32s_I", 6);
  famI("ippsThreshold_LTValGTVal_32f_I", 7);
  printf("== cplx ==\n"); chk_r2c();
  printf("== minmax ==\n"); chk_minmax("ippsMinMax_32f", 0); chk_minmax("ippsMinMax_16s", 1);
  chk_minmax("ippsMin_16s", 2); chk_minmax("ippsMax_16s", 3);
  printf("== set/addproductc/slope ==\n"); chk_set64f(); chk_addproductc(); chk_slope64();
  printf("== reorder ==\n");
  chk_il("ippsInterleave_32f", 0, 1); chk_il("ippsInterleave_32f", 0, 2);
  chk_il("ippsInterleave_32f", 0, 3); chk_il("ippsInterleave_32f", 0, 4);
  chk_il("ippsInterleave_16s", 1, 1); chk_il("ippsInterleave_16s", 1, 2);
  chk_il("ippsInterleave_16s", 1, 3); chk_il("ippsInterleave_16s", 1, 4);
  chk_de("ippsDeinterleave_32f", 0, 2); chk_de("ippsDeinterleave_32f", 0, 3); chk_de("ippsDeinterleave_32f", 0, 4);
  chk_de("ippsDeinterleave_16s", 1, 2); chk_de("ippsDeinterleave_16s", 1, 3); chk_de("ippsDeinterleave_16s", 1, 4);
  printf("== kaiser ==\n"); chk_kaiser();
  printf("== error grid (NULL x len) ==\n");
  err_grid_1("ippsCopy_8u", 1); err_grid_1("ippsZero_32s", 2); err_grid_1("ippsZero_64s", 3);
  err_grid_1("ippsCopy_64s", 4); err_grid_1("ippsRound_32f", 0); err_grid_1("ippsAbs_32f", 0);
  err_grid_1("ippsConvert_16s32f", 0); err_grid_1("ippsPowerSpectr_32fc", 0);
  err_grid_1("ippsFlip_32f_I", 5); err_grid_1("ippsFlip_16u_I", 6); err_grid_1("ippsSwapBytes_32u_I", 7);
  err_grid_1("ippsSwapBytes_16u_I", 8); err_grid_1("ippsSet_64f", 9); err_grid_1("ippsWinKaiser_32f_I", 10);
  err_grid_1("ippsVectorSlope_64f", 11);
  err_grid_thr("ippsThreshold_LT_64f_I", 0); err_grid_thr("ippsThreshold_LT_32s_I", 1);
  err_grid_thr("ippsThreshold_LTValGTVal_32f_I", 2);
  err_grid_r2c(); err_grid_mm("ippsMinMax_32f", 0); err_grid_mm("ippsMinMax_16s", 1);
  err_grid_il("ippsInterleave_32f", 0, 2); err_grid_il("ippsInterleave_16s", 1, 2);
  printf("SUM {\"fns\":%ld,\"cases\":%ld,\"st_mis\":%ld,\"case_diff\":%ld,\"byte_diff\":%ld}\n", g_fns, g_cases, g_st, g_case, g_byte);
#ifdef WASM_REPLAY
  if (g_dumpf) fclose(g_dumpf);
  printf("wasm replay: records=%ld mismatch=%ld -> %s\n", g_wasmrec, g_wasmbad, g_wasmbad ? "FAIL" : "PASS");
  return g_wasmbad ? 1 : 0;
#else
  printf("dump records=%ld\n", g_rec);
  return 0;
#endif
}
