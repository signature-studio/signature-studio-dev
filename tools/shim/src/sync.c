/* thread / sync 相当 (§3 #4 の P0 最小面)。
 * - CRITICAL_SECTION はクライアント確保メモリ (ポインタ) をキーに shim 内部で
 *   pthread_mutex を管理 (Delphi は自前 40byte 構造体を渡すため、shim 側で
 *   上書きせずポインタ対応表で写影する)。
 * - CreateThread → pthread、終了検出は SAB 上の done フラグ + futex_wake。
 *   WaitForSingleObject(HANDLE, timeout) は futex_wait ループで実装。
 * - TLS は pthread_getspecific ベース (スレッドごとに index 配列)。
 * - シングルスレッド (非 pthread) ビルドでは CreateThread / ExitThread は
 *   fail-fast、CS/recursion は単一スレッド前提の近似動作。
 */
#include "shim.h"
#include "shim_internal.h"
#include <math.h>
#include <errno.h>

/* ---------------------------------------------------------------
 * スレッド (§3 #4)
 * --------------------------------------------------------------- */
static DWORD g_main_thread_id = 1;

DWORD GetCurrentThreadId(void) {
#if defined(__EMSCRIPTEN_PTHREADS__)
    /* 素朴な一意化: pthread_self() 値をハッシュ (衝突時の影響は
     * 表示/所有者管理のみで、必ず非 0 にする) */
    uintptr_t v = (uintptr_t)pthread_self();
    v *= 2654435761u;
    return (DWORD)(v >> 3) | 1u;
#else
    return g_main_thread_id;
#endif
}

#if defined(__EMSCRIPTEN_PTHREADS__)
static void* thread_trampoline(void* raw) {
    ShimSlot* s = (ShimSlot*)raw;
    DWORD rc = s->fn(s->param);
    s->exit_code = rc;
    __atomic_store_n(&s->done, 1u, __ATOMIC_SEQ_CST);
    emscripten_futex_wake((volatile void*)&s->done, INT32_MAX);
    return NULL;
}
#endif

HANDLE CreateThread(LPSECURITY_ATTRIBUTES sa, SIZE_T stackSize,
                    LPTHREAD_START_ROUTINE start, LPVOID param,
                    DWORD flags, LPDWORD threadId) {
    (void)sa; (void)stackSize; (void)flags;
    if (!start) { SetLastError(ERROR_INVALID_PARAMETER); return INVALID_HANDLE_VALUE; }
#if defined(__EMSCRIPTEN_PTHREADS__)
    ShimSlot* s = shim_alloc_slot(SHIM_TYPE_THREAD);
    if (!s) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE_VALUE; }
    s->fn = start;
    s->param = param;
    if (pthread_create(&s->pt, NULL, thread_trampoline, s) != 0) {
        shim_free_slot(s);
        SetLastError(ERROR_NOT_ENOUGH_MEMORY);
        return INVALID_HANDLE_VALUE;
    }
    if (threadId) *threadId = GetCurrentThreadId();
    SetLastError(ERROR_SUCCESS);
    return shim_handle_from_slot(s);
#else
    (void)param; (void)threadId;
    shim_unimplemented("CreateThread (シングルスレッドビルド)");
    return INVALID_HANDLE_VALUE;
#endif
}

void ExitThread(DWORD exitCode) {
#if defined(__EMSCRIPTEN_PTHREADS__)
    /* 自スレッドの slot を探索し、done フラグ + wake を済ませてから
     * pthread_exit する (routine 内からの強制終了でも待機者を閉じ込めない)。 */
    pthread_t self = pthread_self();
    for (int i = 0; i < SHIM_MAX_HANDLES; i++) {
        ShimSlot* s = &g_slots[i];
        if (s->used && s->type == SHIM_TYPE_THREAD && !s->joined &&
            pthread_equal(s->pt, self)) {
            s->exit_code = exitCode;
            __atomic_store_n(&s->done, 1u, __ATOMIC_SEQ_CST);
            emscripten_futex_wake((volatile void*)&s->done, INT32_MAX);
            break;
        }
    }
    pthread_exit((void*)(uintptr_t)exitCode);
#else
    (void)exitCode;
    shim_unimplemented("ExitThread (シングルスレッドビルド)");
#endif
}

/* ---------------------------------------------------------------
 * WaitForSingleObject (§3 #4) — thread / event のみ v1 対応
 * --------------------------------------------------------------- */
static double shim_now(void) {
    return emscripten_get_now();
}

static DWORD wait_event_slot(ShimSlot* s, double deadline) {
    volatile uint32_t* w = &s->state;
    for (;;) {
        uint32_t v = __atomic_load_n(w, __ATOMIC_SEQ_CST);
        if (v) {
            if (!s->manual_reset)
                __atomic_store_n(w, 0u, __ATOMIC_SEQ_CST);
            return WAIT_OBJECT_0;
        }
        double remain = deadline - shim_now();
        if (remain <= 0.0) return WAIT_TIMEOUT;
        emscripten_futex_wait((volatile void*)w, v, remain);
    }
}

#if defined(__EMSCRIPTEN_PTHREADS__)
static DWORD wait_thread_slot(ShimSlot* s, double deadline) {
    volatile uint32_t* w = &s->done;
    for (;;) {
        uint32_t v = __atomic_load_n(w, __ATOMIC_SEQ_CST);
        if (v) {
            if (!s->joined) {
                pthread_join(s->pt, NULL);
                s->joined = 1;
            }
            return WAIT_OBJECT_0;
        }
        double remain = deadline - shim_now();
        if (remain <= 0.0) return WAIT_TIMEOUT;
        emscripten_futex_wait((volatile void*)w, v, remain);
    }
}
#endif

DWORD WaitForSingleObject(HANDLE h, DWORD ms) {
    ShimSlot* s = shim_slot_lookup(h);
    if (!s) { SetLastError(ERROR_INVALID_FUNCTION); return WAIT_FAILED; }
    double deadline = (ms == INFINITE) ? INFINITY : shim_now() + (double)ms;
    DWORD rc;
    switch (s->type) {
        case SHIM_TYPE_EVENT:  rc = wait_event_slot(s, deadline); break;
#if defined(__EMSCRIPTEN_PTHREADS__)
        case SHIM_TYPE_THREAD: rc = wait_thread_slot(s, deadline); break;
#else
        case SHIM_TYPE_THREAD: rc = WAIT_FAILED; break;
#endif
        default:
            SetLastError(ERROR_INVALID_FUNCTION);
            return WAIT_FAILED;
    }
    if (rc != WAIT_TIMEOUT) SetLastError(ERROR_SUCCESS);
    return rc;
}

DWORD WaitForSingleObjectEx(HANDLE h, DWORD ms, BOOL alertable) {
    (void)alertable; /* APC なし前提 */
    return WaitForSingleObject(h, ms);
}

/* ---------------------------------------------------------------
 * Event (§3 #4)
 * --------------------------------------------------------------- */
static HANDLE shim_create_event(int manualReset, int initialState) {
    ShimSlot* s = shim_alloc_slot(SHIM_TYPE_EVENT);
    if (!s) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return INVALID_HANDLE_VALUE; }
    s->manual_reset = manualReset;
    __atomic_store_n(&s->state, initialState ? 1u : 0u, __ATOMIC_SEQ_CST);
    SetLastError(ERROR_SUCCESS);
    return shim_handle_from_slot(s);
}

HANDLE CreateEventW(LPSECURITY_ATTRIBUTES sa, BOOL manualReset, BOOL initialState,
                    LPCWSTR name) {
    (void)sa; (void)name; /* named event (プロセス間共有) は v1 非対応 */
    return shim_create_event(manualReset, initialState);
}

HANDLE CreateEventA(LPSECURITY_ATTRIBUTES sa, BOOL manualReset, BOOL initialState,
                    const char* nameA) {
    (void)sa; (void)nameA;
    return shim_create_event(manualReset, initialState);
}

BOOL SetEvent(HANDLE h) {
    ShimSlot* s = shim_slot_lookup(h);
    if (!s || s->type != SHIM_TYPE_EVENT) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
    __atomic_store_n(&s->state, 1u, __ATOMIC_SEQ_CST);
    emscripten_futex_wake((volatile void*)&s->state, INT32_MAX);
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

BOOL ResetEvent(HANDLE h) {
    ShimSlot* s = shim_slot_lookup(h);
    if (!s || s->type != SHIM_TYPE_EVENT) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
    __atomic_store_n(&s->state, 0u, __ATOMIC_SEQ_CST);
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

/* ---------------------------------------------------------------
 * CRITICAL_SECTION (§3 #4) — ポインタ対応表で pthread_mutex に写影
 * --------------------------------------------------------------- */
#define SHIM_CS_MAX 128

typedef struct ShimCSEntry {
    const void* key;      /* クライアントが渡した CRITICAL_SECTION ポインタ */
    int used;
    DWORD recursion;
#if defined(__EMSCRIPTEN_PTHREADS__)
    pthread_mutex_t mtx;
#endif
} ShimCSEntry;

static ShimCSEntry g_cs[SHIM_CS_MAX];

static ShimCSEntry* cs_entry(PCRITICAL_SECTION cs, int createIfNew) {
    if (!cs) return NULL;
    ShimCSEntry* freeEntry = NULL;
    for (int i = 0; i < SHIM_CS_MAX; i++) {
        if (g_cs[i].used && g_cs[i].key == cs) return &g_cs[i];
        if (!g_cs[i].used && !freeEntry) freeEntry = &g_cs[i];
    }
    if (!createIfNew || !freeEntry) return NULL;
    ShimCSEntry* e = freeEntry;
    memset(e, 0, sizeof(*e));
    e->key = cs;
    e->used = 1;
#if defined(__EMSCRIPTEN_PTHREADS__)
    /* Win32 CRITICAL_SECTION は再帰可能 → PTHREAD_MUTEX_RECURSIVE で写影 */
    pthread_mutexattr_t attr;
    pthread_mutexattr_init(&attr);
    pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE);
    if (pthread_mutex_init(&e->mtx, &attr) != 0) {
        pthread_mutexattr_destroy(&attr);
        e->used = 0;
        return NULL;
    }
    pthread_mutexattr_destroy(&attr);
#endif
    return e;
}

BOOL InitializeCriticalSectionAndSpinCount(PCRITICAL_SECTION cs, DWORD spin) {
    (void)spin; /* spin count は wasm 上で無意味 */
    ShimCSEntry* e = cs_entry(cs, 1);
    if (!e) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return FALSE; }
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

void InitializeCriticalSection(PCRITICAL_SECTION cs) {
    if (!InitializeCriticalSectionAndSpinCount(cs, 0)) {
        shim_unimplemented("InitializeCriticalSection (対応表満杯)");
    }
}

void EnterCriticalSection(PCRITICAL_SECTION cs) {
    ShimCSEntry* e = cs_entry(cs, 0);
    if (!e) {
        fprintf(stderr, "[shim] CS-MISS key=0x%x\n", (unsigned)(uintptr_t)cs);
        shim_unimplemented("EnterCriticalSection (未初期化/未登録)");
        return;
    }
#if defined(__EMSCRIPTEN_PTHREADS__)
    if (pthread_mutex_lock(&e->mtx) != 0) {
        shim_unimplemented("EnterCriticalSection (lock 失敗)");
        return;
    }
#endif
    e->recursion++;
}

BOOL TryEnterCriticalSection(PCRITICAL_SECTION cs) {
    ShimCSEntry* e = cs_entry(cs, 0);
    if (!e) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
#if defined(__EMSCRIPTEN_PTHREADS__)
    if (pthread_mutex_trylock(&e->mtx) != 0) return FALSE;
#endif
    e->recursion++;
    return TRUE;
}

void LeaveCriticalSection(PCRITICAL_SECTION cs) {
    ShimCSEntry* e = cs_entry(cs, 0);
    if (!e || e->recursion == 0) return; /* 対応する Enter が無い Leave は no-op */
    e->recursion--;
#if defined(__EMSCRIPTEN_PTHREADS__)
    /* 再帰 mutex: Enter/Leave を必ず対にして unlock する */
    pthread_mutex_unlock(&e->mtx);
#endif
}

void DeleteCriticalSection(PCRITICAL_SECTION cs) {
    ShimCSEntry* e = cs_entry(cs, 0);
    if (!e) return;
#if defined(__EMSCRIPTEN_PTHREADS__)
    pthread_mutex_destroy(&e->mtx);
#endif
    e->used = 0;
}

/* ---------------------------------------------------------------
 * メモリバリア / Interlocked
 * --------------------------------------------------------------- */
void MemoryBarrier(void) {
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
}

LONG InterlockedIncrement(volatile LONG* v) {
    return __atomic_add_fetch(v, 1, __ATOMIC_SEQ_CST);
}

LONG InterlockedDecrement(volatile LONG* v) {
    return __atomic_sub_fetch(v, 1, __ATOMIC_SEQ_CST);
}

LONG InterlockedExchange(volatile LONG* v, LONG newVal) {
    return __atomic_exchange_n(v, newVal, __ATOMIC_SEQ_CST);
}

LONG InterlockedExchangeAdd(volatile LONG* v, LONG add) {
    return __atomic_fetch_add(v, add, __ATOMIC_SEQ_CST);
}

/* ---------------------------------------------------------------
 * TLS (§3 #4 / §5.3) — pthread_getspecific ベース
 * --------------------------------------------------------------- */
#define SHIM_TLS_MAX 64

#if defined(__EMSCRIPTEN_PTHREADS__)
static pthread_key_t g_tls_key;
static int g_tls_key_ready = 0;  /* main 初期化後に書き換わらない */

static void** tls_thread_array(void) {
    void** arr = (void**)pthread_getspecific(g_tls_key);
    if (!arr) {
        arr = (void**)calloc(SHIM_TLS_MAX, sizeof(void*));
        if (!arr) return NULL;
        pthread_setspecific(g_tls_key, arr);
    }
    return arr;
}
#else
static void* g_tls_st_values[SHIM_TLS_MAX]; /* 単一スレッド限定 */
#endif

static int g_tls_used[SHIM_TLS_MAX];

DWORD TlsAlloc(void) {
#if defined(__EMSCRIPTEN_PTHREADS__)
    if (!g_tls_key_ready) {
        if (pthread_key_create(&g_tls_key, NULL) != 0) {
            SetLastError(ERROR_NOT_ENOUGH_MEMORY);
            return 0xFFFFFFFFu;
        }
        g_tls_key_ready = 1;
    }
#endif
    int found = -1;
    for (int i = 0; i < SHIM_TLS_MAX; i++) {
        if (!g_tls_used[i]) { g_tls_used[i] = 1; found = i; break; }
    }
    if (found < 0) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0xFFFFFFFFu; }
    SetLastError(ERROR_SUCCESS);
    return (DWORD)found;
}

BOOL TlsFree(DWORD idx) {
    if (idx >= SHIM_TLS_MAX || !g_tls_used[idx]) {
        SetLastError(ERROR_INVALID_PARAMETER);
        return FALSE;
    }
    g_tls_used[idx] = 0;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

LPVOID TlsGetValue(DWORD idx) {
    if (idx >= SHIM_TLS_MAX) return NULL; /* Win 準拠の GetLastError 詳細挙動は省略 */
#if defined(__EMSCRIPTEN_PTHREADS__)
    if (!g_tls_key_ready) return NULL;
    void** arr = tls_thread_array();
    return arr ? arr[idx] : NULL;
#else
    return g_tls_st_values[idx];
#endif
}

BOOL TlsSetValue(DWORD idx, LPVOID val) {
    if (idx >= SHIM_TLS_MAX) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
#if defined(__EMSCRIPTEN_PTHREADS__)
    if (!g_tls_key_ready) { SetLastError(ERROR_INVALID_FUNCTION); return FALSE; }
    void** arr = tls_thread_array();
    if (!arr) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return FALSE; }
    arr[idx] = val;
#else
    g_tls_st_values[idx] = val;
#endif
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}
