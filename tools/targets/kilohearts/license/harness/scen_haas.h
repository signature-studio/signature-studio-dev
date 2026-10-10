/* Haas (haas::HaasDsp)  slot13 0x1804d0180 (無音ブロック: リングへ 0 を n 個書く)  slot14 process 0x1804d0280
 *   slot15 reset 0x1804cff00  slot17 0x1804cff90 (flags 再初期化)  slot19 0x1804d0720 (latency = (int)(self.f60*P.f4)+0x40)
 * self(0x108): +0x60 f(samples/ms 係数) +0x64 u8 first +0x68..0x78 遅延量 ramp(a,tgt,cur,pos) +0x78 f(ramp 時間係数)
 *   +0x7c..0x8c gain-A ramp, +0x90 u8 firstA, +0x94..0xa4 gain-B ramp, +0xa8 u8 firstB,
 *   ring1: +0xb4 f scale, +0xb8 i size, +0xc0 ptr, +0xc8 u maxCount, +0xcc u mask, +0xd0 u idx, +0xd4 u count
 *   ring2: +0xdc f scale, +0xe0 i size, +0xe8 ptr, +0xf0 u maxCount, +0xf4 u mask, +0xf8 u idx, +0xfc u count
 * ctx+0x3188 -> P{u8 flags@0 (bit0), float delay@4} */
#include "scen_common.h"
#define HS_S13 0x1804d0180UL
#define HS_PROC 0x1804d0280UL
#define HS_RESET 0x1804cff00UL
#define HS_S17 0x1804cff90UL
#define HS_LAT 0x1804d0720UL
static void trial_haas(int t) {
    u8* self = A(0x110); u8* ctx = A(0x3200); u8* P = A(16);
    *(void**)(ctx + 0x3188) = P;
    REGION("self", self, 0x110); REGION("P", P, 16);
    int cap1 = 1 << RI(6, 10), cap2 = 1 << RI(6, 10);
    float* r1 = A((size_t)(cap1 + 8) * 4); float* r2 = A((size_t)(cap2 + 8) * 4);
    REGION("ring1", r1, (cap1 + 8) * 4); REGION("ring2", r2, (cap2 + 8) * 4);
    for (int i = 0; i < cap1 + 4; i++) r1[i] = RF(-1, 1);
    for (int i = 0; i < cap2 + 4; i++) r2[i] = RF(-1, 1);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    *(float*)(self + 0x60) = RF(10, 200); *(float*)(self + 0x78) = RF(0.02f, 3);
    self[0x64] = (t % 3) == 0; self[0x90] = R32() & 1; self[0xa8] = R32() & 1;
    *(float*)(self + 0x68) = RF(0, 1); *(float*)(self + 0x6c) = RF(0, 1); *(float*)(self + 0x70) = RF(0, 1); *(float*)(self + 0x74) = RF(0, 1.3f);
    for (int o = 0x7c; o <= 0x8c; o += 4) *(float*)(self + o) = RF(0, 1);
    for (int o = 0x94; o <= 0xa4; o += 4) *(float*)(self + o) = RF(0, 1);
    *(float*)(self + 0x80) = RF(0, 0.05f); *(float*)(self + 0x98) = RF(0, 0.05f);
    *(float*)(self + 0xb4) = RF(0.5f, 60); *(float*)(self + 0xdc) = RF(0.5f, 60);
    *(int*)(self + 0xb8) = cap1; *(void**)(self + 0xc0) = r1; *(u32*)(self + 0xc8) = cap1 - RI(0, 8); *(u32*)(self + 0xcc) = cap1 - 1;
    *(u32*)(self + 0xd0) = R32() & (cap1 - 1); *(u32*)(self + 0xd4) = RI(0, cap1 - 8);
    *(int*)(self + 0xe0) = cap2; *(void**)(self + 0xe8) = r2; *(u32*)(self + 0xf0) = cap2 - RI(0, 8); *(u32*)(self + 0xf4) = cap2 - 1;
    *(u32*)(self + 0xf8) = R32() & (cap2 - 1); *(u32*)(self + 0xfc) = RI(0, cap2 - 8);
    int nb = 4 + (t % 4);
    for (int k = 0; k < nb; k++) {
        int op = R32() % 10;
        if (op == 0) { C1(HS_RESET, RET_NONE, self); continue; }
        if (op == 1) { C1(HS_S17, RET_NONE, self); continue; }
        if (op == 2) { *(float*)(P + 4) = RF(0, 80); C2(HS_LAT, RET_I32, self, ctx); continue; }
        int n = pick_n();
        P[0] = (u8)(R32() & 1);
        float cur = *(float*)(self + 0x6c);
        int r = R32() % 5;
        *(float*)(P + 4) = (r == 0) ? cur : (r == 1) ? cur + 1e-9f : RFSPECIAL(0, 80);
        refill(&b, n, 1.0f);
        if (op == 3) { C3(HS_S13, RET_NONE, self, ctx, b.raw); continue; }
        C3(HS_PROC, RET_NONE, self, ctx, b.raw);
    }
}
