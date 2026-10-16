/* wasm 側の検査 (f80_lower.py で x87 bitcast を展開した IR と結合する)。 期待値は gen_cases.c が作る rt_cases.h。 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "rt_cases.h"

uint64_t to_mant(double x);
uint64_t to_se(double x);
double from_img(uint64_t m, uint64_t se);

int main(void) {
  long fail_to = 0, fail_from = 0;
  for (int i = 0; i < NT; i++) {
    double x;
    memcpy(&x, &TO_IN[i], 8);
    uint64_t gm = to_mant(x);
    uint64_t gse = to_se(x) & 0xFFFF;
    if (gm != TO_M[i] || gse != TO_SE[i]) {
      if (fail_to < 5)
        printf("TO in=%016llx want m=%016llx se=%04x got m=%016llx se=%04llx\n",
               (unsigned long long)TO_IN[i], (unsigned long long)TO_M[i], TO_SE[i],
               (unsigned long long)gm, (unsigned long long)gse);
      fail_to++;
    }
  }
  for (int i = 0; i < NF; i++) {
    double got = from_img(FR_M[i], FR_E[i]);
    uint64_t gb;
    memcpy(&gb, &got, 8);
    if (gb != FR_OUT[i]) {
      if (fail_from < 5)
        printf("FROM m=%016llx e=%04x want=%016llx got=%016llx\n",
               (unsigned long long)FR_M[i], (unsigned)FR_E[i],
               (unsigned long long)FR_OUT[i], (unsigned long long)gb);
      fail_from++;
    }
  }
  printf("to: n=%d fail=%ld\nfrom: n=%d fail=%ld\n", NT, fail_to, NF, fail_from);
  return (fail_to || fail_from) ? 1 : 0;
}
