/* メモリ内レジストリ (advapi32 Reg*)。
 * - 5 ルート (HKCR/HKCU/HKLM/HKU/HKCC) の木構造。サブキーは名前順 (大小無視)、値は作成順で列挙
 * - 開いたキーは統一ハンドル表 (OBJ_KEY)。削除済みキーは ERROR_KEY_DELETED
 * - 既定値シード + `.reg` 風テキストの import/export (永続化は下流: IndexedDB 等)
 * 全操作を 1 本の mutex で保護 (呼出頻度が低いため)。
 */
#include "shimx_internal.h"
#include <ctype.h>

#define ERROR_KEY_DELETED 1018u
#define ERROR_UNSUPPORTED_TYPE 1630u

typedef struct RegVal {
    WCHAR* name; DWORD type; uint8_t* data; DWORD cb; struct RegVal* next;
} RegVal;
typedef struct RegKey {
    WCHAR* name; struct RegKey* parent; struct RegKey* child; struct RegKey* sibling;
    RegVal* vals; RegVal* vtail; int nvals, nsub; uint64_t mtime; int deleted;
} RegKey;

static shx_mutex_t g_reg_lk;
static RegKey* g_roots[5];
static const char* const k_root_names[5] = { "HKEY_CLASSES_ROOT", "HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE", "HKEY_USERS", "HKEY_CURRENT_CONFIG" };
static const char* const k_root_short[5] = { "HKCR", "HKCU", "HKLM", "HKU", "HKCC" };
static int g_reg_inited;

static uint64_t now_ft(void) { FILETIME ft; GetSystemTimeAsFileTime(&ft); return ((uint64_t)ft.dwHighDateTime << 32) | ft.dwLowDateTime; }
static WCHAR* wdup(const WCHAR* s, int n) {
    WCHAR* d = (WCHAR*)malloc(((size_t)n + 1) * 2);
    if (d) { memcpy(d, s, (size_t)n * 2); d[n] = 0; }
    return d;
}
static int wn(const WCHAR* a, int la, const WCHAR* b, int lb) {   /* 大小無視比較 (長さ指定) */
    int n = la < lb ? la : lb;
    for (int i = 0; i < n; i++) {
        uint32_t x = shimx_towlower(a[i]), y = shimx_towlower(b[i]);
        if (x != y) return x < y ? -1 : 1;
    }
    return la == lb ? 0 : (la < lb ? -1 : 1);
}

static RegKey* key_new(const WCHAR* name, int n, RegKey* parent) {
    RegKey* k = (RegKey*)calloc(1, sizeof(RegKey));
    k->name = wdup(name, n); k->parent = parent; k->mtime = now_ft();
    return k;
}
static RegKey* find_sub(RegKey* p, const WCHAR* name, int n) {
    for (RegKey* c = p->child; c; c = c->sibling)
        if (!c->deleted && wn(c->name, shx_wstr_len(c->name), name, n) == 0) return c;
    return NULL;
}
static RegKey* add_sub(RegKey* p, const WCHAR* name, int n) {
    RegKey* k = key_new(name, n, p);
    RegKey** pp = &p->child;
    while (*pp && wn((*pp)->name, shx_wstr_len((*pp)->name), name, n) < 0) pp = &(*pp)->sibling;
    k->sibling = *pp; *pp = k;
    p->nsub++; p->mtime = now_ft();
    return k;
}

/* 解決: hKey → RegKey* (shx_lock 不要, g_reg_lk 保持中に呼ぶ)。err を返す */
static RegKey* resolve(HKEY h, DWORD* err) {
    if (!g_reg_inited) shx_ensure_init();
    uint32_t v = (uint32_t)h;
    if (v >= 0x80000000u && v <= 0x80000005u && v != 0x80000004u) { *err = 0; return g_roots[v - 0x80000000u]; }
    ShxObj* o = shx_ref(h, OBJ_KEY);
    if (!o) { *err = ERROR_INVALID_HANDLE; return NULL; }
    RegKey* k = (RegKey*)o->node;
    shx_unref(o);
    if (!k || k->deleted) { *err = ERROR_KEY_DELETED; return NULL; }
    *err = 0;
    return k;
}

/* 相対パス (backslash 区切り) を辿る。create=1 で作成。*created に新規作成の有無 */
static RegKey* walk(RegKey* k, const WCHAR* sub, int create, int* created) {
    if (created) *created = 0;
    if (!sub) return k;
    while (*sub) {
        while (*sub == '\\') sub++;
        if (!*sub) break;
        const WCHAR* e = sub; while (*e && *e != '\\') e++;
        int n = (int)(e - sub);
        RegKey* c = find_sub(k, sub, n);
        if (!c) {
            if (!create) return NULL;
            c = add_sub(k, sub, n);
            if (created) *created = 1;
        }
        k = c; sub = e;
    }
    return k;
}

static HANDLE key_handle(RegKey* k) {
    ShxObj* o = shx_obj_new(OBJ_KEY);
    if (!o) return 0;
    o->node = k;
    return shx_handle_new(o);
}
void shx_key_destroy(ShxObj* o) { (void)o; }   /* RegKey 自体は木に残す */

static RegVal* find_val2(RegKey* k, const WCHAR* name) {
    int n = name ? shx_wstr_len(name) : 0;
    for (RegVal* v = k->vals; v; v = v->next)
        if (wn(v->name, shx_wstr_len(v->name), name, n) == 0) return v;
    return NULL;
}
static int set_val(RegKey* k, const WCHAR* name, DWORD type, const void* data, DWORD cb) {
    int n = name ? shx_wstr_len(name) : 0;
    RegVal* v = find_val2(k, name);
    uint8_t* d = (uint8_t*)malloc(cb ? cb : 1);
    if (!d) return -1;
    if (cb) memcpy(d, data, cb);
    if (!v) {
        v = (RegVal*)calloc(1, sizeof(RegVal));
        v->name = wdup(name ? name : (const WCHAR*)"\0", n);
        if (k->vtail) k->vtail->next = v; else k->vals = v;
        k->vtail = v; k->nvals++;
    } else free(v->data);
    v->type = type; v->data = d; v->cb = cb;
    k->mtime = now_ft();
    return 0;
}

/* ---------------------------------------------------------------
 * 公開 API (W)
 * --------------------------------------------------------------- */
LSTATUS RegOpenKeyExW(HKEY h, LPCWSTR sub, DWORD opt, REGSAM sam, PHKEY out) {
    (void)opt; (void)sam;
    if (!out) return ERROR_INVALID_PARAMETER;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* b = resolve(h, &err);
    if (!b) { shx_mutex_unlock(&g_reg_lk); return err; }
    RegKey* k = walk(b, sub, 0, NULL);
    shx_mutex_unlock(&g_reg_lk);
    if (!k) return ERROR_FILE_NOT_FOUND;
    if ((!sub || !*sub) && (uint32_t)h >= 0x80000000u) { *out = h; return ERROR_SUCCESS; }
    HANDLE nh = key_handle(k);
    if (!nh) return ERROR_NOT_ENOUGH_MEMORY;
    *out = nh;
    return ERROR_SUCCESS;
}
LSTATUS RegOpenKeyW(HKEY h, LPCWSTR sub, PHKEY out) { return RegOpenKeyExW(h, sub, 0, KEY_ALL_ACCESS, out); }

LSTATUS RegCreateKeyExW(HKEY h, LPCWSTR sub, DWORD rsv, LPWSTR cls, DWORD opt, REGSAM sam,
                        LPVOID sa, PHKEY out, LPDWORD disp) {
    (void)rsv; (void)cls; (void)opt; (void)sam; (void)sa;
    if (!out) return ERROR_INVALID_PARAMETER;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* b = resolve(h, &err);
    if (!b) { shx_mutex_unlock(&g_reg_lk); return err; }
    int created = 0;
    RegKey* k = walk(b, sub, 1, &created);
    shx_mutex_unlock(&g_reg_lk);
    if (disp) *disp = created ? REG_CREATED_NEW_KEY : REG_OPENED_EXISTING_KEY;
    HANDLE nh = key_handle(k);
    if (!nh) return ERROR_NOT_ENOUGH_MEMORY;
    *out = nh;
    return ERROR_SUCCESS;
}
LSTATUS RegCreateKeyW(HKEY h, LPCWSTR sub, PHKEY out) { return RegCreateKeyExW(h, sub, 0, NULL, 0, KEY_ALL_ACCESS, NULL, out, NULL); }

LSTATUS RegCloseKey(HKEY h) {
    uint32_t v = (uint32_t)h;
    if (v >= 0x80000000u && v <= 0x80000005u) return ERROR_SUCCESS;
    ShxObj* o = shx_ref(h, OBJ_KEY);
    if (!o) return ERROR_INVALID_HANDLE;
    shx_unref(o);
    CloseHandle(h);
    return ERROR_SUCCESS;
}
LSTATUS RegFlushKey(HKEY h) {
    shx_mutex_lock(&g_reg_lk); DWORD err; RegKey* k = resolve(h, &err); shx_mutex_unlock(&g_reg_lk);
    return k ? ERROR_SUCCESS : err;
}

static LSTATUS copy_out(const RegVal* v, LPDWORD type, LPBYTE data, LPDWORD cb) {
    if (type) *type = v->type;
    if (!cb) return data ? ERROR_INVALID_PARAMETER : ERROR_SUCCESS;
    if (!data) { *cb = v->cb; return ERROR_SUCCESS; }
    if (*cb < v->cb) { *cb = v->cb; return ERROR_MORE_DATA; }
    memcpy(data, v->data, v->cb);
    *cb = v->cb;
    return ERROR_SUCCESS;
}

LSTATUS RegQueryValueExW(HKEY h, LPCWSTR name, LPDWORD rsv, LPDWORD type, LPBYTE data, LPDWORD cb) {
    (void)rsv;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* k = resolve(h, &err);
    LSTATUS r;
    if (!k) r = err;
    else {
        RegVal* v = find_val2(k, name);
        r = v ? copy_out(v, type, data, cb) : ERROR_FILE_NOT_FOUND;
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}

LSTATUS RegSetValueExW(HKEY h, LPCWSTR name, DWORD rsv, DWORD type, const BYTE* data, DWORD cb) {
    (void)rsv;
    if (!data && cb) return ERROR_INVALID_PARAMETER;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* k = resolve(h, &err);
    LSTATUS r = k ? (set_val(k, name, type, data, cb) == 0 ? ERROR_SUCCESS : ERROR_NOT_ENOUGH_MEMORY) : err;
    shx_mutex_unlock(&g_reg_lk);
    return r;
}
LSTATUS RegDeleteValueW(HKEY h, LPCWSTR name) {
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* k = resolve(h, &err);
    LSTATUS r;
    if (!k) r = err;
    else {
        RegVal** pp = &k->vals; r = ERROR_FILE_NOT_FOUND;
        int n = name ? shx_wstr_len(name) : 0;
        while (*pp) {
            if (wn((*pp)->name, shx_wstr_len((*pp)->name), name, n) == 0) {
                RegVal* d = *pp; *pp = d->next;
                if (k->vtail == d) { k->vtail = NULL; for (RegVal* t = k->vals; t; t = t->next) k->vtail = t; }
                free(d->name); free(d->data); free(d); k->nvals--; r = ERROR_SUCCESS; break;
            }
            pp = &(*pp)->next;
        }
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}
LSTATUS RegDeleteKeyW(HKEY h, LPCWSTR sub) {
    if (!sub || !*sub) return ERROR_INVALID_PARAMETER;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* b = resolve(h, &err);
    LSTATUS r;
    if (!b) r = err;
    else {
        RegKey* k = walk(b, sub, 0, NULL);
        if (!k) r = ERROR_FILE_NOT_FOUND;
        else if (k->nsub > 0) r = ERROR_ACCESS_DENIED;
        else if (!k->parent) r = ERROR_ACCESS_DENIED;
        else {
            k->deleted = 1; k->parent->nsub--;
            RegKey** pp = &k->parent->child;
            while (*pp && *pp != k) pp = &(*pp)->sibling;
            if (*pp) *pp = k->sibling;
            r = ERROR_SUCCESS;
        }
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}
LSTATUS RegDeleteKeyExW(HKEY h, LPCWSTR sub, REGSAM sam, DWORD rsv) { (void)sam; (void)rsv; return RegDeleteKeyW(h, sub); }

static LSTATUS put_name(const WCHAR* src, LPWSTR dst, LPDWORD cch) {
    DWORD n = (DWORD)shx_wstr_len(src);
    if (!cch || !dst) return ERROR_INVALID_PARAMETER;
    if (*cch < n + 1) return ERROR_MORE_DATA;
    memcpy(dst, src, ((size_t)n + 1) * 2);
    *cch = n;
    return ERROR_SUCCESS;
}
LSTATUS RegEnumKeyExW(HKEY h, DWORD idx, LPWSTR name, LPDWORD cchName, LPDWORD rsv, LPWSTR cls,
                      LPDWORD cchCls, FILETIME* lw) {
    (void)rsv;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* k = resolve(h, &err);
    LSTATUS r;
    if (!k) r = err;
    else {
        RegKey* c = k->child; DWORD i = 0;
        while (c && i < idx) { c = c->sibling; i++; }
        if (!c) r = ERROR_NO_MORE_ITEMS;
        else {
            r = put_name(c->name, name, cchName);
            if (r == ERROR_SUCCESS) {
                if (cls && cchCls && *cchCls) cls[0] = 0;
                if (cchCls) *cchCls = 0;
                if (lw) { lw->dwLowDateTime = (DWORD)c->mtime; lw->dwHighDateTime = (DWORD)(c->mtime >> 32); }
            }
        }
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}
LSTATUS RegEnumValueW(HKEY h, DWORD idx, LPWSTR name, LPDWORD cchName, LPDWORD rsv, LPDWORD type,
                      LPBYTE data, LPDWORD cb) {
    (void)rsv;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* k = resolve(h, &err);
    LSTATUS r;
    if (!k) r = err;
    else {
        RegVal* v = k->vals; DWORD i = 0;
        while (v && i < idx) { v = v->next; i++; }
        if (!v) r = ERROR_NO_MORE_ITEMS;
        else {
            r = put_name(v->name, name, cchName);
            if (r == ERROR_SUCCESS) r = copy_out(v, type, data, cb);
        }
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}
LSTATUS RegQueryInfoKeyW(HKEY h, LPWSTR cls, LPDWORD cchCls, LPDWORD rsv, LPDWORD nSub, LPDWORD maxSub,
                         LPDWORD maxCls, LPDWORD nVal, LPDWORD maxValName, LPDWORD maxValData,
                         LPDWORD secDesc, FILETIME* lw) {
    (void)rsv; (void)cls;
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* k = resolve(h, &err);
    LSTATUS r = ERROR_SUCCESS;
    if (!k) r = err;
    else {
        DWORD ms = 0, mvn = 0, mvd = 0;
        for (RegKey* c = k->child; c; c = c->sibling) { DWORD l = (DWORD)shx_wstr_len(c->name); if (l > ms) ms = l; }
        for (RegVal* v = k->vals; v; v = v->next) { DWORD l = (DWORD)shx_wstr_len(v->name); if (l > mvn) mvn = l; if (v->cb > mvd) mvd = v->cb; }
        if (cchCls) *cchCls = 0;
        if (nSub) *nSub = (DWORD)k->nsub;
        if (maxSub) *maxSub = ms;
        if (maxCls) *maxCls = 0;
        if (nVal) *nVal = (DWORD)k->nvals;
        if (maxValName) *maxValName = mvn;
        if (maxValData) *maxValData = mvd;
        if (secDesc) *secDesc = 0;
        if (lw) { lw->dwLowDateTime = (DWORD)k->mtime; lw->dwHighDateTime = (DWORD)(k->mtime >> 32); }
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}

LSTATUS RegGetValueW(HKEY h, LPCWSTR sub, LPCWSTR name, DWORD flags, LPDWORD type, PVOID data, LPDWORD cb) {
    shx_mutex_lock(&g_reg_lk);
    DWORD err; RegKey* b = resolve(h, &err);
    LSTATUS r;
    if (!b) r = err;
    else {
        RegKey* k = walk(b, sub, 0, NULL);
        RegVal* v = k ? find_val2(k, name) : NULL;
        if (!v) r = ERROR_FILE_NOT_FOUND;
        else {
            int ok = 0;
            switch (v->type) {
                case REG_SZ: ok = (flags & RRF_RT_REG_SZ) || (flags & 0xFFFFu) == 0xFFFFu; break;
                case REG_DWORD: ok = (flags & RRF_RT_REG_DWORD) || (flags & 0xFFFFu) == 0xFFFFu; break;
                case REG_EXPAND_SZ: ok = (flags & 0x4u) || (flags & 0xFFFFu) == 0xFFFFu || (flags & RRF_RT_REG_SZ); break;
                case REG_BINARY: ok = (flags & 0x8u) || (flags & 0xFFFFu) == 0xFFFFu; break;
                case REG_MULTI_SZ: ok = (flags & 0x20u) || (flags & 0xFFFFu) == 0xFFFFu; break;
                case REG_QWORD: ok = (flags & 0x40u) || (flags & 0xFFFFu) == 0xFFFFu; break;
                default: ok = (flags & 0xFFFFu) == 0xFFFFu;
            }
            if (!ok) r = ERROR_UNSUPPORTED_TYPE;
            else r = copy_out(v, type, (LPBYTE)data, cb);
        }
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}

/* ---------------------------------------------------------------
 * A 版 (ACP ↔ UTF-16)
 * --------------------------------------------------------------- */
static WCHAR* a2w(LPCSTR a) {
    if (!a) return NULL;
    int n = MultiByteToWideChar(CP_ACP, 0, a, -1, NULL, 0);
    WCHAR* w = (WCHAR*)malloc(((size_t)(n > 0 ? n : 1)) * 2);
    if (n > 0) MultiByteToWideChar(CP_ACP, 0, a, -1, w, n); else w[0] = 0;
    return w;
}
LSTATUS RegOpenKeyExA(HKEY k, LPCSTR sub, DWORD opt, REGSAM sam, PHKEY out) {
    WCHAR* w = a2w(sub); LSTATUS r = RegOpenKeyExW(k, w, opt, sam, out); free(w); return r;
}
LSTATUS RegCreateKeyExA(HKEY k, LPCSTR sub, DWORD rsv, LPSTR cls, DWORD opt, REGSAM sam, LPVOID sa, PHKEY out, LPDWORD disp) {
    (void)cls; WCHAR* w = a2w(sub); LSTATUS r = RegCreateKeyExW(k, w, rsv, NULL, opt, sam, sa, out, disp); free(w); return r;
}
LSTATUS RegDeleteKeyA(HKEY k, LPCSTR sub) { WCHAR* w = a2w(sub); LSTATUS r = RegDeleteKeyW(k, w); free(w); return r; }
LSTATUS RegDeleteValueA(HKEY k, LPCSTR n) { WCHAR* w = a2w(n); LSTATUS r = RegDeleteValueW(k, w); free(w); return r; }
static int is_str_type(DWORD t) { return t == REG_SZ || t == REG_EXPAND_SZ || t == REG_MULTI_SZ; }
LSTATUS RegSetValueExA(HKEY k, LPCSTR name, DWORD rsv, DWORD type, const BYTE* data, DWORD cb) {
    WCHAR* wn_ = a2w(name); LSTATUS r;
    if (is_str_type(type) && data) {
        int n = MultiByteToWideChar(CP_ACP, 0, (const char*)data, (int)cb, NULL, 0);
        WCHAR* w = (WCHAR*)malloc(((size_t)(n > 0 ? n : 0) + 1) * 2);
        if (n > 0) MultiByteToWideChar(CP_ACP, 0, (const char*)data, (int)cb, w, n);
        r = RegSetValueExW(k, wn_, rsv, type, (const BYTE*)w, (DWORD)(n > 0 ? n : 0) * 2);
        free(w);
    } else r = RegSetValueExW(k, wn_, rsv, type, data, cb);
    free(wn_);
    return r;
}
LSTATUS RegQueryValueExA(HKEY k, LPCSTR name, LPDWORD rsv, LPDWORD type, LPBYTE data, LPDWORD cb) {
    WCHAR* wn_ = a2w(name);
    DWORD t = 0, need = 0;
    LSTATUS r = RegQueryValueExW(k, wn_, rsv, &t, NULL, &need);
    if (r != ERROR_SUCCESS) { free(wn_); return r; }
    if (type) *type = t;
    if (!is_str_type(t)) { LSTATUS q = RegQueryValueExW(k, wn_, rsv, type, data, cb); free(wn_); return q; }
    WCHAR* w = (WCHAR*)malloc((size_t)need + 4);
    DWORD got = need;
    RegQueryValueExW(k, wn_, rsv, &t, (LPBYTE)w, &got);
    free(wn_);
    int nb = WideCharToMultiByte(CP_ACP, 0, w, (int)(got / 2), NULL, 0, NULL, NULL);
    if (cb) {
        if (!data) { *cb = (DWORD)nb; free(w); return ERROR_SUCCESS; }
        if (*cb < (DWORD)nb) { *cb = (DWORD)nb; free(w); return ERROR_MORE_DATA; }
        WideCharToMultiByte(CP_ACP, 0, w, (int)(got / 2), (char*)data, nb, NULL, NULL);
        *cb = (DWORD)nb;
    }
    free(w);
    return ERROR_SUCCESS;
}
LSTATUS RegEnumKeyExA(HKEY k, DWORD idx, LPSTR name, LPDWORD cchName, LPDWORD rsv, LPSTR cls, LPDWORD cchCls, FILETIME* lw) {
    (void)cls;
    WCHAR tmp[512]; DWORD n = 512;
    LSTATUS r = RegEnumKeyExW(k, idx, tmp, &n, rsv, NULL, cchCls, lw);
    if (r != ERROR_SUCCESS) return r;
    int nb = WideCharToMultiByte(CP_ACP, 0, tmp, (int)n + 1, NULL, 0, NULL, NULL);
    if (!cchName || !name || *cchName < (DWORD)nb) { if (cchName) *cchName = (DWORD)nb - 1; return ERROR_MORE_DATA; }
    WideCharToMultiByte(CP_ACP, 0, tmp, (int)n + 1, name, nb, NULL, NULL);
    *cchName = (DWORD)nb - 1;
    return ERROR_SUCCESS;
}
LSTATUS RegEnumValueA(HKEY k, DWORD idx, LPSTR name, LPDWORD cchName, LPDWORD rsv, LPDWORD type, LPBYTE data, LPDWORD cb) {
    WCHAR tmp[512]; DWORD n = 512;
    LSTATUS r = RegEnumValueW(k, idx, tmp, &n, rsv, type, data, cb);
    if (r != ERROR_SUCCESS && r != ERROR_MORE_DATA) return r;
    int nb = WideCharToMultiByte(CP_ACP, 0, tmp, (int)n + 1, NULL, 0, NULL, NULL);
    if (!cchName || !name || *cchName < (DWORD)nb) { if (cchName) *cchName = (DWORD)nb - 1; return ERROR_MORE_DATA; }
    WideCharToMultiByte(CP_ACP, 0, tmp, (int)n + 1, name, nb, NULL, NULL);
    *cchName = (DWORD)nb - 1;
    return r;
}

/* ---------------------------------------------------------------
 * トークン (OpenProcessToken / GetTokenInformation): 非昇格ユーザの擬似トークン
 * --------------------------------------------------------------- */
BOOL OpenProcessToken(HANDLE proc, DWORD access, LPHANDLE tok) {
    (void)access;
    ShxObj* p = shx_ref(proc, OBJ_PROCESS);
    if (!p) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    shx_unref(p);
    if (!tok) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    ShxObj* o = shx_obj_new(OBJ_TOKEN);
    if (!o) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return FALSE; }
    *tok = shx_handle_new(o);
    return *tok != 0;
}
BOOL GetTokenInformation(HANDLE tok, int cls, LPVOID info, DWORD n, LPDWORD ret) {
    ShxObj* o = shx_ref(tok, OBJ_TOKEN);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    shx_unref(o);
    if (cls == 20 /* TokenElevation */ || cls == 18 /* TokenElevationType */ || cls == 26 /* TokenElevation? */) {
        DWORD v = (cls == 18) ? 1 /* TokenElevationTypeDefault */ : 0;
        if (ret) *ret = 4;
        if (n < 4 || !info) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return FALSE; }
        *(DWORD*)info = v;
        return TRUE;
    }
    SetLastError(ERROR_INVALID_PARAMETER);
    return FALSE;
}

/* ---------------------------------------------------------------
 * シード / import / export
 * --------------------------------------------------------------- */
static RegKey* path_to_key(const char* path, int create) {
    /* "HKEY_CURRENT_USER\Software\X" / "HKCU\..." / 先頭 "\" 許容 */
    int root = -1; size_t rl = 0;
    for (int i = 0; i < 5; i++) {
        size_t l1 = strlen(k_root_names[i]), l2 = strlen(k_root_short[i]);
        if (!strncasecmp(path, k_root_names[i], l1) && (path[l1] == '\\' || !path[l1])) { root = i; rl = l1; break; }
        if (!strncasecmp(path, k_root_short[i], l2) && (path[l2] == '\\' || !path[l2])) { root = i; rl = l2; break; }
    }
    if (root < 0) return NULL;
    const char* rest = path + rl;
    while (*rest == '\\') rest++;
    WCHAR* w = shx_wcsdup_utf8(rest);
    RegKey* k = walk(g_roots[root], w, create, NULL);
    free(w);
    return k;
}

int shimx_reg_set(const char* path, const char* name, DWORD type, const void* data, DWORD cb) {
    shx_ensure_init();
    shx_mutex_lock(&g_reg_lk);
    RegKey* k = path_to_key(path, 1);
    int r = -1;
    if (k) {
        WCHAR* w = name ? shx_wcsdup_utf8(name) : NULL;
        r = set_val(k, w, type, data, cb);
        free(w);
    }
    shx_mutex_unlock(&g_reg_lk);
    return r;
}
int shimx_reg_set_sz(const char* path, const char* name, const char* utf8) {
    WCHAR* w = shx_wcsdup_utf8(utf8);
    int r = shimx_reg_set(path, name, REG_SZ, w, (DWORD)(shx_wstr_len(w) + 1) * 2);
    free(w);
    return r;
}
int shimx_reg_set_dword(const char* path, const char* name, DWORD v) { return shimx_reg_set(path, name, REG_DWORD, &v, 4); }
void shimx_reg_stats(int* nKeys, int* nVals) {
    int nk = 0, nv = 0;
    shx_mutex_lock(&g_reg_lk);
    RegKey* stack[256]; int sp = 0;
    for (int i = 0; i < 5; i++) if (g_roots[i]) stack[sp++] = g_roots[i];
    while (sp) {
        RegKey* k = stack[--sp]; nk++; nv += k->nvals;
        for (RegKey* c = k->child; c && sp < 255; c = c->sibling) stack[sp++] = c;
    }
    shx_mutex_unlock(&g_reg_lk);
    if (nKeys) *nKeys = nk;
    if (nVals) *nVals = nv;
}

static void seed_defaults(void);
void shimx_reg_reset(void) {
    shx_ensure_init();
    shx_mutex_lock(&g_reg_lk);
    for (int i = 0; i < 5; i++) {
        for (RegKey* c = g_roots[i]->child; c; c = c->sibling) c->deleted = 1;   /* 開いているハンドル保護のため解放せず削除印 */
        g_roots[i]->child = NULL; g_roots[i]->nsub = 0;
        for (RegVal* v = g_roots[i]->vals; v;) { RegVal* n = v->next; free(v->name); free(v->data); free(v); v = n; }
        g_roots[i]->vals = g_roots[i]->vtail = NULL; g_roots[i]->nvals = 0;
    }
    shx_mutex_unlock(&g_reg_lk);
    seed_defaults();
}

static int hexv(int c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }
static uint8_t* parse_hex_list(const char* s, DWORD* n) {
    size_t cap = 64, k = 0; uint8_t* b = (uint8_t*)malloc(cap);
    while (*s) {
        while (*s == ' ' || *s == ',' || *s == '\\' || *s == '\r' || *s == '\n') s++;
        int a = hexv(s[0]), c = hexv(s[1]);
        if (a < 0 || c < 0) break;
        if (k == cap) { cap *= 2; b = (uint8_t*)realloc(b, cap); }
        b[k++] = (uint8_t)(a * 16 + c); s += 2;
    }
    *n = (DWORD)k;
    return b;
}

int shimx_reg_import_text(const char* text) {
    shx_ensure_init();
    int count = 0;
    shx_mutex_lock(&g_reg_lk);
    RegKey* cur = NULL;
    const char* p = text;
    while (*p) {
        /* 論理行 (行末 '\' 継続は hex 値のみ) を組み立てる */
        const char* e = strchr(p, '\n');
        size_t len = e ? (size_t)(e - p) : strlen(p);
        char* line = (char*)malloc(len + 1); memcpy(line, p, len); line[len] = 0;
        p = e ? e + 1 : p + len;
        while (len && (line[len - 1] == '\r')) line[--len] = 0;
        while (len && line[len - 1] == '\\' && *p) {      /* 継続 */
            const char* e2 = strchr(p, '\n'); size_t l2 = e2 ? (size_t)(e2 - p) : strlen(p);
            line = (char*)realloc(line, len + l2 + 1); memcpy(line + len - 1, p, l2); len = len - 1 + l2; line[len] = 0;
            p = e2 ? e2 + 1 : p + l2;
            while (len && line[len - 1] == '\r') line[--len] = 0;
        }
        char* s = line; while (*s == ' ' || *s == '\t') s++;
        if (*s == '[') {
            char* rb = strrchr(s, ']');
            if (rb) { *rb = 0; cur = path_to_key(s + 1, 1); }
        } else if (cur && (*s == '"' || *s == '@')) {
            WCHAR* nm = NULL; char* q = s;
            if (*q == '@') { q++; }
            else {
                q++; char* ns = (char*)malloc(strlen(q) + 1); size_t ni = 0;
                while (*q && *q != '"') { if (*q == '\\' && q[1]) q++; ns[ni++] = *q++; }
                ns[ni] = 0; if (*q == '"') q++;
                nm = shx_wcsdup_utf8(ns); free(ns);
            }
            while (*q == ' ') q++;
            if (*q == '=') {
                q++; while (*q == ' ') q++;
                if (*q == '"') {
                    q++; char* vs = (char*)malloc(strlen(q) + 1); size_t vi = 0;
                    while (*q && *q != '"') { if (*q == '\\' && q[1]) q++; vs[vi++] = *q++; }
                    vs[vi] = 0;
                    WCHAR* w = shx_wcsdup_utf8(vs);
                    if (set_val(cur, nm, REG_SZ, w, (DWORD)(shx_wstr_len(w) + 1) * 2) == 0) count++;
                    free(w); free(vs);
                } else if (!strncasecmp(q, "dword:", 6)) {
                    DWORD v = (DWORD)strtoul(q + 6, NULL, 16);
                    if (set_val(cur, nm, REG_DWORD, &v, 4) == 0) count++;
                } else if (!strncasecmp(q, "hex", 3)) {
                    DWORD type = REG_BINARY; const char* c = q + 3;
                    if (*c == '(') { type = (DWORD)strtoul(c + 1, NULL, 16); c = strchr(c, ')'); if (!c) c = q + 3; else c++; }
                    if (*c == ':') {
                        DWORD n; uint8_t* b = parse_hex_list(c + 1, &n);
                        if (set_val(cur, nm, type, b, n) == 0) count++;
                        free(b);
                    }
                }
            }
            free(nm);
        }
        free(line);
    }
    shx_mutex_unlock(&g_reg_lk);
    return count;
}

typedef struct { char* b; size_t n, cap; } Sb;
static void sb_put(Sb* s, const char* t) {
    size_t l = strlen(t);
    if (s->n + l + 1 > s->cap) { s->cap = (s->n + l + 1) * 2; s->b = (char*)realloc(s->b, s->cap); }
    memcpy(s->b + s->n, t, l + 1); s->n += l;
}
static void export_str(Sb* s, const WCHAR* w) {
    int n = shx_wstr_len(w);
    char* u = (char*)malloc((size_t)n * 4 + 1);
    shimx_utf16_to_utf8(w, n, u, (size_t)n * 4 + 1);
    char t[2]; t[1] = 0;
    for (char* c = u; *c; c++) { if (*c == '\\' || *c == '"') sb_put(s, "\\"); t[0] = *c; sb_put(s, t); }
    free(u);
}
static void export_key(Sb* s, RegKey* k, const char* path) {
    if (k->nvals || !k->child) {
        sb_put(s, "["); sb_put(s, path); sb_put(s, "]\n");
        for (RegVal* v = k->vals; v; v = v->next) {
            if (!v->name[0]) sb_put(s, "@="); else { sb_put(s, "\""); export_str(s, v->name); sb_put(s, "\"="); }
            char tmp[64];
            if (v->type == REG_SZ && v->cb >= 2 && v->cb % 2 == 0 && ((WCHAR*)v->data)[v->cb / 2 - 1] == 0) {
                sb_put(s, "\""); export_str(s, (WCHAR*)v->data); sb_put(s, "\"");
            } else if (v->type == REG_DWORD && v->cb == 4) {
                snprintf(tmp, sizeof tmp, "dword:%08x", *(DWORD*)v->data); sb_put(s, tmp);
            } else {
                if (v->type == REG_BINARY) sb_put(s, "hex:"); else { snprintf(tmp, sizeof tmp, "hex(%x):", v->type); sb_put(s, tmp); }
                for (DWORD i = 0; i < v->cb; i++) { snprintf(tmp, sizeof tmp, "%s%02x", i ? "," : "", v->data[i]); sb_put(s, tmp); }
            }
            sb_put(s, "\n");
        }
        sb_put(s, "\n");
    }
    for (RegKey* c = k->child; c; c = c->sibling) {
        int n = shx_wstr_len(c->name); char* u = (char*)malloc((size_t)n * 4 + 1); shimx_utf16_to_utf8(c->name, n, u, (size_t)n * 4 + 1);
        char* np = (char*)malloc(strlen(path) + strlen(u) + 2); sprintf(np, "%s\\%s", path, u);
        export_key(s, c, np); free(np); free(u);
    }
}
char* shimx_reg_export_text(void) {
    shx_ensure_init();
    Sb s = {0};
    sb_put(&s, "Windows Registry Editor Version 5.00\n\n");
    shx_mutex_lock(&g_reg_lk);
    for (int i = 0; i < 5; i++) export_key(&s, g_roots[i], k_root_names[i]);
    shx_mutex_unlock(&g_reg_lk);
    return s.b;
}

static const char* const k_seed =
    "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion]\n"
    "\"ProductName\"=\"Windows 10 Pro\"\n\"CurrentVersion\"=\"6.3\"\n\"CurrentBuild\"=\"19045\"\n\"CurrentBuildNumber\"=\"19045\"\n"
    "\"CurrentMajorVersionNumber\"=dword:0000000a\n\"CurrentMinorVersionNumber\"=dword:00000000\n"
    "\"EditionID\"=\"Professional\"\n\"InstallationType\"=\"Client\"\n\"RegisteredOwner\"=\"user\"\n\n"
    "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion]\n"
    "\"ProgramFilesDir\"=\"C:\\\\Program Files\"\n\"CommonFilesDir\"=\"C:\\\\Program Files\\\\Common Files\"\n"
    "\"ProgramFilesDir (x86)\"=\"C:\\\\Program Files (x86)\"\n\n"
    "[HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Cryptography]\n\"MachineGuid\"=\"00000000-0000-4000-8000-0000574542ad\"\n\n"
    "[HKEY_LOCAL_MACHINE\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0]\n"
    "\"ProcessorNameString\"=\"WebAssembly vCPU\"\n\"Identifier\"=\"Intel64 Family 6 Model 158 Stepping 10\"\n\"~MHz\"=dword:00000bb8\n\"VendorIdentifier\"=\"GenuineIntel\"\n\n"
    "[HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Control\\Nls\\CodePage]\n\"ACP\"=\"1252\"\n\"OEMCP\"=\"437\"\n\n"
    "[HKEY_CURRENT_USER\\Control Panel\\International]\n\"sDecimal\"=\".\"\n\"sThousand\"=\",\"\n\"sShortDate\"=\"M/d/yyyy\"\n\"sLongDate\"=\"dddd, MMMM d, yyyy\"\n\"iMeasure\"=\"1\"\n\"LocaleName\"=\"en-US\"\n\n"
    "[HKEY_CURRENT_USER\\Software]\n\n";

static void seed_defaults(void) { shimx_reg_import_text(k_seed); }

void shx_init_reg(void) {
    static const WCHAR e[1] = {0};
    for (int i = 0; i < 5; i++) g_roots[i] = key_new(e, 0, NULL);
    g_reg_inited = 1;
    seed_defaults();
}

/* ---- advapi32 Crypt* (ハッシュ API) は非対応: 常に失敗 (NTE_PROVIDER_DLL_FAIL) ---- */
BOOL CryptAcquireContextA(LPHANDLE prov, LPCSTR cont, LPCSTR name, DWORD type, DWORD flags) {
    (void)cont; (void)name; (void)type; (void)flags; if (prov) *prov = 0; SetLastError(0x8009001Du); return FALSE;
}
BOOL CryptCreateHash(HANDLE prov, DWORD alg, HANDLE key, DWORD flags, LPHANDLE hash) { (void)prov; (void)alg; (void)key; (void)flags; if (hash) *hash = 0; SetLastError(0x80090008u); return FALSE; }
BOOL CryptHashData(HANDLE h, const BYTE* d, DWORD n, DWORD flags) { (void)h; (void)d; (void)n; (void)flags; SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
BOOL CryptGetHashParam(HANDLE h, DWORD p, BYTE* d, LPDWORD n, DWORD flags) { (void)h; (void)p; (void)d; (void)n; (void)flags; SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
BOOL CryptDestroyHash(HANDLE h) { (void)h; return TRUE; }
