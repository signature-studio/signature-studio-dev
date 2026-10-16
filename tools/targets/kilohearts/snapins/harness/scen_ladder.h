/* Ladder (ladder::LadderDsp)  slot14 process 0x1804d9930 (args: this=rcx, ctx=rdx, buf=r8)
 *   slot15 0x1804d9820 (init: this+0x70 のサブオブジェクトを 0x180b824d0 で構築) /
 *   slot20 0x1804d9ba0 (block DSP) は this の vtable から間接 call する。
 *   vtable 配置は REPORT_APPENDIX_780 §3d の census 結果に従う (self+0 = vtable)。
 * self: +0x60 f32 (係数)  +0x528/+0x52c i32 (state, 0..2)  +0x5d8 ptr (callback, 0 で無効)
 *   サブオブジェクト +0x70 は slot15 が構築する。ここへランダム値を書いてはいけない (slot20 が間接参照する)。
 * ctx+0x3188 -> P{f32 @0/4/8/0xc (ctx.model), i32 @0x10 (model id), u8 @0x14 (bit0)}
 * UCRT matherr thunk (0x181383e30/e50 = jmp rax) は pow/log の edge 経路で到達する。native は既定 _matherr
 * (0 を返す) へ差し替える。wasm 側は snapins.json shims の ret0 と同一意味 (scen_delay.h と同じ扱い)。 */
#include "scen_common.h"
#include "scen_khmath.h"
#define LD_PROC 0x1804d9930UL
#define LD_S15 0x1804d9820UL
#define LD_S20 0x1804d9ba0UL
#ifndef __EMSCRIPTEN__
static u64 __attribute__((ms_abi)) ld_matherr_default(void) { return 0; }
#endif
static void trial_ladder(int t) {
    if (t == 0) {
        patch_iats();
#ifndef __EMSCRIPTEN__
        *(u64*)0x1813a1d38ULL = (u64)ld_matherr_default;
        *(u64*)0x1813a1d40ULL = (u64)ld_matherr_default;
        *(u64*)0x1813a1d48ULL = (u64)ld_matherr_default;
#endif
    }
    u8* self = A(0x600); u8* ctx = A(0x3200); u8* P = A(0x40); u8* vt = A(0x100);
    *(void**)(self + 0) = vt;
    *(void**)(vt + 0x78) = (void*)LD_S15;
    *(void**)(vt + 0xa0) = (void*)LD_S20;
    *(void**)(ctx + 0x3188) = P;
    REGION("self", self, 0x600); REGION("vt", vt, 0x100); REGION("P", P, 0x40);
    C1(LD_S15, RET_NONE, self);
    for (int o = 0x4b0; o < 0x5d8; o += 4) if (o != 0x528 && o != 0x52c) *(float*)(self + o) = RF(-1, 1);
    *(float*)(self + 0x60) = RF(0.5f, 20);
    *(int*)(self + 0x528) = RI(0, 2); *(int*)(self + 0x52c) = RI(0, 2);
    for (int k = 0; k < 4; k++) *(float*)(P + 4 * k) = RF(0, 1);
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n();
        Buf b = mkbuf(n, 1.0f); REGION("buf", b.raw, 0x30);
        *(int*)(P + 0x10) = RI(0, 3);
        P[0x14] = R32() & 1;
        C3(LD_PROC, RET_NONE, self, ctx, b.raw);
    }
}
