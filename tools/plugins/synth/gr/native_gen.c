/* native 参照 (x86_64 Linux): synth shell DLL を VA 0x400000 に MAP_FIXED 敷設し、
 * Gen_Render(this, DestBuffer, &Length) (MS x64 ABI, ABI.md §3) を実機械語のまま呼ぶ。lift IR / wasm に非依存。
 *   usage: native_gen <dll> <gen_render_va_hex> <instance_size> <cases.bin> <results.bin>
 * cases.bin : u32 ncases, 各 case = {u32 length; u32 padD; u32 reset}   reset=1: case の前に this を 0 埋めし直す (0 = 前 case の状態を引き継ぐ)
 * results.bin: 各 case {u32 status; u32 sig; u64 fault_rip; u64 fault_addr; u64 ret; u32 nd; u32 dst[nd]}
 *   status 0 = 正常 return / 1 = SIGSEGV 等で中断 (sig, fault_* に記録) / dst は nd = 2*length+16 word
 * this = 0 埋めの instance_size バイト (ctor を通していない = framework 未結合の状態)。 IAT は未解決 (0)。
 * 中断は sigsetjmp/siglongjmp で捕捉し、次の case へ進む (落ちた事実を結果に残す: 黙って成功にしない)。
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <setjmp.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <ucontext.h>

#define REBASE 0x400000UL
#define SCR_D 0x18100000UL
#define SCR_T 0x18300000UL
#define SCR_L 0x18400000UL
typedef uint64_t (__attribute__((ms_abi)) *fn3)(uint64_t, uint64_t, uint64_t);

static sigjmp_buf jb;
static volatile uint64_t f_rip, f_addr;
static volatile int f_sig;
static void on_sig(int s, siginfo_t* si, void* uc) {
    ucontext_t* u = uc;
    f_sig = s; f_addr = (uint64_t)(uintptr_t)si->si_addr; f_rip = (uint64_t)u->uc_mcontext.gregs[REG_RIP];
    siglongjmp(jb, 1);
}
static void map_image(const char* path) {
    int fd = open(path, O_RDONLY); if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t nsec, optsz; memcpy(&nsec, f + pe + 6, 2); memcpy(&optsz, f + pe + 20, 2);
    uint32_t imgsz; memcpy(&imgsz, f + pe + 24 + 56, 4);
    uint64_t ib; memcpy(&ib, f + pe + 24 + 24, 8);
    if (ib != REBASE) { fprintf(stderr, "ImageBase %lx != 0x400000 (未対応)\n", ib); exit(4); }
    void* b = mmap((void*)REBASE, imgsz, PROT_READ|PROT_WRITE|PROT_EXEC, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED|MAP_NORESERVE, -1, 0);
    if (b != (void*)REBASE) { fprintf(stderr, "MAP_FIXED 0x400000 失敗\n"); exit(3); }
    uint32_t so = pe + 24 + optsz;
    for (int i = 0; i < nsec; i++) {
        uint32_t vs, va, rs, rp; uint8_t* e = f + so + 40 * i;
        memcpy(&vs, e + 8, 4); memcpy(&va, e + 12, 4); memcpy(&rs, e + 16, 4); memcpy(&rp, e + 20, 4);
        uint32_t n = rs < vs ? rs : vs;
        if (n) memcpy((void*)(REBASE + va), f + rp, n);
    }
}
static void scr(uint64_t a, size_t n) {
    void* p = mmap((void*)a, n, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED, -1, 0);
    if (p != (void*)a) { fprintf(stderr, "scratch map 失敗 %lx\n", a); exit(3); }
}
int main(int argc, char** argv) {
    if (argc < 6) return 2;
    map_image(argv[1]);
    uint64_t va = strtoull(argv[2], NULL, 16);
    size_t isz = strtoull(argv[3], NULL, 0);
    scr(SCR_D, 0x100000); scr(SCR_T, 0x10000); scr(SCR_L, 0x1000);
    struct sigaction sa; memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_sig; sa.sa_flags = SA_SIGINFO | SA_NODEFER;
    sigaction(SIGSEGV, &sa, NULL); sigaction(SIGBUS, &sa, NULL); sigaction(SIGILL, &sa, NULL); sigaction(SIGFPE, &sa, NULL);
    FILE* in = fopen(argv[4], "rb"); FILE* out = fopen(argv[5], "wb");
    if (!in || !out) return 2;
    uint32_t nc; if (fread(&nc, 4, 1, in) != 1) return 4;
    fn3 gen = (fn3)(va);
    for (uint32_t c = 0; c < nc; c++) {
        uint32_t h[3]; if (fread(h, 4, 3, in) != 3) return 4;
        uint32_t n = h[0], padD = h[1];
        float* dst = (float*)(SCR_D + 4 * padD);
        memset((void*)SCR_D, 0xA5, 0x2000);
        if (h[2] || c == 0) memset((void*)SCR_T, 0, isz > 0x10000 ? 0x10000 : isz);
        *(int32_t*)SCR_L = (int32_t)n;
        uint32_t status = 0; uint64_t ret = 0;
        f_sig = 0; f_rip = f_addr = 0;
        if (sigsetjmp(jb, 1) == 0) ret = gen(SCR_T, (uint64_t)dst, SCR_L);
        else status = 1;
        uint32_t nd = 2 * n + 16, sg = (uint32_t)f_sig;
        fwrite(&status, 4, 1, out); fwrite(&sg, 4, 1, out);
        uint64_t fr = f_rip, fa = f_addr;
        fwrite(&fr, 8, 1, out); fwrite(&fa, 8, 1, out); fwrite(&ret, 8, 1, out);
        fwrite(&nd, 4, 1, out); fwrite(dst, 4, nd, out);
    }
    fclose(out);
    return 0;
}
