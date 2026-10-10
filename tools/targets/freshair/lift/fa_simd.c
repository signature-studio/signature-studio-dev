/* fa_simd.c — gain::GainDsp::process lift (gain_fixed.ll) が参照する __asm_* helper.
 * signature は IR の declare 通り (RetDec の per-binary suffix: __1/__2/__3 は別バイナリと
 * 意味が一致しない → gen_msimd6.py の suffix 名キーは流用不可、base名+型で再定義)。
 * 意味は x86 SSE scalar の lane0 演算 (上位 lane は dst 保持)。msimd6_core.h を参照コピーして使用。 */
#include "../ref/msimd6_core.h"

EMSCRIPTEN_KEEPALIVE u128 __asm_movss(u32 a)            { return set_u32_lo(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movd(u32 a)             { return set_u32_lo(a); }
EMSCRIPTEN_KEEPALIVE u128 __asm_movaps(u128 a)          { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_xorps(u128 a, u128 b)   { return a ^ b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_addss(u128 a, u128 b)   { return _laneop32(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_subss(u128 a, u128 b)   { return _laneop32(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_divss(u128 a, u128 b)   { return _laneop32(a, b, '/'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulss(u128 a, u32 b)    { return _laneop32c(a, asf(b), '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulss__2(u128 a, u128 b){ return _laneop32(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u64  __asm_movss__1(u128 a)        { return (u64)(u32)a; }
EMSCRIPTEN_KEEPALIVE u64  __asm_movaps__3(u128 a)       { return (u64)a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtdq2ps(u128 a) {
    v4i i; v4f f; memcpy(&i, &a, 16);
    f = __builtin_convertvector(i, v4f);
    u128 r; memcpy(&r, &f, 16); return r;
}
