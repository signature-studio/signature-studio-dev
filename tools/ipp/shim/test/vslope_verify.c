/* IPP-9 (#276): ippsVectorSlope_64f / _32f の bit 一致検証 (実 DLL vs 自前実装, 乱数ケース)。
   build: gcc -O1 -ffp-contract=off -fno-fast-math -I ../../src -o vslope_verify vslope_verify.c \
          ../../ref/pe_load.c ../impl/ipp_sig_fill3.c ../../src/ipp_min.c -lm
   usage: vslope_verify <dll> [--neg] [--mis K]
     --neg: 自前実装を 1 ULP 壊して FAIL することを確認 / --mis K: 出力先を 64B 境界から K 要素ずらす (実 DLL は出力先アライメントで出力が変わる) */
#include "../../ref/pe_load.h"
#include "ipp_min.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
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

int main(int argc, char **argv) {
  if (argc < 2) return 2;
  int neg = 0, mis = 0;
  for (int a_ = 2; a_ < argc; a_++) { if (!strcmp(argv[a_], "--neg")) neg = 1; else if (!strcmp(argv[a_], "--mis") && a_ + 1 < argc) mis = atoi(argv[++a_]); }
  PE pe;
  if (pe_load(argv[1], &pe)) return 1;
  static const int NS[] = {1, 2, 3, 4, 5, 7, 8, 9, 12, 15, 16, 17, 24, 31, 32, 33, 48, 64, 100, 257, 1000, 4097};
  static const uint64_t masks[] = {0x1, 0x3, 0x7, 0xf, 0x1f, 0x3f};
  static double r64a[4216] __attribute__((aligned(64))), o64a[4216] __attribute__((aligned(64)));
  static float r32a[4216] __attribute__((aligned(64))), o32a[4216] __attribute__((aligned(64)));
  double *r64 = r64a + mis, *o64 = o64a + mis; float *r32 = r32a + mis, *o32 = o32a + mis;
  long ncase = 0, nelem = 0, bad_case = 0, bad_elem = 0;
  for (int mi = 0; mi < 6; mi++) {
    ((int (MS *)(uint64_t))pe_export(&pe, "ippSetCpuFeatures"))(masks[mi]);
    int (MS *rv64)(double *, int, double, double) = pe_export(&pe, "ippsVectorSlope_64f");
    int (MS *rv32)(float *, int, float, float) = pe_export(&pe, "ippsVectorSlope_32f");
    rs = 0x9e3779b97f4a7c15ULL + (uint64_t)mi * 0x1234567ULL;
    for (int t = 0; t < 400; t++) {
      double o = pick(), s = pick();
      int n = NS[(int)(rnd01() * 22)];
      memset(r64a, 0, sizeof r64a); memset(o64a, 0, sizeof o64a); memset(r32a, 0, sizeof r32a); memset(o32a, 0, sizeof o32a);
      int a = rv64(r64, n, o, s), b = ippsVectorSlope_64f(o64, n, o, s);
      int c = rv32(r32, n, (float)o, (float)s), d = ippsVectorSlope_32f(o32, n, (float)o, (float)s);
      if (neg && n > 20) { o64[n - 1] = nextafter(o64[n - 1], 1e300); o32[n - 1] = nextafterf(o32[n - 1], 1e30f); }
      long bd = 0;
      for (int i = 0; i < n; i++) { if (memcmp(&r64[i], &o64[i], 8)) bd++; if (memcmp(&r32[i], &o32[i], 4)) bd++; }
      ncase += 2; nelem += 2L * n;
      if (a != b || c != d) { bad_case += 2; printf("ST-MIS n=%d %d/%d %d/%d\n", n, a, b, c, d); }
      if (bd) { bad_case++; bad_elem += bd; if (bad_case <= 3) printf("DIFF mask=0x%llx n=%d o=%a s=%a bd=%ld\n", (unsigned long long)masks[mi], n, o, s, bd); }
    }
  }
  printf("vslope_verify%s mis=%d: masks=6 cases=%ld elements=%ld bad_cases=%ld bad_elements=%ld\n", neg ? " (NEG)" : "", mis, ncase, nelem, bad_case, bad_elem);
  return bad_case ? 1 : 0;
}
