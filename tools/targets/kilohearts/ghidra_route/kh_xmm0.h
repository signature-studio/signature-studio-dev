/* kh_xmm0.h — Stereo の callee の戻り xmm0 (縮約後の double) を機械語から確定した式で C 化する helper (KH-74・#3853)。
 * ghidra_to_c.py が stereo の出力 C に丸ごと入れる。呼出元の extraout_XMM0_Qa* は kh_xmm0_<va> を読む。
 * 式の根拠 (capstone 逆アセンブル): FUN_180fdc660 の ret は 180fdc6d6 の 1 本。xmm0 は 180fdc6c5 の vmovapd xmm0,xmm2 で
 * t2 = fma(-k, m2, t1)、t1 = fma(-k, m1, x)、k = fma(x, 2/pi, 1.5*2^52) - 1.5*2^52 (= xmm1)。
 * 数値突合は xmm0_check.c (native 実行と bit 一致)。 */
#include <math.h>
#include <stdint.h>

static double kh_xmm0_180fdc660;

static inline unsigned kh_fn_180fdc660(double x) {
    const double kM = 0x1.45f306dc9c883p-1, kK2 = 0x1.8000000000000p+52;
    const double kM1 = 0x1.921fb54442d18p+0, kM2 = 0x1.1a62633145c00p-54;
    double k = fma(x, kM, kK2) - kK2;
    double t1 = fma(-k, kM1, x);
    int32_t ki = (k > -2147483649.0 && k < 2147483648.0) ? (int32_t)k : INT32_MIN;
    kh_xmm0_180fdc660 = fma(-k, kM2, t1);
    return (unsigned)(ki & 3);
}
