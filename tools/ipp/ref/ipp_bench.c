/* ネイティブ側ベンチ: 実 IPP (win DLL, 指定 ISA 経路) vs ipp_min.c(-O2 native)。n=4096 float / 16KB byte, ns/call を出力 */
#define _GNU_SOURCE
#include "pe_load.h"
#include "../src/ipp_min.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e9 + t.tv_nsec; }
typedef int (MS *fSD)(const void *, void *, int); typedef int (MS *fV)(float, float *, int);
int main(int argc, char **argv) {
  PE pe; pe_load(argv[1], &pe); ((int (MS *)(uint64_t))pe_export(&pe, "ippSetCpuFeatures"))(strtoull(argv[2], 0, 0));
  int n = 4096, iters = 200000; float *a = aligned_alloc(64, n * 4), *d = aligned_alloc(64, n * 4);
  for (int i = 0; i < n; i++) { a[i] = (i % 97) * 0.01f + 0.5f; d[i] = 0.25f; }
  fSD radd = pe_export(&pe, "ippsAdd_32f_I"), rmv = pe_export(&pe, "ippsMove_8u"), rsq = pe_export(&pe, "ippsSqrt_32f_A11"), rex = pe_export(&pe, "ippsExp_32f_A11");
  fV rmc = pe_export(&pe, "ippsMulC_32f_I");
  float *a_ = a; double t; printf("{\"n\":%d,\"iters\":%d,\"ns_per_call\":{", n, iters);
  #define B(label, ref, ours) \
    t = now(); for (int k = 0; k < iters; k++) { ref; } double tr_##label = (now() - t) / iters; \
    t = now(); for (int k = 0; k < iters; k++) { ours; } double to_##label = (now() - t) / iters; \
    printf("\"%s\":{\"ipp\":%.0f,\"ours_native\":%.0f},", #label, tr_##label, to_##label);
  B(Add_32f_I, radd(a, d, n), ippsAdd_32f_I(a, d, n))
  B(MulC_32f_I, rmc(1.0000001f, d, n), ippsMulC_32f_I(1.0000001f, d, n))
  B(Move_8u_16KB, rmv(a, d, n * 4), ippsMove_8u((Ipp8u *)a, (Ipp8u *)d, n * 4))
  B(Sqrt_32f_A11, rsq(a, d, n), ippsSqrt_32f_A11(a, d, n))
  B(Exp_32f_A11, rex(a, d, n), ippsExp_32f_A11(a, d, n))
  { int a, bb, c; typedef int (MS *gs_t)(int, int, int, int *, int *, int *); typedef int (MS *in_t)(void **, int, int, int, uint8_t *, uint8_t *); typedef int (MS *fw_t)(const float *, float *, const void *, uint8_t *);
    ((gs_t)pe_export(&pe, "ippsFFTGetSize_R_32f"))(12, 1, 0, &a, &bb, &c); void *spec; uint8_t *sp = aligned_alloc(64, a + 64), *sb = aligned_alloc(64, bb + 64), *bf = aligned_alloc(64, c + 64);
    ((in_t)pe_export(&pe, "ippsFFTInit_R_32f"))(&spec, 12, 1, 0, sp, sb); fw_t fw = pe_export(&pe, "ippsFFTFwd_RToPack_32f"); void *fi; float *y = aligned_alloc(64, 4096 * 4);
    (void)fi; int it2 = 20000; t = now(); for (int k = 0; k < it2; k++) fw(a_, y, spec, bf); printf("\"FFTFwd_RToPack_32f_4096\":{\"ipp\":%.0f},", (now() - t) / it2); }
  printf("\"_\":0}}\n"); return 0;
}
