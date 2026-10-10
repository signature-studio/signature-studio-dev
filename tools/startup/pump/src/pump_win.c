/* pump_win.c — user32 ポンプ系の強定義 (CAB-102)。
 *
 * winstubs (CAB-96) の weak 10 本 (ws_ui.c) を同一シグネチャの強定義で置換し、
 * RING ABI (src/runtime/worker_pump.ts PumpRing) に接続する。
 * - シグネチャは winstubs weak 定義と 1 ビットも変えない (wasm リンクは署名一致を要求するため)。
 * - 呼出カウントは g_ws.pump_calls を踏襲 (winstubs REPORT §4 の指示)。
 * - 優先順は worker_pump.ts MessagePump.take と同一: held → stash → ring(投稿) → QUIT → PAINT → TIMER。
 * - フィルタ (hwnd / msg 範囲) は stash 方式: 範囲外の先頭メッセージを退避し、後続取得で先出しする。
 *
 * 計装対象 (強定義 15 + Ex):
 *   GetMessageW/A PeekMessageW/A TranslateMessage DispatchMessageW/A PostMessageW/A SendMessageW
 *   PostQuitMessage SetTimer KillTimer WaitMessage PostThreadMessageW
 *   MsgWaitForMultipleObjects(+Ex) InvalidateRect
 * gui 経路 (tools/gui gui_adapt_w32) とは**別構成** (同時リンクは duplicate symbol になる →
 * gui をリンクする構成では本 TU を外す。REPORT §4 参照)。
 */
#include "pump_internal.h"

#define STASH_N 64
#define PAINT_N 64
#define PWND_N  64

int g_initialized;   /* デバッグ用 */

static WMSG     g_held;
static int      g_held_valid;
static WMSG     g_stash[STASH_N];
static int      g_stash_n;
static void*    g_paints[PAINT_N];
static int      g_paint_n;
static struct { void* hwnd; PWNDPROC proc; } g_wnd[PWND_N];
static int      g_wnd_n;
static int      g_quit_posted;
static int      g_quit_code;

/* ---------------- 内部状態 ---------------- */
int ptake_held_valid(void) { return g_held_valid; }
void pstash_clear(void) { g_stash_n = 0; }

int ppaint_add(void* hwnd) {
    for (int i = 0; i < g_paint_n; i++)
        if (g_paints[i] == hwnd) return 1;   /* 既に有効 (Win32 InvalidateRect は重ねても 1 件) */
    if (g_paint_n >= PAINT_N) return 1;      /* 満杯は drop ではなく黙って間引く (fail-soft) */
    g_paints[g_paint_n++] = hwnd;
    return 1;
}

int pquit_post(int code) {
    g_quit_posted = 1;
    g_quit_code = code;
    __atomic_add_fetch(&g_pstat.quit_posts, 1u, __ATOMIC_RELAXED);
    return 1;
}

int pquit_taken(int* code) {
    if (!g_quit_posted) return 0;
    if (code) *code = g_quit_code;
    return 1;
}

void pwnd_register(void* hwnd, PWNDPROC proc) {
    for (int i = 0; i < g_wnd_n; i++)
        if (g_wnd[i].hwnd == hwnd) { g_wnd[i].proc = proc; return; }
    if (g_wnd_n < PWND_N) { g_wnd[g_wnd_n].hwnd = hwnd; g_wnd[g_wnd_n].proc = proc; g_wnd_n++; }
}

PWNDPROC pwnd_lookup(void* hwnd) {
    for (int i = 0; i < g_wnd_n; i++)
        if (g_wnd[i].hwnd == hwnd) return g_wnd[i].proc;
    return 0;
}

/* ---------------- フィルタと取り出し ---------------- */
static int filter_match(const PumpFilter* f, void* hwnd, uint32_t msg) {
    if (f->hwnd && f->hwnd != hwnd) return 0;
    if (!f->lo && !f->hi) return 1;
    return msg >= f->lo && msg <= f->hi;
}

static void log_pop_msg(uint32_t msg, double due_or_post, uint32_t aux) {
    plog_record(msg, pnow(), due_or_post, aux);
}

/* ring から 1 件 (フィルタ不一致は stash へ退避)。戻り値: 1=取得 / 0=空 */
static int take_from_ring(const PumpFilter* f, WMSG* out) {
    uint32_t raw[11];
    double t_post;
    while (pring_pop(raw, &t_post)) {
        __atomic_add_fetch(&g_pstat.pops, 1u, __ATOMIC_RELAXED);
        void* hwnd = (void*)(uintptr_t)raw[PR_S_HWND_LO];
        uint32_t msg = raw[PR_S_MSG];
        if (filter_match(f, hwnd, msg)) {
            out->hwnd = (uint64_t)(uintptr_t)hwnd;
            out->message = msg;
            out->wParam = (uint64_t)raw[PR_S_W_LO] | ((uint64_t)raw[PR_S_W_HI] << 32);
            out->lParam = (uint64_t)raw[PR_S_L_LO] | ((uint64_t)raw[PR_S_L_HI] << 32);
            out->time = raw[PR_S_TIME];
            out->pt_x = (int32_t)raw[PR_S_PTX];
            out->pt_y = (int32_t)raw[PR_S_PTY];
            log_pop_msg(msg, t_post, raw[PR_S_PTX]);
            return 1;
        }
        __atomic_add_fetch(&g_pstat.stash_skip, 1u, __ATOMIC_RELAXED);
        if (g_stash_n >= STASH_N) {
            /* stash 満杯: フィルタを無視して先頭を返す (fail-soft、順序はstash分だけ後ろへ) */
            __atomic_add_fetch(&g_pstat.stash_overflow, 1u, __ATOMIC_RELAXED);
            out->hwnd = (uint64_t)(uintptr_t)hwnd; out->message = msg;
            out->wParam = (uint64_t)raw[PR_S_W_LO] | ((uint64_t)raw[PR_S_W_HI] << 32);
            out->lParam = (uint64_t)raw[PR_S_L_LO] | ((uint64_t)raw[PR_S_L_HI] << 32);
            out->time = raw[PR_S_TIME];
            out->pt_x = (int32_t)raw[PR_S_PTX];
            out->pt_y = (int32_t)raw[PR_S_PTY];
            log_pop_msg(msg, t_post, raw[PR_S_PTX]);
            return 1;
        }
        g_stash[g_stash_n].hwnd = (uint64_t)(uintptr_t)hwnd;
        g_stash[g_stash_n].message = msg;
        g_stash[g_stash_n].wParam = (uint64_t)raw[PR_S_W_LO] | ((uint64_t)raw[PR_S_W_HI] << 32);
        g_stash[g_stash_n].lParam = (uint64_t)raw[PR_S_L_LO] | ((uint64_t)raw[PR_S_L_HI] << 32);
        g_stash[g_stash_n].time = raw[PR_S_TIME];
        g_stash[g_stash_n].pt_x = (int32_t)raw[PR_S_PTX];
        g_stash[g_stash_n].pt_y = (int32_t)raw[PR_S_PTY];
        g_stash_n++;
    }
    return 0;
}

static int take_from_stash(const PumpFilter* f, WMSG* out) {
    for (int i = 0; i < g_stash_n; i++) {
        if (filter_match(f, (void*)(uintptr_t)g_stash[i].hwnd, g_stash[i].message)) {
            *out = g_stash[i];
            for (int j = i; j + 1 < g_stash_n; j++) g_stash[j] = g_stash[j + 1];
            g_stash_n--;
            __atomic_add_fetch(&g_pstat.stash_hit, 1u, __ATOMIC_RELAXED);
            log_pop_msg(out->message, 0.0, 0);   /* stash 分の t_post は保持しない (遅延統計除外) */
            return 1;
        }
    }
    return 0;
}

int ptake(WMSG* out, const PumpFilter* f, int remove) {
    pctrl_service_done();   /* HOSTED/NONE 時の非同期応答完了 */
    /* 1. held (Peek PM_NOREMOVE / WaitMessage が覗いた同一メッセージ) */
    if (g_held_valid && filter_match(f, (void*)(uintptr_t)g_held.hwnd, g_held.message)) {
        *out = g_held;
        if (remove) { g_held_valid = 0; log_pop_msg(out->message, 0.0, 0); }
        return 1;
    }
    /* 2. stash (フィルタで退避済み) */
    if (take_from_stash(f, out)) return 1;
    /* 3. ring (投稿済みメッセージ) */
    if (take_from_ring(f, out)) {
        if (!remove) { g_held = *out; g_held_valid = 1; }
        return 1;
    }
    /* 4. QUIT (キューが空いてから。gui 実装と同様にフィルタ対象) */
    if (g_quit_posted && filter_match(f, 0, PWM_QUIT)) {
        int code = g_quit_code;
        out->hwnd = 0; out->message = PWM_QUIT; out->wParam = (uint64_t)(uint32_t)code;
        out->lParam = 0; out->time = (uint32_t)pnow(); out->pt_x = out->pt_y = 0;
        if (remove) { g_quit_posted = 0; log_pop_msg(PWM_QUIT, 0.0, 0); }
        return 1;
    }
    /* 5. PAINT (InvalidateRect 済み hwnd。低優先) */
    for (int i = 0; i < g_paint_n; i++) {
        if (filter_match(f, g_paints[i], PWM_PAINT)) {
            out->hwnd = (uint64_t)(uintptr_t)g_paints[i]; out->message = PWM_PAINT;
            out->wParam = 0; out->lParam = 0; out->time = (uint32_t)pnow();
            out->pt_x = out->pt_y = 0;
            for (int j = i; j + 1 < g_paint_n; j++) g_paints[j] = g_paints[j + 1];
            g_paint_n--;
            __atomic_add_fetch(&g_pstat.paints, 1u, __ATOMIC_RELAXED);
            if (!remove) { g_held = *out; g_held_valid = 1; }
            log_pop_msg(PWM_PAINT, 0.0, 0);
            return 1;
        }
    }
    /* 6. TIMER (最下優先・合流) */
    {
        void* th; uint64_t tid; PTIMERPROC proc; double due;
        if (ptimer_take_due(&th, &tid, &proc, &due)) {
            if (filter_match(f, th, PWM_TIMER)) {
                out->hwnd = (uint64_t)(uintptr_t)th; out->message = PWM_TIMER;
                out->wParam = tid; out->lParam = (uint64_t)(uintptr_t)proc;
                out->time = (uint32_t)pnow(); out->pt_x = out->pt_y = 0;
                if (!remove) { g_held = *out; g_held_valid = 1; }
                log_pop_msg(PWM_TIMER, due, (uint32_t)tid);   /* t_post に期待時刻 (遅延 = t_pop - due) */
                return 1;
            }
            /* フィルタが TIMER を排す場合は due 済を 1 周期先へ送って次回に回す */
        }
    }
    return 0;
}

static int any_pending(const PumpFilter* f) {
    WMSG tmp;
    return ptake(&tmp, f, 0);   /* held に残るので remove=0 で状態を壊さない */
}

/* ---------------- 強定義 (winstubs weak と同一シグネチャ) ---------------- */

BOOL PeekMessageW(LPVOID msg, HWND h, UINT lo, UINT hi, UINT rm) {
    pump_count();
    PumpFilter f = { h, lo, hi };
    if (ptake((WMSG*)msg, &f, (rm & PPM_REMOVE) ? 1 : 0)) return TRUE;
    return FALSE;
}

LONG GetMessageW(LPVOID msg, HWND h, UINT lo, UINT hi) {
    pump_count();
    PumpFilter f = { h, lo, hi };
    for (;;) {
        if (ptake((WMSG*)msg, &f, 1))
            return ((WMSG*)msg)->message == PWM_QUIT ? 0 : 1;
        switch (pump_eff_wait_mode()) {
            case PUMP_WAIT_HOSTED:
            case PUMP_WAIT_NONE:
                /* 待たない: 空は -1 (呼び出し側ループ継続)。HOSTED は pump_wait_ms() のヒントでホストが寝る */
                if (pump_eff_wait_mode() == PUMP_WAIT_NONE) __atomic_add_fetch(&g_pstat.nowait_empty, 1u, __ATOMIC_RELAXED);
                else __atomic_add_fetch(&g_pstat.hosted_empty, 1u, __ATOMIC_RELAXED);
                return -1;
            default:
                pump_wait_progress(&f);
                break;
        }
    }
}

BOOL TranslateMessage(const void* msg) {
    pump_count();
    const WMSG* m = (const WMSG*)msg;
    /* WM_CHAR 合成は下流 (キーレイアウト)。範囲判定だけは gui / worker_pump.ts と一致させる */
    return (m->message >= PWM_KEYDOWN && m->message <= PWM_SYSKEYUP) ? TRUE : FALSE;
}

LONG DispatchMessageW(const void* msg) {
    pump_count();
    const WMSG* m = (const WMSG*)msg;
    __atomic_add_fetch(&g_pstat.dispatched, 1u, __ATOMIC_RELAXED);
    if (m->message == PWM_TIMER && m->lParam) {
        PTIMERPROC proc = (PTIMERPROC)(uintptr_t)m->lParam;
        proc((void*)(uintptr_t)m->hwnd, PWM_TIMER, m->wParam, (uint32_t)pnow());
        return 0;
    }
    PWNDPROC proc = pwnd_lookup((void*)(uintptr_t)m->hwnd);
    if (proc) return (LONG)proc((void*)(uintptr_t)m->hwnd, m->message, m->wParam, m->lParam);
    __atomic_add_fetch(&g_pstat.wndproc_miss, 1u, __ATOMIC_RELAXED);
    return 0;
}

BOOL PostMessageW(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp) {
    pump_count();
    if (!pring_push(h, m, wp, lp, pnow())) {
        __atomic_add_fetch(&g_pstat.push_full, 1u, __ATOMIC_RELAXED);
        return FALSE;
    }
    __atomic_add_fetch(&g_pstat.pushes, 1u, __ATOMIC_RELAXED);
    return TRUE;
}

LRESULT_T SendMessageW(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp) {
    pump_count();
    __atomic_add_fetch(&g_pstat.sent_calls, 1u, __ATOMIC_RELAXED);
    /* 同一スレッドの SendMessage は直接呼出 (Win32 同様)。wndproc 未登録は fail-soft で 0 */
    PWNDPROC proc = pwnd_lookup(h);
    if (proc) return (LRESULT_T)(uint32_t)(int64_t)proc(h, m, wp, lp);
    __atomic_add_fetch(&g_pstat.wndproc_miss, 1u, __ATOMIC_RELAXED);
    return 0;
}

void PostQuitMessage(int code) {
    pump_count();
    pquit_post(code);
}

UINT_PTR_T SetTimer(HWND h, UINT_PTR_T id, UINT ms, LPVOID fn) {
    pump_count();
    int r = ptimer_set(h, (uint64_t)id, ms, (PTIMERPROC)(uintptr_t)fn);
    return (UINT_PTR_T)(uint32_t)r;
}

BOOL KillTimer(HWND h, UINT_PTR_T id) {
    pump_count();
    return ptimer_kill(h, (uint64_t)id) ? TRUE : FALSE;
}

BOOL WaitMessage(void) {
    pump_count();
    PumpFilter f = { 0, 0, 0 };
    if (any_pending(&f)) return TRUE;
    switch (pump_eff_wait_mode()) {
        case PUMP_WAIT_HOSTED:
        case PUMP_WAIT_NONE:
            return FALSE;   /* 待たない (HOSTED は pump_wait_ms() を見て再呼出) */
        default:
            for (;;) {
                if (any_pending(&f)) return TRUE;
                pump_wait_progress(&f);
            }
    }
}

BOOL PostMessageA(HWND h, UINT m, UINT_PTR_T wp, LPARAM_T lp) { return PostMessageW(h, m, wp, lp); }

BOOL PeekMessageA(LPVOID msg, HWND h, UINT lo, UINT hi, UINT rm) { return PeekMessageW(msg, h, lo, hi, rm); }

LONG GetMessageA(LPVOID msg, HWND h, UINT lo, UINT hi) { return GetMessageW(msg, h, lo, hi); }

LONG DispatchMessageA(const void* msg) { return DispatchMessageW(msg); }

BOOL PostThreadMessageW(DWORD tid, UINT m, UINT_PTR_T wp, LPARAM_T lp) {
    /* スレッドキューは UI スレッド 1 本 (wasm UI スレッド) に統一: tid は記録のみ */
    pump_count();
    (void)tid;
    if (!pring_push(0, m, wp, lp, pnow())) {
        __atomic_add_fetch(&g_pstat.push_full, 1u, __ATOMIC_RELAXED);
        return FALSE;
    }
    __atomic_add_fetch(&g_pstat.pushes, 1u, __ATOMIC_RELAXED);
    return TRUE;
}

/* MsgWaitForMultipleObjects: 新着入力は WAIT_OBJECT_0 + nCount (Win32 仕様)。ハンドルは WAIT_OBJECT_0 + i。
 * ハンドル待ちは shimx WaitForMultipleObjects (強定義) に委譲し、スライス毎にメッセージを横取りする。 */
DWORD MsgWaitForMultipleObjects(DWORD n, const HANDLE* hs, BOOL all, DWORD ms, DWORD mask) {
    pump_count();
    (void)mask;
    if (n > 64u) { SetLastError(87u /* ERROR_INVALID_PARAMETER */); return WAIT_FAILED; }
    double deadline = (ms == INFINITE) ? PINF : pnow() + (double)ms;
    if (n == 0) {
        PumpFilter f = { 0, 0, 0 };
        for (;;) {
            if (any_pending(&f)) return WAIT_OBJECT_0 + 0u;   /* 入力あり */
            double now = pnow();
            if (ms == 0 || now >= deadline) return WAIT_TIMEOUT;
            if (pump_eff_wait_mode() == PUMP_WAIT_HOSTED || pump_eff_wait_mode() == PUMP_WAIT_NONE) return WAIT_TIMEOUT;
            pump_wait_progress(&f);
        }
    }
    for (;;) {
        double now = pnow();
        double remain = (deadline >= PINF) ? g_slice_ms : (deadline - now);
        if (remain > g_slice_ms) remain = g_slice_ms;
        if (remain < 0.0) remain = 0.0;
        DWORD r = WaitForMultipleObjects(n, hs, all, (DWORD)remain);
        if (r != WAIT_TIMEOUT) return r;
        PumpFilter f = { 0, 0, 0 };
        if (any_pending(&f)) return WAIT_OBJECT_0 + n;
        if (pnow() >= deadline) return WAIT_TIMEOUT;
        if (pump_eff_wait_mode() == PUMP_WAIT_HOSTED || pump_eff_wait_mode() == PUMP_WAIT_NONE) return WAIT_TIMEOUT;
    }
}

DWORD MsgWaitForMultipleObjectsEx(DWORD n, const HANDLE* hs, DWORD ms, DWORD mask, DWORD flags) {
    return MsgWaitForMultipleObjects(n, hs, (flags & 1u) /* MWMO_WAITALL */ ? TRUE : FALSE, ms, mask);
}

BOOL InvalidateRect(HWND h, const void* rect, BOOL erase) {
    pump_count();
    (void)rect; (void)erase;
    return ppaint_add(h) ? TRUE : FALSE;
}
