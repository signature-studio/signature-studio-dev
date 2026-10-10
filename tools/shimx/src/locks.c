/* CRITICAL_SECTION / SRWLOCK / CONDITION_VARIABLE / InitOnce / SList / Interlocked。
 *
 * M4 差分: CRITICAL_SECTION は M4 では「ポインタ→pthread_mutex 対応表 (128 件上限)」だった。
 * ここでは Win64 の RTL_CRITICAL_SECTION レイアウト (40B) をクライアントメモリ上で *直接* 実装する
 * (表の上限なし / malloc なし / ゼロ初期化メモリも未ロック状態として扱える):
 *   +8  LockCount(int32, 未ロック=-1)   +12 RecursionCount(int32)
 *   +16 OwningThread(uint64, TID)       +24 LockSemaphore(uint32 を futex mutex 語として流用)
 *   +32 SpinCount
 */
#include "shimx_internal.h"

typedef struct {
    uint64_t DebugInfo;
    volatile int32_t LockCount;
    volatile int32_t RecursionCount;
    volatile uint64_t OwningThread;
    shx_mutex_t LockSemaphore; uint32_t _pad;
    uint64_t SpinCount;
} ShxCS;   /* 40B (wasm32 でもフィールド幅は固定) */

static ShxCS* cs_of(PCRITICAL_SECTION p, const char* who) {
    if (!p || ((uintptr_t)p & 7u)) shim_unimplemented(who);
    return (ShxCS*)p;
}

BOOL InitializeCriticalSectionEx(PCRITICAL_SECTION p, DWORD spin, DWORD flags) {
    (void)flags;
    ShxCS* cs = cs_of(p, "InitializeCriticalSection (NULL/misaligned)");
    memset(cs, 0, sizeof(*cs));
    cs->LockCount = -1;
    cs->SpinCount = spin;
    return TRUE;
}
BOOL InitializeCriticalSectionAndSpinCount(PCRITICAL_SECTION p, DWORD spin) {
    return InitializeCriticalSectionEx(p, spin, 0);
}
void InitializeCriticalSection(PCRITICAL_SECTION p) { InitializeCriticalSectionEx(p, 0, 0); }
DWORD SetCriticalSectionSpinCount(PCRITICAL_SECTION p, DWORD spin) {
    ShxCS* cs = cs_of(p, "SetCriticalSectionSpinCount");
    DWORD old = (DWORD)cs->SpinCount;
    cs->SpinCount = spin;
    return old;
}

void EnterCriticalSection(PCRITICAL_SECTION p) {
    ShxCS* cs = cs_of(p, "EnterCriticalSection (NULL/misaligned)");
    uint64_t me = shx_tid();
    if (__atomic_load_n(&cs->OwningThread, __ATOMIC_RELAXED) == me) {
        cs->RecursionCount++;
        cs->LockCount++;
        return;
    }
    shx_mutex_lock(&cs->LockSemaphore);
    __atomic_store_n(&cs->OwningThread, me, __ATOMIC_RELAXED);
    cs->RecursionCount = 1;
    cs->LockCount = 0;
}

BOOL TryEnterCriticalSection(PCRITICAL_SECTION p) {
    ShxCS* cs = cs_of(p, "TryEnterCriticalSection (NULL/misaligned)");
    uint64_t me = shx_tid();
    if (__atomic_load_n(&cs->OwningThread, __ATOMIC_RELAXED) == me) {
        cs->RecursionCount++;
        cs->LockCount++;
        return TRUE;
    }
    if (!shx_mutex_trylock(&cs->LockSemaphore)) return FALSE;
    __atomic_store_n(&cs->OwningThread, me, __ATOMIC_RELAXED);
    cs->RecursionCount = 1;
    cs->LockCount = 0;
    return TRUE;
}

void LeaveCriticalSection(PCRITICAL_SECTION p) {
    ShxCS* cs = cs_of(p, "LeaveCriticalSection (NULL/misaligned)");
    if (__atomic_load_n(&cs->OwningThread, __ATOMIC_RELAXED) != shx_tid()) return;  /* 対応 Enter 無しは no-op (M4 同様) */
    if (--cs->RecursionCount > 0) { cs->LockCount--; return; }
    cs->LockCount = -1;
    __atomic_store_n(&cs->OwningThread, 0, __ATOMIC_RELAXED);
    shx_mutex_unlock(&cs->LockSemaphore);
}

void DeleteCriticalSection(PCRITICAL_SECTION p) {
    if (!p || ((uintptr_t)p & 7u)) return;
    ShxCS* cs = (ShxCS*)p;
    cs->DebugInfo = 0;
    cs->LockCount = -1;
}

/* ---------------------------------------------------------------
 * SRWLOCK (Win64: ポインタ幅 1 語 → 先頭 32bit を状態語に)
 *   bit31 = writer, 下位 = reader 数
 * --------------------------------------------------------------- */
#define SRW_W 0x80000000u
static volatile uint32_t* srw(PSRWLOCK l) {
    if (!l || ((uintptr_t)l & 3u)) shim_unimplemented("SRWLOCK (NULL/misaligned)");
    return (volatile uint32_t*)l;
}
void InitializeSRWLock(PSRWLOCK l) { *(volatile uint64_t*)l = 0; }

BOOLEAN TryAcquireSRWLockExclusive(PSRWLOCK l) {
    volatile uint32_t* w = srw(l);
    uint32_t z = 0;
    return __atomic_compare_exchange_n(w, &z, SRW_W, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED) ? 1 : 0;
}
void AcquireSRWLockExclusive(PSRWLOCK l) {
    volatile uint32_t* w = srw(l);
    for (;;) {
        uint32_t z = 0;
        if (__atomic_compare_exchange_n(w, &z, SRW_W, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return;
        shx_futex_wait(w, z, INFINITY);
    }
}
void ReleaseSRWLockExclusive(PSRWLOCK l) {
    volatile uint32_t* w = srw(l);
    __atomic_store_n(w, 0u, __ATOMIC_RELEASE);
    shx_futex_wake(w, 0x7fffffff);
}
BOOLEAN TryAcquireSRWLockShared(PSRWLOCK l) {
    volatile uint32_t* w = srw(l);
    uint32_t v = __atomic_load_n(w, __ATOMIC_RELAXED);
    while (!(v & SRW_W)) {
        if (__atomic_compare_exchange_n(w, &v, v + 1, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return 1;
    }
    return 0;
}
void AcquireSRWLockShared(PSRWLOCK l) {
    volatile uint32_t* w = srw(l);
    for (;;) {
        uint32_t v = __atomic_load_n(w, __ATOMIC_RELAXED);
        if (!(v & SRW_W)) {
            if (__atomic_compare_exchange_n(w, &v, v + 1, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return;
        } else {
            shx_futex_wait(w, v, INFINITY);
        }
    }
}
void ReleaseSRWLockShared(PSRWLOCK l) {
    volatile uint32_t* w = srw(l);
    if (__atomic_sub_fetch(w, 1u, __ATOMIC_RELEASE) == 0) shx_futex_wake(w, 0x7fffffff);
}

/* ---------------------------------------------------------------
 * CONDITION_VARIABLE (先頭 32bit = 世代カウンタ)
 * --------------------------------------------------------------- */
static volatile uint32_t* cvw(PCONDITION_VARIABLE c) {
    if (!c || ((uintptr_t)c & 3u)) shim_unimplemented("CONDITION_VARIABLE (NULL/misaligned)");
    return (volatile uint32_t*)c;
}
void InitializeConditionVariable(PCONDITION_VARIABLE c) { *(volatile uint64_t*)c = 0; }
void WakeConditionVariable(PCONDITION_VARIABLE c) {
    volatile uint32_t* w = cvw(c);
    __atomic_add_fetch(w, 1u, __ATOMIC_SEQ_CST);
    shx_futex_wake(w, 1);
}
void WakeAllConditionVariable(PCONDITION_VARIABLE c) {
    volatile uint32_t* w = cvw(c);
    __atomic_add_fetch(w, 1u, __ATOMIC_SEQ_CST);
    shx_futex_wake(w, 0x7fffffff);
}
static BOOL cv_wait(PCONDITION_VARIABLE c, DWORD ms, void (*unlock)(void*), void (*lock)(void*), void* lk) {
    volatile uint32_t* w = cvw(c);
    uint32_t seq = __atomic_load_n(w, __ATOMIC_SEQ_CST);
    unlock(lk);
    shx_futex_wait(w, seq, ms == INFINITE ? INFINITY : (double)ms);
    BOOL timedOut = (__atomic_load_n(w, __ATOMIC_SEQ_CST) == seq) && ms != INFINITE;
    lock(lk);
    if (timedOut) { SetLastError(ERROR_TIMEOUT); return FALSE; }
    return TRUE;
}
static void cs_unlock_cb(void* p) {
    /* 再帰ロック中でも全回数解放が必要: 回数を保存して元に戻す */
    ShxCS* cs = (ShxCS*)p;
    int32_t rc = cs->RecursionCount;
    cs->LockCount = -1;
    cs->RecursionCount = 0;
    __atomic_store_n(&cs->OwningThread, 0, __ATOMIC_RELAXED);
    cs->_pad = (uint32_t)rc;
    shx_mutex_unlock(&cs->LockSemaphore);
}
static void cs_lock_cb(void* p) {
    ShxCS* cs = (ShxCS*)p;
    int32_t rc = (int32_t)cs->_pad;
    shx_mutex_lock(&cs->LockSemaphore);
    __atomic_store_n(&cs->OwningThread, shx_tid(), __ATOMIC_RELAXED);
    cs->RecursionCount = rc ? rc : 1;
    cs->LockCount = cs->RecursionCount - 1;
}
BOOL SleepConditionVariableCS(PCONDITION_VARIABLE c, PCRITICAL_SECTION p, DWORD ms) {
    return cv_wait(c, ms, cs_unlock_cb, cs_lock_cb, cs_of(p, "SleepConditionVariableCS"));
}
static void srw_unlock_cb(void* p) {
    /* ULONG flags 不明のため CONDITION_VARIABLE_LOCKMODE_SHARED 判定は呼び出し側で */
    (void)p;
}
static _Thread_local int t_srw_shared;
static void srw_ex_unlock(void* p) { ReleaseSRWLockExclusive(p); }
static void srw_ex_lock(void* p)   { AcquireSRWLockExclusive(p); }
static void srw_sh_unlock(void* p) { ReleaseSRWLockShared(p); }
static void srw_sh_lock(void* p)   { AcquireSRWLockShared(p); }
BOOL SleepConditionVariableSRW(PCONDITION_VARIABLE c, PSRWLOCK l, DWORD ms, ULONG flags) {
    (void)srw_unlock_cb; (void)t_srw_shared;
    if (flags & 1u /* CONDITION_VARIABLE_LOCKMODE_SHARED */)
        return cv_wait(c, ms, srw_sh_unlock, srw_sh_lock, l);
    return cv_wait(c, ms, srw_ex_unlock, srw_ex_lock, l);
}

/* ---------------------------------------------------------------
 * InitOnce (state: 0 未, 1 実行中, 2 完了; ctx は +4)
 * --------------------------------------------------------------- */
BOOL InitOnceBeginInitialize(PINIT_ONCE once, DWORD flags, BOOL* pending, LPVOID* ctx) {
    (void)flags;
    volatile uint32_t* st = (volatile uint32_t*)once;
    for (;;) {
        uint32_t z = 0;
        if (__atomic_compare_exchange_n(st, &z, 1u, 0, __ATOMIC_ACQUIRE, __ATOMIC_ACQUIRE)) {
            if (pending) *pending = TRUE;
            return TRUE;
        }
        if (z == 2) {
            if (pending) *pending = FALSE;
            if (ctx) *ctx = (LPVOID)(uintptr_t)st[1];
            return TRUE;
        }
        shx_futex_wait(st, 1u, INFINITY);
    }
}
BOOL InitOnceComplete(PINIT_ONCE once, DWORD flags, LPVOID ctx) {
    volatile uint32_t* st = (volatile uint32_t*)once;
    if (flags & 4u /* INIT_ONCE_INIT_FAILED */) __atomic_store_n(st, 0u, __ATOMIC_RELEASE);
    else { st[1] = (uint32_t)(uintptr_t)ctx; __atomic_store_n(st, 2u, __ATOMIC_RELEASE); }
    shx_futex_wake(st, 0x7fffffff);
    return TRUE;
}
BOOL InitOnceExecuteOnce(PINIT_ONCE once, PINIT_ONCE_FN fn, LPVOID param, LPVOID* ctx) {
    BOOL pend = FALSE;
    LPVOID c = NULL;
    if (!InitOnceBeginInitialize(once, 0, &pend, &c)) return FALSE;
    if (!pend) { if (ctx) *ctx = c; return TRUE; }
    BOOL ok = fn ? fn(once, param, &c) : FALSE;
    InitOnceComplete(once, ok ? 0 : 4u, c);
    if (ok && ctx) *ctx = c;
    return ok;
}

/* ---------------------------------------------------------------
 * SList (Win64 SLIST_HEADER 16B: +0 Next(8B スロット), +8 Depth(WORD)。全体を 1 本の mutex で保護)
 * --------------------------------------------------------------- */
static shx_mutex_t g_slist_lk;
void InitializeSListHead(void* head) { memset(head, 0, 16); }
void* InterlockedPushEntrySList(void* head, void* entry) {
    uint64_t* h = (uint64_t*)head;
    shx_mutex_lock(&g_slist_lk);
    void* old = (void*)(uintptr_t)h[0];
    *(uint64_t*)entry = h[0];
    h[0] = (uint64_t)(uintptr_t)entry;
    (*(uint16_t*)&h[1])++;
    shx_mutex_unlock(&g_slist_lk);
    return old;
}
void* InterlockedPopEntrySList(void* head) {
    uint64_t* h = (uint64_t*)head;
    shx_mutex_lock(&g_slist_lk);
    void* top = (void*)(uintptr_t)h[0];
    if (top) { h[0] = *(uint64_t*)top; (*(uint16_t*)&h[1])--; }
    shx_mutex_unlock(&g_slist_lk);
    return top;
}
void* InterlockedFlushSList(void* head) {
    uint64_t* h = (uint64_t*)head;
    shx_mutex_lock(&g_slist_lk);
    void* top = (void*)(uintptr_t)h[0];
    h[0] = 0; *(uint16_t*)&h[1] = 0;
    shx_mutex_unlock(&g_slist_lk);
    return top;
}
WORD QueryDepthSList(void* head) { return *(uint16_t*)((uint64_t*)head + 1); }

/* ---------------------------------------------------------------
 * Interlocked / barrier
 * --------------------------------------------------------------- */
void MemoryBarrier(void) { __atomic_thread_fence(__ATOMIC_SEQ_CST); }
LONG InterlockedIncrement(volatile LONG* v) { return __atomic_add_fetch(v, 1, __ATOMIC_SEQ_CST); }
LONG InterlockedDecrement(volatile LONG* v) { return __atomic_sub_fetch(v, 1, __ATOMIC_SEQ_CST); }
LONG InterlockedExchange(volatile LONG* v, LONG n) { return __atomic_exchange_n(v, n, __ATOMIC_SEQ_CST); }
LONG InterlockedExchangeAdd(volatile LONG* v, LONG a) { return __atomic_fetch_add(v, a, __ATOMIC_SEQ_CST); }
LONG InterlockedCompareExchange(volatile LONG* v, LONG x, LONG c) {
    __atomic_compare_exchange_n(v, &c, x, 0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); return c;
}
LONG InterlockedAnd(volatile LONG* v, LONG m) { return __atomic_fetch_and(v, m, __ATOMIC_SEQ_CST); }
LONG InterlockedOr(volatile LONG* v, LONG m)  { return __atomic_fetch_or(v, m, __ATOMIC_SEQ_CST); }
LONG InterlockedXor(volatile LONG* v, LONG m) { return __atomic_fetch_xor(v, m, __ATOMIC_SEQ_CST); }
LONGLONG InterlockedIncrement64(volatile LONGLONG* v) { return __atomic_add_fetch(v, 1, __ATOMIC_SEQ_CST); }
LONGLONG InterlockedDecrement64(volatile LONGLONG* v) { return __atomic_sub_fetch(v, 1, __ATOMIC_SEQ_CST); }
LONGLONG InterlockedExchange64(volatile LONGLONG* v, LONGLONG n) { return __atomic_exchange_n(v, n, __ATOMIC_SEQ_CST); }
LONGLONG InterlockedExchangeAdd64(volatile LONGLONG* v, LONGLONG a) { return __atomic_fetch_add(v, a, __ATOMIC_SEQ_CST); }
LONGLONG InterlockedCompareExchange64(volatile LONGLONG* v, LONGLONG x, LONGLONG c) {
    __atomic_compare_exchange_n(v, &c, x, 0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); return c;
}
PVOID InterlockedExchangePointer(volatile PVOID* v, PVOID n) { return __atomic_exchange_n(v, n, __ATOMIC_SEQ_CST); }
PVOID InterlockedCompareExchangePointer(volatile PVOID* v, PVOID x, PVOID c) {
    __atomic_compare_exchange_n(v, &c, x, 0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); return c;
}
