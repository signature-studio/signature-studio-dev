/* cb_mod.c — hostbridge/cb: shimx R2 コールバック変換の実体接続を「実リンク構成」で往復検証するハーネス (CAB-177)。
 *
 * 構成 (= tools/hostbridge/h2 の module+driver 流儀の mini 版):
 *   - shimx 全ソースを**無改変**でリンク (src/*.c)
 *   - 模擬 lift closure: VA→関数表 (m11_disp_tab / icall_tbl 相当) + uniform u64×8 ABI の lift 関数
 *   - invoke を差し替え可能: (a) m11_icall 形 (表引き+直接呼出) (b) __icall_dispatch 形
 *     (BLK への引数 store → dispatch → i64 f(void)) — tools/icall/rt/icall_rt.c の縮約再現
 *   - guest 側エントリ (exported): lifted コードの振舞を再現し shimx 7 API / R3 トークンを駆動
 *   - constructor で boot (shimx_link の sx_cbboot と同一手順): invoke 登録 + translator 取付 + proc_resolver
 *
 * 検証の往復: guest が shimx API に guest VA を渡す → shimx が cbtrans トランポリン経由で invoke へ →
 * lift 関数表で本体実行 → 戻り値が shimx API を通じて guest に戻る。
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <emscripten.h>
#include "shimx.h"

typedef unsigned long long u64x;
typedef u64x (*shx_thunk8)(u64x, u64x, u64x, u64x, u64x, u64x, u64x, u64x);

#define LB 0x400000u            /* VA = LVA + 0x400000 (M11 image 敷設規約と同じ) */
#define VA_ENUMCAL 0x4476d0u    /* 実測: M11 純リンク unit 18 の EnumCalendarInfoW コールバック */
#define VA_ENUMLOC 0x447710u
#define VA_ENUMLOC2 0x447740u   /* BLK route 用 */
#define VA_THREAD  0x447780u
#define VA_FLS     0x4477c0u
#define VA_TIMER   0x447800u
#define VA_POOL    0x447840u
#define VA_INITONCE 0x447880u
#define VA_UNKNOWN 0x9ffff0u

/* ---- lift 側カウンタ (JS から検査する) ---- */
static int g_cal_hits, g_loc_hits, g_loc2_hits, g_thread_ran, g_fls_hits, g_timer_hits, g_pool_hits,
           g_initonce_hits, g_blk_hits, g_invoke_miss, g_invoke_ok;
static uintptr_t g_cal_last_arg, g_fls_last, g_pool_arg3;
static u64x g_thread_rc;

static u64x fn_enumcal(u64x a0) { g_cal_hits++; g_cal_last_arg = (uintptr_t)a0; return 1; }
static u64x fn_enumloc(u64x a0) { (void)a0; g_loc_hits++; return 1; }
static u64x fn_enumloc2(u64x a0) { (void)a0; g_loc2_hits++; return 1; }
static u64x fn_thread(u64x a0) { (void)a0; g_thread_ran = 1; g_thread_rc = 42; return 42; }
static u64x fn_fls(u64x a0) { g_fls_hits++; g_fls_last = (uintptr_t)a0; return 0; }
static u64x fn_timer(u64x a0, u64x a1) { (void)a1; g_timer_hits++; return 0; }
static u64x fn_pool(u64x a0, u64x a1, u64x a2) { (void)a0; (void)a1; g_pool_arg3 = (uintptr_t)a2; g_pool_hits++; return 0; }
static u64x fn_initonce(u64x a0, u64x a1, u64x a2) { (void)a0; (void)a2; g_initonce_hits++; return a1 ? 1 : 0; }

#define LIFT_TR(nm, body) \
    static u64x nm(u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) { \
        (void)a1; (void)a2; (void)a3; (void)a4; (void)a5; (void)a6; (void)a7; body \
    }
LIFT_TR(tr_enumcal, return fn_enumcal(a0);)
LIFT_TR(tr_enumloc, return fn_enumloc(a0);)
LIFT_TR(tr_enumloc2, return fn_enumloc2(a0);)
LIFT_TR(tr_thread, return fn_thread(a0);)
LIFT_TR(tr_fls, return fn_fls(a0);)
LIFT_TR(tr_timer, return fn_timer(a0, a1);)
LIFT_TR(tr_pool, return fn_pool(a0, a1, a2);)
LIFT_TR(tr_initonce, return fn_initonce(a0, a1, a2);)

typedef struct { uint32_t va; shx_thunk8 fn; } LiftEnt;
/* ソート済み VA→fn 表 = m11_disp_tab / icall_tbl 相当 (実 lift IR から生成される関数表の模倣) */
static const LiftEnt g_liftfn[] = {
    { VA_ENUMCAL, tr_enumcal }, { VA_ENUMLOC, tr_enumloc }, { VA_ENUMLOC2, tr_enumloc2 },
    { VA_THREAD, tr_thread }, { VA_FLS, tr_fls }, { VA_TIMER, tr_timer },
    { VA_POOL, tr_pool }, { VA_INITONCE, tr_initonce },
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

/* ---- invoke (a): m11_icall 形 (tools/m11/m11_ov.c と同規約: +0x400000 を先に試す) ---- */
static u64x ic_invoke_m11(u64x va, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) {
    shx_thunk8 f = lift_find((uint32_t)(va + LB));
    if (!f) f = lift_find((uint32_t)va);
    if (!f) { g_invoke_miss++; return 0; }    /* closure 外 → 0 (穏当な打切り, trap しない) */
    g_invoke_ok++;
    return f(a0, a1, a2, a3, a4, a5, a6, a7);
}

/* ---- invoke (b): __icall_dispatch 形 (BLK + 一様 ABI i64 f(void); tools/icall/rt/icall_rt.c 縮約) ---- */
static u64x g_icblk[32];                /* BLK (実装では固定アドレス; ここは縮約で静的バッファ) */
#define BLKQ(off) (g_icblk[(off) >> 3])
static u64x blk_loc2_fn(void) { g_blk_hits++; return BLKQ(8) ? 1 : 0; }   /* 一様 ABI の lift 関数本体 */
static void ic_dispatch(uint32_t site) {
    (void)site;
    uint32_t t = (uint32_t)BLKQ(0);
    if (t == VA_ENUMLOC2) { g_invoke_ok++; BLKQ(0x80) = blk_loc2_fn(); return; }
    fprintf(stderr, "[cb] FAIL-FAST: unresolved indirect target 0x%x at site 0x%x\n", t, site);
    emscripten_force_exit(3);
}
static u64x ic_invoke_blk(u64x va, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) {
    (void)a3; (void)a4; (void)a5; (void)a6; (void)a7;
    BLKQ(0) = va; BLKQ(8) = a0; BLKQ(0x10) = a1; BLKQ(0x18) = a2; BLKQ(0x80) = 0;
    ic_dispatch(0x401000u);
    return BLKQ(0x80);
}

/* ---- boot (shimx_link sx_cbboot と同一手順) ---- */
static int g_booted;
static void cb_boot(void) {
    if (g_booted) return;
    shimx_cbtrans_set_invoke(ic_invoke_m11);
    shimx_cbtrans_install();
    shimx_set_proc_resolver(shimx_lifttab_proc_resolver);
    g_booted = 1;
}
__attribute__((constructor)) static void cb_boot_ctor(void) { cb_boot(); }
EMSCRIPTEN_KEEPALIVE int cb_booted(void) { return g_booted; }   /* constructor が走ったことの確認用 */

/* ---- R3: lift dispatch 側 (--wrap=m11_icall 相当): token → thunk → 実体 ---- */
static u64x lift_dispatch(u64x target, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) {
    shimx_lift_thunk_fn th = shimx_lifttab_trampoline((unsigned)target);
    if (th) return th(a0, a1, a2, a3, a4, a5, a6, a7);
    return ic_invoke_m11(target, a0, a1, a2, a3, a4, a5, a6, a7);   /* 実 lift 関数表へ (通常経路) */
}

/* ===============================================================
 * guest 側エントリ (= lifted コードの振舞)
 * =============================================================== */
EMSCRIPTEN_KEEPALIVE int g_enum_calendar(void) {   /* M11 unit 18 と同じ形: VA 定数を直接渡す */
    EnumCalendarInfoW((CALINFO_ENUMPROCW)(uintptr_t)VA_ENUMCAL, 0x0409, 1, 5);
    return g_cal_hits;
}
EMSCRIPTEN_KEEPALIVE int g_enum_locales(void) {
    EnumSystemLocalesW((LOCALE_ENUMPROCW)(uintptr_t)VA_ENUMLOC, 0);
    return g_loc_hits;
}
EMSCRIPTEN_KEEPALIVE int g_enum_unknown(void) {    /* closure 外 VA: trap せず 0 で打ち切られる */
    int before = g_invoke_miss;
    EnumSystemLocalesW((LOCALE_ENUMPROCW)(uintptr_t)VA_UNKNOWN, 0);
    return (g_invoke_miss - before) * 100 + g_loc_hits;
}
EMSCRIPTEN_KEEPALIVE int g_initonce(void) {
    uint32_t once[2] = { 0, 0 };
    InitOnceExecuteOnce((PINIT_ONCE)once, (PINIT_ONCE_FN)(uintptr_t)VA_INITONCE, (LPVOID)0x51AB, NULL);
    InitOnceExecuteOnce((PINIT_ONCE)once, (PINIT_ONCE_FN)(uintptr_t)VA_INITONCE, (LPVOID)0x51AB, NULL);
    return g_initonce_hits;                        /* 1 完了済みの 2 度目は fn 不呼出 */
}
#if defined(__EMSCRIPTEN_PTHREADS__)
EMSCRIPTEN_KEEPALIVE int g_thread(void) {
    HANDLE h = CreateThread(NULL, 0, (LPTHREAD_START_ROUTINE)(uintptr_t)VA_THREAD, NULL, 0, NULL);
    if (!h) return -1;
    DWORD ec = 0;
    for (int i = 0; i < 500 && ec == 0; i++) { Sleep(2); GetExitCodeThread(h, &ec); if (ec != 259 /*STILL_ACTIVE*/) break; }
    CloseHandle(h);
    return (int)g_thread_rc;
}
EMSCRIPTEN_KEEPALIVE int g_timer(void) {
    HANDLE th = NULL;
    if (!CreateTimerQueueTimer(&th, NULL, (WAITORTIMERCALLBACK)(uintptr_t)VA_TIMER, (PVOID)0x77, 10, 30, 0)) return -1;
    for (int i = 0; i < 300 && g_timer_hits < 2; i++) Sleep(2);
    DeleteTimerQueueTimer(NULL, th, NULL);
    return g_timer_hits;
}
EMSCRIPTEN_KEEPALIVE int g_pool(void) {
    void* w = CreateThreadpoolWork((void (*)(void*, void*, void*))(uintptr_t)VA_POOL, (void*)0x88, NULL);
    if (!w) return -1;
    SubmitThreadpoolWork(w);
    for (int i = 0; i < 300 && g_pool_hits < 1; i++) Sleep(2);
    CloseThreadpoolWork(w);
    Sleep(20);
    return (g_pool_hits == 1 && g_pool_arg3 == (uintptr_t)w) ? 1 : 0;
}
#endif
EMSCRIPTEN_KEEPALIVE int g_fls(void) {
    DWORD fls = FlsAlloc((PFLS_CALLBACK_FUNCTION)(uintptr_t)VA_FLS);
    if (fls == FLS_OUT_OF_INDEXES) return -1;
    FlsSetValue(fls, (void*)0x51AB);
    FlsFree(fls);
    return (g_fls_hits == 1 && g_fls_last == 0x51ab) ? 1 : 0;
}
/* 実 C 関数ポインタ (wasm テーブル index) は恒等経路で従来どおり動く (= M4 互換) */
static BOOL c_loc_proc(LPWSTR s) { (void)s; return TRUE; }
EMSCRIPTEN_KEEPALIVE int g_identity(void) {
    return EnumSystemLocalesW(c_loc_proc, 0) ? 1 : 0;
}
/* BLK route (__icall_dispatch 形) への差し替え: 同一フックで icall route が動く */
EMSCRIPTEN_KEEPALIVE int g_route_switch(void) {
    shimx_cbtrans_set_invoke(ic_invoke_blk);
    EnumSystemLocalesW((LOCALE_ENUMPROCW)(uintptr_t)VA_ENUMLOC2, 0);
    shimx_cbtrans_set_invoke(ic_invoke_m11);       /* 元に戻す */
    return g_blk_hits;
}
/* R3: GetProcAddress → トークン → lift dispatch → 実体 (ILGetSize / ILIsEqual / GetThreadUILanguage) */
EMSCRIPTEN_KEEPALIVE int g_r3_roundtrip(void) {
    HMODULE sh = GetModuleHandleA("shell32.dll");
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    if (!sh || !k32) return -1;
    void* tok_size = GetProcAddress(sh, (LPCSTR)(uintptr_t)152);
    void* tok_eq = GetProcAddress(sh, (LPCSTR)(uintptr_t)21);
    void* tok_lang = GetProcAddress(k32, "GetThreadUILanguage");
    if (!tok_size || !tok_eq || !tok_lang) return -2;
    if ((uintptr_t)tok_size < 0x7F000000u) return -3;   /* トークン化されていない (= resolver 未接続) */
    static const uint8_t pidl[] = { 12, 0, 'C', 0, ':', 0, '\\', 0, 'x', 0, 0, 0, 0, 0 };
    if (lift_dispatch((u64x)(uintptr_t)tok_size, (uintptr_t)pidl, 0,0,0,0,0,0,0) != 14) return -4;
    if (lift_dispatch((u64x)(uintptr_t)tok_eq, (uintptr_t)pidl, (uintptr_t)pidl, 0,0,0,0,0,0) != 1) return -5;
    if (lift_dispatch((u64x)(uintptr_t)tok_lang, 0,0,0,0,0,0,0,0) != 0x409) return -6;
    return 7;                                      /* 3 往復すべて一致 */
}
static int g_out[8];
EMSCRIPTEN_KEEPALIVE void* g_stats_buf(void) { return g_out; }
EMSCRIPTEN_KEEPALIVE void g_stats(int* out) {
    out[0] = shimx_cbtrans_slots();
    out[1] = shimx_cbtrans_calls();
    out[2] = g_invoke_ok;
    out[3] = g_invoke_miss;
    out[4] = shimx_lifttab_count();
}
