/* 環境変数 / コマンドライン / システム情報 / バージョン / プロセス終了 / デバッグ / アトム。 */
#include "shimx_internal.h"
#include <strings.h>
#if defined(__EMSCRIPTEN__)
int emscripten_num_logical_cores(void);
#endif

static WCHAR* wdup_w(const WCHAR* s) {
    size_t n = (size_t)shx_wstr_len(s);
    WCHAR* d = (WCHAR*)malloc((n + 1) * 2);
    if (d) memcpy(d, s, (n + 1) * 2);
    return d;
}

/* ---------------------------------------------------------------
 * 環境変数 (UTF-8 "NAME=VALUE" 配列, 名前は大小無視)
 * --------------------------------------------------------------- */
static char** g_env; static int g_env_n, g_env_cap;
static shx_mutex_t g_env_lk;

static int env_find(const char* name, size_t nl) {
    for (int i = 0; i < g_env_n; i++)
        if (!strncasecmp(g_env[i], name, nl) && g_env[i][nl] == '=') return i;
    return -1;
}
static void env_set_locked(const char* name, const char* value) {
    size_t nl = strlen(name);
    int i = env_find(name, nl);
    if (!value) {
        if (i >= 0) { free(g_env[i]); g_env[i] = g_env[--g_env_n]; }
        return;
    }
    char* e = (char*)malloc(nl + strlen(value) + 2);
    sprintf(e, "%s=%s", name, value);
    if (i >= 0) { free(g_env[i]); g_env[i] = e; return; }
    if (g_env_n == g_env_cap) { g_env_cap = g_env_cap ? g_env_cap * 2 : 32; g_env = (char**)realloc(g_env, (size_t)g_env_cap * sizeof(char*)); }
    g_env[g_env_n++] = e;
}
int shimx_setenv_utf8(const char* name, const char* value) {
    shx_mutex_lock(&g_env_lk); env_set_locked(name, value); shx_mutex_unlock(&g_env_lk);
    return 0;
}

static int g_ncpu = 8;
void shx_init_env(void) {
#if defined(__EMSCRIPTEN__)
    g_ncpu = emscripten_num_logical_cores();
    if (g_ncpu < 1) g_ncpu = 1;
    if (g_ncpu > 64) g_ncpu = 64;
#endif
    char n[16]; snprintf(n, sizeof n, "%d", g_ncpu);
    static const char* const kv[][2] = {
        {"SystemRoot", "C:\\Windows"}, {"windir", "C:\\Windows"}, {"SystemDrive", "C:"},
        {"USERPROFILE", "C:\\Users\\webstudio"}, {"HOMEDRIVE", "C:"}, {"HOMEPATH", "\\Users\\webstudio"},
        {"APPDATA", "C:\\Users\\webstudio\\AppData\\Roaming"}, {"LOCALAPPDATA", "C:\\Users\\webstudio\\AppData\\Local"},
        {"TEMP", "C:\\Users\\webstudio\\AppData\\Local\\Temp"}, {"TMP", "C:\\Users\\webstudio\\AppData\\Local\\Temp"},
        {"ProgramFiles", "C:\\Program Files"}, {"ProgramFiles(x86)", "C:\\Program Files (x86)"},
        {"CommonProgramFiles", "C:\\Program Files\\Common Files"}, {"ProgramData", "C:\\ProgramData"},
        {"ALLUSERSPROFILE", "C:\\ProgramData"}, {"PUBLIC", "C:\\Users\\Public"},
        {"COMPUTERNAME", "WEBSTUDIO"}, {"USERNAME", "webstudio"}, {"USERDOMAIN", "WEBSTUDIO"},
        {"OS", "Windows_NT"}, {"PROCESSOR_ARCHITECTURE", "AMD64"}, {"PROCESSOR_IDENTIFIER", "Intel64 Family 6 Model 158 Stepping 10, GenuineIntel"},
        {"PATHEXT", ".COM;.EXE;.BAT;.CMD"}, {"ComSpec", "C:\\Windows\\system32\\cmd.exe"},
        {"PATH", "C:\\Windows\\system32;C:\\Windows"},
    };
    shx_mutex_lock(&g_env_lk);
    for (size_t i = 0; i < sizeof kv / sizeof kv[0]; i++) env_set_locked(kv[i][0], kv[i][1]);
    env_set_locked("NUMBER_OF_PROCESSORS", n);
    shx_mutex_unlock(&g_env_lk);
}

DWORD GetEnvironmentVariableW(LPCWSTR name, LPWSTR buf, DWORD n) {
    shx_ensure_init();
    char nm[512];
    if (!name || shimx_utf16_to_utf8(name, -1, nm, sizeof nm) < 0) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    shx_mutex_lock(&g_env_lk);
    int i = env_find(nm, strlen(nm));
    char* v = i >= 0 ? strdup(g_env[i] + strlen(nm) + 1) : NULL;
    shx_mutex_unlock(&g_env_lk);
    if (!v) { SetLastError(ERROR_ENVVAR_NOT_FOUND); return 0; }
    WCHAR* w = shx_wcsdup_utf8(v);
    int len = shx_wstr_len(w);
    DWORD r;
    if (!buf || n < (DWORD)len + 1) r = (DWORD)len + 1;
    else { memcpy(buf, w, ((size_t)len + 1) * 2); r = (DWORD)len; SetLastError(ERROR_SUCCESS); }
    free(w); free(v);
    return r;
}
BOOL SetEnvironmentVariableW(LPCWSTR name, LPCWSTR val) {
    shx_ensure_init();
    char nm[512], vv[4096];
    if (!name || !*name || shimx_utf16_to_utf8(name, -1, nm, sizeof nm) < 0 || strchr(nm, '=')) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (val && shimx_utf16_to_utf8(val, -1, vv, sizeof vv) < 0) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    shx_mutex_lock(&g_env_lk);
    if (!val && env_find(nm, strlen(nm)) < 0) { shx_mutex_unlock(&g_env_lk); SetLastError(ERROR_ENVVAR_NOT_FOUND); return FALSE; }
    env_set_locked(nm, val ? vv : NULL);
    shx_mutex_unlock(&g_env_lk);
    return TRUE;
}
DWORD ExpandEnvironmentStringsW(LPCWSTR src, LPWSTR dst, DWORD n) {
    shx_ensure_init();
    char in[4096], out[8192]; size_t o = 0;
    if (!src || shimx_utf16_to_utf8(src, -1, in, sizeof in) < 0) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    for (const char* p = in; *p && o < sizeof out - 600;) {
        if (*p == '%') {
            const char* e = strchr(p + 1, '%');
            if (e && e > p + 1) {
                char nm[256]; size_t nl = (size_t)(e - p - 1);
                if (nl < sizeof nm) {
                    memcpy(nm, p + 1, nl); nm[nl] = 0;
                    shx_mutex_lock(&g_env_lk);
                    int i = env_find(nm, nl);
                    if (i >= 0) { size_t vl = strlen(g_env[i] + nl + 1); if (o + vl < sizeof out - 8) { memcpy(out + o, g_env[i] + nl + 1, vl); o += vl; } }
                    shx_mutex_unlock(&g_env_lk);
                    if (i >= 0) { p = e + 1; continue; }
                }
                size_t cl = (size_t)(e - p) + 1;      /* 未定義: そのまま出力 */
                memcpy(out + o, p, cl); o += cl; p = e + 1; continue;
            }
        }
        out[o++] = *p++;
    }
    out[o] = 0;
    int w = shimx_utf8_to_utf16(out, (int)o, NULL, 0);
    DWORD need = (DWORD)(w < 0 ? 0 : w) + 1;
    if (dst && n >= need) { shimx_utf8_to_utf16(out, (int)o, dst, n); dst[need - 1] = 0; }
    return need;
}
LPWSTR GetEnvironmentStringsW(void) {
    shx_ensure_init();
    shx_mutex_lock(&g_env_lk);
    size_t cap = 4;
    for (int i = 0; i < g_env_n; i++) cap += strlen(g_env[i]) * 2 + 2;
    WCHAR* b = (WCHAR*)malloc(cap * 2); size_t k = 0;
    for (int i = 0; i < g_env_n; i++) {
        int w = shimx_utf8_to_utf16(g_env[i], -1, b + k, cap - k);
        k += (size_t)(w < 0 ? 0 : w); b[k++] = 0;
    }
    b[k++] = 0;
    shx_mutex_unlock(&g_env_lk);
    return b;
}
BOOL FreeEnvironmentStringsW(LPWSTR p) { free(p); return TRUE; }

/* ---------------------------------------------------------------
 * コマンドライン / StartupInfo
 * --------------------------------------------------------------- */
static char* g_cmdline = NULL; static WCHAR* g_cmdlineW = NULL; static char* g_cmdlineA = NULL;
static shx_mutex_t g_cmd_lk;
void shimx_set_command_line(const char* u) {
    shx_mutex_lock(&g_cmd_lk);
    free(g_cmdline); g_cmdline = strdup(u);
    g_cmdlineW = NULL; g_cmdlineA = NULL;       /* 旧バッファは参照中の可能性があるため解放しない (リーク許容) */
    shx_mutex_unlock(&g_cmd_lk);
}
static void cmd_ensure(void) {
    if (!g_cmdline) g_cmdline = strdup("\"C:\\Program Files\\Image-Line\\FL Studio 2026\\FL64.exe\"");
}
LPCWSTR GetCommandLineW(void) {
    shx_mutex_lock(&g_cmd_lk);
    cmd_ensure();
    if (!g_cmdlineW) g_cmdlineW = shx_wcsdup_utf8(g_cmdline);
    LPCWSTR r = g_cmdlineW;
    shx_mutex_unlock(&g_cmd_lk);
    return r;
}
LPCSTR GetCommandLineA(void) {
    shx_mutex_lock(&g_cmd_lk);
    cmd_ensure();
    if (!g_cmdlineA) {
        WCHAR* w = shx_wcsdup_utf8(g_cmdline);
        int n = WideCharToMultiByte(CP_ACP, 0, w, -1, NULL, 0, NULL, NULL);
        g_cmdlineA = (char*)malloc((size_t)(n > 0 ? n : 1));
        if (n > 0) WideCharToMultiByte(CP_ACP, 0, w, -1, g_cmdlineA, n, NULL, NULL); else g_cmdlineA[0] = 0;
        free(w);
    }
    LPCSTR r = g_cmdlineA;
    shx_mutex_unlock(&g_cmd_lk);
    return r;
}
void GetStartupInfoW(STARTUPINFOW64* si) {
    shx_ensure_init();
    if (!si) return;
    memset(si, 0, sizeof(*si));
    si->cb = sizeof(*si);
    si->dwFlags = 0x1 /* STARTF_USESHOWWINDOW */;
    si->wShowWindow = 1;
    si->hStdInput = (uint64_t)GetStdHandle(STD_INPUT_HANDLE);
    si->hStdOutput = (uint64_t)GetStdHandle(STD_OUTPUT_HANDLE);
    si->hStdError = (uint64_t)GetStdHandle(STD_ERROR_HANDLE);
}

/* ---------------------------------------------------------------
 * システム情報 / バージョン
 * --------------------------------------------------------------- */
static DWORD g_ver_major = 10, g_ver_minor = 0, g_ver_build = 19045;
DWORD g_shx_fv_ms = (26u << 16) | 1u, g_shx_fv_ls = (7u << 16) | 5653u;     /* GetFileVersionInfo が返す FL のファイル版 */
void shimx_set_version(DWORD major, DWORD minor, DWORD build, DWORD fileHi, DWORD fileLo) {
    g_ver_major = major; g_ver_minor = minor; g_ver_build = build;
    if (fileHi || fileLo) { g_shx_fv_ms = fileHi; g_shx_fv_ls = fileLo; }
}
void GetSystemInfo(SYSTEM_INFO64* si) {
    shx_ensure_init();
    if (!si) return;
    memset(si, 0, sizeof(*si));
    si->wProcessorArchitecture = 9;   /* AMD64 */
    si->dwPageSize = 4096;
    si->lpMinimumApplicationAddress = 0x10000;
    si->lpMaximumApplicationAddress = 0x7FFEFFFFull;
    si->dwActiveProcessorMask = (g_ncpu >= 64) ? ~0ull : ((1ull << g_ncpu) - 1);
    si->dwNumberOfProcessors = (DWORD)g_ncpu;
    si->dwProcessorType = 8664;
    si->dwAllocationGranularity = 65536;
    si->wProcessorLevel = 6;
    si->wProcessorRevision = 0x9E0A;
}
void GetNativeSystemInfo(SYSTEM_INFO64* si) { GetSystemInfo(si); }
DWORD GetVersion(void) { return (g_ver_build << 16) | (g_ver_minor << 8) | g_ver_major; }
BOOL GetVersionExW(OSVERSIONINFOEXW* vi) {
    if (!vi || (vi->dwOSVersionInfoSize != 276 && vi->dwOSVersionInfoSize != 284)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    DWORD sz = vi->dwOSVersionInfoSize;
    memset(vi, 0, sz);
    vi->dwOSVersionInfoSize = sz;
    vi->dwMajorVersion = g_ver_major; vi->dwMinorVersion = g_ver_minor; vi->dwBuildNumber = g_ver_build;
    vi->dwPlatformId = 2;
    if (sz == 284) { vi->wProductType = 1; vi->wSuiteMask = 0x100; }
    return TRUE;
}
ULONGLONG VerSetConditionMask(ULONGLONG cond, DWORD typeMask, BYTE op) {
    for (int i = 0; i < 8; i++) if (typeMask & (1u << i)) {
        cond &= ~(7ull << (i * 3));
        cond |= (ULONGLONG)(op & 7) << (i * 3);
    }
    return cond;
}
static int cmp_cond(DWORD actual, DWORD want, int op) {
    switch (op) {
        case 2: return actual > want;
        case 3: return actual >= want;
        case 4: return actual < want;
        case 5: return actual <= want;
        default: return actual == want;
    }
}
BOOL VerifyVersionInfoW(OSVERSIONINFOEXW* vi, DWORD mask, ULONGLONG cond) {
    if (!vi) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    #define OPOF(bit) (int)((cond >> ((bit) * 3)) & 7)
    if ((mask & 2u)) {          /* MAJOR: 非 EQUAL なら主バージョンの大小で確定 */
        int op = OPOF(1);
        if (op != 1) {
            if (g_ver_major > vi->dwMajorVersion) { if (op == 2 || op == 3) return TRUE; if (op == 4 || op == 5) return FALSE; }
            if (g_ver_major < vi->dwMajorVersion) { if (op == 4 || op == 5) return TRUE; if (op == 2 || op == 3) return FALSE; }
        }
        if (!cmp_cond(g_ver_major, vi->dwMajorVersion, op)) return FALSE;
    }
    if ((mask & 1u)) { if (!cmp_cond(g_ver_minor, vi->dwMinorVersion, OPOF(0))) return FALSE; }
    if ((mask & 4u)) { if (!cmp_cond(g_ver_build, vi->dwBuildNumber, OPOF(2))) return FALSE; }
    if ((mask & 8u)) { if (!cmp_cond(2, vi->dwPlatformId, OPOF(3))) return FALSE; }
    if ((mask & 0x20u)) { if (!cmp_cond(0, vi->wServicePackMajor, OPOF(5))) return FALSE; }
    if ((mask & 0x10u)) { if (!cmp_cond(0, vi->wServicePackMinor, OPOF(4))) return FALSE; }
    if ((mask & 0x80u)) { if (!cmp_cond(1, vi->wProductType, OPOF(7))) return FALSE; }
    #undef OPOF
    return TRUE;
}

BOOL GetComputerNameW(LPWSTR buf, LPDWORD n) {
    static const WCHAR nm[] = {'W','E','B','S','T','U','D','I','O',0};
    DWORD len = 9;
    if (!n) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (!buf || *n < len + 1) { *n = len + 1; SetLastError(111 /* ERROR_BUFFER_OVERFLOW */); return FALSE; }
    memcpy(buf, nm, sizeof nm); *n = len;
    return TRUE;
}
BOOL GetComputerNameExW(uint64_t type, LPWSTR buf, LPDWORD n) { (void)type; return GetComputerNameW(buf, n); }
BOOL IsWow64Process(HANDLE h, BOOL* wow) { (void)h; if (wow) *wow = FALSE; return TRUE; }
BOOL GetLogicalProcessorInformation(void* buf, LPDWORD len) {
    DWORD need = (DWORD)g_ncpu * 32;
    if (!len) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (!buf || *len < need) { *len = need; SetLastError(ERROR_INSUFFICIENT_BUFFER); return FALSE; }
    memset(buf, 0, need);
    for (int i = 0; i < g_ncpu; i++) {
        uint8_t* e = (uint8_t*)buf + (size_t)i * 32;
        *(uint64_t*)e = 1ull << i;             /* ProcessorMask */
        *(uint32_t*)(e + 8) = 0;               /* RelationProcessorCore */
    }
    *len = need;
    return TRUE;
}
static UINT g_errmode;
UINT SetErrorMode(UINT m) { UINT o = g_errmode; g_errmode = m; return o; }
DWORD SetThreadErrorMode(DWORD m, LPDWORD old) { if (old) *old = g_errmode; g_errmode = m; return TRUE; }

static UINT sys_dir(const char* s, LPWSTR buf, UINT n) {
    UINT len = (UINT)strlen(s);
    if (!buf || n < len + 1) return len + 1;
    for (UINT i = 0; i <= len; i++) buf[i] = (WCHAR)s[i];
    return len;
}
UINT GetSystemDirectoryW(LPWSTR buf, UINT n) { return sys_dir("C:\\Windows\\System32", buf, n); }
UINT GetWindowsDirectoryW(LPWSTR buf, UINT n) { return sys_dir("C:\\Windows", buf, n); }

void OutputDebugStringW(LPCWSTR s) {
    if (!g_shx_trace || !s) return;
    char u[1024]; if (shimx_utf16_to_utf8(s, -1, u, sizeof u) >= 0) fprintf(stderr, "[dbg] %s", u);
}
void OutputDebugStringA(LPCSTR s) { if (g_shx_trace && s) fprintf(stderr, "[dbg] %s", s); }
BOOL IsDebuggerPresent(void) { return FALSE; }
BOOL IsProcessorFeaturePresent(DWORD f) {
    switch (f) {
        case 2: case 3: case 6: case 8: case 9: case 10: case 12: case 13: case 14: case 15: case 16: case 17:
        case 36: case 37: case 38:
            return TRUE;
        default:
            return FALSE;     /* 23(FASTFAIL) と AVX 系は意図的に FALSE */
    }
}

/* ---------------------------------------------------------------
 * プロセス終了 / 子プロセス
 * --------------------------------------------------------------- */
static void (*g_exit_hook)(UINT);
void shimx_set_exit_hook(void (*fn)(UINT)) { g_exit_hook = fn; }
void ExitProcess(UINT code) {
    SHX_TRACE("ExitProcess(%u)", code);
    ShxObj* p = shx_ref((HANDLE)-1, OBJ_PROCESS);
    if (p) { shx_lock(); p->exit_code = code; p->state = 1; shx_unlock(); shx_notify(); shx_unref(p); }
    fflush(stdout); fflush(stderr);
    if (g_exit_hook) g_exit_hook(code);
    exit((int)code);
}
BOOL TerminateProcess(HANDLE h, UINT code) {
    if (h == (HANDLE)-1) ExitProcess(code);
    ShxObj* p = shx_ref(h, OBJ_PROCESS);
    if (p) { shx_unref(p); ExitProcess(code); }
    SetLastError(ERROR_INVALID_HANDLE);
    return FALSE;
}
BOOL CreateProcessW(LPCWSTR app, LPWSTR cmd, LPVOID pa, LPVOID ta, BOOL inherit, DWORD flags,
                    LPVOID env, LPCWSTR dir, LPVOID si, PROCESS_INFORMATION64* pi) {
    (void)pa; (void)ta; (void)inherit; (void)flags; (void)env; (void)dir; (void)si;
    if (g_shx_trace) {
        char u[512] = "";
        const WCHAR* s = app ? app : cmd;
        if (s) shimx_utf16_to_utf8(s, -1, u, sizeof u);
        fprintf(stderr, "[shimx] CreateProcessW denied: %s\n", u);
    }
    if (pi) memset(pi, 0, sizeof(*pi));
    SetLastError(ERROR_FILE_NOT_FOUND);       /* 外部プロセスは起動不可 (§3 #9: stub) */
    return FALSE;
}
BOOL AssignProcessToJobObject(HANDLE job, HANDLE proc) { (void)job; (void)proc; SetLastError(ERROR_ACCESS_DENIED); return FALSE; }

/* ---------------------------------------------------------------
 * アトム (ローカル/グローバル別表, 参照カウント付き)
 * --------------------------------------------------------------- */
typedef struct { WCHAR* s; int refs; } AtomEnt;
#define ATOM_MAX 2048
static AtomEnt g_atoms[2][ATOM_MAX];
static shx_mutex_t g_atom_lk;
static ATOM atom_add(int t, LPCWSTR s) {
    if (!s) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (shx_is_iptr((uintptr_t)s)) return (ATOM)(uintptr_t)s;   /* MAKEINTATOM */
    int n = shx_wstr_len(s);
    if (n == 0 || n > 255) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    shx_mutex_lock(&g_atom_lk);
    int free_i = -1, hit = -1;
    for (int i = 0; i < ATOM_MAX; i++) {
        if (!g_atoms[t][i].s) { if (free_i < 0) free_i = i; continue; }
        if (shx_wcsicmp(g_atoms[t][i].s, s) == 0) { hit = i; break; }
    }
    ATOM a = 0;
    if (hit >= 0) { g_atoms[t][hit].refs++; a = (ATOM)(0xC000 + hit); }
    else if (free_i >= 0) { g_atoms[t][free_i].s = wdup_w(s); g_atoms[t][free_i].refs = 1; a = (ATOM)(0xC000 + free_i); }
    shx_mutex_unlock(&g_atom_lk);
    if (!a) SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return a;
}
static ATOM atom_find(int t, LPCWSTR s) {
    if (!s) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (shx_is_iptr((uintptr_t)s)) return (ATOM)(uintptr_t)s;
    ATOM a = 0;
    shx_mutex_lock(&g_atom_lk);
    for (int i = 0; i < ATOM_MAX; i++) if (g_atoms[t][i].s && shx_wcsicmp(g_atoms[t][i].s, s) == 0) { a = (ATOM)(0xC000 + i); break; }
    shx_mutex_unlock(&g_atom_lk);
    if (!a) SetLastError(ERROR_FILE_NOT_FOUND);
    return a;
}
static ATOM atom_del(int t, ATOM a) {
    if (a < 0xC000 || a - 0xC000 >= ATOM_MAX) { SetLastError(ERROR_INVALID_HANDLE); return a; }
    int i = a - 0xC000; ATOM r = 0;
    shx_mutex_lock(&g_atom_lk);
    if (!g_atoms[t][i].s) { r = a; SetLastError(ERROR_INVALID_HANDLE); }
    else if (--g_atoms[t][i].refs <= 0) { free(g_atoms[t][i].s); g_atoms[t][i].s = NULL; }
    shx_mutex_unlock(&g_atom_lk);
    return r;
}
ATOM AddAtomW(LPCWSTR s) { return atom_add(0, s); }
ATOM FindAtomW(LPCWSTR s) { return atom_find(0, s); }
ATOM DeleteAtom(ATOM a) { return atom_del(0, a); }
ATOM GlobalAddAtomW(LPCWSTR s) { return atom_add(1, s); }
ATOM GlobalFindAtomW(LPCWSTR s) { return atom_find(1, s); }
ATOM GlobalDeleteAtom(ATOM a) { return atom_del(1, a); }
