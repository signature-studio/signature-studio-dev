/* qfc_ov_trace_4263.c — 計測専用 (T-SH-107 / #4263)。qfc_ov.c と同じ継続の復元に、入口の状態出力を足したもの。
 * qfc_trace_4263.sh が使う。判定はしない。本体の override (qfc_ov.c) は変えない。 */
#include <stdio.h>
#include <setjmp.h>
#include "fle_cpu.h"

extern uint64_t fle_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                        uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3);

static jmp_buf qfc_anchor;
static uint64_t qfc_target;

void qfc_ov_longjmp(void) {
    uint64_t buf = R[1];
    uint32_t retval = R[2] & 0xffffffff;
    fprintf(stderr, "[trace4263] longjmp enter buf=%#llx retval=%u caller_ret=%#llx flagB(0x5d0cb0)=%u recB(0x5d0c80)=%#llx flagA(0x5d0db0)=%u flagAll(0x5aa000)=%u\n",
            (unsigned long long)buf, retval, (unsigned long long)LD64(R[RSP]),
            (unsigned)LD8(0x5d0cb0), (unsigned long long)LD64(0x5d0c80),
            (unsigned)LD8(0x5d0db0), (unsigned)LD32(0x5aa000));
    for (int k = 0; k < 400; k++) {
        uint64_t w = LD64(R[RSP] + 8 * k);
        if (w >= 0x400000 && w < 0x620000) fprintf(stderr, "[trace4263] stack[%d]=%#llx\n", k, (unsigned long long)w);
    }
    R[0] = retval;
    R[3] = LD64(buf + 0x10);
    R[5] = LD64(buf + 0x18);
    R[6] = LD64(buf + 0x20);
    R[7] = LD64(buf + 0x28);
    R[12] = LD64(buf + 0x30); R[13] = LD64(buf + 0x38); R[14] = LD64(buf + 0x40); R[15] = LD64(buf + 0x48);
    for (int k = 0; k < 10; k++) X[6 + k] = LDX(buf + 0x50 + 16 * k);
    R[4] = LD64(buf + 8);
    qfc_target = LD64(buf);
    longjmp(qfc_anchor, 1);
}

uint64_t qfc_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                 uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) {
    if (setjmp(qfc_anchor) == 0)
        return fle_run(va, a0, a1, a2, a3, x0, x1, x2, x3);
    ott_dispatch(qfc_target);
    return R[RAX];
}
