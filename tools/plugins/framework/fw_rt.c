/* fw_rt.c — P0a (CAB-194) Delphi framework lift の runtime。
 * 構成は tools/icall/rt/icall_rt.c (OTT bit-exact 実績) + tools/m11/m11_win.c/m11_rt.c (起動 shim) の
 * Balance (block18983 / ImageBase 0x400000) 版。shift 無し: PE VA = wasm アドレス。
 *   BLK (memory-ABI block) = 0x8A1000 (fw_map.json blk; fw_image.bin が敷設済み)
 *   image   = 0x400000..0xD02000 (node ハーネスが fw_image.bin を HEAPU8 に敷設)
 *   import  = 0xE000000.. (IAT 合成 VA; fw_image.py が IAT を差し替え, fw_table.py が imp_<name> を接続)
 * 全 lifted 関数は uniform ABI (引数/戻り値は BLK 経由 or RetDec が再接続した直接 call)。
 * 未登録 target / 未実装 import / decode 漏れ関数は site VA or 名前を表示して fail-fast。
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten.h>

#ifndef FW_BLK
#define FW_BLK 0x8A1000u
#endif
#define BLKQ(off) (*(volatile uint64_t *)(uintptr_t)(FW_BLK + (off)))

extern const uint32_t icall_tbl_va[];
extern long long (*const icall_tbl_fn[])(void);
extern const unsigned icall_tbl_n;
extern const uint32_t icall_cfg_va[];
extern const unsigned icall_cfg_n;

/* ---- probe / fail-fast ---- */
static unsigned long long g_dispatch_cnt, g_last_site, g_last_target, g_ff_cnt;
static char g_ff_msg[256];

EMSCRIPTEN_KEEPALIVE void fw_ff(const char *what) {
    g_ff_cnt++;
    snprintf(g_ff_msg, sizeof g_ff_msg, "%.200s", what ? what : "?");
    fprintf(stderr, "[fw][FAIL-FAST] %s (site VA 0x%llx, target 0x%llx)\n",
            what ? what : "?", (unsigned long long)g_last_site, (unsigned long long)g_last_target);
    fflush(stderr);
    emscripten_force_exit(101);
}
EMSCRIPTEN_KEEPALIVE const char *fw_ff_msg(void) { return g_ff_msg; }
EMSCRIPTEN_KEEPALIVE unsigned long long fw_dispatch_count(void) { return g_dispatch_cnt; }
EMSCRIPTEN_KEEPALIVE unsigned long long fw_last_site(void) { return g_last_site; }
EMSCRIPTEN_KEEPALIVE unsigned long long fw_last_target(void) { return g_last_target; }
EMSCRIPTEN_KEEPALIVE unsigned long long fw_ff_count(void) { return g_ff_cnt; }

static long long (*lookup(uint32_t va))(void) {
    unsigned lo = 0, hi = icall_tbl_n;
    while (lo < hi) {
        unsigned mid = (lo + hi) / 2;
        if (icall_tbl_va[mid] < va) lo = mid + 1; else hi = mid;
    }
    if (lo < icall_tbl_n && icall_tbl_va[lo] == va) return icall_tbl_fn[lo];
    return 0;
}

void __icall_dispatch(uint64_t site) {
    uint64_t t = BLKQ(0);
    for (unsigned k = 0; k < icall_cfg_n; k++)
        if ((uint32_t)t == icall_cfg_va[k]) { t = BLKQ(0x90); break; }
    long long (*f)(void) = lookup((uint32_t)t);
    if (!f || (t >> 32)) {
        /* CAB-195: host shim 連鎖 (CreatePlugInstance → ctor) では, Delphi framework が
         * Delphi RTL の例外フック (0x710030 = RaiseException thunk 0x404c00, 0x710038 = RtlUnwind
         * thunk 0x404c10, 0x710040 = 0x43d940: REPORT_2008 §8) が未初期化 (target 0) のまま呼ばれる。
         * Phase B は DllMain/InitUnits を通らないので呼出は不能。
         * 連鎖検証を止めないため fail-soft (0 を返し記録) にする。
         * fw_ff ではない (exit しない) ので回復可能。 */
        g_dispatch_cnt++;
        g_last_site = site;
        g_last_target = t;
        static unsigned soft = 0;
        if (soft < 40) {
            soft++;
            fprintf(stderr, "[fw][hostshim] soft-miss indirect target 0x%llx at site VA 0x%llx (FL export table?)\n",
                    (unsigned long long)t, (unsigned long long)site);
            fflush(stderr);
        }
        BLKQ(0x80) = 0;
        return;
    }
    g_dispatch_cnt++;
    g_last_site = site;
    g_last_target = t;
    { static int tr = 0; if (tr < 40) { tr++; fprintf(stderr, "[dispatch] site=0x%llx -> target=0x%llx\n",
        (unsigned long long)site, (unsigned long long)t); } }
    BLKQ(0x80) = (uint64_t)f();     /* lifted 関数の wasm 戻り値 (rax) を BLK 経由で渡す */
}

/* fw_boot 用: BLK 現状のままで lifted 関数 (VA) を呼び, rax を返す */
long long fw_call_cur(uint32_t va) {
    long long (*f)(void) = lookup(va);
    if (!f) {
        fprintf(stderr, "[fw] FAIL-FAST: fw_call_cur: unknown VA 0x%x\n", va);
        fflush(stderr);
        emscripten_force_exit(103);
    }
    g_dispatch_cnt++;
    g_last_site = 0;
    g_last_target = va;
    return f();
}


#include "fw_rt.h"

/* ---- Local 系, Global 系メモリ API (RetDec が IAT thunk を名前解決して直接 call する) ---- */
void *LocalAlloc(unsigned flags, unsigned bytes) { return HeapAlloc(0, flags, bytes); }
void *LocalReAlloc(void *p, unsigned bytes, unsigned flags) { (void)flags; return HeapReAlloc(0, 0, p, bytes); }
void *LocalFree(void *p) { HeapFree(0, 0, p); return p; }
void *LocalLock(void *p) { return p; }
int LocalUnlock(void *p) { (void)p; return 1; }
unsigned LocalSize(void *p) { (void)p; return 0; }
void *GlobalAlloc(unsigned flags, unsigned bytes) { return HeapAlloc(0, flags, bytes); }
void *GlobalReAlloc(void *p, unsigned bytes, unsigned flags) { (void)flags; return HeapReAlloc(0, 0, p, bytes); }
void *GlobalFree(void *p) { HeapFree(0, 0, p); return p; }
void *GlobalLock(void *p) { return p; }
int GlobalUnlock(void *p) { (void)p; return 1; }
unsigned GlobalSize(void *p) { (void)p; return 0; }
unsigned GlobalFlags(void *p) { (void)p; return 0; }
void *GlobalHandle(void *p) { return p; }


/* GetProcAddress: headless では解決できない DLL エクスポート → fail-fast でなく
 * 「名前のハッシュを返す」偽ポインタを返す (呼び出し先が dispatch 表に無ければ
 * site VA 付きで可視化される) */
unsigned fw_name_hash(const char *s) { unsigned h = 2166136261u; while (*s) { h ^= (unsigned char)*s++; h *= 16777619u; } return h; }
void *GetProcAddress(void *h, const char *name) {
    (void)h;
    unsigned hh = 0x40000000u | (fw_name_hash(name) >> 2);
    fprintf(stderr, "[fw][GetProcAddress] %s -> 0x%x\n", name ? name : "(null)", hh);
    return (void *)(uintptr_t)hh;
}


/* LoadStringW: リソース文字列は無い → 0 (空文字) を返す (m11_win.c 実績) */
unsigned LoadStringW(void *h, unsigned id, unsigned short *buf, unsigned n) {
    (void)h; (void)id;
    if (buf && n) buf[0] = 0;
    return 0;
}


/* MessageBoxA/W: headless では表示しない (内容を stderr に出す) → IDOK (1) を返す */
unsigned MessageBoxA(void *h, const char *text, const char *cap, unsigned type) {
    fprintf(stderr, "[fw][MessageBoxA] %s: %s\n", cap ? cap : "", text ? text : "");
    return 1;
}
unsigned MessageBoxW(void *h, const unsigned short *text, const unsigned short *cap, unsigned type) {
    (void)h; (void)type;
    fprintf(stderr, "[fw][MessageBoxW] (text omitted)\n");
    return 1;
}

/* comis/ucomis → EFLAGS(AH 形式: bit0 CF, bit2 PF, bit6 ZF) を BLK+0xB0 へ (icall_rt.c 同一) */
void __icall_comis(void) {
    uint64_t a = BLKQ(0xA0), b = BLKQ(0xA8);
    uint32_t k = (uint32_t)BLKQ(0xB8);
    double x, y;
    if (k < 2) { memcpy(&x, &a, 8); memcpy(&y, &b, 8); }
    else {
        float fx, fy;
        uint32_t ia = (uint32_t)a, ib = (uint32_t)b;
        memcpy(&fx, &ia, 4); memcpy(&fy, &ib, 4);
        x = fx; y = fy;
    }
    uint8_t fl;
    if (x != x || y != y) fl = 0x01 | 0x04 | 0x40;
    else if (x > y) fl = 0;
    else if (x < y) fl = 0x01;
    else fl = 0x40;
    BLKQ(0xB0) = fl;
}

/* ---- x87 (frontend fpr) — f80→f64 近似 (本命は CAB-196 P0c の lowering pass) ----
 * IR のシンボルは RetDec 由来の dot 付き名 (__frontend_reg_load.fpr) なので asm label で接続する */
static double g_fpr[8];
double fw_fpr_load(uint32_t idx) { return g_fpr[idx & 7]; }
void fw_fpr_store(uint32_t idx, double v) { g_fpr[idx & 7] = v; }
double __frontend_reg_load_fpr(uint32_t idx) __asm__("__frontend_reg_load.fpr");
void __frontend_reg_store_fpr(uint32_t idx, double v) __asm__("__frontend_reg_store.fpr");
__attribute__((used)) double __frontend_reg_load_fpr(uint32_t idx) { return fw_fpr_load(idx); }
__attribute__((used)) void __frontend_reg_store_fpr(uint32_t idx, double v) { fw_fpr_store(idx, v); }

/* ---- TLS (gs:[0x58] = ThreadLocalStoragePointer) ---- */
static uint64_t g_tls_slots[128];
static uint32_t g_tls_next = 1;
int TlsAlloc(void) { return (int)(g_tls_next++); }
int TlsFree(int i) { (void)i; return 1; }
void *TlsGetValue(int i) { return (i >= 0 && i < 128) ? (void *)(uintptr_t)g_tls_slots[i] : 0; }
int TlsSetValue(int i, void *v) { if (i >= 0 && i < 128) { g_tls_slots[i] = (uint64_t)(uintptr_t)v; return 1; } return 0; }
int64_t __readgsqword(int64_t off) {
    if (off == 88) return (int64_t)(uintptr_t)g_tls_slots;    /* TEB->ThreadLocalStoragePointer */
    if (off == 48) return (int64_t)(uintptr_t)g_tls_slots;    /* TEB->Self 相当 (fallback) */
    fw_ff("__readgsqword other offset");
    return 0;
}

/* ---- Virtual memory shim (m11_rt.c 規約: 要求ごと calloc + 64KB align) ---- */
static unsigned long long g_va_used, g_va_calls;
EMSCRIPTEN_KEEPALIVE
void *VirtualAlloc(void *addr, unsigned size, unsigned type, unsigned protect) {
    (void)type; (void)protect;
    g_va_calls++;
    if (addr) return addr;
    unsigned long long need = ((unsigned long long)size + 0xffffULL) & ~0xffffULL;
    unsigned char *raw = (unsigned char *)calloc(1, (size_t)(need + 0x10000ULL));
    if (!raw) { fprintf(stderr, "[fw][VA] OOM want=%.1fMB\n", need / 1e6); return 0; }
    unsigned long long p = (unsigned long long)raw;
    unsigned long long offv = (0x10000ULL - (p & 0xffffULL)) & 0xffffULL;
    g_va_used += need;
    return raw + offv;
}
EMSCRIPTEN_KEEPALIVE int64_t fw_va_used(void) { return (int64_t)g_va_used; }
EMSCRIPTEN_KEEPALIVE int64_t fw_va_calls(void) { return (int64_t)g_va_calls; }
int VirtualFree(void *p, unsigned size, unsigned type) { (void)p; (void)size; (void)type; return 1; }
int VirtualProtect(void *p, unsigned size, unsigned prot, unsigned *old) { (void)p; (void)size; (void)prot; if (old) *old = 0; return 1; }
unsigned VirtualQuery(void *p, void *buf, unsigned len) { (void)p; (void)buf; return len; }

/* ---- Win32: 初期化経路の実装 (m11_win.c / icall_rt.c から Balance 用に写し+拡張) ---- */
static unsigned char g_dummy_heap[64];
static unsigned long long g_alloc_cnt, g_alloc_bytes;
void *GetProcessHeap(void) { return g_dummy_heap; }
static void *allog(void *p, unsigned long long n) { g_alloc_cnt++; g_alloc_bytes += n; return p; }
EMSCRIPTEN_KEEPALIVE int64_t fw_alloc_count(void) { return (int64_t)g_alloc_cnt; }
EMSCRIPTEN_KEEPALIVE int64_t fw_alloc_bytes(void) { return (int64_t)g_alloc_bytes; }
void *HeapAlloc(void *h, unsigned flags, unsigned long long bytes) {
    (void)h; void *p = malloc((size_t)(bytes ? bytes : 1));
    if ((flags & 8) && p) memset(p, 0, (size_t)bytes);
    return allog(p, bytes);
}
int HeapFree(void *h, unsigned flags, void *p) { (void)h; (void)flags; free(p); return 1; }
unsigned long long HeapSize(void *h, unsigned flags, void *p) { (void)h; (void)flags; (void)p; return 0; }
void *HeapReAlloc(void *h, unsigned flags, void *p, unsigned long long bytes) {
    (void)h; (void)flags; void *q = realloc(p, (size_t)(bytes ? bytes : 1));
    return allog(q, bytes);
}
unsigned GetLastError(void) { return 0; }
void SetLastError(unsigned e) { (void)e; }
unsigned GetCurrentThreadId(void) { return 1; }
unsigned GetCurrentProcessId(void) { return 4242; }
void *GetCurrentProcess(void) { return (void *)0x1234; }
void Sleep(unsigned ms) { (void)ms; }
int SwitchToThread(void) { return 1; }
unsigned GetTickCount(void) { return 1000; }
unsigned long long GetTickCount64(void) { return 1000; }
void GetSystemTimeAsFileTime(void *p) { memset(p, 0, 8); }
int QueryPerformanceCounter(void *p) { if (p) *(unsigned long long *)p = 12345; return 1; }
int QueryPerformanceFrequency(void *p) { if (p) *(unsigned long long *)p = 10000000; return 1; }

/* CRITICAL_SECTION: RTL 初期化で使う (軽量 no-op; 差分試験は単 thread) */
int InitializeCriticalSectionAndSpinCount(void *cs, unsigned c) { (void)cs; (void)c; memset(cs, 0, 24); return 1; }
void InitializeCriticalSection(void *cs) { memset(cs, 0, 24); }
void DeleteCriticalSection(void *cs) { (void)cs; }
void EnterCriticalSection(void *cs) { (void)cs; }
void LeaveCriticalSection(void *cs) { (void)cs; }
int TryEnterCriticalSection(void *cs) { (void)cs; return 1; }
void InitializeSRWLock(void *l) { memset(l, 0, 8); }
void AcquireSRWLockExclusive(void *l) { (void)l; }
void AcquireSRWLockShared(void *l) { (void)l; }
void ReleaseSRWLockExclusive(void *l) { (void)l; }
void ReleaseSRWLockShared(void *l) { (void)l; }

/* locale / 文字コード: CP1252 相当の最小実装 (CAB-129 教訓: GetLocaleInfoW=0 固定は Halt 連鎖の疑い) */
unsigned GetACP(void) { return 1252; }
unsigned GetOEMCP(void) { return 850; }
unsigned GetConsoleCP(void) { return 65001; }
unsigned GetConsoleOutputCP(void) { return 65001; }
unsigned GetThreadLocale(void) { return 0x0409; }
unsigned SetThreadLocale(unsigned l) { (void)l; return 1; }
unsigned GetSystemDefaultUILanguage(void) { return 0x0409; }
unsigned GetUserDefaultUILanguage(void) { return 0x0409; }
unsigned short GetUserDefaultLangID(void) { return 0x0409; }
unsigned short GetSystemDefaultLangID(void) { return 0x0409; }
int IsValidLocale(unsigned lcid, unsigned fl) { (void)lcid; (void)fl; return 1; }
int IsValidLanguageName(const unsigned short *n) { (void)n; return 1; }
int GetCPInfo(unsigned cp, void *info) {
    if (cp != 1252 && cp != 850 && cp != 65001) return 0;
    unsigned char *p = info;
    memset(p, 0, 20);
    p[0] = 1;                       /* MaxCharSize */
    p[4] = '?';                     /* DefaultChar[0] */
    return 1;
}
/* GetLocaleInfoW: LOCALE_ILANGUAGE(0x1)=0409 / LOCALE_SLANGUAGE(0x2) 等の最小応答。
 * 数値系 (0x000B dec digits 等) は 1 文字応答。不明 LCType は 0 (既定の言語依存値なし) —
 * Halt 連鎖が見えたら個別に足す (fail-fast でなく 0 返しは m11 実績) */
int GetLocaleInfoW(unsigned lcid, unsigned lctype, unsigned short *out, int cout) {
    (void)lcid;
    static const unsigned short lang[] = {'0', '4', '0', '9', 0};
    static const unsigned short name[] = {'E', 'n', 'g', 'l', 'i', 's', 'h', ' ', '(', 'U', 'n', 'i', 't', 'e', 'd', ' ', 'S', 't', 'a', 't', 'e', 's', ')', 0};
    static const unsigned short dec[] = {'1', 0};
    const unsigned short *src = 0;
    switch (lctype & 0xffff) {
        case 0x0001: case 0x0005: case 0x000B: src = (lctype & 0xffff) == 0x0001 ? lang : dec; break;
        case 0x0002: src = name; break;
        default: src = dec; break;
    }
    int n = 0; while (src[n]) n++;
    n++;
    if (cout == 0) return n;
    if (cout < n) return 0;
    for (int i = 0; i < n; i++) out[i] = src[i];
    return n;
}
int SetThreadUILanguage(unsigned l) { (void)l; return 1; }
unsigned LCIDToLocaleName(unsigned lcid, unsigned short *out, int c, unsigned fl) {
    (void)lcid; (void)fl;
    if (c < 6) return 0;
    static const unsigned short s[] = {'e', 'n', '-', 'U', 'S', 0};
    for (int i = 0; i < 6; i++) out[i] = s[i];
    return 6;
}
unsigned GetFullPathNameW(const unsigned short *n, unsigned c, unsigned short *buf, unsigned short **fp) {
    unsigned k = 0; while (n[k]) k++;
    if (c < k + 1) return k + 1;
    for (unsigned i = 0; i <= k; i++) buf[i] = n[i];
    if (fp) *fp = buf;
    return k;
}
unsigned GetTempPathW(unsigned c, unsigned short *buf) {
    static const unsigned short s[] = {'/', 't', 'm', 'p', '/', 0};
    unsigned k = 5;
    if (c < k + 1) return k + 1;
    for (unsigned i = 0; i <= k; i++) buf[i] = s[i];
    return k;
}
void *GetModuleHandleW(const unsigned short *name) { return name ? (void *)0x7ff00000 : (void *)0x400000; }
void *GetModuleHandleA(const char *name) { return name ? (void *)0x7ff00000 : (void *)0x400000; }
unsigned GetModuleFileNameW(void *h, unsigned short *buf, unsigned n) {
    static const unsigned short s[] = {'C', ':', '\\', 'a', 'p', 'p', '\\', 'p', 'l', 'u', 'g', 'i', 'n', '.', 'd', 'l', 'l', 0};
    unsigned k = 0; while (s[k]) k++;
    if (n < k + 1) return k + 1;
    for (unsigned i = 0; i <= k; i++) buf[i] = s[i];
    return k;
}
unsigned GetModuleFileNameA(void *h, char *buf, unsigned n) {
    const char *s = "C:\\app\\plugin.dll";
    unsigned k = 0; while (s[k]) k++;
    if (n < k + 1) return k + 1;
    for (unsigned i = 0; i <= k; i++) buf[i] = s[i];
    return k;
}
unsigned GetVersion(void) { return 0x4a63000au; }        /* Win10 19043 */
int GetVersionExW(void *p) {
    unsigned char *b = p;
    if (*(unsigned *)p < 20 + 4 * 4) return 0;
    memset(p, 0, 20 + 4 * 4 + 4 + 128 * 2);
    *(unsigned *)p = 20 + 4 * 4 + 4 + 128 * 2;           /* dwOSVersionInfoSize */
    *(unsigned *)(p + 4) = 10;                            /* dwMajorVersion */
    *(unsigned *)(p + 8) = 0;                             /* dwMinorVersion */
    *(unsigned *)(p + 12) = 19043;                        /* dwBuildNumber */
    *(unsigned *)(p + 16) = 2;                            /* dwPlatformId = VER_PLATFORM_WIN32_NT */
    strcpy((char *)p + 20 + 4 * 4 + 4, "Windows 10 ");
    return 1;
}
unsigned long long VerSetConditionMask(unsigned long long m, unsigned t, unsigned char op) {
    (void)t; (void)op; return m;
}
int VerifyVersionInfoW(void *info, unsigned mask, unsigned long long cond) { (void)info; (void)mask; (void)cond; return 1; }
void GetSystemInfo(void *p) {
    unsigned char *b = p;
    memset(b, 0, 36 + 8 + 8 + 8);
    *(unsigned *)(b + 4) = 16;        /* dwNumberOfProcessors */
    *(unsigned *)(b + 8) = 4096;      /* dwPageSize */
    *(unsigned long long *)(b + 12 + 8) = 0x10000000;   /* lpMaximumApplicationAddress */
}
/* GetLogicalProcessorInformation: CPU トポロジは headless 固定 → FALSE (0) を返し
 * *ReturnLength = 0。Delphi RTL (SysUtils unit init の GetCPUCount) は失敗時に
 * GetSystemInfo の dwNumberOfProcessors への fallback を持つため init は継続する
 * (fw_ff で落とすと unit init #2 が停止 — CAB-195 で実測)。 */
int GetLogicalProcessorInformation(void *buf, unsigned *len) {
    if (len) *len = 0;
    (void)buf;
    return 0;
}
void GetStartupInfoW(void *p) { memset(p, 0, 104); *(unsigned *)p = 104; }
void GetStartupInfoA(void *p) { memset(p, 0, 68); *(unsigned *)p = 68; }
const void *GetCommandLineW(void) { return (const void*)"p\0l\0u\0g\0i\0n\0\0\0"; }
const void *GetCommandLineA(void) { return "plugin"; }
unsigned SetErrorMode(unsigned m) { (void)m; return 0; }
int IsDebuggerPresent(void) { return 0; }
int IsProcessorFeaturePresent(unsigned f) {
    /* PF_系: SSE/SSE2/3/4.1/SSE4.2/AVX 等を有効 (M11 cpuid 実装と整合) */
    (void)f;
    return 1;
}
void *CreateThread(void *sa, unsigned long long st, void *fn, void *arg, unsigned fl, unsigned *tid) {
    /* headless smoke は単 thread。スレッド起動要求は fail-fast で可視化 (m11 規約) */
    fw_ff("CreateThread called (headless: 未対応)");
    (void)sa; (void)st; (void)fn; (void)arg; (void)fl; (void)tid;
    return 0;
}
unsigned SetTimer(void *h, unsigned id, unsigned el, void *fn) { (void)h; (void)el; (void)fn; return id; }
int KillTimer(void *h, unsigned id) { (void)h; (void)id; return 1; }
void *CreateEventW(void *sa, int manual, int init, const unsigned short *name) {
    (void)sa; (void)manual; (void)init; (void)name;
    static unsigned long long ev = 0xdead0001;
    ev++;
    return (void *)(uintptr_t)ev;
}
int SetEvent(void *e) { (void)e; return 1; }
int ResetEvent(void *e) { (void)e; return 1; }
int CloseHandle(void *h) { (void)h; return 1; }
unsigned FormatMessageW(unsigned fl, const void *src, unsigned msg, unsigned lid, unsigned short *buf, unsigned n, void *args) {
    (void)fl; (void)src; (void)msg; (void)lid; (void)args;
    if (buf && n) buf[0] = 0;
    return 0;
}

/* WideChar↔MultiByte (CP1252/UTF-8 最小; m11_win.c 実績版) */
unsigned WideCharToMultiByte(unsigned cp, unsigned fl, const unsigned short *w, int nw, char *out, int nout, const char *def, int *used) {
    (void)cp; (void)fl; (void)def;
    if (used) *used = 0;
    if (nw < 0) { nw = 0; while (w[nw]) nw++; }
    if (!out || nout == 0) return nw;
    unsigned k = 0;
    for (int i = 0; i < nw && (int)k < nout; i++) out[k++] = (w[i] < 256) ? (char)w[i] : '?';
    return k;
}
unsigned MultiByteToWideChar(unsigned cp, unsigned fl, const char *s, int ns, unsigned short *out, int nout) {
    (void)cp; (void)fl;
    if (ns < 0) { ns = 0; while (s[ns]) ns++; }
    if (!out || nout == 0) return ns;
    unsigned k = 0;
    for (int i = 0; i < ns && (int)k < nout; i++) out[k++] = (unsigned char)s[i];
    return k;
}
int CompareStringW(unsigned lcid, unsigned fl, const unsigned short *s1, int n1, const unsigned short *s2, int n2) {
    (void)lcid; (void)fl;
    if (n1 < 0) { n1 = 0; while (s1[n1]) n1++; }
    if (n2 < 0) { n2 = 0; while (s2[n2]) n2++; }
    int n = n1 < n2 ? n1 : n2;
    for (int i = 0; i < n; i++) {
        unsigned a = s1[i], b = s2[i];
        if (fl & 1) { if (a >= 'A' && a <= 'Z') a += 32; if (b >= 'A' && b <= 'Z') b += 32; }
        if (a != b) return a < b ? 1 : 3;
    }
    if (n1 == n2) return 2;
    return n1 < n2 ? 1 : 3;
}
int LCMapStringW(unsigned lcid, unsigned fl, const unsigned short *src, int nsrc, unsigned short *dst, int ndst) {
    (void)lcid;
    if (nsrc < 0) { nsrc = 0; while (src[nsrc]) nsrc++; nsrc++; }
    if (ndst == 0) return nsrc;
    if (ndst < nsrc) return 0;
    for (int i = 0; i < nsrc; i++) {
        unsigned short c = src[i];
        if ((fl & 0x100) && c >= 'A' && c <= 'Z') c = (unsigned short)(c + 32);
        else if ((fl & 0x200) && c >= 'a' && c <= 'z') c = (unsigned short)(c - 32);
        dst[i] = c;
    }
    return nsrc;
}
int GetStringTypeW(unsigned fl, const unsigned short *s, int n, unsigned short *t) {
    (void)fl;
    if (n < 0) { n = 0; while (s[n]) n++; }
    for (int i = 0; i < n; i++) {
        unsigned c = s[i];
        unsigned short ty = 0;
        if (c == ' ' || (c >= 9 && c <= 13)) ty |= 0x10;
        if (c >= 'a' && c <= 'z') ty |= 0x100;
        if (c >= 'A' && c <= 'Z') ty |= 0x200;
        if (c >= '0' && c <= '9') ty |= 0x400;
        if (t) t[i] = ty;
    }
    return 1;
}
/* レジストリ: 空扱い (m11 規約; 列挙は ERROR_NO_MORE_ITEMS=259) */
int RegOpenKeyExW(void *h, const unsigned short *sub, unsigned opt, unsigned sam, void *out) {
    (void)h; (void)sub; (void)opt; (void)sam; if (out) *(void **)out = 0; return 2;
}
int RegQueryValueExW(void *h, const unsigned short *n, void *r, void *t, void *d, void *cb) {
    (void)h; (void)n; (void)r; (void)t; (void)d; (void)cb; return 2;
}
int RegCloseKey(void *h) { (void)h; return 0; }
int RegEnumKeyExW(void *h, unsigned i, void *a, void *b, void *c, void *d, void *e, void *f) {
    (void)h; (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; return 259;
}
int RegEnumValueW(void *h, unsigned i, void *a, void *b, void *c, void *d, void *e, void *f) {
    (void)h; (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; return 259;
}
int RegQueryInfoKeyW(void *h, void *a, void *b, void *c, void *d, void *e, void *f, void *g, void *i2, void *j, void *k, void *l) {
    (void)h; (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)i2; (void)j; (void)k; (void)l; return 2;
}
void SysFreeString(void *p) { (void)p; }
int CoInitialize(void *p) { (void)p; return 0; }
void CoUninitialize(void) {}
int OleInitialize(void *p) { (void)p; return 0; }
void OleUninitialize(void) {}
/* CAB-195: plugin ctor (0x6b8f4b) 経路で user32 の WindowLong/ClassLong に到達する
 * (FL plugin の editor window handle 管理)。headless では window が無いので 0 を返す
 * (Delphi 側は 0 チェックして editor 非生成の経路に進む)。
 * 署名は IR (lift) 側の戻り型 i32 に合わせる (GetWindowLongPtrW を long long で
 * 宣言すると IR の trunc と mismatch になり wasm で unreachable になる —
 * CAB-195 hs_e2e 実測。function_41ed80/41ed90 は i32)。 */
int GetWindowLongPtrW(void *h, int i) { (void)h; (void)i; return 0; }
int SetWindowLongPtrW(void *h, int i, int v) { (void)h; (void)i; return v; }
int GetClassLongPtrW(void *h, int i) { (void)h; (void)i; return 0; }
int SetClassLongPtrW(void *h, int i, int v) { (void)h; (void)i; return v; }
int GetWindowLongW(void *h, int i) { (void)h; (void)i; return 0; }
int SetWindowLongW(void *h, int i, int v) { (void)h; (void)i; return v; }

/* ---- rep string helpers (fw_rep.py が正規化した固定署名; m11 REPORT #2 の意味) ---- */
void fw_rep_movsb(void *dst, void *src, long long n) {
    if (n > 0) memmove(dst, src, (size_t)n);
}
void fw_rep_movsq(void *dst, void *src, long long qwords) {
    if (qwords > 0) memmove(dst, src, (size_t)qwords * 8);
}
void fw_rep_stosb(void *dst, unsigned char v, long long n) {
    if (n > 0) memset(dst, (int)v, (size_t)n);
}
void fw_rep_stosq(void *dst, long long v, long long qwords) {
    if (qwords > 0) {
        unsigned long long *p = dst;
        for (long long i = 0; i < qwords; i++) p[i] = (unsigned long long)v;
    }
}

/* ---- cpuid (fw_cpuid.py が正規化; m11_simd2 と同じ「SSE2 まで広告」方針) ---- */
struct fw_cpuid_ret fw_cpuid(int leaf) {
    struct fw_cpuid_ret r;
    memset(&r, 0, sizeof r);
    if (leaf == 0) {
        r.a = 7;                                   /* max leaf */
        r.b = 0x756e6547; r.d = 0x49656e69; r.c = 0x6c65746e;   /* "GenuineIntel" */
    } else if (leaf == 1) {
        r.a = 0x000906a3;                          /* family 6 model 10 */
        r.c = (1u << 0) | (1u << 9) | (1u << 19) | (1u << 20) | (1u << 22) | (1u << 23) |
              (1u << 25) | (1u << 27) | (1u << 28); /* SSE3/SSSE3/SSE4.1/SSE4.2/.../OSXSAVE/AVX */
        r.d = (1u << 0) | (1u << 25) | (1u << 26); /* FPU / SSE / SSE2 */
    } else if (leaf == 7) {
        r.b = (1u << 3) | (1u << 8) | (1u << 9);   /* BMI1/BMI2/... 最小限 */
    } else if (leaf == 0x80000000) {
        r.a = 0x80000004;
    } else if (leaf == 0x80000001) {
        r.d = (1u << 26);                          /* SSE2 (64bit 系の広告は抑制) */
    }
    return r;
}

/* ---- fldenv (x87 環境 28B 読み込み; f80 は f64 近似のため状態保持は no-op) ---- */
void fw_fldenv(void *env) { (void)env; }
