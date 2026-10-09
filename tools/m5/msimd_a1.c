/* msimd_a1.c — (a1) function_6a7540 (waveshaper) 用 __asm_* 名実装。
 * RetDec l_ws.ll の declare に一致させる名前。 */
#include "msimd_core.h"

EMSCRIPTEN_KEEPALIVE u128 __asm_mulps(u128 a, u128 b) { return lane_op_ps(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_subps(u128 a, u128 b) { return lane_op_ps(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addps(u128 a, u128 b) { return lane_op_ps(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulss(u128 a, u128 b) { return lane_op_ss(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_subss(u128 a, u128 b) { return lane_op_ss(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addss(u128 a, u128 b) { return lane_op_ss(a, b, '+'); }
/* l_ws.ll: @__asm_movss(i128, i128)=blend, @__asm_movss__3(i32)=lane load
 * @__asm_movss__4(i128)=lane extract, @__asm_shufps(i128,i128,i8)=broadcast */
EMSCRIPTEN_KEEPALIVE u128 __asm_movss(u128 d, u128 s) { return lane_blend0(d, s); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movss__3(i32 v) {
    union { float f; int32_t i; } c; c.i = (int32_t)v;
    u128 r = 0; __builtin_memcpy(&r, &c.f, 4);   /* {v,0,0,0} */
    return r;
}
EMSCRIPTEN_KEEPALIVE i64  __asm_movss__4(u128 a) { return lane_to_i64_l0(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_shufps(u128 a, u128 b, int8_t imm) { return lane_broadcast0(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movups(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movaps(u128 a) { return a; }
/* store 型 (movups.2) は ir5_patch [S1a] で store 命令へ復元済 — 到達は fail-fast */
EMSCRIPTEN_KEEPALIVE void __asm_movups__2(u128 a, u128 b) {
    fprintf(stderr, "[msimd_a1] FAIL-FAST: movups.2 store が IR 復元されず到達\n");
    fflush(stderr); abort();
}
