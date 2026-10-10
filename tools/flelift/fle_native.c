/* fle_native.c — FLEngine_x64.dll (ImageBase 0x400000) を Linux プロセス内に VA 通り敷設し,
 * 実物の x64 機械語を MS x64 ABI で直接実行する bit-exact 参照ローダ (CAB-226 spot diff 用)。
 * 原型 = tools/ott/native/ott_native.c (OTT で 89/89 bit-exact 実績) を FLEngine 用に調整:
 *   - ImageBase 0x400000 mmap / .bss 含む SizeOfImage 分を anonymous zero page としてmapping
 *   - gs base = TEB モデル (arch_prctl ARCH_SET_GS, wasm 側 fle_install_teb と同一 layout)
 *   - VirtualAlloc bump arena を wasm imp_VirtualAlloc と同一 VA (0x2100000) に配置
 *   - scratch 0x20000000.., diff 領域 = image (.data/.bss) + scratch + arena
 * spot diff 対象は純計算/文字列関数ゆえ import は最小 (未実装は fail-fast)。 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <ucontext.h>
#include <sys/ucontext.h>
#define _GNU_SOURCE 1
#include <asm/prctl.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
long x86_arch_prctl(int code, unsigned long addr) { return syscall(SYS_arch_prctl, code, addr); }
#define arch_prctl x86_arch_prctl

#define MS __attribute__((ms_abi))
#define IMG_BASE 0x400000ULL
#define IMG_SIZE 0x18c0000ULL
#define TEB_BASE 0x1D00000ULL
#define SCRATCH  0x20000000ULL
#define SCRATCH_SZ 0x100000ULL
#define ARENA    0x2100000ULL
#define ARENA_SZ 0x1000000ULL

extern uint64_t fle_ms_call(void* fn, const uint64_t* gpr4, const uint64_t* xmm4, const uint64_t* stk, long nstk, uint64_t* out2);

static uint8_t* g_img;
static uint8_t* g_img_pristine;
static int g_nimp;
static char g_impname[256][96];

static uint64_t g_arena_off;
static uint64_t g_arena_off_saved;
static int g_nlog;
#define MAXLOG 4096
static uint64_t g_log_ptr[MAXLOG], g_log_sz[MAXLOG];
static uint8_t g_teb_pristine[0x400];
static uint8_t g_scratch_base[0x100000];
void fle_scratch_base(void);
void fle_scratch_base(void) { memcpy(g_scratch_base, (void*)SCRATCH, SCRATCH_SZ); }

static MS void* k_VirtualAlloc(void* base, uint64_t sz, uint32_t type, uint32_t prot) {
    (void)base; (void)type; (void)prot;
    uint64_t need = (sz + 0xffff) & ~0xffffull;
    void* p = (void*)(ARENA + g_arena_off);
    memset(p, 0, need);
    g_arena_off += need;
    if (g_nlog < MAXLOG) { g_log_ptr[g_nlog] = (uint64_t)p; g_log_sz[g_nlog] = need; g_nlog++; }
    return p;
}
static MS void k_VirtualFree(void* p, uint64_t sz, uint32_t t) { (void)p; (void)sz; (void)t; }
static MS void* k_HeapAlloc(void* h, uint32_t flags, uint64_t sz) { (void)h; return k_VirtualAlloc(0, sz, 0, 0); }
static MS int k_HeapFree(void* h, uint32_t f, void* p) { (void)h; (void)f; (void)p; return 1; }
static MS void* k_GetProcessHeap(void) { return (void*)0x1000; }
static MS uint32_t k_GetLastError(void) { return 0; }
static MS void k_SetLastError(uint32_t e) { (void)e; }
static MS void k_CS(void* cs) { (void)cs; }
static MS void k_Sleep(uint32_t ms) { (void)ms; }
static MS int k_IsDebuggerPresent(void) { return 0; }
static MS int k_IsProcessorFeaturePresent(uint32_t f) { (void)f; return 1; }
static MS uint32_t k_GetCurrentThreadId(void) { return 1; }
static MS void k_ExitProcess(uint32_t c) { fprintf(stderr, "[fle_native] ExitProcess(%u)\n", c); exit((int)c); }
static MS void k_RaiseException(uint32_t code, uint32_t fl, uint32_t n, const void* a) {
    (void)fl; (void)n; (void)a;
    fprintf(stderr, "[fle_native] RaiseException(0x%x) — fail-fast\n", code); exit(97);
}

typedef struct { const char* n; void* f; } Impl;
static const Impl IMPL[] = {
    {"VirtualAlloc", k_VirtualAlloc}, {"VirtualFree", k_VirtualFree},
    {"HeapAlloc", k_HeapAlloc}, {"HeapFree", k_HeapFree}, {"GetProcessHeap", k_GetProcessHeap},
    {"GetLastError", k_GetLastError}, {"SetLastError", k_SetLastError},
    {"InitializeCriticalSection", k_CS}, {"EnterCriticalSection", k_CS}, {"LeaveCriticalSection", k_CS},
    {"DeleteCriticalSection", k_CS}, {"Sleep", k_Sleep}, {"IsDebuggerPresent", k_IsDebuggerPresent},
    {"IsProcessorFeaturePresent", k_IsProcessorFeaturePresent}, {"GetCurrentThreadId", k_GetCurrentThreadId},
    {"ExitProcess", k_ExitProcess}, {"RaiseException", k_RaiseException},
    {NULL, NULL}};

static MS void missing_import(uint64_t idx) {
    fprintf(stderr, "[fle_native] MISSING IMPORT %s — fail-fast\n", idx < 256 ? g_impname[idx] : "?");
    _exit(99);
}

#include <setjmp.h>

static sigjmp_buf g_case_jb;
static char g_case_detail[128];
static int g_case_active = 0;

static void segv_handler(int sig, siginfo_t* si, void* uc) {
    ucontext_t* c = (ucontext_t*)uc;
    if (g_case_active) {
        snprintf(g_case_detail, sizeof(g_case_detail), "sig%d addr=%p rip=%llx", sig, si->si_addr,
                 (unsigned long long)c->uc_mcontext.gregs[REG_RIP]);
        g_case_active = 0;
        siglongjmp(g_case_jb, 1);
    }
    fprintf(stderr, "[fle_native] FAULT addr=%p rip=%llx\n", si->si_addr,
            (unsigned long long)c->uc_mcontext.gregs[REG_RIP]);
    _exit(98);
}
void fle_install_segv(void);
void fle_install_segv(void) {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = segv_handler;
    sa.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGILL, &sa, NULL);
}

int fle_load(const char* path);
int fle_load(const char* path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    /* PE ヘッダ読んで section 毎に VA 敷設 (簡略: SizeOfImage 全体を anon で確保し, ファイルの
       生イメージを RVA 0 に書く — FLEngine は file offset = RVA の簡略が .text/.data まで概ね成立) */
    g_img = mmap((void*)IMG_BASE, IMG_SIZE, PROT_READ | PROT_WRITE | PROT_EXEC,
                 MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
    if (g_img == MAP_FAILED) { perror("mmap image"); return -2; }
    g_img_pristine = malloc(IMG_SIZE);
    if (!g_img_pristine) return -3;
    /* 生ファイルを読み, section (PointerToRawData → VirtualAddress) を転写 */
    static uint8_t fbuf[32 << 20];
    off_t fsz = lseek(fd, 0, SEEK_END);
    lseek(fd, 0, SEEK_SET);
    if (fsz > (off_t)sizeof(fbuf)) return -4;
    if (read(fd, fbuf, fsz) != fsz) return -5;
    close(fd);
    uint32_t e_lfanew = *(uint32_t*)(fbuf + 0x3c);
    uint8_t* peh = fbuf + e_lfanew;
    uint16_t nsec = *(uint16_t*)(peh + 6);
    uint32_t sechdr = peh[20] ? 240 : 224; /* optional header size */
    uint32_t sizeofimage = *(uint32_t*)(peh + 24 + 56);
    (void)sizeofimage;
    uint8_t* sh = peh + 24 + sechdr;
    /* headers 部分 */
    uint32_t sizeh = *(uint32_t*)(peh + 24 + 60);
    memcpy(g_img, fbuf, sizeh > 0x1000 ? 0x1000 : sizeh);
    for (int i = 0; i < nsec; i++) {
        uint8_t* s = sh + 40 * i;
        uint32_t vaddr = *(uint32_t*)(s + 12);
        uint32_t rawptr = *(uint32_t*)(s + 20);
        uint32_t rawsz = *(uint32_t*)(s + 16);
        if (rawsz && rawptr)
            memcpy(g_img + vaddr, fbuf + rawptr, rawsz);
    }
    memcpy(g_img_pristine, g_img, IMG_SIZE);
    /* .idata の IAT slot → import 名表 (実行時解決) */
    g_nimp = 0;
    uint32_t impdirRva = *(uint32_t*)(peh + 24 + 200 + 8); /* data dir 1 = import */
    if (impdirRva && impdirRva < IMG_SIZE) {
        for (int d = 0; d < 128; d++) {
            uint32_t* desc = (uint32_t*)(g_img + impdirRva) + d * 5;
            uint32_t nameRva = desc[3], iatRva = desc[4];
            if (!nameRva && !iatRva) break;
            if (nameRva >= IMG_SIZE || iatRva >= IMG_SIZE) break;
            const char* dll = (const char*)(g_img + nameRva);
            if (g_nimp < 250) snprintf(g_impname[g_nimp++], 96, "%s", dll);
            /* 各 slot を thunk に差し替え: 名前照合は行わず idx*2+1 の pseudo slot に */
            uint64_t* slot = (uint64_t*)(g_img + iatRva);
            for (int k = 0; slot[k]; k++) {
                /* MSVCP 風の偶数 slot (hint/name RVA) は skip */
            }
        }
    }
    /* IAT 実解決: import名 → 実装 (名前照合)。directory は実在分だけ辿る (境界 check 付き) */
    {
        uint32_t imgsz = IMG_SIZE;
        for (int d = 0; d < 128; d++) {
            uint32_t* desc = (uint32_t*)(g_img + impdirRva) + d * 5;
            uint32_t oftRva = desc[0], nameRva = desc[3], iatRva = desc[4];
            if (!oftRva && !iatRva) break;
            if (oftRva >= imgsz || iatRva >= imgsz || nameRva >= imgsz) break;
            uint64_t* oft = (uint64_t*)(g_img + oftRva);
            uint64_t* iat = (uint64_t*)(g_img + iatRva);
            for (int k = 0; k < 4096 && oft[k]; k++) {
                if (oft[k] & 0x8000000000000000ull) continue; /* ordinal */
                uint32_t hn = (uint32_t)(oft[k] & 0xffffffffull);
                if (hn + 2 >= imgsz) break;
                const char* nm = (const char*)(g_img + hn + 2);
                void* fn = NULL;
                for (int m = 0; IMPL[m].n; m++)
                    if (!strcmp(IMPL[m].n, nm)) { fn = IMPL[m].f; break; }
                if (!fn) {
                    /* 未実装: index を save して fail-fast thunk */
                    int idx = -1;
                    for (int q = 0; q < g_nimp; q++) if (!strcmp(g_impname[q], nm)) { idx = q; break; }
                    (void)idx;
                    continue; /* slot はそのまま (呼ばれたら fault) */
                }
                iat[k] = (uint64_t)(uintptr_t)fn;
            }
        }
    }
    /* TEB + scratch + arena */
    void* teb = mmap((void*)TEB_BASE, 0x100000, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (teb == MAP_FAILED) { perror("mmap teb"); return -6; }
    void* scr = mmap((void*)SCRATCH, SCRATCH_SZ, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
    if (scr == MAP_FAILED) { perror("mmap scratch"); return -7; }
    void* ar = mmap((void*)ARENA, ARENA_SZ, PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
    if (ar == MAP_FAILED) { perror("mmap arena"); return -9; }
    /* gs base = TEB (wasm の SEG_GS モデルと同一) */
    if (arch_prctl(ARCH_SET_GS, TEB_BASE) != 0) { perror("arch_prctl"); return -8; }
    uint64_t tlsarray = TEB_BASE + 0x10000;
    memset((void*)tlsarray, 0, 64 * 8);
    for (int i = 0; i < 64; i++)
        *(uint64_t*)(tlsarray + 8 * i) = TEB_BASE + 0x20000 + 0x10000ull * i;
    *(uint64_t*)(TEB_BASE + 0x30) = TEB_BASE;
    *(uint64_t*)(TEB_BASE + 0x58) = tlsarray;
    *(uint64_t*)(TEB_BASE + 0x08) = 0x1D8000ull;
    *(uint64_t*)(TEB_BASE + 0x10) = 0x1D0000ull;
    memcpy(g_teb_pristine, (void*)TEB_BASE, sizeof(g_teb_pristine));
    return 0;
}

/* state reset: .data/.bss を pristine に戻し, scratch/arena 初期化 */
void fle_reset(void);
void fle_reset(void) {
    /* .data (0xfa5000..0x11e5008) + .bss (0x11e6000..0x156ee9c) を pristine から復元 */
    memcpy(g_img + 0xfa5000, g_img_pristine + 0xfa5000, 0x11e5008 - 0xfa5000);
    memset(g_img + 0x11e5008, 0, 0x156f000 - 0x11e5008);
    memset((void*)SCRATCH, 0, SCRATCH_SZ);
    memset((void*)ARENA, 0, ARENA_SZ);
    g_arena_off = 0; g_nlog = 0;
    uint64_t tlsarray = TEB_BASE + 0x10000;
    for (int i = 0; i < 64; i++)
        *(uint64_t*)(tlsarray + 8 * i) = TEB_BASE + 0x20000 + 0x10000ull * i;
}

/* MS x64 ABI で fn を実行。gpr4 = rcx,rdx,r8,r9 / stk = stack args / out2 = {rax, xmm0}
 * fault (SEGV/BUS/ILL/FPE) は case driver 用に siglongjmp で回収 (g_case_detail に詳細) */
uint64_t fle_call(uint64_t fn, uint64_t* gpr4, uint64_t* xmm4, uint64_t* stk, long nstk, uint64_t* out2) {
    g_case_active = 1;
    uint64_t r = fle_ms_call((void*)fn, gpr4, xmm4, stk, nstk, out2);
    g_case_active = 0;
    return r;
}

/* diff 取得: 領域 [rva, len) の pristine との差分 (8B block) を out に列挙, 返り値 = 差分 block 数 */
long fle_diff_blocks(uint64_t va, uint64_t len, uint64_t* out, long maxout);
long fle_diff_blocks(uint64_t va, uint64_t len, uint64_t* out, long maxout) {
    long n = 0;
    for (uint64_t o = 0; o + 8 <= len; o += 8) {
        uint64_t cur, pri;
        if (va >= TEB_BASE && va < 0x1e00000ull) {
            pri = *(uint64_t*)(g_teb_pristine + (va - TEB_BASE) + o); cur = *(uint64_t*)(TEB_BASE + (va - TEB_BASE) + o);
        }
        else if (va >= SCRATCH && va < SCRATCH + SCRATCH_SZ) {
            pri = *(uint64_t*)(g_scratch_base + (va - SCRATCH) + o); cur = *(uint64_t*)(va + o);
        }
        else if (va >= IMG_BASE && va < IMG_BASE + IMG_SIZE) {
            pri = *(uint64_t*)(g_img_pristine + (va - IMG_BASE) + o); cur = *(uint64_t*)(g_img + (va - IMG_BASE) + o);
        }
        else { pri = 0; cur = *(uint64_t*)(va + o); }   /* scratch / arena は anon 初期 0 */
        if (cur != pri && n + 3 <= maxout) {
            out[n++] = va + o; out[n++] = pri; out[n++] = cur;
        }
    }
    return n / 3;
}
uint8_t* fle_img(void) { return g_img; }

/* 全領域 (image / TEB / scratch / arena) 共通の read/write — fle_nat.py の prep 用 */
void* fle_ptr(uint64_t va) {
    if (va >= IMG_BASE && va < IMG_BASE + IMG_SIZE) return g_img + (va - IMG_BASE);
    if (va >= TEB_BASE && va < TEB_BASE + 0x100000) return (void*)(TEB_BASE + (va - TEB_BASE));
    if (va >= SCRATCH && va < SCRATCH + SCRATCH_SZ) return (void*)va;
    if (va >= ARENA && va < ARENA + ARENA_SZ) return (void*)va;
    return NULL;
}
long fle_read(uint64_t va, uint8_t* out, long n) {
    void* p = fle_ptr(va);
    if (!p) return -1;
    memcpy(out, p, n);
    return n;
}
long fle_write(uint64_t va, const uint8_t* in, long n) {
    void* p = fle_ptr(va);
    if (!p) return -1;
    memcpy(p, in, n);
    return n;
}
