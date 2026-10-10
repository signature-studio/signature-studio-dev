/* Disperser (disperser::DisperserDsp) slot14=process 0x180316480 (2311B) — CAB-225 (bit-exact 判定)。
 * 近似命令なし (rcpps/rsqrtps 0 — 検収で実機逆アセ確認済み)。
 * 構造: 7 段 biquad オールパスカスケード。段数 (= P[0], 前回値 this+0x460) の min/max で 2 系統を処理し
 *   buffer 内で crossfade (段数変更の滑らか化)。状態 = this+0x60 + 段*0x20 (double[4])。
 * this(0x470): +0x58 i32(interp へ渡すが未使用) +0x60.. 段状態 ×8 (double4) +0x460 i32 前回段数 (-1=初回)
 *   +0x464 f サンプルレート +0x468 ptr meter (sub: +0x28/+0x128/+0x228/+0x328/+0x428 に input/output 積算, n≤64)
 * ctx+0xa8 u8 = 0 (dirty 通知 OFF → 0x18004df70 は epilogue のみ = ret0 shim, vtable 間接 call 不発)
 * ctx+0xb0.. = param entry 表 (全 0 → 0x180006500 の照合 loop は 1 周で停止, 0x18004d980 不発)
 * ctx+0x3150 -> R{+4 u8 bit0: 1=有効} / ctx+0x3188 -> P{+0x00 i32 段数, +0x04 f 最大周波数 Hz, +0x08 f 分散量}
 * callee: 0x1803172a0 (入力積算) / 0x1803172f0 (出力積算) / 0x180316d90 (norm=係数変換, quickeq 済) /
 *   0x180bac490 (biquad 設計 type=7, quickeq 済 + jumptable 同設定) / 0x181384040 (memmove shim) */
#include "scen_common.h"
#define DP_PROC 0x180316480UL
static void trial_disperser(int t) {
    u8* self = A(0x470); u8* ctx = A(0x3200); u8* P = A(0x10); u8* R = A(8); u8* meter = A(0x600);
    *(void**)(ctx + 0x3150) = R; *(void**)(ctx + 0x3188) = P; *(void**)(self + 0x468) = meter;
    REGION("self", self, 0x470); REGION("P", P, 0x10); REGION("R", R, 8); REGION("meter", meter, 0x600);
    Buf b = mkbuf(0, 1.0f); REGION("buf", b.raw, 0x30);
    R[4] = (R32() % 8 != 0);                               /* bit0: 有効 (0 なら早期 return 路) */
    *(int*)(self + 0x58) = RI(0, 100);
    *(float*)(self + 0x464) = (R32() & 1) ? 44100.0f : 48000.0f;
    *(int*)(self + 0x460) = (t % 4 == 0) ? -1 : RI(0, 8);  /* 前回段数 (-1 = 初回初期化路) */
    for (int s = 0; s < 8; s++)                            /* 段状態 (double x4): 過去値として小さな値を入れる */
        for (int j = 0; j < 4; j++) *(double*)(self + 0x60 + 0x20 * s + 8 * j) = (double)RF(-0.5f, 0.5f);
    for (int o = 0x28; o < 0x528; o += 4) *(float*)(meter + o) = RF(-1, 1);
    int cur = (R32() % 5 == 0) ? 0 : RI(0, 8);             /* 段数 (0 は bypass 経路) */
    *(int*)P = cur;
    *(float*)(P + 4) = (R32() % 6 == 0) ? RF(100, 30000) : RF(100, 20000);  /* たまに 0.49*SR超 → min クランプ路 */
    *(float*)(P + 8) = RF(0.5f, 40);
    int nb = 4 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n(); if (n > 64) n = 64;              /* meter 積算配列 = 64 float */
        cur = (R32() % 5 == 0) ? 0 : RI(0, 8);
        *(int*)P = cur;
        *(float*)(P + 4) = (R32() % 6 == 0) ? RF(100, 30000) : RF(100, 20000);
        *(float*)(P + 8) = RF(0.5f, 40);
        R[4] = (R32() % 8 != 0);
        refill(&b, n, 1.0f);
        C3(DP_PROC, RET_NONE, self, ctx, b.raw);
    }
}
