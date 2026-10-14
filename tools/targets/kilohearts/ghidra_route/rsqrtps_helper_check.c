/* rsqrtps_helper_check.c — ghidra_route の RSQRTPS_HELPER (V128 rsqrtps 近似, snapins/scripts/approx_tables.b64 の rsq 表) が
 * ホスト CPU の rsqrtps (_mm_rsqrt_ps) と 4 lane 全て bit 一致することを検証する (rcpps_helper_check.c と同じ方式)。
 *
 *   python3 -c "import sys; sys.path.insert(0,'tools/targets/kilohearts/ghidra_route'); \
 *     import ghidra_to_c as g; o,e=g.approx_rsq_tables(); open('work/rsqrtps_helper.c','w').write(g.RSQRTPS_HELPER % (o,e))"
 *   cc -O2 -msse2 -Iwork -o work/rsqrtps_helper_check tools/targets/kilohearts/ghidra_route/rsqrtps_helper_check.c
 *   ./work/rsqrtps_helper_check
 *
 * 入力は線形合同法 (seed 7) の 32bit 乱数 (負数・NaN・非正規を含む)。 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <emmintrin.h>
#include <xmmintrin.h>
typedef unsigned char undefined1;
typedef struct { unsigned char b[16]; } V128;
#include "rsqrtps_helper.c"

int main(void) {
    uint32_t st = 7;
    long n = 0, mis = 0;
    for (long it = 0; it < 2000000; it++) {
        uint32_t w[4];
        for (int i = 0; i < 4; i++) {
            st = st * 1664525u + 1013904223u;
            w[i] = st ^ ((st >> 15) * 0x9e3779b9u);
        }
        V128 s, r;
        memcpy(s.b, w, 16);
        r = rsqrtps(s, s);
        __m128 h = _mm_rsqrt_ps(_mm_castsi128_ps(_mm_loadu_si128((const __m128i *)w)));
        uint32_t hw[4];
        _mm_storeu_si128((__m128i *)hw, _mm_castps_si128(h));
        for (int i = 0; i < 4; i++) {
            uint32_t got;
            memcpy(&got, r.b + 4 * i, 4);
            n++;
            if (got != hw[i]) mis++;
        }
    }
    printf("rsqrtps lanes %ld mismatch %ld\n", n, mis);
    return 0;
}
