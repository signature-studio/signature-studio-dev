/* ks_semantic_gain.c — Gain の意味同一性 (native vs native 差分)。
 * SlateCore の gain::GainDsp::process (0x180afe090) と HeartCore の同 (0x1804b0380) を、
 * 実機 x86-64 機械語のまま同一入力で実行し、L/R 出力・state・通知 vector を 1 case 1 行で出す。
 *   ks_semantic_gain <sc|kh> <core_64> <ncases> <seed>
 * state の配置は SC = KH + 0x38 (self 基準)。param 経路は SC が this+0x90→P、KH が ctx+0x3188→P。
 * PERTURB=1 のとき KH 側の v を 1 ulp ずらす (感度の負例)。
 * CUR_PROBE=1 のとき入力 L を全サンプル 1.0 にする。ramp の cur はサンプルごとに L へ掛かるので、
 * L 出力 = 逐次 cur (1.0*cur は厳密)。case の入力 (b・v・q28・mode・first・n) は stderr に P 行で出す。
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

#define SO_SC 0x38
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
static int probe_cur;
static int indump;
static uint32_t fbits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
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
    int n, mode, first, dl, dr;
    float v, q28, pos, inc, a, b, cur, c1, m1, c2, m2;
    float L[MAXN], R[MAXN];
} Case;

static void gen(Case* c) {
    c->n = (int)(R32() % (MAXN + 1));
    c->mode = (R32() % 3 == 0) ? 1 : 0;
    c->first = (int)(R32() & 1);
    c->v = (R32() % 5 == 0) ? RFS(-4, 4) : RF(0, 1);
    c->q28 = RFS(-4, 4);
    c->pos = RF(0, 50); c->inc = RF(0, 0.05f);
    c->a = RFS(0, 3); c->b = RFS(0, 3); c->cur = RFS(0, 3);
    c->c1 = RF(0.0005f, 0.5f); c->c2 = RF(0.0005f, 0.5f);
    c->m1 = RF(0, 1); c->m2 = RF(0, 1);
    c->dl = (int)(R32() & 1); c->dr = (int)(R32() & 1);
    for (int i = 0; i < c->n; i++) { c->L[i] = RFS(-1, 1); c->R[i] = RFS(-1, 1); }
}

static void hexdump(const void* p, size_t n) { const uint8_t* b = p; for (size_t i = 0; i < n; i++) printf("%02x", b[i]); }

static void run(int sc, uint64_t va, Case* c, int perturb, int dump, int idx) {
    uint8_t* self = calloc(1, 0x200);
    uint8_t* aud = calloc(1, 0x40);                 /* L/R ptr と n (ctx 相当) */
    float *L = calloc(MAXN + 1, 4), *R = calloc(MAXN + 1, 4);
    memcpy(L, c->L, sizeof c->L); memcpy(R, c->R, sizeof c->R);
    if (probe_cur) {
        fprintf(stderr, "I%d ", idx);
        for (int i = 0; i < c->n * 4; i++) fprintf(stderr, "%02x", ((const uint8_t*)c->L)[i]);
        fprintf(stderr, "\n");
        for (int i = 0; i < c->n; i++) L[i] = 1.0f;
    }
    *(float**)(aud + 0) = L; *(float**)(aud + 8) = R; *(int*)(aud + 0x28) = c->n;
    uint8_t* vbuf = calloc(1, 0x40);                 /* 通知 vector (begin/end/cap) */
    int so = sc ? SO_SC : 0;
    *(float*)(self + so + 0x64) = getenv("POS0") ? 0.0f : c->pos;
    *(float*)(self + so + 0x68) = c->inc;
    *(float*)(self + so + 0x6c) = c->a;
    *(float*)(self + so + 0x70) = c->b;
    *(float*)(self + so + 0x74) = c->cur;
    self[so + 0x78] = (uint8_t)c->first;
    *(float*)(self + so + 0x84) = c->c1; *(float*)(self + so + 0x88) = c->m1;
    *(float*)(self + so + 0x94) = c->c2; *(float*)(self + so + 0x98) = c->m2;
    if (dump) fprintf(stderr, "M%d %.9g %.9g %.9g %.9g\n", idx, *(float*)(self + so + 0x88), *(float*)(self + so + 0x84), *(float*)(self + so + 0x98), *(float*)(self + so + 0x94));
    if (indump) {
        fprintf(stderr, "X%d ", idx);
        for (int i = 0; i < 0x38; i++) fprintf(stderr, "%02x", self[so + 0x64 + i]);
        fprintf(stderr, " ");
        for (int i = 0; i < c->n * 4; i++) fprintf(stderr, "%02x", ((const uint8_t*)c->L)[i]);
        fprintf(stderr, " ");
        for (int i = 0; i < c->n * 4; i++) fprintf(stderr, "%02x", ((const uint8_t*)c->R)[i]);
        fprintf(stderr, "\n");
    }
    if (sc) {
        uint8_t* P = calloc(1, 0xa000); uint8_t* Q = calloc(1, 0x80);
        *(void**)(self + 0x90) = P; *(void**)(P + 0x9f30) = Q;
        *(int*)(P + 0x9dc4) = c->mode;
        *(float*)(P + 0x9e0c) = c->v;
        *(float*)(P + 0x9e18) = c->q28;
        P[0x9e93] = (uint8_t)c->dl; P[0x9edb] = (uint8_t)c->dr;
        *(void**)(Q + 0x28) = vbuf; *(void**)(Q + 0x30) = vbuf; *(void**)(Q + 0x38) = vbuf + 8;
        ((fn_t)va)(self, aud, 0);
        uint64_t end; memcpy(&end, Q + 0x30, 8);
        printf("%lu ", (unsigned long)(end - (uint64_t)(uintptr_t)vbuf));
        hexdump(vbuf, 8);
    } else {
        int id = 2000;
        uint8_t* ctx = calloc(1, 0x3200); uint8_t* P = calloc(1, 0x10); uint8_t* Q = calloc(1, 0x80);
        uint8_t* V = calloc(1, 0x80); int* vec = calloc(64, 4);
        *(void**)(ctx + 0x3188) = P; *(void**)(ctx + 0x3198) = Q; *(void**)(ctx + 0x31b0) = V;
        *(int*)(ctx + 0x3180) = id;
        *(int*)(P + 0) = c->mode;
        *(float*)(P + 4) = perturb ? nextafterf(c->v, 2.0f) : c->v;
        *(float*)(Q + 0x28) = c->q28;
        Q[0x5c] = (uint8_t)c->dl; Q[0x7c] = (uint8_t)c->dr;
        *(int**)(V + 0x68) = vec; *(int**)(V + 0x70) = vec + 16;
        ((fn_t)va)(self, ctx, aud);
        int np = (int)(*(int**)(V + 0x68) - vec);
        printf("%d ", np);
        if (np == 0) printf("-");
        for (int i = 0; i < np; i++) printf("%08x", (uint32_t)(vec[i] - id));
    }
    if (probe_cur) {
        if (sc) fprintf(stderr, "S%d coef=%08x A=%08x B=%08x\n", idx, fbits(*(float*)(self + 0xa0)), fbits(*(float*)(self + 0xa4)), fbits(*(float*)(self + 0xa8)));
        else fprintf(stderr, "K%d pos0=%08x inc=%08x a=%08x b=%08x\n", idx, fbits(c->pos), fbits(*(float*)(self + 0x68)), fbits(*(float*)(self + 0x6c)), fbits(*(float*)(self + 0x70)));
    }
    printf(" ");
    if (c->n) { hexdump(L, c->n * 4); printf(" "); hexdump(R, c->n * 4); } else printf("- -");
    printf(" ");
    hexdump(self + so + 0x64, 0x38); printf("\n");
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: ks_semantic_gain <sc|kh> <core_64> <ncases> <seed>\n"); return 2; }
    int sc = !strcmp(argv[1], "sc");
    uint64_t va = sc ? 0x180afe090ULL : 0x1804b0380ULL;
    int nc = atoi(argv[3]);
    rng = (uint32_t)strtoul(argv[4], 0, 0) * 2654435761u + 12345u; if (!rng) rng = 1;
    int perturb = getenv("PERTURB") && getenv("PERTURB")[0] == '1';
    int dump = getenv("METER_DUMP") && getenv("METER_DUMP")[0] == '1';
    probe_cur = getenv("CUR_PROBE") && getenv("CUR_PROBE")[0] == '1';
    indump = getenv("IN_DUMP") && getenv("IN_DUMP")[0] == '1';
    map_pe(argv[2]);
    for (int i = 0; i < nc; i++) {
        Case c; memset(&c, 0, sizeof c);
        gen(&c);
        printf("C%d n=%d mode=%d first=%d dl=%d dr=%d ", i, c.n, c.mode, c.first, c.dl, c.dr);
        run(sc, va, &c, perturb && !sc, dump, i);
    }
    return 0;
}
