/* 3-Band EQ (quickeq::QuickEqDsp)  slot14 process 0x18035fb10 (+ 設計 0x180362700/0x180bac490 + libm 0x180fcd690/0x180fce0d0/0x180fbc1f4 ...)
 * self(0x120): +0x60 double[4] 状態 band1(L,R 各 2) +0x80 double[5] 係数(補間) +0xa8 u8 first1
 *   +0xb0 double[4] 状態 band2 +0xd0 double[5] 係数 +0xf8 u8 first2 +0x100 float sr +0x108 -> meter buf (+0x28 float[])
 * ctx+0x3188 -> P{float gLow, gMid, gHigh (dB), f1, f2 (Hz)}  n<=64 (process 内ローカル配列 ~74 sample) */
#include "scen_common.h"
#define QE_PROC 0x18035fb10UL
static void trial_quickeq(int t) {
    u8* self = A(0x120); u8* ctx = A(0x3200); float* P = A(32); u8* meter = A(0x800);
    *(void**)(ctx + 0x3188) = P; *(void**)(self + 0x108) = meter;
    REGION("self", self, 0x120); REGION("P", P, 32); REGION("meter", meter, 0x800);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    for (int o = 0x60; o < 0x80; o += 8) *(double*)(self + o) = RF(-0.3f, 0.3f);
    for (int o = 0xb0; o < 0xd0; o += 8) *(double*)(self + o) = RF(-0.3f, 0.3f);
    double c0[5] = {1.0, -1.9, 0.9, -1.8, 0.85};
    for (int k = 0; k < 5; k++) { *(double*)(self + 0x80 + 8 * k) = c0[k] * RF(0.5f, 1.5f); *(double*)(self + 0xd0 + 8 * k) = c0[k] * RF(0.5f, 1.5f); }
    self[0xa8] = (t % 3) == 0; self[0xf8] = (t % 3) == 0;
    *(float*)(self + 0x100) = (R32() & 1) ? 44100.0f : 48000.0f;
    for (int i = 0; i < 0x100; i++) ((float*)(meter + 0x28))[i] = RF(0, 1);
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n(); if (n > 64) n = 64;
        P[0] = RFSPECIAL(-24, 24); P[1] = RFSPECIAL(-24, 24); P[2] = RFSPECIAL(-24, 24);
        P[3] = RF(40, 2000); P[4] = RF(2500, 18000);
        if (R32() % 5 == 0 && k) { /* 係数が変わらない経路 (ramp 傾き 0) の再現 */ }
        refill(&b, n, 1.0f);
        C3(QE_PROC, RET_NONE, self, ctx, b.raw);
    }
}
