/* 精度等級の実測: 実 IPP (各 ISA 経路) と ipp_min.c の A11 系/VectorSlope の誤差を倍精度真値に対して測る */
#define _GNU_SOURCE
#include "pe_load.h"
#include "../src/ipp_min.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static uint64_t rs = 88172645463325252ULL;
static double ur(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return (rs >> 11) * (1.0 / 9007199254740992.0); }
typedef int (MS *fA)(const float *, float *, int);
typedef int (MS *fH)(float *, int, float, float);
int main(int argc, char **argv) {
  PE pe; pe_load(argv[1], &pe); void *set = pe_export(&pe, "ippSetCpuFeatures");
  fA rexp = pe_export(&pe, "ippsExp_32f_A11"), rsqrt = pe_export(&pe, "ippsSqrt_32f_A11"); fH rvs = pe_export(&pe, "ippsVectorSlope_32f");
  static const struct { const char *n; unsigned long m; } ISA[] = {{"idx0_sse2", 0x7}, {"idx1_ssse3", 0x1F}, {"idx2_sse42", 0xFF}, {"idx3_avx", 0x1FF}, {"idx4_avx2", 0x1FFFF}, {"idx5_avx512", ~0UL}};
  int N = 200000; float *x = malloc(4 * N), *y = malloc(4 * N), *z = malloc(4 * N);
  printf("{\"acc\":[\n");
  for (int k = -1; k < 6; k++) {
    if (k >= 0) ((int (MS *)(uint64_t))set)(ISA[k].m);
    double ee = 0, es = 0, ev = 0, ev2 = 0;
    /* exp: x in [-87, 88] */
    for (int i = 0; i < N; i++) x[i] = (float)(ur() * 175 - 87);
    if (k < 0) ippsExp_32f_A11(x, y, N); else rexp(x, y, N);
    for (int i = 0; i < N; i++) { double t = exp((double)x[i]); double r = fabs(y[i] - t) / t; if (r > ee) ee = r; }
    for (int i = 0; i < N; i++) x[i] = (float)pow(10.0, ur() * 70 - 35);
    if (k < 0) ippsSqrt_32f_A11(x, y, N); else rsqrt(x, y, N);
    for (int i = 0; i < N; i++) { double t = sqrt((double)x[i]); double r = fabs(y[i] - t) / t; if (r > es) es = r; }
    /* slope: offset/slope audio-like, n up to 4096, 絶対誤差 / (|off|+|slope|*n) */
    for (int t = 0; t < 2000; t++) {
      float off = (float)(ur() * 4 - 2), sl = (float)(ur() * 0.01 - 0.005); int n = 1 + (int)(ur() * 4096);
      if (k < 0) ippsVectorSlope_32f(z, n, off, sl); else rvs(z, n, off, sl);
      double sc = fabs(off) + fabs(sl) * n; for (int i = 0; i < n; i++) { double tr = (double)off + (double)sl * i; double r = fabs(z[i] - tr) / sc; if (r > ev) ev = r; }
    }
    printf("%s{\"impl\":\"%s\",\"exp_A11_max_rel_err\":%.3g,\"exp_bits\":%.1f,\"sqrt_A11_max_rel_err\":%.3g,\"sqrt_bits\":%.1f,\"slope_max_err_over_scale\":%.3g,\"slope_in_eps24\":%.2f}\n",
      k >= 0 ? "," : "", k < 0 ? "ours(ipp_min.c)" : ISA[k].n, ee, -log2(ee), es, -log2(es), ev, ev / 5.96e-8);
  }
  printf("]}\n"); return 0;
}
