/* ildsp_native.c — block24360_PE.bin を ImageBase 0x180000000 に VA 通りに敷設し、
 * GeneralPitchShifter_CreateInstance (RVA 0x1aa290) を MS x64 ABI で native 実行する (#2528 / T-SH-38)。
 *  - IAT: 実装済み Win32 API は ms_abi の C 関数、未実装は名前を記録して 0 を返す thunk (非致命・出力に残す)。
 *  - 間接 call 4 件 (0x1aedf6・0x1aee04・0x1aee4a・0x1b6f6c) は int3 で捕捉し、到達を数える。
 *    呼び先が画像内ポインタ (0x268260・0x268268) の 2 件は実行せず飛ばす (rax が静的に不明なため)。IAT の 2 件は実行する。
 *  - 出力は key=value の行。checker は ildsp_native_check.py。
 * usage: ildsp_native <PE> [--neg-lea]
 *   --neg-lea: CreateInstance の vptr 格納 lea の disp32 を +8 に壊す (ネガティブコントロール)。 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <ucontext.h>

#define MS __attribute__((ms_abi))
#define IMG_BASE 0x180000000ULL
#define HEAP_BASE 0x50000000ULL
#define HEAP_SZ (64ULL << 20)
#define THUNK_BASE 0x60000000ULL
#define CI_RVA 0x1aa290ULL
#define OBJ_SZ 0x2f8

static uint8_t* g_img; static uint32_t g_imgsize;
static uint8_t* g_heap; static uint64_t g_heap_off, g_heap_n;
static uint32_t g_lasterr;
static char g_unimpl[256][96]; static uint64_t g_unimpl_calls[256]; static int g_nunimpl;
static uint8_t* g_thunks; static size_t g_thunk_off;

typedef struct { uint64_t site; const char* name; int skip_image; uint64_t hits; uint64_t target; } Hook;
static Hook g_hooks[] = {
    {0x1aedf6, "helper 0x1aedc0 -> [0x268260] (画像内ポインタ 0x1cb5e0)", 1, 0, 0},
    {0x1aee04, "helper 0x1aedc0 -> [0x268088] RtlPcToFileHeader", 0, 0, 0},
    {0x1aee4a, "helper 0x1aedc0 -> [0x268090] RaiseException", 0, 0, 0},
    {0x1b6f6c, "0x1b6f4c -> [0x268268] (画像内ポインタ 0x1cb600)", 1, 0, 0},
};
#define NHOOK (sizeof g_hooks / sizeof g_hooks[0])

/* ---- Win32 stubs (ms_abi) ---- */
MS static void* k_GetProcessHeap(void) { return (void*)0x1000; }
MS static void* k_HeapAlloc(void* h, uint32_t fl, uint64_t n) {
    (void)h; (void)fl;
    if (!g_heap) {
        g_heap = mmap((void*)HEAP_BASE, HEAP_SZ, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
        if (g_heap == MAP_FAILED) { perror("heap"); _exit(2); }
    }
    uint64_t need = (n + 15) & ~15ULL; if (!need) need = 16;
    if (g_heap_off + need > HEAP_SZ) return NULL;
    uint8_t* p = g_heap + g_heap_off; g_heap_off += need; g_heap_n++;
    memset(p, 0, need);
    return p;
}
MS static int k_HeapFree(void* h, uint32_t fl, void* p) { (void)h; (void)fl; (void)p; return 1; }
MS static uint32_t k_GetLastError(void) { return g_lasterr; }
MS static void k_SetLastError(uint32_t e) { g_lasterr = e; }
MS static uint64_t k_RtlPcToFileHeader(uint64_t pc, uint64_t* base) {
    if (pc >= IMG_BASE && pc < IMG_BASE + g_imgsize) { if (base) *base = IMG_BASE; return IMG_BASE; }
    return 0;
}
MS static void k_RaiseException(uint32_t code, uint32_t fl, uint32_t n, void* args) {
    (void)args;
    printf("exception_raised code=%x flags=%x nargs=%u (例外送出 path 到達。後続は実行しない)\n", code, fl, n);
    fflush(stdout); _exit(96);
}

typedef struct { const char* n; void* f; } Impl;
static const Impl IMPL[] = {
    {"GetProcessHeap", (void*)k_GetProcessHeap}, {"HeapAlloc", (void*)k_HeapAlloc}, {"HeapFree", (void*)k_HeapFree},
    {"GetLastError", (void*)k_GetLastError}, {"SetLastError", (void*)k_SetLastError},
    {"RtlPcToFileHeader", (void*)k_RtlPcToFileHeader}, {"RaiseException", (void*)k_RaiseException},
    {NULL, NULL}};

MS static uint64_t missing_import(uint64_t idx) {
    if (idx < 256) { g_unimpl_calls[idx]++; }
    return 0;
}

static void* make_thunk(int idx) {
    if (!g_thunks) {
        g_thunks = mmap((void*)THUNK_BASE, 1 << 20, PROT_READ | PROT_WRITE | PROT_EXEC,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (g_thunks == MAP_FAILED) { perror("thunks"); _exit(2); }
    }
    uint8_t* p = g_thunks + g_thunk_off; g_thunk_off += 32;
    uint8_t* q = p;
    *q++ = 0x48; *q++ = 0x83; *q++ = 0xEC; *q++ = 0x28;             /* sub rsp,0x28 */
    *q++ = 0xB9; memcpy(q, &idx, 4); q += 4;                         /* mov ecx, idx */
    *q++ = 0x48; *q++ = 0xB8; void* f = (void*)missing_import; memcpy(q, &f, 8); q += 8; /* mov rax, f */
    *q++ = 0xFF; *q++ = 0xD0;                                        /* call rax */
    *q++ = 0x48; *q++ = 0x83; *q++ = 0xC4; *q++ = 0x28;             /* add rsp,0x28 */
    *q++ = 0xC3;                                                     /* ret */
    return p;
}

static Hook* find_hook(uint64_t site) {
    for (size_t i = 0; i < NHOOK; i++) if (g_hooks[i].site == site) return &g_hooks[i];
    return NULL;
}

/* int3 で捕捉した間接 call を、呼び先を読んで実行 (または画像内ポインタなら飛ばす) */
static void on_trap(int sig, siginfo_t* si, void* vuc) {
    (void)sig; (void)si;
    ucontext_t* uc = vuc; greg_t* g = uc->uc_mcontext.gregs;
    uint64_t site = (uint64_t)g[REG_RIP] - 1 - IMG_BASE;
    Hook* h = find_hook(site);
    if (!h) { fprintf(stderr, "unexpected trap at 0x%llx\n", (unsigned long long)site); _exit(95); }
    int32_t disp; memcpy(&disp, g_img + site + 2, 4);
    uint64_t ret = IMG_BASE + site + 6;
    uint64_t slot = ret + (int64_t)disp;
    uint64_t tgt; memcpy(&tgt, (void*)slot, 8);
    h->hits++; h->target = tgt;
    if (h->skip_image) { g[REG_RIP] = ret; return; }
    g[REG_RSP] -= 8; memcpy((void*)g[REG_RSP], &ret, 8);
    g[REG_RIP] = tgt;
}

static void install_hooks(void) {
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_trap; sa.sa_flags = SA_SIGINFO;
    sigaction(SIGTRAP, &sa, NULL);
    for (size_t i = 0; i < NHOOK; i++) g_img[g_hooks[i].site] = 0xCC;
}

static int load_pe(const char* path) {
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
    int nimp = 0;
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
            if (!impl) {
                int idx = g_nunimpl < 256 ? g_nunimpl++ : 255;
                strncpy(g_unimpl[idx], name, 95);
                impl = make_thunk(idx);
            }
            *thunk = (uint64_t)impl;
            nimp++;
        }
    }
    printf("loaded image=0x%llx size=0x%x imports=%d\n", (unsigned long long)IMG_BASE, imgsize, nimp);
    return 0;
}

typedef MS uint64_t (*Fn0)(void);
typedef MS uint64_t (*Fn4)(uint64_t, uint64_t, uint64_t, uint64_t);

static void dump_changed(const uint8_t* a, const uint8_t* b, size_t n) {
    int first = 1; size_t i = 0;
    printf(" changed=[");
    while (i < n) {
        if (a[i] == b[i]) { i++; continue; }
        size_t j = i; while (j < n && a[j] != b[j]) j++;
        printf("%s0x%zx+%zu", first ? "" : ",", i, j - i);
        first = 0; i = j;
    }
    printf("]\n");
}

static uint64_t unimpl_total(void) { uint64_t t = 0; for (int i = 0; i < g_nunimpl; i++) t += g_unimpl_calls[i]; return t; }

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: ildsp_native <PE> [--neg-lea]\n"); return 2; }
    setvbuf(stdout, NULL, _IOLBF, 0);
    int neg = 0, only_k = -1, only_v = -1;
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--neg-lea")) neg = 1;
        else if (!strcmp(argv[i], "--slot") && i + 2 < argc) { only_k = atoi(argv[i + 1]); only_v = atoi(argv[i + 2]); i += 2; }
    }
    if (load_pe(argv[1])) return 3;
    install_hooks();

    if (neg) {
        for (int i = 0; i < 0x40; i++) {
            uint8_t* p = g_img + CI_RVA + i;
            if (p[0] == 0x48 && p[1] == 0x8d && p[2] == 0x05) { int32_t d; memcpy(&d, p + 3, 4); d += 8; memcpy(p + 3, &d, 4); printf("neg: lea at 0x%llx disp +8\n", (unsigned long long)(CI_RVA + i)); break; }
        }
    }

    /* 1. CreateInstance */
    uint64_t W = ((Fn0)(IMG_BASE + CI_RVA))();
    uint64_t vptr = W ? *(uint64_t*)W : 0;
    uint64_t inner = W ? *(uint64_t*)(W + 8) : 0;
    printf("create wrapper=0x%llx vptr=0x%llx inner=0x%llx\n", (unsigned long long)W, (unsigned long long)vptr, (unsigned long long)inner);
    printf("vptr_expected=0x%llx match=%d\n", (unsigned long long)(IMG_BASE + 0x3dfcf8ULL), vptr == IMG_BASE + 0x3dfcf8ULL);
    if (!W) { printf("RESULT FAIL create returned null\n"); return 1; }

    /* 2. 各 slot を、新しい instance ごとに呼ぶ (slot 0 = dtor は呼ばない)。
     *    --slot K V を与えると、その 1 実験だけを行う (実験ごとに別プロセスで回すため) */
    const uint64_t rdx_list[] = {0, 1, 2, 0xe};
    for (int k = 1; k <= 5; k++) {
        int nv = (k <= 3) ? 4 : 1;
        if (only_k >= 0 && k != only_k) continue;
        for (int v = 0; v < nv; v++) {
            if (only_v >= 0 && v != only_v) continue;
            uint64_t w = ((Fn0)(IMG_BASE + CI_RVA))();
            uint64_t in = *(uint64_t*)(w + 8);
            uint8_t before[OBJ_SZ], after[OBJ_SZ];
            memcpy(before, (void*)in, OBJ_SZ);
            uint64_t vt = *(uint64_t*)w;
            uint64_t fn = *(uint64_t*)(vt + 8 * k);
            uint64_t h0[NHOOK]; for (size_t i = 0; i < NHOOK; i++) h0[i] = g_hooks[i].hits;
            uint64_t u0 = unimpl_total();
            uint64_t rdx = (k == 4) ? in : rdx_list[v];
            printf("call k=%d variant=%d rdx=0x%llx wrapper=0x%llx\n", k, v, (unsigned long long)rdx, (unsigned long long)w);
            uint64_t rax = ((Fn4)fn)(w, rdx, 0, 0);
            memcpy(after, (void*)in, OBJ_SZ);
            printf("slot k=%d variant=%d rdx=0x%llx fn=0x%llx rax=0x%llx unimpl_calls=%llu",
                   k, v, (unsigned long long)rdx, (unsigned long long)(fn - IMG_BASE), (unsigned long long)rax,
                   (unsigned long long)(unimpl_total() - u0));
            dump_changed(before, after, OBJ_SZ);
            for (size_t i = 0; i < NHOOK; i++) if (g_hooks[i].hits != h0[i])
                printf("  hook site=0x%llx hits+=%llu (%s)\n", (unsigned long long)g_hooks[i].site,
                       (unsigned long long)(g_hooks[i].hits - h0[i]), g_hooks[i].name);
        }
    }

    /* 3. 集計 */
    for (size_t i = 0; i < NHOOK; i++)
        printf("hook_total site=0x%llx hits=%llu last_target=0x%llx (%s)\n", (unsigned long long)g_hooks[i].site,
               (unsigned long long)g_hooks[i].hits, (unsigned long long)g_hooks[i].target, g_hooks[i].name);
    for (int i = 0; i < g_nunimpl; i++)
        printf("unimpl_import %s calls=%llu\n", g_unimpl[i], (unsigned long long)g_unimpl_calls[i]);
    printf("heap_allocs=%llu\n", (unsigned long long)g_heap_n);
    fflush(stdout);
    return 0;
}
