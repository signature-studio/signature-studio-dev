/* IPP-9 (#276): 自前 VectorSlope_64f/_32f 出力の FNV-1a ハッシュ (native と wasm の bit 一致確認用)。
   vslope_verify.c と同じ乱数列・ケース集合。実 DLL は不要 (wasm で動かすため)。 */
#include "ipp_min.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

IppStatus ippsVectorSlope_64f(double *, int, double, double);

static uint64_t rs = 0x9e3779b97f4a7c15ULL;
static double rnd01(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (double)(rs >> 11) / 9007199254740992.0; }
static double pick(void) {
  static const double fixed[] = {0.0, 1.0, -1.0, 0.1, -1.0 / 3.0, 0.3, 1.2345678, 65536.0, -0.00375};
  int k = (int)(rnd01() * 14);
  if (k < 9) return fixed[k];
  double m = rnd01() * 2.0 - 1.0;
  return k == 9 ? m : k == 10 ? m * 1e-3 : k == 11 ? m * 1e3 : k == 12 ? m * 1e5 : m * 100.0;
}
static uint64_t h = 1469598103934665603ULL;
static void fnv(const void *p, size_t n) { const unsigned char *c = p; for (size_t i = 0; i < n; i++) { h ^= c[i]; h *= 1099511628211ULL; } }

int main(void) {
  static const int NS[] = {1, 2, 3, 4, 5, 7, 8, 9, 12, 15, 16, 17, 24, 31, 32, 33, 48, 64, 100, 257, 1000, 4097};
  static double o64[4200];
  static float o32[4200];
  for (int t = 0; t < 2400; t++) {
    double o = pick(), s = pick();
    int n = NS[(int)(rnd01() * 22)];
    ippsVectorSlope_64f(o64, n, o, s); fnv(o64, sizeof(double) * (size_t)n);
    ippsVectorSlope_32f(o32, n, (float)o, (float)s); fnv(o32, sizeof(float) * (size_t)n);
  }
  printf("vslope_hash %016llx\n", (unsigned long long)h);
  return 0;
}
