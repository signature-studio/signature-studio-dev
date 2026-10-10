/* Channel Mixer (matrix::MatrixDsp)  slot15=reset 0x1804f4180  slot7=setX(float) 0x1804f4190  slot14=process 0x1804f41a0
 * self: +0x60 float[4] 現係数, +0x70 u8 first, +0x74 float(slot7)。 ctx+0x3188 -> P: float[4] (L->L, R->L, L->R, R->R 相当) */
#include "scen_common.h"
#define MX_RESET 0x1804f4180UL
#define MX_SET7 0x1804f4190UL
#define MX_PROC 0x1804f41a0UL
static void trial_matrix(int t) {
    u8* self = A(0x80); u8* ctx = A(0x3200); float* P = A(16);
    *(void**)(ctx + 0x3188) = P;
    REGION("self", self, 0x80); REGION("P", P, 16);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    int mode = t % 4;
    if (mode == 0 || mode == 3) C1(MX_RESET, RET_NONE, self);
    else { for (int i = 0; i < 4; i++) ((float*)(self + 0x60))[i] = RFSPECIAL(-2, 2); self[0x70] = R32() & 1; }
    if (mode == 3) C1F(MX_SET7, RET_NONE, self, RF(8000, 96000));
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n();
        float* cur = (float*)(self + 0x60);
        for (int i = 0; i < 4; i++) {
            int r = R32() % 6;
            P[i] = (r == 0) ? cur[i] : (r == 1) ? (k ? P[i] : 1.0f) : RFSPECIAL(-2, 2);   /* 一部は変化なし → straight 経路 */
        }
        refill(&b, n, 1.0f);
        C3(MX_PROC, RET_NONE, self, ctx, b.raw);
    }
}
