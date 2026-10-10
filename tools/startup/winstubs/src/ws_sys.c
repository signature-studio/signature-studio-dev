/* G07/G16/G04(識別値): OS バージョン / 既知フォルダ / 一時パスを vreg_seed.json に合わせる。 */
#include "ws_internal.h"

/* ---- RtlGetVersion (ntdll): RTL_OSVERSIONINFOW(276B) / EXW(284B) ---- */
LONG RtlGetVersion(void* vi) {
    uint32_t sz = vi ? *(uint32_t*)vi : 0;
    if (sz != 276 && sz != 284) return (LONG)0xC000000D;           /* STATUS_INVALID_PARAMETER */
    return GetVersionExW((OSVERSIONINFOEXW*)vi) ? 0 : (LONG)0xC000000D;   /* STATUS_SUCCESS */
}

/* ---- "C:\Users\user" → "C:\Users\<cfg.user>" ---- */
static int is_default_user_prefix(const WCHAR* s) {
    static const char p[] = "C:\\Users\\user";
    size_t n = sizeof p - 1;
    for (size_t i = 0; i < n; i++) if (s[i] != (WCHAR)p[i]) return 0;
    return s[n] == 0 || s[n] == '\\';
}
/* s を新しい長さで返す。cap = バッファ WCHAR 数。入らなければ -1 */
static int fix_user(WCHAR* s, size_t cap) {
    size_t len = (size_t)shx_wstr_len(s);
    if (!g_ws_cfg.user || !is_default_user_prefix(s)) return (int)len;     /* winstubs_init 前は shimx 既定のまま */
    size_t ul = strlen(g_ws_cfg.user);
    const size_t pre = 13;                      /* strlen("C:\\Users\\user") */
    size_t nl = len - 4 + ul;
    if (nl + 1 > cap) return -1;
    memmove(s + 9 + ul, s + pre, (len - pre + 1) * sizeof(WCHAR));
    for (size_t i = 0; i < ul; i++) s[9 + i] = (WCHAR)(unsigned char)g_ws_cfg.user[i];
    return (int)nl;
}

HRESULT __wrap_SHGetFolderPathW(HWND w, int csidl, HANDLE tok, DWORD flags, LPWSTR path) {
    int create = csidl & 0x8000;
    HRESULT hr = __real_SHGetFolderPathW(w, csidl & ~0x8000, tok, flags, path);   /* CREATE は自前 (webstudio 側を作る) */
    if (hr != S_OK || !path) return hr;
    if (fix_user(path, 260) < 0) return (HRESULT)0x8007007A;      /* HRESULT_FROM_WIN32(ERROR_INSUFFICIENT_BUFFER) */
    if (create) SHCreateDirectoryExW(0, path, NULL);
    return S_OK;
}
BOOL __wrap_SHGetSpecialFolderPathW(HWND w, LPWSTR path, int csidl, BOOL create) {
    return __wrap_SHGetFolderPathW(w, create ? (csidl | 0x8000) : csidl, 0, 0, path) == S_OK;
}
HRESULT __wrap_SHGetKnownFolderPath(const GUID* id, DWORD flags, HANDLE tok, LPWSTR* out) {
    HRESULT hr = __real_SHGetKnownFolderPath(id, flags & ~0x8000u, tok, out);
    if (hr != S_OK || !out || !*out) return hr;
    size_t len = (size_t)shx_wstr_len(*out), cap = len + 16 + strlen(g_ws_cfg.user);
    WCHAR* n = (WCHAR*)CoTaskMemAlloc(cap * sizeof(WCHAR));
    if (!n) { CoTaskMemFree(*out); *out = NULL; return (HRESULT)0x8007000E; }
    memcpy(n, *out, (len + 1) * sizeof(WCHAR));
    CoTaskMemFree(*out);
    fix_user(n, cap);
    *out = n;
    if (flags & 0x8000u /* KF_FLAG_CREATE */) SHCreateDirectoryExW(0, n, NULL);
    return S_OK;
}

DWORD __wrap_GetTempPathW(DWORD n, LPWSTR buf) {
    WCHAR t[300];
    DWORD r = __real_GetTempPathW(300, t);
    if (!r || r >= 300) return __real_GetTempPathW(n, buf);
    int len = fix_user(t, 300);
    if (len < 0) return __real_GetTempPathW(n, buf);
    SHCreateDirectoryExW(0, t, NULL);
    if (!buf || (DWORD)len + 1 > n) return (DWORD)len + 1;
    memcpy(buf, t, ((size_t)len + 1) * sizeof(WCHAR));
    return (DWORD)len;
}
