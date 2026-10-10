/* Gain (gain::GainDsp) slot14=process 0x1804b0380。 PoC (poc_gain/native_ref.c) の layout を ctx-fuzz に汎化。
 * self(0xB0): +0x64 pos +0x68 inc +0x6c a +0x70 b +0x74 cur +0x78 first(u8) +0x84/+0x94 meter係数 +0x88/+0x98 meter
 * ctx: +0x3180 id, +0x3188 P*{int mode; float v; float meterL, meterR}, +0x3198 Q*{float q28@0x28; u8 dirtyL@0x5c, dirtyR@0x7c},
 *      +0x31b0 V*{+0x68 end, +0x70 cap} (変更通知 vector<int>。realloc 経路 0x18004cf20 は未 lift なので常に空き有り or 両 dirty=1) */
#include "scen_common.h"
#define GN_PROC 0x1804b0380UL
static void trial_gain(int t) {
    u8* self = A(0xB0); u8* ctx = A(0x3200); u8* P = A(16); u8* Q = A(0x80); u8* V = A(0x80); int* vec = A(16 * 4);
    *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31b0) = V; *(int*)(ctx + 0x3180) = RI(0, 2000);
    REGION("self", self, 0xB0); REGION("P", P, 16); REGION("Q", Q, 0x80); REGION("V", V, 0x80); REGION("vec", vec, 64);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    self[0x78] = (t % 3) == 0;
    *(float*)(self + 0x84) = RF(0.0005f, 0.5f); *(float*)(self + 0x94) = RF(0.0005f, 0.5f);
    *(float*)(self + 0x88) = RF(0, 1); *(float*)(self + 0x98) = RF(0, 1);
    *(float*)(self + 0x74) = *(float*)(self + 0x70) = *(float*)(self + 0x6c) = RFSPECIAL(0, 3);
    *(float*)(self + 0x64) = RF(0, 50); *(float*)(self + 0x68) = RF(0, 0.05f);
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n();
        *(int*)P = (R32() % 3 == 0) ? 1 : (int)(R32() % 2) * 2;       /* mode 0/1/2 (1 → 2*q28 経路) */
        float cur = *(float*)(self + 0x70);
        int r = R32() % 5;
        *(float*)(P + 4) = (r == 0) ? cur : (r == 1) ? cur + 1e-7f : RFSPECIAL(-4, 4);
        *(float*)(Q + 0x28) = RFSPECIAL(-4, 4);
        Q[0x5c] = R32() & 1; Q[0x7c] = R32() & 1;
        *(float*)(P + 8) = RF(0, 1); *(float*)(P + 12) = RF(0, 1);
        *(int**)(V + 0x68) = vec + (R32() % 3); *(int**)(V + 0x70) = vec + 16;
        refill(&b, n, 1.0f);
        C3(GN_PROC, RET_NONE, self, ctx, b.raw);
    }
}
