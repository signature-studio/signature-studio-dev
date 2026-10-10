/* ott_ovr.c: lifter が機械語 body の代わりに呼ぶ C 実装 (override)。ABI は lifted code と同じ (R/X 状態, 末尾で ret 相当 R[RSP]+=8)。
 * 目的: DLL の CRT が「未初期化」(DllMain 未実行) だと動かない数学エラー報告経路 (UCRT _handle_error) を,
 *       実 CRT の観測可能な意味 (= 呼出側が渡した戻り値 retval を返す) だけに置換する。
 * 検証: native 参照は同経路で CRT 未初期化のため SIGSEGV する (diff/zero_params 参照) ので, UCRT の仕様から導出 (1801c8c00 の dsm: xmm0 ← xmm6 ← 入力 xmm1)。 */
#include "ott_cpu.h"
#define RET() (R[RSP] += 8)
/* 1801c8c00 _handle_error(double): 返り値 = xmm1 (retval) */
void ovr_handle_error_d(void) { X[0].q[0] = X[1].q[0]; RET(); }
/* 1801c8cb8 _handle_errorf(float): 返り値 = xmm1.f32 */
void ovr_handle_error_f(void) { X[0].d[0] = X[1].d[0]; RET(); }
/* 1801a9a6c sqrt(double) CRT wrapper: x<0 → -nan(ind), NaN 伝播, それ以外 sqrt */
void ovr_sqrt_d(void) {
    double x = X[0].df[0];
    if (x != x) { /* NaN: quiet して返す */ X[0].q[0] |= 0x0008000000000000ull; }
    else if (x < 0) X[0].q[0] = 0xfff8000000000000ull;
    else X[0].df[0] = sqrt(x);
    RET();
}
/* 1801a9b38 sqrtf wrapper */
void ovr_sqrt_f(void) {
    float x = X[0].f[0];
    if (x != x) X[0].d[0] |= 0x00400000u;
    else if (x < 0) X[0].d[0] = 0xffc00000u;
    else X[0].f[0] = sqrtf(x);
    RET();
}
