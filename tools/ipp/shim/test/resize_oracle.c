/* CAB-245 オラクル検証: 実 IPP DLL (win64 dsp_ippv2, pe_load ネイティブ実行) vs 自前実装
   (shim/impl/ipp_resize.c + ipp_sig_fill2.c)。
   real は pe_load 経由の DLL 関数 (MS x64)、ours はリンクした impl 関数。
   各ケース: 入力を一度だけ生成 → real/ours バッファに複写 → 両者実行 → status + 出力全語比較。
   build: bash test/resize_oracle_run.sh (work/resize/ にバイナリを出力)
   usage: ./resize_oracle [dll] [--dump <file>] | --replay <file> (wasm)
   出力: 系統ごとの統計 + 最終行に SUM JSON (shim_check.py が読む) */
#define _GNU_SOURCE
#include "../../ref/pe_load.h"
#include "fl_dll_path.h"
#include "../../src/ipp_min.h"
#include "../../shim/gen/ipp_proto.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

typedef struct { int x, y, w, h; } R4;
typedef struct { int w, h; } S2;

static PE pe;
static int g_wasm = 0;
static FILE *g_dumpf = NULL;
static long g_rec = 0, g_bad = 0;
static int MS stub0(void) { return 0; }
static void *ex(const char *n) {
#ifdef WASM_REPLAY
  (void)n; return (void *)stub0;
#else
  void *p = pe_export(&pe, n); if (!p) { fprintf(stderr, "no export %s\n", n); exit(1); } return p;
#endif
}

static uint64_t fnv(const void *p, size_t n, uint64_t h) {
  const unsigned char *b = p;
  for (size_t i = 0; i < n; i++) { h ^= b[i]; h *= 0x100000001b3ULL; }
  return h;
}
/* ours の結果を記録/検証: native --dump はハッシュ追記, wasm --replay は比較 */
static char g_ctx[128];
static void record(IppStatus st, const void *buf, size_t n) {
  uint64_t h = fnv(&st, sizeof st, 0xcbf29ce484222325ULL);
  h = fnv(buf, n, h);
  if (g_wasm) {
    uint64_t e; if (fread(&e, 8, 1, g_dumpf) != 1) { fprintf(stderr, "dump EOF\n"); exit(4); }
    g_rec++;
    if (e != h) { g_bad++; printf("  WASM MISMATCH rec=%ld ctx=%s hash=%016llx want=%016llx\n", g_rec, g_ctx, (unsigned long long)h, (unsigned long long)e); }
  } else if (g_dumpf) {
    fwrite(&h, 8, 1, g_dumpf); g_rec++;
  }
}

static uint64_t rs = 0xCAB245CAB245ULL;
static uint64_t rnd64(void) { rs ^= rs >> 12; rs ^= rs << 25; rs ^= rs >> 27; return rs * 0x2545F4914F6CDD1DULL; }
static int ri(int n) { return (int)(rnd64() % (uint64_t)n); }
static int pick(int k, const int *a) { return a[ri(k)]; }

#define PSZ (200 * 200)
static uint8_t b1[PSZ], b2[PSZ], b3[PSZ];
static uint8_t pbuf[1 << 22];

static void fill_img(uint8_t *b) { for (int i = 0; i < PSZ; i++) b[i] = (uint8_t)(rnd64() & 0xFF); }

typedef struct { long cases, st_mis, byte_diff, case_diff, first_case; int first_it; double first_fx; int first_st_r, first_st_o; long first_off; int first_r, first_o; } Stat;

#define BEGINF(name) { Stat st = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}; Stat *S = &st; const char *SNAME = name; (void)SNAME;
#define ENDF(ncase) \
  printf("%-30s cases=%ld st_mis=%ld case_diff=%ld byte_diff=%ld", SNAME, S->cases, S->st_mis, S->case_diff, S->byte_diff); \
  if (S->case_diff) printf("  first: case=%ld it=%d fx=%.3f stR=%d stO=%d off=%ld r=%d o=%d", S->first_case, S->first_it, S->first_fx, S->first_st_r, S->first_st_o, S->first_off, S->first_r, S->first_o); \
  printf("\n"); totals(SNAME, S, ncase); }

/* 簡易集約 */
static long g_tot_cases, g_tot_case_diff, g_tot_st_mis, g_tot_byte_diff;
static long g_mode_diff[24], g_mode_cases[24];
static long g_mode_px[24], g_mode_pxd[24], g_mode_big[24];
static void totals(const char *tag, Stat *S, long ncase) {
  (void)tag; (void)ncase;
  g_tot_cases += S->cases; g_tot_case_diff += S->case_diff; g_tot_st_mis += S->st_mis; g_tot_byte_diff += S->byte_diff;
}
static long g_px_tot = 0, g_px_diff = 0;
static long g_hist[9];
static int g_big = 0;
static void mode_stat(int it, long cases, long case_diff) { g_mode_cases[it] += cases; g_mode_diff[it] += case_diff; }

/* ---- ResizeSqrPixel 1 家族 (C1/C3/C4 を1ループで) ---- */
static void cmp_resize_one(Stat *S, int ch, int it, double fx, double fy, double sx, double sy,
                           R4 sr, R4 dr, int ss, int ds, int ci) {
  typedef int (MS *F5)(const void *, S2, int, R4, void *, int, R4, double, double, double, double, int, void *);
  const char *nm = ch == 1 ? "ippiResizeSqrPixel_8u_C1R" : ch == 3 ? "ippiResizeSqrPixel_8u_C3R" : "ippiResizeSqrPixel_8u_C4R";
  F5 real = (F5)ex(nm);
  IppStatus (*ours)(const Ipp8u *, IppiSize, int, IppiRect, Ipp8u *, int, IppiRect, double, double, double, double, int, Ipp8u *) =
    ch == 1 ? ippiResizeSqrPixel_8u_C1R : ch == 3 ? ippiResizeSqrPixel_8u_C3R : ippiResizeSqrPixel_8u_C4R;
  size_t outn = (size_t)(dr.y + dr.h) * ds + 64;
  if (outn > PSZ) outn = PSZ;
  memcpy(b2, b1, PSZ);   /* b2 = real 用 dst */
  memcpy(b3, b1, PSZ);   /* b3 = ours 用 dst */
  IppStatus sr_ = real(b1, (S2){200, 200}, ss, sr, b2, ds, dr, fx, fy, sx, sy, it, pbuf);
  IppStatus so_ = ours(b1, (IppiSize){200, 200}, ss, *(IppiRect*)&sr, b3, ds, *(IppiRect*)&dr, fx, fy, sx, sy, it, pbuf);
  S->cases++;
  long wd = 0; size_t foff = 0; int fr = 0, fo = 0;
  for (size_t i = 0; i < outn; i++) if (b2[i] != b3[i]) { if (!wd) { foff = i; fr = b2[i]; fo = b3[i]; } wd++; }
  if (sr_ != so_) {
    S->st_mis++;
    if (S->st_mis <= 6 || getenv("RSZDBG"))
      printf("  ST-MISMATCH ch=%d it=%d fx=%.4f fy=%.4f sx=%.3f sy=%.3f sr=(%d,%d,%d,%d) dr=(%d,%d,%d,%d) real=%d ours=%d\n",
             ch, it, fx, fy, sx, sy, sr.x, sr.y, sr.w, sr.h, dr.x, dr.y, dr.w, dr.h, sr_, so_);
    if (!S->case_diff) { S->first_case = ci; S->first_it = it; S->first_fx = fx; S->first_st_r = sr_; S->first_st_o = so_; S->first_off = -1; }
  }
  if (wd) {
    S->byte_diff += wd; S->case_diff++;
    if (S->case_diff == 1 && !S->st_mis) { S->first_case = ci; S->first_it = it; S->first_fx = fx; S->first_st_r = sr_; S->first_st_o = so_; S->first_off = (long)foff; S->first_r = fr; S->first_o = fo; }
  }
  mode_stat(it, 1, (wd || sr_ != so_) ? 1 : 0);
  { long px = 0; int big = 0; for (size_t i = 0; i < outn; i++) if (b2[i] != b3[i]) { px++; int d = b2[i] - b3[i]; if (d < 0) d = -d; g_hist[d < 8 ? d : 8]++; if (d > 8) { big++; if (g_big < 14 && it == 8) { g_big++; printf("  BIG8 ch=%d it=%d fx=%.4f fy=%.4f sx=%.3f sy=%.3f dr=(%d,%d,%d,%d) row=%d col=%d r=%d o=%d\n", ch, it, fx, fy, sx, sy, dr.x, dr.y, dr.w, dr.h, (int)(i / (size_t)ds) - dr.y, (int)((i % ds) / ch) - dr.x, b2[i], b3[i]); } } } g_px_tot += (long)outn; g_px_diff += px; g_mode_px[it] += (long)outn; g_mode_pxd[it] += px; g_mode_big[it] += big; }
  snprintf(g_ctx, sizeof g_ctx, "resize ch%d it%d fx%.2f", ch, it, fx);
  record(so_, b3, outn);
}

static const double FVL[] = {0.3, 0.5, 0.7, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5};
static const double SHL[] = {0.0, 0.25, 0.5, 0.75, -0.5, 1.0};
static const int ITL[] = {1, 2, 4, 5, 6, 7, 8, 16};
static const int ITL4[] = {1, 2, 4, 16};

static void fam_resize_grid(int ch) {
  BEGINF("resize")
  int ci = 0;
  for (size_t ii = 0; ii < sizeof ITL / sizeof *ITL; ii++)
    for (size_t fi = 0; fi < sizeof FVL / sizeof *FVL; fi++) {
      if (ITL[ii] == 8 && FVL[fi] > 1.0) continue;
      for (size_t si = 0; si < 4; si++) {
        R4 sr = {0, 0, 32, 32}, dr = {0, 0, 16, 16};
        fill_img(b1);
        cmp_resize_one(S, ch, ITL[ii], FVL[fi], FVL[fi], SHL[si], SHL[si], sr, dr, 200, 200, ++ci);
      }
    }
  ENDF(0)
}

static void fam_resize_fuzz(int ch, int ncase) {
  BEGINF("resize")
  static const int WLIST[] = {1, 2, 3, 5, 8, 13, 16, 17, 24, 31, 32, 33, 48, 64};
  for (int ci = 0; ci < ncase; ci++) {
    int it = pick(8, ITL);
    double fx = 0.1 + (rnd64() % 400) / 100.0;  /* 0.1..4.1 */
    double fy = 0.1 + (rnd64() % 400) / 100.0;
    if (it == 8) { if (fx > 1.0) fx = 1.0 / (1.0 + (rnd64() % 300) / 100.0); if (fy > 1.0) fy = 1.0 / (1.0 + (rnd64() % 300) / 100.0); }
    double sx = ((int)(rnd64() % 200) - 100) / 100.0;
    double sy = ((int)(rnd64() % 200) - 100) / 100.0;
    int sw = pick(14, WLIST), sh = pick(14, WLIST);
    int dw = pick(14, WLIST), dh = pick(14, WLIST);
    R4 sr = {ri(3), ri(3), sw, sh}, dr = {ri(3), ri(3), dw, dh};
    int ss = 200, ds = 200;
    if (getenv("RSZDBG")) fprintf(stderr, "fuzz ch=%d ci=%d it=%d fx=%.3f fy=%.3f sx=%.2f sy=%.2f sr=(%d,%d,%d,%d) dr=(%d,%d,%d,%d)\n", ch, ci, it, fx, fy, sx, sy, sr.x, sr.y, sr.w, sr.h, dr.x, dr.y, dr.w, dr.h);
    fill_img(b1);
    cmp_resize_one(S, ch, it, fx, fy, sx, sy, sr, dr, ss, ds, ci + 1);
  }
  ENDF(0)
}

static void fam_resize_err(void) {
  BEGINF("resize")
  int ci = 0;
  R4 sr = {0, 0, 16, 16}, dr = {0, 0, 8, 8};
  S2 s200 = {200, 200};
  fill_img(b1);
  struct { const char *nm; int kind; } tsts[] = {
    {"null_src", 0}, {"null_dst", 1}, {"null_buf", 2}, {"size0", 3}, {"roiW0", 4}, {"interp0", 5}, {"interp999", 6},
    {"fx0", 7}, {"fxneg", 8}, {"super_fx_gt1", 9}, {"dstroi_off", 10}, {"srcoi_off", 11}, {"roi_gt", 12},
  };
  for (size_t t = 0; t < sizeof tsts / sizeof *tsts; t++) {
    for (size_t ii = 0; ii < 4; ii++) {
      int it = ITL4[ii];
      const Ipp8u *psrc = b1; Ipp8u *pdst = b1; Ipp8u *pbuf_ = pbuf;
      S2 ssz = s200; R4 s = sr, d = dr; double fx = 0.5, fy = 0.5;
      switch (tsts[t].kind) {
        case 0: psrc = NULL; break;
        case 1: pdst = NULL; break;
        case 2: pbuf_ = NULL; break;
        case 3: ssz = (S2){0, 0}; break;
        case 4: s = (R4){0, 0, 0, 16}; break;
        case 5: it = 0; break;
        case 6: it = 999; break;
        case 7: fx = fy = 0.0; break;
        case 8: fx = -1.0; break;
        case 9: it = 8; fx = fy = 1.5; break;
        case 10: d = (R4){2, 3, 8, 8}; break;
        case 11: s = (R4){4, 5, 16, 16}; break;
        case 12: s = (R4){0, 0, 64, 64}; break;
      }
      typedef int (MS *F5)(const void *, S2, int, R4, void *, int, R4, double, double, double, double, int, void *);
      F5 real = (F5)ex("ippiResizeSqrPixel_8u_C1R");
      memcpy(b2, b1, PSZ);
      memcpy(b3, b1, PSZ);
      IppStatus sr_ = real(psrc, ssz, 200, s, b2, 200, d, fx, fy, 0, 0, it, pbuf_);
      IppStatus so_ = ippiResizeSqrPixel_8u_C1R(psrc, *(IppiSize*)&ssz, 200, *(IppiRect*)&s, b3, 200, *(IppiRect*)&d, fx, fy, 0, 0, it, pbuf_);
      S->cases++; ci++;
      if (sr_ != so_) {
        S->st_mis++;
        printf("  ERR-MISMATCH %-13s it=%d real=%d ours=%d\n", tsts[t].nm, it, sr_, so_);
        if (!S->case_diff) { S->first_case = ci; S->first_it = it; S->first_st_r = sr_; S->first_st_o = so_; S->first_off = -1; }
      }
      snprintf(g_ctx, sizeof g_ctx, "err %s it%d", tsts[t].nm, it);
      record(so_, b3, PSZ);
    }
  }
  ENDF(0)
}

/* ---- GetBufSize ---- */
static void fam_getbufsize(void) {
  printf("== ippiResizeGetBufSize: 実測式 vs 実 DLL (密グリッド + 拡張ランダム) ==\n");
  typedef int (MS *F6)(R4, R4, int, int, int *);
  F6 real = (F6)ex("ippiResizeGetBufSize");
  long cases = 0, mism = 0, szmis = 0;
  /* 密グリッド */
  for (int dw = 1; dw <= 96; dw++)
    for (int dh = 1; dh <= 48; dh += 1)
      for (int ch = 1; ch <= 4; ch++) {
        if (ch == 2) continue;
        for (int it = 1; it <= 16; it <<= 1) {
          int zr = -12345, zo = -12345;
          IppStatus sr_ = real((R4){0, 0, 64, 64}, (R4){0, 0, dw, dh}, ch, it, &zr);
          IppStatus so_ = ippiResizeGetBufSize((IppiRect){0, 0, 64, 64}, (IppiRect){0, 0, dw, dh}, ch, it, &zo);
          cases++;
          if (sr_ != so_ || zr != zo) {
            mism++;
            if (mism <= 8) printf("  GBS-MISMATCH dw=%d dh=%d ch=%d it=%d real=(%d,%d) ours=(%d,%d)\n", dw, dh, ch, it, sr_, zr, so_, zo);
          }
        }
      }
  /* Super: src 側グリッド */
  for (int sw = 1; sw <= 96; sw++)
    for (int sh = 1; sh <= 48; sh += 7)
      for (int ch = 1; ch <= 4; ch += 2) {
        int zr = -12345, zo = -12345;
        IppStatus sr_ = real((R4){0, 0, sw, sh}, (R4){0, 0, 32, 32}, ch, 8, &zr);
        IppStatus so_ = ippiResizeGetBufSize((IppiRect){0, 0, sw, sh}, (IppiRect){0, 0, 32, 32}, ch, 8, &zo);
        cases++;
        if (sr_ != so_ || zr != zo) {
          mism++;
          if (mism <= 8) printf("  GBS-S-MISMATCH sw=%d sh=%d ch=%d real=(%d,%d) ours=(%d,%d)\n", sw, sh, ch, sr_, zr, so_, zo);
        }
      }
  /* CAB-274: interp 5/6/7 のサイズが cubic (4) と同一かの実測検証 (size mode 5/6/7 -> 4 の裏付け) */
  for (int it = 5; it <= 7; it++)
    for (int dw = 1; dw <= 96; dw += 5)
      for (int dh = 1; dh <= 48; dh += 5)
        for (int ch = 1; ch <= 4; ch++) {
          if (ch == 2) continue;
          int zr = -12345, zo = -12345;
          IppStatus sr_ = real((R4){0, 0, 64, 64}, (R4){0, 0, dw, dh}, ch, it, &zr);
          IppStatus so_ = ippiResizeGetBufSize((IppiRect){0, 0, 64, 64}, (IppiRect){0, 0, dw, dh}, ch, it, &zo);
          cases++;
          if (sr_ != so_ || zr != zo) {
            mism++;
            if (mism <= 8) printf("  GBS5-MISMATCH dw=%d dh=%d ch=%d it=%d real=(%d,%d) ours=(%d,%d)\n", dw, dh, ch, it, sr_, zr, so_, zo);
          }
        }
  /* 拡張ランダム (dw,dh ≤ 600 — 式の外挿検証) */
  for (int k = 0; k < 4000; k++) {
    int dw = 1 + (int)(rnd64() % 600), dh = 1 + (int)(rnd64() % 600);
    int sw = 1 + (int)(rnd64() % 600), sh = 1 + (int)(rnd64() % 600);
    int ch = pick(3, (const int[]){1, 3, 4});
    int it = pick(5, ITL4 == NULL ? (const int[]){1,2,4,8,16} : (const int[]){1,2,4,8,16});
    (void)ITL4;
    int zr = -12345, zo = -12345;
    IppStatus sr_ = real((R4){0, 0, sw, sh}, (R4){0, 0, dw, dh}, ch, it, &zr);
    IppStatus so_ = ippiResizeGetBufSize((IppiRect){0, 0, sw, sh}, (IppiRect){0, 0, dw, dh}, ch, it, &zo);
    cases++;
    if (sr_ != so_ || zr != zo) {
      mism++; szmis++;
      if (szmis <= 8) printf("  GBS-X-MISMATCH dw=%d dh=%d sw=%d sh=%d ch=%d it=%d real=(%d,%d) ours=(%d,%d)\n", dw, dh, sw, sh, ch, it, sr_, zr, so_, zo);
    }
  }
  /* status 系: ch=2 / interp 不正 / NULL */
  {
    int zr = -12345, zo = -12345;
    struct { const char *nm; R4 s, d; int ch, it; int *pr, *po; } tt[] = {
      {"ch2", {0,0,32,32}, {0,0,16,16}, 2, 2, &zr, &zo},
      {"interp3", {0,0,32,32}, {0,0,16,16}, 3, 3, &zr, &zo},
      {"w0", {0,0,32,32}, {0,0,0,16}, 3, 2, &zr, &zo},
      {"null", {0,0,32,32}, {0,0,16,16}, 3, 2, NULL, NULL},
    };
    for (size_t i = 0; i < sizeof tt / sizeof *tt; i++) {
      int r1 = -12345, o1 = -12345;
      IppStatus sr_ = real(tt[i].s, tt[i].d, tt[i].ch, tt[i].it, tt[i].pr ? &r1 : NULL);
      IppStatus so_ = ippiResizeGetBufSize(*(IppiRect*)&tt[i].s, *(IppiRect*)&tt[i].d, tt[i].ch, tt[i].it, tt[i].po ? &o1 : NULL);
      cases++;
      if (sr_ != so_) { mism++; printf("  GBS-ST-MISMATCH %s real=%d ours=%d\n", tt[i].nm, sr_, so_); }
      if (tt[i].pr && r1 != o1) { mism++; printf("  GBS-SZ-MISMATCH %s real=%d ours=%d\n", tt[i].nm, r1, o1); }
    }
  }
  /* SqrPixelGetBufSize: 実 DLL は常時 -8 (書込なし) — 全数確認 */
  {
    typedef int (MS *F7)(S2, int, int, int *);
    F7 real7 = (F7)ex("ippiResizeSqrPixelGetBufSize");
    long c7 = 0, m7 = 0;
    for (int w = 1; w <= 96; w += 5)
      for (int h = 1; h <= 48; h += 5)
        for (int ch = 1; ch <= 4; ch++)
          for (int it = 1; it <= 16; it <<= 1) {
            int zr = -12345, zo = -12345;
            IppStatus sr_ = real7((S2){w, h}, ch, it, &zr);
            IppStatus so_ = ippiResizeSqrPixelGetBufSize((IppiSize){w, h}, ch, it, &zo);
            c7++;
            if (sr_ != so_ || zr != zo) { m7++; if (m7 <= 4) printf("  SGBS-MISMATCH w=%d h=%d ch=%d it=%d real=(%d,%d) ours=(%d,%d)\n", w, h, ch, it, sr_, zr, so_, zo); }
          }
    printf("ippiResizeSqrPixelGetBufSize (常時 -8 実測): cases=%ld mismatch=%ld\n", c7, m7);
    g_tot_cases += c7; g_tot_case_diff += m7;
  }
  printf("ippiResizeGetBufSize: cases=%ld mismatch=%ld\n", cases, mism);
  g_tot_cases += cases; g_tot_case_diff += mism;
}

/* ---- 信号 4 関数 ---- */
static void fam_sig(void) {
  BEGINF("sig")
  static const int LENS[] = {1, 2, 3, 7, 8, 15, 16, 17, 31, 1000, 4097};
  /* Threshold_GT_32s_I */
  for (int ci = 0; ci < 60; ci++) {
    int n = pick(11, LENS);
    static Ipp32s a1[8192], a2[8192];
    Ipp32s level = (Ipp32s)rnd64();
    for (int i = 0; i < n; i++) { a1[i] = a2[i] = (Ipp32s)rnd64(); }
    int sr_ = ((int (MS *)(Ipp32s *, int, Ipp32s))ex("ippsThreshold_GT_32s_I"))(a1, n, level);
    int so_ = ippsThreshold_GT_32s_I(a2, n, level);
    S->cases++;
    if (sr_ != so_) S->st_mis++;
    long wd = 0; for (int i = 0; i < n; i++) if (a1[i] != a2[i]) wd++;
    S->byte_diff += wd; if (wd) S->case_diff++;
    snprintf(g_ctx, sizeof g_ctx, "thr32s");
    record(so_, a2, sizeof(Ipp32s) * (size_t)n);
    if (wd && !S->first_case) { S->first_case = ci + 1; S->first_it = n; S->first_r = a1[0]; S->first_o = a2[0]; }
  }
  /* Sub_32f_I */
  for (int ci = 0; ci < 60; ci++) {
    int n = pick(11, LENS);
    static float s1[8192], d1[8192], d2[8192];
    int sp = ci % 3 == 2;
    for (int i = 0; i < n; i++) {
      float v = (float)((rnd64() >> 11) / 9007199254740992.0) * (float)(1u << ri(50)) * (ri(2) ? 1.f : -1.f);
      if (sp && ri(8) == 0) { switch (ri(6)) { case 0: v = 0.f; break; case 1: v = -0.f; break; case 2: v = INFINITY; break; case 3: v = -INFINITY; break; case 4: v = (float)0x7FC00000; break; default: v = 3.4e38f; } }
      s1[i] = v;
      float w = (float)((rnd64() >> 11) / 9007199254740992.0) * (float)(1u << ri(50)) * (ri(2) ? 1.f : -1.f);
      d1[i] = d2[i] = w;
    }
    int sr_ = ((int (MS *)(const float *, float *, int))ex("ippsSub_32f_I"))(s1, d1, n);
    int so_ = ippsSub_32f_I(s1, d2, n);
    S->cases++;
    if (sr_ != so_) S->st_mis++;
    long wd = 0;
    for (int i = 0; i < n; i++) {
      uint32_t x, y; memcpy(&x, &d1[i], 4); memcpy(&y, &d2[i], 4);
      if (x != y && !((x != x) && (y != y))) wd++;
    }
    S->byte_diff += wd; if (wd) S->case_diff++;
    snprintf(g_ctx, sizeof g_ctx, "sub32f");
    record(so_, d2, sizeof(float) * (size_t)n);
  }
  /* Copy_32s */
  for (int ci = 0; ci < 40; ci++) {
    int n = pick(11, LENS);
    static Ipp32s s1[8192], d1[8192], d2[8192];
    for (int i = 0; i < n; i++) { s1[i] = (Ipp32s)rnd64(); d1[i] = d2[i] = (Ipp32s)rnd64(); }
    int sr_ = ((int (MS *)(const Ipp32s *, Ipp32s *, int))ex("ippsCopy_32s"))(s1, d1, n);
    int so_ = ippsCopy_32s(s1, d2, n);
    S->cases++;
    if (sr_ != so_) S->st_mis++;
    long wd = 0; for (int i = 0; i < n; i++) if (d1[i] != d2[i]) wd++;
    S->byte_diff += wd; if (wd) S->case_diff++;
    snprintf(g_ctx, sizeof g_ctx, "copy32s");
    record(so_, d2, sizeof(Ipp32s) * (size_t)n);
  }
  /* Atan_32f_A11 (A11: bit 一致は要求しない — 統計記録) */
  {
    long diff = 0, elems = 0, nan_diff = 0; double maxulp = 0;
    for (int ci = 0; ci < 60; ci++) {
      int n = pick(11, LENS);
      static float in[8192], t1[8192], t2[8192];
      int sp = ci % 3 == 2;
      for (int i = 0; i < n; i++) {
        float v = (float)((rnd64() >> 11) / 9007199254740992.0) * (float)(1u << ri(60)) * (ri(2) ? 1.f : -1.f);
        if (sp) { switch (ri(10)) { case 0: v = 0.f; break; case 1: v = -0.f; break; case 2: v = INFINITY; break; case 3: v = -INFINITY; break;
                                     case 4: v = (float)0x7FC00000; break; case 5: v = 1.f; break; case 6: v = -1.f; break;
                                     case 7: v = 1e30f; break; case 8: v = 1e-30f; break; default: v = 0.70710678f; } }
        in[i] = v;
      }
      memcpy(t1, in, sizeof(float) * (size_t)n); memcpy(t2, in, sizeof(float) * (size_t)n);
      int sr_ = ((int (MS *)(const float *, float *, int))ex("ippsAtan_32f_A11"))(in, t1, n);
      int so_ = ippsAtan_32f_A11(in, t2, n);
      S->cases++;
      if (sr_ != so_) S->st_mis++;
      for (int i = 0; i < n; i++) {
        uint32_t x, y; memcpy(&x, &t1[i], 4); memcpy(&y, &t2[i], 4);
        elems++;
        if (x == y) continue;
        if (x != x && y != y) { nan_diff++; continue; }
        diff++;
        /* ulp (符号付き int 表現差) */
        int64_t ux = (int32_t)x, uy = (int32_t)y;
        double ulp = fabs((double)(ux - uy));
        if (ulp > maxulp) maxulp = ulp;
      }
#ifndef WASM_REPLAY
      snprintf(g_ctx, sizeof g_ctx, "atan");
      record(so_, t2, sizeof(float) * (size_t)n); /* A11 は許容差のため wasm 突合対象外 (REPORT §12-5) */
#endif
    }
    printf("  ippsAtan_32f_A11: elems=%ld bit_diff=%ld (%.4f%%) nan_payload_diff=%ld maxulp=%.1f (A11: CAB-141 許容)\n",
           elems, diff, elems ? 100.0 * diff / elems : 0.0, nan_diff, maxulp);
  }
  ENDF(0)
}

int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  const char *dll = fl_ipp_dll_path();
  const char *path = NULL;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--dump") && i + 1 < argc) { path = argv[++i]; }
    else if (!strcmp(argv[i], "--replay") && i + 1 < argc) { path = argv[++i]; }
    else dll = argv[i];
  }
#ifdef WASM_REPLAY
  g_wasm = 1;
  if (!path) { fprintf(stderr, "usage: resize_oracle.wasm --replay <hashfile>\n"); return 2; }
  g_dumpf = fopen(path, "rb");
  if (!g_dumpf) { fprintf(stderr, "cannot open %s\n", path); return 2; }
  printf("resize_oracle WASM replay: %s\n", path);
#else
  if (pe_load(dll, &pe)) return 1;
  ((int (MS *)(uint64_t))ex("ippSetCpuFeatures"))(~0ULL);
  if (path) { g_dumpf = fopen(path, "wb"); if (!g_dumpf) return 2; printf("resize_oracle: dump -> %s\n", path); }
  else printf("resize_oracle: loaded %s\n", dll);
#endif

  fam_resize_grid(1);
  fam_resize_grid(3);
  fam_resize_grid(4);
  fam_resize_fuzz(1, 300);
  fam_resize_fuzz(3, 200);
  fam_resize_fuzz(4, 200);
  fam_resize_err();
  fam_getbufsize();
  fam_sig();

  if (g_wasm) {
    fclose(g_dumpf);
    printf("wasm replay: records=%ld mismatch=%ld -> %s\n", g_rec, g_bad, g_bad ? "FAIL" : "PASS");
    return g_bad ? 1 : 0;
  }
  if (g_dumpf) { fclose(g_dumpf); printf("dump records=%ld\n", g_rec); }
  printf("mode stats (cases/case_diff):");
  for (int m = 0; m < 24; m++) if (g_mode_cases[m]) printf(" it%d=%ld/%ld", m, g_mode_cases[m], g_mode_diff[m]);
  printf("\n");
  printf("pixel diff rate: %ld/%ld (%.4f%%)\n", g_px_diff, g_px_tot, g_px_tot ? 100.0 * g_px_diff / g_px_tot : 0.0);
  printf("diff hist |d|: 1:%ld 2:%ld 3:%ld 4:%ld 5:%ld 6:%ld 7:%ld 8+:%ld\n",
         g_hist[1], g_hist[2], g_hist[3], g_hist[4], g_hist[5], g_hist[6], g_hist[7], g_hist[8]);
  for (int m = 0; m < 24; m++) if (g_mode_px[m]) printf("  it%d: px=%ld pxdiff=%ld (%.3f%%) big8=%ld\n", m, g_mode_px[m], g_mode_pxd[m], 100.0 * g_mode_pxd[m] / g_mode_px[m], g_mode_big[m]);
  printf("SUM {\"cases\":%ld,\"case_diff\":%ld,\"st_mis\":%ld,\"byte_diff\":%ld,\"px_diff\":%ld,\"px_tot\":%ld}\n",
         g_tot_cases, g_tot_case_diff, g_tot_st_mis, g_tot_byte_diff, g_px_diff, g_px_tot);
  return 0;
}
