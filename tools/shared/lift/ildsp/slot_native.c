/* slot_native.c: WaveformColouring の vtable slot 1–5 を 1 プロセス 1 実験で単独に呼ぶ native 実行器 (#4169 / T-SH-99)。
 * CreateInstance の直後に、指定した slot 1 回だけを元の機械語で呼ぶ。引数は呼出側 (FL 本体) が渡す値を仮定して変える。
 * 結果: completed (rc 0) か、SIGSEGV/SIGBUS/SIGALRM (rc 4 以上で標準出力に記録)。
 * build: gcc -O1 -w -I <workdir> -o slot_native slot_native.c
 * usage: slot_native image_native.bin K RDX R8 R9 STACK5   (値は 16 進数・そのまま渡す)
 * arena = 0x30500000 (64 KiB)。入力 0x30508000・出力 0x3050C000 のように指定する。 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <signal.h>
#include <unistd.h>
#include <setjmp.h>
#include "wc_layout.h"

static uint64_t hits, heap_top;
#define HEAP_END (WC_ARENA + WC_ARENA_SZ)
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
static volatile uintptr_t last_addr;
static void on_fault(int sig, siginfo_t *si, void *uc) { (void)uc; if (in_case) { last_sig = sig; last_addr = (uintptr_t)si->si_addr; siglongjmp(jb, 1); } _exit(4); }
static void set_iat(uint8_t *img, uint32_t rva, void *fn) { if (rva) *(uint64_t *)(img + rva) = (uint64_t)(uintptr_t)fn; }

int main(int argc, char **argv) {
    if (argc != 7) { fprintf(stderr, "usage: slot_native image_native.bin K RDX R8 R9 STACK5\n"); return 2; }
    FILE *fi = fopen(argv[1], "rb");
    if (!fi) return 2;
    uint8_t *imgbuf = malloc(WC_IMG_SIZE);
    if (fread(imgbuf, 1, WC_IMG_SIZE, fi) != WC_IMG_SIZE) return 2;
    fclose(fi);
    int k = atoi(argv[2]);
    uint64_t a_rdx = strtoull(argv[3], 0, 16), a_r8 = strtoull(argv[4], 0, 16);
    uint64_t a_r9 = strtoull(argv[5], 0, 16), a_s5 = strtoull(argv[6], 0, 16);
    uint8_t *img = mmap((void *)WC_BASE, WC_IMG_SIZE, PROT_READ | PROT_WRITE | PROT_EXEC,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (img != (void *)WC_BASE) return 2;
    uint8_t *arena = mmap((void *)WC_ARENA, WC_ARENA_SZ, PROT_READ | PROT_WRITE,
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

    /* 引数は生の値で渡す (ポインタも数も呼出側の値をそのまま入れる)。arena の 0x8000 以降を入出力に使う */
    in_case = 1;
    if (sigsetjmp(jb, 1) == 0) {
        ualarm(300000, 0);
        uint64_t inst = ((FN)(img + WC_ENTRY_RVA))();
        uint64_t rc_val = ((FN5)(img + WC_SLOT_RVA[k]))(inst, a_rdx, a_r8, a_r9, a_s5);
        ualarm(0, 0);
        printf("RESULT completed slot=%d rax=0x%llx\n", k, (unsigned long long)rc_val);
        return 0;
    }
    ualarm(0, 0);
    printf("RESULT crashed slot=%d sig=%d addr=0x%llx\n", k, (int)last_sig, (unsigned long long)last_addr);
    return 4;
}
