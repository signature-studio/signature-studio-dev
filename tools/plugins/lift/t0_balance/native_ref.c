/* native 参照ドライバ (x86_64 Linux): 実プラグイン DLL の .text/.data 等を VA 0x400000 起点に MAP_FIXED 敷設し、
 * MS x64 ABI (gcc ms_abi) で実機械語の kernel を直接実行する。 lift IR / wasm に一切触れない非循環参照。
 *   usage: native_ref <dll> <cases.bin> <results.bin>
 * cases.bin: u32 ncases, 各 case = {u32 kind,n,padS,padD,inplace,rsv; f32 g[8]; f32 src[2n+8]}
 *   kind 0 = mix  kernel VA 0x5dee90 (rcx=src, rdx=dst, r8=n, r9=&g[0])
 *   kind 1 = peak kernel VA 0x5df940 (rcx=buf, rdx=n, r8=&L, r9=&R)
 * results.bin: 各 case {u64 ret; u32 nw; u32 words[nw]} (mix: dst の 2n+16 word, peak: L,R の 2 word)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#define REBASE 0x400000UL
#define SCR_S 0x18000000UL
#define SCR_D 0x18100000UL
#define SCR_P 0x18200000UL
#define SCR_O 0x18200100UL
typedef uint64_t (__attribute__((ms_abi)) *fn4)(uint64_t, uint64_t, uint64_t, uint64_t);

static void map_image(const char* path) {
    int fd = open(path, O_RDONLY); if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t nsec, optsz; memcpy(&nsec, f + pe + 6, 2); memcpy(&optsz, f + pe + 20, 2);
    uint32_t imgsz; memcpy(&imgsz, f + pe + 24 + 56, 4);
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
    if (argc < 4) return 2;
    map_image(argv[1]);
    scr(SCR_S, 0x100000); scr(SCR_D, 0x100000); scr(SCR_P, 0x10000);
    FILE* in = fopen(argv[2], "rb"); FILE* out = fopen(argv[3], "wb");
    uint32_t nc; fread(&nc, 4, 1, in);
    fn4 mix = (fn4)(REBASE + (0x5dee90 - 0x400000));
    fn4 peak = (fn4)(REBASE + (0x5df940 - 0x400000));
    for (uint32_t c = 0; c < nc; c++) {
        uint32_t h[6]; fread(h, 4, 6, in);
        float g[8]; fread(g, 4, 8, in);
        uint32_t n = h[1], padS = h[2], padD = h[3], inpl = h[4];
        size_t nw = 2 * (size_t)n + 8;
        float* src = (float*)(SCR_S + 4 * padS);
        memset((void*)SCR_S, 0, 0x1000); /* 先頭ガード */
        fread(src, 4, nw, in);
        float* dst = inpl ? src : (float*)(SCR_D + 4 * padD);
        if (!inpl) memset((void*)SCR_D, 0xA5, 0x1000);
        memcpy((void*)SCR_P, g, 32);
        uint64_t ret;
        if (h[0] == 0) {
            ret = mix((uint64_t)src, (uint64_t)dst, n, SCR_P);
            uint32_t nout = 2 * n + 16;
            fwrite(&ret, 8, 1, out); fwrite(&nout, 4, 1, out); fwrite(dst, 4, nout, out);
        } else {
            *(float*)SCR_O = 0.f; *(float*)(SCR_O + 4) = 0.f;
            ret = peak((uint64_t)src, n, SCR_O, SCR_O + 4);
            uint32_t nout = 2;
            fwrite(&ret, 8, 1, out); fwrite(&nout, 4, 1, out); fwrite((void*)SCR_O, 4, 2, out);
        }
    }
    fclose(out);
    return 0;
}
