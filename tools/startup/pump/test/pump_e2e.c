/* pump_e2e.c — e2e 用の検証ドライバ export 群 (製品コードには入らない)。
 *
 * e2e_consumer_run : FL 風メインループ (GetMessageW → Translate → Dispatch)。
 *                    ATOMIC/SLICE/SPIN モードではこの中で C がブロックする
 *                    (node main thread 上の wasm futex 待ち。producer は別スレッド)。
 * e2e_poll_once    : worklet 相当 (NONE モード) の 1 回 Peek。JS が短周期で呼ぶ。
 * e2e_ctrl_probe   : C→host 要求 (ECHO) を n 回。応答待ち戦略は pump_wait_mode に従う。
 */
#include "../src/pump_internal.h"
#include "../src/pump_api.h"

#define EXPORT(n) __attribute__((export_name(n)))

static PTIMERPROC g_last_tproc;
static uint32_t g_tproc_id_sum;

static void e2e_tproc(void* hwnd, uint32_t msg, uint64_t id, uint32_t now) {
    (void)hwnd; (void)msg; (void)now;
    g_tproc_id_sum += (uint32_t)id;
    g_last_tproc = e2e_tproc;
}

EXPORT("e2e_setup") void e2e_setup(void) {
    winstubs_init(0);
    g_tproc_id_sum = 0;
}

/* タイマ設定 (proc 付き / 無し) */
EXPORT("e2e_setup_timer") int e2e_setup_timer(HWND hwnd, UINT_PTR_T id, UINT ms, int use_proc) {
    return SetTimer(hwnd, id, ms, use_proc ? (LPVOID)e2e_tproc : 0);
}

EXPORT("e2e_tproc_sum") uint32_t e2e_tproc_sum(void) { return g_tproc_id_sum; }

/* FL 風コンシューマループ。戻り値: 1=WM_QUIT で正常終了 / 0=タイムアウト */
EXPORT("e2e_consumer_run") int e2e_consumer_run(double max_ms) {
    WMSG m;
    double deadline = pnow() + max_ms;
    while (pnow() < deadline) {
        LONG r = GetMessageW(&m, 0, 0, 0);
        if (r == 0) return 1;                       /* WM_QUIT */
        if (r < 0) {                                 /* HOSTED/NONE で空 — ホスト主導の再入場が無い経路 */
            pump_wait_progress(&(PumpFilter){ 0, 0, 0 });
            continue;
        }
        TranslateMessage(&m);
        DispatchMessageW(&m);
        if (m.message == PWM_APP_RUNTIME_STOP)
            pquit_post(0);                           /* 検証ドライバ相当の終了要求 */
    }
    return 0;
}

/* worklet 相当: 1 回 Peek (決して待たない)。戻り値: message (0 = 無し) */
EXPORT("e2e_poll_once") uint32_t e2e_poll_once(void) {
    WMSG m;
    PumpFilter f = { 0, 0, 0 };
    if (ptake(&m, &f, 1)) {
        if (m.message == PWM_TIMER && m.lParam) ((PTIMERPROC)(uintptr_t)m.lParam)(m.hwnd, PWM_TIMER, m.wParam, (uint32_t)pnow());
        return m.message;
    }
    return 0;
}

/* C→host 要求プローブ: ECHO を n 回 (ATOMIC/SLICE/SPIN はここでブロックする)。
 * 戻り値: 成功数 * 100 + 最後の rc (0 or 正) / 失敗 rc。デバッグ用に失敗理由も返す。 */
static int g_probe_last_rc;
EXPORT("e2e_ctrl_probe") int e2e_ctrl_probe(int n) {
    int ok = 0;
    for (int i = 0; i < n; i++) {
        double ret = 0;
        int rc = pump_ctrl_request(PCTRL_OP_ECHO, (uint32_t)i, 0, &ret, 0);
        g_probe_last_rc = rc;
        if (rc == 0) ok++;
        else break;
    }
    return ok * 100 + (g_probe_last_rc < 0 ? -g_probe_last_rc : 0);
}
EXPORT("e2e_ctrl_probe_rc") int e2e_ctrl_probe_rc(void) { return g_probe_last_rc; }

/* HOSTED 向け: 応答完了を pump_step 頭の service_done に委ねる確認用。
 *   1) e2e_ctrl_async_req() → 要求を積んで pending (-1) で即帰る
 *   2) ホスト (JS) が要求リングを排水して応答を書く
 *   3) e2e_ctrl_take_done() → 完了していれば ret0 を返す (0 = 未完了) */
EXPORT("e2e_ctrl_async_req") int e2e_ctrl_async_req(void) {
    double ret = 0;
    return pump_ctrl_request(PCTRL_OP_ECHO, 0xBEEF, 0, &ret, 0);   /* -1 = pending (期待値) */
}
EXPORT("e2e_ctrl_take_done") double e2e_ctrl_take_done(void) {
    double ret = 0;
    return pump_ctrl_take_done(&ret) ? ret : -1.0;
}

/* プロファイル用: pnow (JS import) と空ループのコスト */
EXPORT("e2e_prof_pnow") double e2e_prof_pnow(int n) {
    double t0 = pnow();
    double acc = 0;
    for (int i = 0; i < n; i++) acc += pnow();
    return pnow() - t0 - acc * 0;   /* 経過 ms */
}
EXPORT("e2e_prof_empty") double e2e_prof_empty(int n) {
    double t0 = pnow();
    long acc = 0;
    for (int i = 0; i < n; i++) acc += i;
    return pnow() - t0 + (double)acc * 0;
}
EXPORT("e2e_prof_take") double e2e_prof_take(int n) {
    /* 空キューでの ptake コスト (service_done + held/stash/ring スキャン) */
    double t0 = pnow();
    WMSG m;
    PumpFilter f = { 0, 0, 0 };
    for (int i = 0; i < n; i++) ptake(&m, &f, 0);
    return pnow() - t0;
}

/* futex wake レイテンシ計測 (micro-bench): addr を timeout ms で待つ。
 * 結果は g_bench_out = { ブロック実測 ms (C clock), 起床時刻 (epoch ms, 較正済) }。
 * addr は pump_scratch_addr() の先頭語を使う (ベンチ中は誰も使わない)。 */
static double g_bench_out[2];
EXPORT("e2e_wait_bench") void e2e_wait_bench(int addr, int timeout_ms) {
    volatile int32_t* p = (volatile int32_t*)(uintptr_t)addr;
    double t0 = pnow();
    int32_t w = __atomic_load_n(p, __ATOMIC_ACQUIRE);
#ifdef __EMSCRIPTEN_PTHREADS__
    __builtin_wasm_memory_atomic_wait32((int32_t*)(uintptr_t)addr, w, (int64_t)timeout_ms * 1000000LL);
#endif
    g_bench_out[0] = pnow() - t0;
    g_bench_out[1] = pnow() + pump_clock_offset();
}
EXPORT("e2e_bench_out_addr") int e2e_bench_out_addr(void) { return (int)(uintptr_t)g_bench_out; }
