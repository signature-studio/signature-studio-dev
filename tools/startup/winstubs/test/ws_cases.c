/* winstubs 単体テスト: 各 API の戻り値を "id<TAB>actual" で標準出力に出す。
 * 期待値は data/retval_table.tsv。run_tests.mjs が全行を突合する (行の過不足も失敗)。
 *   通常ビルド   : winstubs 層 (init + --wrap) あり
 *   -DWS_BASELINE: shimx 単体 (shimx_set_trust_ok(1) のみ)。winstubs 固有 API のケースは除外 → 差分表の根拠
 *   引数 exit    : TerminateProcess(自プロセス) → exit フック + 終了コード
 */
#include "../src/winstubs.h"
#include <strings.h>

#ifdef WS_BASELINE
#define NEWAPI(...)
#else
#define NEWAPI(...) __VA_ARGS__
#endif

/* winstubs 層が公開しないが shimx 側に無い API (user32 / uxtheme / ntdll) の prototype */
#ifndef WS_BASELINE
HWND   FindWindowW(LPCWSTR, LPCWSTR);
HWND   FindWindowExW(HWND, HWND, LPCWSTR, LPCWSTR);
HRESULT BufferedPaintInit(void);
HRESULT BufferedPaintUnInit(void);
HANDLE LoadIconW(HANDLE, LPCWSTR);
int    GetSystemMetrics(int);
BOOL   SystemParametersInfoW(UINT, UINT, PVOID, UINT);
LONG   RtlGetVersion(void*);
BOOL   PeekMessageW(LPVOID, HWND, UINT, UINT, UINT);
LONG   GetMessageW(LPVOID, HWND, UINT, UINT);
BOOL   TranslateMessage(const void*);
LONG   DispatchMessageW(const void*);
BOOL   PostMessageW(HWND, UINT, UINT_PTR_T, LPARAM_T);
LRESULT_T SendMessageW(HWND, UINT, UINT_PTR_T, LPARAM_T);
void   PostQuitMessage(int);
UINT_PTR_T SetTimer(HWND, UINT_PTR_T, UINT, LPVOID);
BOOL   KillTimer(HWND, UINT_PTR_T);
BOOL   WaitMessage(void);
#endif

/* ---------- ユーティリティ ---------- */
static WCHAR* W(const char* s) {
    static WCHAR buf[8][640]; static int k;
    WCHAR* b = buf[k++ & 7]; int i = 0;
    for (; s[i] && i < 639; i++) b[i] = (WCHAR)(unsigned char)s[i];
    b[i] = 0; return b;
}
static const char* U(const WCHAR* w) {
    static char buf[8][640]; static int k;
    char* b = buf[k++ & 7]; int i = 0;
    for (; w[i] && i < 639; i++) b[i] = (char)w[i];
    b[i] = 0; return b;
}
static void emit(const char* id, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
#include <stdarg.h>
static void emit(const char* id, const char* fmt, ...) {
    char b[512]; va_list ap; va_start(ap, fmt); vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
    printf("%s\t%s\n", id, b);
}
#define EC(id, ...) emit(id, __VA_ARGS__)
static HMODULE g_eng;
static int g_exit_hook_called;
static HMODULE any_load_hook(const char* name, DWORD fl) { (void)name; (void)fl; return (HMODULE)0x5000; }   /* hostbridge が何でも解決する状況を模擬 */
static void on_exit_hook(UINT code) { fprintf(stderr, "exit hook code=%u\n", code); g_exit_hook_called = 1; }

static void shell_w(const char* id, const char* verb, const char* file, const char* params) {
    SetLastError(0);
    HINSTANCE r = ShellExecuteW(0, verb ? W(verb) : NULL, W(file), params ? W(params) : NULL, NULL, 1);
    EC(id, "ret=%u", (unsigned)(uintptr_t)r);
}
static void shell_ex(const char* id, int wide, const char* verb, const char* file, const char* params) {
    uint8_t info[112]; memset(info, 0, sizeof info);
    *(uint32_t*)info = 112;
    if (wide) {
        *(uint64_t*)(info + 16) = verb ? (uintptr_t)W(verb) : 0;
        *(uint64_t*)(info + 24) = (uintptr_t)W(file);
        *(uint64_t*)(info + 32) = params ? (uintptr_t)W(params) : 0;
    } else {
        *(uint64_t*)(info + 16) = (uintptr_t)verb; *(uint64_t*)(info + 24) = (uintptr_t)file; *(uint64_t*)(info + 32) = (uintptr_t)params;
    }
    SetLastError(0);
    BOOL r = wide ? ShellExecuteExW(info) : ShellExecuteExA(info);
    EC(id, "ret=%d hInst=%u err=%u", r, (unsigned)*(uint64_t*)(info + 56), GetLastError());
}

/* ---------- G03: 署名ゲート ---------- */
static void t_g03(void) {
    uint8_t wtd[128]; memset(wtd, 0, sizeof wtd);
    GUID act; memset(&act, 0, sizeof act);
    *(uint32_t*)(wtd + 8) = 1;        /* dwUIChoice = WTD_UI_NONE ... (値は shim が見ない) */
    EC("G03.01", "ret=%d", (int)WinVerifyTrust(0, &act, wtd));         /* WTD_STATEACTION_VERIFY */
    EC("G03.02", "ret=%d", (int)WinVerifyTrust(0, &act, wtd));         /* WTD_STATEACTION_CLOSE */

    DWORD enc = 0, ct = 0, ft = 0; void *hs = 0, *hm = 0;
    BOOL q = CryptQueryObject(1, W("C:\\Program Files\\Image-Line\\FL Studio 2026\\FLEngine_x64.dll"), 0x400, 2, 0, &enc, &ct, &ft, &hs, &hm, NULL);
    EC("G03.03", "ret=%d enc=0x%x ct=%u ft=%u store=%d msg=%d", q, enc, ct, ft, hs != 0, hm != 0);
    EC("G03.04", "ret=%d", CryptQueryObject(1, W("x.dll"), 0x2, 2, 0, &enc, &ct, &ft, &hs, &hm, NULL));   /* PKCS7_SIGNED_EMBED を期待しない呼出 */

    DWORD len = 0;
    BOOL r1 = CryptMsgGetParam(hm, 6, 0, NULL, &len);
    EC("G03.05", "ret=%d len=%u", r1, len);
    void* sb = LocalAlloc(0x40 /* LPTR */, len);
    BOOL r2 = CryptMsgGetParam(hm, 6, 0, sb, &len);
    int zero = 1; for (DWORD i = 0; i < len; i++) if (((uint8_t*)sb)[i]) zero = 0;
    EC("G03.06", "ret=%d len=%u zero=%d", r2, len, zero);
    LocalFree(sb);
    DWORD small = 0x40; uint8_t tiny[0x40]; SetLastError(0);
    BOOL r3 = CryptMsgGetParam(hm, 6, 0, tiny, &small);
    EC("G03.07", "ret=%d need=%u err=%u", r3, small, GetLastError());
    DWORD cnt = 0, cl = 4; BOOL r4 = CryptMsgGetParam(hm, 5, 0, &cnt, &cl);
    EC("G03.08", "ret=%d count=%u", r4, cnt);

    uint8_t info[0x80]; memset(info, 0, sizeof info);
    void* ctx = CertFindCertificateInStore(hs, 0x10001, 0, 0xb0000, info, NULL);
    EC("G03.09", "nonnull=%d", ctx != 0);
    SetLastError(0);
    void* c2 = CertFindCertificateInStore(hs, 0x10001, 0, 0xb0000, info, ctx);
    EC("G03.10", "null=%d err=0x%x", c2 == 0, GetLastError());

    DWORD n1 = CertGetNameStringW(ctx, 4, 0, NULL, NULL, 0);
    WCHAR nb[128]; DWORD n2 = CertGetNameStringW(ctx, 4, 0, NULL, nb, 128);
    EC("G03.11", "len=%u", n1);
    EC("G03.12", "ret=%u name=%s", n2, U(nb));
    EC("G03.13", "eq=%d", strcmp(U(nb), "Image Line NV") == 0);
    WCHAR s5[5]; DWORD n5 = CertGetNameStringW(ctx, 4, 0, NULL, s5, 5);
    EC("G03.14", "ret=%u name=%s", n5, U(s5));
    char ab[32]; DWORD na = CertGetNameStringA(ctx, 4, 0, NULL, ab, 32);
    EC("G03.15", "ret=%u name=%s", na, ab);
    DWORD ni = CertGetNameStringW(ctx, 4, 1 /* ISSUER */, NULL, nb, 128);
    EC("G03.16", "ret=%u issuer_len=%d", ni, (int)strlen(U(nb)));
    EC("G03.17", "ret=%d", CertFreeCertificateContext(ctx));
    EC("G03.18", "ret=%d", CertCloseStore(hs, 0));
    EC("G03.19", "ret=%d", CryptMsgClose(hm));
}

/* ---------- G05: cpuid ---------- */
NEWAPI(
static void t_g05(void) {
    uint32_t r[4];
    char v[13];
    winstubs_cpuid(0, 0, r);
    memcpy(v, &r[1], 4); memcpy(v + 4, &r[3], 4); memcpy(v + 8, &r[2], 4); v[12] = 0;
    EC("G05.01", "vendor=%s max=0x%x", v, r[0]);
    winstubs_cpuid(1, 0, r);
    EC("G05.02", "cmov=%d fxsr=%d mmx=%d sse=%d sse2=%d tsc=%d sse3=%d sse41=%d popcnt=%d avx=%d",
       (r[3] >> 15) & 1, (r[3] >> 24) & 1, (r[3] >> 23) & 1, (r[3] >> 25) & 1, (r[3] >> 26) & 1, (r[3] >> 4) & 1,
       r[2] & 1, (r[2] >> 19) & 1, (r[2] >> 23) & 1, (r[2] >> 28) & 1);
    winstubs_cpuid(7, 0, r);
    EC("G05.04", "ebx=0x%x ecx=0x%x edx=0x%x avx2=%d", r[1], r[2], r[3], (r[1] >> 5) & 1);
    winstubs_cpuid(0x80000001u, 0, r);
    EC("G05.05", "lm=%d lahf=%d", (r[3] >> 29) & 1, r[2] & 1);
    winstubs_cpuid(0x80000002u, 0, r);
    EC("G05.06", "brand0=%c%c%c%c", r[0] & 0xff, (r[0] >> 8) & 0xff, (r[0] >> 16) & 0xff, (r[0] >> 24) & 0xff);
    WsConfig c; winstubs_defaults(&c); c.cpu_profile = WS_CPU_PLAN; winstubs_init(&c);
    winstubs_cpuid(0, 0, r);
    EC("G05.07", "plan_max=0x%x", r[0]);
    winstubs_cpuid(1, 0, r);
    EC("G05.08", "plan_ecx=0x%08x sse3=%d ssse3=%d sse41=%d sse42=%d popcnt=%d avx=%d", r[2], r[2] & 1, (r[2] >> 9) & 1, (r[2] >> 19) & 1,
       (r[2] >> 20) & 1, (r[2] >> 23) & 1, (r[2] >> 28) & 1);
    winstubs_cpuid(7, 0, r);
    EC("G05.09", "plan_avx2=%d", (r[1] >> 5) & 1);
    winstubs_defaults(&c); winstubs_init(&c);
}
)

/* ---------- G06: FindWindow ---------- */
NEWAPI(
static void t_g06(void) {
    SetLastError(0);
    HWND h = FindWindowW(W("TFruityLoopsMainForm"), NULL);
    EC("G06.01", "null=%d", h == 0);
    EC("G06.02", "null=%d", FindWindowExW(0, 0, W("TFruityLoopsMainForm"), NULL) == 0);
    EC("G06.03", "null=%d", FindWindowW(NULL, W("FL Studio 2026")) == 0);
}
)

/* ---------- G16 / G04(識別値): OS バージョン・マシン識別 ---------- */
static void t_g16(void) {
    OSVERSIONINFOEXW v; memset(&v, 0, sizeof v); v.dwOSVersionInfoSize = 284;
    BOOL r = GetVersionExW(&v);
    EC("G16.01", "ret=%d ver=%u.%u.%u plat=%u", r, v.dwMajorVersion, v.dwMinorVersion, v.dwBuildNumber, v.dwPlatformId);
    memset(&v, 0, sizeof v); v.dwOSVersionInfoSize = 276;
    EC("G16.02", "ret=%d ver=%u.%u.%u", GetVersionExW(&v), v.dwMajorVersion, v.dwMinorVersion, v.dwBuildNumber);
    memset(&v, 0, sizeof v); v.dwOSVersionInfoSize = 100; SetLastError(0);
    EC("G16.03", "ret=%d err=%u", GetVersionExW(&v), GetLastError());
    EC("G16.04", "ver=0x%08x", GetVersion());
    NEWAPI(
        memset(&v, 0, sizeof v); v.dwOSVersionInfoSize = 284;
        LONG st = RtlGetVersion(&v);
        EC("G16.05", "status=0x%x ver=%u.%u.%u plat=%u", (unsigned)st, v.dwMajorVersion, v.dwMinorVersion, v.dwBuildNumber, v.dwPlatformId);
        memset(&v, 0, sizeof v); v.dwOSVersionInfoSize = 7;
        EC("G16.06", "status=0x%x", (unsigned)RtlGetVersion(&v));
        HMODULE nt = GetModuleHandleW(W("ntdll.dll"));
        EC("G16.07", "gpa=%d", GetProcAddress(nt, "RtlGetVersion") != NULL);
    )
    /* レジストリ側 (shimx の Reg*。定義は CAB-94 担当) との一貫性 */
    HKEY k = 0; WCHAR s[32]; DWORD cb = sizeof s, ty = 0, dw = 0, cb4 = 4;
    LSTATUS e = RegOpenKeyExW(HKEY_LOCAL_MACHINE, W("SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion"), 0, 0x20019, &k);
    LSTATUS e2 = RegQueryValueExW(k, W("CurrentBuild"), NULL, &ty, (LPBYTE)s, &cb);
    LSTATUS e3 = RegQueryValueExW(k, W("CurrentMajorVersionNumber"), NULL, &ty, (LPBYTE)&dw, &cb4);
    EC("G16.08", "open=%d build=%d:%s major=%d:%u type=%u", (int)e, (int)e2, U(s), (int)e3, dw, ty);
    RegCloseKey(k);
}

static void t_g04id(void) {
    WCHAR b[64]; DWORD n = 64;
    BOOL r = GetComputerNameW(b, &n);
    EC("G04.01", "ret=%d name=%s n=%u", r, U(b), n);
    n = 64; r = GetComputerNameExW(5 /* ComputerNameDnsHostName */, b, &n);
    EC("G04.02", "ret=%d name=%s n=%u", r, U(b), n);
    n = 3; SetLastError(0); r = GetComputerNameW(b, &n);
    EC("G04.03", "ret=%d need=%u err=%u", r, n, GetLastError());

    /* MachineGuid: HWID コードの読み経路 (RegOpenKeyExA + RegQueryValueExA)。shimx の Reg* に値を置いて到達性のみ検査 */
    shimx_reg_set_sz("HKLM\\SOFTWARE\\Microsoft\\Cryptography", "MachineGuid", "11111111-2222-4333-8444-555555555555");
    HKEY k = 0; char g[64]; DWORD cb = sizeof g, ty = 0;
    LSTATUS e = RegOpenKeyExA(HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Cryptography", 0, 0x20119 /* KEY_READ|WOW64_64KEY */, &k);
    LSTATUS e2 = RegQueryValueExA(k, "MachineGuid", NULL, &ty, (LPBYTE)g, &cb);
    EC("G04.04", "open=%d query=%d type=%u guid=%s", (int)e, (int)e2, ty, g);
    RegCloseKey(k);

    WCHAR p[260];
    EC("G04.05", "hr=0x%x path=%s", (unsigned)SHGetFolderPathW(0, 5, 0, 0, p), U(p));
    EC("G04.06", "hr=0x%x path=%s", (unsigned)SHGetFolderPathW(0, 0x1a, 0, 0, p), U(p));
    EC("G04.07", "hr=0x%x path=%s", (unsigned)SHGetFolderPathW(0, 0x1c, 0, 0, p), U(p));
    EC("G04.08", "hr=0x%x", (unsigned)SHGetFolderPathW(0, 0x7f, 0, 0, p));
    EC("G04.09", "hr=0x%x path=%s attr_dir=%d", (unsigned)SHGetFolderPathW(0, 5 | 0x8000, 0, 0, p), U(p),
       (int)((GetFileAttributesW(p) & FILE_ATTRIBUTE_DIRECTORY) != 0));
    EC("G04.10", "ret=%d path=%s", SHGetSpecialFolderPathW(0, p, 0x1c, 0), U(p));
    static const GUID docs = { 0xFDD39AD0, 0x238F, 0x46AF, { 0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7 } };
    static const GUID bogus = { 1, 2, 3, { 4, 5, 6, 7, 8, 9, 10, 11 } };
    WCHAR* kp = NULL;
    HRESULT hr = SHGetKnownFolderPath(&docs, 0, 0, &kp);
    EC("G04.11", "hr=0x%x path=%s", (unsigned)hr, kp ? U(kp) : "(null)");
    if (kp) CoTaskMemFree(kp);
    kp = (WCHAR*)1;
    hr = SHGetKnownFolderPath(&bogus, 0, 0, &kp);
    EC("G04.12", "hr=0x%x out_null=%d", (unsigned)hr, kp == NULL);
    DWORD tn = GetTempPathW(260, p);
    EC("G04.13", "n=%u path=%s", tn, U(p));
    EC("G04.14", "need=%u", GetTempPathW(5, p));

    /* SHFolder.dll を LoadLibrary + GetProcAddress("SHGetFolderPathW") で動的束縛 (0x81bca0 ほか) */
    HMODULE sh = LoadLibraryW(W("SHFolder.dll"));
    typedef HRESULT (*PFN)(HWND, int, HANDLE, DWORD, LPWSTR);
    PFN pf = (PFN)GetProcAddress(sh, "SHGetFolderPathW");
    HRESULT h2 = pf ? pf(0, 5, 0, 0, p) : -1;
    EC("G04.15", "dll=%d proc=%d hr=0x%x path=%s", sh != 0, pf != 0, (unsigned)h2, U(p));
    NEWAPI(EC("G04.16", "proc_known=%d", GetProcAddress(GetModuleHandleW(W("shell32.dll")), "SHGetKnownFolderPath") != NULL);)
    EC("G04.17", "proc_miss=%d err=%u", GetProcAddress(GetModuleHandleW(W("kernel32.dll")), "NoSuchApiXyz") == NULL, GetLastError());

    WCHAR m[260];
    EC("G04.18", "ret_exe=%u path=%s", GetModuleFileNameW(0, m, 260), U(m));
    EC("G04.19", "ret_eng=%u path=%s", GetModuleFileNameW(g_eng, m, 260), U(m));
    SetLastError(0);
    EC("G04.20", "ret=%u err=%u", GetModuleFileNameW((HMODULE)0x1234, m, 260), GetLastError());
}

static void t_env(void) {
    WCHAR b[600]; DWORD n;
    b[0] = 0; SetLastError(0);
    n = GetEnvironmentVariableW(W("LANG"), b, 600);
    EC("ENV.01", "n=%u val=%s", n, U(b));
    SetLastError(0);
    n = GetEnvironmentVariableW(W("NO_SUCH_VAR_X"), b, 600);
    EC("ENV.02", "n=%u err=%u", n, GetLastError());
    EC("ENV.03", "ret=%d", SetEnvironmentVariableW(W("FLStudioData"), W("C:\\Users\\webstudio\\Documents\\Image-Line\\")));
    n = GetEnvironmentVariableW(W("FLStudioData"), b, 600);
    EC("ENV.04", "n=%u val=%s", n, U(b));
    EC("ENV.05", "ret=%d", SetEnvironmentVariableW(W("FLStudioData"), NULL));
    SetLastError(0);
    EC("ENV.06", "n=%u err=%u", GetEnvironmentVariableW(W("FLStudioData"), b, 600), GetLastError());
    n = ExpandEnvironmentStringsW(W("%USERPROFILE%\\x%NO_SUCH_VAR_X%"), b, 600);
    EC("ENV.07", "n=%u val=%s", n, U(b));
    n = ExpandEnvironmentStringsW(W("%APPDATA%"), NULL, 0);
    EC("ENV.08", "need=%u", n);
    b[0] = 0;
    n = GetEnvironmentVariableW(W("USERNAME"), b, 600);
    EC("ENV.09", "n=%u val=%s", n, U(b));
}

/* ---------- 時刻 ---------- */
static void t_time(void) {
    LARGE_INTEGER f, c1, c2;
    DWORD t1 = timeGetTime(), g1 = GetTickCount();
    QueryPerformanceFrequency(&f); QueryPerformanceCounter(&c1);
    double t0 = (double)c1.QuadPart;
    volatile unsigned long x = 0; for (unsigned long i = 0; i < 3000000; i++) x += i;
    QueryPerformanceCounter(&c2);
    DWORD t2 = timeGetTime(), g2 = GetTickCount();
    (void)t0;
    EC("TIME.01", "qpf=%lld", (long long)f.QuadPart);
    EC("TIME.02", "qpc_mono=%d", c2.QuadPart >= c1.QuadPart);
    EC("TIME.03", "tgt_mono=%d tick_mono=%d", t2 >= t1, g2 >= g1);
    EC("TIME.04", "tgt_vs_tick_close=%d", (int)(t1 > g1 ? t1 - g1 : g1 - t1) < 1000);
}

/* ---------- heap (CryptMsgGetParam 用) ---------- */
static void t_heap(void) {
    void* p = LocalAlloc(0x40, 136);
    int z = 1; for (int i = 0; i < 136; i++) if (((uint8_t*)p)[i]) z = 0;
    EC("MEM.01", "nonnull=%d zero=%d", p != 0, z);
    EC("MEM.02", "free_ret_null=%d", LocalFree(p) == 0);
}

/* ---------- B: プロセス / シェル / ローダ ---------- */
static void t_proc(void) {
    PROCESS_INFORMATION64 pi; memset(&pi, 0xAB, sizeof pi);
    uint8_t si[104]; memset(si, 0, sizeof si); *(uint32_t*)si = 104;
    WCHAR cmd[300]; { const WCHAR* src = W("\"ilbridge.exe\" \\\\.\\pipe\\x"); int i = 0; while ((cmd[i] = src[i])) i++; }
    SetLastError(0);
    BOOL r = CreateProcessW(W("C:\\Program Files\\Image-Line\\FL Studio 2026\\Plugins\\Fruity\\ilbridge\\64bit\\ilbridge.exe"), cmd, NULL, NULL, 0, 0x1000000, NULL, NULL, si, &pi);
    int z = 1; for (int i = 0; i < 24; i++) if (((uint8_t*)&pi)[i]) z = 0;
    EC("B01.01", "ret=%d err=%u pi_zero=%d", r, GetLastError(), z);
    SetLastError(0);
    r = CreateProcessW(NULL, W("\"CloudBounceConsole.exe\" --getchain"), NULL, NULL, 1, 0, NULL, NULL, si, &pi);
    EC("B01.02", "ret=%d err=%u", r, GetLastError());
}

static void t_shell(void) {
    shell_w("B02.01", "open", "https://www.image-line.com/", NULL);
    shell_w("B02.02", "open", "http://www.image-line.com/fl-studio-learning/", NULL);
    shell_w("B02.03", "explore", "C:\\Users\\webstudio\\Documents\\Image-Line", NULL);
    shell_w("B02.04", "open", "notepad.exe", "C:\\x.txt");
    shell_w("B02.05", "open", "C:\\Program Files\\Image-Line\\FL Studio 2026\\Help\\WhatsNew.htm", NULL);
    shell_w("B02.06", "open", "C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\Tools\\ControlCreator.exe", NULL);
    shell_w("B02.07", "open", "C:\\Program Files\\Image-Line\\FL Studio 2026\\fldiagnostic.exe", "/version \"26.1\"");
    shell_w("B02.08", "open", "C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\Tools\\Plugin Manager\\PluginManager.exe", "-deepscan");
    shell_w("B02.09", "open", "C:\\Program Files\\Image-Line\\FL Cloud Plugins\\FL Cloud Plugins.exe", NULL);
    shell_w("B02.10", "open", "C:\\x\\CopyLicenseToAllUsers.exe", "-load \"a.reg\"");
    shell_w("B02.11", NULL, "https://www.image-line.com/", NULL);    /* verb=NULL は "open" */
    shell_w("B02.12", "open", "C:\\Program Files\\Image-Line\\FL Studio 2026\\fldiagnostic.exe", "/restartfl \"FL64.exe\"");
    NEWAPI(EC("B02.13", "restart=%d", winstubs_restart_requested());)
    {
        SetLastError(0);
        HINSTANCE r = ShellExecuteA(0, "open", "https://support.image-line.com/", NULL, NULL, 1);
        EC("B03.01", "ret=%u", (unsigned)(uintptr_t)r);
        r = ShellExecuteA(0, "open", "C:\\x\\ControlCreator.exe", NULL, NULL, 1);
        EC("B03.02", "ret=%u", (unsigned)(uintptr_t)r);
    }
    shell_ex("B04.01", 1, "open", "https://www.image-line.com/", NULL);
    shell_ex("B04.02", 1, "runas", "C:\\x\\CopyLicenseToAllUsers.exe", "-load \"a.reg\"");
    shell_ex("B04.03", 1, "properties", "C:\\Users\\webstudio\\Documents\\a.flp", NULL);
    shell_ex("B04.04", 1, "open", "C:\\Program Files\\LilyPond\\bin\\lilypond.exe", "-dgui x.ly");
    shell_ex("B04.05", 1, "open", "C:\\x\\ControlCreator.exe", NULL);
    shell_ex("B04.06", 0, "open", "https://www.image-line.com/", NULL);
    shell_ex("B04.07", 0, "runas", "C:\\x\\RemoveLicenses.exe", NULL);
}

static void t_ldr(void) {
    SetLastError(0);
    HMODULE h = LoadLibraryW(W("WebView2Loader.dll"));
    EC("B05.01", "null=%d err=%u", h == 0, GetLastError());
    SetLastError(0);
    h = LoadLibraryW(W("C:\\Program Files\\Image-Line\\FL Studio 2026\\WebView2Loader.dll"));
    EC("B05.02", "null=%d err=%u", h == 0, GetLastError());
    SetLastError(0);
    h = LoadLibraryA("webview2loader.dll");
    EC("B05.03", "null=%d err=%u", h == 0, GetLastError());
    SetLastError(0);
    h = LoadLibraryExW(W("WebView2Loader.dll"), 0, 0);
    EC("B05.04", "null=%d err=%u", h == 0, GetLastError());
    SetLastError(0);
    h = LoadLibraryW(W("Totally Unknown Plugin.dll"));
    EC("B06.01", "null=%d err=%u", h == 0, GetLastError());
    h = LoadLibraryA("python312.dll");
    EC("B06.02", "null=%d err=%u", h == 0, GetLastError());
    h = LoadLibraryW(W("kernel32.dll"));
    EC("B06.03", "nonnull=%d", h != 0);
    NEWAPI(
        int found = 0; for (int i = 0; winstubs_loadlib_miss(i); i++) if (!strcasecmp(winstubs_loadlib_miss(i), "Totally Unknown Plugin.dll")) found = 1;
        EC("B06.04", "logged=%d", found);
    )
    shimx_set_load_hook(any_load_hook);
    SetLastError(0); h = LoadLibraryW(W("WebView2Loader.dll"));
    EC("B05.05", "null=%d err=%u", h == 0, GetLastError());
    SetLastError(0); h = LoadLibraryA("WebView2Loader.dll");
    EC("B05.06", "null=%d err=%u", h == 0, GetLastError());
    SetLastError(0); h = LoadLibraryExW(W("C:\\x\\WebView2Loader.dll"), 0, 8);
    EC("B05.07", "null=%d err=%u", h == 0, GetLastError());
    h = LoadLibraryW(W("SomePluginResolvedByHook.dll"));
    EC("B05.08", "nonnull=%d", h != 0);
    shimx_set_load_hook(NULL);
    GUID clsid = { 0x1, 0x2, 0x3, { 4, 5, 6, 7, 8, 9, 10, 11 } }, iid = { 0 };
    void* out = (void*)1;
    HRESULT hr = CoCreateInstance((uint64_t)(uintptr_t)&clsid, NULL, 1, &iid, &out);
    EC("B07.01", "hr=0x%x out_null=%d", (unsigned)hr, out == NULL);
}

/* ---------- D: UI/OS 付随 ---------- */
static void t_d(void) {
    EC("D01.01", "ret=%d", WTSRegisterSessionNotification(0x1234, 0));
    EC("D01.02", "ret=%d", WTSUnRegisterSessionNotification(0x1234));
    NEWAPI(
        EC("D02.01", "hr=0x%x", (unsigned)BufferedPaintInit());
        EC("D02.02", "hr=0x%x", (unsigned)BufferedPaintUnInit());
        EC("D04.01", "nonnull=%d", LoadIconW(g_eng, W("MAINICON")) != 0);
        EC("D05.01", "cx=%d cy=%d", GetSystemMetrics(0), GetSystemMetrics(1));
        EC("D05.02", "vscroll=%d hscroll=%d caption=%d frame=%d", GetSystemMetrics(2), GetSystemMetrics(3), GetSystemMetrics(4), GetSystemMetrics(32));
        EC("D05.03", "smicon=%d virt=%dx%d mouse=%d unknown=%d", GetSystemMetrics(49), GetSystemMetrics(78), GetSystemMetrics(79), GetSystemMetrics(19), GetSystemMetrics(9999));
        int32_t rc[4] = { -1, -1, -1, -1 };
        BOOL r = SystemParametersInfoW(0x30, 0, rc, 0);
        EC("D06.01", "ret=%d rect=%d,%d,%d,%d", r, rc[0], rc[1], rc[2], rc[3]);
        UINT lines = 0; r = SystemParametersInfoW(0x68, 0, &lines, 0);
        EC("D06.02", "ret=%d lines=%u", r, lines);
        uint8_t ncm[504]; memset(ncm, 0xFF, sizeof ncm);
        r = SystemParametersInfoW(0x29, 504, ncm, 0);
        EC("D06.03", "ret=%d cb=%u scroll=%d face0=%c", r, *(uint32_t*)ncm, ((int32_t*)ncm)[2], ncm[52]);
        SetLastError(0);
        r = SystemParametersInfoW(0x9999, 0, NULL, 0);
        EC("D06.04", "ret=%d err=%u", r, GetLastError());
    )
    EC("D03.01", "ok=%d", SetPriorityClass(GetCurrentProcess(), 0x80));
    UINT old = SetErrorMode(0x8001); UINT cur = SetErrorMode(old);
    EC("D03.02", "old=%u cur=0x%x", old, cur);
    EC("D03.03", "pseudo=0x%x", (unsigned)(uintptr_t)GetCurrentProcess());
}

/* ---------- user32 ポンプ系 (stub = 呼出カウントのみ) ---------- */
NEWAPI(
static void t_pump(void) {
    const uint32_t pump0 = winstubs_stats()->pump_calls;
    uint8_t msg[48]; memset(msg, 0, sizeof msg);
    BOOL p = PeekMessageW(msg, 0, 0, 0, 1);
    LONG g = GetMessageW(msg, 0, 0, 0);
    BOOL tr = TranslateMessage(msg); LONG d = DispatchMessageW(msg);
    BOOL pm = PostMessageW(0x100, 0x400, 1, 2); LRESULT_T sm = SendMessageW(0x100, 0x400, 1, 2);
    PostQuitMessage(0);
    UINT_PTR_T t = SetTimer(0, 7, 100, NULL); BOOL k = KillTimer(0, 7); BOOL w = WaitMessage();
    EC("P01.01", "peek=%d get=%d translate=%d dispatch=%d post=%d send=%u timer=%u kill=%d wait=%d",
       p, (int)g, tr, (int)d, pm, (unsigned)sm, (unsigned)t, k, w);
    EC("P01.02", "pump_calls=%u", winstubs_stats()->pump_calls - pump0);
}
)

/* ---------- G07: ユーザデータ dir 書込 (testpermissions.tmp) ---------- */
static void t_g07(void) {
    WCHAR dir[260];
    SHGetFolderPathW(0, 5 | 0x8000, 0, 0, dir);
    char base[300]; snprintf(base, sizeof base, "%s\\Image-Line", U(dir));
    int d = SHCreateDirectoryExW(0, W(base), NULL);
    char f[340]; snprintf(f, sizeof f, "%s\\testpermissions.tmp", base);
    HANDLE h = CreateFileW(W(f), GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0x80, 0);
    DWORD wr = 0; BOOL ok = h != INVALID_HANDLE_VALUE && WriteFile(h, "test", 4, &wr, NULL);
    if (h != INVALID_HANDLE_VALUE) CloseHandle(h);
    BOOL del = DeleteFileW(W(f));
    EC("G07.01", "mkdir=%d write=%d bytes=%u delete=%d", d == 0 || d == (int)ERROR_ALREADY_EXISTS, ok, wr, del);
}

/* ---------- 統計 (boot 受入) ---------- */
NEWAPI(
static void t_stats(void) {
    const WsStats* s = winstubs_stats();
    EC("S01.01", "createprocess_success=%u createprocess_attempts_ge1=%d", s->createprocess_success, s->createprocess_attempts >= 1);
}
)

/* ---------- G03 検証無効時 (trust=0 は shimx 既定へ委譲) ---------- */
NEWAPI(
static void t_trust_off(void) {
    WsConfig c; winstubs_defaults(&c); c.trust = 0; winstubs_init(&c);
    uint8_t wtd[128] = { 0 }; GUID a = { 0 };
    DWORD enc, ct, ft; void *hs = 0, *hm = 0;
    LONG v = WinVerifyTrust(0, &a, wtd);
    BOOL q = CryptQueryObject(1, W("x.dll"), 0x400, 2, 0, &enc, &ct, &ft, &hs, &hm, NULL);
    EC("G03.20", "verify=0x%x query=%d", (unsigned)v, q);
    winstubs_defaults(&c); winstubs_init(&c);
}
)

int main(int argc, char** argv) {
    int baseline =
#ifdef WS_BASELINE
        1;
#else
        0;
#endif
    if (baseline) {
        shimx_init();
        shimx_set_trust_ok(1);       /* shimx が提供する唯一のゲート用フックのみ。その他の方針は設定しない */
        g_eng = shimx_module_register("FLEngine_x64.dll", 0, "C:\\Program Files\\Image-Line\\FL Studio 2026\\FLEngine_x64.dll");
    }
#ifndef WS_BASELINE
    else {
        WsConfig c; winstubs_defaults(&c);
        winstubs_init(&c);
        g_eng = winstubs_engine_module();
    }
#endif
    if (argc > 1 && !strcmp(argv[1], "exit")) {
        shimx_set_exit_hook(on_exit_hook);
        TerminateProcess(GetCurrentProcess(), 5);
        fprintf(stderr, "UNREACHABLE\n");
        return 99;
    }
    t_g03();
    NEWAPI(t_g05(); t_g06();)
    t_g16(); t_g04id(); t_env(); t_time(); t_heap();
    t_proc(); t_shell(); t_ldr(); t_d();
    NEWAPI(t_pump();)
    t_g07();
    NEWAPI(t_trust_off(); t_stats();)
    fflush(stdout);
    fprintf(stderr, "[ws_cases] done (%s)\n", baseline ? "baseline" : "winstubs");
    return 0;
}
