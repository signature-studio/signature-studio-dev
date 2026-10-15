/* CAB-261: it 別の位相スイープ。dst 行全体を記録し、書込のある dst 位置の重みを使う。
   usage: FL_WIN64_DIR=<fl-win64 展開先> ./sweep2 <it>   (it 既定 7。未設定だと exit 2) */
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
static void *ex(const char *n) { void *p = pe_export(&pe, n); if (!p) { fprintf(stderr, "no %s\n", n); exit(1); } return p; }
#define SZN 128
static uint8_t src[SZN * SZN], dst[SZN * SZN], pbuf[1 << 22];
int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  if (pe_load(fl_ipp_dll_path(), &pe)) return 1;
  ((F_SetCpu)ex("ippSetCpuFeatures"))(~0ULL);
  F_RSP rsp = (F_RSP)ex("ippiResizeSqrPixel_8u_C1R");
  int it = argc > 1 ? atoi(argv[1]) : 7;
  int NPH = 64;
  for (int p = 0; p < NPH; p++) {
    double sx = (double)p / NPH;
    if (sx >= 1.0) sx -= 1.0;
    printf("P %d %.6f", p, sx);
    for (int k = 0; k < 16; k++) {
      memset(src, 0, sizeof src); memset(dst, 0, sizeof dst);
      src[k] = 255;
      int st = rsp(src, (S2){SZN, SZN}, SZN, (R4){0, 0, 96, 1}, dst, SZN, (R4){0, 0, 16, 1}, 1.0, 1.0, sx, 0.0, it, pbuf);
      (void)st;
      /* nonzero な dst 位置を出力 (位置:値) */
      printf(" |");
      for (int x = 0; x < 16; x++) if (dst[x]) printf(" %d:%d", x, dst[x]);
    }
    printf("\n");
  }
  return 0;
}
