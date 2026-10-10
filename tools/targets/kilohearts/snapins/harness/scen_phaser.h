/* Phaser (phaser::PhaserDsp) slot13 0x180727060 (n 変化時に ramp 再計算: (1-f70)^n = dpow) slot14 process 0x1807270d0
 *   slot15 reset 0x180726fa0
 * self(0x1420): +0x60 f(rate divisor) +0x64 i(ramp pos) +0x68 f(inc) +0x6c f(from) +0x70 f(to) +0x74 f(cur) +0x78 u8 first
 *   +0x80..0x400: biquad 状態 7 band × 0x80 = {+0x00 f64x2 x, +0x10 f64x2 y, +0x20..0x60 f64x2 coef×5, +0x70 u8 dirty}
 *   +0x400 f(LFO phase) +0x410..: staging n×16B (f64x2)
 * ctx: +0x3188 P*{i32 bands@0, f depth@8, f rate@c, f center@10, f spread@14}, +0x3198 Q*{f offset@0x28}
 * 新規 lift: expf (0x180fb6830, 表 base 0x182286320 を and 0x3f ×8 = 512B 窓) + UCRT helper 0x180fd4e88 + floorf 0x180fc67f0 */
#include "scen_common.h"
#define PH_PROC 0x1807270d0UL
#define PH_S13  0x180727060UL
#define PH_S15  0x180726fa0UL
static void trial_phaser(int t) {
    u8* self = A(0x1420); u8* ctx = A(0x3200); u8* P = A(0x20); u8* Q = A(0x40);
    *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q;
    REGION("self", self, 0x1420); REGION("P", P, 0x20); REGION("Q", Q, 0x40);
    *(float*)(self + 0x60) = RF(1, 48000);
    self[0x78] = (t % 3) == 0;
    *(float*)(self + 0x400) = RF(0, 4);
    for (int d = 0; d < 7; d++) {
        u8* b = self + 0x80 + d * 0x80;
        b[0x70] = (R32() % 4 != 0);                      /* dirty: たまに既存 coef 経路 */
        *(double*)(b + 0x00) = RF(-2, 2); *(double*)(b + 0x08) = RF(-2, 2);
        *(double*)(b + 0x10) = RF(-2, 2); *(double*)(b + 0x18) = RF(-2, 2);
        for (int k = 0x20; k <= 0x68; k += 8) *(double*)(b + k) = RF(-1.5, 1.5);
    }
    *(float*)(self + 0x6c) = RFSPECIAL(0, 1); *(float*)(self + 0x70) = RFSPECIAL(0, 1);
    *(float*)(self + 0x74) = RF(0, 1); *(int*)(self + 0x64) = RI(0, 100);
    *(float*)(self + 0x68) = RF(0, 0.1f);
    int nb = 4 + (t % 4);
    for (int k = 0; k < nb; k++) {
        int op = R32() % 12;
        if (op == 0) { C3(PH_S15, RET_NONE, self, ctx, ctx); continue; }
        int n = pick_n();
        Buf b = mkbuf(0, 1.0f);
        refill(&b, n, 1.0f);
        *(int*)P = (R32() % 5 == 0) ? 8 : (int)(R32() % 8);   /* bands 0..7 (8 = 全 band 処理, <8 は残り reset 経路) */
        float cur = *(float*)(self + 0x70);
        int r = R32() % 5;
        *(float*)(P + 0x14) = (r == 0) ? cur : (r == 1) ? cur + 1e-7f : RFSPECIAL(0, 1);
        *(float*)(P + 8) = RF(0, 1); *(float*)(P + 0xc) = RF(0, 1); *(float*)(P + 0x10) = RF(0, 1);
        *(float*)(Q + 0x28) = RFSPECIAL(-4, 4);
        REGION("buf", b.raw, 0x30);
        if (op == 1) { C3(PH_S13, RET_NONE, self, ctx, b.raw); continue; }
        C3(PH_PROC, RET_NONE, self, ctx, b.raw);
    }
}
