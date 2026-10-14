/* rcpps_helper_check.c — ghidra_route の RCPPS_HELPER (rcpps(V128 dst, V128 src)) が
 * 実機の rcpps (_mm_rcp_ps) と 4 lane 全て bit 一致することを、ホスト C で検証する。
 *
 *   python3 -c "import sys; sys.path.insert(0,'tools/targets/kilohearts/ghidra_route'); \
 *     import ghidra_to_c as g; open('work/rcpps_helper.c','w').write(g.RCPPS_HELPER % {'RCP': g.rcp_table_literal()})"
 *   cc -O2 -msse2 -Iwork -o work/rcpps_helper_check tools/targets/kilohearts/snapins/scripts/rcpps_helper_check.c
 *   ./work/rcpps_helper_check
 *
 * 入力は乱数 (seed 7)。dst は 0 固定 (helper は dst を読まない)。 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <emmintrin.h>
typedef struct { unsigned char b[16]; } V128;
#include "rcpps_helper.c"

static uint32_t bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float fl(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }

int main(void) {
    long n = 0, bad = 0;
    srand(7);
    for (long i = 0; i < 2000000; i++) {
        V128 s, d;
        float in[4], hw[4];
        memset(&d, 0, sizeof d);
        for (int l = 0; l < 4; l++) {
            uint32_t x = ((uint32_t)rand() << 16) ^ (uint32_t)rand();
            memcpy(s.b + 4 * l, &x, 4);
            in[l] = fl(x);
        }
        V128 r = rcpps(d, s);
        _mm_storeu_ps(hw, _mm_rcp_ps(_mm_loadu_ps(in)));
        for (int l = 0; l < 4; l++) {
            uint32_t y;
            memcpy(&y, r.b + 4 * l, 4);
            n++;
            if (y != bits(hw[l])) {
                bad++;
                if (bad <= 3) printf("lane%d in=%08x helper=%08x hw=%08x\n", l, bits(in[l]), y, bits(hw[l]));
            }
        }
    }
    printf("lanes=%ld mismatch=%ld\n", n, bad);
    return bad != 0;
}
