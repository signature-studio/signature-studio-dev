/* M4 shim unit tests (wasm / node 上で実行)。
 * 対象: timer / file / CRITICAL_SECTION 排他 / heap / thread 生成と join /
 * TLS 分離 / event 待ち (timeout 含む)。fail-fast (abort) 系は test.sh の
 * 別ビルドで独立確認する。
 * すべて C 内で完結し、失敗時に非 0 で終了する。test.sh が exit code を検証。
 * Windows 挙動の bit 厳密一致は要求しない (timer 粒度など「意味論が破綻しない
 * 最小実装」基準)。
 */
#include "../src/shim.h"
#include <sys/stat.h>
#include <errno.h>

#define CHECK(cond) \
    do { if (!(cond)) { \
        fprintf(stderr, "[M4-test] FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
        fflush(stderr); \
        exit(1); \
    } } while (0)

static const char* g_build = "?";

/* ---------------------------------------------------------------
 * timer (§3 #3) — 共通 (MT/ST とも)
 * --------------------------------------------------------------- */
static void test_timer(void) {
    LARGE_INTEGER freq, q0, q1;
    CHECK(QueryPerformanceFrequency(&freq) == TRUE);
    CHECK(freq.QuadPart >= 1000000 && freq.QuadPart <= 1000000000);
    CHECK(QueryPerformanceCounter(&q0) == TRUE);
    CHECK(q0.QuadPart > 0);
    Sleep(20);
    CHECK(QueryPerformanceCounter(&q1) == TRUE);
    CHECK(q1.QuadPart > q0.QuadPart);

    uint64_t t0 = GetTickCount64();
    DWORD g0 = GetTickCount();
    DWORD w0 = timeGetTime();
    Sleep(40);
    uint64_t t1 = GetTickCount64();
    DWORD g1 = GetTickCount();
    DWORD w1 = timeGetTime();
    CHECK(t1 > t0);
    CHECK(t1 - t0 >= 15u);  /* Sleep(40) が時計を十分に進めた (~5ms 余裕) */
    CHECK(t1 - t0 < 5000u); /* 過大に進んでいない (意味論) */
    CHECK(g1 >= g0);
    CHECK(w1 >= w0);
    CHECK(GetTickCount() == (DWORD)GetTickCount64()); /* 下位 32bit 一致 */
}

/* ---------------------------------------------------------------
 * file (§3 #2) — MEMFS 上で byte-faithful 検証 (共通)
 * --------------------------------------------------------------- */
/* "..." を UTF-16 (Latin-1 直接マッピング) に変換するヘルパ */
static unsigned short to_utf16_buf[8][256];
static int to_utf16_next = 0;
static const unsigned short* to_utf16(const char* s) {
    unsigned short* w = to_utf16_buf[to_utf16_next++ & 7];
    size_t i = 0;
    for (; s[i]; i++) w[i] = (unsigned short)(unsigned char)s[i];
    w[i] = 0;
    return w;
}

static void test_file(void) {
    CHECK(mkdir("/flp", 0755) == 0 || errno == EEXIST);

    enum { N = 320 };
    static unsigned char pattern[N];
    for (int i = 0; i < N; i++) pattern[i] = (unsigned char)(i * 37 + 5);

    /* CREATE_ALWAYS で書く */
    HANDLE h = CreateFileW(to_utf16("/flp/m4test.bin"), GENERIC_WRITE, 0, NULL,
                           CREATE_ALWAYS, 0, NULL);
    CHECK(h != INVALID_HANDLE_VALUE);
    DWORD written = 0, got = 0;
    CHECK(WriteFile(h, pattern, N, &written, NULL) == TRUE);
    CHECK(written == N);
    CHECK(CloseHandle(h) == TRUE);

    /* OPEN_EXISTING で読み戻す (byte-faithful) */
    h = CreateFileW(to_utf16("/flp/m4test.bin"), GENERIC_READ, 0, NULL,
                    OPEN_EXISTING, 0, NULL);
    CHECK(h != INVALID_HANDLE_VALUE);
    DWORD sizeHigh = 0;
    DWORD sizeLow = GetFileSize(h, &sizeHigh);
    CHECK(sizeHigh == 0 && sizeLow == (DWORD)N);
    LARGE_INTEGER sz;
    CHECK(GetFileSizeEx(h, &sz) == TRUE && sz.QuadPart == (int64_t)N);

    static unsigned char readback[N + 8];
    memset(readback, 0xAB, sizeof(readback));
    CHECK(ReadFile(h, readback, N, &got, NULL) == TRUE);
    CHECK(got == N);
    CHECK(memcmp(pattern, readback, N) == 0);

    /* EOF でさらに読む → 0 バイト */
    CHECK(ReadFile(h, readback, 64, &got, NULL) == TRUE);
    CHECK(got == 0);

    /* SetFilePointer (head+10) 部分読み */
    CHECK(SetFilePointer(h, 10, NULL, FILE_BEGIN) == 10u);
    CHECK(ReadFile(h, readback, 5, &got, NULL) == TRUE);
    CHECK(got == 5 && memcmp(pattern + 10, readback, 5) == 0);
    CHECK(CloseHandle(h) == TRUE);

    /* 追記は GENERIC_WRITE での open で行う (Win32 と同じく読み込みのみ
     * デスクリプタへの書き込みはエラー) */
    h = CreateFileW(to_utf16("/flp/m4test.bin"), GENERIC_WRITE, 0, NULL,
                    OPEN_EXISTING, 0, NULL);
    CHECK(h != INVALID_HANDLE_VALUE);

    /* SetFilePointerEx (末尾) + 追記 */
    LARGE_INTEGER zero, np, cut;
    zero.QuadPart = 0;
    CHECK(SetFilePointerEx(h, zero, &np, FILE_END) == TRUE);
    CHECK(np.QuadPart == (int64_t)N);
    static const unsigned char tail[8] = {9, 8, 7, 6, 5, 4, 3, 2};
    CHECK(WriteFile(h, tail, sizeof(tail), &written, NULL) == TRUE);
    CHECK(written == sizeof(tail));
    CHECK(CloseHandle(h) == TRUE);

    /* SetEndOfFile による切詰め */
    h = CreateFileW(to_utf16("/flp/m4test.bin"), GENERIC_READ | GENERIC_WRITE, 0,
                    NULL, OPEN_EXISTING, 0, NULL);
    CHECK(h != INVALID_HANDLE_VALUE);
    cut.QuadPart = N + 4;
    CHECK(SetFilePointerEx(h, cut, NULL, FILE_BEGIN) == TRUE);
    CHECK(SetEndOfFile(h) == TRUE);
    CHECK(GetFileSizeEx(h, &sz) == TRUE && sz.QuadPart == (int64_t)(N + 4));
    CHECK(CloseHandle(h) == TRUE);

    /* 存在しないファイル → INVALID_HANDLE_VALUE + GetLastError */
    HANDLE bad = CreateFileW(to_utf16("/flp/no_such_m4.bin"), GENERIC_READ, 0,
                             NULL, OPEN_EXISTING, 0, NULL);
    CHECK(bad == INVALID_HANDLE_VALUE);
    CHECK(GetLastError() == ERROR_FILE_NOT_FOUND);

    /* UTF-16 マルチバイト文字を含むパス (日本語ファイル名相当) */
    static const unsigned short jpName[] = { '/', 'f', 'l', 'p', '/', 'm', '4',
        0x6E2C, 0x8A66, '.', 'b', 'i', 'n', 0 }; /* "/flp/m4テスト.bin" */
    HANDLE hj = CreateFileW(jpName, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    CHECK(hj != INVALID_HANDLE_VALUE);
    static const unsigned char jp[3] = {0x46, 0x4c, 0x30};
    CHECK(WriteFile(hj, jp, sizeof(jp), &written, NULL) == TRUE);
    CHECK(written == sizeof(jp));
    CHECK(CloseHandle(hj) == TRUE);
    hj = CreateFileW(jpName, GENERIC_READ, 0, NULL, OPEN_EXISTING, 0, NULL);
    CHECK(hj != INVALID_HANDLE_VALUE);
    static unsigned char rj[8];
    CHECK(ReadFile(hj, rj, sizeof(jp), &got, NULL) == TRUE);
    CHECK(got == sizeof(jp) && memcmp(jp, rj, sizeof(jp)) == 0);
    CHECK(CloseHandle(hj) == TRUE);
}

/* ---------------------------------------------------------------
 * heap (§3 #7) — 共通
 * --------------------------------------------------------------- */
static void test_heap(void) {
    HGLOBAL g = GlobalAlloc(GMEM_ZEROINIT, 64);
    CHECK(g != NULL);
    for (int i = 0; i < 64; i++) CHECK(((unsigned char*)g)[i] == 0);
    LPVOID lp = GlobalLock(g);
    CHECK(lp != NULL);
    for (int i = 0; i < 64; i++) ((unsigned char*)g)[i] = (unsigned char)i;
    CHECK(GlobalUnlock(g) == TRUE);
    CHECK(GlobalFree(g) == NULL);

    HLOCAL l = LocalAlloc(GPTR, 32); /* GPTR = zero-init */
    CHECK(l != NULL && ((unsigned char*)l)[0] == 0);
    for (int i = 0; i < 32; i++) ((unsigned char*)l)[i] = (unsigned char)~i;
    CHECK(LocalFree(l) == NULL);

    HEAP_HANDLE heap = HeapCreate(0, 0, 0);
    CHECK(heap != NULL && heap != INVALID_HANDLE_VALUE);

    unsigned char* p = (unsigned char*)HeapAlloc(heap, HEAP_ZERO_MEMORY, 128);
    CHECK(p != NULL);
    for (int i = 0; i < 128; i++) p[i] = (unsigned char)(i ^ 0x5A);
    unsigned char* q = (unsigned char*)HeapReAlloc(heap, 0, p, 256);
    CHECK(q != NULL);
    for (int i = 0; i < 128; i++) CHECK(q[i] == (unsigned char)(i ^ 0x5A)); /* 旧 128 バイト保持 */
    CHECK(HeapFree(heap, 0, q) == TRUE);

    /* 繰り返し確保/解放で破綻しない */
    for (int round = 0; round < 16; round++) {
        void* t = HeapAlloc(heap, 0, 33u * (size_t)(round + 1));
        CHECK(t != NULL);
        CHECK(HeapFree(heap, 0, t) == TRUE);
    }
}

/* ---------------------------------------------------------------
 * heap: wasm linear memory の外の値 (LD-132 / #2802)
 *   範囲外のポインタは読まずに扱い、trap しない。HeapFree は native 参照と同じ TRUE (#2821)
 * --------------------------------------------------------------- */
static void test_heap_out_of_range(void) {
    static const uintptr_t bad[] = { 0x1u, 0x3u, 0xFFFFFFF0u, 0xFFFFFFFCu };
    HEAP_HANDLE heap = HeapCreate(0, 0, 0);
    CHECK(heap != NULL);
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
        void* p = (void*)bad[i];
        SetLastError(ERROR_SUCCESS);
        CHECK(HeapFree(heap, 0, p) == TRUE);
        CHECK(GetLastError() == ERROR_SUCCESS);
        CHECK(GlobalLock((HGLOBAL)p) == NULL);
        CHECK(HeapReAlloc(heap, 0, p, 64) == NULL);
        CHECK(GlobalFree((HGLOBAL)p) == (HGLOBAL)p);
    }
    /* 範囲内だが割当てのない p (magic 不一致): 解放せず TRUE (#2821) */
    static unsigned char nonheap[64];
    SetLastError(ERROR_SUCCESS);
    CHECK(HeapFree(heap, 0, nonheap + 32) == TRUE);
    CHECK(GetLastError() == ERROR_SUCCESS);
}

/* ---------------------------------------------------------------
 * CRITICAL_SECTION / Interlocked (§3 #4)
 *   共通部: 再帰・TryEnter・Interlocked (単一スレッド部分)
 * --------------------------------------------------------------- */
static volatile LONG g_cs_counter = 0;
static char g_csMem[512]; /* Delphi が自前で確保する CRITICAL_SECTION 領域相当 */

static void test_critical_section_common(void) {
    g_cs_counter = 0;
    InitializeCriticalSection(g_csMem);
    fprintf(stderr, "[M4-test]   cs: init done\n");

    /* 単一スレッドでの再帰 */
    EnterCriticalSection(g_csMem);
    fprintf(stderr, "[M4-test]   cs: enter1 done\n");
    EnterCriticalSection(g_csMem); /* 再帰 OK */
    fprintf(stderr, "[M4-test]   cs: enter2 done\n");
    CHECK(g_cs_counter == 0);
    LeaveCriticalSection(g_csMem);
    LeaveCriticalSection(g_csMem);
    fprintf(stderr, "[M4-test]   cs: leave done\n");

    /* TryEnter (非保持時に成功・再帰) */
    CHECK(TryEnterCriticalSection(g_csMem) == TRUE);
    CHECK(TryEnterCriticalSection(g_csMem) == TRUE);
    LeaveCriticalSection(g_csMem);
    LeaveCriticalSection(g_csMem);
    fprintf(stderr, "[M4-test]   cs: tryenter done\n");

    /* Interlocked の基本動作 */
    volatile LONG v = 10;
    CHECK(InterlockedExchangeAdd(&v, 5) == 10 && v == 15);
    CHECK(InterlockedExchange(&v, 7) == 15 && v == 7);
    CHECK(InterlockedIncrement(&v) == 8);
    CHECK(InterlockedDecrement(&v) == 7);
    MemoryBarrier();
    fprintf(stderr, "[M4-test]   cs: interlocked done\n");

    /* ふるい: Delete 後は未登録として失敗 (v1) */
    DeleteCriticalSection(g_csMem);
    fprintf(stderr, "[M4-test]   cs: delete done\n");
}

/* ---------------------------------------------------------------
 * event (§3 #4) — MT/ST とも (futex ベースの待機)
 * --------------------------------------------------------------- */
static HANDLE g_test_event = 0;

static void test_event_basic(void) {
    g_test_event = CreateEventW(NULL, TRUE, FALSE, NULL); /* manual-reset */
    CHECK(g_test_event != INVALID_HANDLE_VALUE);

    /* timeout 動作 (未シグナル event へ 30ms 待ち → WAIT_TIMEOUT) */
    LARGE_INTEGER q0, q1;
    CHECK(QueryPerformanceCounter(&q0) == TRUE);
    DWORD rc = WaitForSingleObject(g_test_event, 30);
    CHECK(QueryPerformanceCounter(&q1) == TRUE);
    CHECK(rc == WAIT_TIMEOUT);
    CHECK(q1.QuadPart - q0.QuadPart >= 15); /* 実待機が生じた */

    ResetEvent(g_test_event);
    CHECK(WaitForSingleObject(g_test_event, 5) == WAIT_TIMEOUT);

    /* 存在しないハンドル */
    CHECK(WaitForSingleObject((HANDLE)99999, 1) == WAIT_FAILED);
    CHECK(CloseHandle((HANDLE)99999) == FALSE);
    CHECK(TlsFree(0xFFFFFFFFu) == FALSE); /* 不当 TLS idx は FALSE */

    CHECK(CloseHandle(g_test_event) == TRUE);
    g_test_event = 0;
}

/* ---------------------------------------------------------------
 * TLS (§3 #4) — 共通 (MT では worker 分離を追加)
 * --------------------------------------------------------------- */
static DWORD g_tls_idx = 0xFFFFFFFFu;

static void test_tls_common(void) {
    g_tls_idx = TlsAlloc();
    CHECK(g_tls_idx != 0xFFFFFFFFu);
    CHECK(TlsSetValue(g_tls_idx, (void*)(intptr_t)0x1234) == TRUE);
    CHECK((intptr_t)TlsGetValue(g_tls_idx) == (intptr_t)0x1234);
    CHECK(TlsFree(g_tls_idx) == TRUE);
}

/* ---------------------------------------------------------------
 * thread (§3 #4) — MT のみ
 * --------------------------------------------------------------- */
#if defined(__EMSCRIPTEN_PTHREADS__)
static DWORD WINAPI cs_worker(LPVOID param) {
    (void)param;
    for (int i = 0; i < 10000; i++) {
        EnterCriticalSection(g_csMem);
        g_cs_counter++;
        LeaveCriticalSection(g_csMem);
    }
    return 42;
}

static void test_cs_multithread(void) {
    InitializeCriticalSection(g_csMem);
    /* 4 スレッド × 10,000 回の排他加算 → 並行で合算が壊れない */
    enum { NW = 4 };
    HANDLE th[NW];
    for (int i = 0; i < NW; i++) {
        th[i] = CreateThread(NULL, 0, cs_worker, NULL, 0, NULL);
        CHECK(th[i] != INVALID_HANDLE_VALUE);
    }
    for (int i = 0; i < NW; i++)
        CHECK(WaitForSingleObject(th[i], 60000) == WAIT_OBJECT_0);
    CHECK(g_cs_counter == 40000);
    for (int i = 0; i < NW; i++) CHECK(CloseHandle(th[i]) == TRUE);
    DeleteCriticalSection(g_csMem);
}

static volatile LONG g_atomic_sum = 0;
static volatile LONG g_worker_tls_hit = 0;
static DWORD g_tls_main_idx = 0xFFFFFFFFu;

static DWORD WINAPI worker_fn(LPVOID param) {
    long id = (long)(intptr_t)param;

    /* TLS 分離確認: worker が自分の値を書いても main 側に影響しない */
    if (TlsSetValue(g_tls_main_idx, (void*)(intptr_t)(777 + id)) == TRUE &&
        (intptr_t)TlsGetValue(g_tls_main_idx) == (intptr_t)(777 + id)) {
        InterlockedIncrement(&g_worker_tls_hit);
    }
    for (int i = 0; i < 10; i++) InterlockedExchangeAdd(&g_atomic_sum, 7);
    return 0;
}

static volatile int g_ev_started = 0;
static volatile DWORD g_evt_wait_rc = 0xFFFFFFFFu;

static DWORD WINAPI ev_waiter(LPVOID param) {
    (void)param;
    g_ev_started = 1;
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    g_evt_wait_rc = WaitForSingleObject(g_test_event, 10000);
    return 0;
}

static DWORD WINAPI exit_thread_fn(LPVOID param) {
    (void)param;
    InterlockedExchangeAdd(&g_atomic_sum, 1000);
    ExitThread(123);
    return 0; /* 到達しない */
}

static void test_thread_set(void) {
    /* TLS 分離: main 側の値を設定してから worker を起動 */
    g_tls_main_idx = TlsAlloc();
    CHECK(g_tls_main_idx != 0xFFFFFFFFu);
    CHECK(TlsSetValue(g_tls_main_idx, (void*)(intptr_t)0x1234) == TRUE);

    g_atomic_sum = 0;
    g_worker_tls_hit = 0;

    /* event: manual-reset, non-signaled を worker に待たせる */
    g_test_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    CHECK(g_test_event != INVALID_HANDLE_VALUE);
    CHECK(SetEvent(g_test_event) == TRUE);
    CHECK(WaitForSingleObject(g_test_event, 10) == WAIT_OBJECT_0); /* シグナルで即成功 */
    CHECK(ResetEvent(g_test_event) == TRUE);

    enum { NW = 4 };
    HANDLE threads[NW];
    for (int i = 0; i < NW; i++) {
        threads[i] = CreateThread(NULL, 0, worker_fn, (LPVOID)(long)i, 0, NULL);
        CHECK(threads[i] != INVALID_HANDLE_VALUE);
    }

    HANDLE evt_thread = CreateThread(NULL, 0, ev_waiter, NULL, 0, NULL);
    CHECK(evt_thread != INVALID_HANDLE_VALUE);
    while (__atomic_load_n(&g_ev_started, __ATOMIC_SEQ_CST) == 0) Sleep(1);
    CHECK(SetEvent(g_test_event) == TRUE);
    CHECK(WaitForSingleObject(evt_thread, 30000) == WAIT_OBJECT_0);
    CHECK(g_evt_wait_rc == WAIT_OBJECT_0);
    CHECK(CloseHandle(evt_thread) == TRUE);

    /* join (WaitForSingleObject で thread 終了を待つ) */
    for (int i = 0; i < NW; i++)
        CHECK(WaitForSingleObject(threads[i], 60000) == WAIT_OBJECT_0);
    CHECK(g_atomic_sum == (LONG)(NW * 10 * 7));
    CHECK(g_worker_tls_hit == NW);

    /* TLS 分離: worker 側の 777+i が main 側 0x1234 を壊していない */
    CHECK((intptr_t)TlsGetValue(g_tls_main_idx) == (intptr_t)0x1234);
    CHECK(TlsFree(g_tls_main_idx) == TRUE);

    /* ExitThread: routine 内からの強制終了でも待機者が閉じ込められない。
     * (ExitThread 自体が done フラグを立てるため、trampoline に残る
     * 加算 1000 は行われた状態で即終了し、Wait で回収できる) */
    HANDLE ex = CreateThread(NULL, 0, exit_thread_fn, NULL, 0, NULL);
    CHECK(ex != INVALID_HANDLE_VALUE);
    CHECK(WaitForSingleObject(ex, 30000) == WAIT_OBJECT_0);
    CHECK(g_atomic_sum >= 1000);
    CHECK(CloseHandle(ex) == TRUE);

    CHECK(CloseHandle(g_test_event) == TRUE);
    g_test_event = 0;
}
#endif /* __EMSCRIPTEN_PTHREADS__ */

/* ---------------------------------------------------------------
 * main
 * --------------------------------------------------------------- */
int main(void) {
    test_timer();
    test_file();
    test_heap();
    test_heap_out_of_range();
    test_critical_section_common();
    test_event_basic();
    test_tls_common();
#if defined(__EMSCRIPTEN_PTHREADS__)
    test_cs_multithread();
    test_thread_set();
    g_build = "mt(pthreads)";
#else
    printf("[M4-test] NOTE: pthread tests skipped in single-thread build\n");
    g_build = "st(single-thread)";
#endif
    printf("[M4-test] ALL PASS (build=%s)\n", g_build);
    fflush(stdout);
    return 0;
}
