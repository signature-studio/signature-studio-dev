/* 3-Band EQ の libm 部品を単体で差分: 0x180fcd690 / 0x180fce0d0 (double→double, FMA3) / 0x180fcde58 (double→double) / 0x180fbc1f4 (float→float)
 * 引数は EQ が実際に与える範囲 (角周波数 rad, 10^(x) 指数) + 境界値 */
#include <math.h>
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

/* D14 (KH-2b): sincos_a / k_dfdb0 の大引数差分 (Payne-Hanek 経路 |x| ≥ 5e5)。
 * 引数は log 一様 [5e5, 1e9] + 境界・2冪・負数 + 中域 (π, 5e5) の補正経路。既存 qemath (0..π) の補完で別 scenario (判定行は既存行を変更しない)。 */
static void trial_qebig(int t) {
    (void)t;
    static const double sp[] = {5e5, 500000.5, 1e6, 1048576.0, 1e9, -5e5, -1e6, -1073741824.0, 6.25e8, 999999.5, 5.0000001e5, 1e8};
    for (int k = 0; k < 12; k++) {
        double a;
        if (k % 6 == 0) {
            a = sp[(t + k) % 12];
        } else if (k % 6 == 5) {
            a = 3.2 * pow(10.0, rd(0.0, 5.19));      /* 中域 (π, 5e5): cvttpd2dq 四分円 + Cody-Waite 補正経路 */
            if (k % 5 == 0) a = -a;
        } else {
            a = 5e5 * pow(10.0, rd(0.0, 1.30103));   /* log 一様 [5e5, 1e9] */
            if (k % 5 == 0) a = -a;
        }
        CD0(0x180fcd690UL, RET_F64, a);
        CD0(0x180fdfdb0UL, RET_F64, a);
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
