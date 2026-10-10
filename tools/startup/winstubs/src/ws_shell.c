/* B: プロセス / シェル / ローダ。stub_plan.md §5-B の戻り値表を実装する。
 *   CreateProcessW            → FALSE / ERROR_FILE_NOT_FOUND (shimx 既定を計数付きで委譲)
 *   ShellExecuteW/A "open" http(s) / explore / notepad / .htm → 33 (no-op。URL はコールバックへ)
 *   ShellExecute* 外部 .exe ツール → 2 (SE_ERR_FNF)   ShellExecuteEx の runas/properties/LilyPond → FALSE + 1223
 *   fldiagnostic /restartfl   → 2 + 再起動要求フラグ (G12)
 *   LoadLibrary("WebView2Loader.dll") → NULL / 126 (load hook が将来解決しても常に拒否: G13)
 *   LoadLibrary 未登録名       → NULL / 126、trap しない。名前をログ
 */
#include "ws_internal.h"
#include <ctype.h>
#include <strings.h>

static void (*g_url_cb)(const char*);
static volatile int g_restart;

void winstubs_set_open_url_cb(void (*cb)(const char*)) { g_url_cb = cb; }
int  winstubs_restart_requested(void) { return g_restart; }

static const char* base_of(const char* p) {
    const char* b = p;
    for (; *p; p++) if (*p == '\\' || *p == '/') b = p + 1;
    return b;
}
static int has_ext(const char* f, const char* ext) {
    size_t n = strlen(f), e = strlen(ext);
    return n >= e && !strcasecmp(f + n - e, ext);
}
static int starts_ci(const char* s, const char* p) { return !strncasecmp(s, p, strlen(p)); }
static int contains_ci(const char* h, const char* n) {
    if (!h) return 0;
    size_t nl = strlen(n);
    for (; *h; h++) if (!strncasecmp(h, n, nl)) return 1;
    return 0;
}

int winstubs_shell_classify(const char* verb, const char* file, const char* params, int is_ex) {
    if (!verb || !*verb) verb = "open";
    if (!file) file = "";
    const char* base = base_of(file);
    if (contains_ci(base, "fldiagnostic") && contains_ci(params, "/restartfl")) return 2;
    if (!strcasecmp(verb, "runas") || !strcasecmp(verb, "properties") ||
        contains_ci(base, "lilypond") || contains_ci(base, "midi2ly"))
        return is_ex ? 3 : 2;
    if (!strcasecmp(verb, "open") && (starts_ci(file, "http://") || starts_ci(file, "https://"))) return 1;
    if (!strcasecmp(verb, "explore")) return 1;
    if (!strcasecmp(base, "notepad") || !strcasecmp(base, "notepad.exe")) return 1;
    if (has_ext(file, ".htm") || has_ext(file, ".html")) return 1;
    return 2;                                   /* .exe ツール (ControlCreator / PluginManager / CopyLicense ...) とその他 */
}

int ws_shell_hook(const char* verb, const char* file, const char* params) {
    WS_INC(shell_calls);
    if (!verb || !*verb) verb = "open";
    if (contains_ci(base_of(file ? file : ""), "fldiagnostic") && contains_ci(params, "/restartfl")) {
        g_restart = 1; WS_INC(shell_restartfl);
    }
    int c = winstubs_shell_classify(verb, file, params, 0);
    if (c == 1) {
        WS_INC(shell_ok);
        if (file && !strcasecmp(verb, "open") && (starts_ci(file, "http://") || starts_ci(file, "https://"))) {
            WS_INC(shell_url);
            if (g_url_cb) g_url_cb(file);
        }
        return 1;
    }
    WS_INC(shell_fnf);
    return 0;
}

static BOOL shell_ex_common(uint8_t* i, const char* v, const char* f, const char* p, BOOL (*real)(void*)) {
    if (winstubs_shell_classify(v, f, p, 1) == 3) {
        WS_INC(shell_calls); WS_INC(shell_cancel);
        *(uint64_t*)(i + 56) = 5;               /* hInstApp = SE_ERR_ACCESSDENIED */
        *(uint64_t*)(i + 104) = 0;              /* hProcess */
        SetLastError(ERROR_CANCELLED);          /* UAC キャンセル扱い: FL が通常の失敗処理へ */
        return FALSE;
    }
    return real(i);
}
BOOL __wrap_ShellExecuteExW(void* info) {
    uint8_t* i = (uint8_t*)info;
    char v[64] = "", f[1024] = "", p[1024] = "";
    const WCHAR* wv = (const WCHAR*)(uintptr_t)*(uint64_t*)(i + 16);
    const WCHAR* wf = (const WCHAR*)(uintptr_t)*(uint64_t*)(i + 24);
    const WCHAR* wp = (const WCHAR*)(uintptr_t)*(uint64_t*)(i + 32);
    if (wv) shimx_utf16_to_utf8(wv, -1, v, sizeof v);
    if (wf) shimx_utf16_to_utf8(wf, -1, f, sizeof f);
    if (wp) shimx_utf16_to_utf8(wp, -1, p, sizeof p);
    return shell_ex_common(i, v, f, p, __real_ShellExecuteExW);
}
BOOL __wrap_ShellExecuteExA(void* info) {
    uint8_t* i = (uint8_t*)info;
    const char* v = (const char*)(uintptr_t)*(uint64_t*)(i + 16);
    const char* f = (const char*)(uintptr_t)*(uint64_t*)(i + 24);
    const char* p = (const char*)(uintptr_t)*(uint64_t*)(i + 32);
    return shell_ex_common(i, v ? v : "", f ? f : "", p ? p : "", __real_ShellExecuteExA);
}

/* ---- CreateProcessW ---- */
BOOL __wrap_CreateProcessW(LPCWSTR app, LPWSTR cmd, LPVOID pa, LPVOID ta, BOOL inh, DWORD fl, LPVOID env, LPCWSTR dir, LPVOID si, void* pi) {
    WS_INC(createprocess_attempts);
    BOOL r = __real_CreateProcessW(app, cmd, pa, ta, inh, fl, env, dir, si, pi);
    if (r) WS_INC(createprocess_success);
    return r;
}

/* ---- LoadLibrary ---- */
#define MISS_MAX 32
static char g_miss[MISS_MAX][64];
static volatile int g_miss_n, g_miss_lock;

const char* winstubs_loadlib_miss(int i) { return (i >= 0 && i < g_miss_n) ? g_miss[i] : NULL; }

static void note_miss(const char* name) {
    while (__atomic_test_and_set(&g_miss_lock, __ATOMIC_ACQUIRE)) {}
    char b[64]; snprintf(b, sizeof b, "%s", base_of(name));
    int dup = 0;
    for (int i = 0; i < g_miss_n; i++) if (!strcasecmp(g_miss[i], b)) { dup = 1; break; }
    if (!dup && g_miss_n < MISS_MAX) { memcpy(g_miss[g_miss_n], b, sizeof b); g_miss_n++; }
    __atomic_clear(&g_miss_lock, __ATOMIC_RELEASE);
}
static int blocked(const char* name) { return !strcasecmp(base_of(name), "WebView2Loader.dll") || !strcasecmp(base_of(name), "WebView2Loader"); }

/* 1 = 拒否 (戻り値 0 / 126 を設定済み) */
static int load_denied(const char* u8) {
    WS_INC(loadlib_calls);
    if (!blocked(u8)) return 0;
    WS_INC(loadlib_blocked); WS_INC(loadlib_miss); note_miss(u8);
    SetLastError(ERROR_MOD_NOT_FOUND);
    return 1;
}
HMODULE __wrap_LoadLibraryW(LPCWSTR name) {
    char u[512] = "";
    if (name) shimx_utf16_to_utf8(name, -1, u, sizeof u);
    if (name && load_denied(u)) return 0;
    HMODULE r = __real_LoadLibraryW(name);
    if (!r && name) { WS_INC(loadlib_miss); note_miss(u); }
    return r;
}
HMODULE __wrap_LoadLibraryA(LPCSTR name) {
    if (name && load_denied(name)) return 0;
    HMODULE r = __real_LoadLibraryA(name);
    if (!r && name) { WS_INC(loadlib_miss); note_miss(name); }
    return r;
}
HMODULE __wrap_LoadLibraryExW(LPCWSTR name, HANDLE file, DWORD flags) {
    char u[512] = "";
    if (name) shimx_utf16_to_utf8(name, -1, u, sizeof u);
    if (name && load_denied(u)) return 0;
    HMODULE r = __real_LoadLibraryExW(name, file, flags);
    if (!r && name) { WS_INC(loadlib_miss); note_miss(u); }
    return r;
}
