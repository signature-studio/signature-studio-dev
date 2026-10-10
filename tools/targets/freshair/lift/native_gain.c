/* native_gain.c — 実機 x86-64 機械語参照: SlateCore.core_64 を ImageBase に MAP_FIXED 敷設し,
 * gain::GainDsp::process (0x180afe090) を MS x64 ABI で直接実行 (m5 native_fx.c 方式)。
 *   ./native_gain <SlateCore.core_64> <scen.txt>   → 各シナリオの状態ダンプ (hex 1 行) */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

typedef long long (__attribute__((ms_abi)) *fn_t)(void*, void*);
#define PROCESS_VA 0x180afe090ULL

static uint8_t* map_pe(const char* path) {
    int fd = open(path, O_RDONLY); if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t ns, osz; memcpy(&ns, f + pe + 6, 2); memcpy(&osz, f + pe + 20, 2);
    uint64_t base; memcpy(&base, f + pe + 24 + 24, 8);
    uint32_t img; memcpy(&img, f + pe + 24 + 56, 4);
    uint8_t* m = mmap((void*)base, (img + 4095) & ~4095UL, PROT_READ | PROT_WRITE | PROT_EXEC,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (m != (void*)base) { fprintf(stderr, "map fail %p\n", m); exit(3); }
    uint32_t hdr; memcpy(&hdr, f + pe + 24 + 60, 4);
    memcpy(m, f, hdr);
    for (int i = 0; i < ns; i++) {
        uint8_t* s = f + pe + 24 + osz + i * 40;
        uint32_t vs, va, rs, rp; memcpy(&vs, s + 8, 4); memcpy(&va, s + 12, 4); memcpy(&rs, s + 16, 4); memcpy(&rp, s + 20, 4);
        memcpy(m + va, f + rp, rs < vs ? rs : vs);
    }
    return m;
}

static void hexdump(const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) printf("%02x", b[i]); }

int main(int argc, char** argv) {
    map_pe(argv[1]);
    fn_t fn = (fn_t)PROCESS_VA;
    FILE* fp = fopen(argv[2], "r"); if (!fp) { perror("scen"); return 2; }
    static char line[1 << 16]; int idx = 0;
    while (fgets(line, sizeof line, fp)) {
        unsigned long v[16 + 2 * 256]; int k = 0; char* p = strtok(line, " \n");
        while (p) { v[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int n = (int)v[3];
        uint8_t* a1 = calloc(1, 0x100); uint8_t* P = calloc(1, 0xa000); uint8_t* Q = calloc(1, 0x80);
        uint8_t* buf = calloc(1, 32); uint8_t* ctx = calloc(1, 0x30);
        float* L = calloc(n + 1, 4); float* R = calloc(n + 1, 4);
        for (int i = 0; i < n; i++) { memcpy(&L[i], &(uint32_t){(uint32_t)v[16 + i]}, 4); memcpy(&R[i], &(uint32_t){(uint32_t)v[16 + n + i]}, 4); }
#define W32(base, off, val) do { uint32_t _t = (uint32_t)(val); memcpy((base) + (off), &_t, 4); } while (0)
#define W64(base, off, val) do { uint64_t _t = (uint64_t)(uintptr_t)(val); memcpy((base) + (off), &_t, 8); } while (0)
        W64(a1, 0x90, P);
        W32(P, 0x9dc4, v[0]); W32(P, 0x9e0c, v[1]); W32(P, 0x9e18, v[2]);
        P[0x9e93] = (uint8_t)v[12]; P[0x9edb] = (uint8_t)v[13]; W32(P, 0x9e50, v[14]); W32(P, 0x9e98, v[15]);
        W64(P, 0x9f30, Q);
        W64(Q, 0x28, buf); W64(Q, 0x30, buf); W64(Q, 0x38, buf + 8);
        a1[0xb0] = (uint8_t)v[4]; W32(a1, 0xa8, v[5]); W32(a1, 0xac, v[6]); W32(a1, 0xa4, v[7]);
        W32(a1, 0xbc, v[8]); W32(a1, 0xc0, v[9]); W32(a1, 0xcc, v[10]); W32(a1, 0xd0, v[11]);
        W64(ctx, 0, L); W64(ctx, 8, R); W32(ctx, 0x28, n);
        fn(a1, ctx);
        printf("S%d ", idx++);
        hexdump(a1 + 0x9c, 0x38); printf(" ");
        hexdump(P + 0x9e50, 8); hexdump(P + 0x9e93, 1); hexdump(P + 0x9e98, 8); hexdump(P + 0x9edb, 1); printf(" ");
        uint64_t end; memcpy(&end, Q + 0x30, 8); printf("%lu ", (unsigned long)((end - (uint64_t)(uintptr_t)buf)));
        hexdump(buf, 8); printf(" "); hexdump(L, n * 4); printf(" "); hexdump(R, n * 4); printf("\n");
        free(a1); free(P); free(Q); free(buf); free(ctx); free(L); free(R);
    }
    return 0;
}
