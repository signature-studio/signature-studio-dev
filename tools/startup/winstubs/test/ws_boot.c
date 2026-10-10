/* 起動シーケンス e2e (ホスト glue 抜き): エンジン起動 13 ステップのうち Win32 面を、GATES.md / STARTUP.md に記された
 * 呼出順どおりに叩き、G01〜G08/G16 (+G12/G13) を fail-soft で通過することを確認する。
 * 出力は "step<TAB>result"。期待値は data/boot_expect.tsv (run_boot.mjs が突合)。
 * Reg* は shimx 既存実装 (CAB-94 vreg が seed を担当)。ここでは seed 相当を shimx_reg_set_* で流し込むだけ。
 */
#include "../src/winstubs.h"
#include <stdarg.h>
#include <strings.h>

HWND FindWindowW(LPCWSTR, LPCWSTR);
LONG RtlGetVersion(void*);
int  GetSystemMetrics(int);
HRESULT BufferedPaintInit(void);
HANDLE LoadIconW(HANDLE, LPCWSTR);
LONG GetMessageW(LPVOID, HWND, UINT, UINT);
BOOL PeekMessageW(LPVOID, HWND, UINT, UINT, UINT);

static void step(const char* id, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
static void step(const char* id, const char* fmt, ...) {
    char b[400]; va_list ap; va_start(ap, fmt); vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
    printf("%s\t%s\n", id, b);
}
static WCHAR* W(const char* s) {
    static WCHAR buf[8][520]; static int k;
    WCHAR* b = buf[k++ & 7]; int i = 0;
    for (; s[i] && i < 519; i++) b[i] = (WCHAR)(unsigned char)s[i];
    b[i] = 0; return b;
}
static const char* U(const WCHAR* w) {
    static char buf[8][520]; static int k;
    char* b = buf[k++ & 7]; int i = 0;
    for (; w[i] && i < 519; i++) b[i] = (char)w[i];
    b[i] = 0; return b;
}

/* seed.tsv: hive<TAB>key<TAB>value<TAB>type<TAB>data  (run_boot.mjs が data/vreg_seed.json から生成) */
static int load_seed(const char* path) {
    FILE* f = fopen(path, "r"); char line[1024]; int n = 0;
    if (!f) return -1;
    while (fgets(line, sizeof line, f)) {
        char* t[5]; int k = 0; char* p = line;
        line[strcspn(line, "\r\n")] = 0;
        while (k < 5) { t[k++] = p; char* e = strchr(p, '\t'); if (!e) break; *e = 0; p = e + 1; }
        if (k < 5) continue;
        char key[600]; snprintf(key, sizeof key, "%s\\%s", t[0], t[1]);
        if (!strcmp(t[3], "REG_DWORD")) shimx_reg_set_dword(key, t[2], (DWORD)strtoul(t[4], 0, 10));
        else shimx_reg_set_sz(key, t[2], t[4]);
        n++;
    }
    fclose(f);
    return n;
}

static int g_open_url_calls;
static void on_url(const char* u) { (void)u; g_open_url_calls++; }

static int verify_signature(const char* label, HMODULE m) {
    WCHAR path[260]; GetModuleFileNameW(m, path, 260);
    uint8_t wtd[128] = { 0 }; GUID act = { 0 };
    LONG v = WinVerifyTrust(0, &act, wtd);                              /* VERIFY */
    DWORD enc, ct, ft; void *hs = 0, *hm = 0;
    int ok = (v == 0) && CryptQueryObject(1, path, 0x400, 2, 0, &enc, &ct, &ft, &hs, &hm, NULL);
    DWORD len = 0;
    if (ok) ok = CryptMsgGetParam(hm, 6, 0, NULL, &len) && len >= 0x80;
    void* si = ok ? LocalAlloc(0x40, len) : NULL;
    if (ok) ok = si && CryptMsgGetParam(hm, 6, 0, si, &len);
    void* ctx = ok ? CertFindCertificateInStore(hs, enc, 0, 0xb0000, si, NULL) : NULL;
    WCHAR name[64] = { 0 };
    if (ctx) { DWORD n = CertGetNameStringW(ctx, 4, 0, NULL, NULL, 0); WCHAR* b = (WCHAR*)LocalAlloc(0x40, n * 2); CertGetNameStringW(ctx, 4, 0, NULL, b, n); memcpy(name, b, n * 2); LocalFree(b); }
    int match = ctx && !strcmp(U(name), "Image Line NV");
    if (ctx) CertFreeCertificateContext(ctx);
    if (si) LocalFree(si);
    if (hs) CertCloseStore(hs, 0);
    if (hm) CryptMsgClose(hm);
    LONG c = WinVerifyTrust(0, &act, wtd);                              /* CLOSE */
    step(label, "verify=%d signer_match=%d close=%d", (int)v, match != 0, (int)c);
    return match && v == 0 && c == 0;
}

int main(int argc, char** argv) {
    const char* seedpath = argc > 1 ? argv[1] : "/seed.tsv";
    WsConfig cfg; winstubs_defaults(&cfg);
    winstubs_init(&cfg);
    winstubs_set_open_url_cb(on_url);
    step("S00.init", "seed_values=%d", load_seed(seedpath));

    /* S01: CPU 機能検査 (G05: engine 0x13755b0) */
    uint32_t r[4]; winstubs_cpuid(1, 0, r);
    step("G05.cpu", "cmov=%d", (r[3] >> 15) & 1);

    /* S02: 署名ゲート (G03: engine 0x1375990 ×2 + 呼出元 EXE) */
    HMODULE eng = winstubs_engine_module();
    int s1 = verify_signature("G03.engine_self_1", eng);
    int s2 = verify_signature("G03.engine_self_2", eng);
    int s3 = verify_signature("G03.host_exe", 0);
    step("G03.result", "pass=%d", s1 && s2 && s3);

    /* S03: 単一インスタンス (G06) */
    HWND other = FindWindowW(W("TFruityLoopsMainForm"), NULL);
    step("G06.single_instance", "existing_window=%d", other != 0);

    /* S04: OS バージョン (G16: Delphi RTL / 0x867e10) */
    OSVERSIONINFOEXW v; memset(&v, 0, sizeof v); v.dwOSVersionInfoSize = 284;
    RtlGetVersion(&v);
    OSVERSIONINFOEXW v2; memset(&v2, 0, sizeof v2); v2.dwOSVersionInfoSize = 284;
    GetVersionExW(&v2);
    HKEY k = 0; DWORD major = 0, cb = 4, ty = 0;
    RegOpenKeyExW(HKEY_LOCAL_MACHINE, W("SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion"), 0, 0x20019, &k);
    RegQueryValueExW(k, W("CurrentMajorVersionNumber"), NULL, &ty, (LPBYTE)&major, &cb);
    RegCloseKey(k);
    step("G16.os", "rtl=%u.%u.%u api=%u.%u.%u reg_major=%u consistent=%d", v.dwMajorVersion, v.dwMinorVersion, v.dwBuildNumber,
         v2.dwMajorVersion, v2.dwMinorVersion, v2.dwBuildNumber, major,
         v.dwMajorVersion == v2.dwMajorVersion && v.dwBuildNumber == v2.dwBuildNumber && major == v.dwMajorVersion);

    /* S05: ユーザデータ dir (G07: engine 0x1264050/0x1263d50) */
    WCHAR docs[260]; SHGetFolderPathW(0, 5 | 0x8000, 0, 0, docs);
    char base[300]; snprintf(base, sizeof base, "%s\\Image-Line", U(docs));
    int mk = SHCreateDirectoryExW(0, W(base), NULL);
    char tf[340]; snprintf(tf, sizeof tf, "%s\\testpermissions.tmp", base);
    HANDLE h = CreateFileW(W(tf), GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0x80, 0);
    DWORD wr = 0; int wok = h != INVALID_HANDLE_VALUE && WriteFile(h, "x", 1, &wr, NULL);
    if (h != INVALID_HANDLE_VALUE) CloseHandle(h);
    DeleteFileW(W(tf));
    step("G07.userdata", "dir=%s created=%d writable=%d", base, mk == 0 || mk == (int)ERROR_ALREADY_EXISTS, wok);

    /* S06: 設定フラグ (G08): seed 値が Reg* 経由で読める (Reg 本体と seed は CAB-94) */
    char val[16] = "?"; DWORD vc = sizeof val;
    LSTATUS e = RegOpenKeyExA(HKEY_CURRENT_USER, "Software\\Image-Line\\FL Studio 26\\General", 0, 0x20019, &k);
    LSTATUS e2 = e ? e : RegQueryValueExA(k, "CrashLoadingStartupProject", NULL, &ty, (LPBYTE)val, &vc);
    if (!e) RegCloseKey(k);
    step("G08.flags", "open=%d query=%d CrashLoadingStartupProject=%s", (int)e, (int)e2, val);
    LSTATUS er = RegOpenKeyExA(HKEY_CURRENT_USER, "Software\\Image-Line\\Registrations\\FL Studio 26.1", 0, 0x20019, &k);
    step("G08.registrations_key", "status=%d", (int)er);

    /* S07: マシン識別入力 (G04 の入力供給のみ。判定は FL 側コード) */
    char guid[64] = ""; DWORD gc = sizeof guid;
    LSTATUS g1 = RegOpenKeyExA(HKEY_LOCAL_MACHINE, "SOFTWARE\\Microsoft\\Cryptography", 0, 0x20119, &k);
    LSTATUS g2 = g1 ? g1 : RegQueryValueExA(k, "MachineGuid", NULL, &ty, (LPBYTE)guid, &gc);
    if (!g1) RegCloseKey(k);
    WCHAR cn[64]; DWORD cl = 64; GetComputerNameExW(5, cn, &cl);
    HMODULE shf = LoadLibraryW(W("SHFolder.dll"));
    typedef HRESULT (*PFN)(HWND, int, HANDLE, DWORD, LPWSTR);
    PFN pf = (PFN)GetProcAddress(shf, "SHGetFolderPathW");
    WCHAR pd[260] = { 0 }; HRESULT hr = pf ? pf(0, 5, 0, 0, pd) : -1;
    step("G04.machine_inputs", "guid_len=%d reg=%d/%d computer=%s shfolder_hr=%d path=%s", (int)strlen(guid), (int)g1, (int)g2, U(cn), (int)hr, U(pd));

    /* S08: 環境 (STARTUP: env FLStudio*Data 設定) */
    SetEnvironmentVariableW(W("FLStudioData"), docs);
    WCHAR ev[260]; GetEnvironmentVariableW(W("FLStudioData"), ev, 260);
    WCHAR lang[8]; GetEnvironmentVariableW(W("LANG"), lang, 8);
    step("S08.env", "flstudiodata_ok=%d lang=%s", !strcmp(U(ev), U(docs)), U(lang));

    /* S09: 子プロセス / シェル (G12/G13): すべて失敗しても継続 */
    PROCESS_INFORMATION64 pi; uint8_t si[104] = { 0 };
    BOOL cp = CreateProcessW(W("C:\\Program Files\\Image-Line\\FL Studio 2026\\Plugins\\Fruity\\ilbridge\\64bit\\ilbridge.exe"), NULL, NULL, NULL, 0, 0, NULL, NULL, si, &pi);
    HMODULE wv = LoadLibraryW(W("WebView2Loader.dll"));
    DWORD wverr = GetLastError();
    HINSTANCE se = ShellExecuteW(0, W("open"), W("https://support.image-line.com/"), NULL, NULL, 1);
    HINSTANCE se2 = ShellExecuteW(0, W("open"), W("C:\\Program Files\\Image-Line\\FL Studio 2026\\System\\Tools\\ControlCreator.exe"), NULL, NULL, 1);
    GUID clsid = { 1, 2, 3, { 4, 5, 6, 7, 8, 9, 10, 11 } }, iid = { 0 }; void* po = 0;
    HRESULT cc = CoCreateInstance((uint64_t)(uintptr_t)&clsid, NULL, 1, &iid, &po);
    step("G12.process", "create_process=%d webview2=%d err=%u shell_url=%u shell_exe=%u asio_hr=0x%x", cp, wv != 0, wverr,
         (unsigned)(uintptr_t)se, (unsigned)(uintptr_t)se2, (unsigned)cc);

    /* S10: UI/OS 付随 (S19) */
    BOOL wts = WTSRegisterSessionNotification(0x100, 0);
    step("D.ui", "wts=%d bp=0x%x icon=%d cx=%d", wts, (unsigned)BufferedPaintInit(), LoadIconW(eng, W("MAINICON")) != 0, GetSystemMetrics(0));

    /* S11: メッセージポンプ未結線でも TApplication.Run 相当のループが落ちずに終わる (CAB-102 が実体を結線) */
    uint8_t msg[48]; int spins = 0;
    while (GetMessageW(msg, 0, 0, 0) > 0 && spins < 10) spins++;
    PeekMessageW(msg, 0, 0, 0, 1);
    step("S11.pump_stub", "loop_exit=1 spins=%d", spins);

    /* 受入 */
    const WsStats* s = winstubs_stats();
    step("ACC.createprocess_success", "%u", s->createprocess_success);
    step("ACC.createprocess_attempts", "%u", s->createprocess_attempts);
    step("ACC.shell_url_calls", "%u cb=%d", s->shell_url, g_open_url_calls);
    step("ACC.loadlib_blocked", "%u", s->loadlib_blocked);
    step("ACC.unresolved_trap", "0");   /* shim_unimplemented が呼ばれていれば abort 済みでここへ到達しない */
    fflush(stdout);
    return 0;
}
