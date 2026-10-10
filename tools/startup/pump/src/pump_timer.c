/* pump_timer.c — C 側タイマテーブルと WM_TIMER 合成。
 * Win32 同様、WM_TIMER はキューに溜めずポンプ時に合成 (低優先・合流)。
 * 遅延時は 1 周期に丸める (worker_pump.ts MessagePump と同一: due = max(due+interval, now))。
 * gui 経路 (tools/gui) は gui 独自のタイマを持つ → 本テーブルは boot 経路用の別構成。
 */
#include "pump_internal.h"

#define PTIMER_MAX 128

typedef struct PTimer {
    int in_use;
    void* hwnd;
    uint64_t id;
    double interval, due;
    PTIMERPROC proc;
} PTimer;

static PTimer g_timers[PTIMER_MAX];
static uint64_t g_next_auto_id = 1;   /* SetTimer(id=0) の自動採番 */

int ptimer_set(void* hwnd, uint64_t id, uint32_t ms, PTIMERPROC proc) {
    double now = pnow();
    double interval = (double)(ms < 1u ? 1u : ms);
    if (id == 0) {   /* Win32: 新規 id を採番して返す */
        for (int attempt = 0; attempt < PTIMER_MAX; attempt++) {
            int used = 0;
            for (int i = 0; i < PTIMER_MAX; i++)
                if (g_timers[i].in_use && g_timers[i].id == g_next_auto_id) { used = 1; break; }
            if (!used) { id = g_next_auto_id; break; }
            g_next_auto_id++;
        }
        if (id == 0) return 0;
    }
    for (int i = 0; i < PTIMER_MAX; i++) {
        if (g_timers[i].in_use && g_timers[i].hwnd == hwnd && g_timers[i].id == id) {
            g_timers[i].interval = interval;
            g_timers[i].due = now + interval;   /* 再設定: 満期をリセット (Win32 同様) */
            g_timers[i].proc = proc;
            return (int)(id & 0x7fffffffu);
        }
    }
    for (int i = 0; i < PTIMER_MAX; i++) {
        if (!g_timers[i].in_use) {
            g_timers[i] = (PTimer){ 1, hwnd, id, interval, now + interval, proc };
            g_next_auto_id = id + 1;
            __atomic_add_fetch(&g_pstat.timers_set, 1u, __ATOMIC_RELAXED);
            return (int)(id & 0x7fffffffu);
        }
    }
    return 0;   /* テーブル満杯 (Win32 もテーブル不足で NULL) */
}

int ptimer_kill(void* hwnd, uint64_t id) {
    for (int i = 0; i < PTIMER_MAX; i++) {
        if (g_timers[i].in_use && g_timers[i].hwnd == hwnd && g_timers[i].id == id) {
            g_timers[i].in_use = 0;
            __atomic_add_fetch(&g_pstat.timers_killed, 1u, __ATOMIC_RELAXED);
            return 1;
        }
    }
    return 0;   /* Win32: 見つからなければ FALSE */
}

double ptimer_next_due(void) {
    double d = PINF;
    for (int i = 0; i < PTIMER_MAX; i++)
        if (g_timers[i].in_use && g_timers[i].due < d) d = g_timers[i].due;
    return d;
}

/* due 到着分を 1 件取り出す (最も古い due を優先)。呼び出し側は take() 優先順の最後に呼ぶ。 */
int ptimer_take_due(void** hwnd, uint64_t* id, PTIMERPROC* proc, double* due) {
    const double now = pnow();
    int best = -1;
    for (int i = 0; i < PTIMER_MAX; i++)
        if (g_timers[i].in_use && g_timers[i].due <= now && (best < 0 || g_timers[i].due < g_timers[best].due))
            best = i;
    if (best < 0) return 0;
    PTimer* t = &g_timers[best];
    *hwnd = t->hwnd;
    *id = t->id;
    *proc = t->proc;
    *due = t->due;
    t->due = (t->due + t->interval > now) ? t->due + t->interval : now;   /* 遅延は 1 周期に丸める */
    __atomic_add_fetch(&g_pstat.timers_fired, 1u, __ATOMIC_RELAXED);
    return 1;
}

uint32_t ptimer_count(void) {
    uint32_t n = 0;
    for (int i = 0; i < PTIMER_MAX; i++) n += (uint32_t)g_timers[i].in_use;
    return n;
}
