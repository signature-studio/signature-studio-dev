/* fa_wc_rt.c — fa_wc.py instr が挿入する __wchk の実体 (ICALL-54 #1998)。
 * 監視範囲 [WLO, WHI) と重なる store と、値 "emsc" (0x63736d65) の store (任意アドレス) を stderr に出す。 */
#include <stdint.h>
#include <stdio.h>

#define WLO 0x36319000ull
#define WHI 0x36319020ull
#define WVAL 0x63736d65ull

void __wchk(uint64_t a, uint64_t sz, uint64_t v, uint64_t line) {
  int in = (a < WHI && a + sz > WLO);
  if (in || (v & 0xffffffffull) == WVAL)
    fprintf(stderr, "WC%s line=%llu addr=%llx sz=%llu val=%llx\n", in ? "" : "V",
            (unsigned long long)line, (unsigned long long)a,
            (unsigned long long)sz, (unsigned long long)v);
}
