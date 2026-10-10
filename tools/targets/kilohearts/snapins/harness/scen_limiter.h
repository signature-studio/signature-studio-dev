/* Limiter (limiter::LimiterDsp) slot13 0x1804e8340 (prepare: dpow 0x180fc4590 (c) 関数) slot14 process 0x1804e8500
 *   slot15 reset 0x1804e7c90 (memset + vec push ×3)
 * self(0x4110): +0x60 f(rate div: samples/ms) +0x64 i(lookahead) +0x68 f(gain cur) +0x6c i(ring write idx, 1024)
 *   +0x70..0x1070 f[1024] ring L (入力×gain) +0x1070..0x2070 f[1024] ring R +0x2070..0x3070 f[1024] ring env
 *   +0x3070..0x4070 f[1024] ramp 表 +0x4080/0x4098/0x40b0: ramp{x: pos i, +4: inc f, +8: from f, +0xc: to f, +0x10: cur f, +0x14: u8 first}
 *   +0x40d4 f[2] release smooth gain +0x40e0 f(env follower) +0x40f0 f[2] gain smooth +0x40fc f(gain state) +0x4100 f(cur target)
 * ctx: +0x3188 P*{f thresh@0, f ceiling@4, f release@8, f attack@c, f out gain@10, f out max@14}
 *      +0x3198 Q*{u8 dirty@0x9c, @0xbc, @0xdc} +0x31b0 V*(通知 vector) +0x3180 i(id)
 * P+0x10/P+0x14 は process が書き戻す (出力パラメタ)。(c) 未到達 32 関数のうち 0x180fc4590 (5.8KB double pow) が
 * slot13 経由で到達 → 本チケットで lift (KH-4 §1 の (c) 解消の第 1 例) */
#include "scen_common.h"
#define LT_PROC 0x1804e8500UL
#define LT_S13  0x1804e8340UL
#define LT_S15  0x1804e7c90UL

#ifndef __EMSCRIPTEN__
/* UCRT matherr 既定 (delay と同一: 0x1813a1d38/d40/d48 の pre-terminator を差し替え)。
 * wasm 側は snapins.json shims の ret0 と同一意味。 */
u64 __attribute__((ms_abi)) lt_matherr_default(void) { return 0; }
static void lt_patch_crt(void) {
    static int done = 0;
    if (!done) {
        *(u64*)0x1813a1d38ULL = (u64)lt_matherr_default;
        *(u64*)0x1813a1d40ULL = (u64)lt_matherr_default;
        *(u64*)0x1813a1d48ULL = (u64)lt_matherr_default;
        done = 1;
    }
}
#endif
static void trial_limiter(int t) {
    (void)t;
#ifndef __EMSCRIPTEN__
    lt_patch_crt();
#endif
    u8* self = A(0x4110); u8* ctx = A(0x3200); u8* P = A(0x20); u8* Q = A(0x100); u8* V = A(0x80); int* vec = A(16 * 4);
    *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31b0) = V; *(int*)(ctx + 0x3180) = RI(0, 2000);
    REGION("self", self, 0x4110); REGION("P", P, 0x20); REGION("Q", Q, 0x100); REGION("V", V, 0x80); REGION("vec", vec, 64);
    *(float*)(self + 0x60) = RF(10, 200);
    *(int*)(self + 0x64) = RI(0, 300);
    *(int**)(V + 0x68) = vec + (R32() % 3); *(int**)(V + 0x70) = vec + 16;
    Q[0x9c] = R32() & 1; Q[0xbc] = R32() & 1; Q[0xdc] = R32() & 1;
    *(float*)(self + 0x68) = RFSPECIAL(0, 1);
    *(int*)(self + 0x6c) = RI(0, 1023);
    for (int o = 0x4080; o <= 0x40c4; o += 0x18) {           /* 3 本の ramp */
        int* pos = (int*)(self + o);
        pos[0] = RI(0, 100);
        *(float*)(self + o + 4) = RF(0, 0.1f);
        *(float*)(self + o + 8) = RFSPECIAL(0, 1);
        *(float*)(self + o + 0xc) = RFSPECIAL(0, 1);
        *(float*)(self + o + 0x10) = RF(0, 1);
        self[o + 0x14] = (R32() % 3) == 0;
    }
    *(float*)(self + 0x40d4) = RF(0.0005f, 0.5f); *(float*)(self + 0x40d8) = RF(0.0005f, 0.5f);
    *(float*)(self + 0x40e0) = RF(0, 1);
    *(float*)(self + 0x40f0) = RF(0.0005f, 0.5f); *(float*)(self + 0x40f4) = RF(0.0005f, 0.5f);
    *(float*)(self + 0x40fc) = RFSPECIAL(0, 1); *(float*)(self + 0x4100) = RFSPECIAL(0, 1);
    for (int i = 0; i < 1024; i++) {                          /* ring 初期値 (ネイティブと同一進行のため両側同じ) */
        *(float*)(self + 0x70 + i * 4) = RF(-1, 1);
        *(float*)(self + 0x1070 + i * 4) = RF(-1, 1);
        *(float*)(self + 0x2070 + i * 4) = RF(0, 2);
        *(float*)(self + 0x3070 + i * 4) = RF(0, 1);
    }
    int nb = 4 + (t % 4);
    for (int k = 0; k < nb; k++) {
        int op = R32() % 10;
        if (op == 0) { C2(LT_S15, RET_NONE, self, ctx); continue; }   /* reset は ctx+0x3188/0x3198 も触る (2 引数必須) */
        if (op == 1) { C3(LT_S13, RET_NONE, self, ctx, ctx); continue; }
        int n = pick_n();
        Buf b = mkbuf(0, 1.0f);
        refill(&b, n, 1.0f);
        REGION("buf", b.raw, 0x30);
        *(float*)P = RFSPECIAL(-1, 1); *(float*)(P + 4) = RFSPECIAL(0, 1);
        *(float*)(P + 8) = RF(0.001f, 2000); *(float*)(P + 0xc) = RF(0.01f, 500);
        *(float*)(P + 0x10) = RF(0, 1); *(float*)(P + 0x14) = RF(0, 1);
        C3(LT_PROC, RET_NONE, self, ctx, b.raw);
    }
}
