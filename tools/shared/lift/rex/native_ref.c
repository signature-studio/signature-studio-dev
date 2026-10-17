#define _GNU_SOURCE
/* native_ref.c: REX の *元の機械語* を VA 0x30000000 (wasm と同一アドレス) に敷設し、gcc の ms_abi 関数ポインタで直接実行する参照。
 * 入力は gen_cases.py の case 形式、出力は run_wasm.mjs と同一形式 (case ごと: u64 rax, u64 import 呼出回数, arena, .data)。
 * import (WaitForSingleObject / ReleaseMutex / RtlPcToFileHeader / RaiseException / GetLastError) は同じ規約のスタブを IAT に敷設する。
 * build: gcc -O1 -w -I <workdir> -o native_ref native_ref.c
 * usage: native_ref image_native.bin cases.bin res_native.bin   (rex_layout.h は -I の dir から読む) */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <signal.h>
#include <unistd.h>
#include <sys/time.h>
#include "rex_layout.h"

static uint64_t hits;
static uint64_t __attribute__((ms_abi)) st_gle(void) { return 0; }
static uint64_t __attribute__((ms_abi)) st_wait(uint64_t h, uint64_t ms) { (void)h; (void)ms; hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_release(uint64_t h) { (void)h; hits++; return 1; }
static uint64_t __attribute__((ms_abi)) st_rtlpc(uint64_t pc, uint64_t b) { (void)pc; (void)b; hits++; return 0; }
static uint64_t __attribute__((ms_abi)) st_raise(uint64_t c, uint64_t f, uint64_t n, uint64_t p) { (void)c; (void)f; (void)n; (void)p; fprintf(stderr, "[rex] RaiseException reached (fail-fast)\n"); exit(3); }
static uint64_t __attribute__((ms_abi)) st_noop(void) { hits++; return 0; }   /* dllmain: rex_imp_noop.c と同じ no-op */

typedef uint64_t (__attribute__((ms_abi)) *FN)(uint64_t, uint64_t, uint64_t, uint64_t);
#include <setjmp.h>
static sigjmp_buf jb;
static volatile sig_atomic_t in_case, n_segv, n_alrm, last_sig;
static volatile uintptr_t last_addr;
static volatile greg_t last_gregs[NGREG];
static uint32_t n_null, n_arena, n_img, n_oth;
static void on_fault(int sig, siginfo_t *si, void *uc) {
    if (in_case) {
        last_sig = sig; last_addr = (uintptr_t)si->si_addr;
        for (int i = 0; i < NGREG; i++) last_gregs[i] = ((ucontext_t *)uc)->uc_mcontext.gregs[i];
        if (sig == SIGALRM) n_alrm++; else n_segv++;
        siglongjmp(jb, 1);
    }
    _exit(4);
}
#define CRASH_MARK 0xC2A5C2A5C2A5C2A5ULL
#define DIE(...) do { fprintf(stderr, __VA_ARGS__); return 2; } while (0)

static void rd_exact(FILE *f, void *p, size_t n) { if (fread(p, 1, n, f) != n) { fprintf(stderr, "short read\n"); exit(2); } }

int main(int argc, char **argv) {
    if (argc != 4) DIE("usage: native_ref image_native.bin cases.bin res_native.bin\n");
    FILE *fi = fopen(argv[1], "rb");
    if (!fi) DIE("open image\n");
    uint8_t *imgbuf = malloc(REX_IMG_SIZE);
    if (fread(imgbuf, 1, REX_IMG_SIZE, fi) != REX_IMG_SIZE) DIE("image size\n");
    fclose(fi);
    uint8_t *img = mmap((void *)REX_BASE, REX_IMG_SIZE, PROT_READ | PROT_WRITE | PROT_EXEC,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (img != (void *)REX_BASE) DIE("mmap image at REX_BASE failed\n");
    uint8_t *arena = mmap((void *)REX_ARENA, REX_ARENA_SZ, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (arena != (void *)REX_ARENA) DIE("mmap arena failed\n");

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
    uint8_t *rec = malloc(REX_ARENA_SZ);
    /* REX_DLLMAIN=1: IAT 全件を 0 を返す no-op で敷き、DllMain(reason=1) を 1 回実行した後の image を各 case の基準にする。
     * 既定 (0): 従来どおり 5 件のスタブだけ敷く (ok / neg-* の既存結果は変えない)。 */
    int dllmain = getenv("REX_DLLMAIN") != NULL && getenv("REX_DLLMAIN")[0] == '1';
    uint8_t *base_img = imgbuf;
    if (dllmain) {
        memcpy(img, imgbuf, REX_IMG_SIZE);
        FILE *fs = fopen(getenv("REX_IAT_SLOTS"), "r");
        if (!fs) DIE("REX_IAT_SLOTS not set\n");
        unsigned int s; char nm[256];
        while (fscanf(fs, "%x %255s", &s, nm) == 2) *(uint64_t *)(img + s) = (uint64_t)(uintptr_t)st_noop;
        fclose(fs);
        *(uint64_t *)(img + REX_IAT_WAIT_RVA) = (uint64_t)(uintptr_t)st_wait;
        *(uint64_t *)(img + REX_IAT_RELEASE_RVA) = (uint64_t)(uintptr_t)st_release;
        *(uint64_t *)(img + REX_IAT_RTLPC_RVA) = (uint64_t)(uintptr_t)st_rtlpc;
        *(uint64_t *)(img + REX_IAT_RAISE_RVA) = (uint64_t)(uintptr_t)st_noop;
        *(uint64_t *)(img + REX_IAT_GLE_RVA) = (uint64_t)(uintptr_t)st_noop;
        ((FN)(img + REX_DLLMAIN_RVA))(REX_BASE, 1, 0, 0);
        base_img = malloc(REX_IMG_SIZE);
        memcpy(base_img, img, REX_IMG_SIZE);
        FILE *fd = fopen(getenv("REX_DATA_BASE_OUT"), "wb");
        if (!fd) DIE("REX_DATA_BASE_OUT\n");
        fwrite(img + REX_DATA_RVA, 1, REX_DATA_SZ, fd);
        fclose(fd);
    }
    for (uint32_t c = 0; c < ncase; c++) {
        uint32_t fn, pad; uint64_t a[4], ctx;
        rd_exact(fc, &fn, 4); rd_exact(fc, &pad, 4); rd_exact(fc, a, 32); rd_exact(fc, &ctx, 8);
        rd_exact(fc, rec, REX_ARENA_SZ);
        memcpy(img, base_img, REX_IMG_SIZE);
        if (!dllmain) {
            *(uint64_t *)(img + REX_IAT_WAIT_RVA) = (uint64_t)(uintptr_t)st_wait;
            *(uint64_t *)(img + REX_IAT_RELEASE_RVA) = (uint64_t)(uintptr_t)st_release;
            *(uint64_t *)(img + REX_IAT_RTLPC_RVA) = (uint64_t)(uintptr_t)st_rtlpc;
            *(uint64_t *)(img + REX_IAT_RAISE_RVA) = (uint64_t)(uintptr_t)st_raise;
            *(uint64_t *)(img + REX_IAT_GLE_RVA) = (uint64_t)(uintptr_t)st_gle;
        }
        *(uint64_t *)(img + REX_CTX_RVA) = ctx;
        memcpy(arena, rec, REX_ARENA_SZ);
        hits = 0;
        uint32_t rva = fn == 0 ? REX_EXP_CREATOR_RVA : REX_EXP_INFO_RVA;
        uint64_t rax = CRASH_MARK;
        in_case = 1;
        if (sigsetjmp(jb, 1) == 0) {
            ualarm(300000, 0);   /* 1 case 300 ms で打ち切り (ループ長の暴走対策) */
            rax = ((FN)(img + rva))(a[0], a[1], a[2], a[3]);
            ualarm(0, 0);
        } else {
            /* 元の機械語が無効アクセス/時間超過: 定義された結果が無いので比較対象から外す (件数は diff_test が報告) */
            hits = CRASH_MARK; memset(arena, 0, REX_ARENA_SZ); memset(img + REX_DATA_RVA, 0, REX_DATA_SZ);
            if (last_sig == SIGALRM) {
                fprintf(stderr, "[native] crash case=%u fn=%u sig=ALRM\n", c, fn);
            } else {
                uintptr_t ad = last_addr;
                if (ad < 0x10000) n_null++;
                else if (ad >= REX_ARENA && ad < REX_ARENA + REX_ARENA_SZ) n_arena++;
                else if (ad >= REX_BASE && ad < REX_BASE + REX_IMG_SIZE) n_img++;
                else n_oth++;
                fprintf(stderr, "[native] crash case=%u fn=%u sig=%d addr=0x%llx rip=0x%llx", c, fn, (int)last_sig, (unsigned long long)ad,
                        (unsigned long long)last_gregs[REG_RIP]);
                static const struct { const char *nm; int reg; } rl[] = {
                    {"rax", REG_RAX}, {"rbx", REG_RBX}, {"rcx", REG_RCX}, {"rdx", REG_RDX}, {"rsi", REG_RSI}, {"rdi", REG_RDI},
                    {"rbp", REG_RBP}, {"rsp", REG_RSP}, {"r8", REG_R8}, {"r9", REG_R9}, {"r10", REG_R10}, {"r11", REG_R11},
                    {"r12", REG_R12}, {"r13", REG_R13}, {"r14", REG_R14}, {"r15", REG_R15}};
                for (size_t k = 0; k < sizeof rl / sizeof rl[0]; k++)
                    fprintf(stderr, " %s=0x%llx", rl[k].nm, (unsigned long long)last_gregs[rl[k].reg]);
                fprintf(stderr, "\n");
            }
        }
        in_case = 0;
        fwrite(&rax, 8, 1, fo);
        fwrite(&hits, 8, 1, fo);
        fwrite(arena, 1, REX_ARENA_SZ, fo);
        fwrite(img + REX_DATA_RVA, 1, REX_DATA_SZ, fo);
    }
    fclose(fo);
    fprintf(stderr, "[native] excluded: SIGSEGV/SIGBUS=%d (addr<0x10000: %u / arena: %u / image: %u / other: %u) SIGALRM(300ms)=%d\n",
            (int)n_segv, n_null, n_arena, n_img, n_oth, (int)n_alrm);
    return 0;
}
