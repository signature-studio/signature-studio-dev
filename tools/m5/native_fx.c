/* M5 (a) native 検証ドライバ (x86_64 Linux):
 * FLEngine_x64.dll の .text/.data/.rdata を VA 通りに mmap MAP_FIXED で敷設し
 * (tools/m3/m3_perf_native.c の実績踏襲), MS x64 呼び出し規約で
 * lift 対象 0x6a7540 (waveshaper) / 0x6a2fb0 (distortion) を直接実行する。
 * 入力の float 配列は out-of-image scratch VA に置く。
 *
 *   ./native_fx <dllpath>  --func ws    <srcVA> <count> <k> ... (stdin の float データは使わない)
 *   ./native_fx <dllpath>  --func dist  <srcVA> <dstVA> <count>
 *
 * 出力: 変換後の一連 float ビットを stdout に hex 行で吐く (node 側が bit-exact 照合)。
 * (独立根拠: 本ドライバは「実物の Delphi 機械語」を直接実行する。liftされた IR
 *  と wasm に一切触れないので, wasm 側との一致判定は非循環の参照となる。)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

#define PAGE 4096UL
/* ImageBase 0x400000 (VA 通りの固定敷設) */
#define REBASE 0x400000UL   /* Linux mmap_min_addr 以上の固定敷設起点 */

/* --- 最小 PE パーサ (M2 pescan.py の C 版) ------------------------------- */
typedef struct { char name[9]; uint32_t vaddr, vsize, raw_ptr, raw_size; } Sec;

static void* map_image(const char* path, Sec* secs, int* nsec_out) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    /* file 全体を 0x0 領域に読み捨てる (VA 敷設後に部分コピーするため) */
    uint8_t* fbuf = mmap(NULL, (size_t)sz, PROT_READ, MAP_PRIVATE, fd, 0);
    if (fbuf == (void*)-1) { perror("mmap file"); exit(2); }
    uint32_t pe_off; memcpy(&pe_off, fbuf + 0x3c, 4);
    uint32_t opt_off = pe_off + 24;
    uint16_t nsec16, optsz;
    memcpy(&nsec16, fbuf + pe_off + 6, 2);
    memcpy(&optsz, fbuf + pe_off + 20, 2);
    uint32_t sec_off = opt_off + optsz;
    uint32_t lo = 0xffffffff, hi = 0;
    for (int i = 0; i < nsec16; i++) {
        uint32_t e = sec_off + i * 40;
        Sec* s = &secs[i];
        memcpy(&s->vsize, fbuf + e + 8, 4);
        memcpy(&s->vaddr, fbuf + e + 12, 4);
        memcpy(&s->raw_size, fbuf + e + 16, 4);
        memcpy(&s->raw_ptr, fbuf + e + 20, 4);
        memcpy(s->name, fbuf + e, 8); s->name[8] = 0;
        if (s->vsize == 0 || s->vaddr == 0) continue;
        if (s->vaddr < lo) lo = s->vaddr;
        if (s->vaddr + s->vsize > hi) hi = s->vaddr + s->vsize;
    }
    *nsec_out = nsec16;
    /* 全 VA 空間を 1 枚の RWX マッピングに敷く (VA < 4GB のユーザ空間) */
    void* base = mmap((void*)(uintptr_t)REBASE, (hi + PAGE - 1) & ~(PAGE - 1),
                      PROT_READ | PROT_WRITE | PROT_EXEC,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED | MAP_NORESERVE, -1, 0);
    if (base != (void*)(uintptr_t)REBASE) {
        fprintf(stderr, "native_fx: VA 0x%lx に MAP_FIXED できません (base=%p)\n", REBASE, base);
        exit(3);
    }
    for (int i = 0; i < nsec16; i++) {
        Sec* s = &secs[i];
        if (s->vsize == 0 || s->raw_size == 0) continue;
        uint32_t n = s->raw_size < s->vsize ? s->raw_size : s->vsize;
        memcpy((void*)(uintptr_t)(REBASE + s->vaddr), fbuf + s->raw_ptr, n);
    }
    munmap(fbuf, (size_t)sz);
    (void)lo;
    return (void*)(uintptr_t)REBASE;
}

/* --- Win64 呼び出し規約のトランポリン (rcx=arg1, rdx=arg2, r8=arg3, xmm2) */
static void call_wsi(void* f, void* rcx, size_t rdx, float xmm2k) {
    asm volatile("push %%rbp\n\tmov %%rsp, %%r10\n\tand $-16, %%rsp\n\t"
                 "mov %1, %%rcx\n\tmov %2, %%rdx\n\tmovss %3, %%xmm2\n\t"
                 "call *%0\n\tmov %%r10, %%rsp\n\tpop %%rbp"
                 :: "r"(f), "r"(rcx), "r"(rdx), "x"(xmm2k)
                 : "r10","rax","rcx","rdx","xmm0","xmm1","xmm2","xmm3","xmm4","xmm5","xmm6","xmm7","memory");
}
static void call_wso(void* f, void* rcx, void* rdx, size_t r8) {
    asm volatile("push %%rbp\n\tmov %%rsp, %%r10\n\tand $-16, %%rsp\n\t"
                 "mov %1, %%rcx\n\tmov %2, %%rdx\n\tmov %3, %%r8\n\t"
                 "call *%0\n\tmov %%r10, %%rsp\n\tpop %%rbp"
                 :: "r"(f), "r"(rcx), "r"(rdx), "r"(r8)
                 : "r10","rax","rcx","rdx","r8","xmm0","xmm1","xmm2","xmm3","xmm4","xmm5","xmm6","xmm7","memory");
}

static void hexdump(const volatile uint32_t* p, size_t words) {
    for (size_t i = 0; i < words; i++)
        printf("%08x\n", p[i]);
}

/* scratch VA (OOB 領域): (a1)(a2) 対象関数はここを参照しないので自由に使える */
#define SCRATCH_SRC  0x18000000u
#define SCRATCH_DST  0x18100000u

static void map_scratch(void) {
    void* s = mmap((void*)(uintptr_t)SCRATCH_SRC, 0x10000UL,
                   PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (s != (void*)(uintptr_t)SCRATCH_SRC) { fprintf(stderr, "native_fx: scratch SRC の MAP_FIXED 失敗\n"); exit(3); }
    void* d = mmap((void*)(uintptr_t)SCRATCH_DST, 0x10000UL,
                   PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (d != (void*)(uintptr_t)SCRATCH_DST) { fprintf(stderr, "native_fx: scratch DST の MAP_FIXED 失敗\n"); exit(3); }
    memset(s, 0, 0x10000UL);
    memset(d, 0, 0x10000UL);
}

int main(int argc, char** argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: native_fx <dll> --func ws|dist <args...>\n");
        return 2;
    }
    Sec secs[24]; int nsec;
    map_scratch();
    map_image(argv[1], secs, &nsec);

    const char* fn = argv[3];
    if (strcmp(fn, "ws") == 0) {
        /* 0x6a7540(rcx=dst/src 同一, rdx=count, xmm2=k) */
        size_t count = (size_t)strtoull(argv[4], 0, 0);
        float k = strtof(argc > 5 ? argv[5] : "0", 0);
        volatile uint32_t* src = (uint32_t*)(uintptr_t)SCRATCH_SRC;
        /* stdin から hex 行で float を読む (srcVA = SCRATCH_SRC に敷く前提) */
        char line[64]; size_t n = 0;
        while (n < count && fgets(line, sizeof line, stdin)) {
            if (line[0] == '\n' || line[0] == '#') continue;
            src[n++] = (uint32_t)strtoul(line, 0, 16);
        }
        void* f = (void*)(uintptr_t)0x6a7540u;
        int nsig = count & ~3u;   /* SIMD 本数 4 の倍数分 */
        /* x64 passthrough: 関数は SIMD 本数分 + 残余を処理する */
        call_wsi(f, (void*)src, (size_t)count, k);
        hexdump(src, count);
    } else if (strcmp(fn, "dist") == 0) {
        /* 0x6a2fb0(rcx=src, rdx=dst, r8=count) */
        size_t count = (size_t)strtoull(argv[4], 0, 0);
        volatile uint32_t* src = (uint32_t*)(uintptr_t)SCRATCH_SRC;
        volatile uint32_t* dst = (uint32_t*)(uintptr_t)SCRATCH_DST;
        /* scratch 初期化: 入力は stdin hex 行 → SRC 側に敷設 */
        char line[64]; size_t n = 0;
        while (n < count && fgets(line, sizeof line, stdin)) {
            if (line[0] == '\n' || line[0] == '#') continue;
            src[n++] = (uint32_t)strtoul(line, 0, 16);
        }
        for (size_t i = n; i < count; i++) dst[i] = 0;
        void* f = (void*)(uintptr_t)0x6a2fb0u;
        call_wso(f, (void*)src, (void*)dst, count);
        hexdump(dst, count);
    } else {
        fprintf(stderr, "native_fx: unknown func %s\n", fn);
        return 2;
    }
    return 0;
}
