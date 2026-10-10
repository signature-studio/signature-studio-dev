/* INI (GetPrivateProfile / WritePrivateProfile) とコンソール系。 */
#include "shimx_internal.h"
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>

/* ---------------------------------------------------------------
 * コンソール: 常に「コンソールではない」(GetConsoleMode=FALSE)。WriteConsoleW は stdout/stderr へ UTF-8 で書く
 * --------------------------------------------------------------- */
BOOL GetConsoleMode(HANDLE h, LPDWORD mode) { (void)h; if (mode) *mode = 0; SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
UINT GetConsoleCP(void) { return 437; }
UINT GetConsoleOutputCP(void) { return 437; }
BOOL WriteConsoleW(HANDLE h, LPCVOID buf, DWORD n, LPDWORD written, LPVOID rsv) {
    (void)rsv;
    ShxObj* o = shx_ref(h, OBJ_FILE);
    if (!o) { SetLastError(ERROR_INVALID_HANDLE); return FALSE; }
    int fd = o->fd;
    shx_unref(o);
    char* u = (char*)malloc((size_t)n * 4 + 1);
    if (!u) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return FALSE; }
    int r = shimx_utf16_to_utf8((const WCHAR*)buf, (int)n, u, (size_t)n * 4 + 1);
    if (r > 0) { ssize_t w = write(fd, u, (size_t)r); (void)w; }
    free(u);
    if (written) *written = n;
    return TRUE;
}
BOOL ReadConsoleW(HANDLE h, LPVOID buf, DWORD n, LPDWORD read, LPVOID ctl) {
    (void)h; (void)buf; (void)n; (void)ctl;
    if (read) *read = 0;
    SetLastError(ERROR_INVALID_HANDLE);
    return FALSE;
}

/* ---------------------------------------------------------------
 * INI
 * --------------------------------------------------------------- */
typedef struct { WCHAR* text; size_t len; int utf16; } IniFile;

static int ini_load(LPCWSTR file, IniFile* f, char* pathOut, size_t pathSz) {
    memset(f, 0, sizeof(*f));
    if (shx_wpath_to_posix(file, pathOut, pathSz) < 0) return -1;
    int fd = open(pathOut, O_RDONLY);
    if (fd < 0) { f->text = (WCHAR*)calloc(1, 2); return 0; }     /* 未存在: 空 */
    struct stat st; fstat(fd, &st);
    unsigned char* raw = (unsigned char*)malloc((size_t)st.st_size + 2);
    ssize_t r = read(fd, raw, (size_t)st.st_size);
    close(fd);
    if (r < 0) r = 0;
    raw[r] = 0; raw[r + 1] = 0;
    if (r >= 2 && raw[0] == 0xFF && raw[1] == 0xFE) {
        f->utf16 = 1;
        size_t n = ((size_t)r - 2) / 2;
        f->text = (WCHAR*)malloc((n + 1) * 2);
        memcpy(f->text, raw + 2, n * 2);
        f->text[n] = 0; f->len = n;
    } else {
        size_t off = (r >= 3 && raw[0] == 0xEF && raw[1] == 0xBB && raw[2] == 0xBF) ? 3 : 0;
        int cp = off ? CP_UTF8 : CP_ACP;
        int n = MultiByteToWideChar(cp, 0, (const char*)raw + off, (int)((size_t)r - off), NULL, 0);
        f->text = (WCHAR*)malloc(((size_t)(n > 0 ? n : 0) + 1) * 2);
        if (n > 0) MultiByteToWideChar(cp, 0, (const char*)raw + off, (int)((size_t)r - off), f->text, n);
        f->len = n > 0 ? (size_t)n : 0;
        f->text[f->len] = 0;
    }
    free(raw);
    return 0;
}

typedef struct { size_t ls, le, ns, ne, vs, ve; int kind; } IniLine;   /* kind: 0 other, 1 section, 2 key */

static size_t ini_lines(const IniFile* f, IniLine** out) {
    size_t cap = 64, n = 0;
    IniLine* L = (IniLine*)malloc(cap * sizeof(IniLine));
    size_t i = 0;
    while (i < f->len) {
        size_t s = i;
        while (i < f->len && f->text[i] != '\n') i++;
        size_t e = i;
        if (i < f->len) i++;
        size_t te = e;
        if (te > s && f->text[te - 1] == '\r') te--;
        IniLine ln = {s, i, 0, 0, 0, 0, 0};
        size_t a = s;
        while (a < te && (f->text[a] == ' ' || f->text[a] == '\t')) a++;
        if (a < te && f->text[a] == '[') {
            size_t b = a + 1; while (b < te && f->text[b] != ']') b++;
            ln.kind = 1; ln.ns = a + 1; ln.ne = b;
        } else if (a < te && f->text[a] != ';') {
            size_t eq = a; while (eq < te && f->text[eq] != '=') eq++;
            if (eq < te) {
                size_t ke = eq; while (ke > a && (f->text[ke - 1] == ' ' || f->text[ke - 1] == '\t')) ke--;
                size_t vs = eq + 1; while (vs < te && (f->text[vs] == ' ' || f->text[vs] == '\t')) vs++;
                size_t ve = te; while (ve > vs && (f->text[ve - 1] == ' ' || f->text[ve - 1] == '\t')) ve--;
                ln.kind = 2; ln.ns = a; ln.ne = ke; ln.vs = vs; ln.ve = ve;
            }
        }
        if (n == cap) { cap *= 2; L = (IniLine*)realloc(L, cap * sizeof(IniLine)); }
        L[n++] = ln;
    }
    *out = L;
    return n;
}
static int name_eq(const WCHAR* t, size_t s, size_t e, LPCWSTR name) {
    size_t n = (size_t)shx_wstr_len(name);
    if (e - s != n) return 0;
    return shx_wcsnicmp(t + s, name, n) == 0;
}

DWORD GetPrivateProfileStringW(LPCWSTR sec, LPCWSTR key, LPCWSTR def, LPWSTR out, DWORD n, LPCWSTR file) {
    if (!out || n == 0) return 0;
    char pp[2048]; IniFile f;
    if (ini_load(file, &f, pp, sizeof pp) < 0) { out[0] = 0; return 0; }
    IniLine* L; size_t nl = ini_lines(&f, &L);
    WCHAR* res = (WCHAR*)malloc((f.len + 8) * 2 + 4);
    size_t rl = 0; int found = 0, multi = 0;
    if (!sec) {           /* セクション名一覧 */
        multi = 1; found = 1;
        for (size_t i = 0; i < nl; i++) if (L[i].kind == 1) { size_t k = L[i].ne - L[i].ns; memcpy(res + rl, f.text + L[i].ns, k * 2); rl += k; res[rl++] = 0; }
    } else {
        int in = 0;
        for (size_t i = 0; i < nl; i++) {
            if (L[i].kind == 1) { in = name_eq(f.text, L[i].ns, L[i].ne, sec); continue; }
            if (!in || L[i].kind != 2) continue;
            if (!key) {   /* キー名一覧 */
                multi = 1; found = 1;
                size_t k = L[i].ne - L[i].ns; memcpy(res + rl, f.text + L[i].ns, k * 2); rl += k; res[rl++] = 0;
            } else if (name_eq(f.text, L[i].ns, L[i].ne, key)) {
                size_t vs = L[i].vs, ve = L[i].ve;
                if (ve - vs >= 2 && ((f.text[vs] == '"' && f.text[ve - 1] == '"') || (f.text[vs] == '\'' && f.text[ve - 1] == '\''))) { vs++; ve--; }
                memcpy(res, f.text + vs, (ve - vs) * 2); rl = ve - vs; found = 1; break;
            }
        }
    }
    DWORD ret;
    if (!found && !multi) {
        if (def) { rl = (size_t)shx_wstr_len(def); memcpy(res, def, rl * 2); } else rl = 0;
    }
    if (multi) {
        if (rl + 1 > n) { size_t cp = n >= 2 ? n - 2 : 0; memcpy(out, res, cp * 2); if (n >= 2) { out[n - 2] = 0; out[n - 1] = 0; } ret = (DWORD)(n >= 2 ? n - 2 : 0); }
        else { memcpy(out, res, rl * 2); out[rl] = 0; ret = (DWORD)rl; }
    } else if (rl >= n) { memcpy(out, res, ((size_t)n - 1) * 2); out[n - 1] = 0; ret = n - 1; }
    else { memcpy(out, res, rl * 2); out[rl] = 0; ret = (DWORD)rl; }
    free(res); free(L); free(f.text);
    return ret;
}

UINT GetPrivateProfileIntW(LPCWSTR sec, LPCWSTR key, int def, LPCWSTR file) {
    WCHAR b[64];
    DWORD n = GetPrivateProfileStringW(sec, key, NULL, b, 64, file);
    if (!n) return (UINT)def;
    char a[64]; int i = 0;
    for (; i < 63 && b[i]; i++) a[i] = (char)b[i];
    a[i] = 0;
    return (UINT)strtol(a, NULL, 10);
}

static void sb_add(WCHAR** b, size_t* n, size_t* cap, const WCHAR* s, size_t k) {
    if (*n + k + 1 > *cap) { *cap = (*n + k + 1) * 2; *b = (WCHAR*)realloc(*b, *cap * 2); }
    memcpy(*b + *n, s, k * 2); *n += k; (*b)[*n] = 0;
}

BOOL WritePrivateProfileStringW(LPCWSTR sec, LPCWSTR key, LPCWSTR val, LPCWSTR file) {
    if (!sec) return TRUE;   /* キャッシュフラッシュ要求 */
    char pp[2048]; IniFile f;
    if (ini_load(file, &f, pp, sizeof pp) < 0) return FALSE;
    IniLine* L; size_t nl = ini_lines(&f, &L);
    WCHAR* o = (WCHAR*)calloc(1, 2); size_t on = 0, cap = 1;
    static const WCHAR crlf[] = {'\r', '\n'};
    int in = 0, secFound = 0, done = 0;
    size_t secEndOut = 0;      /* 該当セクション末尾の出力位置 (キー追加用) */
    for (size_t i = 0; i < nl; i++) {
        const WCHAR* ls = f.text + L[i].ls; size_t lk = L[i].le - L[i].ls;
        if (L[i].kind == 1) {
            if (in && !done && key && val) { /* 直前のセクション終端でキー追記 */
                sb_add(&o, &on, &cap, key, (size_t)shx_wstr_len(key));
                WCHAR eq = '='; sb_add(&o, &on, &cap, &eq, 1);
                sb_add(&o, &on, &cap, val, (size_t)shx_wstr_len(val)); sb_add(&o, &on, &cap, crlf, 2); done = 1;
            }
            in = name_eq(f.text, L[i].ns, L[i].ne, sec);
            if (in) secFound = 1;
            if (in && !key) continue;          /* セクション削除 */
            sb_add(&o, &on, &cap, ls, lk);
            continue;
        }
        if (in && !key) continue;              /* セクション内行を削除 */
        if (in && L[i].kind == 2 && key && name_eq(f.text, L[i].ns, L[i].ne, key)) {
            done = 1;
            if (!val) continue;                /* キー削除 */
            sb_add(&o, &on, &cap, key, (size_t)shx_wstr_len(key));
            WCHAR eq = '='; sb_add(&o, &on, &cap, &eq, 1);
            sb_add(&o, &on, &cap, val, (size_t)shx_wstr_len(val)); sb_add(&o, &on, &cap, crlf, 2);
            continue;
        }
        sb_add(&o, &on, &cap, ls, lk);
        if (in) secEndOut = on;
    }
    (void)secEndOut;
    if (!done && key && val) {
        if (!secFound) {
            if (on && !(on >= 1 && o[on - 1] == '\n')) sb_add(&o, &on, &cap, crlf, 2);
            WCHAR lb = '[', rb = ']';
            sb_add(&o, &on, &cap, &lb, 1); sb_add(&o, &on, &cap, sec, (size_t)shx_wstr_len(sec)); sb_add(&o, &on, &cap, &rb, 1); sb_add(&o, &on, &cap, crlf, 2);
        } else if (on && o[on - 1] != '\n') sb_add(&o, &on, &cap, crlf, 2);
        sb_add(&o, &on, &cap, key, (size_t)shx_wstr_len(key));
        WCHAR eq = '='; sb_add(&o, &on, &cap, &eq, 1);
        sb_add(&o, &on, &cap, val, (size_t)shx_wstr_len(val)); sb_add(&o, &on, &cap, crlf, 2);
    }
    /* 書き出し */
    char* bytes; size_t bn;
    if (f.utf16) {
        bn = on * 2 + 2; bytes = (char*)malloc(bn);
        bytes[0] = (char)0xFF; bytes[1] = (char)0xFE; memcpy(bytes + 2, o, on * 2);
    } else {
        int nb = WideCharToMultiByte(CP_ACP, 0, o, (int)on, NULL, 0, NULL, NULL);
        bytes = (char*)malloc((size_t)(nb > 0 ? nb : 0) + 1); bn = nb > 0 ? (size_t)nb : 0;
        if (nb > 0) WideCharToMultiByte(CP_ACP, 0, o, (int)on, bytes, nb, NULL, NULL);
    }
    int fd = open(pp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    BOOL ok = FALSE;
    if (fd >= 0) { ok = (write(fd, bytes, bn) == (ssize_t)bn); close(fd); }
    else SetLastError(ERROR_PATH_NOT_FOUND);
    free(bytes); free(o); free(L); free(f.text);
    return ok;
}
