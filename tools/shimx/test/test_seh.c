/* shimx 単体テスト (seh): setjmp 系 SEH 実巻き戻し (#171)。scope table は Delphi x64 inline 形式。 */
#include "test_common.h"

static int g_pad_log[16];
static uint64_t g_pad_frame[16];
static DWORD g_pad_flags[16];
static int g_pad_n;

static uint64_t pad_a(uint64_t ep, uint64_t frame) {
    EXCEPTION_RECORD64* r = (EXCEPTION_RECORD64*)(uintptr_t)((EXCEPTION_POINTERS64*)(uintptr_t)ep)->ExceptionRecord;
    g_pad_log[g_pad_n] = 'a'; g_pad_frame[g_pad_n] = frame; g_pad_flags[g_pad_n] = r->ExceptionFlags; g_pad_n++;
    return 0;
}
static uint64_t pad_b(uint64_t ep, uint64_t frame) {
    EXCEPTION_RECORD64* r = (EXCEPTION_RECORD64*)(uintptr_t)((EXCEPTION_POINTERS64*)(uintptr_t)ep)->ExceptionRecord;
    g_pad_log[g_pad_n] = 'b'; g_pad_frame[g_pad_n] = frame; g_pad_flags[g_pad_n] = r->ExceptionFlags; g_pad_n++;
    return 0;
}
static shimx_seh_pad_fn resolver(uint32_t rva) { return rva == 0x900 ? pad_a : rva == 0xA00 ? pad_b : NULL; }
static int typed_matcher(const EXCEPTION_RECORD64* rec, uint32_t desc, uint32_t* h) {
    if (desc == 0x5000 && rec->ExceptionCode == 0x0EEDFADEu) { *h = 0x777; return 1; }
    return 0;
}

/* scope table: count + entries */
static const uint32_t scopes_catchall[] = { 1, 0x100, 0x200, 2, 0x200 };
static const uint32_t scopes_pad[]      = { 2, 0x300, 0x400, 2, 0x400,   0x400, 0x480, 0, 0x900 };
static const uint32_t scopes_pad_b[]    = { 1, 0x500, 0x600, 0, 0xA00 };
static const uint32_t scopes_typed[]    = { 1, 0x100, 0x200, 0x5000, 0 };

static void t_catchall(void) {
    ShxSehFrame f; memset(&f, 0, sizeof f);
    f.frame = 0x1000; f.scopes = scopes_catchall;
    shimx_seh_enter(&f);
    CHECK(shimx_seh_depth() == 1);
    volatile int caught = 0;
    if (setjmp(f.jb) == 0) {
        f.pc = 0x150;
        RaiseException(0xE06D7363u, EXCEPTION_NONCONTINUABLE, 0, NULL);
        CHECK(0 && "RaiseException が戻った");
    } else {
        caught = 1;
    }
    CHECK(caught && f.resume_ip == 0x200);
    CHECK(shimx_seh_current_exception() && shimx_seh_current_exception()->ExceptionCode == 0xE06D7363u);
    shimx_seh_leave(&f);
    CHECK(shimx_seh_depth() == 0);
}

/* 内側 frame (pad あり) → 外側 frame (catch-all): pad が内側から順に 1 回ずつ、frame 引数と UNWINDING フラグ付きで走る */
static void t_nested_pads(void) {
    ShxSehFrame outer, mid, inner;
    memset(&outer, 0, sizeof outer); memset(&mid, 0, sizeof mid); memset(&inner, 0, sizeof inner);
    outer.frame = 0x2000; outer.scopes = scopes_pad;        /* try 本体 [0x300,0x400) catch-all */
    mid.frame = 0x3000;   mid.scopes = scopes_pad_b;        /* [0x500,0x600) に pad b (kind 0) */
    inner.frame = 0x4000; inner.scopes = scopes_pad;        /* handler 領域 [0x400,0x480) に pad a (kind 0) */
    g_pad_n = 0;
    shimx_seh_set_pad_resolver(resolver);
    shimx_seh_enter(&outer); shimx_seh_enter(&mid); shimx_seh_enter(&inner);
    CHECK(shimx_seh_depth() == 3);
    outer.pc = 0x350;                                       /* 外側は try 本体内 → 捕捉 */
    mid.pc = 0x550;
    inner.pc = 0x420;
    volatile int landed = 0;
    if (setjmp(outer.jb) == 0) {
        RaiseException(0xE0000002u, EXCEPTION_NONCONTINUABLE, 0, NULL);
        CHECK(0 && "RaiseException が戻った");
    } else {
        landed = 1;
    }
    /* 検索相は内側から: inner は pc=0x420 が catch-all [0x300,0x400) 外 → 非該当、mid は scope kind 0 のみ → 非該当、outer が捕捉 */
    CHECK(landed && outer.resume_ip == 0x400);
    CHECK(g_pad_n == 2);
    CHECK(g_pad_log[0] == 'a' && g_pad_frame[0] == 0x4000);   /* inner 先 */
    CHECK(g_pad_log[1] == 'b' && g_pad_frame[1] == 0x3000);
    CHECK((g_pad_flags[0] & 2u) && (g_pad_flags[1] & 2u));    /* EXCEPTION_UNWINDING */
    CHECK(shimx_seh_depth() == 1);                            /* 捕捉 frame (outer) だけ残る */
    shimx_seh_leave(&outer);
    CHECK(shimx_seh_depth() == 0);
    shimx_seh_set_pad_resolver(NULL);
}

static void t_typed(void) {
    ShxSehFrame f; memset(&f, 0, sizeof f);
    f.frame = 0x5000; f.scopes = scopes_typed; f.pc = 0x150;
    shimx_seh_enter(&f);
    shimx_seh_set_typed_matcher(typed_matcher);
    volatile int landed = 0;
    if (setjmp(f.jb) == 0) {
        uint64_t a[1] = { 0x1234 };
        RaiseException(0x0EEDFADEu, EXCEPTION_NONCONTINUABLE, 1, a);
        CHECK(0 && "RaiseException が戻った");
    } else landed = 1;
    CHECK(landed && f.resume_ip == 0x777);
    CHECK(shimx_seh_current_exception()->NumberParameters == 1 && shimx_seh_current_exception()->ExceptionInformation[0] == 0x1234);
    shimx_seh_leave(&f);
    shimx_seh_set_typed_matcher(NULL);
}

/* RtlUnwindEx: targetFrame まで巻き戻して targetIp / retval 付きで復帰。targetFrame==NULL は全 pad 実行のみで戻る */
static void t_rtlunwind(void) {
    ShxSehFrame outer, inner;
    memset(&outer, 0, sizeof outer); memset(&inner, 0, sizeof inner);
    outer.frame = 0x6000; outer.scopes = NULL;
    inner.frame = 0x7000; inner.scopes = scopes_pad_b; inner.pc = 0x550;
    g_pad_n = 0;
    shimx_seh_set_pad_resolver(resolver);
    shimx_seh_enter(&outer); shimx_seh_enter(&inner);
    volatile int landed = 0;
    if (setjmp(outer.jb) == 0) {
        RtlUnwindEx((PVOID)0x6000, (PVOID)0x1234, NULL, (PVOID)0x99, NULL, NULL);
        CHECK(0 && "RtlUnwindEx が戻った");
    } else landed = 1;
    CHECK(landed && outer.resume_ip == 0x1234 && outer.resume_ret == 0x99);
    CHECK(g_pad_n == 1 && g_pad_log[0] == 'b' && g_pad_frame[0] == 0x7000);
    CHECK(shimx_seh_depth() == 1);

    g_pad_n = 0;
    shimx_seh_enter(&inner);                                  /* 再び inner を積み、exit unwind (targetFrame=NULL) */
    RtlUnwind(NULL, NULL, NULL, NULL);
    CHECK(g_pad_n == 1 && shimx_seh_depth() == 0);
    shimx_seh_set_pad_resolver(NULL);
}

/* 別スレッドの frame 鎖は独立 (thread-local) */
static void t_isolation(void) {
    ShxSehFrame f; memset(&f, 0, sizeof f);
    shimx_seh_enter(&f);
    CHECK(shimx_seh_depth() == 1);
    shimx_seh_leave(&f);
    shimx_seh_leave(&f);                                      /* 未登録の leave は無害 */
    CHECK(shimx_seh_depth() == 0);
}

void run_seh_tests(void) {
    CHECK(shimx_seh_depth() == 0 && shimx_seh_current_exception() == NULL);
    t_catchall();
    t_nested_pads();
    t_typed();
    t_rtlunwind();
    t_isolation();
}

/* fail-fast モード: frame はあるが pc が scope 外 / 一致 frame 無し */
void seh_failfast_nomatch(void) {
    static const uint32_t sc[] = { 1, 0x100, 0x200, 2, 0x200 };
    static ShxSehFrame f;
    f.frame = 1; f.scopes = sc; f.pc = 0x999;
    shimx_seh_enter(&f);
    RaiseException(0xE0000003u, EXCEPTION_NONCONTINUABLE, 0, NULL);
}
void seh_failfast_badtarget(void) {
    static ShxSehFrame f;
    f.frame = 1;
    shimx_seh_enter(&f);
    RtlUnwindEx((PVOID)0xBAD, NULL, NULL, NULL, NULL, NULL);
}
