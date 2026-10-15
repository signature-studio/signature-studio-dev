/* x87_fn_glue.c: x87 を含む関数 (#2989) を wasm から呼ぶ入口。
 * x87 の状態 (ott_fst・ott_ftop) は ott_x87.h の static なので、lift 出力 (LIFT_C) と同じ翻訳単位に取り込んでから読む。
 * guest 値は VA そのまま (ia32 の lift は恒等写像)。 guest stack は VA 0x10F00000 に置く (rt32_glue.c と同じ)。
 * ビルド: emcc ... -DLIFT_C='"<ott_lifted.c の絶対パス>"' x87_fn_glue.c ott_cpu.c (tools/ott/rt) */
#include LIFT_C
#include <string.h>
uint64_t ott_gbase = 0x10000000ull;
#define GUEST_STACK_TOP 0x10F00000ull
static uint32_t g_st0, g_depth;
static uint64_t g_st0d;
uint32_t ott_call32x(uint32_t va, uint32_t ecx, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4, uint32_t a5) {
    uint32_t args[6] = {a0, a1, a2, a3, a4, a5};
    R[RSP] = GUEST_STACK_TOP;
    for (int i = 5; i >= 0; i--) { R[RSP] -= 4; ST32(R[RSP], args[i]); }
    R[RSP] -= 4; ST32(R[RSP], 0xdead0000u);
    R[RCX] = ecx; R[RAX] = 0; R[RDX] = 0;
    memset(ott_fst, 0, sizeof ott_fst);
    for (int p = 0; p < 8; p++) ott_tag[p] = 3;
    ott_ftop = 0; ott_fsw = 0; ott_fcw = 0x037f;
    ott_dispatch(va);
    g_depth = (8u - ott_ftop) & 7u;
    float f = g_depth ? (float)x87_st(0) : 0.0f;
    double d = g_depth ? x87_st(0) : 0.0;
    memcpy(&g_st0, &f, 4);
    memcpy(&g_st0d, &d, 8);
    return (uint32_t)R[RAX];
}
uint32_t ott_x87_st0(void) { return g_st0; }
uint32_t ott_x87_st0d_hi(void) { return (uint32_t)(g_st0d >> 32); }
uint32_t ott_x87_st0d_lo(void) { return (uint32_t)g_st0d; }
uint32_t ott_x87_depth(void) { return g_depth; }
