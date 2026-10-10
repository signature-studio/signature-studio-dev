/* 時刻系 API (M4 timer.c の拡張): Tick/QPC/Sleep + SYSTEMTIME/FILETIME/DOS 時刻/TZ/日付書式。
 * ローカル時間は libc の localtime_r (emscripten が JS Date の TZ から設定) を使う。
 */
#include "shimx_internal.h"
#include <time.h>
#include <sched.h>

#define SHX_QPF 1000000LL
#define FT_EPOCH_DIFF 11644473600LL   /* 1601-01-01 → 1970-01-01 (秒) */

uint64_t GetTickCount64(void) {
    double now = shx_now_ms();
    return (uint64_t)(now > 0.0 ? now : 0.0);
}
DWORD GetTickCount(void) { return (DWORD)GetTickCount64(); }
DWORD timeGetTime(void) { return (DWORD)GetTickCount64(); }

BOOL QueryPerformanceCounter(LARGE_INTEGER* out) {
    if (!out) return FALSE;
    out->QuadPart = (int64_t)(shx_now_ms() * 1000.0);
    return TRUE;
}
BOOL QueryPerformanceFrequency(LARGE_INTEGER* out) {
    if (!out) return FALSE;
    out->QuadPart = SHX_QPF;
    return TRUE;
}

void Sleep(DWORD ms) {
    if (ms == 0) { sched_yield(); return; }
    static volatile uint32_t sleep_token;
    double deadline = shx_now_ms() + (double)ms;
    for (;;) {
        double remain = deadline - shx_now_ms();
        if (remain <= 0.0) break;
        shx_futex_wait(&sleep_token, sleep_token, remain);
    }
}
DWORD SleepEx(DWORD ms, BOOL alertable) { (void)alertable; Sleep(ms); return 0; }
BOOL SwitchToThread(void) { sched_yield(); return TRUE; }

/* ---------------------------------------------------------------
 * civil 日付 ↔ 日数 (Howard Hinnant のアルゴリズム)
 * --------------------------------------------------------------- */
static int64_t days_from_civil(int64_t y, unsigned m, unsigned d) {
    y -= m <= 2;
    int64_t era = (y >= 0 ? y : y - 399) / 400;
    unsigned yoe = (unsigned)(y - era * 400);
    unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + (int64_t)doe - 719468;
}
static void civil_from_days(int64_t z, int64_t* y, unsigned* m, unsigned* d) {
    z += 719468;
    int64_t era = (z >= 0 ? z : z - 146096) / 146097;
    unsigned doe = (unsigned)(z - era * 146097);
    unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int64_t yy = (int64_t)yoe + era * 400;
    unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    unsigned mp = (5 * doy + 2) / 153;
    *d = doy - (153 * mp + 2) / 5 + 1;
    *m = mp + (mp < 10 ? 3 : -9);
    *y = yy + (*m <= 2);
}

static uint64_t ft_to_u64(const FILETIME* ft) { return ((uint64_t)ft->dwHighDateTime << 32) | ft->dwLowDateTime; }
static void u64_to_ft(uint64_t v, FILETIME* ft) { ft->dwLowDateTime = (DWORD)v; ft->dwHighDateTime = (DWORD)(v >> 32); }

BOOL SystemTimeToFileTime(const SYSTEMTIME* st, FILETIME* ft) {
    if (!st || !ft || st->wYear < 1601 || st->wMonth < 1 || st->wMonth > 12 || st->wDay < 1 || st->wDay > 31 ||
        st->wHour > 23 || st->wMinute > 59 || st->wSecond > 59 || st->wMilliseconds > 999) {
        SetLastError(ERROR_INVALID_PARAMETER);
        return FALSE;
    }
    int64_t days = days_from_civil(st->wYear, st->wMonth, st->wDay);
    int64_t secs = days * 86400 + st->wHour * 3600 + st->wMinute * 60 + st->wSecond + FT_EPOCH_DIFF;
    if (secs < 0) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    u64_to_ft((uint64_t)secs * 10000000ull + (uint64_t)st->wMilliseconds * 10000ull, ft);
    return TRUE;
}

BOOL FileTimeToSystemTime(const FILETIME* ft, SYSTEMTIME* st) {
    if (!ft || !st) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    uint64_t v = ft_to_u64(ft);
    if (v >> 63) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    uint64_t ms = v / 10000ull;
    uint64_t secs = ms / 1000ull;
    st->wMilliseconds = (WORD)(ms % 1000ull);
    int64_t unixs = (int64_t)secs - FT_EPOCH_DIFF;
    int64_t days = unixs >= 0 ? unixs / 86400 : -((-unixs + 86399) / 86400);
    int64_t rem = unixs - days * 86400;
    int64_t y; unsigned m, d;
    civil_from_days(days, &y, &m, &d);
    st->wYear = (WORD)y; st->wMonth = (WORD)m; st->wDay = (WORD)d;
    st->wHour = (WORD)(rem / 3600); st->wMinute = (WORD)((rem % 3600) / 60); st->wSecond = (WORD)(rem % 60);
    int64_t dow = (days + 4) % 7; if (dow < 0) dow += 7;     /* 1970-01-01 = 木曜 */
    st->wDayOfWeek = (WORD)dow;
    return TRUE;
}

void GetSystemTimeAsFileTime(FILETIME* ft) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    u64_to_ft(((uint64_t)ts.tv_sec + FT_EPOCH_DIFF) * 10000000ull + (uint64_t)ts.tv_nsec / 100ull, ft);
}
void GetSystemTime(SYSTEMTIME* st) { FILETIME ft; GetSystemTimeAsFileTime(&ft); FileTimeToSystemTime(&ft, st); }

static int local_bias_min(time_t t) {   /* UTC - local (分)。localtime_r の gmtoff から */
    struct tm tmv;
    if (!localtime_r(&t, &tmv)) return 0;
    return -(int)(tmv.tm_gmtoff / 60);
}
void GetLocalTime(SYSTEMTIME* st) {
    FILETIME ft, lft;
    GetSystemTimeAsFileTime(&ft);
    time_t t = (time_t)(ft_to_u64(&ft) / 10000000ull) - FT_EPOCH_DIFF;
    int64_t bias = local_bias_min(t);
    u64_to_ft(ft_to_u64(&ft) - (uint64_t)(bias * 60ll * 10000000ll), &lft);
    FileTimeToSystemTime(&lft, st);
}
BOOL FileTimeToLocalFileTime(const FILETIME* ft, FILETIME* out) {
    time_t t = (time_t)(ft_to_u64(ft) / 10000000ull) - FT_EPOCH_DIFF;
    int64_t bias = local_bias_min(t);
    u64_to_ft(ft_to_u64(ft) - (uint64_t)(bias * 60ll * 10000000ll), out);
    return TRUE;
}
BOOL LocalFileTimeToFileTime(const FILETIME* ft, FILETIME* out) {
    time_t t = (time_t)(ft_to_u64(ft) / 10000000ull) - FT_EPOCH_DIFF;
    int64_t bias = local_bias_min(t);
    u64_to_ft(ft_to_u64(ft) + (uint64_t)(bias * 60ll * 10000000ll), out);
    return TRUE;
}

DWORD GetTimeZoneInformation(TIME_ZONE_INFORMATION* tz) {
    if (!tz) { SetLastError(ERROR_INVALID_PARAMETER); return 0xFFFFFFFFu; }
    memset(tz, 0, sizeof(*tz));
    time_t now = time(NULL);
    tz->Bias = local_bias_min(now);
    static const WCHAR std[] = {'S','t','a','n','d','a','r','d',' ','T','i','m','e',0};
    static const WCHAR dst[] = {'D','a','y','l','i','g','h','t',' ','T','i','m','e',0};
    memcpy(tz->StandardName, std, sizeof(std));
    memcpy(tz->DaylightName, dst, sizeof(dst));
    return 0;   /* TIME_ZONE_ID_UNKNOWN (DST 遷移情報なし) */
}
BOOL GetTimeZoneInformationForYear(WORD year, void* dtzi, TIME_ZONE_INFORMATION* tz) {
    (void)year; (void)dtzi;
    return GetTimeZoneInformation(tz) != 0xFFFFFFFFu;
}
BOOL SystemTimeToTzSpecificLocalTime(const TIME_ZONE_INFORMATION* tz, const SYSTEMTIME* u, SYSTEMTIME* l) {
    FILETIME ft;
    if (!u || !l || !SystemTimeToFileTime(u, &ft)) return FALSE;
    int64_t bias = tz ? tz->Bias + tz->StandardBias : 0;
    if (!tz) { time_t t = (time_t)(ft_to_u64(&ft) / 10000000ull) - FT_EPOCH_DIFF; bias = local_bias_min(t); }
    u64_to_ft(ft_to_u64(&ft) - (uint64_t)(bias * 60ll * 10000000ll), &ft);
    return FileTimeToSystemTime(&ft, l);
}
BOOL TzSpecificLocalTimeToSystemTime(const TIME_ZONE_INFORMATION* tz, const SYSTEMTIME* l, SYSTEMTIME* u) {
    FILETIME ft;
    if (!l || !u || !SystemTimeToFileTime(l, &ft)) return FALSE;
    int64_t bias = tz ? tz->Bias + tz->StandardBias : 0;
    if (!tz) { time_t t = (time_t)(ft_to_u64(&ft) / 10000000ull) - FT_EPOCH_DIFF; bias = local_bias_min(t); }
    u64_to_ft(ft_to_u64(&ft) + (uint64_t)(bias * 60ll * 10000000ll), &ft);
    return FileTimeToSystemTime(&ft, u);
}
LONG CompareFileTime(const FILETIME* a, const FILETIME* b) {
    uint64_t x = ft_to_u64(a), y = ft_to_u64(b);
    return x < y ? -1 : (x > y ? 1 : 0);
}

BOOL DosDateTimeToFileTime(WORD date, WORD time_, FILETIME* ft) {
    SYSTEMTIME st = {0};
    st.wYear = 1980 + ((date >> 9) & 0x7f);
    st.wMonth = (date >> 5) & 0xf;
    st.wDay = date & 0x1f;
    st.wHour = (time_ >> 11) & 0x1f;
    st.wMinute = (time_ >> 5) & 0x3f;
    st.wSecond = (time_ & 0x1f) * 2;
    return SystemTimeToFileTime(&st, ft);
}
BOOL FileTimeToDosDateTime(const FILETIME* ft, WORD* date, WORD* time_) {
    SYSTEMTIME st;
    if (!FileTimeToSystemTime(ft, &st) || st.wYear < 1980 || st.wYear > 2107) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (date) *date = (WORD)(((st.wYear - 1980) << 9) | (st.wMonth << 5) | st.wDay);
    if (time_) *time_ = (WORD)((st.wHour << 11) | (st.wMinute << 5) | (st.wSecond / 2));
    return TRUE;
}

/* ---------------------------------------------------------------
 * 日付/時刻書式 (en-US 固定の簡易版)
 * --------------------------------------------------------------- */
static const char* const k_mon[12] = {"January","February","March","April","May","June","July","August","September","October","November","December"};
static const char* const k_day[7] = {"Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"};

static int fmt_picture(const WCHAR* pic, const SYSTEMTIME* st, WCHAR* out, int cch) {
    char buf[256]; size_t n = 0;
    #define PUT(str) do { const char* _s = (str); while (*_s && n < sizeof(buf) - 1) buf[n++] = *_s++; } while (0)
    char tmp[32];
    for (const WCHAR* p = pic; *p;) {
        if (*p == '\'') {
            p++;
            while (*p && *p != '\'') { if (n < sizeof(buf) - 1) buf[n++] = (char)*p; p++; }
            if (*p) p++;
            continue;
        }
        int run = 1;
        while (p[run] == p[0]) run++;
        switch (*p) {
            case 'd': if (run >= 4) PUT(k_day[st->wDayOfWeek % 7]);
                      else if (run == 3) { strncpy(tmp, k_day[st->wDayOfWeek % 7], 3); tmp[3] = 0; PUT(tmp); }
                      else { snprintf(tmp, sizeof tmp, run == 2 ? "%02d" : "%d", st->wDay); PUT(tmp); } break;
            case 'M': if (run >= 4) PUT(k_mon[(st->wMonth + 11) % 12]);
                      else if (run == 3) { strncpy(tmp, k_mon[(st->wMonth + 11) % 12], 3); tmp[3] = 0; PUT(tmp); }
                      else { snprintf(tmp, sizeof tmp, run == 2 ? "%02d" : "%d", st->wMonth); PUT(tmp); } break;
            case 'y': if (run >= 4) snprintf(tmp, sizeof tmp, "%04d", st->wYear);
                      else snprintf(tmp, sizeof tmp, run == 2 ? "%02d" : "%d", st->wYear % 100);
                      PUT(tmp); break;
            case 'h': { int h = st->wHour % 12; if (!h) h = 12; snprintf(tmp, sizeof tmp, run >= 2 ? "%02d" : "%d", h); PUT(tmp); } break;
            case 'H': snprintf(tmp, sizeof tmp, run >= 2 ? "%02d" : "%d", st->wHour); PUT(tmp); break;
            case 'm': snprintf(tmp, sizeof tmp, run >= 2 ? "%02d" : "%d", st->wMinute); PUT(tmp); break;
            case 's': snprintf(tmp, sizeof tmp, run >= 2 ? "%02d" : "%d", st->wSecond); PUT(tmp); break;
            case 't': { const char* s = st->wHour < 12 ? "AM" : "PM"; if (run == 1) { tmp[0] = s[0]; tmp[1] = 0; PUT(tmp); } else PUT(s); } break;
            default: for (int i = 0; i < run; i++) if (n < sizeof(buf) - 1) buf[n++] = (char)*p; break;
        }
        p += run;
    }
    buf[n] = 0;
    #undef PUT
    int need = (int)n + 1;
    if (cch == 0) return need;
    if (cch < need) { SetLastError(ERROR_INSUFFICIENT_BUFFER); return 0; }
    for (size_t i = 0; i <= n; i++) out[i] = (WCHAR)(unsigned char)buf[i];
    return need;
}

static int fmt_common(const SYSTEMTIME* st, const WCHAR* fmt, const char* dflt, WCHAR* out, int cch) {
    SYSTEMTIME now;
    if (!st) { GetLocalTime(&now); st = &now; }
    WCHAR pic[128];
    if (!fmt) { size_t i = 0; for (; dflt[i]; i++) pic[i] = (WCHAR)dflt[i]; pic[i] = 0; fmt = pic; }
    return fmt_picture(fmt, st, out, cch);
}
int GetDateFormatW(LCID loc, DWORD flags, const SYSTEMTIME* st, LPCWSTR fmt, LPWSTR out, int cch) {
    (void)loc;
    return fmt_common(st, fmt, (flags & 2u) /* DATE_LONGDATE */ ? "dddd, MMMM d, yyyy" : "M/d/yyyy", out, cch);
}
int GetTimeFormatW(LCID loc, DWORD flags, const SYSTEMTIME* st, LPCWSTR fmt, LPWSTR out, int cch) {
    (void)loc;
    const char* d = (flags & 8u) ? ((flags & 2u) ? "HH:mm" : "HH:mm:ss") : ((flags & 2u) ? "h:mm tt" : "h:mm:ss tt");
    return fmt_common(st, fmt, d, out, cch);
}

/* ---------------------------------------------------------------
 * winmm の時刻系 (weak: tools/audio が上書き可)
 * --------------------------------------------------------------- */
SHIMX_WEAK UINT timeBeginPeriod(UINT ms) { (void)ms; return 0; }
SHIMX_WEAK UINT timeEndPeriod(UINT ms) { (void)ms; return 0; }
SHIMX_WEAK UINT timeGetDevCaps(void* caps, UINT n) {
    if (!caps || n < 8) return 11;   /* TIMERR_STRUCT */
    ((UINT*)caps)[0] = 1;            /* wPeriodMin */
    ((UINT*)caps)[1] = 1000000;      /* wPeriodMax */
    return 0;
}
