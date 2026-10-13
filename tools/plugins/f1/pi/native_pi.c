/* native 参照 (x86_64 Linux): Fruity Phase Inverter_x64.dll を VA 0x400000 に MAP_FIXED 敷設し、
 * Eff_Render(this, src, dst, len) (MS x64 ABI) を実機械語のまま呼ぶ。lift IR / wasm に非依存。
 *   usage: native_pi <dll> <cases.bin> <results.bin>
 * cases.bin : u32 ncases, 各 case = {i32 mode; u32 n, padS, padD, inplace; f32 src[2n]}
 * results.bin: 各 case {u64 ret; u32 nd; u32 dst[nd] (nd=2n+16); u32 ns; u32 src[ns] (ns=2n)}
 * 外部状態: 0x709e00 の cell が指す bss 変数 0x717e98 は dsp_ippv2!ippsMove_8u(pSrc,pDst,len) の関数ポインタ。
 *           Windows の DLL は無いので同一意味 (memmove) の ms_abi 関数を差し込む。
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#define REBASE 0x400000UL
#define EFF 0x6ba930UL
#define MOVE_VAR 0x717e98UL
#define SCR_T 0x18300000UL
#define SCR_S 0x18000000UL
#define SCR_D 0x18100000UL
typedef uint64_t (__attribute__((ms_abi)) *fn4)(uint64_t, uint64_t, uint64_t, uint64_t);

static uint64_t __attribute__((ms_abi)) ipps_move_8u(uint64_t src, uint64_t dst, uint64_t len) {
    memmove((void*)dst, (void*)src, (uint32_t)len);
    return 0;
}
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
    scr(SCR_S, 0x100000); scr(SCR_D, 0x100000); scr(SCR_T, 0x10000);
    *(uint64_t*)MOVE_VAR = (uint64_t)(uintptr_t)ipps_move_8u;
    FILE* in = fopen(argv[2], "rb"); FILE* out = fopen(argv[3], "wb");
    uint32_t nc; if (fread(&nc, 4, 1, in) != 1) return 4;
    fn4 eff = (fn4)(EFF);
    for (uint32_t c = 0; c < nc; c++) {
        int32_t mode; uint32_t h[4];
        if (fread(&mode, 4, 1, in) != 1 || fread(h, 4, 4, in) != 4) return 4;
        uint32_t n = h[0], padS = h[1], padD = h[2], inpl = h[3];
        size_t ns = 2 * (size_t)n;
        memset((void*)SCR_S, 0, 0x1000);
        float* src = (float*)(SCR_S + 4 * padS);
        if (ns && fread(src, 4, ns, in) != ns) return 4;
        float* dst = inpl ? src : (float*)(SCR_D + 4 * padD);
        if (!inpl) memset((void*)SCR_D, 0xA5, 0x1000);
        memset((void*)SCR_T, 0, 0x400);
        *(int32_t*)(SCR_T + 0x128) = mode;
        uint64_t ret = eff(SCR_T, (uint64_t)src, (uint64_t)dst, n);
        uint32_t nd = 2 * n + 16;
        fwrite(&ret, 8, 1, out); fwrite(&nd, 4, 1, out); fwrite(dst, 4, nd, out);
        uint32_t nss = (uint32_t)ns; fwrite(&nss, 4, 1, out); fwrite(src, 4, ns, out);
    }
    fclose(out);
    return 0;
}
