/* shimx 単体テスト (core): ハンドル表 / 待機 / スレッド / ロック / TLS・FLS / タイマキュー。 */
#include "test_common.h"

static void test_handles_events(void) {
    HANDLE e = CreateEventW(NULL, TRUE, FALSE, NULL);
    CHECK(e != 0 && e != INVALID_HANDLE_VALUE && (e & 3) == 0);
    CHECK(WaitForSingleObject(e, 0) == WAIT_TIMEOUT);
    CHECK(SetEvent(e));
    CHECK(WaitForSingleObject(e, 0) == WAIT_OBJECT_0);
    CHECK(WaitForSingleObject(e, 0) == WAIT_OBJECT_0);          /* manual-reset は残る */
    CHECK(ResetEvent(e));
    CHECK(WaitForSingleObject(e, 10) == WAIT_TIMEOUT);

    HANDLE a = CreateEventA(NULL, FALSE, TRUE, NULL);           /* auto-reset, 初期 signaled */
    CHECK(WaitForSingleObject(a, 0) == WAIT_OBJECT_0);
    CHECK(WaitForSingleObject(a, 0) == WAIT_TIMEOUT);           /* 消費済み */

    /* 名前付き: 同名は同一オブジェクト (ERROR_ALREADY_EXISTS) */
    HANDLE n1 = CreateEventW(NULL, TRUE, FALSE, W("Local\\shimx_ev"));
    CHECK(n1 && GetLastError() == ERROR_SUCCESS);
    HANDLE n2 = CreateEventW(NULL, TRUE, FALSE, W("Global\\shimx_ev"));
    CHECK(n2 && n2 != n1 && GetLastError() == ERROR_ALREADY_EXISTS);
    CHECK(SetEvent(n1));
    CHECK(WaitForSingleObject(n2, 0) == WAIT_OBJECT_0);
    HANDLE n3 = OpenEventW(EVENT_MODIFY_STATE, FALSE, W("shimx_ev"));
    CHECK(n3 && WaitForSingleObject(n3, 0) == WAIT_OBJECT_0);
    CHECK(OpenEventW(0, FALSE, W("no_such_event")) == 0 && GetLastError() == ERROR_FILE_NOT_FOUND);
    /* 型違いの同名は失敗 */
    CHECK(CreateMutexW(NULL, FALSE, W("shimx_ev")) == 0 && GetLastError() == ERROR_INVALID_HANDLE);

    /* DuplicateHandle: 元を閉じても複製は有効 / 状態共有 */
    HANDLE d = 0;
    CHECK(DuplicateHandle(GetCurrentProcess(), e, GetCurrentProcess(), &d, 0, FALSE, DUPLICATE_SAME_ACCESS));
    CHECK(d && d != e);
    CHECK(CloseHandle(e));
    CHECK(SetEvent(d) && WaitForSingleObject(d, 0) == WAIT_OBJECT_0);
    CHECK(CloseHandle(d));
    CHECK(CloseHandle(d) == FALSE && GetLastError() == ERROR_INVALID_HANDLE);   /* 二重 Close */
    CHECK(WaitForSingleObject(d, 0) == WAIT_FAILED);                              /* 無効ハンドル */
    CHECK(CloseHandle(0) == FALSE);
    CHECK(CloseHandle(a) && CloseHandle(n1) && CloseHandle(n2) && CloseHandle(n3));
    int open0, peak; shimx_handle_stats(&open0, &peak);
    CHECK(peak >= 3);
}

static void test_wait_multi(void) {
    HANDLE e1 = CreateEventW(NULL, TRUE, FALSE, NULL), e2 = CreateEventW(NULL, TRUE, FALSE, NULL);
    HANDLE s = CreateSemaphoreW(NULL, 0, 3, NULL);
    HANDLE hs[3] = { e1, e2, s };
    CHECK(WaitForMultipleObjects(3, hs, FALSE, 0) == WAIT_TIMEOUT);
    SetEvent(e2);
    CHECK(WaitForMultipleObjects(3, hs, FALSE, 0) == WAIT_OBJECT_0 + 1);
    CHECK(WaitForMultipleObjects(3, hs, TRUE, 0) == WAIT_TIMEOUT);       /* 全員は未達 */
    SetEvent(e1);
    LONG prev = -1;
    CHECK(ReleaseSemaphore(s, 2, &prev) && prev == 0);
    CHECK(WaitForMultipleObjects(3, hs, TRUE, 0) == WAIT_OBJECT_0);      /* semaphore が 1 減る */
    CHECK(WaitForSingleObject(s, 0) == WAIT_OBJECT_0);                   /* 残り 1 */
    CHECK(WaitForSingleObject(s, 0) == WAIT_TIMEOUT);
    CHECK(ReleaseSemaphore(s, 4, &prev) == FALSE && GetLastError() == ERROR_TOO_MANY_POSTS);   /* max 3 超過 */
    CHECK(WaitForMultipleObjects(0, hs, FALSE, 0) == WAIT_FAILED);
    HANDLE bad[2] = { e1, 0x7774 };
    CHECK(WaitForMultipleObjects(2, bad, FALSE, 0) == WAIT_FAILED);

    /* mutex: 再帰取得 / 所有者のみ Release */
    HANDLE m = CreateMutexW(NULL, FALSE, NULL);
    CHECK(WaitForSingleObject(m, 0) == WAIT_OBJECT_0);
    CHECK(WaitForSingleObject(m, 0) == WAIT_OBJECT_0);                   /* 同一スレッドで再帰 */
    CHECK(ReleaseMutex(m) && ReleaseMutex(m));
    CHECK(ReleaseMutex(m) == FALSE && GetLastError() == ERROR_NOT_OWNER);
    CHECK(SignalObjectAndWait(e1, e2, 0, FALSE) == WAIT_OBJECT_0);

    double t0 = now_ms();
    CHECK(WaitForSingleObject(s, 60) == WAIT_TIMEOUT);
    CHECK(now_ms() - t0 >= 40.0);
    CloseHandle(e1); CloseHandle(e2); CloseHandle(s); CloseHandle(m);
}

static void test_interlocked_slist(void) {
    volatile LONG v = 5;
    CHECK(InterlockedIncrement(&v) == 6 && InterlockedDecrement(&v) == 5);
    CHECK(InterlockedExchange(&v, 9) == 5 && v == 9);
    CHECK(InterlockedExchangeAdd(&v, 3) == 9 && v == 12);
    CHECK(InterlockedCompareExchange(&v, 100, 12) == 12 && v == 100);
    CHECK(InterlockedCompareExchange(&v, 7, 1) == 100 && v == 100);
    CHECK(InterlockedAnd(&v, 0x0F) == 100 && v == 4);
    CHECK(InterlockedOr(&v, 0x10) == 4 && v == 20);
    CHECK(InterlockedXor(&v, 0x04) == 20 && v == 16);
    volatile LONGLONG q = 1;
    CHECK(InterlockedIncrement64(&q) == 2 && InterlockedExchangeAdd64(&q, 5) == 2 && q == 7);
    CHECK(InterlockedCompareExchange64(&q, 1ll << 40, 7) == 7 && q == (1ll << 40));
    PVOID p = (PVOID)0x1234;
    CHECK(InterlockedExchangePointer(&p, (PVOID)0x5678) == (PVOID)0x1234 && p == (PVOID)0x5678);

    uint64_t head[2] __attribute__((aligned(16)));
    uint64_t e[3][2] __attribute__((aligned(16)));
    InitializeSListHead(head);
    CHECK(InterlockedPushEntrySList(head, e[0]) == NULL);
    CHECK(InterlockedPushEntrySList(head, e[1]) == e[0]);
    CHECK(InterlockedPushEntrySList(head, e[2]) == e[1]);
    CHECK(QueryDepthSList(head) == 3);
    CHECK(InterlockedPopEntrySList(head) == e[2]);
    void* all = InterlockedFlushSList(head);
    CHECK(all == e[1] && QueryDepthSList(head) == 0 && InterlockedPopEntrySList(head) == NULL);
}

static void test_cs_layout(void) {
    /* Win64 RTL_CRITICAL_SECTION レイアウトをクライアント領域に直接実装 */
    uint64_t cs[8] __attribute__((aligned(8))) = {0};
    InitializeCriticalSection(cs);
    CHECK(*(int32_t*)((char*)cs + 8) == -1);                    /* LockCount = -1 (未ロック) */
    EnterCriticalSection(cs);
    CHECK(*(int32_t*)((char*)cs + 8) == 0 && *(int32_t*)((char*)cs + 12) == 1);
    CHECK(*(uint64_t*)((char*)cs + 16) == GetCurrentThreadId());    /* OwningThread */
    EnterCriticalSection(cs);
    CHECK(*(int32_t*)((char*)cs + 12) == 2);
    LeaveCriticalSection(cs); LeaveCriticalSection(cs);
    CHECK(*(int32_t*)((char*)cs + 8) == -1 && *(uint64_t*)((char*)cs + 16) == 0);
    /* 0 初期化のみ (Delphi の static CS) でも未ロック扱い */
    uint64_t z[8] __attribute__((aligned(8))) = {0};
    CHECK(TryEnterCriticalSection(z));
    LeaveCriticalSection(z);
    DeleteCriticalSection(cs);
    /* 上限なし: 5000 個の CS を同時に初期化 */
    uint64_t* many = (uint64_t*)aligned_alloc(8, 5000 * 40);
    for (int i = 0; i < 5000; i++) InitializeCriticalSection(many + i * 5);
    for (int i = 0; i < 5000; i++) { EnterCriticalSection(many + i * 5); LeaveCriticalSection(many + i * 5); }
    free(many);
}

static void test_srw_once_cv_st(void) {
    uint64_t srw = 0;
    InitializeSRWLock(&srw);
    AcquireSRWLockShared(&srw); AcquireSRWLockShared(&srw);
    CHECK(TryAcquireSRWLockExclusive(&srw) == 0);
    ReleaseSRWLockShared(&srw); ReleaseSRWLockShared(&srw);
    CHECK(TryAcquireSRWLockExclusive(&srw) == 1);
    CHECK(TryAcquireSRWLockShared(&srw) == 0);
    ReleaseSRWLockExclusive(&srw);
    AcquireSRWLockExclusive(&srw); ReleaseSRWLockExclusive(&srw);

    uint64_t once = 0; BOOL pend = 0; LPVOID ctx = 0;
    CHECK(InitOnceBeginInitialize(&once, 0, &pend, &ctx) && pend);
    CHECK(InitOnceComplete(&once, 0, (LPVOID)0x77));
    CHECK(InitOnceBeginInitialize(&once, 0, &pend, &ctx) && !pend && ctx == (LPVOID)0x77);

    uint64_t cv = 0, cs[8] __attribute__((aligned(8))) = {0};
    InitializeConditionVariable(&cv); InitializeCriticalSection(cs);
    EnterCriticalSection(cs);
    CHECK(SleepConditionVariableCS(&cv, cs, 20) == FALSE && GetLastError() == ERROR_TIMEOUT);   /* 起こされず timeout */
    LeaveCriticalSection(cs);
}

static void test_tls_fls_st(void) {
    DWORD t = TlsAlloc();
    CHECK(t != TLS_OUT_OF_INDEXES);
    CHECK(TlsGetValue(t) == NULL && GetLastError() == ERROR_SUCCESS);
    CHECK(TlsSetValue(t, (LPVOID)0xABCD));
    CHECK(TlsGetValue(t) == (LPVOID)0xABCD);
    /* 64 個超 (拡張スロット) も確保できる */
    DWORD many[200];
    for (int i = 0; i < 200; i++) { many[i] = TlsAlloc(); CHECK(many[i] != TLS_OUT_OF_INDEXES); CHECK(TlsSetValue(many[i], (LPVOID)(uintptr_t)(i + 1))); }
    for (int i = 0; i < 200; i++) CHECK(TlsGetValue(many[i]) == (LPVOID)(uintptr_t)(i + 1));
    for (int i = 0; i < 200; i++) CHECK(TlsFree(many[i]));
    CHECK(TlsFree(t) && !TlsFree(t));
    CHECK(TlsSetValue(t, (LPVOID)1) == FALSE);                  /* 解放済み */

    /* 擬似 TEB: gs:[0x30]=Self, gs:[0x68]=LastError, gs:[0x1480+8*i]=TlsSlots[i] */
    uint64_t self = __readgsqword(0x30);
    CHECK(self != 0);
    SetLastError(0x1234);
    CHECK(__readgsdword(0x68) == 0x1234 && GetLastError() == 0x1234);
    CHECK(__readgsdword(0x48) == GetCurrentThreadId());
    DWORD t2 = TlsAlloc();
    TlsSetValue(t2, (LPVOID)0x42);
    if (t2 < 64) CHECK(__readgsqword(0x1480 + 8 * t2) == 0x42);
    TlsFree(t2);
    CHECK(__readgsqword(0x60) != 0);                            /* PEB */
}

#if defined(__EMSCRIPTEN_PTHREADS__)
static volatile LONG g_fls_called;
static void fls_cb(void* v) { if (v == (void*)0x55) InterlockedIncrement(&g_fls_called); }

static DWORD g_tid_in_thread;
static DWORD WINAPI thr_basic(LPVOID p) {
    g_tid_in_thread = GetCurrentThreadId();
    SetLastError(777);
    return (DWORD)(uintptr_t)p + 1;
}
static DWORD tls_idx, fls_idx;
static DWORD WINAPI thr_tls(LPVOID p) {
    (void)p;
    CHECK(TlsGetValue(tls_idx) == NULL);                        /* 他スレッドの値は見えない */
    TlsSetValue(tls_idx, (LPVOID)0x99);
    FlsSetValue(fls_idx, (PVOID)0x55);
    CHECK(GetLastError() != 4242);                              /* LastError もスレッドローカル */
    return 0;
}
static DWORD WINAPI thr_exit(LPVOID p) { (void)p; ExitThread(31337); return 0; }

static void test_threads(void) {
    DWORD tid = 0;
    HANDLE h = CreateThread(NULL, 0, thr_basic, (LPVOID)41, 0, &tid);
    CHECK(h && tid != 0);
    CHECK(WaitForSingleObject(h, 5000) == WAIT_OBJECT_0);
    CHECK(tid == g_tid_in_thread && tid != GetCurrentThreadId());    /* M4 は作成側 ID を返していた */
    DWORD rc = 0;
    CHECK(GetExitCodeThread(h, &rc) && rc == 42);
    CHECK(GetThreadId(h) == tid);
    CloseHandle(h);
    SetLastError(4242);                                          /* 子の SetLastError(777) と干渉しない */
    CHECK(GetLastError() == 4242);

    /* CREATE_SUSPENDED → ResumeThread で起動 */
    g_tid_in_thread = 0;
    h = CreateThread(NULL, 0, thr_basic, (LPVOID)1, CREATE_SUSPENDED, &tid);
    CHECK(h);
    CHECK(WaitForSingleObject(h, 80) == WAIT_TIMEOUT);          /* まだ走らない */
    CHECK(g_tid_in_thread == 0);
    DWORD rc0 = 0; CHECK(GetExitCodeThread(h, &rc0) && rc0 == STILL_ACTIVE);
    CHECK(ResumeThread(h) == 1);
    CHECK(WaitForSingleObject(h, 5000) == WAIT_OBJECT_0 && g_tid_in_thread == tid);
    CloseHandle(h);

    /* TLS / FLS (終了時コールバック) */
    tls_idx = TlsAlloc();
    fls_idx = FlsAlloc(fls_cb);
    TlsSetValue(tls_idx, (LPVOID)0x11);
    h = CreateThread(NULL, 0, thr_tls, NULL, 0, NULL);
    CHECK(WaitForSingleObject(h, 5000) == WAIT_OBJECT_0);
    CloseHandle(h);
    CHECK(TlsGetValue(tls_idx) == (LPVOID)0x11);                 /* 親の値は不変 */
    CHECK(g_fls_called == 1);                                    /* スレッド終了で FLS コールバック */
    CHECK(FlsFree(fls_idx) && TlsFree(tls_idx));

    /* ExitThread / ハンドルを閉じてもスレッドは継続 / 自スレッドを待たない */
    h = CreateThread(NULL, 0, thr_exit, NULL, 0, NULL);
    CHECK(WaitForSingleObject(h, 5000) == WAIT_OBJECT_0);
    CHECK(GetExitCodeThread(h, &rc) && rc == 31337);
    CloseHandle(h);

    /* 擬似ハンドル: GetCurrentThread() を DuplicateHandle で実体化 */
    HANDLE me = 0;
    CHECK(DuplicateHandle(GetCurrentProcess(), GetCurrentThread(), GetCurrentProcess(), &me, 0, FALSE, DUPLICATE_SAME_ACCESS));
    CHECK(me && GetThreadId(me) == GetCurrentThreadId());
    CHECK(SetThreadPriority(me, 2) && GetThreadPriority(me) == 2);
    CloseHandle(me);
    CHECK(SuspendThread(GetCurrentThread()) == 0);               /* スタブ: カウントのみ */
    CHECK(ResumeThread(GetCurrentThread()) == 1);
}

static volatile LONG g_cs_count;
static uint64_t g_cs[8] __attribute__((aligned(8)));
static DWORD WINAPI thr_cs(LPVOID p) {
    (void)p;
    for (int i = 0; i < 10000; i++) { EnterCriticalSection(g_cs); g_cs_count++; LeaveCriticalSection(g_cs); }
    return 0;
}
static uint64_t g_srw __attribute__((aligned(8)));
static volatile LONG g_srw_count;
static DWORD WINAPI thr_srw(LPVOID p) {
    (void)p;
    for (int i = 0; i < 5000; i++) { AcquireSRWLockExclusive(&g_srw); g_srw_count++; ReleaseSRWLockExclusive(&g_srw); }
    return 0;
}
static void test_contention(void) {
    InitializeCriticalSection(g_cs);
    HANDLE th[4];
    for (int i = 0; i < 4; i++) th[i] = CreateThread(NULL, 0, thr_cs, NULL, 0, NULL);
    CHECK(WaitForMultipleObjects(4, th, TRUE, 20000) == WAIT_OBJECT_0);
    CHECK(g_cs_count == 40000);
    for (int i = 0; i < 4; i++) CloseHandle(th[i]);
    InitializeSRWLock(&g_srw);
    for (int i = 0; i < 4; i++) th[i] = CreateThread(NULL, 0, thr_srw, NULL, 0, NULL);
    CHECK(WaitForMultipleObjects(4, th, TRUE, 20000) == WAIT_OBJECT_0);
    CHECK(g_srw_count == 20000);
    for (int i = 0; i < 4; i++) CloseHandle(th[i]);
}

/* 待機 → 別スレッドが Set で解除 / mutex 排他 / semaphore 生産消費 / 条件変数 */
static HANDLE g_ev, g_sem, g_mtx;
static DWORD WINAPI thr_setter(LPVOID p) { (void)p; Sleep(60); SetEvent(g_ev); return 0; }
static volatile LONG g_consumed;
static DWORD WINAPI thr_consumer(LPVOID p) {
    (void)p;
    while (WaitForSingleObject(g_sem, 5000) == WAIT_OBJECT_0) { if (InterlockedIncrement(&g_consumed) >= 10) break; }
    return 0;
}
static HANDLE g_started;
static DWORD WINAPI thr_mtx_owner(LPVOID p) {
    (void)p;
    WaitForSingleObject(g_mtx, 5000);
    SetEvent(g_started);
    Sleep(150);
    ReleaseMutex(g_mtx);
    return 0;
}
static uint64_t g_cv_cs[8] __attribute__((aligned(8)));
static uint64_t g_cv;
static volatile LONG g_cv_ready;
static DWORD WINAPI thr_cv_waiter(LPVOID p) {
    (void)p;
    EnterCriticalSection(g_cv_cs);
    while (!g_cv_ready) SleepConditionVariableCS(&g_cv, g_cv_cs, 5000);
    LeaveCriticalSection(g_cv_cs);
    return 7;
}
static void test_cross_thread_sync(void) {
    g_ev = CreateEventW(NULL, TRUE, FALSE, NULL);
    HANDLE th = CreateThread(NULL, 0, thr_setter, NULL, 0, NULL);
    double t0 = now_ms();
    CHECK(WaitForSingleObject(g_ev, 5000) == WAIT_OBJECT_0);
    CHECK(now_ms() - t0 >= 40.0 && now_ms() - t0 < 3000.0);
    CloseHandle(th); CloseHandle(g_ev);

    g_sem = CreateSemaphoreW(NULL, 0, 100, NULL);
    th = CreateThread(NULL, 0, thr_consumer, NULL, 0, NULL);
    for (int i = 0; i < 10; i++) { ReleaseSemaphore(g_sem, 1, NULL); Sleep(2); }
    CHECK(WaitForSingleObject(th, 5000) == WAIT_OBJECT_0);
    CHECK(g_consumed == 10);
    CloseHandle(th); CloseHandle(g_sem);

    g_mtx = CreateMutexW(NULL, FALSE, NULL);
    g_started = CreateEventW(NULL, TRUE, FALSE, NULL);
    th = CreateThread(NULL, 0, thr_mtx_owner, NULL, 0, NULL);
    CHECK(WaitForSingleObject(g_started, 5000) == WAIT_OBJECT_0);
    CHECK(WaitForSingleObject(g_mtx, 10) == WAIT_TIMEOUT);       /* 他スレッドが保持中 */
    CHECK(WaitForSingleObject(g_mtx, 5000) == WAIT_OBJECT_0);    /* 解放後に取得 */
    ReleaseMutex(g_mtx);
    WaitForSingleObject(th, 5000); CloseHandle(th); CloseHandle(g_mtx);

    InitializeCriticalSection(g_cv_cs); InitializeConditionVariable(&g_cv);
    th = CreateThread(NULL, 0, thr_cv_waiter, NULL, 0, NULL);
    Sleep(30);
    EnterCriticalSection(g_cv_cs); g_cv_ready = 1; LeaveCriticalSection(g_cv_cs);
    WakeAllConditionVariable(&g_cv);
    CHECK(WaitForSingleObject(th, 5000) == WAIT_OBJECT_0);
    DWORD rc; CHECK(GetExitCodeThread(th, &rc) && rc == 7);
    CloseHandle(th);
}

static volatile LONG g_timer_hits;
static void CALLBACK timer_cb(LPVOID p, BOOLEAN fired) { (void)p; (void)fired; InterlockedIncrement(&g_timer_hits); }
static void test_timer_queue(void) {
    HANDLE t = 0;
    CHECK(CreateTimerQueueTimer(&t, 0, timer_cb, NULL, 20, 0, 0));        /* one-shot */
    Sleep(150);
    CHECK(g_timer_hits == 1);
    HANDLE p = 0;
    CHECK(CreateTimerQueueTimer(&p, 0, timer_cb, NULL, 10, 20, 0));       /* 周期 */
    Sleep(200);
    CHECK(DeleteTimerQueueTimer(0, p, INVALID_HANDLE_VALUE));
    LONG hits = g_timer_hits;
    CHECK(hits >= 4);
    Sleep(80);
    CHECK(g_timer_hits == hits);                                          /* 削除後は発火しない */
    CHECK(DeleteTimerQueueTimer(0, t, NULL));
    CHECK(DeleteTimerQueueTimer(0, t, NULL) == FALSE);
}

static volatile LONG g_work_ran;
static void work_cb(void* inst, void* ctx, void* work) { (void)inst; (void)work; InterlockedExchangeAdd(&g_work_ran, (LONG)(uintptr_t)ctx); }
static void test_threadpool_work(void) {
    void* w = CreateThreadpoolWork(work_cb, (void*)5, NULL);
    CHECK(w);
    SubmitThreadpoolWork(w); SubmitThreadpoolWork(w);
    for (int i = 0; i < 100 && g_work_ran < 10; i++) Sleep(10);
    CHECK(g_work_ran == 10);
    CloseThreadpoolWork(w);
}
#endif

void run_core_tests(int mt) {
    test_handles_events();
    test_wait_multi();
    test_interlocked_slist();
    test_cs_layout();
    test_srw_once_cv_st();
    test_tls_fls_st();
#if defined(__EMSCRIPTEN_PTHREADS__)
    if (mt) {
        test_threads();
        test_contention();
        test_cross_thread_sync();
        test_timer_queue();
        test_threadpool_work();
    }
#else
    (void)mt;
#endif
}
