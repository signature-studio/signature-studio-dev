/* shell32 / shlwapi / SHFolder / version / propsys(一部) / comdlg32 / winspool / oleacc / msacm32 / wtsapi32。
 * 方針: ブラウザ内に存在しないシステム機能は「無い/キャンセル」を意味するエラーを返す (fail-fast にはしない)。
 * 実体が要るもの (ShellExecute のブラウザ起動, ファイル選択ダイアログ) は下流のフック口のみ。
 */
#include "shimx_internal.h"
#include <strings.h>
#include <ctype.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>

extern DWORD g_shx_fv_ms, g_shx_fv_ls;

/* ---------------------------------------------------------------
 * 特殊フォルダ
 * --------------------------------------------------------------- */
static const char* csidl_path(int csidl) {
    switch (csidl & 0xFF) {
        case 0x00: case 0x10: return "C:\\Users\\webstudio\\Desktop";
        case 0x05: return "C:\\Users\\webstudio\\Documents";
        case 0x0D: return "C:\\Users\\webstudio\\Music";
        case 0x0E: return "C:\\Users\\webstudio\\Videos";
        case 0x27: return "C:\\Users\\webstudio\\Pictures";
        case 0x1A: return "C:\\Users\\webstudio\\AppData\\Roaming";
        case 0x1C: return "C:\\Users\\webstudio\\AppData\\Local";
        case 0x23: return "C:\\ProgramData";
        case 0x2E: return "C:\\Users\\Public\\Documents";
        case 0x28: return "C:\\Users\\webstudio";
        case 0x24: return "C:\\Windows";
        case 0x25: return "C:\\Windows\\System32";
        case 0x26: return "C:\\Program Files";
        case 0x2A: return "C:\\Program Files (x86)";
        case 0x2B: return "C:\\Program Files\\Common Files";
        case 0x14: return "C:\\Windows\\Fonts";
        case 0x15: return "C:\\Users\\webstudio\\AppData\\Roaming\\Microsoft\\Windows\\Templates";
        case 0x02: return "C:\\Users\\webstudio\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs";
        case 0x0B: return "C:\\Users\\webstudio\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu";
        case 0x07: return "C:\\Users\\webstudio\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup";
        case 0x20: return "C:\\Users\\webstudio\\AppData\\Local\\Microsoft\\Windows\\INetCache";
        case 0x19: return "C:\\Users\\Public\\Desktop";
        case 0x35: return "C:\\Users\\Public\\Music";
        default: return NULL;
    }
}
static void mk_win_dir(const char* win) {
    char px[2048], t[2048];
    if (shimx_path_to_posix(win, px, sizeof px) < 0) return;
    snprintf(t, sizeof t, "%s", px);
    for (char* p = t + 1; *p; p++) if (*p == '/') { *p = 0; mkdir(t, 0755); *p = '/'; }
    mkdir(t, 0755);
}
HRESULT SHGetFolderPathW(HWND w, int csidl, HANDLE tok, DWORD flags, LPWSTR path) {
    (void)w; (void)tok; (void)flags;
    shx_ensure_init();
    const char* p = csidl_path(csidl);
    if (!p || !path) return E_INVALIDARG;
    if (csidl & 0x8000) mk_win_dir(p);          /* CSIDL_FLAG_CREATE */
    int n = shimx_utf8_to_utf16(p, -1, path, MAX_PATH - 1);
    path[n < 0 ? 0 : n] = 0;
    return S_OK;
}

typedef struct { GUID id; const char* path; } KnownFolder;
#define G(a,b,c,d0,d1,d2,d3,d4,d5,d6,d7) {a,b,c,{d0,d1,d2,d3,d4,d5,d6,d7}}
static const KnownFolder k_known[] = {
    { G(0x3EB685DB,0x65F9,0x4CF6,0xA0,0x3A,0xE3,0xEF,0x65,0x72,0x9F,0x3D), "C:\\Users\\webstudio\\AppData\\Roaming" },
    { G(0xF1B32785,0x6FBA,0x4FCF,0x9D,0x55,0x7B,0x8E,0x7F,0x15,0x70,0x91), "C:\\Users\\webstudio\\AppData\\Local" },
    { G(0xFDD39AD0,0x238F,0x46AF,0xAD,0xB4,0x6C,0x85,0x48,0x03,0x69,0xC7), "C:\\Users\\webstudio\\Documents" },
    { G(0x62AB5D82,0xFDC1,0x4DC3,0xA9,0xDD,0x07,0x0D,0x1D,0x49,0x5D,0x97), "C:\\ProgramData" },
    { G(0xB4BFCC3A,0xDB2C,0x424C,0xB0,0x29,0x7F,0xE9,0x9A,0x87,0xC6,0x41), "C:\\Users\\webstudio\\Desktop" },
    { G(0x4BD8D571,0x6D19,0x48D3,0xBE,0x97,0x42,0x22,0x20,0x08,0x0E,0x43), "C:\\Users\\webstudio\\Music" },
    { G(0x905E63B6,0xC1BF,0x494E,0xB2,0x9C,0x65,0xB7,0x32,0xD3,0xD2,0x1A), "C:\\Program Files" },
    { G(0xF38BF404,0x1D43,0x42F2,0x93,0x05,0x67,0xDE,0x0B,0x28,0xFC,0x23), "C:\\Windows" },
    { G(0x5E6C858F,0x0E22,0x4760,0x9A,0xFE,0xEA,0x33,0x17,0xB6,0x71,0x73), "C:\\Users\\webstudio" },
};
HRESULT SHGetKnownFolderPath(const GUID* id, DWORD flags, HANDLE tok, LPWSTR* out) {
    (void)tok;
    shx_ensure_init();
    if (!id || !out) return E_INVALIDARG;
    *out = NULL;
    for (size_t i = 0; i < sizeof k_known / sizeof k_known[0]; i++) {
        if (!IsEqualGUID(id, &k_known[i].id)) continue;
        if (flags & 0x8000u /* KF_FLAG_CREATE */) mk_win_dir(k_known[i].path);
        WCHAR* w = shx_wcsdup_utf8(k_known[i].path);
        size_t n = (size_t)shx_wstr_len(w) + 1;
        WCHAR* c = (WCHAR*)CoTaskMemAlloc(n * 2);
        memcpy(c, w, n * 2); free(w);
        *out = c;
        return S_OK;
    }
    return (HRESULT)0x80070002;     /* HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND) */
}

/* PIDL: [uint16 cb][UTF-16 path + NUL][uint16 0] の自前形式 (往復のみ有効) */
static void* pidl_make(const WCHAR* path) {
    size_t n = (size_t)shx_wstr_len(path) + 1;
    uint8_t* p = (uint8_t*)CoTaskMemAlloc(2 + n * 2 + 2);
    if (!p) return NULL;
    *(uint16_t*)p = (uint16_t)(2 + n * 2);
    memcpy(p + 2, path, n * 2);
    *(uint16_t*)(p + 2 + n * 2) = 0;
    return p;
}
HRESULT SHGetSpecialFolderLocation(HWND w, int csidl, LPVOID* pidl) {
    WCHAR buf[MAX_PATH];
    HRESULT hr = SHGetFolderPathW(w, csidl, 0, 0, buf);
    if (FAILED(hr)) return hr;
    *pidl = pidl_make(buf);
    return *pidl ? S_OK : E_OUTOFMEMORY;
}
LPVOID ILCreateFromPathW(LPCWSTR path) { return path ? pidl_make(path) : NULL; }
void ILFree(LPVOID pidl) { CoTaskMemFree(pidl); }

/* R3: shell32 序数 16/17/18/19/21/25/152/153/155 (= IL* PIDL 操作系, Win10/11 の序数表)。
 * shimx 自前 PIDL 形式 ([u16 cb][UTF-16 path+NUL][u16 0]) の単項 + 終端で実装する。
 * ILGetNext/ILFindLastID は「1 項目しか無いリスト」としての正しい答えを返す。 */
static size_t pidl_total(const void* pidl) {           /* 終端含む総バイト数 */
    size_t tot = 0;
    const uint8_t* p = (const uint8_t*)pidl;
    if (!p) return 0;
    while (*(const uint16_t*)p) {
        uint16_t cb = *(const uint16_t*)p;
        if (cb < 4) break;
        tot += cb;
        p += cb;
    }
    return tot + 2;                                    /* 終端 [u16 0] */
}
LPVOID ILGetNext(const void* pidl) {
    if (!pidl) return NULL;
    uint16_t cb = *(const uint16_t*)pidl;
    if (cb < 4) return NULL;                           /* 空または終端 */
    const uint8_t* next = (const uint8_t*)pidl + cb;
    return *(const uint16_t*)next ? (LPVOID)next : NULL;
}
LPVOID ILFindLastID(const void* pidl) {
    /* 最終項目の先頭。空リストは NULL。単項リストでは pidl 自身 */
    if (!pidl || !*(const uint16_t*)pidl) return NULL;
    const uint8_t* last = (const uint8_t*)pidl;
    const uint8_t* p = last;
    while (*(const uint16_t*)p) {
        uint16_t cb = *(const uint16_t*)p;
        if (cb < 4) break;
        last = p;
        p += cb;
    }
    return (LPVOID)last;
}
BOOL ILRemoveLastID(void* pidl) {
    /* 最終項目を除去 (in place)。空リストは FALSE。単項リスト → 空リスト化 */
    uint8_t* last = (uint8_t*)ILFindLastID(pidl);
    if (!last || !*(uint16_t*)last) return FALSE;
    *(uint16_t*)last = 0;
    return TRUE;
}
LPVOID ILClone(const void* pidl) {
    if (!pidl) return NULL;
    size_t n = pidl_total(pidl);
    void* c = CoTaskMemAlloc(n);
    if (!c) return NULL;
    memcpy(c, pidl, n);
    return c;
}
LPVOID ILCloneFirst(const void* pidl) {
    if (!pidl || *(const uint16_t*)pidl < 4) return NULL;
    uint16_t cb = *(const uint16_t*)pidl;
    void* c = CoTaskMemAlloc((size_t)cb + 2);
    if (!c) return NULL;
    memcpy(c, pidl, cb);
    *(uint16_t*)((uint8_t*)c + cb) = 0;
    return c;
}
BOOL ILIsEqual(const void* a, const void* b) {
    if (!a || !b) return a == b;
    size_t na = pidl_total(a), nb = pidl_total(b);
    return na == nb && (na == 2 || memcmp(a, b, na) == 0);
}
LPVOID ILCombine(const void* a, const void* b) {
    if (!a) return ILClone(b);
    if (!b) return ILClone(a);
    size_t na = pidl_total(a);                         /* 終端含む */
    size_t nb = pidl_total(b);                         /* b は終端抜きで連結 */
    uint8_t* c = (uint8_t*)CoTaskMemAlloc(na + nb - 2);
    if (!c) return NULL;
    memcpy(c, a, na - 2);                              /* a の項目群 (終端除く) */
    memcpy(c + na - 2, b, nb);                         /* b 全体 (項目群+終端) */
    return c;
}
UINT ILGetSize(const void* pidl) {
    return pidl ? (UINT)pidl_total(pidl) : 0;          /* 終端含むバイト数 (Win32 同様) */
}
BOOL SHGetPathFromIDListW(const void* pidl, LPWSTR path) {
    if (!pidl || !path) return FALSE;
    const uint8_t* p = (const uint8_t*)pidl;
    uint16_t cb = *(const uint16_t*)p;
    if (cb < 4 || *(const uint16_t*)(p + cb) != 0) return FALSE;
    size_t n = (cb - 2) / 2;
    if (n > MAX_PATH) return FALSE;
    memcpy(path, p + 2, n * 2);
    return TRUE;
}
HRESULT SHGetDesktopFolder(LPVOID* out) { if (out) *out = NULL; return E_NOTIMPL; }
HRESULT SHCreateItemFromParsingName(LPCWSTR p, LPVOID bc, const GUID* iid, LPVOID* out) { (void)p; (void)bc; (void)iid; if (out) *out = NULL; return E_NOTIMPL; }
HRESULT SHOpenFolderAndSelectItems(LPVOID pidl, UINT n, LPVOID* ch, DWORD fl) { (void)pidl; (void)n; (void)ch; (void)fl; return S_OK; }

int SHCreateDirectoryExW(HWND w, LPCWSTR path, LPVOID sa) {
    (void)w; (void)sa;
    char px[2048];
    if (shx_wpath_to_posix(path, px, sizeof px) < 0) return ERROR_BAD_PATHNAME;
    struct stat st;
    if (stat(px, &st) == 0) return S_ISDIR(st.st_mode) ? (int)ERROR_ALREADY_EXISTS : (int)ERROR_FILE_EXISTS;
    char t[2048]; snprintf(t, sizeof t, "%s", px);
    for (char* p = t + 1; *p; p++) if (*p == '/') { *p = 0; mkdir(t, 0755); *p = '/'; }
    if (mkdir(t, 0755) != 0 && errno != EEXIST) return (int)ERROR_PATH_NOT_FOUND;
    return 0;
}

/* ---- SHFileOperationW (Win64 SHFILEOPSTRUCTW: pFrom@16 pTo@24 flags@32 aborted@36, wFunc@8) ---- */
static int rm_rf(const char* p) {
    struct stat st;
    if (lstat(p, &st) != 0) return -1;
    if (S_ISDIR(st.st_mode)) {
        DIR* d = opendir(p);
        if (d) {
            struct dirent* de;
            while ((de = readdir(d))) {
                if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, "..")) continue;
                char c[2600]; snprintf(c, sizeof c, "%s/%s", p, de->d_name);
                rm_rf(c);
            }
            closedir(d);
        }
        return rmdir(p);
    }
    return unlink(p);
}
static int cp_rf(const char* from, const char* to) {
    struct stat st;
    if (stat(from, &st) != 0) return -1;
    if (S_ISDIR(st.st_mode)) {
        mkdir(to, 0755);
        DIR* d = opendir(from);
        if (!d) return -1;
        struct dirent* de;
        while ((de = readdir(d))) {
            if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, "..")) continue;
            char a[2600], b[2600]; snprintf(a, sizeof a, "%s/%s", from, de->d_name); snprintf(b, sizeof b, "%s/%s", to, de->d_name);
            cp_rf(a, b);
        }
        closedir(d);
        return 0;
    }
    int fi = open(from, O_RDONLY), fo = open(to, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fi < 0 || fo < 0) { if (fi >= 0) close(fi); if (fo >= 0) close(fo); return -1; }
    char buf[8192]; ssize_t r;
    while ((r = read(fi, buf, sizeof buf)) > 0) if (write(fo, buf, (size_t)r) != r) break;
    close(fi); close(fo);
    return 0;
}
int SHFileOperationW(void* op) {
    uint8_t* o = (uint8_t*)op;
    DWORD func = *(uint32_t*)(o + 8);
    const WCHAR* from = (const WCHAR*)(uintptr_t)*(uint64_t*)(o + 16);
    const WCHAR* to = (const WCHAR*)(uintptr_t)*(uint64_t*)(o + 24);
    *(uint32_t*)(o + 36) = 0;
    if (!from) return 0x402;
    char dest[2048] = "";
    if (to && func != 3 && shx_wpath_to_posix(to, dest, sizeof dest) < 0) return 0x7C;
    struct stat dst; int destIsDir = (dest[0] && stat(dest, &dst) == 0 && S_ISDIR(dst.st_mode));
    int err = 0;
    for (const WCHAR* f = from; *f; f += shx_wstr_len(f) + 1) {
        char src[2048];
        if (shx_wpath_to_posix(f, src, sizeof src) < 0) { err = 0x7C; break; }
        struct stat s;
        if (stat(src, &s) != 0) { err = 0x402; break; }
        const char* base = strrchr(src, '/'); base = base ? base + 1 : src;
        char target[2700];
        if (func != 3) snprintf(target, sizeof target, "%s%s%s", dest, destIsDir ? "/" : "", destIsDir ? base : "");
        if (func == 3) { if (rm_rf(src) != 0) { err = 0x7C; break; } }
        else if (func == 2) { if (cp_rf(src, target) != 0) { err = 0x7C; break; } }
        else if (func == 1 || func == 4) { if (rename(src, target) != 0) { err = 0x7C; break; } }
        else { err = 0x7C; break; }
    }
    return err;
}
void SHAddToRecentDocs(UINT flags, LPCVOID pv) { (void)flags; (void)pv; }
UINT_PTR_T SHAppBarMessage(DWORD msg, void* data) { (void)msg; (void)data; return 0; }
static volatile uint32_t g_notify_id;
ULONG SHChangeNotifyRegister(HWND w, int src, LONG events, UINT msg, int n, const void* entries) {
    (void)w; (void)src; (void)events; (void)msg; (void)n; (void)entries;
    return __atomic_add_fetch(&g_notify_id, 1u, __ATOMIC_SEQ_CST);
}
BOOL SHChangeNotifyDeregister(ULONG id) { (void)id; return TRUE; }
BOOL Shell_NotifyIconW(DWORD msg, void* data) { (void)msg; (void)data; return FALSE; }

/* ---- Drag&Drop (shell32; #172 SHX-T5) ----
 * DragAcceptFiles は受付ウィンドウ表を持つ (gui が shimx_drag_accepts で引く)。HDROP は DROPFILES ブロック
 * (pFiles@0 pt@4 fNC@12 fWide@16 + UTF-16 二重 NUL 列) への不透明ハンドルで、gui が shimx_hdrop_create で作り
 * WM_DROPFILES の wParam に載せる。DragFinish で解放。登録外ハンドルは 0/FALSE を返す (Windows の無効ハンドル相当)。 */
#define DA_MAX 64
#define HD_MAX 64
static HWND g_da[DA_MAX];
static struct { uint8_t* blk; DWORD nfiles; } g_hd[HD_MAX];
void DragAcceptFiles(HWND w, BOOL a) {
    if (!w) return;
    shx_lock();
    int slot = -1;
    for (int i = 0; i < DA_MAX; i++) {
        if (g_da[i] == w) { slot = i; break; }
        if (!g_da[i] && slot < 0) slot = i;
    }
    if (slot >= 0) g_da[slot] = a ? w : 0;
    shx_unlock();
}
int shimx_drag_accepts(HWND w) {
    int r = 0;
    shx_lock();
    for (int i = 0; i < DA_MAX && !r; i++) r = (g_da[i] == w && w);
    shx_unlock();
    return r;
}
HANDLE shimx_hdrop_create(const WCHAR* const* wpaths, DWORD n, int x, int y, int nc) {
    size_t chars = 1;
    for (DWORD i = 0; i < n; i++) chars += (size_t)shx_wstr_len(wpaths[i]) + 1;
    uint8_t* b = (uint8_t*)calloc(1, 20 + chars * 2);
    if (!b) return 0;
    ((uint32_t*)b)[0] = 20; ((int32_t*)b)[1] = x; ((int32_t*)b)[2] = y; ((uint32_t*)b)[3] = nc ? 1u : 0u; ((uint32_t*)b)[4] = 1u;
    WCHAR* d = (WCHAR*)(b + 20);
    for (DWORD i = 0; i < n; i++) { size_t l = (size_t)shx_wstr_len(wpaths[i]) + 1; memcpy(d, wpaths[i], l * 2); d += l; }
    HANDLE h = 0;
    shx_lock();
    for (int i = 0; i < HD_MAX; i++) if (!g_hd[i].blk) { g_hd[i].blk = b; g_hd[i].nfiles = n; h = (HANDLE)(uintptr_t)b; break; }
    shx_unlock();
    if (!h) free(b);
    return h;
}
static uint8_t* hdrop_find(HANDLE d, DWORD* n) {
    uint8_t* r = NULL;
    shx_lock();
    for (int i = 0; i < HD_MAX; i++) if (g_hd[i].blk && (uintptr_t)g_hd[i].blk == (uintptr_t)d) { r = g_hd[i].blk; if (n) *n = g_hd[i].nfiles; break; }
    shx_unlock();
    return r;
}
void DragFinish(HANDLE d) {
    uint8_t* b = NULL;
    shx_lock();
    for (int i = 0; i < HD_MAX; i++) if (g_hd[i].blk && (uintptr_t)g_hd[i].blk == (uintptr_t)d) { b = g_hd[i].blk; g_hd[i].blk = NULL; g_hd[i].nfiles = 0; break; }
    shx_unlock();
    free(b);
}
UINT DragQueryFileW(HANDLE d, UINT i, LPWSTR buf, UINT cch) {
    DWORD n = 0;
    uint8_t* b = hdrop_find(d, &n);
    if (!b) return 0;
    if (i == 0xFFFFFFFFu) return n;
    if (i >= n) return 0;
    const WCHAR* p = (const WCHAR*)(b + *(uint32_t*)b);
    for (UINT k = 0; k < i; k++) p += shx_wstr_len(p) + 1;
    UINT len = (UINT)shx_wstr_len(p);
    if (!buf) return len;
    if (!cch) return 0;
    UINT c = len < cch - 1 ? len : cch - 1;
    memcpy(buf, p, (size_t)c * 2);
    buf[c] = 0;
    return c;
}
BOOL DragQueryPoint(HANDLE d, void* pt) {
    uint8_t* b = hdrop_find(d, NULL);
    if (!b || !pt) return FALSE;
    memcpy(pt, b + 4, 8);
    return !((uint32_t*)b)[3];   /* fNC=0 (クライアント領域) なら TRUE */
}

/* ---- ShellExecute: ブラウザ起動などは下流フックへ ---- */
static int (*g_shexec_hook)(const char*, const char*, const char*);
void shimx_set_shell_execute_hook(int (*fn)(const char*, const char*, const char*)) { g_shexec_hook = fn; }
static HINSTANCE do_shexec(const WCHAR* verb, const WCHAR* file, const WCHAR* params) {
    char v[64] = "open", f[1024] = "", p[1024] = "";
    if (verb) shimx_utf16_to_utf8(verb, -1, v, sizeof v);
    if (file) shimx_utf16_to_utf8(file, -1, f, sizeof f);
    if (params) shimx_utf16_to_utf8(params, -1, p, sizeof p);
    SHX_TRACE("ShellExecute(%s, %s, %s)", v, f, p);
    if (g_shexec_hook && g_shexec_hook(v, f, p)) return (HINSTANCE)33;
    SetLastError(ERROR_FILE_NOT_FOUND);
    return (HINSTANCE)2;          /* SE_ERR_FNF */
}
HINSTANCE ShellExecuteW(HWND w, LPCWSTR op, LPCWSTR file, LPCWSTR params, LPCWSTR dir, int show) {
    (void)w; (void)dir; (void)show; return do_shexec(op, file, params);
}
HINSTANCE ShellExecuteA(HWND w, LPCSTR op, LPCSTR file, LPCSTR params, LPCSTR dir, int show) {
    (void)w; (void)dir; (void)show;
    WCHAR a[64] = {0}, b[1024] = {0}, c[1024] = {0};
    if (op) MultiByteToWideChar(CP_ACP, 0, op, -1, a, 64);
    if (file) MultiByteToWideChar(CP_ACP, 0, file, -1, b, 1024);
    if (params) MultiByteToWideChar(CP_ACP, 0, params, -1, c, 1024);
    return do_shexec(op ? a : NULL, file ? b : NULL, params ? c : NULL);
}
BOOL ShellExecuteExW(void* info) {
    uint8_t* i = (uint8_t*)info;       /* Win64 SHELLEXECUTEINFOW: lpVerb@16 lpFile@24 lpParameters@32 hInstApp@56 hProcess@104 */
    HINSTANCE r = do_shexec((const WCHAR*)(uintptr_t)*(uint64_t*)(i + 16), (const WCHAR*)(uintptr_t)*(uint64_t*)(i + 24),
                            (const WCHAR*)(uintptr_t)*(uint64_t*)(i + 32));
    *(uint64_t*)(i + 56) = (uint64_t)(uintptr_t)r;
    *(uint64_t*)(i + 104) = 0;
    return (uintptr_t)r > 32;
}

/* ---- shlwapi: PathUnExpandEnvStringsW ---- */
BOOL PathUnExpandEnvStringsW(LPCWSTR path, LPWSTR out, UINT cch) {
    static const char* const vars[] = { "SystemRoot", "ProgramFiles(x86)", "ProgramFiles", "CommonProgramFiles", "ProgramData",
        "LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "SystemDrive" };
    const char* bestVar = NULL; size_t bestLen = 0;
    char p8[2048];
    if (!path || shimx_utf16_to_utf8(path, -1, p8, sizeof p8) < 0) return FALSE;
    for (size_t i = 0; i < sizeof vars / sizeof vars[0]; i++) {
        WCHAR wn[64], wv[1024];
        int k = shimx_utf8_to_utf16(vars[i], -1, wn, 63); wn[k] = 0;
        DWORD n = GetEnvironmentVariableW(wn, wv, 1024);
        if (!n || n >= 1024) continue;
        char v8[2048]; shimx_utf16_to_utf8(wv, -1, v8, sizeof v8);
        size_t vl = strlen(v8);
        if (vl > bestLen && !strncasecmp(p8, v8, vl) && (p8[vl] == '\\' || p8[vl] == 0)) { bestVar = vars[i]; bestLen = vl; }
    }
    char res[2200];
    if (bestVar) snprintf(res, sizeof res, "%%%s%%%s", bestVar, p8 + bestLen); else snprintf(res, sizeof res, "%s", p8);
    WCHAR* w = shx_wcsdup_utf8(res);
    int len = shx_wstr_len(w);
    if ((UINT)len + 1 <= cch && out) memcpy(out, w, ((size_t)len + 1) * 2);
    free(w);
    return bestVar != NULL;
}

/* ---------------------------------------------------------------
 * version.dll: 合成バージョン情報 (FL ファイル版 + 固定文字列)。構造は不透明 (不変条件: GetFileVersionInfoW → VerQueryValueW のみで解釈)
 * --------------------------------------------------------------- */
typedef struct { uint32_t magic, total; uint32_t ffi[13]; uint32_t trans; } VerHdr;   /* 8+52+4 = 64B */
static const char* const k_vstr[][2] = {
    { "CompanyName", "Image-Line" }, { "FileDescription", "FL Studio" }, { "ProductName", "FL Studio" },
    { "InternalName", "FL Studio" }, { "LegalCopyright", "Copyright Image-Line" }, { "OriginalFilename", "FL64.exe" },
};
static size_t ver_blob_size(void) {
    size_t n = sizeof(VerHdr);
    for (size_t i = 0; i < sizeof k_vstr / sizeof k_vstr[0]; i++) n += 4 + (strlen(k_vstr[i][0]) + 1 + strlen(k_vstr[i][1]) + 1) * 2;
    n += 2 * (2 * 28 + 4);   /* FileVersion / ProductVersion */
    return n + 4;
}
static int file_exists_w(LPCWSTR f) {
    if (!f) return 0;
    if (GetFileAttributesW(f) != INVALID_FILE_ATTRIBUTES) return 1;
    return 0;
}
DWORD GetFileVersionInfoSizeW(LPCWSTR file, LPDWORD handle) {
    if (handle) *handle = 0;
    if (!file_exists_w(file)) { SetLastError(ERROR_FILE_NOT_FOUND); return 0; }
    return (DWORD)ver_blob_size();
}
static uint8_t* ver_put(uint8_t* p, const char* k, const char* v) {
    uint16_t kl = (uint16_t)(strlen(k) + 1), vl = (uint16_t)(strlen(v) + 1);
    *(uint16_t*)p = kl; p += 2;
    for (int i = 0; i < kl; i++) { *(uint16_t*)p = (uint16_t)(unsigned char)k[i]; p += 2; }
    *(uint16_t*)p = vl; p += 2;
    for (int i = 0; i < vl; i++) { *(uint16_t*)p = (uint16_t)(unsigned char)v[i]; p += 2; }
    return p;
}
BOOL GetFileVersionInfoW(LPCWSTR file, DWORD handle, DWORD len, LPVOID data) {
    (void)handle;
    if (!file_exists_w(file)) { SetLastError(ERROR_FILE_NOT_FOUND); return FALSE; }
    size_t need = ver_blob_size();
    if (!data || len < need) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return FALSE; }
    memset(data, 0, need);
    VerHdr* h = (VerHdr*)data;
    h->magic = 0x56584853u; h->total = (uint32_t)need;
    h->ffi[0] = 0xFEEF04BDu; h->ffi[1] = 0x10000;
    h->ffi[2] = g_shx_fv_ms; h->ffi[3] = g_shx_fv_ls; h->ffi[4] = g_shx_fv_ms; h->ffi[5] = g_shx_fv_ls;
    h->ffi[6] = 0x3F; h->ffi[7] = 0; h->ffi[8] = 0x40004; h->ffi[9] = 1; h->ffi[10] = 0;
    h->trans = 0x04B00409u;
    uint8_t* p = (uint8_t*)data + sizeof(VerHdr);
    char fv[48]; snprintf(fv, sizeof fv, "%u.%u.%u.%u", g_shx_fv_ms >> 16, g_shx_fv_ms & 0xFFFF, g_shx_fv_ls >> 16, g_shx_fv_ls & 0xFFFF);
    for (size_t i = 0; i < sizeof k_vstr / sizeof k_vstr[0]; i++) p = ver_put(p, k_vstr[i][0], k_vstr[i][1]);
    p = ver_put(p, "FileVersion", fv);
    p = ver_put(p, "ProductVersion", fv);
    *(uint16_t*)p = 0;
    return TRUE;
}
BOOL VerQueryValueW(LPCVOID block, LPCWSTR sub, LPVOID* buf, UINT* len) {
    const VerHdr* h = (const VerHdr*)block;
    if (!h || h->magic != 0x56584853u || !sub || !buf) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    char s[256]; int i = 0;
    for (; sub[i] && i < 255; i++) s[i] = (char)sub[i];
    s[i] = 0;
    if (!strcmp(s, "\\") ) { *buf = (void*)h->ffi; if (len) *len = 52; return TRUE; }
    if (!strcasecmp(s, "\\VarFileInfo\\Translation")) { *buf = (void*)&h->trans; if (len) *len = 4; return TRUE; }
    const char* pre = "\\StringFileInfo\\";
    if (!strncasecmp(s, pre, strlen(pre))) {
        const char* r = s + strlen(pre);
        const char* sl = strchr(r, '\\');
        if (sl) {
            const char* key = sl + 1;
            const uint8_t* p = (const uint8_t*)block + sizeof(VerHdr);
            while (*(const uint16_t*)p) {
                uint16_t kl = *(const uint16_t*)p; const uint16_t* kw = (const uint16_t*)(p + 2);
                const uint16_t* vlp = kw + kl; uint16_t vl = *vlp; const uint16_t* vw = vlp + 1;
                int eq = (int)strlen(key) + 1 == kl;
                for (int k = 0; eq && k < kl; k++) if (tolower((unsigned char)key[k]) != tolower((int)kw[k])) eq = 0;
                if (eq) { *buf = (void*)vw; if (len) *len = vl; return TRUE; }
                p = (const uint8_t*)(vw + vl);
            }
        }
    }
    SetLastError(ERROR_RESOURCE_TYPE_NOT_FOUND);
    return FALSE;
}

/* ---------------------------------------------------------------
 * comdlg32 / winspool / oleacc / wtsapi32 / propsys / msacm32 : 「無い・キャンセル」スタブ
 * --------------------------------------------------------------- */
BOOL GetOpenFileNameW(LPVOID ofn) { (void)ofn; SHX_TRACE("GetOpenFileNameW: ファイル選択 UI は未接続 → キャンセル扱い"); return FALSE; }
BOOL GetSaveFileNameW(LPVOID ofn) { (void)ofn; SHX_TRACE("GetSaveFileNameW: ファイル選択 UI は未接続 → キャンセル扱い"); return FALSE; }
DWORD CommDlgExtendedError(void) { return 0; }

BOOL OpenPrinterW(LPWSTR name, LPHANDLE h, LPVOID def) { (void)name; (void)def; if (h) *h = 0; SetLastError(1801 /* ERROR_INVALID_PRINTER_NAME */); return FALSE; }
BOOL ClosePrinter(HANDLE h) { (void)h; return TRUE; }
BOOL EnumPrintersW(DWORD flags, LPWSTR name, DWORD level, LPBYTE buf, DWORD n, LPDWORD needed, LPDWORD returned) {
    (void)flags; (void)name; (void)level; (void)buf; (void)n;
    if (needed) *needed = 0;
    if (returned) *returned = 0;
    return TRUE;
}
BOOL GetDefaultPrinterW(LPWSTR buf, LPDWORD n) { (void)buf; (void)n; SetLastError(ERROR_FILE_NOT_FOUND); return FALSE; }
LONG DocumentPropertiesW(HWND w, HANDLE h, LPWSTR dev, LPVOID out, LPVOID in, DWORD mode) { (void)w; (void)h; (void)dev; (void)out; (void)in; (void)mode; return 0; }

LRESULT_T LresultFromObject(const GUID* iid, LRESULT_T wp, LPVOID unk) { (void)iid; (void)wp; (void)unk; return (LRESULT_T)(uint32_t)E_NOTIMPL; }
/* weak: tools/gui が強定義で置換する (#172。両方 strong だと IR が宣言したとき wasm-ld の duplicate symbol になっていた) */
SHIMX_WEAK BOOL WTSRegisterSessionNotification(HWND w, DWORD flags) { (void)w; (void)flags; return TRUE; }
SHIMX_WEAK BOOL WTSUnRegisterSessionNotification(HWND w) { (void)w; return TRUE; }

const WCHAR* PropVariantToStringWithDefault(const void* pv, const WCHAR* def) {
    uint16_t vt = pv ? *(const uint16_t*)pv : 0;
    if (vt == 31 /* VT_LPWSTR */ || vt == 8 /* VT_BSTR */) { const WCHAR* s = (const WCHAR*)(uintptr_t)*(const uint64_t*)((const uint8_t*)pv + 8); if (s) return s; }
    return def;
}
BOOL PropVariantToBooleanWithDefault(const void* pv, BOOL def) {
    if (pv && *(const uint16_t*)pv == 11) return *(const int16_t*)((const uint8_t*)pv + 8) != 0;
    return def;
}
HRESULT PropVariantToFileTime(const void* pv, int type, FILETIME* ft) { (void)pv; (void)type; (void)ft; return E_NOTIMPL; }
HRESULT PropVariantToVariant(const void* pv, void* v) { (void)pv; (void)v; return E_NOTIMPL; }
HRESULT VariantToPropVariant(const void* v, void* pv) { (void)v; (void)pv; return E_NOTIMPL; }

/* msacm32: ACM ドライバ無し */
#define MMSYSERR_INVALHANDLE 5u
#define MMSYSERR_NODRIVER 6u
#define ACMERR_NOTPOSSIBLE 0x200u
#define ACMERR_CANCELED 0x203u
UINT acmMetrics(uint64_t h, UINT metric, LPVOID out) { (void)h; (void)metric; if (out) *(DWORD*)out = 0; return 0; }
UINT acmDriverEnum(LPVOID cb, ULONG_PTR dw, DWORD flags) { (void)cb; (void)dw; (void)flags; return 0; }
UINT acmDriverOpen(LPHANDLE h, HANDLE id, DWORD flags) { (void)id; (void)flags; if (h) *h = 0; return MMSYSERR_NODRIVER; }
UINT acmDriverClose(HANDLE h, DWORD flags) { (void)h; (void)flags; return MMSYSERR_INVALHANDLE; }
UINT acmDriverDetailsA(HANDLE h, LPVOID d, DWORD flags) { (void)h; (void)d; (void)flags; return MMSYSERR_INVALHANDLE; }
UINT acmFormatChooseW(LPVOID p) { (void)p; return ACMERR_CANCELED; }
UINT acmFormatSuggest(HANDLE h, LPVOID src, LPVOID dst, DWORD n, DWORD flags) { (void)h; (void)src; (void)dst; (void)n; (void)flags; return ACMERR_NOTPOSSIBLE; }
UINT acmStreamOpen(LPHANDLE h, HANDLE drv, LPVOID src, LPVOID dst, LPVOID flt, ULONG_PTR cb, ULONG_PTR inst, DWORD flags) {
    (void)drv; (void)src; (void)dst; (void)flt; (void)cb; (void)inst; (void)flags; if (h) *h = 0; return ACMERR_NOTPOSSIBLE;
}
UINT acmStreamClose(HANDLE h, DWORD flags) { (void)h; (void)flags; return MMSYSERR_INVALHANDLE; }
UINT acmStreamConvert(HANDLE h, LPVOID hdr, DWORD flags) { (void)h; (void)hdr; (void)flags; return MMSYSERR_INVALHANDLE; }
UINT acmStreamMessage(HANDLE h, UINT msg, ULONG_PTR a, ULONG_PTR b) { (void)h; (void)msg; (void)a; (void)b; return MMSYSERR_INVALHANDLE; }
UINT acmStreamPrepareHeader(HANDLE h, LPVOID hdr, DWORD flags) { (void)h; (void)hdr; (void)flags; return MMSYSERR_INVALHANDLE; }
UINT acmStreamUnprepareHeader(HANDLE h, LPVOID hdr, DWORD flags) { (void)h; (void)hdr; (void)flags; return MMSYSERR_INVALHANDLE; }
UINT acmStreamSize(HANDLE h, DWORD n, LPDWORD out, DWORD flags) { (void)h; (void)n; (void)flags; if (out) *out = 0; return MMSYSERR_INVALHANDLE; }

/* SHGetFileInfoW: アイコン/種別情報は取得不可 → 0 (失敗) */
ULONG_PTR SHGetFileInfoW(LPCWSTR path, DWORD attrs, LPVOID info, UINT cb, UINT flags) {
    (void)path; (void)attrs; (void)cb; (void)flags;
    (void)info;
    return 0;
}

BOOL SHGetSpecialFolderPathW(HWND w, LPWSTR path, int csidl, BOOL create) {
    return SUCCEEDED(SHGetFolderPathW(w, create ? (csidl | 0x8000) : csidl, 0, 0, path));
}
BOOL ShellExecuteExA(void* info) {
    uint8_t* i = (uint8_t*)info;       /* Win64 SHELLEXECUTEINFOA: lpVerb@16 lpFile@24 lpParameters@32 hInstApp@56 hProcess@104 */
    HINSTANCE r = ShellExecuteA(0, (LPCSTR)(uintptr_t)*(uint64_t*)(i + 16), (LPCSTR)(uintptr_t)*(uint64_t*)(i + 24),
                                (LPCSTR)(uintptr_t)*(uint64_t*)(i + 32), NULL, 1);
    *(uint64_t*)(i + 56) = (uint64_t)(uintptr_t)r;
    *(uint64_t*)(i + 104) = 0;
    return (uintptr_t)r > 32;
}
HANDLE ExtractAssociatedIconW(HANDLE inst, LPWSTR path, WORD* idx) { (void)inst; (void)path; (void)idx; return 0; }
HRESULT SHCreateStreamOnFileEx(LPCWSTR path, DWORD mode, DWORD attrs, BOOL create, LPVOID tmpl, LPVOID* out) {
    (void)path; (void)mode; (void)attrs; (void)create; (void)tmpl; if (out) *out = NULL; return E_NOTIMPL;
}
