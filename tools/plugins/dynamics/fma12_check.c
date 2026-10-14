/* 12 形 (3 順序 x 4 演算) の FMA3 sd: 実機命令 vs msimd11_core.h の _f*sd 系 (lane0)。
 * tol: ±0 と NaN の符号を同一視して比較 / strict: bit 完全一致。
 * 実機 asm は AT&T 構文 (オペランド逆順): Intel "op %dst, %src2, %src3" = AT&T "op %src3, %src2, %dst"。
 * ビルド: gcc -O0 -mfma -msse2 -I../ -o fma12_check fma12_check.c -lm   実行: ./fma12_check [N] */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <immintrin.h>
#include "lift/passes/msimd11_core.h"

static u64 s = 0x9E3779B97F4A7C15ull;
static u64 rnd(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s; }
static double rd(void) {
    u64 r = rnd(); unsigned k = (unsigned)(r % 40);
    if (k == 0) return 0.0;
    if (k == 1) return -0.0;
    if (k == 2) return 1.0 / 0.0;
    if (k == 3) return -1.0 / 0.0;
    double d; u64 b = rnd();
    b = (b & 0x800FFFFFFFFFFFFFull) | ((u64)(1023 - 30 + (rnd() % 60)) << 52);
    memcpy(&d, &b, 8); return d;
}

#define FORM(NAME, ASM, FN)                                                              \
static void run_##NAME(long N, long *tol, long *strict) {                                \
    long tb = 0, sb = 0;                                                                 \
    for (long i = 0; i < N; i++) {                                                       \
        double a = rd(), b = rd(), c = rd();                                             \
        __m128d va = _mm_set_sd(a), vb = _mm_set_sd(b), vc = _mm_set_sd(c);              \
        __asm__ volatile(ASM : "+x"(va) : "x"(vb), "x"(vc));                             \
        u128 ha = 0, hb = 0; memcpy(&ha, &a, 8); memcpy(&hb, &b, 8);                     \
        u128 hr = FN(ha, hb, c);                                                         \
        double rv, hd; u64 x, y;                                                         \
        _mm_store_sd(&rv, va); memcpy(&hd, &hr, 8);                                      \
        memcpy(&x, &rv, 8); memcpy(&y, &hd, 8);                                          \
        if (x != y) sb++;                                                                \
        if (!((rv != rv && hd != hd) || (rv == 0 && hd == 0) || x == y)) tb++;           \
    }                                                                                    \
    *tol = tb; *strict = sb;                                                             \
}

FORM(f132, "vfmadd132sd %2, %1, %0", _fma132sd)
FORM(s132, "vfmsub132sd %2, %1, %0", _fms132sd)
FORM(nm132, "vfnmadd132sd %2, %1, %0", _fnm132sd)
FORM(ns132, "vfnmsub132sd %2, %1, %0", _fnms132sd)
FORM(f213, "vfmadd213sd %2, %1, %0", _fma213sd)
FORM(s213, "vfmsub213sd %2, %1, %0", _fms213sd)
FORM(nm213, "vfnmadd213sd %2, %1, %0", _fnm213sd)
FORM(ns213, "vfnmsub213sd %2, %1, %0", _fnms213sd)
FORM(f231, "vfmadd231sd %2, %1, %0", _fma231sd)
FORM(s231, "vfmsub231sd %2, %1, %0", _fms231sd)
FORM(nm231, "vfnmadd231sd %2, %1, %0", _fnm231sd)
FORM(ns231, "vfnmsub231sd %2, %1, %0", _fnms231sd)

int main(int argc, char **argv) {
    long N = argc > 1 ? atol(argv[1]) : 20000;
    long tt = 0, st = 0; int forms = 0;
#define RUN(NAME) { long t, q; run_##NAME(N, &t, &q); \
    printf("%-6s tol-mismatch %ld / %ld  strict-bit-mismatch %ld\n", #NAME, t, N, q); tt += t; st += q; forms++; }
    RUN(f132) RUN(s132) RUN(nm132) RUN(ns132)
    RUN(f213) RUN(s213) RUN(nm213) RUN(ns213)
    RUN(f231) RUN(s231) RUN(nm231) RUN(ns231)
    printf("forms %d, tol-mismatch total %ld, strict-bit total %ld\n", forms, tt, st);
    return tt != 0;
}
