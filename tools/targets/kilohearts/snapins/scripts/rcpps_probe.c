/* rcpps_probe.c — 実機 rcpps 近似の依存性 / テーブル測定 (KH-6 REPORT §13-1 の根拠)。
 * usage:
 *   cc -O2 -msse -mno-avx -o rcpps_probe rcpps_probe.c
 *   ./rcpps_probe deps             低 11 mantissa bit / sign / exponent への依存性
 *   ./rcpps_probe table <NB>       exp(256) × mantissa 上位 NB bit の全列挙 (16進 bits)
 *   ./rcpps_probe check < in.txt   任意の float bits (16進) → rcpps 結果 bits
 *
 * レガシー SSE エンコーディング (VEX 無し) を -mno-avx で強制すること (vrcpps は同じ近似だが
 * 念のため)。native oracle は実機 AMD Ryzen 9 9950X。
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <emmintrin.h>

static uint32_t bitsf(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float fl(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }

/* rcpps (packed, 4 lane) の lane0 を返す */
static uint32_t rcp_lane0(uint32_t u) {
    __m128 v = _mm_set_ps(0.f, 0.f, 0.f, fl(u));
    float out[4] __attribute__((aligned(16)));
    _mm_store_ps(out, _mm_rcp_ps(v));
    return bitsf(out[0]);
}

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "deps";
    if (!strcmp(mode, "deps")) {
        uint32_t base = (100u << 23) | (0x5A5u << 11);
        uint32_t first = rcp_lane0(base);
        int ndiff = 0;
        for (uint32_t k = 0; k < 2048; k++) {
            uint32_t r = rcp_lane0(base | k);
            if (r != first) { if (ndiff < 8) printf("  lowbits %u -> %08x (base -> %08x)\n", k, r, first); ndiff++; }
        }
        printf("low11 dependency: %d / 2048 differ\n", ndiff);
        uint32_t rp = rcp_lane0(base), rn = rcp_lane0(base | 0x80000000u);
        printf("sign: +%08x  -%08x  same=%d\n", rp, rn, rp == rn);
        for (int e = 126; e <= 129; e++)
            printf("  exp %d -> %08x\n", e, rcp_lane0(((uint32_t)e << 23) | (0x5A5u << 11)));
        return 0;
    }
    if (!strcmp(mode, "table")) {
        int NB = argc > 2 ? atoi(argv[2]) : 12;
        uint32_t n = 1u << NB;
        for (uint32_t e = 0; e < 256; e++)
            for (uint32_t a = 0; a < n; a++)
                printf("%08x\n", rcp_lane0((e << 23) | (a << (23 - NB))));
        return 0;
    }
    if (!strcmp(mode, "check")) {
        char line[64];
        while (fgets(line, sizeof line, stdin)) {
            if (line[0] == '\n' || line[0] == 0) continue;
            printf("%08x\n", rcp_lane0((uint32_t)strtoul(line, 0, 16)));
        }
        return 0;
    }
    return 2;
}
