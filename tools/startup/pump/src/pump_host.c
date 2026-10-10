/* pump_host.c — ホスト (JS) 側との結線 export 群。
 *
 * 必須結線:
 *   pump_ring_addr()      → 共有 wasm メモリ上のリング先頭 (64B アライン)。
 *                           ホストは `new PumpRing(memory.buffer, addr)` (worker_pump.ts) で push する。
 *   pump_step / pump_wait_ms → HOSTED モードのプロトコル。「C は 1 回試行して待ち時間ヒントを返し、
 *                           ホスト (Worker) が実際に寝てから再入場する」。AudioWorklet では NONE を使う。
 *   pump_set_wait_mode    → ATOMIC/SLICE/SPIN/HOSTED/NONE (pump_abi.h)。
 *   pump_ctrl_*           → 要求リング / 応答メールボックスのアドレス (host が排水する)。
 */
#include "pump_internal.h"

#define EXPORT(n) __attribute__((export_name(n)))

EXPORT("pump_abi_version") int pump_abi_version(void) { return 1; }

EXPORT("pump_ring_addr") int pump_ring_addr(void) { return (int)(uintptr_t)&g_pring; }
EXPORT("pump_ring_capacity") int pump_ring_capacity(void) { return (int)PR_CAP_DEFAULT; }

EXPORT("pump_ctrl_req_addr") int pump_ctrl_req_addr(void) { return pctrl_req_seq(); }
EXPORT("pump_ctrl_resp_addr") int pump_ctrl_resp_addr(void) { return pctrl_resp_seq(); }

EXPORT("pump_set_wait_mode") void pump_set_wait_mode(int mode) {
    if (mode >= PUMP_WAIT_ATOMIC && mode <= PUMP_WAIT_NONE) g_wait_mode = mode;
}
EXPORT("pump_get_wait_mode") int pump_get_wait_mode(void) {
    return g_wait_mode < 0 ? pump_default_wait_mode() : g_wait_mode;
}
EXPORT("pump_set_slice_ms") void pump_set_slice_ms_e(int ms) { pump_set_slice_ms(ms); }
EXPORT("pump_set_wait_cap_ms") void pump_set_wait_cap_ms_e(int ms) { pump_set_wait_cap_ms(ms); }
EXPORT("pump_set_ctrl_timeout_ms") void pump_set_ctrl_timeout_ms_e(double ms) { pump_set_ctrl_timeout_ms(ms); }

/* HOSTED プロトコル: 1 回の非ブロッキング試行。
 * 戻り値: 1 = メッセージ取得 (*msg に WMSG 48B) / 0 = WM_QUIT / -1 = 空 (pump_wait_ms() 待って再入場) */
EXPORT("pump_step") int pump_step(void* msg) {
    pump_count();
    PumpFilter f = { 0, 0, 0 };
    if (ptake((WMSG*)msg, &f, 1))
        return ((WMSG*)msg)->message == PWM_QUIT ? 0 : 1;
    if (pump_eff_wait_mode() == PUMP_WAIT_NONE) __atomic_add_fetch(&g_pstat.nowait_empty, 1u, __ATOMIC_RELAXED);
    else __atomic_add_fetch(&g_pstat.hosted_empty, 1u, __ATOMIC_RELAXED);
    return -1;
}

/* 次に寝るべき時間 (ms): タイマ満期まで。-1 = タイマ無し (ホストは自枠の予算で寝てよい) */
EXPORT("pump_wait_ms") double pump_wait_ms(void) {
    double due = ptimer_next_due();
    if (due >= PINF) return -1.0;
    double r = due - pnow();
    return r > 0.0 ? r : 0.0;
}

/* ---- 統計 / ログ ---- */
EXPORT("pump_stats_addr") int pump_stats_addr(void) { return (int)(uintptr_t)&g_pstat; }
EXPORT("pump_stats_reset") void pump_stats_reset_e(void) { memset(&g_pstat, 0, sizeof g_pstat); }
/* pump_pop_log_addr / pump_pop_log_count は pump_stats.c が export する */

/* ---- 時刻較正 (ctrl 経由)。HOSTED/NONE では後続 step で完了する ---- */
EXPORT("pump_calibrate") void pump_calibrate_e(void) { pump_calibrate(); }
EXPORT("pump_clock_offset") double pump_clock_offset_e(void) { return pump_clock_offset(); }
EXPORT("pump_clock_calibrated") int pump_clock_calibrated_e(void) { return pump_clock_calibrated(); }
/* デバッグ/校正補助: C 生クロックと強制オフセット設定 (ホストが自クロックと突き合わせる用) */
EXPORT("pump_now_raw") double pump_now_raw(void) { return pnow(); }
EXPORT("pump_set_clock_offset") void pump_set_clock_offset_e(double o) {
    extern void pump_force_clock_offset(double);
    pump_force_clock_offset(o);
}

/* ---- wndproc 結線 (boot 経路用。gui 経路では gui 側が Dispatch を持つ) ---- */
EXPORT("pump_set_wndproc") void pump_set_wndproc_e(void* hwnd, void* proc) {
    pwnd_register(hwnd, (PWNDPROC)(uintptr_t)proc);
}

/* ---- テスト補助 (e2e / 単体から使う。製品コードは Win32 API 面だけを見る) ---- */
static uint64_t g_scratch[8];   /* HOSTED ドライバが WMSG を受け取る静的バッファ */
EXPORT("pump_scratch_addr") int pump_scratch_addr(void) { return (int)(uintptr_t)g_scratch; }
EXPORT("pump_t_post_quit") void pump_t_post_quit(int code) { pquit_post(code); }
EXPORT("pump_t_pending") int pump_t_pending(void) {
    WMSG tmp;
    PumpFilter f = { 0, 0, 0 };
    return ptake(&tmp, &f, 0);
}
EXPORT("pump_t_quit_posted") int pump_t_quit_posted(void) {
    int code = 0;
    return pquit_taken(&code) ? code : -1;
}
