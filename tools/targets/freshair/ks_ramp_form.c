/* ks_ramp_form.c — Gain の ramp 1 段 (first=0 経路) の丸め形だけを比べる単体テスト。
 *   KH (0x1804b0380): cur = a + (b - a) * t     (xmm3 = (b-a)*t; += a)
 *   SC (0x180afe090): cur = (1 - t) * a + t * b (xmm0 = (1-t)*a; xmm1 = t*b; +)
 * t = k * (1/n) (k = 1..n)。-ffp-contract=off で FMA を禁止し、float32 のまま比べる。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned rng = 12345;
static unsigned R32(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
static float RF(float lo, float hi) { return lo + (hi - lo) * ((R32() >> 8) / 16777216.0f); }

int main(void) {
    long total = 0, diff = 0;
    for (int trial = 0; trial < 1000000; trial++) {
        int n = 1 + (int)(R32() % 128);
        volatile float a = RF(0, 3), b = RF(0, 3), coef = 1.0f / (float)n;
        float cur_kh = a, cur_sc_dummy = 0;
        (void)cur_sc_dummy;
        for (int k = 1; k <= n; k++) {
            volatile float t = (float)k * coef;
            volatile float kh = a + (b - a) * t;
            volatile float sc = (1.0f - t) * a + t * b;
            total++;
            if (memcmp((const void*)&kh, (const void*)&sc, 4) != 0) diff++;
        }
    }
    printf("{\"samples\": %ld, \"differ\": %ld}\n", total, diff);
    return 0;
}
