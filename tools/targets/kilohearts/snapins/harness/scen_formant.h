/* Formant Filter (vocalfilter::VocalFilterDsp) slot14=process 0x18085a730 (614B) — KH-1c (CAB-243, bit-exact 判定)。
 * process: P{+0x00 f: 周波数 A, +0x04 f: 周波数 B, +0x08 f: Q (>0 → log10f 定義域), +0x0c u8: biquad type 選択 bit0
 *   (2 + 3·bit = 2 or 5), +0x10 u8: 同 (5·bit = 0 or 5)} を読み,
 *   0x180fbbae0 (log10f, FMA3/SSE2 二系統, ディスパッチ flag 0x184162364 = 非 0 → FMA 系) で 20·log10(Q) [dB]
 *   を求め biquad design 0x180bac490 を 2 回 (係数はスタック引数 5/6 番 = P8 と dB) 呼んで
 *   2 段縦続 biquad の係数を作り, per-sample で DF2 状態 (this+0x70..+0xf0 = 16B×8, L/R を f64 ペア) を更新。
 * this(0x100): +0x60 f32 サンプルレート (prepare 0x180020650 の設定値)。状態は reset (slot15) 後の 0 初期化 =
 *   arena 0 転写と一致。近似命令なし (rcpps/rsqrtps なし) → bit-exact 判定。
 * log10f は P8 > 0 (常時) で特殊値経路 (0x180fd4c50 → CRT 例外報告) 不発 → 同 callee は fail-fast stub のまま。 */
#include "scen_common.h"
#define VF_PROC 0x18085a730UL
static const int VF_SR[] = {44100, 48000, 88200, 96000};
static void trial_formant(int t) {
    (void)t;
    u8* self = A(0x100); u8* ctx = A(0x3200); u8* P = A(0x14);
    *(void**)(ctx + 0x3188) = P;
    REGION("self", self, 0x100); REGION("P", P, 0x14);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    *(float*)(self + 0x60) = (float)VF_SR[R32() % 4];
    *(float*)(P + 0) = RF(20, 20000);
    *(float*)(P + 4) = RF(20, 20000);
    *(float*)(P + 8) = RF(0.1f, 30);
    P[0xc] = (u8)(R32() & 1);
    P[0x10] = (u8)(R32() & 1);
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n();
        *(float*)(P + 0) = RF(20, 20000);
        *(float*)(P + 4) = RF(20, 20000);
        *(float*)(P + 8) = RF(0.1f, 30);
        P[0xc] = (u8)(R32() & 1);
        P[0x10] = (u8)(R32() & 1);
        refill(&b, n, 1.0f);
        C3(VF_PROC, RET_NONE, self, ctx, b.raw);
    }
}
