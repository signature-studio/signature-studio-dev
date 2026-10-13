/* 文字列 / コードページ / 簡易ロケール。
 * ACP 既定は 1252 (shimx_set_acp で変更可: 65001=UTF-8 を推奨する場合あり)。
 * 対応コードページ: 1252 / 28591(Latin-1) / 437・850(近似=Latin-1) / 20127(ASCII) / 65001(UTF-8) /
 *                   932 (Shift-JIS: DBCS。表は scripts/gen_cp932.py が生成する src/cp932_tab.c)。
 * 他 (936/949/950 等) は ERROR_INVALID_PARAMETER を返す (inventory の制限参照)。
 */
#include "shimx_internal.h"
#include <wctype.h>
#include <strings.h>
#include <ctype.h>

static UINT g_acp = 1252;
void shimx_set_acp(UINT cp) { g_acp = cp; }
int shx_acp(void) { return (int)g_acp; }

uint32_t shimx_towlower(uint32_t c) { return (uint32_t)towlower((wint_t)c); }
uint32_t shimx_towupper(uint32_t c) { return (uint32_t)towupper((wint_t)c); }

int shx_wstr_len(const WCHAR* w) { int n = 0; while (w[n]) n++; return n; }
int shx_wcsicmp(const WCHAR* a, const WCHAR* b) {
    for (;; a++, b++) {
        uint32_t x = shimx_towlower(*a), y = shimx_towlower(*b);
        if (x != y) return x < y ? -1 : 1;
        if (!*a) return 0;
    }
}
int shx_wcsnicmp(const WCHAR* a, const WCHAR* b, size_t n) {
    for (size_t i = 0; i < n; i++) {
        uint32_t x = shimx_towlower(a[i]), y = shimx_towlower(b[i]);
        if (x != y) return x < y ? -1 : 1;
        if (!a[i]) return 0;
    }
    return 0;
}

/* ---------------------------------------------------------------
 * UTF-16 ↔ UTF-8
 * --------------------------------------------------------------- */
int shimx_utf16_to_utf8(const WCHAR* w, int nw, char* out, size_t outSize) {
    size_t n = 0;
    if (!w) return -1;
    int i = 0;
    while (nw < 0 ? w[i] != 0 : i < nw) {
        uint32_t cp = w[i++];
        if (cp >= 0xD800u && cp <= 0xDBFFu && (nw < 0 ? w[i] != 0 : i < nw) && w[i] >= 0xDC00u && w[i] <= 0xDFFFu) {
            cp = 0x10000u + ((cp - 0xD800u) << 10) + (w[i] - 0xDC00u);
            i++;
        } else if (cp >= 0xD800u && cp <= 0xDFFFu) {
            cp = 0xFFFDu;
        }
        unsigned need = cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
        if (out) {
            if (n + need + 1 > outSize) return -1;
            if (need == 1) out[n] = (char)cp;
            else if (need == 2) { out[n] = (char)(0xC0 | (cp >> 6)); out[n+1] = (char)(0x80 | (cp & 0x3F)); }
            else if (need == 3) { out[n] = (char)(0xE0 | (cp >> 12)); out[n+1] = (char)(0x80 | ((cp >> 6) & 0x3F)); out[n+2] = (char)(0x80 | (cp & 0x3F)); }
            else { out[n] = (char)(0xF0 | (cp >> 18)); out[n+1] = (char)(0x80 | ((cp >> 12) & 0x3F)); out[n+2] = (char)(0x80 | ((cp >> 6) & 0x3F)); out[n+3] = (char)(0x80 | (cp & 0x3F)); }
        }
        n += need;
    }
    if (out) out[n] = 0;
    return (int)n;
}

/* strict=1: 不正なら -1。戻り=WCHAR 数 (out==NULL なら数えるだけ) */
static int utf8_decode(const unsigned char* s, int ns, WCHAR* out, size_t outCch, int strict) {
    size_t n = 0;
    for (int i = 0; i < ns;) {
        uint32_t cp; int len = 1;
        unsigned char c = s[i];
        if (c < 0x80) cp = c;
        else if (c >= 0xC2 && c <= 0xDF && i + 1 < ns && (s[i+1] & 0xC0) == 0x80) { cp = ((c & 0x1F) << 6) | (s[i+1] & 0x3F); len = 2; }
        else if (c >= 0xE0 && c <= 0xEF && i + 2 < ns && (s[i+1] & 0xC0) == 0x80 && (s[i+2] & 0xC0) == 0x80) {
            cp = ((c & 0x0F) << 12) | ((s[i+1] & 0x3F) << 6) | (s[i+2] & 0x3F); len = 3;
            if (cp < 0x800 || (cp >= 0xD800 && cp <= 0xDFFF)) { cp = 0xFFFD; len = 1; if (strict) return -1; }
        }
        else if (c >= 0xF0 && c <= 0xF4 && i + 3 < ns && (s[i+1] & 0xC0) == 0x80 && (s[i+2] & 0xC0) == 0x80 && (s[i+3] & 0xC0) == 0x80) {
            cp = ((c & 0x07) << 18) | ((s[i+1] & 0x3F) << 12) | ((s[i+2] & 0x3F) << 6) | (s[i+3] & 0x3F); len = 4;
            if (cp < 0x10000 || cp > 0x10FFFF) { cp = 0xFFFD; len = 1; if (strict) return -1; }
        }
        else { cp = 0xFFFD; if (strict) return -1; }
        i += len;
        size_t need = cp >= 0x10000 ? 2 : 1;
        if (out) {
            if (n + need > outCch) return -2;
            if (need == 2) { cp -= 0x10000; out[n] = (WCHAR)(0xD800 + (cp >> 10)); out[n+1] = (WCHAR)(0xDC00 + (cp & 0x3FF)); }
            else out[n] = (WCHAR)cp;
        }
        n += need;
    }
    return (int)n;
}
int shimx_utf8_to_utf16(const char* s, int ns, WCHAR* out, size_t outCch) {
    if (ns < 0) ns = (int)strlen(s);
    int r = utf8_decode((const unsigned char*)s, ns, out, outCch, 0);
    if (r >= 0 && out && (size_t)r < outCch) out[r] = 0;
    return r;
}

WCHAR* shx_wcsdup_utf8(const char* s) {
    size_t n = strlen(s);
    WCHAR* w = (WCHAR*)malloc((n + 1) * sizeof(WCHAR));
    if (!w) return NULL;
    int r = shimx_utf8_to_utf16(s, (int)n, w, n + 1);
    if (r < 0) r = 0;
    w[r] = 0;
    return w;
}

/* ---------------------------------------------------------------
 * 単一バイトコードページ表
 * --------------------------------------------------------------- */
static const uint16_t k_cp1252_hi[32] = {
    0x20AC,0x0081,0x201A,0x0192,0x201E,0x2026,0x2020,0x2021,0x02C6,0x2030,0x0160,0x2039,0x0152,0x008D,0x017D,0x008F,
    0x0090,0x2018,0x2019,0x201C,0x201D,0x2022,0x2013,0x2014,0x02DC,0x2122,0x0161,0x203A,0x0153,0x009D,0x017E,0x0178 };

static UINT resolve_cp(UINT cp) {
    if (cp == CP_ACP || cp == CP_THREAD_ACP) return g_acp;
    if (cp == CP_OEMCP) return 437;
    if (cp == CP_MACCP) return 10000;
    return cp;
}
/* ---------------------------------------------------------------
 * CP932 (Windows-31J)。表 = Microsoft WindowsBestFit/bestfit932.txt
 *   MB→WC: 単一バイト 256 + DBCS (リード 0x81-0x9F/0xE0-0xFC × トレイル 0x40-0xFC, 0x7F 除く)
 *   WC→MB: WCTABLE 全件 (厳密 + best-fit)。WC_NO_BEST_FIT_CHARS 指定時は往復一致するものだけ
 * 無効並び (リード単独 / 無効トレイル / 未割当) は U+30FB (CPINFO の UnicodeDefaultChar) か、
 * MB_ERR_INVALID_CHARS 時は ERROR_NO_UNICODE_TRANSLATION。無効トレイルの 1 バイトは再解釈する。
 * --------------------------------------------------------------- */
extern const uint16_t shx_cp932_sb[256];
extern const uint16_t shx_cp932_db[60 * 189];
extern const uint32_t shx_cp932_wc[];
extern const unsigned shx_cp932_wc_n;
#define CP932_DEFAULT_WC 0x30FBu
static int cp932_is_lead(unsigned b) { return (b >= 0x81 && b <= 0x9F) || (b >= 0xE0 && b <= 0xFC); }
static int cp932_is_trail(unsigned b) { return b >= 0x40 && b <= 0xFC && b != 0x7F; }
static uint32_t cp932_db_at(unsigned lead, unsigned trail) {
    unsigned row = lead <= 0x9F ? lead - 0x81 : lead - 0xE0 + 31;
    return shx_cp932_db[row * 189 + (trail - 0x40)];
}
static uint32_t cp932_decode_code(unsigned code) {     /* code: 1 バイト値 or (lead<<8|trail)。無効は 0xFFFF */
    if (code <= 0xFF) { uint32_t v = shx_cp932_sb[code]; return v; }
    unsigned ld = code >> 8, tr = code & 0xFF;
    if (!cp932_is_lead(ld) || !cp932_is_trail(tr)) return 0xFFFF;
    uint32_t v = cp932_db_at(ld, tr);
    return v ? v : 0xFFFF;
}
static int cp932_encode_wc(uint32_t wc, int strict, unsigned* code) {   /* 1: 変換可 */
    unsigned lo = 0, hi = shx_cp932_wc_n;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        uint32_t e = shx_cp932_wc[mid], w = e >> 16;
        if (w == wc) {
            unsigned c = e & 0xFFFF;
            if (strict && cp932_decode_code(c) != wc) return 0;
            *code = c; return 1;
        }
        if (w < wc) lo = mid + 1; else hi = mid;
    }
    return 0;
}
static int mb2wc_932(DWORD flags, const unsigned char* s, int len, WCHAR* wc, int cchWc) {
    int n = 0, strict = (flags & MB_ERR_INVALID_CHARS) != 0;
    for (int i = 0; i < len;) {
        unsigned b = s[i]; uint32_t c; int adv = 1;
        if (cp932_is_lead(b)) {
            unsigned t = (i + 1 < len) ? s[i + 1] : 0;
            uint32_t v = 0;
            int trail_ok = (i + 1 < len) && cp932_is_trail(t);
            if (trail_ok) { v = cp932_db_at(b, t); adv = 2; }
            if (!v) {
                if (strict) { SetLastError(ERROR_NO_UNICODE_TRANSLATION); return 0; }
                c = CP932_DEFAULT_WC;
            } else c = v;
        } else c = shx_cp932_sb[b];
        if (cchWc) {
            if (n >= cchWc) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
            wc[n] = (WCHAR)c;
        }
        n++; i += adv;
    }
    return n;
}
static int wc2mb_932(DWORD flags, const WCHAR* wc, int len, char* mb, int cbMb, LPCSTR defChar, BOOL* usedDef) {
    int n = 0, strict = (flags & WC_NO_BEST_FIT_CHARS) != 0;
    unsigned dc = defChar ? (unsigned char)defChar[0] : 0x3F;
    for (int i = 0; i < len; i++) {
        unsigned code; int ok = cp932_encode_wc(wc[i], strict, &code);
        if (!ok) { code = dc; if (usedDef) *usedDef = TRUE; }
        int nb = code > 0xFF ? 2 : 1;
        if (cbMb) {
            if (n + nb > cbMb) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
            if (nb == 2) { mb[n] = (char)(code >> 8); mb[n + 1] = (char)(code & 0xFF); } else mb[n] = (char)code;
        }
        n += nb;
    }
    return n;
}

/* 1: 単一バイト対応, 0: 非対応 */
static int cp_sbcs_kind(UINT cp) {
    switch (cp) {
        case 1252: return 1;
        case 28591: case 437: case 850: case 10000: return 2;   /* Latin-1 近似 */
        case 20127: return 3;
        default: return 0;
    }
}
static uint32_t sb_to_wc(UINT kind, unsigned char b) {
    if (b < 0x80) return b;
    if (kind == 1 && b < 0xA0) return k_cp1252_hi[b - 0x80];
    if (kind == 3) return 0xFFFD;
    return b;
}
static int wc_to_sb(UINT kind, uint32_t wc) {      /* -1: 変換不可 */
    if (wc < 0x80) return (int)wc;
    if (kind == 1) {
        if (wc >= 0xA0 && wc <= 0xFF) return (int)wc;
        for (int i = 0; i < 32; i++) if (k_cp1252_hi[i] == wc) return 0x80 + i;
        return -1;
    }
    if (kind == 2 && wc <= 0xFF) return (int)wc;
    return -1;
}

int MultiByteToWideChar(UINT cp, DWORD flags, LPCSTR mb, int cbMb, LPWSTR wc, int cchWc) {
    shx_ensure_init();
    if (!mb || cbMb == 0 || cchWc < 0 || (cchWc > 0 && !wc)) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    cp = resolve_cp(cp);
    int len = cbMb < 0 ? (int)strlen(mb) + 1 : cbMb;
    const unsigned char* s = (const unsigned char*)mb;
    int n;
    if (cp == CP_UTF8) {
        n = utf8_decode(s, len, cchWc ? wc : NULL, (size_t)cchWc, (flags & MB_ERR_INVALID_CHARS) != 0);
        if (n == -1) { SetLastError(ERROR_NO_UNICODE_TRANSLATION); return 0; }
        if (n == -2) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
        return n;
    }
    if (cp == 932) return mb2wc_932(flags, s, len, cchWc ? wc : NULL, cchWc);
    int kind = cp_sbcs_kind(cp);
    if (!kind) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (cchWc == 0) return len;
    if (cchWc < len) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
    for (int i = 0; i < len; i++) {
        uint32_t c = sb_to_wc(kind, s[i]);
        if (c == 0xFFFD && (flags & MB_ERR_INVALID_CHARS)) { SetLastError(ERROR_NO_UNICODE_TRANSLATION); return 0; }
        wc[i] = (WCHAR)c;
    }
    return len;
}

int WideCharToMultiByte(UINT cp, DWORD flags, LPCWSTR wc, int cchWc, LPSTR mb, int cbMb,
                        LPCSTR defChar, BOOL* usedDef) {
    shx_ensure_init();
    if (!wc || cchWc == 0 || cbMb < 0 || (cbMb > 0 && !mb)) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    cp = resolve_cp(cp);
    int len = cchWc < 0 ? shx_wstr_len(wc) + 1 : cchWc;
    if (usedDef) *usedDef = FALSE;
    if (cp == CP_UTF8) {
        if (defChar || usedDef) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
        /* UTF-16 → UTF-8: 終端 NUL を含めて変換 (cchWc=-1 の場合) */
        int need = 0;
        for (int i = 0; i < len;) {
            uint32_t c = wc[i++];
            if (c >= 0xD800 && c <= 0xDBFF && i < len && wc[i] >= 0xDC00 && wc[i] <= 0xDFFF) { c = 0x10000; i++; }
            else if (c >= 0xD800 && c <= 0xDFFF) {
                if (flags & WC_ERR_INVALID_CHARS) { SetLastError(ERROR_NO_UNICODE_TRANSLATION); return 0; }
                c = 0xFFFD;
            }
            need += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4;
        }
        if (cbMb == 0) return need;
        if (cbMb < need) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
        char* tmp = (char*)malloc((size_t)need + 8);
        if (!tmp) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
        int hasNul = (cchWc < 0);
        int r = shimx_utf16_to_utf8(wc, hasNul ? len - 1 : len, tmp, (size_t)need + 8);
        if (r < 0) { free(tmp); SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
        memcpy(mb, tmp, (size_t)r);
        if (hasNul) mb[r++] = 0;
        free(tmp);
        return r;
    }
    if (cp == 932) return wc2mb_932(flags, wc, len, mb, cbMb, defChar, usedDef);
    int kind = cp_sbcs_kind(cp);
    if (!kind) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (cbMb == 0) return len;
    if (cbMb < len) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
    char dc = defChar ? defChar[0] : '?';
    for (int i = 0; i < len; i++) {
        int b = wc_to_sb(kind, wc[i]);
        if (b < 0) { b = (unsigned char)dc; if (usedDef) *usedDef = TRUE; }
        mb[i] = (char)b;
    }
    return len;
}

/* ---------------------------------------------------------------
 * lstr* / MulDiv
 * --------------------------------------------------------------- */
int lstrlenW(LPCWSTR s) { return s ? shx_wstr_len(s) : 0; }
int lstrlenA(LPCSTR s) { return s ? (int)strlen(s) : 0; }
int lstrcmpA(LPCSTR a, LPCSTR b) { int r = strcmp(a, b); return r < 0 ? -1 : r > 0 ? 1 : 0; }
int lstrcmpiA(LPCSTR a, LPCSTR b) { return strcasecmp(a, b) < 0 ? -1 : strcasecmp(a, b) > 0 ? 1 : 0; }
static int wcmp(const WCHAR* a, const WCHAR* b, int ci) {
    const WCHAR* ea = a; const WCHAR* eb = b;
    int la = shx_wstr_len(a), lb = shx_wstr_len(b);
    (void)ea; (void)eb;
    return CompareStringW(0x0400, ci ? NORM_IGNORECASE : 0, a, la, b, lb) - CSTR_EQUAL;
}
int lstrcmpW(LPCWSTR a, LPCWSTR b) { return wcmp(a, b, 0); }
int lstrcmpiW(LPCWSTR a, LPCWSTR b) { return wcmp(a, b, 1); }
LPWSTR lstrcpyW(LPWSTR d, LPCWSTR s) { int n = shx_wstr_len(s); memcpy(d, s, (size_t)(n + 1) * 2); return d; }
LPWSTR lstrcpynW(LPWSTR d, LPCWSTR s, int n) {
    if (n <= 0) return d;
    int i = 0;
    for (; i < n - 1 && s[i]; i++) d[i] = s[i];
    d[i] = 0;
    return d;
}
LPSTR lstrcpyA(LPSTR d, LPCSTR s) { return strcpy(d, s); }
LPWSTR lstrcatW(LPWSTR d, LPCWSTR s) { lstrcpyW(d + shx_wstr_len(d), s); return d; }

int MulDiv(int n, int num, int den) {
    if (den == 0) return -1;
    int64_t p = (int64_t)n * (int64_t)num;
    int64_t d = den;
    int neg = (p < 0) != (d < 0);
    uint64_t up = p < 0 ? (uint64_t)(-p) : (uint64_t)p;
    uint64_t ud = d < 0 ? (uint64_t)(-d) : (uint64_t)d;
    uint64_t q = (up + ud / 2) / ud;
    if (!neg && q > 0x7FFFFFFFull) return -1;
    if (neg && q > 0x80000000ull) return -1;
    return neg ? (int)(-(int64_t)q) : (int)q;
}

/* ---------------------------------------------------------------
 * 比較 / 大小変換 / 文字種
 * --------------------------------------------------------------- */
int CompareStringW(LCID loc, DWORD flags, LPCWSTR a, int na, LPCWSTR b, int nb) {
    (void)loc;
    if (!a || !b) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (na < 0) na = shx_wstr_len(a);
    if (nb < 0) nb = shx_wstr_len(b);
    int ic = (flags & (NORM_IGNORECASE | LINGUISTIC_IGNORECASE)) != 0;
    int n = na < nb ? na : nb;
    int tie = 0;    /* 二次差: 小文字 < 大文字 (Windows の culture 比較に近い) */
    for (int i = 0; i < n; i++) {
        uint32_t x = a[i], y = b[i];
        uint32_t fx = shimx_towlower(x), fy = shimx_towlower(y);
        if (fx != fy) return fx < fy ? CSTR_LESS_THAN : CSTR_GREATER_THAN;
        if (!ic && !tie && x != y) tie = (x == fx) ? CSTR_LESS_THAN : CSTR_GREATER_THAN;
    }
    if (na != nb) return na < nb ? CSTR_LESS_THAN : CSTR_GREATER_THAN;
    return tie ? tie : CSTR_EQUAL;
}
int CompareStringA(LCID loc, DWORD flags, LPCSTR a, int na, LPCSTR b, int nb) {
    if (!a || !b) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (na < 0) na = (int)strlen(a);
    if (nb < 0) nb = (int)strlen(b);
    WCHAR* wa = (WCHAR*)malloc((size_t)(na + 1) * 2 * 2);
    WCHAR* wb = (WCHAR*)malloc((size_t)(nb + 1) * 2 * 2);
    int r = 0;
    if (wa && wb) {
        int la = MultiByteToWideChar(CP_ACP, 0, a, na ? na : 0, wa, na * 2 + 1);
        int lb = MultiByteToWideChar(CP_ACP, 0, b, nb ? nb : 0, wb, nb * 2 + 1);
        r = CompareStringW(loc, flags, wa, la, wb, lb);
    }
    free(wa); free(wb);
    return r;
}
int CompareStringEx(LPCWSTR loc, DWORD flags, LPCWSTR a, int na, LPCWSTR b, int nb, LPVOID v, LPVOID r, LPARAM_T l) {
    (void)loc; (void)v; (void)r; (void)l;
    return CompareStringW(0x0400, flags, a, na, b, nb);
}

int LCMapStringW(LCID loc, DWORD flags, LPCWSTR src, int cch, LPWSTR dst, int cchDst) {
    (void)loc;
    if (!src) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    int n = cch < 0 ? shx_wstr_len(src) + 1 : cch;
    if (flags & LCMAP_SORTKEY) {
        /* 順序保存の擬似 sort key: 小文字化した UTF-16BE + 0x0001 + 元文字の大文字フラグ列 + 0 */
        int need = n * 2 + n + 2;
        if (cchDst == 0) return need;
        if (cchDst * 2 < need) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
        uint8_t* o = (uint8_t*)dst; int k = 0;
        for (int i = 0; i < n; i++) { uint32_t f = shimx_towlower(src[i]); o[k++] = (uint8_t)(f >> 8); o[k++] = (uint8_t)f; }
        o[k++] = 1;
        for (int i = 0; i < n; i++) o[k++] = (src[i] != shimx_towlower(src[i])) ? 2 : 1;
        o[k++] = 0;
        return k;
    }
    if (cchDst == 0) return n;
    if (cchDst < n) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
    for (int i = 0; i < n; i++) {
        uint32_t c = src[i];
        if (flags & LCMAP_LOWERCASE) c = shimx_towlower(c);
        else if (flags & LCMAP_UPPERCASE) c = shimx_towupper(c);
        dst[i] = (WCHAR)c;
    }
    return n;
}
int LCMapStringEx(LPCWSTR loc, DWORD flags, LPCWSTR src, int cch, LPWSTR dst, int cchDst, LPVOID v, LPVOID r, LPARAM_T l) {
    (void)loc; (void)v; (void)r; (void)l;
    return LCMapStringW(0x0400, flags, src, cch, dst, cchDst);
}

BOOL GetStringTypeW(DWORD type, LPCWSTR src, int cch, WORD* out) {
    if (!src || !out) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (cch < 0) cch = shx_wstr_len(src) + 1;
    for (int i = 0; i < cch; i++) {
        wint_t c = src[i];
        WORD v = 0;
        if (type == CT_CTYPE1) {
            if (iswupper(c)) v |= C1_UPPER | C1_ALPHA;
            else if (iswlower(c)) v |= C1_LOWER | C1_ALPHA;
            else if (iswalpha(c)) v |= C1_ALPHA;
            if (c < 0x80 && isdigit((int)c)) v |= C1_DIGIT;
            if (c < 0x80 && isxdigit((int)c)) v |= C1_XDIGIT;
            if (iswspace(c)) v |= C1_SPACE;
            if (c == ' ' || c == '\t') v |= C1_BLANK;
            if (iswcntrl(c)) v |= C1_CNTRL;
            if (iswpunct(c) && !iswalpha(c) && !(c < 0x80 && isdigit((int)c))) v |= C1_PUNCT;
            v |= C1_DEFINED;
        } else if (type == CT_CTYPE2) {
            v = iswalpha(c) ? 1 /*L*/ : (c < 0x80 && isdigit((int)c)) ? 3 /*EN*/ : iswspace(c) ? 0xC /*WS*/ : 0;
        } else if (type == CT_CTYPE3) {
            if (iswalpha(c)) v |= 0x8000;      /* C3_ALPHA */
        } else { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        out[i] = v;
    }
    return TRUE;
}

static LPWSTR char_xform(LPWSTR s, int upper) {
    if (shx_is_iptr((uintptr_t)s)) {            /* 単一文字モード (閾値は shimx_set_intptr_limit) */
        uint32_t c = (uint32_t)(uintptr_t)s;
        return (LPWSTR)(uintptr_t)(upper ? shimx_towupper(c) : shimx_towlower(c));
    }
    for (WCHAR* p = s; *p; p++) *p = (WCHAR)(upper ? shimx_towupper(*p) : shimx_towlower(*p));
    return s;
}
SHIMX_WEAK LPWSTR CharUpperW(LPWSTR s) { return char_xform(s, 1); }
SHIMX_WEAK LPWSTR CharLowerW(LPWSTR s) { return char_xform(s, 0); }
SHIMX_WEAK DWORD CharUpperBuffW(LPWSTR s, DWORD n) { for (DWORD i = 0; i < n; i++) s[i] = (WCHAR)shimx_towupper(s[i]); return n; }
SHIMX_WEAK DWORD CharLowerBuffW(LPWSTR s, DWORD n) { for (DWORD i = 0; i < n; i++) s[i] = (WCHAR)shimx_towlower(s[i]); return n; }
SHIMX_WEAK LPWSTR CharNextW(LPCWSTR s) {
    if (!*s) return (LPWSTR)s;
    if (s[0] >= 0xD800 && s[0] <= 0xDBFF && s[1] >= 0xDC00 && s[1] <= 0xDFFF) return (LPWSTR)s + 2;
    return (LPWSTR)s + 1;
}
SHIMX_WEAK LPSTR CharNextExA(WORD cp, LPCSTR s, DWORD flags) {
    (void)flags;
    if (!*s) return (LPSTR)s;
    if (IsDBCSLeadByteEx(cp, (BYTE)*s) && s[1]) return (LPSTR)(s + 2);
    return (LPSTR)(s + 1);
}
SHIMX_WEAK BOOL CharToOemBuffW(LPCWSTR src, LPSTR dst, DWORD n) {
    for (DWORD i = 0; i < n; i++) { int b = wc_to_sb(2, src[i]); dst[i] = (char)(b < 0 ? '?' : b); }
    return TRUE;
}

/* ---------------------------------------------------------------
 * コードページ情報
 * --------------------------------------------------------------- */
UINT GetACP(void) { return g_acp; }
UINT GetOEMCP(void) { return 437; }
BOOL IsValidCodePage(UINT cp) { cp = resolve_cp(cp); return cp == CP_UTF8 || cp == 932 || cp_sbcs_kind(cp) != 0; }
BOOL GetCPInfo(UINT cp, LPCPINFO info) {
    if (!info) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    UINT r = resolve_cp(cp);
    if (r != CP_UTF8 && r != 932 && !cp_sbcs_kind(r)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    memset(info, 0, sizeof(*info));
    info->MaxCharSize = (r == CP_UTF8) ? 4 : (r == 932) ? 2 : 1;
    info->DefaultChar[0] = '?';
    if (r == 932) { info->LeadByte[0] = 0x81; info->LeadByte[1] = 0x9F; info->LeadByte[2] = 0xE0; info->LeadByte[3] = 0xFC; }
    return TRUE;
}
BOOL GetCPInfoExW(UINT cp, DWORD flags, LPCPINFOEXW info) {
    (void)flags;
    if (!info) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    CPINFO ci;
    if (!GetCPInfo(cp, &ci)) return FALSE;
    memset(info, 0, sizeof(*info));
    info->MaxCharSize = ci.MaxCharSize;
    info->DefaultChar[0] = '?';
    memcpy(info->LeadByte, ci.LeadByte, sizeof ci.LeadByte);
    info->UnicodeDefaultChar = resolve_cp(cp) == 932 ? CP932_DEFAULT_WC : '?';
    info->CodePage = resolve_cp(cp);
    char nm[48]; if (info->CodePage == 932) snprintf(nm, sizeof nm, "932 (ANSI/OEM - Japanese Shift-JIS)"); else snprintf(nm, sizeof nm, "%u (ANSI)", info->CodePage);
    for (int i = 0; nm[i]; i++) info->CodePageName[i] = (WCHAR)nm[i];
    return TRUE;
}
BOOL IsDBCSLeadByteEx(UINT cp, BYTE c) { return resolve_cp(cp) == 932 && cp932_is_lead(c); }
int NormalizeString(int form, LPCWSTR src, int cch, LPWSTR dst, int cchDst) {
    (void)form;
    if (!src) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    int n = cch < 0 ? shx_wstr_len(src) + 1 : cch;
    if (cchDst == 0) return n;
    if (cchDst < n) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
    memcpy(dst, src, (size_t)n * 2);
    return n;
}
