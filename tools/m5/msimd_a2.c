/* msimd_a2.c — (a2) function_6a2fb0 (distortion, (x-g)^2*x^2) 用名実装。
 * l_a2.ll の declare に一致: movss(i32)=lane load, movss.3(i128,i128)=blend,
 * movss.4(i128)=extract, movdqa(i128)=? (i64) — RetDec の spill 表現。 */
#include "msimd_core.h"

EMSCRIPTEN_KEEPALIVE u128 __asm_mulps(u128 a, u128 b) { return lane_op_ps(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_subps(u128 a, u128 b) { return lane_op_ps(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addps(u128 a, u128 b) { return lane_op_ps(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulss(u128 a, u128 b) { return lane_op_ss(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_subss(u128 a, u128 b) { return lane_op_ss(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addss(u128 a, u128 b) { return lane_op_ss(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_xorps(u128 a, u128 b) {
    v4f f; __builtin_memcpy(&f, &a, 16);
    f = (v4f){0.f, 0.f, 0.f, 0.f};
    u128 r; __builtin_memcpy(&r, &f, 16); return r;
}
EMSCRIPTEN_KEEPALIVE u128 __asm_movss(i32 v) {
    union { float f; int32_t i; } c; c.i = (int32_t)v;
    u128 r = 0; __builtin_memcpy(&r, &c.f, 4);
    return r;
}
EMSCRIPTEN_KEEPALIVE u128 __asm_movss__3(u128 d, u128 s) { return lane_blend0(d, s); }
EMSCRIPTEN_KEEPALIVE i64  __asm_movss__4(u128 a) { return lane_to_i64_l0(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movups(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movaps(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movdqu(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movdqa__5(u128 a) { return a; }
/* nil: movdqa(i128)→i64 は RetDec spill 表現 (結果は大きく再利用されない)。
 * 対応として lane0 抽出を返す。 */
EMSCRIPTEN_KEEPALIVE i64 __asm_movdqa(u128 a) { return lane_to_i64_l0(a); }
EMSCRIPTEN_KEEPALIVE void __asm_movups__2(u128 a, u128 b) {
    fprintf(stderr, "[msimd_a2] FAIL-FAST: movups.2 store が IR 復元されず到達\n");
    fflush(stderr); abort();
}
