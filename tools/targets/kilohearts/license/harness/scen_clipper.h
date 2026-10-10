/* Clipper (clipper::ClipperDsp)  slot14 process 0x180884b30  slot15 reset 0x180884b10  callee peak-hold 0x180884790(this+0xc0, idx, f2, f3)
 * self(0xD0): 4 本の param ramp {pos,inc,a,tgt,cur,...}: ramp0 +0x60..0x70 (first@0x74) ramp1 +0x78..0x88 (first@0x8c)
 *   ramp2 +0x90..0xa0 (first@0xa4) ramp3 +0xa8..0xb8 (first@0xbc);  +0xc0 -> meter{ +0x28 peakIn[], +0x128 peakOut[] }
 * ctx+0x3188 -> P{float t0,t1,t2,t3}  buf = AudioBuffer。 soft-knee 区分関数 (ucomiss/ja/jbe の入れ子) を 3 領域とも踏むよう振幅を振る */
#include "scen_common.h"
#define CL_PROC 0x180884b30UL
#define CL_RESET 0x180884b10UL
#define CL_PEAK 0x180884790UL
static void trial_clipper(int t) {
    u8* self = A(0xD0); u8* ctx = A(0x3200); float* P = A(16); u8* meter = A(0x800);
    *(void**)(ctx + 0x3188) = P; *(void**)(self + 0xc0) = meter;
    REGION("self", self, 0xD0); REGION("P", P, 16); REGION("meter", meter, 0x800);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    static const int base[4] = {0x60, 0x78, 0x90, 0xa8};
    static const int firstoff[4] = {0x74, 0x8c, 0xa4, 0xbc};
    for (int r = 0; r < 4; r++) {
        for (int k = 0; k < 6; k++) *(float*)(self + base[r] + 4 * k) = RF(0, 1);
        *(float*)(self + base[r] + 4) = RF(0, 0.05f);
        self[firstoff[r]] = (t % 3) == 0;
    }
    for (int i = 0; i < 0x100; i++) ((float*)(meter + 0x28))[i] = RF(0, 1);
    int nb = 4 + (t % 4);
    for (int k = 0; k < nb; k++) {
        int op = R32() % 12;
        if (op == 0) { C1(CL_RESET, RET_NONE, self); continue; }
        if (op == 1) { do_call(CL_PEAK, RET_NONE, (u64)meter, RI(0, 63), 0, 0, 0, 0, fbits(RF(0, 2)), fbits(RF(0, 2)), 0, 0, 0, 0); continue; }
        int n = pick_n(); if (n > 64) n = 64;
        float lo[4] = {0.2f, 0.05f, 0.5f, 0.5f}, hi[4] = {1.5f, 1.0f, 2.0f, 2.0f};
        for (int r = 0; r < 4; r++) {
            float cur = *(float*)(self + base[r] + 0xc);
            int q = R32() % 5;
            P[r] = (q == 0) ? cur : RFSPECIAL(lo[r], hi[r]);
            if (P[r] < lo[r]) P[r] = lo[r];
        }
        refill(&b, n, (R32() & 1) ? 0.4f : 2.5f);          /* 小振幅 (線形域) / 大振幅 (knee・飽和域) */
        C3(CL_PROC, RET_NONE, self, ctx, b.raw);
    }
}
