/* rcpps_helper_check.c — ghidra_route の RCPPS_HELPER (V128 rcpps(undefined1 dst[16], V128 src)) が
 * 実機の rcpps (_mm_rcp_ps) と 4 lane 全て bit 一致することを、ホスト C で検証する。
 * 戻り値 (V128) を突合する。dst 引数は helper 内で使われない (呼出形の互換のため渡すだけ)。
 * 突合は -O0 / -O2 の両方で行う (strict aliasing の回帰検出)。
 *
 *   python3 -c "import sys; sys.path.insert(0,'tools/targets/kilohearts/ghidra_route'); \
 *     import ghidra_to_c as g; open('work/rcpps_helper.c','w').write(g.RCPPS_HELPER % g.approx_rcp_table())"
 *   cc -O2 -msse2 -Iwork -o work/rcpps_helper_check tools/targets/kilohearts/snapins/scripts/rcpps_helper_check.c
 *   ./work/rcpps_helper_check
 *
 * 入力は乱数 (seed 7)。 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <emmintrin.h>
typedef unsigned char undefined1;
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
        for (int l = 0; l < 4; l++) {
            uint32_t x = ((uint32_t)rand() << 16) ^ (uint32_t)rand();
            memcpy(s.b + 4 * l, &x, 4);
            in[l] = fl(x);
        }
        d = rcpps(NULL, s);
        _mm_storeu_ps(hw, _mm_rcp_ps(_mm_loadu_ps(in)));
        for (int l = 0; l < 4; l++) {
            uint32_t y;
            memcpy(&y, d.b + 4 * l, 4);
            n++;
            if (y != bits(hw[l])) {
                bad++;
                if (bad <= 3) printf("lane%d in=%08x out=%08x hw=%08x\n", l, bits(in[l]), y, bits(hw[l]));
            }
        }
    }
    printf("lanes=%ld mismatch=%ld\n", n, bad);
    return bad != 0;
}
