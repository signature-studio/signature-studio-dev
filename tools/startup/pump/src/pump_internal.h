/* pump_internal.h — pump shim 内部共有。winstubs の計数方式 (WS_INC / g_ws.pump_calls) を踏襲する。 */
#ifndef PUMP_INTERNAL_H
#define PUMP_INTERNAL_H

#include "pump_abi.h"
#include "../../winstubs/src/winstubs.h"   /* shimx.h 由来の型 (HWND/BOOL/...) + WsStats */

#include <emscripten.h>
#include <string.h>

/* ---- winstubs 統計への踏襲カウント (CAB-96 REPORT §4: 「WS_INC(pump_calls) の計数署名を踏襲」)。
 * winstubs がリンクに無い場合は weak 参照が NULL になるので何もしない (単独リンク可)。 */
extern WsStats g_ws __attribute__((weak));
static inline void pump_count(void) {
    if (&g_ws) __atomic_add_fetch(&g_ws.pump_calls, 1u, __ATOMIC_RELAXED);
}

/* ---- クロック: shimx と同一 (emscripten_get_now)。node ではエポック ms、
 * ブラウザでは文脈内単調 ms → エポック系へは pump_calibrate() がオフセットを管理する。 */
static inline double pnow(void) { return emscripten_get_now(); }
#define PINF 1.0e308

/* ---- 取り出しフィルタ (hwnd / msg 範囲) — 先に定義 (プロトタイプ内タグのスコープ問題回避) ---- */
typedef struct PumpFilterT {
    void* hwnd;
    uint32_t lo, hi;
} PumpFilter;

/* ---- リング実体 (pump_ring.c) ---- */
typedef struct PrRing {
    int32_t hdr[PR_HDR_I32] __attribute__((aligned(64)));
    int32_t slot[PR_CAP_DEFAULT][PR_SLOT_I32] __attribute__((aligned(64)));
} PrRing;
extern PrRing g_pring;

void  pring_init(void);                       /* コンストラクタ (__wasm_call_ctors) から 1 回 */
int   pring_pop(uint32_t out[11], double* t_post);  /* 1 件取り出し (空 0)。out = slot 生値 [0..10] */
int   pring_push(void* hwnd, uint32_t msg, uint64_t wp, uint64_t lp, double t_post);
int32_t pring_wake(void);
void  pring_notify(void);                     /* MT ビルドのみ futex wake (ST では no-op) */

/* ---- タイマ (pump_timer.c) ---- */
typedef void (*PTIMERPROC)(void* hwnd, uint32_t msg, uint64_t id, uint32_t now_ms);
int       ptimer_set(void* hwnd, uint64_t id, uint32_t ms, PTIMERPROC proc);   /* 戻り値: 実効 id / 0=失敗 */
int       ptimer_kill(void* hwnd, uint64_t id);
double    ptimer_next_due(void);              /* 最も近い due。無ければ PINF */
int       ptimer_take_due(void** hwnd, uint64_t* id, PTIMERPROC* proc, double* due);
uint32_t  ptimer_count(void);

/* ---- コントロール要求リング (pump_ctrl.c): C→host の要求 / host→C の応答 ---- */
#define PCTRL_REQ_SLOTS  16
#define PCTRL_REQ_I32    8     /* 32B: seq, op, a0, a1, req_id, pad, t_req(f64) */
#define PCTRL_RESP_I32   8     /* 32B: seq, req_id, ret0, ret1, pad[2], t_resp(f64) */
enum { PCTRL_OP_NOPING = 1, PCTRL_OP_EPOCH_NOW = 2, PCTRL_OP_ECHO = 3 };
int32_t pctrl_req_seq(void);
int32_t pctrl_resp_seq(void);
void    pctrl_service_done(void);   /* 応答メールボックスの非ブロック吸い出し (take 前に呼ぶ) */
int     pump_ctrl_request(uint32_t op, uint32_t a0, uint32_t a1, double* ret0, double* ret1);
int     pump_ctrl_take_done(double* ret0);   /* 非同期完了 (HOSTED/NONE) の吸い出し */
void    pump_calibrate(void);       /* host epoch 時刻とのオフセット較正 (ctrl 経由) */
double  pump_clock_offset(void);
void    pump_force_clock_offset(double o);   /* ホスト側較正値の直接設定 (ctrl 較正より正確) */
int     pump_clock_calibrated(void);
double  pump_ctrl_rtt(int i);
uint32_t pump_ctrl_rtt_count(void);
void    pump_set_ctrl_timeout_ms(double ms);

/* ---- 待機 (pump_wait.c) ---- */
int pump_default_wait_mode(void);   /* MT=ATOMIC / ST=HOSTED */
int pump_eff_wait_mode(void);       /* g_wait_mode 未設定 (-1) なら既定を返す */
void pump_wait_progress(const PumpFilter* f);   /* 空キューでの 1 チャンク待機 */
void pump_set_slice_ms(int ms);
void pump_set_wait_cap_ms(int ms);

/* ---- 共有ランタイム状態 ---- */
extern int      g_wait_mode;    /* PUMP_WAIT_* (既定: MT=ATOMIC / ST=HOSTED) */
extern double   g_slice_ms;     /* SLICE モードの 1 スライス (既定 5ms) */
extern double   g_wait_cap_ms;  /* GetMessage 内部待機チャンクの上限 (安全弁。INFINITE 相当運用) */
extern int      g_ctrl_done_flag;      /* 直近要求の応答完了 (pump_ctrl.c) */
extern double   g_ctrl_pending_treq;   /* in-flight 要求の発行時刻 (C clock) */
extern int      g_calibrating;         /* 時刻較正要求 in-flight */

/* ---- 出力ログ / 統計 (pump_stats.c) ---- */
extern PumpStats g_pstat;
void plog_record(uint32_t msg, double t_pop, double t_post, uint32_t aux);

/* ---- ウィンドウプロシージャ登録 (pump_win.c) ----
 * boot 経路 (gui 未リンク) で FL 側 wndproc を結線する入口。gui 経路では gui 側が Dispatch を持つ。 */
typedef int64_t (*PWNDPROC)(void* hwnd, uint32_t msg, uint64_t wp, uint64_t lp);
void  pwnd_register(void* hwnd, PWNDPROC proc);
PWNDPROC pwnd_lookup(void* hwnd);

/* ---- 取り出し中核 (pump_win.c) ----
 * Win32 優先順 (worker_pump.ts MessagePump.take と同一): held → stash → ring → QUIT → PAINT → TIMER。
 * remove=1 で消費 (0 は PeekMessage(PM_NOREMOVE) / WaitMessage 用: 同一 msg が held に残る)。
 * 戻り値: 1=msg 設置 / 0=無し */
int ptake(WMSG* out, const PumpFilter* f, int remove);

/* 内部状態アクセサ (テスト用) */
int  ptake_held_valid(void);
void pstash_clear(void);
int  ppaint_add(void* hwnd);      /* InvalidateRect 本体 */
int  pquit_post(int code);
int  pquit_taken(int* code);       /* QUIT フラグが立っているか (未消費) */
#endif
