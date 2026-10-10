/* verify_approx_helpers.c — gen_simd.py が生成した kh_rcp_exact / kh_rsqrt_exact が
 * 実機 (9950X) の rcpps / rsqrtps と bit 一致することを、ホスト C で独立に検証する。
 *
 * なぜこの検証が必要か: approx_probe.c の verify は「同一構造の emu_*」で検証している。
 * 本ファイルは **gen_simd.py が実際に出力した C コード** (work/verify_simd.c) をそのまま
 * コンパイルして噛ませるので、テンプレート展開ミス (型・lane 番号・シフト量) まで捕捉できる
 * (= 独立再計算スクリプト, 規則 37)。
 *
 *   cc -O2 -msse -mno-avx -I<snapins>/lift -o verify_approx_helpers \
 *      verify_approx_helpers.c work/verify_simd.c
 *   ./verify_approx_helpers           全グリッド + 乱数
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <emmintrin.h>

/* 生成物 (work/verify_simd.c) と同じヘッダ畳み込み。EX は KEEPALIVE 相当に寄せる。 */
typedef uint32_t u32;
#define EX __attribute__((used))
#include "verify_simd.c"   /* -I work */

static uint32_t bitsf(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float fl(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }
static uint32_t hw_rcp(uint32_t u) {
    __m128 v = _mm_set_ps(0.f, 0.f, 0.f, fl(u));
    float o[4] __attribute__((aligned(16)));
    _mm_store_ps(o, _mm_rcp_ps(v));
    return bitsf(o[0]);
}
static uint32_t hw_rsqrt(uint32_t u) {
    __m128 v = _mm_set_ps(0.f, 0.f, 0.f, fl(u));
    float o[4] __attribute__((aligned(16)));
    _mm_store_ps(o, _mm_rsqrt_ps(v));
    return bitsf(o[0]);
}

int main(int argc, char** argv) {
    long nrand = argc > 1 ? atol(argv[1]) : 500000;
    long b1 = 0, b2 = 0, g = 0, r = 0;
    /* 全グリッド e in 0..255 × m in 0..4095 (下位 11bit は 0) */
    for (uint32_t e = 0; e <= 255; e++)
        for (uint32_t m = 0; m < 4096; m++) {
            uint32_t x = (e << 23) | (m << 11);
            if (kh_rcp_exact(x) != hw_rcp(x)) { if (b1 < 5) printf("RCP grid e=%u m=%u got=%08x want=%08x\n", e, m, kh_rcp_exact(x), hw_rcp(x)); b1++; }
            if (kh_rsqrt_exact(x) != hw_rsqrt(x)) { if (b2 < 5) printf("RSQ grid e=%u m=%u got=%08x want=%08x\n", e, m, kh_rsqrt_exact(x), hw_rsqrt(x)); b2++; }
            g++;
        }
    uint32_t st = 987654321u;
    for (long i = 0; i < nrand; i++) {
        st = st * 1664525u + 1013904223u;
        uint32_t x = st;
        if (kh_rcp_exact(x) != hw_rcp(x)) b1++;
        if (kh_rsqrt_exact(x) != hw_rsqrt(x)) b2++;
        r++;
    }
    printf("generated-helper check: grid=%ld rand=%ld  rcp mismatches=%ld  rsqrt mismatches=%ld\n", g, r, b1, b2);
    return (b1 || b2) ? 1 : 0;
}
