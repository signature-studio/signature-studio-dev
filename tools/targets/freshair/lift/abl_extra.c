/* gain_ablate.sh 用: P1' 無効時に残る comisd/cvtps2pd/定数の最小定義 (no-op helper; 分岐は無いまま) */
#include "../ref/msimd6_core.h"
EMSCRIPTEN_KEEPALIVE void __asm_comisd(u128 a, u128 b) { (void)a; (void)b; }
EMSCRIPTEN_KEEPALIVE u128 __asm_cvtps2pd(u128 a) {
    float f0, f1; memcpy(&f0, &a, 4); memcpy((char*)&f1, (char*)&a + 4, 4);
    double d[2] = {f0, f1}; u128 r; memcpy(&r, d, 16); return r; }
EMSCRIPTEN_KEEPALIVE const u128 global_var_1810cac18 = ((u128)0x0000000000000000ULL << 64) | 0xBCD203AF9EE75616ULL;
