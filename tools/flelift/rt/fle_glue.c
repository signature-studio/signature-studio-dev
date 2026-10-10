/* fle_glue.c: JS から lifted 関数を MS x64 ABI 風に呼ぶ入口 (原型 = tools/ott/rt/ott_glue.c)。
 * FLEngine は恒等写像 (VA=guest address) のため stackarg も guest stack に直接置く。
 * 5+ 引数 (第 5 引数以降 = [rsp+0x28+8k]) は _InitLib(8 引数) 等で必要。 */
#include "fle_cpu.h"
static uint8_t guest_stack[1 << 21] __attribute__((aligned(16)));
#define STACK_TOP ((uint64_t)(uintptr_t)guest_stack + sizeof(guest_stack) - 0x100)
uint64_t fle_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                 uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3) {
    R[RSP] = STACK_TOP;
    R[RCX] = a0; R[RDX] = a1; R[R8] = a2; R[R9] = a3;
    X[0].q[0] = x0; X[0].q[1] = 0; X[1].q[0] = x1; X[1].q[1] = 0; X[2].q[0] = x2; X[2].q[1] = 0; X[3].q[0] = x3; X[3].q[1] = 0;
    R[RAX] = 0xFEEDFACE5EED0000ULL;   /* rax 未書込関数の判別用 sentinel (native ms_call と同一値) */
    R[RSP] -= 8; ST64(R[RSP], 0xdead0000ull);
    ott_dispatch(va);
    return R[RAX];
}
uint64_t fle_xmm0(void) { return X[0].q[0]; }
uint64_t fle_xmm1(void) { return X[1].q[0]; }
uint64_t fle_rget(int i) { return (i >= 0 && i < 16) ? R[i] : 0; }
uint64_t fle_mget(int i) { return (i >= 0 && i < 8) ? M[i] : 0; }
void fle_set_stackarg(int i, uint64_t v) { ST64(STACK_TOP + 0x20 + 8 * (uint64_t)i, v); }
void fle_reset(void);
void fle_reset(void) {
    memset(R, 0, sizeof(R)); memset(X, 0, sizeof(X)); memset(YL, 0, sizeof(YL));
    memset(M, 0, sizeof(M));
    fZF = fSF = fCF = fOF = fPF = fAF = fDF = 0;
    x87_cw = 0x037f; x87_sw = 0; mxcsr = 0x1f80;
    guest_stack[0] = 0;   /* touch */
}
void fle_init(void) {
    fle_install_teb();
    memset((void*)A_(FLE_ALOG), 0, 0x40000);
}
