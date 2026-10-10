/* pump_wait.c — 空キューでの待機チャンク (GetMessage / WaitMessage / MsgWait 共通)。
 *
 * 戦略ごとの振る舞い (e2e で遅延とコストを計測する):
 *   ATOMIC : memory.atomic.wait32(wake 語, 期待値, min(next_due, wait_cap)) — 本命。
 *            タイマ満期を futex タイムアウトに畳み込む (worker_pump.ts MessagePump.waitForMessage と同一)。
 *   SLICE  : 同 futex を g_slice_ms (既定 5ms) 刻みで繰り返す (長時間待ちの分割・応答性確認用)。
 *   SPIN   : wake 語のビジー比較 (無待機スレッドでの極短待ち。CPU を消費するため計測用)。
 *   HOSTED / NONE : 待たない (呼び出し側に返る。HOSTED は pump_wait_ms() の待ち時間ヒントをホストが使う)。
 *
 * 戻るタイミング: メッセージが取り出せる可能性が生じたとき / タイマ満期 / wait_cap 経過。
 * タイマ満期は待機に入る前に next_due を計算し、futex のタイムアウトとして目覚める。
 */
#include "pump_internal.h"

int    g_wait_mode = -1;     /* -1 = 未設定 → pump_default_wait_mode() で決める */
double g_slice_ms = 5.0;
double g_wait_cap_ms = 1000.0;

int pump_default_wait_mode(void) {
#ifdef __EMSCRIPTEN_PTHREADS__
    return PUMP_WAIT_ATOMIC;
#else
    return PUMP_WAIT_HOSTED;
#endif
}

int pump_eff_wait_mode(void) { return g_wait_mode < 0 ? pump_default_wait_mode() : g_wait_mode; }

void pump_set_slice_ms(int ms) { if (ms > 0) g_slice_ms = (double)ms; }
void pump_set_wait_cap_ms(int ms) { if (ms > 0) g_wait_cap_ms = (double)ms; }

/* キューが空のときに 1 チャンク待つ。f は呼び出し中のフィルタ (タイマはフィルタ外で満期判定)。 */
void pump_wait_progress(const PumpFilter* f) {
    (void)f;
    double now = pnow();
    double due = ptimer_next_due();
    double timeout = (due >= PINF) ? g_wait_cap_ms : (due - now);
    if (timeout > g_wait_cap_ms) timeout = g_wait_cap_ms;
    if (timeout < 0.0) return;   /* タイマ満期済 → 呼び出し側の take が拾う */
    switch (g_wait_mode) {
        case PUMP_WAIT_SPIN: {
            /* ビジーウェイト: wake 語の変化 or 満期まで */
            __atomic_add_fetch(&g_pstat.waits_spin, 1u, __ATOMIC_RELAXED);
            int32_t wake = pring_wake();
            double deadline = now + timeout;
            while (pnow() < deadline) {
                if (pring_wake() != wake) break;
                if (ptimer_next_due() <= pnow()) break;
            }
            break;
        }
        case PUMP_WAIT_SLICE: {
            __atomic_add_fetch(&g_pstat.waits_slice, 1u, __ATOMIC_RELAXED);
            __atomic_add_fetch(&g_pstat.wait_chunks, 1u, __ATOMIC_RELAXED);
            double s = (g_slice_ms < timeout) ? g_slice_ms : timeout;
#ifdef __EMSCRIPTEN_PTHREADS__
            int rc = (int)__builtin_wasm_memory_atomic_wait32((int32_t*)&g_pring.hdr[PR_H_WAKE],
                                                              pring_wake(), (int64_t)(s * 1e6));
            if (rc == 2) __atomic_add_fetch(&g_pstat.wait_chunks_timedout, 1u, __ATOMIC_RELAXED);
#endif
            break;
        }
        case PUMP_WAIT_ATOMIC: {
            __atomic_add_fetch(&g_pstat.waits_atomic, 1u, __ATOMIC_RELAXED);
            __atomic_add_fetch(&g_pstat.wait_chunks, 1u, __ATOMIC_RELAXED);
#ifdef __EMSCRIPTEN_PTHREADS__
            int rc = (int)__builtin_wasm_memory_atomic_wait32((int32_t*)&g_pring.hdr[PR_H_WAKE],
                                                              pring_wake(), (int64_t)(timeout * 1e6));
            if (rc == 2) __atomic_add_fetch(&g_pstat.wait_chunks_timedout, 1u, __ATOMIC_RELAXED);
#endif
            break;
        }
        default:
            /* HOSTED / NONE: 待たない (呼び出し側が即 return する前提で到達しない) */
            break;
    }
}
