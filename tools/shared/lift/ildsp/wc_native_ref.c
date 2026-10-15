/* wc_native_ref.c: ildsp WaveformColouring_CreateInstance の *元の機械語* を VA 0x30000000 (wasm と同一アドレス) に敷設し、
 * gcc の ms_abi 関数ポインタで直接実行する参照 (T-SH-52 / #3216)。
 * case ごとに .data の事前状態を cases.bin から入れ、戻り値 RAX・import 呼出回数・heap (arena)・.data を出力する。
 * import スタブ (HeapAlloc / EnterCriticalSection 等) は wc_glue.c と同じ規約 (同じ bump heap・同じ戻り値)。
 * build: gcc -O1 -w -I <workdir> -o native_ref wc_native_ref.c
 * usage: native_ref image_native.bin cases.bin res_native.bin   (wc_layout.h は -I の dir から読む) */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <signal.h>
#include <unistd.h>
#include <sys/time.h>
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
typedef uint64_t (__attribute__((ms_abi)) *FN4)(uint64_t, uint64_t, uint64_t, uint64_t);
#include <setjmp.h>
static sigjmp_buf jb;
static volatile sig_atomic_t in_case, n_segv, n_alrm, last_sig;
static volatile uintptr_t last_addr;
static void on_fault(int sig, siginfo_t *si, void *uc) { (void)uc; if (in_case) { last_sig = sig; last_addr = (uintptr_t)si->si_addr; if (sig == SIGALRM) n_alrm++; else n_segv++; siglongjmp(jb, 1); } _exit(4); }
#define CRASH_MARK 0xC2A5C2A5C2A5C2A5ULL
#define DIE(...) do { fprintf(stderr, __VA_ARGS__); return 2; } while (0)

static void rd_exact(FILE *f, void *p, size_t n) { if (fread(p, 1, n, f) != n) { fprintf(stderr, "short read\n"); exit(2); } }

static void set_iat(uint8_t *img, uint32_t rva, void *fn) { if (rva) *(uint64_t *)(img + rva) = (uint64_t)(uintptr_t)fn; }

int main(int argc, char **argv) {
    if (argc != 4) DIE("usage: native_ref image_native.bin cases.bin res_native.bin\n");
    FILE *fi = fopen(argv[1], "rb");
    if (!fi) DIE("open image\n");
    uint8_t *imgbuf = malloc(WC_IMG_SIZE);
    if (fread(imgbuf, 1, WC_IMG_SIZE, fi) != WC_IMG_SIZE) DIE("image size\n");
    fclose(fi);
    uint8_t *img = mmap((void *)WC_BASE, WC_IMG_SIZE, PROT_READ | PROT_WRITE | PROT_EXEC,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (img != (void *)WC_BASE) DIE("mmap image at WC_BASE failed\n");
    uint8_t *arena = mmap((void *)WC_ARENA, WC_ARENA_SZ, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (arena != (void *)WC_ARENA) DIE("mmap arena failed\n");

    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_fault;
    sa.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGALRM, &sa, NULL);
    FILE *fc = fopen(argv[2], "rb"), *fo = fopen(argv[3], "wb");
    if (!fc || !fo) DIE("open cases/out\n");
    uint32_t ncase; rd_exact(fc, &ncase, 4);
    uint8_t *data = malloc(WC_DATA_SZ);
    for (uint32_t c = 0; c < ncase; c++) {
        rd_exact(fc, data, WC_DATA_SZ);
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
        memcpy(img + WC_DATA_RVA, data, WC_DATA_SZ);
        memset(arena, 0, WC_ARENA_SZ);
        heap_top = WC_ARENA;
        hits = 0;
        uint64_t rax = CRASH_MARK;
        in_case = 1;
        if (sigsetjmp(jb, 1) == 0) {
            ualarm(300000, 0);   /* 1 case 300 ms で打ち切り */
            /* CreateInstance → vtable の先頭 WC_CALL_SLOTS 個の slot を順に呼ぶ (rcx = instance, rdx = 作業用バッファ, r8 = r9 = 0)。
             * 戻り値は acc = acc*31 + rax で 1 つにまとめる (wasm 側 wc_run_wasm.mjs と同一の式)。 */
            uint64_t inst = ((FN)(img + WC_ENTRY_RVA))();
            uint64_t acc = inst;
            for (int k = 0; k < WC_CALL_SLOTS; k++) {
                uint64_t r = ((FN4)(img + WC_SLOT_RVA[k]))(inst, WC_ARENA + 0x8000, 0, 0);
                acc = acc * 31 + r;
            }
            rax = acc;
            ualarm(0, 0);
        } else {
            /* 元の機械語が無効アクセス/時間超過: 定義された結果が無いので比較対象から外す。
             * 残った SIGALRM を解除しないと、次の case の判定や _exit(4) を起こすため先に止める。 */
            ualarm(0, 0);
            hits = CRASH_MARK; memset(arena, 0, WC_ARENA_SZ); memset(img + WC_DATA_RVA, 0, WC_DATA_SZ);
            fprintf(stderr, "[native] crash case=%u sig=%d addr=0x%llx\n", c, (int)last_sig, (unsigned long long)last_addr);
        }
        in_case = 0;
        fwrite(&rax, 8, 1, fo);
        fwrite(&hits, 8, 1, fo);
        fwrite(arena, 1, WC_ARENA_SZ, fo);
        fwrite(img + WC_DATA_RVA, 1, WC_DATA_SZ, fo);
    }
    fclose(fo);
    fprintf(stderr, "[native] cases=%u SIGSEGV/SIGBUS=%d SIGALRM=%d\n", ncase, (int)n_segv, (int)n_alrm);
    return 0;
}
