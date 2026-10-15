/* rt32_glue.c: ia32 lift (x64c --arch ia32) を wasm から呼ぶ入口 (#1223)。
 * guest 値は VA そのまま (ia32 の lift は恒等写像)。 guest stack は VA 0x10F00000 (image の上の余白) に置く。 */
#include "ott_cpu.h"
uint64_t ott_gbase = 0x10000000ull;
#define GUEST_STACK_TOP 0x10F00000ull
uint32_t ott_call32(uint32_t va, uint32_t ecx, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3) {
    uint32_t args[4] = {a0, a1, a2, a3};
    R[RSP] = GUEST_STACK_TOP;
    for (int i = 3; i >= 0; i--) { R[RSP] -= 4; ST32(R[RSP], args[i]); }
    R[RSP] -= 4; ST32(R[RSP], 0xdead0000u);
    R[RCX] = ecx; R[RAX] = 0; R[RDX] = 0;   /* native 側 (native_entry.c) と同じ呼出し前の eax/edx = 0 */
    ott_dispatch(va);
    return (uint32_t)R[RAX];
}
