/* ks_semantic_filter_kh.c — HeartCore の Filter process (0x1804655e0) を実機 x86-64 機械語のまま同一入力で実行する。
 *   ks_semantic_filter_kh <core_64> <ncases> <seed>
 * 呼び出し形は ks_semantic_gain.c の KH 側と同じ: process(this=rcx, ctx=rdx, aud=r8)。
 * 読み (objdump の逆アセンブル、tools/targets/freshair/REPORT_APPENDIX_FA39.md §2):
 *   aud : L/R の float ポインタ @0/@8、n @0x28 (int)
 *   ctx : P = *(ctx+0x3188)。P+0 type (int, 0..7)、P+4 freq (float, xmm3)、P+8 Q (float)、P+0xc gain (float)、
 *         P+0x10 order (int, 2 倍して渡す)。SC の同じ呼び出し位置 (0x180b6f0f2・0x180b6f1a3) は
 *         P+0x9dc4 type / P+0x9e0c freq / P+0x9e54 Q / P+0x9e9c gain / P+0x9ee4 order を渡す (tools/targets/freshair/REPORT_APPENDIX_FA39.md §2)
 *   this: this+0x60 (float, n/this+0x60 を時間加算に使う → 基準値 48000 とする)、this+0x12d8 (合算バッファ。
 *         0x1802ff250 が ptr+0x28 から書くので、0x28 + 4*n 以上の確保が要る)
 * 出力: case ごとに 1 行。"C<i> n=.. mode=.. ..." 形式の入力、続けて L・R・this[0x60..0x12e0) を hex で出す。
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

typedef long long (__attribute__((ms_abi)) *fn_t)(void*, void*, void*);

#define VA_FILTER 0x1804655e0ULL
#define SUM_VA 0x200000000ULL
#define ST_SIZE 0x1400
#define ST_DUMP_LO 0x60
#define ST_DUMP_HI 0x12e0
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

static uint32_t rng;
static uint32_t R32(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
static float bitsf(uint32_t b) { float f; memcpy(&f, &b, 4); return f; }
static float RF(float lo, float hi) { return lo + (hi - lo) * ((R32() >> 8) / 16777216.0f); }
static float RFS(float lo, float hi) {
    switch (R32() % 24) {
    case 0: return 0.0f;
    case 1: return lo;
    case 2: return hi;
    case 3: return bitsf(0x00000400u);
    case 4: return bitsf(0x80000400u);
    case 5: return 1e-20f;
    default: return RF(lo, hi);
    }
}

typedef struct {
    int n, mode, pn;
    float a, b, c;
    float L[MAXN], R[MAXN];
} Case;

static float LG(float lo, float hi) { return powf(10.0f, RF(lo, hi)); }

static void gen(Case* c) {
    static const int ord[6] = {0, 1, 1, 2, 3, 4};
    c->n = 1 + (int)(R32() % MAXN);
    c->mode = (int)(R32() % 8);
    c->pn = ord[R32() % 6];
    c->a = LG(1.3f, 4.3f);
    c->b = LG(-1, 1);
    c->c = LG(-1, 1);
    for (int i = 0; i < c->n; i++) { c->L[i] = RFS(-1, 1); c->R[i] = RFS(-1, 1); }
}

static void hexdump(FILE* f, const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) fprintf(f, "%02x", b[i]); }

static int run(uint64_t va, Case* c, int idx) {
    uint8_t* self = calloc(1, ST_SIZE);
    uint8_t* aud = calloc(1, 0x40);
    uint8_t* ctx = calloc(1, 0x3200);
    uint8_t* P = calloc(1, 0x20);
    float *L = calloc(MAXN + 1, 4), *R = calloc(MAXN + 1, 4);
    memcpy(L, c->L, sizeof c->L); memcpy(R, c->R, sizeof c->R);
    memset((void*)SUM_VA, 0, 0x1000);
    *(float**)(aud + 0) = L; *(float**)(aud + 8) = R; *(int*)(aud + 0x28) = c->n;
    *(float*)(self + 0x60) = 48000.0f;
    *(void**)(self + 0x12d8) = (uint8_t*)SUM_VA - 0x28;
    *(int*)(P + 0) = c->mode;
    *(float*)(P + 4) = c->a;
    *(float*)(P + 8) = c->b;
    *(float*)(P + 0xc) = c->c;
    *(int*)(P + 0x10) = c->pn;
    *(void**)(ctx + 0x3188) = P;
    printf("C%d n=%d mode=%d pn=%d a=%08x b=%08x c=%08x ", idx, c->n, c->mode, c->pn,
           *(uint32_t*)&c->a, *(uint32_t*)&c->b, *(uint32_t*)&c->c);
    if (getenv("IN_DUMP") && getenv("IN_DUMP")[0] == '1') {
        fprintf(stderr, "I%d ", idx); hexdump(stderr, c->L, c->n * 4); fprintf(stderr, " "); hexdump(stderr, c->R, c->n * 4); fprintf(stderr, "\n");
    }
    ((fn_t)va)(self, ctx, aud);
    hexdump(stdout, L, c->n * 4); printf(" "); hexdump(stdout, R, c->n * 4); printf(" ");
    hexdump(stdout, self + ST_DUMP_LO, ST_DUMP_HI - ST_DUMP_LO); printf("\n");
    free(self); free(aud); free(ctx); free(P); free(L); free(R);
    return 0;
}

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: ks_semantic_filter_kh <core_64> <ncases> <seed>\n"); return 2; }
    int nc = atoi(argv[2]);
    rng = (uint32_t)strtoul(argv[3], 0, 0) * 2654435761u + 12345u; if (!rng) rng = 1;
    map_pe(argv[1]);
    if (mmap((void*)SUM_VA, 0x1000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) != (void*)SUM_VA) { fprintf(stderr, "sum map fail\n"); return 3; }
    for (int i = 0; i < nc; i++) {
        Case c; memset(&c, 0, sizeof c);
        gen(&c);
        run(VA_FILTER, &c, i);
    }
    return 0;
}
