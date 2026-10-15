/* ks_semantic_vf_kh.c — KH VocalFilter (formant process 0x18085a730) を実機機械語で同一シナリオ実行 (#4071)。
 *   ks_semantic_vf_kh <core_64> scen <scen.txt>
 * 呼び出し形: process(this=rcx, ctx=rdx, aud=r8)。
 * 読み (objdump -d -M intel HeartCore.core_64, REPORT_APPENDIX_FA51.md §2):
 *   ctx : P = *(ctx+0x3188)。
 *         P+0 (float) @18085a76e movss xmm0,[rax] と P+4 (float) @18085a772 movss xmm7,[rax+4] は
 *         @18085a780・@18085a785 で minss/maxss の組 (周波数の下端・上端)。
 *         P+8 (float, Q) @18085a777 movss xmm6,[rax+8] → log10f 側へ。
 *         P+0xc (u8) @18085a789 movzx + and 1 → 0/1 から 2/5 を作る (@18085a790)。
 *         P+0x10 (u8) @18085a796 movzx + and 1 → 0/5 を作る (@18085a79d)。
 *   aud : L/R の float ポインタ @0/@8、n @0x28 (int)。
 *   this: this+0x60 (float, sr)。this+0x12d8 (合算バッファ。0x1802ff250 が ptr+0x28 から書く)。
 * SC (SlateCore 0x1808e1fa0) の同じ値の読み位置: 0x9dc4 (float, @1808e1fd4) と 0x9e0c (float, @1808e1fec) が周波数の組、
 *   0x9e54 (float, Q, @1808e1fcc)、0x9e9c (u8, cmp @1808e2013)・0x9ee4 (u8, neg/sbb @1808e1ff5) が flag、S+0x98 (float, sr, @1808e201a)。
 * 写像: 0x9dc4→P+0、0x9e0c→P+4、0x9e54→P+8、0x9e9c→P+0xc、0x9ee4→P+0x10、S+0x98→this+0x60。
 * 出力: case ごとに 1 行。" |" + this+0x60 (8) + this+0x70 (0x200) + this+0x470 (0x200) + this+0xc70 (0x670) + " " L " " R。
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

typedef long long (__attribute__((ms_abi)) *fn_t)(void*, void*, void*);

#define VA_FILTER 0x18085a730ULL
#define SUM_VA 0x200000000ULL
#define MAXN 128

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

static void hexdump_out(const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) printf("%02x", b[i]); }

/* シナリオ入力 (lift2/gen_vf_scen.py が作る SC 用ファイル) を同じ値で実行する。書込み (region 0=S, 1=P) は上の写像で KH に変換する。 */
static int run_scen(const char* core, const char* path) {
    static char line[1 << 22]; static unsigned long tok[1 << 20];
    map_pe(core);
    if (mmap((void*)SUM_VA, 0x1000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) != (void*)SUM_VA) { fprintf(stderr, "sum map fail\n"); return 3; }
    FILE* fp = fopen(path, "r"); if (!fp) { perror("scen"); return 2; }
    while (fgets(line, sizeof line, fp)) {
        int k = 0; char* p = strtok(line, " \n"); while (p) { tok[k++] = strtoul(p, NULL, 16); p = strtok(NULL, " \n"); }
        int ti = 0; int sidx = (int)tok[ti++]; int ncalls = (int)tok[ti++];
        uint8_t* self = calloc(1, 0x1400); uint8_t* P = calloc(1, 0x20); uint8_t* ctx = calloc(1, 0x3200);
        *(void**)(ctx + 0x3188) = P;
        *(void**)(self + 0x12d8) = (uint8_t*)SUM_VA - 0x28;
        printf("S%d", sidx);
        for (int c = 0; c < ncalls; c++) {
            int nW = (int)tok[ti++];
            for (int w = 0; w < nW; w++) {
                int rg = (int)tok[ti++]; unsigned off = (unsigned)tok[ti++]; uint32_t val = (uint32_t)tok[ti++];
                if (rg == 0 && off == 0x98) memcpy(self + 0x60, &val, 4);
                else if (rg == 1 && off == 0x9dc4) memcpy(P + 0, &val, 4);
                else if (rg == 1 && off == 0x9e0c) memcpy(P + 4, &val, 4);
                else if (rg == 1 && off == 0x9e54) memcpy(P + 8, &val, 4);
                else if (rg == 1 && off == 0x9e9c) memcpy(P + 0xc, &val, 4);
                else if (rg == 1 && off == 0x9ee4) memcpy(P + 0x10, &val, 4);
                else { fprintf(stderr, "unmapped write rg=%d off=%x\n", rg, off); return 4; }
            }
            int n = (int)tok[ti++];
            float* L = calloc(MAXN + 1, 4); float* R = calloc(MAXN + 1, 4);
            for (int i = 0; i < n; i++) { uint32_t b = (uint32_t)tok[ti + i]; memcpy(&L[i], &b, 4); b = (uint32_t)tok[ti + n + i]; memcpy(&R[i], &b, 4); }
            ti += 2 * n;
            uint8_t* aud = calloc(1, 0x40);
            *(float**)(aud + 0) = L; *(float**)(aud + 8) = R; *(int*)(aud + 0x28) = n;
            memset((void*)SUM_VA, 0, 0x1000);
            ((fn_t)VA_FILTER)(self, ctx, aud);
            printf(" |"); hexdump_out(self + 0x60, 8); hexdump_out(self + 0x70, 0x200); hexdump_out(self + 0x470, 0x200);
            hexdump_out(self + 0xc70, 0x670);
            printf(" "); hexdump_out(L, n * 4); printf(" "); hexdump_out(R, n * 4);
            free(aud); free(L); free(R);
        }
        printf("\n");
        free(self); free(P); free(ctx);
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc == 4 && !strcmp(argv[2], "scen")) return run_scen(argv[1], argv[3]);
    fprintf(stderr, "usage: ks_semantic_vf_kh <core_64> scen <scen.txt>\n");
    return 2;
}
