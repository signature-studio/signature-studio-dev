/* CAB-261 (IPP-6): interp 5/7 (CUBIC2P 系) の 1D 重みをスパイク法で実 DLL から直接抽出。
   src の 1 バイト (k) だけ 255、他 0 → dst = 255·w_k(x) (整数)。
   H パス (1 行) と V パス (1 列) を分離して採取。it=5/6/7 + 比較用 it=4 (CUBIC)。
   build: gcc -O1 -g -o sp57 sp57.c ../../ref/pe_load.c -lm
   usage: FL_WIN64_DIR=<fl-win64 展開先> ./sp57 > sp57.log */
#define _GNU_SOURCE
#include "../../ref/pe_load.h"
#include "fl_dll_path.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { int x, y, w, h; } R4;
typedef struct { int w, h; } S2;
typedef int (MS *F_SetCpu)(uint64_t);
typedef int (MS *F_RSP)(const void *, S2, int, R4, void *, int, R4, double, double, double, double, int, void *);

static PE pe;
static void *ex(const char *n) { void *p = pe_export(&pe, n); if (!p) { fprintf(stderr, "no export %s\n", n); exit(1); } return p; }

#define SZN 96
static uint8_t src[SZN * SZN], dst[SZN * SZN], pbuf[1 << 22];

static void run1(F_RSP rsp, int it, double fx, double fy, double sx, double sy, R4 sr, R4 dr, int ss, int ds) {
  memset(dst, 0, sizeof dst);
  int st = rsp(src, (S2){SZN, SZN}, ss, sr, dst, ds, dr, fx, fy, sx, sy, it, pbuf);
  printf("st=%d :", st);
  for (int y = dr.y; y < dr.y + dr.h; y++)
    for (int x = dr.x; x < dr.x + dr.w; x++) printf(" %d", dst[y * ds + x]);
  printf("\n");
}

int main(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  if (pe_load(fl_ipp_dll_path(), &pe)) return 1;
  ((F_SetCpu)ex("ippSetCpuFeatures"))(~0ULL);
  F_RSP rsp = (F_RSP)ex("ippiResizeSqrPixel_8u_C1R");
  memset(src, 0, sizeof src);

  /* ターゲット: 縮小 (fx < 1) と拡大 (fx > 1) の両方。it=5/7 は Cubic2P 系の推定。
     H: srcRoi (0,0,SZ,1) dst SZ/2 x 1 → fx=0.5。拡大は fx=2.0 で dst 2*SZ。 */
  static const double CF[] = {2.0, 1.5, 1.25, 1.0, 0.75, 0.5, 0.3, 0.25};
  static const double CS[] = {0.0, 0.25, 0.5, 0.75, -0.25, -0.5, -0.75, 1.0};
  static const int ITS[] = {4, 5, 6, 7};

  for (size_t ii = 0; ii < sizeof ITS / sizeof *ITS; ii++) {
    int it = ITS[ii];
    for (size_t fi = 0; fi < sizeof CF / sizeof *CF; fi++) {
      double fx = CF[fi];
      /* dst 幅は ROI 幅 / fx に合わせる (書込条件 0<=u<=w を満たす範囲で) */
      int dw = (int)(32.0 / fx + 0.5);
      if (dw < 1) dw = 1;
      if (dw > 48) dw = 48;
      for (size_t si = 0; si < sizeof CS / sizeof *CS; si++) {
        for (int k = 0; k < 32; k++) {
          memset(src, 0, sizeof src);
          src[k] = 255;
          printf("H it=%d fx=%.3f sx=%.2f k=%d ", it, fx, CS[si], k);
          run1(rsp, it, fx, 1.0, CS[si], 0.0, (R4){0, 0, 32, 1}, (R4){0, 0, dw, 1}, SZN, SZN);
        }
      }
    }
    /* V パス */
    for (size_t fi = 0; fi < sizeof CF / sizeof *CF; fi++) {
      double fy = CF[fi];
      int dh = (int)(32.0 / fy + 0.5);
      if (dh < 1) dh = 1;
      if (dh > 48) dh = 48;
      for (size_t si = 0; si < sizeof CS / sizeof *CS; si++) {
        for (int k = 0; k < 32; k++) {
          memset(src, 0, sizeof src);
          src[k * SZN] = 255;
          printf("V it=%d fy=%.3f sy=%.2f k=%d ", it, fy, CS[si], k);
          run1(rsp, it, 1.0, fy, 0.0, CS[si], (R4){0, 0, 1, 32}, (R4){0, 0, 1, dh}, SZN, SZN);
        }
      }
    }
  }
  printf("done\n");
  return 0;
}
