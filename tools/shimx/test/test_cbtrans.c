/* shimx 単体テスト: R2 コールバック変換の実体 (cbtrans.c) + R3 lift ABI トークン表 (CAB-177)。
 *   - 模擬 lift closure: VA→関数表 (m11_icall 形 uniform u64×8 invoke) を C で再現し、
 *     shimx 7 API への VA 登録 → トランポリン → invoke → lift 側関数本体の往復を検査
 *   - BLK 方式 (__icall_dispatch 相当) への invoke 差し替えも同一フックで動くことを検査
 *   - R3: GetProcAddress → トークン → shimx_lifttab_trampoline → u64×8 実呼出
 * (フック口自体のテストは test_link.c test_r2_callback_translator / R3 組込み表は test_r3_proctable)
 */
#include "test_common.h"
#include <string.h>

typedef unsigned long long u64x;
typedef u64x (*shx_thunk8)(u64x, u64x, u64x, u64x, u64x, u64x, u64x, u64x);
typedef void (*shx_test_PTP_WORK_CALLBACK)(void* instance, void* ctx, void* work);   /* shimx の thread.c と同形 */

/* ---------------------------------------------------------------
 * 模擬 lift 側: VA 関数表 + uniform ABI (m11_icall 相当)
 * --------------------------------------------------------------- */
#define VA_ENUMP   0x4476d0u     /* M11 純リンク unit 18 の実測値 (closure 外コールバック) */
#define VA_ENUMP2  0x447710u
#define VA_THREAD  0x447750u
#define VA_FLS     0x447790u
#define VA_TIMER   0x4477d0u
#define VA_POOL    0x447810u
#define VA_INITONCE 0x447850u
#define VA_UNKNOWN 0x9ffff0u     /* 関数表に無い VA (graceful 0 の検査用) */

static int g_fn_enump_hits, g_fn_enump2_hits, g_fn_thread_ran, g_fn_fls_hits, g_fn_timer_hits,
           g_fn_pool_hits, g_fn_initonce_hits;
static uintptr_t g_fn_enump_last_arg, g_fn_fls_last, g_fn_pool_arg2;
static u64x g_fn_initonce_ret;

static u64x fn_enump(u64x a0) { g_fn_enump_hits++; g_fn_enump_last_arg = (uintptr_t)a0; return 1; }
static u64x fn_enump2(u64x a0) { (void)a0; g_fn_enump2_hits++; return 1; }
static u64x fn_thread(u64x a0) { (void)a0; g_fn_thread_ran = 1; return 42; }
static u64x fn_fls(u64x a0) { g_fn_fls_hits++; g_fn_fls_last = (uintptr_t)a0; return 0; }
static u64x fn_timer(u64x a0, u64x a1) { (void)a1; g_fn_timer_hits++; return 0; }
static u64x fn_pool(u64x a0, u64x a1, u64x a2) { (void)a0; g_fn_pool_arg2 = (uintptr_t)a2; g_fn_pool_hits++; return 0; }
static u64x fn_initonce(u64x a0, u64x a1, u64x a2) {
    (void)a0; (void)a2;
    g_fn_initonce_hits++;
    g_fn_initonce_ret = a1;
    return 1;
}

/* lift 関数表に置かれる uniform ABI トランポリン (= m11_tr_* / icall 表の fn 相当) */
#define LIFT_TR(nm, body) \
    static u64x nm(u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) { \
        (void)a1; (void)a2; (void)a3; (void)a4; (void)a5; (void)a6; (void)a7; body \
    }
LIFT_TR(tr_enump, return fn_enump(a0);)
LIFT_TR(tr_enump2, return fn_enump2(a0);)
LIFT_TR(tr_thread, return fn_thread(a0);)
LIFT_TR(tr_fls, return fn_fls(a0);)
LIFT_TR(tr_timer, return fn_timer(a0, a1);)
LIFT_TR(tr_pool, return fn_pool(a0, a1, a2);)
LIFT_TR(tr_initonce, return fn_initonce(a0, a1, a2);)

typedef struct { uint32_t va; shx_thunk8 fn; } LiftEnt;
/* ソート済み VA 関数表 (= m11_disp_tab / icall_tbl 相当) */
static const LiftEnt g_liftfn[] = {
    { VA_ENUMP, tr_enump }, { VA_ENUMP2, tr_enump2 }, { VA_THREAD, tr_thread }, { VA_FLS, tr_fls },
    { VA_TIMER, tr_timer }, { VA_POOL, tr_pool }, { VA_INITONCE, tr_initonce },
};
#define LIFTN (sizeof g_liftfn / sizeof g_liftfn[0])
static shx_thunk8 lift_find(uint32_t va) {
    unsigned lo = 0, hi = LIFTN;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (g_liftfn[mid].va < va) lo = mid + 1; else hi = mid;
    }
    if (lo < LIFTN && g_liftfn[lo].va == va) return g_liftfn[lo].fn;
    return NULL;
}

/* invoke: m11_icall と同形 (va 照合は +0x400000 を先に試す規約も再現) */
static u64x mock_invoke(u64x va, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) {
    shx_thunk8 f = lift_find((uint32_t)(va + 0x400000ull));
    if (!f) f = lift_find((uint32_t)va);
    if (!f) return 0;                       /* closure 外 → 0 (列挙打切り等)。trap にしない */
    return f(a0, a1, a2, a3, a4, a5, a6, a7);
}

/* ---------------------------------------------------------------
 * BLK 方式 (__icall_dispatch 相当) の invoke: 引数を共有 BLK に載せ替えて f() を呼ぶ
 * --------------------------------------------------------------- */
#define BLK_TGT 0
#define BLK_A0  8
#define BLK_A1  16
#define BLK_A2  24
#define BLK_RET 128
static u64x g_blk[40];
static int g_blk_dispatch_hits;
static u64x blk_enump_fn(void) {           /* icall route: 全 lifted 関数が i64 f(void) の一様 ABI */
    g_blk_dispatch_hits++;
    return g_blk[BLK_A0 >> 3] ? 1 : 0;     /* BLK[A0] に列挙文字列ポインタが載っている前提の最小確認 */
}
static void ic_dispatch(void) {            /* __icall_dispatch(site) 相当: BLK[0] の target を表引き */
    if ((uint32_t)g_blk[BLK_TGT >> 3] == VA_ENUMP2) { g_blk[BLK_RET >> 3] = blk_enump_fn(); return; }
    fprintf(stderr, "[cbtrans-test] FAIL-FAST: unresolved indirect target 0x%x\n", (uint32_t)g_blk[BLK_TGT >> 3]);
    abort();
}
static u64x blk_invoke(u64x va, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) {
    (void)a3; (void)a4; (void)a5; (void)a6; (void)a7;
    g_blk[BLK_TGT >> 3] = va;
    g_blk[BLK_A0 >> 3] = a0;
    g_blk[BLK_A1 >> 3] = a1;
    g_blk[BLK_A2 >> 3] = a2;
    g_blk[BLK_RET >> 3] = 0;
    ic_dispatch();
    return g_blk[BLK_RET >> 3];
}

/* ---------------------------------------------------------------
 * 実 C 関数ポインタ (恒等経路 = M4 互換) の検収用スパイ
 * --------------------------------------------------------------- */
static int g_c_enump_hits, g_c_cal_hits;
static BOOL c_enump(LPWSTR s) { (void)s; g_c_enump_hits++; return TRUE; }
static BOOL c_cal(LPWSTR s) { (void)s; g_c_cal_hits++; return TRUE; }

static void reset_counters(void) {
    g_fn_enump_hits = g_fn_enump2_hits = g_fn_thread_ran = g_fn_fls_hits = g_fn_timer_hits = 0;
    g_fn_pool_hits = g_fn_initonce_hits = g_c_enump_hits = g_c_cal_hits = 0;
    g_fn_enump_last_arg = g_fn_fls_last = g_fn_pool_arg2 = 0;
    g_blk_dispatch_hits = 0;
    shimx_cbtrans_reset();
}

static void test_cbtrans_sync_enum(void) {
    reset_counters();
    shimx_cbtrans_set_invoke(mock_invoke);
    CHECK(shimx_cbtrans_install() == NULL);                       /* 前のフックは無し */
    CHECK(shimx_get_callback_translator() == (shimx_callback_translator_fn)shimx_cb_translator);

    /* EnumSystemLocalesW: VA 登録 → 全ロケール列挙で lift 側 fn_enump が往復実行 */
    CHECK(EnumSystemLocalesW((LOCALE_ENUMPROCW)(uintptr_t)VA_ENUMP, 0));
    CHECK(g_fn_enump_hits >= 4);                                  /* shimx のロケール表 (en-US 等複数) */
    CHECK(g_fn_enump_last_arg != 0);                              /* LPWSTR が渡っている */
    CHECK(shimx_cbtrans_slots() == 1 && shimx_cbtrans_calls() >= 4);

    /* 同一 VA の再登録は同一トランポリン (slot 安定 = 寿命契約) */
    void* t1 = shimx_cb_translator("EnumSystemLocalesW", (void*)(uintptr_t)VA_ENUMP);
    void* t2 = shimx_cb_translator("EnumSystemLocalesW", (void*)(uintptr_t)VA_ENUMP);
    CHECK(t1 && t1 == t2);
    CHECK(shimx_cbtrans_slots() == 1);

    /* 別 VA は別 slot */
    CHECK(shimx_cb_translator("EnumSystemLocalesW", (void*)(uintptr_t)VA_ENUMP2) != NULL);
    CHECK(shimx_cbtrans_slots() == 2);

    /* EnumCalendarInfoW (shimx の CALINFO_ENUMPROCW は 1 引数): type=5 (日付書式) で 1 回呼ばれる */
    g_fn_enump_hits = 0;
    CHECK(EnumCalendarInfoW((CALINFO_ENUMPROCW)(uintptr_t)VA_ENUMP, 0x0409, 1, 5));
    CHECK(g_fn_enump_hits == 1);

    /* InitOnceExecuteOnce: i3 形状。lift 側 fn が 1 回だけ実行され once が完了する */
    uint32_t once[2] = { 0, 0 };
    LPVOID ctx = NULL;
    CHECK(InitOnceExecuteOnce((PINIT_ONCE)once, (PINIT_ONCE_FN)(uintptr_t)VA_INITONCE, (LPVOID)0x51AB, &ctx));
    CHECK(g_fn_initonce_hits == 1 && g_fn_initonce_ret == 0x51ab);
    CHECK(InitOnceExecuteOnce((PINIT_ONCE)once, (PINIT_ONCE_FN)(uintptr_t)VA_INITONCE, (LPVOID)0x51AB, &ctx));
    CHECK(g_fn_initonce_hits == 1);                               /* 完了済みなので fn は呼ばれない */

    /* closure 外 VA (関数表に無い) → invoke が 0 を返し列挙は打ち切られるが trap しない */
    g_fn_enump_hits = 0;
    CHECK(EnumSystemLocalesW((LOCALE_ENUMPROCW)(uintptr_t)VA_UNKNOWN, 0));
    CHECK(g_fn_enump_hits == 0 && shimx_cbtrans_slots() == 4);   /* ENUMP/ENUMP2/INITONCE/UNKNOWN */
}

static void test_cbtrans_identity(void) {
    reset_counters();
    /* 実 C 関数ポインタ (< intptr limit) は恒等通過: M4 互換テスト等の直接 C 呼出を壊さない */
    CHECK(shimx_cb_translator("EnumSystemLocalesW", (void*)c_enump) == (void*)c_enump);
    CHECK(shimx_cb_translator("CreateThread", (void*)c_enump) == (void*)c_enump);
    CHECK(EnumSystemLocalesW(c_enump, 0) && g_c_enump_hits >= 4);
    CHECK(EnumCalendarInfoW(c_cal, 0x0409, 1, 5) && g_c_cal_hits == 1);
    CHECK(shimx_cbtrans_calls() == 0);                            /* C ポインタはトランポリンを経由しない */
    /* 閾値連動: 閾値を大きくすると VA も「実ポインタ扱い」になる (R1 と共通の 1 変数) */
    shimx_set_intptr_limit(0x1000000);
    CHECK(shimx_cb_translator("EnumSystemLocalesW", (void*)(uintptr_t)VA_ENUMP) == (void*)(uintptr_t)VA_ENUMP);
    shimx_set_intptr_limit(0x10000);
    CHECK(shimx_cb_translator("EnumSystemLocalesW", (void*)(uintptr_t)VA_ENUMP) != (void*)(uintptr_t)VA_ENUMP);
}

static void test_cbtrans_blk_route(void) {
    /* invoke を BLK 方式 (__icall_dispatch 相当) に差し替え: 同一フックで icall route も動く */
    shimx_cbtrans_set_invoke(blk_invoke);
    g_fn_enump2_hits = 0;
    CHECK(EnumSystemLocalesW((LOCALE_ENUMPROCW)(uintptr_t)VA_ENUMP2, 0));
    CHECK(g_blk_dispatch_hits >= 4);                              /* BLK 経由で lift fn (blk_enump_fn) が実行 */
    shimx_cbtrans_set_invoke(mock_invoke);
}

#if defined(__EMSCRIPTEN_PTHREADS__)
static void test_cbtrans_async(void) {
    /* CreateThread: VA の start ルーチンが実スレッドで実行され戻り値が lift 側の 42 */
    g_fn_thread_ran = 0;
    HANDLE h = CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)(uintptr_t)VA_THREAD, NULL, 0, NULL);
    CHECK(h);
    DWORD ec = STILL_ACTIVE;
    for (int i = 0; i < 500 && ec == STILL_ACTIVE; i++) { Sleep(2); CHECK(GetExitCodeThread(h, &ec)); }
    CHECK(ec == 42 && g_fn_thread_ran);
    CloseHandle(h);

    /* CreateTimerQueueTimer: VA コールバックがワーカースレッドから複数回呼ばれる */
    g_fn_timer_hits = 0;
    HANDLE th = NULL;
    CHECK(CreateTimerQueueTimer(&th, NULL, (WAITORTIMERCALLBACK)(uintptr_t)VA_TIMER, (PVOID)0x77, 10, 30, 0));
    for (int i = 0; i < 300 && g_fn_timer_hits < 2; i++) Sleep(2);
    CHECK(g_fn_timer_hits >= 2);
    CHECK(DeleteTimerQueueTimer(NULL, th, NULL));

    /* CreateThreadpoolWork: Submit ごとに v3 形状 (inst, ctx, work) で実行 */
    g_fn_pool_hits = 0;
    void* w = CreateThreadpoolWork((shx_test_PTP_WORK_CALLBACK)(uintptr_t)VA_POOL, (void*)0x88, NULL);
    CHECK(w);
    SubmitThreadpoolWork(w);
    for (int i = 0; i < 300 && g_fn_pool_hits < 1; i++) Sleep(2);
    CHECK(g_fn_pool_hits == 1 && g_fn_pool_arg2 == (uintptr_t)w);
    CloseThreadpoolWork(w);
    Sleep(20);
}
#endif

static void test_cbtrans_fls(void) {
    /* FlsAlloc: FlsFree 時に VA コールバックが marker 付きで実行される (寿命: FLS スロット解放まで) */
    g_fn_fls_hits = 0;
    DWORD fls = FlsAlloc((PFLS_CALLBACK_FUNCTION)(uintptr_t)VA_FLS);
    CHECK(fls != FLS_OUT_OF_INDEXES);
    CHECK(FlsSetValue(fls, (void*)0x51AB));
    CHECK(FlsFree(fls));
    CHECK(g_fn_fls_hits == 1 && g_fn_fls_last == 0x51ab);
}

/* ---------------------------------------------------------------
 * R3: lift ABI トークン表
 * --------------------------------------------------------------- */
static void test_cbtrans_r3_lifttab(void) {
    HMODULE sh = GetModuleHandleW(W("shell32.dll"));
    HMODULE k32 = GetModuleHandleW(W("kernel32.dll"));
    CHECK(sh && k32);

    /* resolver 未接続: 組込み表の実 C ポインタ (CAB-211 からの既存挙動) */
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)152) == (void*)ILGetSize);
    CHECK(GetProcAddress(k32, "GetThreadUILanguage") == (void*)GetThreadUILanguage);

    /* resolver 接続: IL* と UI言語 が lift 関数表から解決可能なトークンになる */
    shimx_set_proc_resolver(shimx_lifttab_proc_resolver);
    void* tok_size = GetProcAddress(sh, (LPCSTR)(uintptr_t)152);
    void* tok_free = GetProcAddress(sh, "ILFree");
    void* tok_lang = GetProcAddress(k32, "GetThreadUILanguage");
    CHECK(tok_size && tok_size != (void*)ILGetSize);              /* トークン (実ポインタではない) */
    CHECK(tok_free && tok_lang);
    CHECK((uintptr_t)tok_size >= 0x7F000000u);                    /* トークン域 = wasm メモリ上限外 */

    /* トークン → u64×8 thunk → 実体呼出の往復 (lift dispatch の --wrap=m11_icall 相当を模擬) */
    shimx_lift_thunk_fn th = shimx_lifttab_trampoline((unsigned)(uintptr_t)tok_size);
    CHECK(th != NULL);
    /* shimx 自前 PIDL ([u16 cb][UTF-16 path+NUL][u16 0]): "C:\x" = cb 12 + 終端 2 = 14 バイト (pidl_make と同一) */
    static const uint8_t pidl[] = { 12, 0, 'C', 0, ':', 0, '\\', 0, 'x', 0, 0, 0, 0, 0 };
    CHECK(th((u64x)(uintptr_t)pidl, 0, 0, 0, 0, 0, 0, 0) == 14);

    shimx_lift_thunk_fn th_eq = shimx_lifttab_trampoline((unsigned)(uintptr_t)GetProcAddress(sh, (LPCSTR)(uintptr_t)21));
    CHECK(th_eq != NULL);
    CHECK(th_eq((u64x)(uintptr_t)pidl, (u64x)(uintptr_t)pidl, 0, 0, 0, 0, 0, 0) == 1);   /* ILIsEqual */

    shimx_lift_thunk_fn th_lang = shimx_lifttab_trampoline((unsigned)(uintptr_t)tok_lang);
    CHECK(th_lang != NULL && th_lang(0, 0, 0, 0, 0, 0, 0, 0) == 0x409);                  /* GetThreadUILanguage = en-US */

    /* 序数 #16 (ILFindLastID) もトークン化。単項リストでは自身を返す */
    shimx_lift_thunk_fn th_fl = shimx_lifttab_trampoline((unsigned)(uintptr_t)GetProcAddress(sh, (LPCSTR)(uintptr_t)16));
    CHECK(th_fl != NULL && th_fl((u64x)(uintptr_t)pidl, 0, 0, 0, 0, 0, 0, 0) == (u64x)(uintptr_t)pidl);

    /* ILFree 往復 (void 戻り): thunk 経由の解放が abort しない */
    void* p = ILCreateFromPathW(W("C:\\x"));
    CHECK(p);
    shimx_lift_thunk_fn th_free = shimx_lifttab_trampoline((unsigned)(uintptr_t)tok_free);
    CHECK(th_free != NULL && th_free((u64x)(uintptr_t)p, 0, 0, 0, 0, 0, 0, 0) == 0);

    /* SHX-T8: shell32 #74 / shlwapi #12・#219 もトークン化される。未知序数は対象外 */
    CHECK(shimx_lifttab_token(NULL, 74) != 0 && shimx_lifttab_token(NULL, 75) == 0);
    HMODULE shl = GetModuleHandleW(W("shlwapi.dll"));
    CHECK(shl);
    void* tok_ms = GetProcAddress(shl, (LPCSTR)(uintptr_t)12);
    void* tok_qi = GetProcAddress(shl, (LPCSTR)(uintptr_t)219);
    CHECK((uintptr_t)tok_ms >= 0x7F000000u && (uintptr_t)tok_qi >= 0x7F000000u && tok_ms != tok_qi);
    CHECK(GetProcAddress(shl, (LPCSTR)(uintptr_t)16) == NULL);              /* shlwapi #16 は shell32 #16 のトークンを返してはならない */
    shimx_lift_thunk_fn th_ms = shimx_lifttab_trampoline((unsigned)(uintptr_t)tok_ms);
    CHECK(th_ms != NULL);
    void* ms = (void*)(uintptr_t)th_ms((u64x)(uintptr_t)"abc", 3, 0, 0, 0, 0, 0, 0);
    CHECK(ms != NULL);
    uint64_t* vt = (uint64_t*)(uintptr_t)*(uint64_t*)ms;
    char buf[8]; ULONG got = 0;
    CHECK(((HRESULT (*)(void*, void*, ULONG, ULONG*))(uintptr_t)vt[3])(ms, buf, 3, &got) == S_OK && got == 3 && !memcmp(buf, "abc", 3));
    ((ULONG (*)(void*))(uintptr_t)vt[2])(ms);
    shimx_lift_thunk_fn th_en = shimx_lifttab_trampoline((unsigned)(uintptr_t)GetProcAddress(sh, (LPCSTR)(uintptr_t)74));
    CHECK(th_en != NULL);
    void* en = NULL; uint8_t fe[32] = { 0x0F, 0 };
    CHECK(th_en(1, (u64x)(uintptr_t)fe, (u64x)(uintptr_t)&en, 0, 0, 0, 0, 0) == 0 && en);
    ((ULONG (*)(void*))(uintptr_t)(*(uint64_t**)en)[2])(en);

    /* 解除: 組込み表の実 C ポインタに戻る */
    shimx_set_proc_resolver(NULL);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)152) == (void*)ILGetSize);
    CHECK(shimx_lifttab_trampoline(0x7fffffffu) == NULL);         /* 未知トークン */
}

void run_cbtrans_tests(int multithread) {
    (void)multithread;
    test_cbtrans_sync_enum();
    test_cbtrans_identity();
    test_cbtrans_blk_route();
#if defined(__EMSCRIPTEN_PTHREADS__)
    test_cbtrans_async();
#endif
    test_cbtrans_fls();
    test_cbtrans_r3_lifttab();
    /* 掃除: 後続テスト (既存 R1〜R8) に影響を残さない */
    shimx_set_callback_translator(NULL);
    shimx_set_proc_resolver(NULL);
    shimx_cbtrans_reset();
}
