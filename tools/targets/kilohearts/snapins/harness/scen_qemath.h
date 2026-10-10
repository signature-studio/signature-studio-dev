/* 3-Band EQ の libm 部品を単体で差分: 0x180fcd690 / 0x180fce0d0 (double→double, FMA3) / 0x180fcde58 (double→double) / 0x180fbc1f4 (float→float)
 * 引数は EQ が実際に与える範囲 (角周波数 rad, 10^(x) 指数) + 境界値 */
#include "scen_common.h"
static double rd(double lo, double hi) { return lo + (hi - lo) * ((R32() >> 8) / 16777216.0); }
static void trial_qemath(int t) {
    (void)t;
    for (int k = 0; k < 24; k++) {
        double a = (k % 6 == 0) ? 0.0 : (k % 6 == 1) ? 3.141592653589793 : rd(0, 3.1415926);
        CD0(0x180fcd690UL, RET_F64, a);
        CD0(0x180fce0d0UL, RET_F64, a);
        double e = rd(-2.5, 2.5);
        CD0(0x180fcde58UL, RET_F64, e);
        CF0(0x180fbc1f4UL, RET_F32, (float)rd(-12, 12));
    }
}

/* CRT 分類器 _dtest (0x180fbde90, rcx=double*) / _dscale 系を単体差分 */
static void trial_qeclass(int t) {
    (void)t;
    double* x = A(16); REGION("x", x, 16);
    double vals[] = {0.0, -0.0, 1.0, -1.5, 3.25, 1e-310, -1e-310, 1e300, 0.5, 123456.789};
    for (int k = 0; k < 20; k++) {
        double v = (k < 10) ? vals[k] : rd(-100, 100);
        *x = v;
        C1(0x180fbde90UL, RET_I32, x);
    }
}

static void trial_qeclass2(int t) {
    (void)t;
    for (int k = 0; k < 12; k++) CD0(0x180fd27a8UL, RET_I32, (k == 0) ? 0.0 : rd(-3, 3));
}
