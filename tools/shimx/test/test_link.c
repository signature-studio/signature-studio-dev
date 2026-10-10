/* shimx 単体テスト (link feedback): M11 shimx_link REPORT §6 の要求 R1〜R8 対応分 (CAB-211)。
 *   R1 intptr 閾値 / R2 コールバック変換フック / R3 GetProcAddress 組込み表追加 (kernel32 UI言語・shell32 序数)
 *   R4 擬似ロード / R5 SysFreeString 管理外ポインタ / R7 EnterCriticalSection(NULL) 方針
 * (R6 は scripts/ir_undef.py の test.sh 組込み検査、R8 は scripts/rem11_check.sh で検証)
 */
#include "test_common.h"

/* ---------------------------------------------------------------
 * R1: 「値 < 0x10000 は序数/整数」判定の閾値
 * --------------------------------------------------------------- */
static void test_r1_intptr_limit(void) {
    CHECK(shimx_get_intptr_limit() == 0x10000);                      /* 既定 */
    /* 序数 GetProcAddress (既定閾値): shell32 #16 = ILFindLastID (R3 の序数表) */
    HMODULE sh = GetModuleHandleW(W("shell32.dll"));
    CHECK(sh);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)16) == (void*)ILFindLastID);

    /* 閾値を下げる: 序数 16 は文字列ポインタ扱い → miss (LVA=0 敷設の lift IR 相当) */
    shimx_set_intptr_limit(4);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)16) == NULL && GetLastError() == ERROR_PROC_NOT_FOUND);
    /* 閾値 0x20000: 実アドレスの名前文字列も「整数」扱いにはならない (ヒープ/静的は > 0x20000)。
     * 序数扱いの上限が広がることだけ確認 (16 は序数) */
    shimx_set_intptr_limit(0x20000);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)16) == (void*)ILFindLastID);
    /* CharUpper/Atom の単一文字・MAKEINTATOM も同一閾値に従う */
    CHECK((uintptr_t)CharLowerW((LPWSTR)(uintptr_t)'Q') == 'q');
    shimx_set_intptr_limit(4);
    LPWSTR str = (LPWSTR)W("abc");                                   /* ヒープ/静的アドレスは文字列扱いに戻る */
    CHECK(CharLowerW(str) == str && wstr_eq(str, "abc"));
    shimx_set_intptr_limit(0x10000);                                 /* 復元 */
    CHECK(shimx_get_intptr_limit() == 0x10000);
}

/* ---------------------------------------------------------------
 * R2: コールバック変換フック
 * --------------------------------------------------------------- */
static int g_trans_calls;
static void* g_trans_last_api_cb;
static BOOL g_spy_locales_hit;
static BOOL g_spy_cal_hit;
static DWORD g_spy_thread_rc;
static int g_spy_thread_ran;
static int g_spy_fls_ran;
static void* g_fls_marker = (void*)0x51AB;

static void* my_translator(const char* api, void* cb) {
    g_trans_calls++;
    g_trans_last_api_cb = cb;
    return cb;                                                       /* 恒等 (フック経由であることだけ検証) */
}
static BOOL spy_locales(LPWSTR s) { (void)s; g_spy_locales_hit = 1; return TRUE; }
static BOOL spy_cal(LPWSTR s) { (void)s; g_spy_cal_hit = 1; return TRUE; }
static DWORD spy_thread(LPVOID p) { (void)p; g_spy_thread_ran = 1; g_spy_thread_rc = 42; return 42; }
static void spy_fls(LPVOID v) { (void)v; g_spy_fls_ran = 1; }

static void test_r2_callback_translator(void) {
    CHECK(EnumSystemLocalesW(spy_locales, 0) && g_spy_locales_hit);

    shimx_set_callback_translator(my_translator);
    g_trans_calls = 0; g_spy_cal_hit = 0;
    CHECK(EnumCalendarInfoW(spy_cal, 0x0409, 1, 5) && g_spy_cal_hit);
    CHECK(g_trans_calls == 1 && g_trans_last_api_cb == (void*)spy_cal);   /* Enum* がフック経由 */

    g_trans_calls = 0;
    DWORD fls = FlsAlloc(spy_fls);
    CHECK(fls != FLS_OUT_OF_INDEXES && g_trans_calls == 1);               /* FlsAlloc もフック経由 */
    CHECK(FlsSetValue(fls, g_fls_marker) && FlsFree(fls) && g_spy_fls_ran);

    /* CreateThread (MT のみ): start ルーチンがフック経由で実スレッド起動される */
#if defined(__EMSCRIPTEN_PTHREADS__)
    g_trans_calls = 0; g_spy_thread_ran = 0;
    HANDLE h = CreateThread(NULL, 0, spy_thread, NULL, 0, NULL);
    CHECK(h);
    CHECK(g_trans_calls == 1);
    DWORD ec = STILL_ACTIVE;
    for (int i = 0; i < 500 && ec == STILL_ACTIVE; i++) { Sleep(2); CHECK(GetExitCodeThread(h, &ec)); }   /* 完了待ち (最大1秒) */
    if (ec != 42 || !g_spy_thread_ran) fprintf(stderr, "[shimx-test][dbg] thread ec=%u ran=%d trans=%d\n", ec, g_spy_thread_ran, g_trans_calls);
    CHECK(ec == 42 && g_spy_thread_ran);
    CloseHandle(h);
#endif
    shimx_set_callback_translator(NULL);
    CHECK(EnumSystemLocalesW(spy_locales, 0));                            /* 解除後はフック無しに戻る */
}

/* ---------------------------------------------------------------
 * R3: GetProcAddress 組込み表追加 (kernel32 UI言語 3 本 / shell32 序数)
 * --------------------------------------------------------------- */
static void test_r3_proctable(void) {
    HMODULE k32 = GetModuleHandleW(W("kernel32.dll"));
    HMODULE sh = GetModuleHandleW(W("shell32.dll"));
    CHECK(k32 && sh);
    void* f = GetProcAddress(k32, "GetThreadPreferredUILanguages");
    CHECK(f == (void*)GetThreadPreferredUILanguages);
    CHECK(GetProcAddress(k32, "SetThreadPreferredUILanguages") == (void*)SetThreadPreferredUILanguages);
    CHECK(GetProcAddress(k32, "GetThreadUILanguage") == (void*)GetThreadUILanguage);

    /* 実働: MUI 言語 (en-US 固定, multi-sz) */
    ULONG num = 0, cch = 0;
    CHECK(GetThreadPreferredUILanguages(0, &num, NULL, &cch) && num == 1 && cch == 7);   /* "en-US\0\0" */
    WCHAR buf[16];
    cch = sizeof buf / 2;
    CHECK(GetThreadPreferredUILanguages(0, &num, buf, &cch) && wstr_eq(buf, "en-US") && buf[6] == 0 && buf[7] == 0);
    CHECK(GetThreadUILanguage() == 0x0409);
    CHECK(SetThreadPreferredUILanguages(0, W("ja-JP"), &num) && num == 1);
    cch = sizeof buf / 2;
    CHECK(GetThreadPreferredUILanguages(0, &num, buf, &cch) && wstr_eq(buf, "ja-JP"));
    CHECK(SetThreadPreferredUILanguages(0, NULL, &num));                  /* NULL = 既定に戻す */
    cch = sizeof buf / 2;
    CHECK(GetThreadPreferredUILanguages(0, &num, buf, &cch) && wstr_eq(buf, "en-US"));

    /* shell32 序数表 (Windows 10/11 のエクスポート序数): R3 の 9 本 + 既知 190 */
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)16) == (void*)ILFindLastID);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)17) == (void*)ILRemoveLastID);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)18) == (void*)ILClone);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)19) == (void*)ILCloneFirst);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)21) == (void*)ILIsEqual);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)25) == (void*)ILCombine);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)152) == (void*)ILGetSize);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)153) == (void*)ILGetNext);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)155) == (void*)ILFree);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)190) == (void*)ILCreateFromPathW);
    CHECK(GetProcAddress(sh, (LPCSTR)(uintptr_t)74) == NULL);             /* SHCreateStdEnumFmtEtc は未実装のまま */
    CHECK(GetLastError() == ERROR_PROC_NOT_FOUND);

    /* IL* 実働 (shimx 自前 PIDL 形式) */
    LPVOID pidl = ILCreateFromPathW(W("C:\\Program Files\\FL"));
    CHECK(pidl && ILGetSize(pidl) == 2 + (lstrlenW(W("C:\\Program Files\\FL")) + 1) * 2 + 2);
    LPVOID cl = ILClone(pidl);
    CHECK(cl && ILIsEqual(cl, pidl) && !ILIsEqual(cl, NULL));
    CHECK(ILGetNext(pidl) == NULL);                                       /* 単項リスト */
    CHECK(ILFindLastID(pidl) == pidl);
    LPVOID head = ILCloneFirst(pidl);
    CHECK(head && ILIsEqual(head, pidl));
    LPVOID comb = ILCombine(pidl, head);
    CHECK(comb && ILGetSize(comb) == ILGetSize(pidl) + ILGetSize(head) - 2);
    CHECK(ILGetNext(comb) != NULL);                                       /* 2 項目化 */
    CHECK(ILFindLastID(comb) == (LPVOID)((uint8_t*)comb + ILGetSize(pidl) - 2));
    BOOL rem = ILRemoveLastID(comb);                                      /* 最終項目除去 → 単項化 */
    CHECK(rem && ILIsEqual(comb, pidl));
    CHECK(ILRemoveLastID(comb));                                          /* → 空 */
    CHECK(ILGetSize(comb) == 2 && ILRemoveLastID(comb) == FALSE);
    ILFree(comb); ILFree(head); ILFree(cl); ILFree(pidl);
    ILFree(NULL);
}

/* ---------------------------------------------------------------
 * R4: LoadLibrary 失敗方針 (擬似ロード)
 * --------------------------------------------------------------- */
static void test_r4_pseudo_load(void) {
    /* 既定: 失敗 (M11 survey 実測の Msctf.dll / avrt / PowrProf.dll は組込み表に無い) */
    CHECK(LoadLibraryW(W("Msctf.dll")) == 0 && GetLastError() == ERROR_MOD_NOT_FOUND);
    CHECK(LoadLibraryW(W("avrt")) == 0);
    shimx_set_pseudo_load(1);
    HMODULE m1 = LoadLibraryW(W("Msctf.dll"));
    CHECK(m1 && GetModuleHandleW(W("msctf")) == m1);                      /* 擬似モジュールとして登録 */
    WCHAR path[300];
    CHECK(GetModuleFileNameW(m1, path, 300) > 0 && wstr_eq(path, "Msctf.dll"));
    HMODULE a1 = LoadLibraryW(W("avrt"));
    HMODULE p1 = LoadLibraryW(W("PowrProf.dll"));
    CHECK(a1 && p1);
    HMODULE m2 = LoadLibraryW(W("Msctf.dll"));                            /* 2 度目は同一ハンドル */
    CHECK(m2 == m1);
    CHECK(FreeLibrary(m2) && FreeLibrary(m1) && FreeLibrary(a1) && FreeLibrary(p1));
    shimx_set_pseudo_load(0);
    CHECK(LoadLibraryW(W("avrt")) == a1);                                 /* 登録済み擬似モジュールは cache として残る */
    CHECK(FreeLibrary(a1));
    CHECK(LoadLibraryW(W("XyzTestFake.dll")) == 0 && GetLastError() == ERROR_MOD_NOT_FOUND);   /* 既定に戻る (未知は失敗) */
}

/* ---------------------------------------------------------------
 * R5: SysFreeString 管理外ポインタ
 * --------------------------------------------------------------- */
static void test_r5_sysfreestring(void) {
    BSTR b = SysAllocString(W("own"));                                    /* 所有済み → 従来どおり解放 */
    CHECK(SysStringLen(b) == 3);
    SysFreeString(b);

    /* 管理外ポインタ (スタック番地) は strict=0 で無視 (旧実装は free して abort していた) */
    uint64_t dummy[4] = { 1, 2, 3, 4 };
    BSTR foreign = (BSTR)&dummy[1];
    SysFreeString(foreign);                                               /* 無視されて戻る */
    CHECK(dummy[0] == 1 && dummy[3] == 4);                                /* 内容は無傷 */

    /* 二重 free も同一経路で無害化 */
    BSTR b2 = SysAllocStringByteLen("xy", 2);
    SysFreeString(b2);
    SysFreeString(b2);                                                    /* 所有表に無い → 無視 */
    /* 管理外で GetLastError を壊さない */
    SetLastError(ERROR_SUCCESS);
    SysFreeString(foreign);
    CHECK(GetLastError() == ERROR_SUCCESS);
}

/* ---------------------------------------------------------------
 * R7: EnterCriticalSection(NULL) 方針
 * --------------------------------------------------------------- */
static void test_r7_cs_null(void) {
    /* 既定: fail-fast (= Win32 の AV 相当) は fail-fast モードで別途確認 (test_main.c の csnull) */
    shimx_set_cs_null_ok(1);                                              /* 許可モード: no-op */
    EnterCriticalSection(NULL);
    EnterCriticalSection((PCRITICAL_SECTION)(uintptr_t)6);                /* 非整列 */
    CHECK(TryEnterCriticalSection(NULL) == FALSE);
    LeaveCriticalSection(NULL);
    DWORD sp = SetCriticalSectionSpinCount(NULL, 7);
    CHECK(sp == 0);
    InitializeCriticalSection(NULL);                                      /* 何もしない */
    uint8_t csbuf[64];
    PCRITICAL_SECTION cs = (PCRITICAL_SECTION)csbuf;
    InitializeCriticalSection(cs);
    EnterCriticalSection(cs);
    CHECK(TryEnterCriticalSection(cs));                                   /* 再帰 */
    LeaveCriticalSection(cs);
    LeaveCriticalSection(cs);
    DeleteCriticalSection(cs);
    shimx_set_cs_null_ok(0);
}

void run_link_tests(int multithread) {
    (void)multithread;
    test_r1_intptr_limit();
    test_r2_callback_translator();
    test_r3_proctable();
    test_r4_pseudo_load();
    test_r5_sysfreestring();
    test_r7_cs_null();
}
