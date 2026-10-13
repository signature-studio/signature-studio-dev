/* M11 Win32 API 実装 (tools/shim と重ならない最小集合). 署名は IR の declare (wasm32: ptr/i1/i16=i32, HANDLE=i32) に合わせる.
 * 未実装 API は m11_genstubs.py が生成する m11_winstubs.c の stub (m11_stub_hit 計数, 0 を返す) が受ける. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten.h>
extern int m11_trace_flag;

static int g_dummy_heap;
void* GetProcessHeap(void) { return &g_dummy_heap; }

/* ---- 起動初期に叩かれる情報系 API (実測 stub_hits 順に追加) ---- */
unsigned GetVersion(void) { return 0x4a63000au; /* Win10 19043: major 10 minor 0 build 19043 */ }
unsigned GetACP(void) { return 1252; }
int SetThreadLocale(unsigned lcid) { (void)lcid; return 1; }
void SysFreeString(void* p) { (void)p; }   /* 自前確保でない BSTR (静的/他経路) が来るため free しない (PoC: リーク許容) */
/* BSTR: [u32 バイト長][UTF-16 文字列][NUL]. SysAllocStringLen(NULL, n) は未初期化 n 文字 (+NUL). 失敗時 NULL */
void* SysAllocStringLen(const unsigned short* src, unsigned len) {
    unsigned char* b = (unsigned char*)malloc(4 + (size_t)len * 2 + 2);
    if (!b) return 0;
    *(unsigned*)b = len * 2;
    unsigned short* w = (unsigned short*)(b + 4);
    if (src) memcpy(w, src, (size_t)len * 2); else memset(w, 0, (size_t)len * 2);
    w[len] = 0;
    return w;
}
int SysReAllocStringLen(void** pbstr, const unsigned short* src, unsigned len) {
    void* nb = SysAllocStringLen(src, len);
    if (!nb) return 0;
    if (!src && *pbstr) {
        unsigned old = *(unsigned*)((unsigned char*)*pbstr - 4) / 2;
        memcpy(nb, *pbstr, (size_t)(old < len ? old : len) * 2);
    }
    if (*pbstr) SysFreeString(*pbstr);
    *pbstr = nb;
    return 1;
}
unsigned SysStringLen(const void* p) { return p ? *(const unsigned*)((const char*)p - 4) / 2 : 0; }
unsigned long long VerSetConditionMask(unsigned long long m, unsigned type, unsigned char op) {
    return m | ((unsigned long long)op << ((type & 7) * 3)); /* 簡略 (VerifyVersionInfo は常に TRUE) */
}
int VerifyVersionInfoW(void* info, unsigned mask, unsigned long long cond) { (void)info; (void)mask; (void)cond; return 1; }
void GetSystemInfo(void* p) {
    unsigned char* b = (unsigned char*)p;
    memset(b, 0, 48);
    *(unsigned short*)(b + 0) = 9;                    /* PROCESSOR_ARCHITECTURE_AMD64 */
    *(unsigned*)(b + 4) = 4096;                       /* dwPageSize */
    *(unsigned long long*)(b + 8) = 0x10000ull;       /* lpMinimumApplicationAddress */
    *(unsigned long long*)(b + 16) = 0x7ffffffeffffull;
    *(unsigned long long*)(b + 24) = 1;               /* dwActiveProcessorMask */
    *(unsigned*)(b + 32) = 1;                         /* dwNumberOfProcessors */
    *(unsigned*)(b + 36) = 8664;                      /* dwProcessorType */
    *(unsigned*)(b + 40) = 65536;                     /* dwAllocationGranularity */
    *(unsigned short*)(b + 44) = 6;                   /* wProcessorLevel */
}
void GetStartupInfoW(void* p) { memset(p, 0, 104); *(unsigned*)p = 104; }
static unsigned short g_cmdline[] = { 'F', 'L', 'E', 'n', 'g', 'i', 'n', 'e', 0 };
const void* GetCommandLineW(void) { return g_cmdline; }
unsigned GetCurrentProcessId(void) { return 4242; }
unsigned SetErrorMode(unsigned m) { (void)m; return 0; }
int CoInitialize(void* p) { (void)p; return 0; }
int OleInitialize(void* p) { (void)p; return 0; }
unsigned GetThreadLocale(void) { return 0x0409; }
int GetCPInfo(unsigned cp, void* info) {          /* CPINFO: MaxCharSize=1, DefaultChar='?' */
    (void)cp; unsigned char* b = (unsigned char*)info; memset(b, 0, 20); *(unsigned*)b = 1; b[4] = '?'; return 1;
}

/* ---- Registry: HKCU/HKLM は空 (キー無し) として振る舞う. 列挙系は ERROR_NO_MORE_ITEMS(259) を返して無限ループを避ける
 *      (実測: stub が 0=ERROR_SUCCESS を返し RegEnumValueW が 1,101,264 回ループ → GetMem 1.1M 回) ---- */
int RegOpenKeyExW(void* h, void* sub, unsigned opt, unsigned sam, void* out) { (void)h; (void)sub; (void)opt; (void)sam; if (out) *(void**)out = 0; return 2; }
int RegCreateKeyExW(void* h, void* sub, unsigned r, void* cls, unsigned opt, unsigned sam, void* sa, void* out, void* disp) { (void)h; (void)sub; (void)r; (void)cls; (void)opt; (void)sam; (void)sa; if (out) *(void**)out = 0; if (disp) *(unsigned*)disp = 0; return 5; }
int RegQueryValueExW(void* h, void* name, void* res, void* type, void* data, void* cb) { (void)h; (void)name; (void)res; (void)type; (void)data; (void)cb; return 2; }
int RegQueryInfoKeyW(void* h, void* a, void* b, void* c, void* d, void* e, void* f, void* g, void* i, void* j, void* k, void* l) { (void)h; (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)i; (void)j; (void)k; (void)l; return 2; }
int RegEnumValueW(void* h, unsigned i, void* a, void* b, void* c, void* d, void* e, void* f) { (void)h; (void)i; (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; return 259; }
int RegEnumKeyExW(void* h, unsigned i, void* a, void* b, void* c, void* d, void* e, void* f) { (void)h; (void)i; (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; return 259; }
int RegFlushKey(void* h) { (void)h; return 0; }

/* ---- module / loader ---- */
void* GetModuleHandleW(const unsigned short* name) { return name ? (void*)0x7ff00000 : (void*)0x400000; }
unsigned GetModuleFileNameW(void* h, unsigned short* buf, unsigned n) {
    static const char* path = "C:\\Program Files\\Image-Line\\FL Studio 2026\\FLEngine_x64.dll";
    unsigned i = 0;
    while (path[i] && i + 1 < n) { buf[i] = (unsigned char)path[i]; i++; }
    if (n) buf[i] = 0;
    (void)h;
    return i;
}
void* LoadLibraryW(const unsigned short* name) { (void)name; return 0; }          /* DLL は無い: 失敗 */
void* GetProcAddress(void* h, const char* name) { (void)h; (void)name; return 0; }
int GetVersionExW(void* p) {
    unsigned* v = (unsigned*)p;
    v[1] = 10; v[2] = 0; v[3] = 19043; v[4] = 2;
    return 1;
}
unsigned LoadStringW(void* h, unsigned id, unsigned short* buf, unsigned n) { (void)h; (void)id; if (buf && n) buf[0] = 0; return 0; }
EM_JS(void, m11_js_stack, (void), { Error.stackTraceLimit = 60; console.error(new Error().stack.split("\n").slice(2, 60).join("\n")); });
unsigned MessageBoxA(void* h, const char* text, const char* cap, unsigned type) {
    if (m11_trace_flag) m11_js_stack();   /* --trace 時: 呼出し元 wasm frame を表示 */
    fprintf(stderr, "[m11][MessageBoxA] caption='%s' text='%s' type=0x%x (自動 IDOK)\n", cap ? cap : "", text ? text : "", type);
    (void)h; return 1;
}
unsigned MessageBoxW(void* h, const unsigned short* text, const unsigned short* cap, unsigned type) {
    char t[256], c[128]; int i;
    for (i = 0; text && text[i] && i < 255; i++) t[i] = text[i] < 128 ? (char)text[i] : '?'; t[i] = 0;
    for (i = 0; cap && cap[i] && i < 127; i++) c[i] = cap[i] < 128 ? (char)cap[i] : '?'; c[i] = 0;
    fprintf(stderr, "[m11][MessageBoxW] caption='%s' text='%s' type=0x%x (自動 IDOK)\n", c, t, type);
    (void)h; return 1;
}
unsigned WideCharToMultiByte(unsigned cp, unsigned fl, const unsigned short* w, int nw, char* out, int nout, const char* def, int* used) {
    (void)cp; (void)fl; (void)def; if (used) *used = 0;
    if (nw < 0) { nw = 0; while (w[nw]) nw++; nw++; }
    if (!out || nout == 0) return (unsigned)nw;
    int n = nw < nout ? nw : nout;
    for (int i = 0; i < n; i++) out[i] = w[i] < 128 ? (char)w[i] : '?';
    return (unsigned)n;
}
unsigned MultiByteToWideChar(unsigned cp, unsigned fl, const char* s, int ns, unsigned short* out, int nout) {
    (void)cp; (void)fl;
    if (ns < 0) { ns = (int)strlen(s) + 1; }
    if (!out || nout == 0) return (unsigned)ns;
    int n = ns < nout ? ns : nout;
    for (int i = 0; i < n; i++) out[i] = (unsigned char)s[i];
    return (unsigned)n;
}
int IsValidLocale(unsigned lcid, unsigned fl) { (void)lcid; (void)fl; return 1; }

/* LCMapStringW: 大文字/小文字化 (ASCII のみ), それ以外は素通し. 戻り値 = 出力文字数 */
int LCMapStringW(unsigned lcid, unsigned flags, const unsigned short* src, int nsrc, unsigned short* dst, int ndst) {
    (void)lcid;
    if (nsrc < 0) { nsrc = 0; while (src[nsrc]) nsrc++; nsrc++; }
    if (ndst == 0) return nsrc;
    if (ndst < nsrc) return 0;
    for (int i = 0; i < nsrc; i++) {
        unsigned short c = src[i];
        if ((flags & 0x100) && c >= 'A' && c <= 'Z') c = (unsigned short)(c + 32);
        else if ((flags & 0x200) && c >= 'a' && c <= 'z') c = (unsigned short)(c - 32);
        dst[i] = c;
    }
    return nsrc;
}
