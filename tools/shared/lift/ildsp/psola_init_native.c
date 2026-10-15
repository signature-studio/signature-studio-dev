#define _GNU_SOURCE
/* psola_init_native.c: PSOLA (block24360) の DSP 本体 slot 1–3 を呼ぶ前に、host 初期化 (CRT 相当) を
 * 元の機械語で 1 回実行する native 実行器 (#4302 / T-SH-114)。
 * 順序: INIT (RVA init_rva) → CreateInstance (WC_ENTRY_RVA) → 指定 slot の順に呼ぶ。
 * usage: psola_init_native image_native.bin INIT_RVA K_CSV RDX R8 R9 STACK5
 *   slot 3 は R8 = 要素数・R9 = 入力配列・STACK5 = 出力 (RDX は不使用)。slot 1 は RDX = 入力・R8 = 出力。
 *   K_CSV は呼ぶ slot 番号のカンマ区切り (例: 0,1,2,3,4,5)。引数は全 slot 共通 (16 進)。
 * 結果: 各 slot ごとに "RESULT slot=K rax=..." か、crash の sig/addr を標準出力に出す。 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <signal.h>
#include <unistd.h>
#include <setjmp.h>
#include <ucontext.h>
#include "wc_layout.h"

static uint64_t hits, heap_top;
#define NATIVE_ARENA_SZ 0x400000 /* init の確保 (new 0xa72c 等) が 64 KiB arena を超えるため広げる (#4302) */
#define HEAP_END (WC_ARENA + NATIVE_ARENA_SZ)
static uint64_t __attribute__((ms_abi)) st_heapalloc(uint64_t h, uint64_t fl, uint64_t sz) {
    (void)h; (void)fl; hits++;
    uint64_t p = heap_top; uint64_t n = (sz + 15) & ~15ull;
    if (p + n > HEAP_END) return 0;
    heap_top += n;
    return p;
}
static uint64_t __attribute__((ms_abi)) st_heapfree(uint64_t h, uint64_t fl, uint64_t p) { (void)h; (void)fl; (void)p; hits++; return 1; }
static uint64_t __attribute__((ms_abi)) st_gle(void) { hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_sle(uint64_t e) { (void)e; hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_curproc(void) { hits++; return 0xFFFFFFFFFFFFFFFFull; }
static uint64_t __attribute__((ms_abi)) st_enter(uint64_t cs) { (void)cs; hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_leave(uint64_t cs) { (void)cs; hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_flsget(uint64_t i) { (void)i; hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_flsset(uint64_t i, uint64_t v) { (void)i; (void)v; hits++; return 1; }
static uint64_t __attribute__((ms_abi)) st_ipfp(uint64_t f) { (void)f; hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_zero(void) { hits++; return 0; }

typedef uint64_t (__attribute__((ms_abi)) *FN)(void);
typedef uint64_t (__attribute__((ms_abi)) *FN5)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
static sigjmp_buf jb;
static volatile sig_atomic_t in_case, last_sig;
static volatile uintptr_t last_addr, last_rip;
static void on_fault(int sig, siginfo_t *si, void *uc) { if (in_case) { last_sig = sig; last_addr = (uintptr_t)si->si_addr; last_rip = (uintptr_t)((ucontext_t *)uc)->uc_mcontext.gregs[REG_RIP]; siglongjmp(jb, 1); } _exit(4); }
static void set_iat(uint8_t *img, uint32_t rva, void *fn) { if (rva) *(uint64_t *)(img + rva) = (uint64_t)(uintptr_t)fn; }

int main(int argc, char **argv) {
    if (argc != 8) { fprintf(stderr, "usage: psola_init_native image_native.bin INIT_RVA K_CSV RDX R8 R9 STACK5\n"); return 2; }
    FILE *fi = fopen(argv[1], "rb");
    if (!fi) return 2;
    uint8_t *imgbuf = malloc(WC_IMG_SIZE);
    if (fread(imgbuf, 1, WC_IMG_SIZE, fi) != WC_IMG_SIZE) return 2;
    fclose(fi);
    setvbuf(stdout, NULL, _IONBF, 0);
    uint64_t init_rva = strtoull(argv[2], 0, 16);
    uint64_t a_rdx = strtoull(argv[4], 0, 16), a_r8 = strtoull(argv[5], 0, 16);
    uint64_t a_r9 = strtoull(argv[6], 0, 16), a_s5 = strtoull(argv[7], 0, 16);
    uint8_t *img = mmap((void *)WC_BASE, WC_IMG_SIZE, PROT_READ | PROT_WRITE | PROT_EXEC,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (img != (void *)WC_BASE) return 2;
    uint8_t *arena = mmap((void *)WC_ARENA, NATIVE_ARENA_SZ, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (arena != (void *)WC_ARENA) return 2;
    memcpy(img, imgbuf, WC_IMG_SIZE);
    set_iat(img, WC_IAT_HeapAlloc_RVA, st_heapalloc);
    set_iat(img, WC_IAT_HeapFree_RVA, st_heapfree);
    set_iat(img, WC_IAT_GetLastError_RVA, st_gle);
    set_iat(img, WC_IAT_SetLastError_RVA, st_sle);
    set_iat(img, WC_IAT_GetCurrentProcess_RVA, st_curproc);
    set_iat(img, WC_IAT_EnterCriticalSection_RVA, st_enter);
    set_iat(img, WC_IAT_LeaveCriticalSection_RVA, st_leave);
    set_iat(img, WC_IAT_FlsGetValue_RVA, st_flsget);
    set_iat(img, WC_IAT_FlsSetValue_RVA, st_flsset);
    set_iat(img, WC_IAT_IsProcessorFeaturePresent_RVA, st_ipfp);
    set_iat(img, WC_IAT_RaiseException_RVA, st_zero);
    set_iat(img, WC_IAT_RtlCaptureContext_RVA, st_zero);
    set_iat(img, WC_IAT_RtlLookupFunctionEntry_RVA, st_zero);
    set_iat(img, WC_IAT_RtlPcToFileHeader_RVA, st_zero);
    set_iat(img, WC_IAT_RtlVirtualUnwind_RVA, st_zero);
    set_iat(img, WC_IAT_SetUnhandledExceptionFilter_RVA, st_zero);
    set_iat(img, WC_IAT_UnhandledExceptionFilter_RVA, st_zero);
    set_iat(img, WC_IAT_TerminateProcess_RVA, st_zero);
    heap_top = WC_ARENA;

    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_fault;
    sa.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGALRM, &sa, NULL);
    sigaction(SIGTRAP, &sa, NULL);

    in_case = 1;
    if (sigsetjmp(jb, 1) != 0) {
        ualarm(0, 0);
        printf("RESULT crashed stage=init-or-create sig=%d addr=0x%llx\n", (int)last_sig, (unsigned long long)last_addr);
        return 4;
    }
    ualarm(300000, 0);
    if (init_rva) ((FN)(img + init_rva))();
    uint64_t inst = ((FN)(img + WC_ENTRY_RVA))();
    printf("INST 0x%llx\n", (unsigned long long)inst);
    char *p = argv[3], *save = NULL;
    for (char *t = strtok_r(p, ",", &save); t; t = strtok_r(NULL, ",", &save)) {
        int k = atoi(t);
        if (sigsetjmp(jb, 1) != 0) {
            ualarm(0, 0);
            printf("RESULT crashed slot=%d sig=%d addr=0x%llx rip=0x%llx\n", k, (int)last_sig, (unsigned long long)last_addr, (unsigned long long)(last_rip - (uintptr_t)img));
            return 4;
        }
        ualarm(300000, 0);
        uint64_t rc_val = ((FN5)(img + WC_SLOT_RVA[k]))(inst, a_rdx, a_r8, a_r9, a_s5);
        ualarm(0, 0);
        printf("RESULT completed slot=%d rax=0x%llx\n", k, (unsigned long long)rc_val);
    }
    return 0;
}
