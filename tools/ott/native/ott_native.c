/* ott_native.c — OTT_vst2_win64.dll を Linux x86_64 プロセス内に VA 通り (ImageBase 0x180000000) で敷設し,
 * 実物の x64 機械語を MS x64 ABI で直接実行する bit-exact 参照ローダ (m5 native_fx 方式の拡張)。
 *  - IAT: 実装済み Win32 API は C 関数, 未実装は「名前を出して即 exit(99)」thunk (fail-fast)。
 *  - CRT 初期化 (DllMain) は走らせない: wasm lift 側 (m6_data install) と同じ「.data 静的初期値」状態を共有する。
 *  - ctypes から使う shared library: ott_load / ott_call / ott_heap_* 。
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <signal.h>
#include <ucontext.h>

#define MS __attribute__((ms_abi))
#define IMG_BASE 0x180000000ULL

extern uint64_t ott_ms_call(void* fn, const uint64_t* gpr4, const uint64_t* xmm4, const uint64_t* stk, long nstk, uint64_t* out2);

static uint8_t* g_img;
static uint32_t g_imgsize;
static int g_nimp;
static char g_impname[1024][96];
static int g_heap_fill = 0;           /* 0: 確保メモリ zero, 非0: そのバイトで埋める (未初期化依存の検出用) */
static uint64_t g_heap_calls, g_heap_bytes;

/* ---- 簡易ヒープ: 16B 整列 bump + 先頭に size header (free は no-op) ---- */
#define ARENA_SZ (256ULL << 20)
static uint8_t* g_arena; static uint64_t g_arena_off;
typedef struct { uint64_t size, magic; } HHdr;
/* replay: wasm 側 alloc log (ptr,size) 列を再生し heap アドレスを wasm linear と完全一致させる */
#define MAXLOG 65536
static uint64_t g_log_ptr[MAXLOG], g_log_sz[MAXLOG]; static int g_nlog;
static uint64_t g_rp_ptr[MAXLOG], g_rp_sz[MAXLOG]; static int g_nrp, g_rp_i;
static int g_rp_mismatch;
static void* heap_alloc(uint64_t sz, int zero) {
    if (g_nrp && g_rp_i < g_nrp) {
        uint64_t p = g_rp_ptr[g_rp_i];
        if (g_rp_sz[g_rp_i] != sz) { g_rp_mismatch++; fprintf(stderr, "[ott_native] replay size mismatch at #%d: wasm=%llu native=%llu\n", g_rp_i, (unsigned long long)g_rp_sz[g_rp_i], (unsigned long long)sz); }
        g_rp_i++;
        memset((void*)p, zero ? 0 : g_heap_fill, sz);
        if (g_nlog < MAXLOG) { g_log_ptr[g_nlog] = p; g_log_sz[g_nlog] = sz; g_nlog++; }
        g_heap_calls++; g_heap_bytes += sz;
        return (void*)p;
    }
    if (!g_arena) {
        g_arena = mmap((void*)0x50000000ULL, ARENA_SZ, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
        if (g_arena == MAP_FAILED) { perror("arena"); exit(2); }
    }
    uint64_t need = (sz + 15) & ~15ULL;
    HHdr* h = (HHdr*)(g_arena + g_arena_off);
    g_arena_off += 16 + need;
    if (g_arena_off > ARENA_SZ) { fprintf(stderr, "[ott_native] arena exhausted\n"); exit(98); }
    h->size = sz; h->magic = 0xA110CA7EULL;
    uint8_t* p = (uint8_t*)(h + 1);
    if (zero) memset(p, 0, need); else memset(p, g_heap_fill, need);
    g_heap_calls++; g_heap_bytes += sz;
    if (g_nlog < MAXLOG) { g_log_ptr[g_nlog] = (uint64_t)p; g_log_sz[g_nlog] = sz; g_nlog++; }
    return p;
}

/* ---- 実装済み Win32 API ---- */
static MS void* k_GetProcessHeap(void) { return (void*)0x1000; }
static MS void* k_HeapAlloc(void* h, uint32_t flags, uint64_t sz) { (void)h; return heap_alloc(sz, (flags & 8) != 0); }
static MS int k_HeapFree(void* h, uint32_t f, void* p) { (void)h; (void)f; (void)p; return 1; }
static uint64_t heap_size_of(void* p) {
    for (int i = g_nlog - 1; i >= 0; i--) if (g_log_ptr[i] == (uint64_t)p) return g_log_sz[i];
    return ((HHdr*)p)[-1].size;
}
static MS uint64_t k_HeapSize(void* h, uint32_t f, void* p) { (void)h; (void)f; return heap_size_of(p); }
static MS void* k_HeapReAlloc(void* h, uint32_t f, void* p, uint64_t sz) {
    (void)h; void* n = heap_alloc(sz, (f & 8) != 0);
    if (p) { uint64_t o = heap_size_of(p); memcpy(n, p, o < sz ? o : sz); }
    return n;
}
static uint32_t g_lasterr;
static MS uint32_t k_GetLastError(void) { return g_lasterr; }
static MS void k_SetLastError(uint32_t e) { g_lasterr = e; }
static MS void k_RaiseException(uint32_t code, uint32_t fl, uint32_t n, const void* a) {
    (void)fl; (void)n; (void)a;
    fprintf(stderr, "[ott_native] RaiseException(0x%x) 到達 — fail-fast\n", code); exit(97);
}
static MS int k_QPC(int64_t* v) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); *v = t.tv_sec * 1000000000LL + t.tv_nsec; return 1; }
static MS int k_QPF(int64_t* v) { *v = 1000000000LL; return 1; }
static MS void k_CS(void* cs) { (void)cs; }
static MS int k_CSi(void* cs, uint32_t n) { (void)cs; (void)n; return 1; }
static MS void* k_EncodePointer(void* p) { return p; }
static MS uint32_t k_GetCurrentThreadId(void) { return 1; }
static MS uint32_t k_GetCurrentProcessId(void) { return 1; }
static MS int k_IsDebuggerPresent(void) { return 0; }
static MS int k_IsProcessorFeaturePresent(uint32_t f) { (void)f; return 1; }
static MS void k_Sleep(uint32_t ms) { (void)ms; }
static MS uint32_t k_TlsAlloc(void) { return 0; }
static void* g_tls[64];
static MS void* k_TlsGetValue(uint32_t i) { return g_tls[i & 63]; }
static MS int k_TlsSetValue(uint32_t i, void* v) { g_tls[i & 63] = v; return 1; }

typedef struct { const char* n; void* f; } Impl;
static const Impl IMPL[] = {
    {"GetProcessHeap", k_GetProcessHeap}, {"HeapAlloc", k_HeapAlloc}, {"HeapFree", k_HeapFree},
    {"HeapSize", k_HeapSize}, {"HeapReAlloc", k_HeapReAlloc},
    {"GetLastError", k_GetLastError}, {"SetLastError", k_SetLastError}, {"RaiseException", k_RaiseException},
    {"QueryPerformanceCounter", k_QPC}, {"QueryPerformanceFrequency", k_QPF},
    {"InitializeCriticalSection", k_CS}, {"InitializeCriticalSectionAndSpinCount", k_CSi},
    {"InitializeCriticalSectionEx", k_CSi}, {"EnterCriticalSection", k_CS}, {"LeaveCriticalSection", k_CS},
    {"DeleteCriticalSection", k_CS}, {"EncodePointer", k_EncodePointer}, {"DecodePointer", k_EncodePointer},
    {"GetCurrentThreadId", k_GetCurrentThreadId}, {"GetCurrentProcessId", k_GetCurrentProcessId},
    {"IsDebuggerPresent", k_IsDebuggerPresent}, {"IsProcessorFeaturePresent", k_IsProcessorFeaturePresent},
    {"Sleep", k_Sleep}, {"TlsAlloc", k_TlsAlloc}, {"TlsGetValue", k_TlsGetValue}, {"TlsSetValue", k_TlsSetValue},
    {"FlsGetValue", k_TlsGetValue}, {"FlsSetValue", k_TlsSetValue},
    {NULL, NULL}};

static MS void missing_import(uint64_t idx) {
    fprintf(stderr, "[ott_native] MISSING IMPORT %s — fail-fast\n", idx < 1024 ? g_impname[idx] : "?");
    _exit(99);
}

static uint8_t* g_thunks; static size_t g_thunk_off;
static void* make_thunk(int idx) {
    if (!g_thunks) {
        g_thunks = mmap((void*)0x60000000ULL, 1 << 20, PROT_READ | PROT_WRITE | PROT_EXEC,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (g_thunks == MAP_FAILED) { perror("thunks"); exit(2); }
    }
    uint8_t* p = g_thunks + g_thunk_off; g_thunk_off += 32;
    uint8_t* q = p;
    *q++ = 0xB9; memcpy(q, &idx, 4); q += 4;                      /* mov ecx, idx */
    *q++ = 0x48; *q++ = 0xB8; void* f = (void*)missing_import; memcpy(q, &f, 8); q += 8; /* mov rax, f */
    *q++ = 0xFF; *q++ = 0xD0;                                       /* call rax */
    return p;
}

int ott_load(const char* path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); return -1; }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t ns, osz; memcpy(&ns, f + pe + 6, 2); memcpy(&osz, f + pe + 20, 2);
    uint32_t imgsize; memcpy(&imgsize, f + pe + 24 + 56, 4);
    uint64_t ib; memcpy(&ib, f + pe + 24 + 24, 8);
    if (ib != IMG_BASE) { fprintf(stderr, "ImageBase != 0x180000000\n"); return -2; }
    g_img = mmap((void*)IMG_BASE, imgsize, PROT_READ | PROT_WRITE | PROT_EXEC,
                 MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (g_img != (uint8_t*)IMG_BASE) { perror("mmap image"); return -3; }
    g_imgsize = imgsize;
    uint32_t hsz; memcpy(&hsz, f + pe + 24 + 60, 4);
    memcpy(g_img, f, hsz);
    uint32_t so = pe + 24 + osz;
    for (int i = 0; i < ns; i++) {
        uint32_t va, vs, rp, rs; uint8_t* e = f + so + i * 40;
        memcpy(&vs, e + 8, 4); memcpy(&va, e + 12, 4); memcpy(&rs, e + 16, 4); memcpy(&rp, e + 20, 4);
        uint32_t n = rs < vs ? rs : vs;
        memcpy(g_img + va, f + rp, n);
    }
    uint32_t idrva; memcpy(&idrva, f + pe + 24 + 112 + 8, 4);   /* DataDirectory[1] = Import */
    for (uint8_t* d = g_img + idrva;; d += 20) {
        uint32_t oft, nm, ft; memcpy(&oft, d, 4); memcpy(&nm, d + 12, 4); memcpy(&ft, d + 16, 4);
        if (!nm) break;
        uint64_t* thunk = (uint64_t*)(g_img + ft);
        uint64_t* orig = (uint64_t*)(g_img + (oft ? oft : ft));
        for (; *orig; orig++, thunk++) {
            char name[96];
            if (*orig >> 63) snprintf(name, sizeof name, "%s!#%u", (char*)(g_img + nm), (unsigned)(*orig & 0xffff));
            else snprintf(name, sizeof name, "%s", (char*)(g_img + (*orig & 0x7fffffff) + 2));
            void* impl = NULL;
            for (const Impl* m = IMPL; m->n; m++) if (!strcmp(m->n, name)) { impl = m->f; break; }
            if (!impl) { int idx = g_nimp++; strncpy(g_impname[idx], name, 95); impl = make_thunk(idx); }
            *thunk = (uint64_t)impl;
        }
    }
    munmap(f, sz); close(fd);
    return 0;
}

/* 汎用の encoded slot 初期化: 各 slot に enc(NULL) = cookie を書く (ICALL-51)。cookie は cookie_va の現在値。 */
void ott_enc_slots(uint64_t cookie_va, const uint64_t* slots, int n) {
    uint64_t c; memcpy(&c, (void*)cookie_va, 8);
    for (int i = 0; i < n; i++) memcpy((void*)slots[i], &c, 8);
}
uint64_t ott_call(uint64_t fn, const uint64_t* gpr4, const uint64_t* xmm4, const uint64_t* stk, long nstk, uint64_t* out2) {
    return ott_ms_call((void*)fn, gpr4, xmm4, stk, nstk, out2);
}
void ott_set_heap_fill(int b) { g_heap_fill = b; }
uint64_t ott_heap_alloc(uint64_t sz) { return (uint64_t)heap_alloc(sz, 1); }
uint64_t ott_heap_used(void) { return g_arena_off; }
uint64_t ott_arena_base(void) { return (uint64_t)g_arena; }
uint64_t ott_heap_calls(void) { return g_heap_calls; }

/* replay API */
int ott_map_range(uint64_t lo, uint64_t hi) {
    void* m = mmap((void*)lo, hi - lo, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
    return m == (void*)lo ? 0 : -1;
}
void ott_replay_set(const uint64_t* ptr, const uint64_t* size, int n) {
    for (int i = 0; i < n && i < MAXLOG; i++) { g_rp_ptr[i] = ptr[i]; g_rp_sz[i] = size[i]; }
    g_nrp = n; g_rp_i = 0; g_rp_mismatch = 0;
}
int ott_replay_mismatch(void) { return g_rp_mismatch; }
int ott_replay_pos(void) { return g_rp_i; }
int ott_alog_count(void) { return g_nlog; }
void ott_alog_get(int i, uint64_t* p, uint64_t* s) { *p = g_log_ptr[i]; *s = g_log_sz[i]; }

/* ---- 関数 entry tracer: INT3 patch + TF 単歩で再挿入 (wasm 側 ott_trace と同形式) ---- */
typedef struct { uint64_t va, a[4], x[4], rsp, ret; } TrRec;
#define TR_CAP (1 << 22)
static TrRec* g_tr; static uint64_t g_tr_n; static int g_tr_on;
static uint64_t g_hva[2048]; static uint8_t g_horig[2048]; static int g_nh, g_pend = -1;
extern char ott_ms_ret[];
static int g_cov_on; static uint8_t* g_cov; static uint8_t* g_cov_ct; static uint64_t g_cov_steps; static uint64_t g_prev_rip;
static int is_ijmp_insn(const uint8_t* p) {
    if ((p[0] & 0xf0) == 0x40) p++;
    return p[0] == 0xFF && (((p[1] >> 3) & 7) == 4);
}
static int is_call_insn(const uint8_t* p) {
    if ((p[0] & 0xf0) == 0x40) p++;
    if (p[0] == 0xE8) return 1;
    if (p[0] == 0xFF && (((p[1] >> 3) & 7) == 2)) return 1;
    return 0;
}
static void on_trap(int sig, siginfo_t* si, void* uc_) {
    (void)sig; (void)si;
    ucontext_t* uc = (ucontext_t*)uc_;
    greg_t* g = uc->uc_mcontext.gregs;
    if (g_cov_on) {
        uint64_t rip0 = (uint64_t)g[REG_RIP];
        if (rip0 == (uint64_t)ott_ms_ret) { g_cov_on = 0; g[REG_EFL] &= ~0x100; return; }
        g_cov_steps++;
        if (rip0 >= IMG_BASE && rip0 < IMG_BASE + 0x308000) {
            g_cov[rip0 - IMG_BASE] = 1;
            if (g_prev_rip >= IMG_BASE && g_prev_rip < IMG_BASE + 0x308000 && is_call_insn((const uint8_t*)g_prev_rip)) g_cov_ct[rip0 - IMG_BASE] = 1;
            else if (g_prev_rip >= IMG_BASE && g_prev_rip < IMG_BASE + 0x308000 && is_ijmp_insn((const uint8_t*)g_prev_rip) &&
                     (rip0 > g_prev_rip + 0x4000 || rip0 + 0x4000 < g_prev_rip || ((((const uint8_t*)g_prev_rip)[((((const uint8_t*)g_prev_rip)[0] & 0xf0) == 0x40) ? 2 : 1]) >> 6) != 3)) g_cov_ct[rip0 - IMG_BASE] = 1;   /* CFG thunk 経由 (jmp rax) の遠方 target */
        }
        g_prev_rip = rip0;
        g[REG_EFL] |= 0x100;
        return;
    }
    if (g_pend >= 0) { *(volatile uint8_t*)g_hva[g_pend] = 0xCC; g[REG_EFL] &= ~0x100; g_pend = -1; return; }
    uint64_t rip = (uint64_t)g[REG_RIP] - 1;
    int idx = -1;
    for (int i = 0; i < g_nh; i++) if (g_hva[i] == rip) { idx = i; break; }
    if (idx < 0) { const char m[] = "[ott_native] unexpected SIGTRAP\n"; if (write(2, m, sizeof m - 1) < 0) {} _exit(96); }
    *(volatile uint8_t*)rip = g_horig[idx];
    g[REG_RIP] = rip; g[REG_EFL] |= 0x100; g_pend = idx;
    if (g_tr_on && g_tr_n < TR_CAP) {
        TrRec* r = &g_tr[g_tr_n++];
        r->va = rip; r->a[0] = g[REG_RCX]; r->a[1] = g[REG_RDX]; r->a[2] = g[REG_R8]; r->a[3] = g[REG_R9];
        for (int k = 0; k < 4; k++) { uint64_t v; memcpy(&v, &uc->uc_mcontext.fpregs->_xmm[k], 8); r->x[k] = v; }
        r->rsp = g[REG_RSP]; r->ret = *(uint64_t*)g[REG_RSP];
    }
}
void ott_trace_install(const uint64_t* vas, int n) {
    if (!g_tr) g_tr = calloc(TR_CAP, sizeof(TrRec));
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_trap; sa.sa_flags = SA_SIGINFO; sigemptyset(&sa.sa_mask);
    sigaction(SIGTRAP, &sa, NULL);
    for (int i = 0; i < n && g_nh < 2048; i++) {
        g_hva[g_nh] = vas[i]; g_horig[g_nh] = *(uint8_t*)vas[i]; *(volatile uint8_t*)vas[i] = 0xCC; g_nh++;
    }
}
void ott_trace_enable(int on) { g_tr_on = on; if (on) g_tr_n = 0; }
uint64_t ott_trace_count(void) { return g_tr_n; }
const TrRec* ott_trace_buf(void) { return g_tr; }

/* ---- coverage: ott_cov_call 実行中は全命令を単歩し image 内 RIP を記録 ---- */
void ott_cov_begin(void) {
    if (!g_cov) { g_cov = calloc(0x308000, 1); g_cov_ct = calloc(0x308000, 1); }
    g_prev_rip = 0;
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_trap; sa.sa_flags = SA_SIGINFO; sigemptyset(&sa.sa_mask);
    sigaction(SIGTRAP, &sa, NULL);
    g_cov_on = 1;
}
void ott_cov_kick(void) { raise(SIGTRAP); }
const uint8_t* ott_cov_buf(void) { return g_cov; }
uint64_t ott_cov_steps(void) { return g_cov_steps; }
uint64_t ott_call_cov(uint64_t fn, const uint64_t* gpr4, const uint64_t* xmm4, const uint64_t* stk, long nstk, uint64_t* out2) {
    ott_cov_begin();
    raise(SIGTRAP);
    return ott_ms_call((void*)fn, gpr4, xmm4, stk, nstk, out2);
}
const uint8_t* ott_cov_ct_buf(void) { return g_cov_ct; }

static void on_segv(int sig, siginfo_t* si, void* uc_) {
    ucontext_t* uc = (ucontext_t*)uc_; greg_t* g = uc->uc_mcontext.gregs;
    fprintf(stderr, "[ott_native] SIGSEGV(%d) rip=%#llx (rva %#llx) addr=%p rsp=%#llx rcx=%#llx rdx=%#llx rax=%#llx\n", sig,
            (unsigned long long)g[REG_RIP], (unsigned long long)(g[REG_RIP] - IMG_BASE), si->si_addr,
            (unsigned long long)g[REG_RSP], (unsigned long long)g[REG_RCX], (unsigned long long)g[REG_RDX], (unsigned long long)g[REG_RAX]);
    for (int i = 0; i < 400; i++) {
        uint64_t v = ((uint64_t*)g[REG_RSP])[i];
        if (v >= IMG_BASE && v < IMG_BASE + 0x308000) fprintf(stderr, "   stack[%d] = %#llx\n", i, (unsigned long long)v);
    }
    _exit(95);
}
void ott_install_segv(void) {
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_segv; sa.sa_flags = SA_SIGINFO; sigemptyset(&sa.sa_mask);
    sigaction(SIGSEGV, &sa, NULL); sigaction(SIGBUS, &sa, NULL); sigaction(SIGFPE, &sa, NULL);
}
