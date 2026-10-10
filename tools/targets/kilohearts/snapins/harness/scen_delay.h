/* Delay (delay::DelayDsp) process 0x1802ed7f0 (3291B) — KH-6 Tier-M (CAB-258)。
 * this(0x1a0, DelayDsp — deleting dtor 0x1802ee550 の op_new(this,0x1a0) 実測):
 *   +0x60 (未使用) +0x64 f fs (setfs 0x1802ed550 が xmm1 から格納) +0x68 f fs2 +0x6c f mult (ctor 設定, scenario で与える)
 *   +0x70 f coeff (setfs: powf 経由で計算) +0x78 u8 first +0x7c..0x8c 遅延 ramp {from,target,cur,progress,slope}
 *   +0x90..0x15c feed/pan ramp 群 +0x140..0x15c d[4] 内部 1-pole 状態
 *   +0x160 DelayLine {+0x00 f fs, +0x08 f cap, +0x10 histL*, +0x18 f oldcap, +0x20 histR*,
 *     +0x28 f cap1, +0x2c u32 mask, +0x30 u32 wr(3), +0x34 u32 fill(3)} (dl_prepare 0x1802ed640 が
 *     op_new[] (0x180f87cac → HeapAlloc IAT) で (cap+16)*4 を 2 本確保)
 *   +0x198 obj* (tap_add 0x1802ecfc0 の加算先: +0x28 / +0x228 に float2 配列, idx<n → 0xB00 確保)
 * ctx: +0x3180 i32 (vec push 値 = +10), +0x3188 P*, +0x3198 Q*{+0x15c u8 dirty}, +0x31b0 V*{+0x60 end*, +0x70 cap*}
 *   proc 冒頭: Q.dirty==0 → dirty=1 して V へ (ctx+0x3180 + 10) を push (満杯時 0x18004cf20 realloc 経路)
 * buf: L@0 R@8 n@0x28, +0x58 f64 sample rate (proc が読む)
 * P: [0] f delay(s) [1] i sync num [2] i sync mode (表 0x181563298 ×6, 2/3..1/8) [3] f sync on
 *    [4] f [6] f [7] f [8] f — proc は P+0x28 f (表示値) を書く
 * 呼出: setfs(this, xmm1=fs) / reset(this) / s13(this, ctx, buf) / process(this, ctx, buf)
 * fs=8000 固定 (cap = 2^ceil(8000*5+15)-1+1 = 65536 → hist 2 本 × 262KB が KH_HEAP 1MB 内に収まる) */
#include "scen_khmath.h"
#define DL_PROC   0x1802ed7f0UL
#define DL_S13    0x1802ed790UL
#define DL_RESET  0x1802ed3b0UL
#define DL_RESET2 0x1802ed490UL
#define DL_SETFS  0x1802ed550UL
#define DL_FS     8000.0f

#ifndef __EMSCRIPTEN__
/* UCRT matherr 既定 (何もせず 0 = 既定処理) — 0x1813a1d38/d40/d48 スロットへ patch */
u64 __attribute__((ms_abi)) dl_matherr_default(void) { return 0; }
#endif

static void trial_delay(int t) {
    if (t == 0) {
        patch_iats();
#ifndef __EMSCRIPTEN__
        /* UCRT matherr pre-terminator (encoded-pointer 初期化前の jmp rax thunk 指し先) を
         * 既定 _matherr (= 0 返して既定処理続行) と同意味の shim へ差し替え。
         * pow 0x180fc4590 の underflow/edge 経路で到達 (native は未 patch だと jmp rax → SEGV)。
         * wasm 側は snapins.json shims の ret0 (function_181383e30/e50 が 0 を返す) と同一意味。 */
        { static u8 crt_term_slot_done = 0;
          if (!crt_term_slot_done) {
            *(u64*)0x1813a1d38ULL = (u64)dl_matherr_default;
            *(u64*)0x1813a1d40ULL = (u64)dl_matherr_default;
            *(u64*)0x1813a1d48ULL = (u64)dl_matherr_default;
            crt_term_slot_done = 1;
          } }
#endif
    }
    u8* hc = A(0x110); *(u64*)(hc + 0x100) = 0;      /* kh heap bump 状態を trial 毎に reset (khmath 慣習) */
    u8* self = A(0x1a0); u8* ctx = A(0x3200); u8* P = A(0x30); u8* Q = A(0x200);
    u8* V = A(0x80); u8* vecbuf = A(0x100); u8* tap = A(0xb00);
    u8* raw = A(0x80);
    Buf b; b.raw = raw; b.L = A((BUFCAP + 4) * 4); b.R = A((BUFCAP + 4) * 4); b.n = 0;
    *(float**)(raw + 0) = b.L; *(float**)(raw + 8) = b.R; *(double*)(raw + 0x58) = (double)DL_FS;
    REGION("self", self, 0x1a0); REGION("P", P, 0x30); REGION("Q", Q, 0x200);
    REGION("V", V, 0x80); REGION("tap", tap, 0xb00); REGION("raw", raw, 0x80);
    REGION("bufL", b.L, (BUFCAP + 4) * 4); REGION("bufR", b.R, (BUFCAP + 4) * 4);
    *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31b0) = V;
    *(int*)(ctx + 0x3180) = RI(0, 2000);
    *(float**)(V + 0x60) = (float*)vecbuf; *(float**)(V + 0x70) = (float*)(vecbuf + 0x100);
    /* V は vec<int> ヘッダ {begin@0x60, end@0x68, cap@0x70}: proc 冒頭 push が end を読む (未設置だと NULL 書込で SEGV)。
     * end を 0..64 slot に散らし 64 (= cap) で 0x18004cf20 realloc 経路も発火させる */
    *(float**)(V + 0x68) = (float*)(vecbuf + 4 * (size_t)(R32() % 65));
    *(void**)(self + 0x198) = tap;
    *(float*)(self + 0x6c) = RF(0.05f, 2.0f);
    C2F(DL_SETFS, RET_NONE, self, DL_FS);            /* fs → xmm1 (dl 準備 + op_new[] 確保) */
    self[0x78] = (t % 2) != 0;                       /* 遅延 ramp first */
    if (t % 4 == 1) C2(DL_RESET, RET_NONE, self, 0);
    if (t % 4 == 3) C2(DL_RESET2, RET_NONE, self, 0);
    int nb = 3 + (t % 3);
    for (int k = 0; k < nb; k++) {
        int n = pick_n();
        for (int i = 0; i < n; i++) { b.L[i] = RF(-1.0f, 1.0f); b.R[i] = RF(-1.0f, 1.0f); }
        *(int*)(raw + 0x28) = n; b.n = n;
        *(float*)(P + 0) = RFSPECIAL(0.0f, 4.5f);    /* delay sec (max 5.0) */
        *(int*)(P + 4) = RI(1, 8);                   /* sync num */
        *(int*)(P + 8) = RI(1, 6);                   /* sync mode (表 idx 0..5) */
        *(float*)(P + 0xc) = (t % 2) ? 1.0f : 0.0f;  /* sync on/off */
        *(float*)(P + 0x10) = RF(-1.0f, 1.0f);
        *(float*)(P + 0x18) = RF(0.0f, 1.0f);
        *(float*)(P + 0x1c) = RFSPECIAL(-1.0f, 1.0f);
        *(float*)(P + 0x20) = RF(-1.0f, 1.0f);
        C3(DL_PROC, RET_NONE, self, ctx, raw);
        if ((t + k) % 4 == 2) C3(DL_S13, RET_NONE, self, ctx, raw);
    }
}
