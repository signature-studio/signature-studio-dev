/* Resonator (resonator::ResonatorDsp) slot14=process 0x180743390 (2020B) — CAB-224 (許容誤差判定)。
 * process 内 0x180743419: rcpps xmm2, xmm1 (逆数, Newton 1 段で精密化) → native 参照 = 実機 AMD Ryzen 9 9950X の
 * 近似表。wasm 側は IEEE 1/x → 差は liftlib simdtest.py と同一基準の相対誤差 gate (1.6*2^-12) で許容する。
 * this(0x120) — slot7 prepare(f) が +0x60 = f を設定し、共通 DelayLine prepare (0x1802c82e0, this+0x68) が
 *   +0x6c = f (同一値), +0x70 = cap, +0x78 = histL, +0x80 = cap, +0x88 = histR, +0x90 = cap, +0x94 = mask,
 *   +0x98 = +0x9c = 3 (wr / fill 初期値) を設定。バッファは (cap+3) float で cap..cap+2 が wrap ミラー
 *   (書込 pos < 3 の時に process 内 jb 経路で mirror 書込)。
 *   ramp 群 ×5 (0xa0/0xb8/0xd0/0xe8/0x100): +0x00 pos(f) +0x04 slope(f) +0x08 from(f) +0x0c to(f) +0x10 cur(f) +0x14 u8 first
 * ctx+0x3188 -> P{+0x00 f: MIDI note (expf(note/12-5.75) → 440/880 倍), +0x04 f: decay div, +0x08 f: resonance,
 *   +0x0c u8: mode (bit0), +0x10 f} — process は P を書かない。
 * ループ: 遅延 = spread(ramp1 cur) × f ([0x6c]) = O(1) sample + cubic 補間 + 状態変数共振 → outL/outR。 */
#include "scen_common.h"
#define RE_PROC 0x180743390UL
static const int RE_CAPS[] = {256, 512, 1024, 2048};
static void trial_resonator(int t) {
    u8* self = A(0x120); u8* ctx = A(0x3200); u8* P = A(0x14);
    int cap = RE_CAPS[R32() % 4];
    float* hL = A((size_t)(cap + 8) * 4); float* hR = A((size_t)(cap + 8) * 4);
    float F = RF(80, 4000);
    *(void**)(ctx + 0x3188) = P;
    REGION("self", self, 0x120); REGION("P", P, 0x14); REGION("histL", hL, (size_t)(cap + 8) * 4); REGION("histR", hR, (size_t)(cap + 8) * 4);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    *(float*)(self + 0x60) = F;                            /* prepare(f) 設定値 (rcpps の lane1) */
    *(float*)(self + 0x6c) = F;                            /* DelayLine prepare 設定値 (遅延倍率 = 同一周波数) */
    *(int*)(self + 0x70) = cap;                            /* histL mirror offset (= cap) */
    *(float**)(self + 0x78) = hL;
    *(int*)(self + 0x80) = cap;                            /* histR mirror offset (= cap) */
    *(float**)(self + 0x88) = hR;
    *(int*)(self + 0x90) = cap; *(int*)(self + 0x94) = cap - 1;
    *(int*)(self + 0x98) = (t % 2) ? 3 : RI(3, cap - 1);   /* 書込 pos (実初期値 3 / 進行中) */
    *(int*)(self + 0x9c) = (t % 2) ? 3 : RI(3, cap);       /* 履歴 fill (実初期値 3, cap で飽和) */
    for (int g = 0; g < 5; g++) {                          /* ramp 群: pos/slope/from/to/cur/first */
        u8* G = self + 0xa0 + 0x18 * g;
        *(float*)(G + 0) = RF(0, 4); *(float*)(G + 4) = RF(-0.01f, 0.01f);
        *(float*)(G + 8) = RFSPECIAL(-0.9f, 0.9f); *(float*)(G + 0xc) = RFSPECIAL(-0.9f, 0.9f);
        *(float*)(G + 0x10) = RF(-0.9f, 0.9f); G[0x14] = (t % 3) == 0;
    }
    *(float*)(P + 0) = RF(70, 96);                         /* MIDI note (expf 引数 > 0 を保証) */
    *(float*)(P + 4) = RF(0.05f, 2);                       /* decay (0 除げ, 高Q 極端角の利得爆発回避) */
    *(float*)(P + 8) = RF(0.1f, 1);                        /* resonance → |利得| ≤ 0.9 (増幅 1/(1-|g|) ≤ 10 倍) */
    P[0xc] = R32() & 1;                                    /* mode bit0 */
    *(float*)(P + 0x10) = RF(0.1f, 1.1f);
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n();
        *(float*)(P + 0) = RF(70, 96);
        *(float*)(P + 4) = RF(0.05f, 8);
        *(float*)(P + 8) = RF(0.1f, 1);
        P[0xc] = R32() & 1;
        *(float*)(P + 0x10) = RF(0.1f, 1.1f);
        refill(&b, n, 1.0f);
        C3(RE_PROC, RET_NONE, self, ctx, b.raw);
    }
}
