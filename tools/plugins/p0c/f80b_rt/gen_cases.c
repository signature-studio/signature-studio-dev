/* host (x86-64) で実行する。long double は x87 80-bit のため、wasm 側の検査の期待値をここで作る。
 * 出力 rt_cases.h: double→x87 像 (TO_*) と x87 像→double (FR_*) の期待値 200,000 件ずつ。 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

static uint64_t rnd64(void) {
  return ((uint64_t)rand() << 42) ^ ((uint64_t)rand() << 21) ^ (uint64_t)rand();
}

int main(void) {
  srand(12345);
  enum { N = 200000 };
  static uint64_t to_in[N], to_m[N], fr_m[N], fr_out[N];
  static uint16_t to_se[N], fr_e[N];
  int nt = 0;
  while (nt < N) {
    uint64_t bits = rnd64();
    if (nt % 4 == 0) bits &= 0x800FFFFFFFFFFFFFULL;
    if (nt % 7 == 0) bits &= 0x800FFFFFFFFFFFFFULL;
    double x; memcpy(&x, &bits, 8);
    if (isnan(x)) continue;
    unsigned char buf[16] = {0};
    long double ld = (long double)x;
    memcpy(buf, &ld, 10);
    memcpy(&to_m[nt], buf, 8);
    memcpy(&to_se[nt], buf + 8, 2);
    to_in[nt] = bits;
    nt++;
  }
  for (int i = 0; i < N; i++) {
    uint64_t m = rnd64() | 0x8000000000000000ULL;
    uint64_t e = 16383 - 1100 + (uint64_t)(rand() % 2200);
    if (i % 3 == 0) m &= ~0x7FFULL;
    if (i % 5 == 0) m |= 0x400ULL;
    if (i % 11 == 0) m = (m & ~0x7FFULL) | 0x3FFULL;
    if (i % 13 == 0) e = 16383 - 1074 + (uint64_t)(rand() % 60);
    unsigned char buf[16] = {0};
    uint16_t se16 = (uint16_t)e;
    memcpy(buf, &m, 8);
    memcpy(buf + 8, &se16, 2);
    long double ld;
    memcpy(&ld, buf, 10);
    double want = (double)ld;
    fr_m[i] = m; fr_e[i] = (uint16_t)e;
    memcpy(&fr_out[i], &want, 8);
  }
  FILE *f = fopen("rt_cases.h", "w");
  if (!f) return 1;
  fprintf(f, "static const uint64_t TO_IN[%d] = {", N);
  for (int i = 0; i < N; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)to_in[i]);
  fprintf(f, "};\nstatic const uint64_t TO_M[%d] = {", N);
  for (int i = 0; i < N; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)to_m[i]);
  fprintf(f, "};\nstatic const uint16_t TO_SE[%d] = {", N);
  for (int i = 0; i < N; i++) fprintf(f, "%s0x%04x", i ? "," : "", (unsigned)to_se[i]);
  fprintf(f, "};\nstatic const uint64_t FR_M[%d] = {", N);
  for (int i = 0; i < N; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)fr_m[i]);
  fprintf(f, "};\nstatic const uint16_t FR_E[%d] = {", N);
  for (int i = 0; i < N; i++) fprintf(f, "%s0x%04x", i ? "," : "", (unsigned)fr_e[i]);
  fprintf(f, "};\nstatic const uint64_t FR_OUT[%d] = {", N);
  for (int i = 0; i < N; i++) fprintf(f, "%s0x%016llxULL", i ? "," : "", (unsigned long long)fr_out[i]);
  fprintf(f, "};\n#define NT %d\n#define NF %d\n", N, N);
  fclose(f);
  return 0;
}
