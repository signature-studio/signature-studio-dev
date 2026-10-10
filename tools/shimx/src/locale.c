/* ロケール (en-US 固定データ + LCID 名のみ数種) / FormatMessage。 */
#include "shimx_internal.h"
#include <strings.h>
#include <ctype.h>

static LCID g_thread_lcid = 0;

typedef struct { LCID id; const char* name; const char* iso639; const char* iso3166; const char* eng; const char* native; } LocName;
static const LocName k_locs[] = {
    { 0x0409, "en-US", "en", "US", "English (United States)", "English (United States)" },
    { 0x0809, "en-GB", "en", "GB", "English (United Kingdom)", "English (United Kingdom)" },
    { 0x0411, "ja-JP", "ja", "JP", "Japanese (Japan)", "\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E (\xE6\x97\xA5\xE6\x9C\xAC)" },
    { 0x0407, "de-DE", "de", "DE", "German (Germany)", "Deutsch (Deutschland)" },
    { 0x040C, "fr-FR", "fr", "FR", "French (France)", "fran\xC3\xA7" "ais (France)" },
    { 0x0C0A, "es-ES", "es", "ES", "Spanish (Spain)", "espa\xC3\xB1ol (Espa\xC3\xB1" "a)" },
};
static LCID g_user_lcid = 0x0409;
void shimx_set_locale(LCID l) { g_user_lcid = l; }

static const LocName* loc_find(LCID id) {
    if (id == LOCALE_USER_DEFAULT || id == LOCALE_SYSTEM_DEFAULT || id == LOCALE_NEUTRAL || id == 0x0400) id = g_user_lcid;
    for (size_t i = 0; i < sizeof k_locs / sizeof k_locs[0]; i++) if (k_locs[i].id == id) return &k_locs[i];
    return NULL;
}

LCID GetUserDefaultLCID(void) { return g_user_lcid; }
LCID GetThreadLocale(void) { return g_thread_lcid ? g_thread_lcid : g_user_lcid; }
BOOL SetThreadLocale(LCID l) { g_thread_lcid = l; return TRUE; }
LANGID GetSystemDefaultUILanguage(void) { return (LANGID)g_user_lcid; }
LANGID GetUserDefaultUILanguage(void) { return (LANGID)g_user_lcid; }
BOOL IsValidLocale(LCID l, DWORD flags) { (void)flags; return loc_find(l) != NULL; }
LCID LocaleNameToLCID(LPCWSTR name, DWORD flags) {
    (void)flags;
    if (!name) return g_user_lcid;
    for (size_t i = 0; i < sizeof k_locs / sizeof k_locs[0]; i++) {
        const char* n = k_locs[i].name; int j = 0;
        while (n[j] && name[j] == (WCHAR)n[j]) j++;
        if (!n[j] && !name[j]) return k_locs[i].id;
    }
    SetLastError(ERROR_INVALID_PARAMETER);
    return 0;
}
int GetSystemDefaultLocaleName(LPWSTR out, int cch) {
    const LocName* l = loc_find(0x0400);
    int n = (int)strlen(l->name) + 1;
    if (cch < n) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
    for (int i = 0; i < n; i++) out[i] = (WCHAR)l->name[i];
    return n;
}
BOOL GetUserPreferredUILanguages(DWORD flags, ULONG* num, LPWSTR buf, ULONG* cch) {
    (void)flags;
    const LocName* l = loc_find(0x0400);
    ULONG n = (ULONG)strlen(l->name) + 2;       /* multi-sz: "en-US\0\0" */
    if (num) *num = 1;
    if (!cch) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (!buf) { *cch = n; return TRUE; }
    if (*cch < n) { *cch = n; SetLastError(ERROR_INSUFFICIENT_BUFFER); return FALSE; }
    for (ULONG i = 0; l->name[i]; i++) buf[i] = (WCHAR)l->name[i];
    buf[n - 2] = 0; buf[n - 1] = 0;
    *cch = n;
    return TRUE;
}

static const char* const k_dayn[7] = {"Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"};
static const char* const k_dayab[7] = {"Mon","Tue","Wed","Thu","Fri","Sat","Sun"};
static const char* const k_monn[12] = {"January","February","March","April","May","June","July","August","September","October","November","December"};
static const char* const k_monab[12] = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"};

/* 文字列値を返す。numeric: LOCALE_RETURN_NUMBER 用に数値も設定 (-1: 文字列のみ) */
static const char* loc_value(const LocName* l, LCTYPE t, char* tmp, long* num) {
    *num = -1;
    t &= ~(LOCALE_NOUSEROVERRIDE | LOCALE_RETURN_NUMBER);
    switch (t) {
        case 0x01: snprintf(tmp, 16, "%04x", l->id); *num = l->id; return tmp;       /* ILANGUAGE */
        case 0x02: return l->eng;                                                    /* SLANGUAGE */
        case 0x1001: return l->eng;                                                  /* SENGLANGUAGE */
        case 0x03: snprintf(tmp, 16, "%s%c", l->iso639, 0); { for (int i = 0; tmp[i]; i++) tmp[i] = (char)toupper((unsigned char)tmp[i]); } return tmp; /* SABBREVLANGNAME */
        case 0x04: return l->native;                                                 /* SNATIVELANGNAME */
        case 0x05: *num = 1; return "1";                                             /* ICOUNTRY */
        case 0x06: case 0x1002: return l->eng;                                       /* SCOUNTRY/SENGCOUNTRY */
        case 0x07: return l->iso3166;
        case 0x08: return l->native;
        case 0x09: snprintf(tmp, 16, "%04x", l->id); return tmp;
        case 0x0A: *num = 1; return "1";
        case 0x0B: *num = 437; return "437";                                         /* IDEFAULTCODEPAGE */
        case 0x1004: *num = 1252; return "1252";                                     /* IDEFAULTANSICODEPAGE */
        case 0x0C: return ",";                                                       /* SLIST */
        case 0x0D: *num = 1; return "1";                                             /* IMEASURE */
        case 0x0E: return ".";                                                       /* SDECIMAL */
        case 0x0F: return ",";                                                       /* STHOUSAND */
        case 0x10: return "3;0";                                                     /* SGROUPING */
        case 0x11: *num = 2; return "2";                                             /* IDIGITS */
        case 0x12: *num = 1; return "1";                                             /* ILZERO */
        case 0x1010: *num = 1; return "1";                                           /* INEGNUMBER */
        case 0x13: return "0123456789";
        case 0x14: return "$";
        case 0x15: return "USD";
        case 0x16: return ".";
        case 0x17: return ",";
        case 0x18: return "3;0";
        case 0x19: *num = 2; return "2";
        case 0x1B: *num = 0; return "0";
        case 0x1C: *num = 0; return "0";
        case 0x1D: return "/";                                                       /* SDATE */
        case 0x1E: return ":";                                                       /* STIME */
        case 0x1F: return "M/d/yyyy";                                                /* SSHORTDATE */
        case 0x20: return "dddd, MMMM d, yyyy";                                      /* SLONGDATE */
        case 0x1003: return "h:mm:ss tt";                                            /* STIMEFORMAT */
        case 0x21: *num = 0; return "0";                                             /* IDATE */
        case 0x22: *num = 0; return "0";
        case 0x23: *num = 0; return "0";                                             /* ITIME */
        case 0x1005: *num = 0; return "0";
        case 0x24: *num = 1; return "1";
        case 0x25: *num = 0; return "0";
        case 0x26: *num = 0; return "0";
        case 0x27: *num = 0; return "0";
        case 0x28: return "AM";
        case 0x29: return "PM";
        case 0x1009: *num = 1; return "1";                                           /* ICALENDARTYPE */
        case 0x100C: *num = 6; return "6";                                           /* IFIRSTDAYOFWEEK (日曜=6) */
        case 0x100D: *num = 0; return "0";
        case 0x50: return "";
        case 0x51: return "-";
        case 0x59: return l->iso639;
        case 0x5A: return l->iso3166;
        case 0x5C: return l->name;                                                   /* SNAME */
        case 0x72: return l->eng;
        case 0x73: return l->native;
        default: break;
    }
    if (t >= 0x2A && t <= 0x30) return k_dayn[t - 0x2A];
    if (t >= 0x31 && t <= 0x37) return k_dayab[t - 0x31];
    if (t >= 0x38 && t <= 0x43) return k_monn[t - 0x38];
    if (t >= 0x44 && t <= 0x4F) return k_monab[t - 0x44];
    if (t == 0x100E || t == 0x100F) return "";
    return NULL;
}

int GetLocaleInfoW(LCID loc, LCTYPE type, LPWSTR out, int cch) {
    const LocName* l = loc_find(loc);
    if (!l) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    char tmp[32]; long num;
    const char* v = loc_value(l, type, tmp, &num);
    if (!v) { SetLastError(ERROR_INVALID_FLAGS); return 0; }
    if (type & LOCALE_RETURN_NUMBER) {
        if (num < 0) { SetLastError(ERROR_INVALID_FLAGS); return 0; }
        if (cch == 0) return 2;
        if (cch < 2) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
        *(DWORD*)out = (DWORD)num;
        return 2;
    }
    int w = shimx_utf8_to_utf16(v, -1, NULL, 0);
    if (cch == 0) return w + 1;
    if (cch < w + 1) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
    shimx_utf8_to_utf16(v, -1, out, (size_t)cch);
    out[w] = 0;
    return w + 1;
}
int GetLocaleInfoEx(LPCWSTR name, LCTYPE type, LPWSTR out, int cch) {
    return GetLocaleInfoW(name ? LocaleNameToLCID(name, 0) : 0x0400, type, out, cch);
}

BOOL EnumSystemLocalesW(LOCALE_ENUMPROCW cb, DWORD flags) {
    (void)flags;
    if (!cb) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    for (size_t i = 0; i < sizeof k_locs / sizeof k_locs[0]; i++) {
        WCHAR s[16]; char t[16]; snprintf(t, sizeof t, "%08x", k_locs[i].id);
        for (int j = 0; j < 9; j++) s[j] = (WCHAR)t[j];
        if (!cb(s)) break;
    }
    return TRUE;
}

BOOL EnumCalendarInfoW(CALINFO_ENUMPROCW cb, LCID loc, DWORD cal, DWORD type) {
    (void)loc; (void)cal;
    if (!cb) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    const char* v = NULL; char tmp[32];
    if (type >= 7 && type <= 13) v = k_dayn[type - 7];
    else if (type >= 14 && type <= 20) v = k_dayab[type - 14];
    else if (type >= 21 && type <= 32) v = k_monn[type - 21];
    else if (type == 33 || type == 46) v = "";
    else if (type >= 34 && type <= 45) v = k_monab[type - 34];
    else if (type == 5) v = "M/d/yyyy";
    else if (type == 6) v = "dddd, MMMM d, yyyy";
    else if (type == 47) v = "MMMM yyyy";
    else if (type == 48) v = "2029";
    else if (type == 2) v = "Gregorian Calendar";
    else if (type == 1) { snprintf(tmp, sizeof tmp, "1"); v = tmp; }
    else if (type == 4) v = "A.D.";
    if (!v) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    WCHAR w[64];
    int n = shimx_utf8_to_utf16(v, -1, w, 63);
    w[n < 0 ? 0 : n] = 0;
    cb(w);
    return TRUE;
}

/* ---------------------------------------------------------------
 * FormatMessage
 * --------------------------------------------------------------- */
typedef struct { DWORD id; const char* text; } SysMsg;
static const SysMsg k_sysmsg[] = {
    {0, "The operation completed successfully."}, {1, "Incorrect function."},
    {2, "The system cannot find the file specified."}, {3, "The system cannot find the path specified."},
    {4, "The system cannot open the file."}, {5, "Access is denied."}, {6, "The handle is invalid."},
    {8, "Not enough memory resources are available to process this command."},
    {14, "Not enough storage is available to complete this operation."},
    {18, "There are no more files."}, {32, "The process cannot access the file because it is being used by another process."},
    {38, "Reached the end of the file."}, {50, "The request is not supported."}, {80, "The file exists."},
    {87, "The parameter is incorrect."}, {122, "The data area passed to a system call is too small."},
    {123, "The filename, directory name, or volume label syntax is incorrect."},
    {126, "The specified module could not be found."}, {127, "The specified procedure could not be found."},
    {145, "The directory is not empty."}, {183, "Cannot create a file when that file already exists."},
    {193, "%1 is not a valid Win32 application."}, {234, "More data is available."}, {259, "No more data is available."},
    {1168, "Element not found."}, {1223, "The operation was canceled by the user."},
    {1314, "A required privilege is not held by the client."}, {1460, "This operation returned because the timeout period expired."},
    {1812, "The specified image file did not contain a resource section."},
};

static int fm_append(WCHAR** buf, size_t* len, size_t* cap, const WCHAR* s, size_t n) {
    if (*len + n + 1 > *cap) {
        size_t nc = (*cap ? *cap * 2 : 128);
        while (nc < *len + n + 1) nc *= 2;
        WCHAR* nb = (WCHAR*)realloc(*buf, nc * 2);
        if (!nb) return -1;
        *buf = nb; *cap = nc;
    }
    memcpy(*buf + *len, s, n * 2);
    *len += n;
    (*buf)[*len] = 0;
    return 0;
}
static int fm_append_a(WCHAR** buf, size_t* len, size_t* cap, const char* s) {
    size_t n = strlen(s);
    WCHAR tmp[512];
    while (n) {
        size_t c = n > 500 ? 500 : n;
        int w = shimx_utf8_to_utf16(s, (int)c, tmp, 512);
        if (w < 0) w = 0;
        if (fm_append(buf, len, cap, tmp, (size_t)w)) return -1;
        s += c; n -= c;
    }
    return 0;
}

DWORD FormatMessageW(DWORD flags, LPCVOID src, DWORD msgId, DWORD langId, LPWSTR out, DWORD n, void* args) {
    (void)langId;
    shx_ensure_init();
    const WCHAR* fmt = NULL; WCHAR* fmtOwn = NULL;
    if (flags & FORMAT_MESSAGE_FROM_STRING) fmt = (const WCHAR*)src;
    else if (flags & FORMAT_MESSAGE_FROM_SYSTEM) {
        const char* t = NULL;
        for (size_t i = 0; i < sizeof k_sysmsg / sizeof k_sysmsg[0]; i++) if (k_sysmsg[i].id == (msgId & 0xFFFF)) t = k_sysmsg[i].text;
        if (!t) { SetLastError(317 /* ERROR_MR_MID_NOT_FOUND */); return 0; }
        char tmp[256]; snprintf(tmp, sizeof tmp, "%s\r\n", t);
        fmtOwn = shx_wcsdup_utf8(tmp); fmt = fmtOwn;
    } else { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (!fmt) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    const uint64_t* av = (flags & FORMAT_MESSAGE_ARGUMENT_ARRAY) ? (const uint64_t*)args : NULL;   /* Win64: 8B 要素 */
    if (!(flags & FORMAT_MESSAGE_IGNORE_INSERTS) && !av && args) {
        free(fmtOwn);
        shim_unimplemented("FormatMessage (va_list 引数: FORMAT_MESSAGE_ARGUMENT_ARRAY 以外)");
    }
    WCHAR* res = NULL; size_t len = 0, cap = 0;
    int ignoreInserts = (flags & FORMAT_MESSAGE_IGNORE_INSERTS) != 0;
    for (const WCHAR* p = fmt; *p; ) {
        if (*p != '%') { if (fm_append(&res, &len, &cap, p, 1)) break; p++; continue; }
        p++;
        if (*p >= '1' && *p <= '9' && !ignoreInserts) {
            int idx = 0;
            while (*p >= '0' && *p <= '9') idx = idx * 10 + (*p++ - '0');
            char spec = 's';
            if (*p == '!') {
                p++;
                char f[16]; int k = 0;
                while (*p && *p != '!' && k < 15) f[k++] = (char)*p++;
                f[k] = 0; if (*p == '!') p++;
                spec = k ? f[k - 1] : 's';
            }
            uint64_t a = (av && idx >= 1) ? av[idx - 1] : 0;
            char tmp[64];
            if (spec == 's' || spec == 'S') {
                if (!a) { fm_append_a(&res, &len, &cap, "(null)"); }
                else if (spec == 's') fm_append(&res, &len, &cap, (const WCHAR*)(uintptr_t)a, (size_t)shx_wstr_len((const WCHAR*)(uintptr_t)a));
                else fm_append_a(&res, &len, &cap, (const char*)(uintptr_t)a);
            } else {
                if (spec == 'd' || spec == 'i') snprintf(tmp, sizeof tmp, "%d", (int)(int32_t)a);
                else if (spec == 'u') snprintf(tmp, sizeof tmp, "%u", (unsigned)a);
                else if (spec == 'x') snprintf(tmp, sizeof tmp, "%x", (unsigned)a);
                else if (spec == 'X') snprintf(tmp, sizeof tmp, "%X", (unsigned)a);
                else if (spec == 'c') snprintf(tmp, sizeof tmp, "%c", (int)a);
                else snprintf(tmp, sizeof tmp, "%llu", (unsigned long long)a);
                fm_append_a(&res, &len, &cap, tmp);
            }
            continue;
        }
        switch (*p) {
            case 'n': fm_append_a(&res, &len, &cap, "\r\n"); p++; break;
            case 'r': fm_append_a(&res, &len, &cap, "\r"); p++; break;
            case 't': fm_append_a(&res, &len, &cap, "\t"); p++; break;
            case '0': p = fmt + shx_wstr_len(fmt); break;
            case '%': fm_append_a(&res, &len, &cap, "%"); p++; break;
            case '.': fm_append_a(&res, &len, &cap, "."); p++; break;
            case '!': fm_append_a(&res, &len, &cap, "!"); p++; break;
            case ' ': fm_append_a(&res, &len, &cap, " "); p++; break;
            default:  fm_append_a(&res, &len, &cap, "%"); break;      /* 未知: '%' をそのまま出力して続行 */
        }
    }
    free(fmtOwn);
    if (!res) { res = (WCHAR*)calloc(1, 2); }
    if (!(flags & FORMAT_MESSAGE_MAX_WIDTH_MASK) || 1) {
        /* 末尾の "\r\n" は FROM_SYSTEM で付いたものをそのまま返す (Win と同様)。FROM_STRING は触らない */
    }
    DWORD rc;
    if (flags & FORMAT_MESSAGE_ALLOCATE_BUFFER) {
        HLOCAL h = LocalAlloc(0, (len + 1) * 2);
        if (!h) { free(res); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
        memcpy((void*)h, res, (len + 1) * 2);
        *(LPWSTR*)out = (LPWSTR)h;
        rc = (DWORD)len;
    } else {
        if (!out || n < len + 1) { free(res); SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
        memcpy(out, res, (len + 1) * 2);
        rc = (DWORD)len;
    }
    free(res);
    SetLastError(ERROR_SUCCESS);
    return rc;
}

DWORD FormatMessageA(DWORD flags, LPCVOID src, DWORD msgId, DWORD langId, LPSTR out, DWORD n, void* args) {
    const WCHAR* wsrc = NULL; WCHAR* own = NULL;
    if (flags & FORMAT_MESSAGE_FROM_STRING) {
        const char* s = (const char*)src;
        own = (WCHAR*)malloc((strlen(s) * 2 + 2));
        int w = MultiByteToWideChar(CP_ACP, 0, s, (int)strlen(s) + 1, own, (int)strlen(s) * 2 + 1);
        (void)w; wsrc = own;
    }
    WCHAR* wbuf = NULL; DWORD wl;
    DWORD flagsW = (flags | FORMAT_MESSAGE_ALLOCATE_BUFFER);
    wl = FormatMessageW(flagsW, wsrc ? wsrc : src, msgId, langId, (LPWSTR)&wbuf, 0, args);
    free(own);
    if (!wl || !wbuf) return 0;
    int need = WideCharToMultiByte(CP_ACP, 0, wbuf, (int)wl + 1, NULL, 0, NULL, NULL);
    DWORD rc = 0;
    if (flags & FORMAT_MESSAGE_ALLOCATE_BUFFER) {
        HLOCAL h = LocalAlloc(0, (size_t)need);
        if (h) { WideCharToMultiByte(CP_ACP, 0, wbuf, (int)wl + 1, (char*)h, need, NULL, NULL); *(LPSTR*)out = (LPSTR)h; rc = (DWORD)(need - 1); }
    } else if (out && n >= (DWORD)need) {
        WideCharToMultiByte(CP_ACP, 0, wbuf, (int)wl + 1, out, need, NULL, NULL);
        rc = (DWORD)(need - 1);
    } else SetLastError(ERROR_INSUFFICIENT_BUFFER);
    LocalFree((HLOCAL)wbuf);
    return rc;
}

void shx_locale_init(void) {}
