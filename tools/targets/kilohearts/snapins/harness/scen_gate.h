/* Gate (gate::GateDsp)  slot14 process 0x1804c2f50   callee: lookahead 0x180295f20 -> 0x180020e70 -> (memmove 0x181384040 / memset 0x1813846e0 は C shim)
 * self(0x360): +0x68 i32 size +0x70 ptr +0x78 maxcnt +0x7c mask +0x80 idx +0x84 count (ring1) / +0x90.. (ring2: +0x98 ptr +0xa0 +0xa4 +0xa8 +0xac)
 *   +0xb0..+0xc0 + first@0xc4: param ramp (P[5])  +0xd4[2] +0xe0: エンベロープ係数/状態  +0xf0[2] +0xfc: 2段目  +0x100: lookahead delay obj x2 (+0x20 間隔),
 *   +0x140/+0x240: lookahead 出力 buf (各 64 float) +0x340 f(sr) +0x344 f +0x348 f +0x34c u8 +0x350 f
 * ctx: +0x3150 -> X{u32 @0x24 maxLook}  +0x3180 id  +0x3188 P  +0x3198 Q  +0x31a8 -> aux table (stride 0x18, [P.i@0x30] -> info{i32 @0x40 = aux idx(<0: 無し)})
 *      +0x31b0 V (通知 vector)    P: f[0..5], u8 @0x1c, f @0x20..0x28, i32 @0x2c, i32 @0x30
 * AudioBuffer: +0x18 -> aux array (stride 0x18: ch0*,ch1*, i32 @0x14 latency, u8 @0x10) */
#include "scen_common.h"
#define GT_PROC 0x1804c2f50UL
#define GT_LOOK 0x180295f20UL
#define GT_DLY 0x180020e70UL
static void init_dly(u8* o, int S, float* ring) {
    int x = RI(0, 3);
    ((int*)o)[0] = x; ((int*)o)[1] = S; ((int*)o)[2] = RI(0, S - 2 * x - 1); ((int*)o)[3] = RI(0, S - 1); ((int*)o)[4] = RI(0, 3 * S); ((int*)o)[5] = RI(0, 40);
    *(float**)(o + 0x18) = ring;
    for (int i = 0; i < S + 4; i++) ring[i] = RF(-1, 1);
}
static void trial_gate(int t) {
    u8* self = A(0x360); u8* ctx = A(0x3200); u8* P = A(0x40); u8* Q = A(0x200); u8* V = A(0x80); int* vec = A(16 * 4);
    u8* X = A(0x40); u8* tab = A(0x18 * 4); u8* info = A(0x80); u8* aux = A(0x18 * 2);
    *(void**)(ctx + 0x3150) = X; *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31a8) = tab; *(void**)(ctx + 0x31b0) = V;
    *(int*)(ctx + 0x3180) = RI(0, 2000);
    *(void**)(tab + 0x18 * 1) = info;                                     /* P.i = 1 */
    *(u32*)(X + 0x24) = RI(0, 300);
    REGION("self", self, 0x360); REGION("P", P, 0x40); REGION("Q", Q, 0x200); REGION("V", V, 0x80); REGION("vec", vec, 64); REGION("aux", aux, 0x30); REGION("info", info, 0x80);
    int cap1 = 1 << RI(6, 10), cap2 = 1 << RI(6, 10);
    float* r1 = A((size_t)(cap1 + 8) * 4); float* r2 = A((size_t)(cap2 + 8) * 4);
    REGION("ring1", r1, (cap1 + 8) * 4); REGION("ring2", r2, (cap2 + 8) * 4);
    for (int i = 0; i < cap1 + 4; i++) r1[i] = RF(-1, 1);
    for (int i = 0; i < cap2 + 4; i++) r2[i] = RF(-1, 1);
    *(int*)(self + 0x68) = cap1; *(void**)(self + 0x70) = r1; *(u32*)(self + 0x78) = cap1 - RI(0, 8); *(u32*)(self + 0x7c) = cap1 - 1; *(u32*)(self + 0x80) = R32() & (cap1 - 1); *(u32*)(self + 0x84) = RI(0, cap1 - 8);
    *(int*)(self + 0x90) = cap2; *(void**)(self + 0x98) = r2; *(u32*)(self + 0xa0) = cap2 - RI(0, 8); *(u32*)(self + 0xa4) = cap2 - 1; *(u32*)(self + 0xa8) = R32() & (cap2 - 1); *(u32*)(self + 0xac) = RI(0, cap2 - 8);
    self[0xc4] = (t % 4) == 0;
    for (int k = 0; k < 5; k++) *(float*)(self + 0xb0 + 4 * k) = RF(0, 1);
    *(float*)(self + 0xb4) = RF(0, 0.05f);
    *(float*)(self + 0xd4) = RF(0.001f, 0.5f); *(float*)(self + 0xd8) = RF(0.0001f, 0.2f); *(float*)(self + 0xe0) = RF(0, 1);
    *(float*)(self + 0xf0) = RF(0.001f, 0.5f); *(float*)(self + 0xf4) = RF(0.0001f, 0.2f); *(float*)(self + 0xfc) = RF(0, 1);
    *(float*)(self + 0x340) = (R32() & 1) ? 44100.0f : 48000.0f; *(float*)(self + 0x344) = RF(0, 1); *(float*)(self + 0x348) = RF(0, 0.5f); self[0x34c] = R32() & 1; *(float*)(self + 0x350) = RF(0, 0.3f);
    int sidechain = (t % 2) == 1;
    u8* d1 = self + 0x100; u8* d2 = self + 0x120;
    float* lr1 = A(2100 * 4); float* lr2 = A(2100 * 4);
    REGION("lring1", lr1, 2100 * 4); REGION("lring2", lr2, 2100 * 4);
    init_dly(d1, RI(300, 2000), lr1); init_dly(d2, RI(300, 2000), lr2);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    float* sL = A((BUFCAP + 4) * 4); float* sR = A((BUFCAP + 4) * 4); REGION("sideL", sL, (BUFCAP + 4) * 4); REGION("sideR", sR, (BUFCAP + 4) * 4);
    *(void**)(b.raw + 0x18) = aux; *(float**)(aux + 0) = sL; *(float**)(aux + 8) = sR;
    *(int*)(P + 0x30) = 1; *(int*)(info + 0x40) = sidechain ? 0 : -1;
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n(); if (sidechain && n > 64) n = 64;
        float* p = (float*)P;
        p[0] = RFSPECIAL(0.0f, 0.2f); p[1] = RF(0, 0.5f); p[2] = RFSPECIAL(0.0f, 0.5f); p[3] = RF(0.2f, 3); p[4] = RF(0, 1);
        p[5] = (R32() % 4 == 0) ? *(float*)(self + 0xbc) : RFSPECIAL(0, 1);
        P[0x1c] = R32() & 1;
        *(float*)(P + 0x20) = RF(0, 1); *(float*)(P + 0x24) = RF(0, 1); *(float*)(P + 0x28) = RF(0, 1);
        *(int*)(P + 0x2c) = RI(0, 240);
        *(int*)(aux + 0x14) = RI(0, 60); aux[0x10] = R32() & 1;
        Q[0x13c] = R32() & 1; Q[0x11c] = R32() & 1; Q[0x15c] = R32() & 1;
        *(int**)(V + 0x68) = vec + (R32() % 3); *(int**)(V + 0x70) = vec + 16;
        refill(&b, n, (R32() & 1) ? 0.3f : 1.0f);
        for (int i = 0; i < n; i++) { sL[i] = RF(-1, 1); sR[i] = RF(-1, 1); }
        C3(GT_PROC, RET_NONE, self, ctx, b.raw);
    }
}
