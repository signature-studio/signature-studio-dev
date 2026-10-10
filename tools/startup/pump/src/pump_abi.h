/* pump_abi.h — user32 ポンプ shim の RING ABI (CAB-102)。
 *
 * リングのバイトレイアウトは src/runtime/worker_pump.ts の RING 定数と**完全一致**させる
 * (ヘッダ 16×i32 = 64B + スロット 16×i32 = 64B × capacity)。JS 側 (main / GUI worker /
 * AudioWorklet) は worker_pump.ts の PumpRing を共有 wasm メモリ上のこのリングに直接 push し、
 * C 側 (wasm UI スレッド) が GetMessageW 等で消費する。
 *
 * 配置: リングは本 TU の静的領域 (wasm リニアメモリ内, 64B アライン)。
 * ホストは pump_ring_addr() の返値を byteOffset にして PumpRing を構築する (init=false)。
 * 初期化 (seq/capacity/magic) は C 側のコンストラクタが __wasm_call_ctors で行う。
 *
 * 待機モード (AudioWorklet 内は Atomics.wait 不可 → NONE を使う。D 検収確認済み):
 *   PUMP_WAIT_ATOMIC : memory.atomic.wait32 で直接ブロック (MT ビルド / UI スレッド)。本命。
 *   PUMP_WAIT_SLICE  : futex を短いスライスで寝る (ATOMIC の保守フォールバック)。
 *   PUMP_WAIT_SPIN   : wake 語のビジーウェイト (極短待ち・CPU を消費する計測用)。
 *   PUMP_WAIT_HOSTED : ブロックせずホストに返す (pump_step + pump_wait_ms プロトコル)。
 *                      ST ビルド用。「C が待ち時間を計算して返し、ホスト (JS) が実際に寝て再入場する」。
 *   PUMP_WAIT_NONE   : 決して待たない (worklet 相当)。空なら即 -1 / FALSE。
 */
#ifndef PUMP_ABI_H
#define PUMP_ABI_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- リング ABI 定数 (worker_pump.ts RING と同一値) ---- */
#define PR_HDR_I32     16
#define PR_SLOT_I32    16
#define PR_H_ENQ       0
#define PR_H_DEQ       1
#define PR_H_WAKE      2
#define PR_H_MAGIC     3   /* TS 側は未使用 (スパイクが quit に使った番号)。本 ABI ではマジック */
#define PR_H_CAPACITY  4
#define PR_H_DROPPED   5
#define PR_MAGIC       0x50554D50u  /* "PUMP" */

#define PR_S_SEQ       0
#define PR_S_MSG       1
#define PR_S_HWND_LO   2
#define PR_S_HWND_HI   3
#define PR_S_W_LO      4
#define PR_S_W_HI      5
#define PR_S_L_LO      6
#define PR_S_L_HI      7
#define PR_S_TIME      8
#define PR_S_PTX       9
#define PR_S_PTY       10
/* [11..15] 予約。tPost (f64) はスロット先頭 +48B (= i32 索引 12, 8B アライン済) */
#define PR_S_TPOST_I32 12

#define PR_CAP_DEFAULT 1024u  /* 2 のべき乗。worker_pump.ts 既定と同一 */
#define PR_CAP_MAX     4096u

/* ---- Win64 MSG (48B): lift 側 (Delphi / win64 呼出規約) が期待するレイアウト。
 * wasm32 でもポインタ幅に寄せず Win64 のオフセットを維持する (hwnd +0 8B / message +8)。 ---- */
typedef struct WMSG {
    uint64_t hwnd;      /* +0  (Win64 HWND: 上位 32bit は 0) */
    uint32_t message;   /* +8  */
    uint32_t pad0;      /* +12 */
    uint64_t wParam;    /* +16 */
    uint64_t lParam;    /* +24 */
    uint32_t time;      /* +32 */
    int32_t  pt_x;      /* +36 */
    int32_t  pt_y;      /* +40 */
    uint32_t pad1;      /* +44 */
} WMSG;                 /* sizeof == 48 */

/* ---- メッセージ定数 (worker_pump.ts WM と同一) ---- */
#define PWM_NULL    0x0000u
#define PWM_PAINT   0x000fu
#define PWM_QUIT    0x0012u
#define PWM_KEYDOWN 0x0100u
#define PWM_KEYUP   0x0101u
#define PWM_CHAR    0x0102u
#define PWM_SYSKEYDOWN 0x0104u
#define PWM_SYSKEYUP   0x0105u
#define PWM_TIMER   0x0113u
#define PWM_MOUSEMOVE 0x0200u
#define PWM_APP_RUNTIME_STOP 0x8001u

/* ---- 待機モード ---- */
enum {
    PUMP_WAIT_ATOMIC = 0,
    PUMP_WAIT_SLICE  = 1,
    PUMP_WAIT_SPIN   = 2,
    PUMP_WAIT_HOSTED = 3,
    PUMP_WAIT_NONE   = 4,
};

/* PeekMessage フラグ */
#define PPM_NOREMOVE 0u
#define PPM_REMOVE   1u
#define PPM_NOYIELD  2u

/* ---- 統計 (pump_stats_addr 経由でホストから読む。全て relaxed 32bit 加算) ---- */
typedef struct PumpStats {
    uint32_t pops;              /* ring から実取り出し */
    uint32_t pushes;            /* ring への投稿 (PostMessage/PostThreadMessage) */
    uint32_t push_full;         /* 満杯で失敗 (Win32 PostMessage 失敗相当) */
    uint32_t timers_set, timers_killed, timers_fired, paints;
    uint32_t waits_atomic, waits_slice, waits_spin;
    uint32_t wait_chunks, wait_chunks_timedout;   /* ATOMIC/SLICE/SPIN のチャンク実績 */
    uint32_t hosted_empty, nowait_empty;          /* HOSTED/NONE で空だった回数 */
    uint32_t dispatched, sent_calls, quit_posts;
    uint32_t stash_hit, stash_skip, stash_overflow;
    uint32_t ctrl_req, ctrl_ok, ctrl_timeout;
    uint32_t wndproc_miss;      /* Dispatch/Send で wndproc 未登録 */
} PumpStats;

/* pop ログ 1 件 (24B: f64×2 + u32×2): 遅延計測用。t_post==0 は合成メッセージ (PAINT/QUIT/held) で遅延統計から除外。
 * TIMER は t_post に「期待時刻 (due)」を入れ、JS 側で (t_pop - t_post) = タイマ遅延を計算する。 */
typedef struct PumpPopLog {
    double t_pop;
    double t_post;
    uint32_t message;
    uint32_t aux;   /* ring 由来: producer 通し番号 (pt.x) */
} PumpPopLog;

#ifdef __cplusplus
}
#endif
#endif
