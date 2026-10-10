/* ott_glue.c: JS から lifted 関数を MS x64 ABI 風に呼ぶ入口 */
#include "ott_cpu.h"
static uint8_t guest_stack[1 << 20] __attribute__((aligned(16)));
#define STACK_TOP ((uint64_t)(uintptr_t)guest_stack + sizeof(guest_stack) - 0x100)
uint64_t ott_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                 uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) {
    R[RSP] = STACK_TOP;
    R[RCX] = a0; R[RDX] = a1; R[R8] = a2; R[R9] = a3;
    X[0].q[0] = x0; X[0].q[1] = 0; X[1].q[0] = x1; X[1].q[1] = 0; X[2].q[0] = x2; X[2].q[1] = 0; X[3].q[0] = x3; X[3].q[1] = 0;
    R[RSP] -= 8; ST64(R[RSP], 0xdead0000ull);
    ott_dispatch(va);
    return R[RAX];
}
uint64_t ott_xmm0(void) { return X[0].q[0]; }
void ott_set_stackarg(int i, uint64_t v) { ST64(STACK_TOP + 0x20 + 8 * (uint64_t)i, v); }
uint64_t ott_rget(int i) { return R[i]; }
