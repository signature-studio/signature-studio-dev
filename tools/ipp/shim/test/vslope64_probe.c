/* IPP-9 (#276) 探索用: 実 IPP ippsVectorSlope_64f / _32f の出力 bit をダンプする。
   usage: vslope64_probe <dll> <cpumask> <64|32> <offset> <slope> <n> [misalign_elems]  (出力: 要素ごとに hex) */
#include "../../ref/pe_load.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
  if (argc < 7) return 2;
  PE pe;
  if (pe_load(argv[1], &pe)) return 1;
  ((int (MS *)(uint64_t))pe_export(&pe, "ippSetCpuFeatures"))(strtoull(argv[2], 0, 0));
  int bits = atoi(argv[3]);
  double off = strtod(argv[4], 0), sl = strtod(argv[5], 0);
  int n = atoi(argv[6]);
  int mis = argc > 7 ? atoi(argv[7]) : 0;
  if (bits == 64) {
    int (MS *vs)(double *, int, double, double) = pe_export(&pe, "ippsVectorSlope_64f");
    static double d0[(1 << 16) + 16] __attribute__((aligned(64)));
    double *d = d0 + mis;
    int st = vs(d, n, off, sl);
    printf("st=%d\n", st);
    for (int i = 0; i < n; i++) { uint64_t b; memcpy(&b, &d[i], 8); printf("%d %016llx\n", i, (unsigned long long)b); }
  } else {
    int (MS *vs)(float *, int, float, float) = pe_export(&pe, "ippsVectorSlope_32f");
    static float d0[(1 << 16) + 16] __attribute__((aligned(64)));
    float *d = d0 + mis;
    int st = vs(d, n, (float)off, (float)sl);
    printf("st=%d\n", st);
    for (int i = 0; i < n; i++) { uint32_t b; memcpy(&b, &d[i], 4); printf("%d %08x\n", i, b); }
  }
  return 0;
}
