/* Stereo (stereo::StereoDsp) slot14=process 0x18080d4d0 (1679B) — CAB-224 (許容誤差判定)。
 * process 内 0x18080da3b: rsqrtps xmm3, xmm2 (逆平方根, Newton 1 段で精密化) → native 参照 = 実機 Ryzen 9 9950X。
 * this(0xd0): ramp 群 ×4 (0x60 gC / 0x78 gA / 0x90 gB / 0xa8 gD: 各 +0 pos +4 slope +8 from +c to +10 cur +14 u8 first)
 *   +0xc0 f[2] one-pole 状態 (movlps store / movsd 再読 = f32 ペア) +0xc8 f one-pole +0xcc f 係数
 * ctx+0x3188 -> P{+0x00 f, +0x04 f} — 終端に meter 計算結果を +0x0c / +0x10 へ書き戻す (rsqrtps 経路)。
 * ctx+0x3198 -> Q{+0x48 f: 位相 (quarter-turns; sin(Q*π/2)。|θ|<5e5 まで bit-exact 検証済み、
 *   k_dfdb0 Payne-Hanek 経路 (|θ|≥5e5) は lift 未検証 = 申し送り), +0x7c u8 / +0x9c u8: dirty}
 * ctx+0x31b0 -> V{+0x68 end, +0x70 cap} 変更通知 vector<int> (常に空き有り → realloc 0x18004cf20 未到達)。 */
#include "scen_common.h"
#define ST_PROC 0x18080d4d0UL
static void trial_stereo(int t) {
    u8* self = A(0xd0); u8* ctx = A(0x3200); u8* P = A(0x14); u8* Q = A(0xa0); u8* V = A(0x80); int* vec = A(16 * 4);
    *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31b0) = V; *(int*)(ctx + 0x3180) = RI(0, 2000);
    REGION("self", self, 0xd0); REGION("P", P, 0x14); REGION("Q", Q, 0xa0); REGION("V", V, 0x80); REGION("vec", vec, 64);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    const struct { unsigned short o; } grp[4] = {{0x60}, {0x78}, {0x90}, {0xa8}};
    for (int g = 0; g < 4; g++) {
        u8* G = self + grp[g].o;
        *(float*)(G + 0) = RF(0, 4); *(float*)(G + 4) = RF(-0.01f, 0.01f);
        *(float*)(G + 8) = RFSPECIAL(-1.5f, 1.5f); *(float*)(G + 0xc) = RFSPECIAL(-1.5f, 1.5f);
        *(float*)(G + 0x10) = RF(-1, 1); G[0x14] = (t % 3) == 0;
    }
    *(float*)(self + 0xc0) = RF(0.01f, 2);   /* one-pole 状態 (正側に寄せる: rsqrtps 負入力 NaN は mask で打ち消されるが大部分を正に) */
    *(float*)(self + 0xc4) = RF(0.01f, 2);
    *(float*)(self + 0xc8) = RF(0.01f, 2);
    *(float*)(self + 0xcc) = RF(0, 0.999f);
    *(float*)(Q + 0x48) = RF(-64, 64);                     /* 位相 (quarter-turns, model 層 wrap 前提 → θ=Q*π/2 ≤ 100) */
    Q[0x7c] = R32() & 1; Q[0x9c] = R32() & 1;
    *(int**)(V + 0x68) = vec + (R32() % 3); *(int**)(V + 0x70) = vec + 16;
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n();
        *(float*)(P + 0) = RFSPECIAL(-1.5f, 1.5f);
        *(float*)(P + 4) = RFSPECIAL(-1.5f, 1.5f);
        *(float*)(Q + 0x48) = RF(-64, 64);
        Q[0x7c] = R32() & 1; Q[0x9c] = R32() & 1;
        refill(&b, n, 1.0f);
        C3(ST_PROC, RET_NONE, self, ctx, b.raw);
    }
}
