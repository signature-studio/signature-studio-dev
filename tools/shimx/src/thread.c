/* スレッド / プロセス擬似ハンドル / Timer queue。
 *
 * M4 差分:
 *   - CREATE_SUSPENDED 対応 (ResumeThread で起動ゲートを開く)
 *   - CreateThread の threadId を *新スレッドの* ID で返す (M4 は作成側 ID を返していた)
 *   - 全スレッド detached。終了検出は ShxObj.state + 全体 notify。ハンドルを閉じても終了しない (Win 準拠)
 *   - SuspendThread は *スタブ*: 実行中スレッドは止められない (カウントのみ)。TerminateThread も状態のみ。
 */
#include "shimx_internal.h"

extern volatile uint32_t g_shx_sig_seq;

#if defined(__EMSCRIPTEN__)
int emscripten_num_logical_cores(void);
#endif
#define SHX_PROC_ID 0x1000

DWORD GetCurrentThreadId(void) { return shx_tid(); }
HANDLE GetCurrentThread(void) { return (HANDLE)-2; }
HANDLE GetCurrentProcess(void) { return (HANDLE)-1; }
DWORD GetCurrentProcessId(void) { return SHX_PROC_ID; }

DWORD GetThreadId(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return 0; }
    DWORD t = o->tid;
    shx_unref(o);
    return t;
}
DWORD GetProcessId(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_PROCESS);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return 0; }
    shx_unref(o);
    return SHX_PROC_ID;
}

HANDLE OpenProcess(DWORD access, BOOL inherit, DWORD pid) {
    (void)access; (void)inherit;
    if (pid != SHX_PROC_ID) { shx_set_last_error(ERROR_INVALID_PARAMETER); return 0; }
    ShxObj* o = shx_ref((HANDLE)-1, OBJ_PROCESS);   /* refs++ 済み */
    HANDLE h = shx_handle_new(o);
    if (h) shx_set_last_error(ERROR_SUCCESS);
    return h;
}

BOOL GetExitCodeProcess(HANDLE h, LPDWORD code) {
    ShxObj* o = shx_ref(h, OBJ_PROCESS);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    if (code) *code = o->state ? o->exit_code : STILL_ACTIVE;
    shx_unref(o);
    return TRUE;
}

BOOL SetPriorityClass(HANDLE h, DWORD cls) { (void)h; (void)cls; return TRUE; }
DWORD GetPriorityClass(HANDLE h) { (void)h; return NORMAL_PRIORITY_CLASS; }
DWORD SetThreadExecutionState(DWORD flags) { (void)flags; return 0x80000000u; }
BOOL GetProcessAffinityMask(HANDLE h, ULONG_PTR* proc, ULONG_PTR* sys) {
    (void)h;
    int n = 8;
#if defined(__EMSCRIPTEN__)
    n = emscripten_num_logical_cores();
    if (n < 1) n = 1;
    if (n > 31) n = 31;
#endif
    ULONG_PTR m = ((ULONG_PTR)1 << n) - 1;
    if (proc) *proc = m;
    if (sys) *sys = m;
    return TRUE;
}
BOOL SetProcessAffinityMask(HANDLE h, ULONG_PTR mask) { (void)h; (void)mask; return TRUE; }

/* ---------------------------------------------------------------
 * スレッド
 * --------------------------------------------------------------- */
void shx_thread_destroy(ShxObj* o) { (void)o; }

#if defined(__EMSCRIPTEN_PTHREADS__)
static void thread_finish(ShxObj* o, DWORD rc) {
    shx_thread_exit_cleanup();
    shx_lock();
    o->exit_code = rc;
    o->state = 1;
    shx_unlock();
    shx_notify();
    shx_clear_self();
    shx_unref(o);                 /* スレッド自身の内部参照 */
}

static void* thread_trampoline(void* raw) {
    ShxObj* o = (ShxObj*)raw;
    shx_set_self(o);              /* 内部参照を thread-local へ移譲 (終了時 thread_finish で解放) */
    while (__atomic_load_n(&o->gate, __ATOMIC_SEQ_CST) == 0)
        shx_futex_wait(&o->gate, 0u, INFINITY);
    DWORD rc = o->fn(o->param);
    thread_finish(o, rc);
    return NULL;
}
#endif

HANDLE CreateThread(LPSECURITY_ATTRIBUTES sa, SIZE_T stackSize, LPTHREAD_START_ROUTINE start,
                    LPVOID param, DWORD flags, LPDWORD threadId) {
    (void)sa;
    shx_ensure_init();
    if (!start) { shx_set_last_error(ERROR_INVALID_PARAMETER); return 0; }
#if defined(__EMSCRIPTEN_PTHREADS__)
    ShxObj* o = shx_obj_new(OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_NOT_ENOUGH_MEMORY); return 0; }
    o->fn = start;
    o->param = param;
    o->tid = shx_alloc_tid();
    o->refs = 2;                  /* ハンドル + スレッド内部参照 */
    o->joined = 1;
    o->exit_code = STILL_ACTIVE;
    o->affinity = 1;
    if (flags & CREATE_SUSPENDED) { o->suspend_count = 1; o->gate = 0; }
    else o->gate = 1;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    if (stackSize >= 65536) pthread_attr_setstacksize(&attr, stackSize);
    pthread_t pt;
    int rc = pthread_create(&pt, &attr, thread_trampoline, o);
    pthread_attr_destroy(&attr);
    if (rc != 0) {
        o->refs = 1;
        shx_unref(o);
        shx_set_last_error(ERROR_NOT_ENOUGH_MEMORY);
        return 0;
    }
    o->started = 1;
    HANDLE h = shx_handle_new(o);
    if (!h) return 0;
    if (threadId) *threadId = o->tid;
    shx_set_last_error(ERROR_SUCCESS);
    return h;
#else
    (void)stackSize; (void)param; (void)flags; (void)threadId;
    shim_unimplemented("CreateThread (シングルスレッドビルド)");
    return 0;
#endif
}

void ExitThread(DWORD exitCode) {
#if defined(__EMSCRIPTEN_PTHREADS__)
    ShxObj* o = shx_self_thread_obj();      /* refs++ */
    if (!o->fn) {                            /* 外来スレッド (main 等) */
        shx_unref(o);
        shim_unimplemented("ExitThread (non-CreateThread thread)");
    }
    shx_unref(o);
    thread_finish(o, exitCode);
    pthread_exit(NULL);
#else
    (void)exitCode;
    shim_unimplemented("ExitThread (シングルスレッドビルド)");
#endif
}

BOOL TerminateThread(HANDLE h, DWORD code) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    /* pthread を強制停止する手段は無い。待機者を解放するため状態だけ完了にする (スタブ) */
    shx_lock(); o->exit_code = code; o->state = 1; shx_unlock();
    shx_notify();
    SHX_TRACE("TerminateThread: tid=%u 状態のみ完了扱い (実体は継続し得る)", o->tid);
    shx_unref(o);
    return TRUE;
}

DWORD SuspendThread(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return (DWORD)-1; }
    DWORD prev = (DWORD)__atomic_fetch_add(&o->suspend_count, 1, __ATOMIC_SEQ_CST);
    shx_unref(o);
    return prev;
}

DWORD ResumeThread(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return (DWORD)-1; }
    shx_lock();
    DWORD prev = (DWORD)o->suspend_count;
    if (o->suspend_count > 0) o->suspend_count--;
    int open = (o->suspend_count == 0);
    shx_unlock();
    if (open && o->gate == 0) {
        __atomic_store_n(&o->gate, 1u, __ATOMIC_SEQ_CST);
        shx_futex_wake(&o->gate, 0x7fffffff);
    }
    shx_unref(o);
    return prev;
}

BOOL GetExitCodeThread(HANDLE h, LPDWORD code) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    if (code) *code = o->state ? o->exit_code : STILL_ACTIVE;
    shx_unref(o);
    return TRUE;
}

BOOL SetThreadPriority(HANDLE h, int prio) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    o->prio = prio;
    shx_unref(o);
    return TRUE;
}
int GetThreadPriority(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return THREAD_PRIORITY_ERROR_RETURN; }
    int p = o->prio;
    shx_unref(o);
    return p;
}
ULONG_PTR SetThreadAffinityMask(HANDLE h, ULONG_PTR mask) {
    ShxObj* o = shx_ref(h, OBJ_THREAD);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return 0; }
    ULONG_PTR prev = o->affinity ? o->affinity : 1;
    o->affinity = mask;
    shx_unref(o);
    return prev;
}

void FreeLibraryAndExitThread(HMODULE m, DWORD code) {
    FreeLibrary(m);
    ExitThread(code);
}

/* ---------------------------------------------------------------
 * Timer queue (専用ワーカー thread 1 本。MT ビルドのみ)
 * --------------------------------------------------------------- */
typedef struct ShxTimer {
    struct ShxTimer* next;
    WAITORTIMERCALLBACK cb;
    void* param;
    double due;
    DWORD period;
    HANDLE queue;
    int active, running, deleted;
} ShxTimer;

static ShxTimer* g_timers;
static volatile uint32_t g_tq_seq;
static int g_tq_started;

#if defined(__EMSCRIPTEN_PTHREADS__)
static void* tq_thread(void* arg) {
    (void)arg;
    for (;;) {
        uint32_t seq = __atomic_load_n(&g_tq_seq, __ATOMIC_SEQ_CST);
        shx_lock();
        ShxTimer* best = NULL;
        for (ShxTimer* t = g_timers; t; t = t->next)
            if (t->active && (!best || t->due < best->due)) best = t;
        double now = shx_now_ms();
        if (best && best->due <= now) {
            WAITORTIMERCALLBACK cb = best->cb;
            void* p = best->param;
            if (best->period) best->due = now + best->period; else best->active = 0;
            best->running++;
            shx_unlock();
            if (cb) cb(p, TRUE);
            shx_lock();
            best->running--;
            if (best->deleted && best->running == 0) free(best);
            shx_unlock();
            continue;
        }
        double wait = best ? best->due - now : INFINITY;
        shx_unlock();
        shx_futex_wait(&g_tq_seq, seq, wait);
    }
    return NULL;
}
#endif

static void tq_poke(void) {
    __atomic_add_fetch(&g_tq_seq, 1u, __ATOMIC_SEQ_CST);
    shx_futex_wake(&g_tq_seq, 1);
}

HANDLE CreateTimerQueue(void) {
    ShxObj* o = shx_obj_new(OBJ_TIMERQ);
    return o ? shx_handle_new(o) : 0;
}

BOOL CreateTimerQueueTimer(LPHANDLE timer, HANDLE queue, WAITORTIMERCALLBACK cb, PVOID param,
                           DWORD due, DWORD period, ULONG flags) {
    (void)flags;
    shx_ensure_init();
#if defined(__EMSCRIPTEN_PTHREADS__)
    if (!timer || !cb) { shx_set_last_error(ERROR_INVALID_PARAMETER); return FALSE; }
    ShxTimer* t = (ShxTimer*)calloc(1, sizeof(*t));
    if (!t) { shx_set_last_error(ERROR_NOT_ENOUGH_MEMORY); return FALSE; }
    t->cb = cb; t->param = param; t->period = period; t->queue = queue;
    t->due = shx_now_ms() + due; t->active = 1;
    int need_thread = 0;
    shx_lock();
    t->next = g_timers; g_timers = t;
    if (!g_tq_started) { g_tq_started = 1; need_thread = 1; }
    shx_unlock();
    if (need_thread) {
        pthread_attr_t attr; pthread_t pt;
        pthread_attr_init(&attr);
        pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
        if (pthread_create(&pt, &attr, tq_thread, NULL) != 0) {
            pthread_attr_destroy(&attr);
            shx_set_last_error(ERROR_NOT_ENOUGH_MEMORY);
            return FALSE;
        }
        pthread_attr_destroy(&attr);
    }
    tq_poke();
    *timer = (HANDLE)t;
    shx_set_last_error(ERROR_SUCCESS);
    return TRUE;
#else
    (void)timer; (void)queue; (void)cb; (void)param; (void)due; (void)period;
    shim_unimplemented("CreateTimerQueueTimer (シングルスレッドビルド)");
    return FALSE;
#endif
}

BOOL ChangeTimerQueueTimer(HANDLE queue, HANDLE timer, ULONG due, ULONG period) {
    (void)queue;
    int ok = 0;
    shx_lock();
    for (ShxTimer* t = g_timers; t; t = t->next)
        if ((HANDLE)t == timer && !t->deleted) {
            t->due = shx_now_ms() + due; t->period = period; t->active = 1; ok = 1; break;
        }
    shx_unlock();
    if (!ok) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    tq_poke();
    return TRUE;
}

BOOL DeleteTimerQueueTimer(HANDLE queue, HANDLE timer, HANDLE completion) {
    (void)queue;
    ShxTimer* found = NULL;
    int blocking = (completion == INVALID_HANDLE_VALUE);
    shx_lock();
    ShxTimer** pp = &g_timers;
    while (*pp) {
        if ((HANDLE)*pp == timer) { found = *pp; *pp = found->next; break; }
        pp = &(*pp)->next;
    }
    int running = 0;
    if (found) {
        found->active = 0;
        running = found->running;
        if (running > 0 && !blocking) found->deleted = 1;   /* ワーカーが free */
    }
    shx_unlock();
    if (!found) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    if (running == 0) free(found);
    else if (blocking) {
        for (;;) {                       /* リストから外れているのでワーカーは free しない */
            shx_lock(); int r = found->running; shx_unlock();
            if (r == 0) break;
            Sleep(1);
        }
        free(found);
    }
    shx_set_last_error(ERROR_SUCCESS);
    return TRUE;
}

BOOL DeleteTimerQueueEx(HANDLE q, HANDLE completion) {
    (void)completion;
    shx_lock();
    for (ShxTimer* t = g_timers; t; t = t->next)
        if (t->queue == q) t->active = 0;
    shx_unlock();
    return CloseHandle(q);
}

/* ---------------------------------------------------------------
 * Thread pool work (最小): Submit のたびに専用スレッドでコールバックを 1 回実行
 * --------------------------------------------------------------- */
typedef void (*PTP_WORK_CALLBACK)(void* instance, void* ctx, void* work);
typedef struct { PTP_WORK_CALLBACK cb; void* ctx; volatile int pending; volatile int closed; } ShxWork;

void* CreateThreadpoolWork(PTP_WORK_CALLBACK cb, void* ctx, void* env) {
    (void)env;
    if (!cb) { shx_set_last_error(ERROR_INVALID_PARAMETER); return NULL; }
    ShxWork* w = (ShxWork*)calloc(1, sizeof(ShxWork));
    if (!w) { shx_set_last_error(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    w->cb = cb; w->ctx = ctx;
    return w;
}
static DWORD work_thread(LPVOID p) {
    ShxWork* w = (ShxWork*)p;
    w->cb(NULL, w->ctx, w);
    int pend = __atomic_sub_fetch(&w->pending, 1, __ATOMIC_SEQ_CST);
    if (pend == 0 && w->closed) free(w);
    return 0;
}
void SubmitThreadpoolWork(void* work) {
    ShxWork* w = (ShxWork*)work;
    if (!w) return;
    __atomic_add_fetch(&w->pending, 1, __ATOMIC_SEQ_CST);
    HANDLE h = CreateThread(NULL, 0, work_thread, w, 0, NULL);
    if (h) CloseHandle(h);
    else __atomic_sub_fetch(&w->pending, 1, __ATOMIC_SEQ_CST);
}
void CloseThreadpoolWork(void* work) {
    ShxWork* w = (ShxWork*)work;
    if (!w) return;
    w->closed = 1;
    if (__atomic_load_n(&w->pending, __ATOMIC_SEQ_CST) == 0) free(w);
}
void FreeLibraryWhenCallbackReturns(void* instance, HMODULE m) { (void)instance; (void)m; }
HANDLE CreateIoCompletionPort(HANDLE file, HANDLE port, ULONG_PTR key, DWORD threads) {
    (void)file; (void)port; (void)key; (void)threads; shx_set_last_error(ERROR_NOT_SUPPORTED); return 0;
}
BOOL GetQueuedCompletionStatus(HANDLE port, LPDWORD n, ULONG_PTR* key, LPOVERLAPPED* ov, DWORD ms) {
    (void)port; (void)n; (void)key; (void)ov; (void)ms; shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE;
}
