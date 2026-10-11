/* native_ref.c — ctx-fuzz 汎用 native 参照ドライバ (poc_gain/native_ref.c の汎化)。
 *   native_ref <HeartCore.core_64> <scenario> <ntrials> <seed> <out.bin>
 *   native_ref - list                       (scenario 一覧)
 *
 * vectors.bin 形式 (little endian):
 *   "KHV2" u32 ntrials u32 nregions_max(0)
 *   trial*: u32 ncalls u32 0
 *     call*: u32 npatch { u32 off u32 len bytes }*  u64 va u64 a[4] u64 x[4] u32 rk u64 rax u64 xmm0 u32 postlen post[postlen]
 *     u32 nreg { u32 off u32 len u32 namelen name[] }*
 */
#define _GNU_SOURCE
#include "ctxfuzz.h"
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#define IMG 0x180000000UL

static void map_image(const char* path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) { perror("open"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    u8* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    u32 pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t ns, osz; memcpy(&ns, f + pe + 6, 2); memcpy(&osz, f + pe + 20, 2);
    u32 soff = pe + 24 + osz, imgsz; memcpy(&imgsz, f + pe + 24 + 56, 4);
    void* b = mmap((void*)IMG, imgsz, PROT_READ | PROT_WRITE | PROT_EXEC,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE | MAP_NORESERVE, -1, 0);
    if (b != (void*)IMG) { fprintf(stderr, "cannot map image at %lx\n", IMG); exit(3); }
    for (int i = 0; i < ns; i++) {
        u32 vs, va, rs, rp; u8* e = f + soff + i * 40;
        memcpy(&vs, e + 8, 4); memcpy(&va, e + 12, 4); memcpy(&rs, e + 16, 4); memcpy(&rp, e + 20, 4);
        u32 n = rs < vs ? rs : vs;
        memcpy((void*)(IMG + va), f + rp, n);
    }
}

static u8* arena; static size_t used, shadow_used;
static u8* shadow;
static u32 rng;
static FILE* out;
static int ncalls_cur;
static struct { char name[32]; u32 off, len; } regs[64]; static int nreg;

void* A(size_t n) {
    size_t o = (used + 15) & ~15UL;
    if (o + n > ARENA_SIZE) { fprintf(stderr, "arena overflow\n"); exit(4); }
    used = o + n;
    return arena + o;
}
void REGION(const char* name, const void* p, size_t n) {
    strncpy(regs[nreg].name, name, 31); regs[nreg].off = (u32)((const u8*)p - arena); regs[nreg].len = (u32)n; nreg++;
}
u32 R32(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }
float RF(float lo, float hi) { return lo + (hi - lo) * ((R32() >> 8) / 16777216.0f); }
int RI(int lo, int hi) { return lo + (int)(R32() % (u32)(hi - lo + 1)); }
float RFSPECIAL(float lo, float hi) {
    switch (R32() % 24) {
    case 0: return 0.0f;
    case 1: return lo;
    case 2: return hi;
    case 3: return bitsf(0x00000400u);          /* 非正規数 */
    case 4: return bitsf(0x80000400u);
    case 5: return 1e-20f;
    default: return RF(lo, hi);
    }
}

typedef struct { u64 a[8], x[4], rax, xmm0; } Frame;
static u64 msx64_call(u64 fn, Frame* fr) {
    __asm__ volatile(
        "mov %%rsp, %%r12\n\t"
        "sub $128, %%rsp\n\t"
        "and $-16, %%rsp\n\t"
        "sub $0x20, %%rsp\n\t"
        "mov 0(%%rdi), %%rcx\n\t"
        "mov 8(%%rdi), %%rdx\n\t"
        "mov 16(%%rdi), %%r8\n\t"
        "mov 24(%%rdi), %%r9\n\t"
        "/* スタック引数 a4..a7 (Frame+32..56) → call 後 callee entry rsp+0x28+8k == call 前 rsp+0x20+8k */\n\t"
        "mov 32(%%rdi), %%rax\n\t"
        "mov %%rax, 0x20(%%rsp)\n\t"
        "mov 40(%%rdi), %%rax\n\t"
        "mov %%rax, 0x28(%%rsp)\n\t"
        "mov 48(%%rdi), %%rax\n\t"
        "mov %%rax, 0x30(%%rsp)\n\t"
        "mov 56(%%rdi), %%rax\n\t"
        "mov %%rax, 0x38(%%rsp)\n\t"
        "movq 64(%%rdi), %%xmm0\n\t"
        "movq 72(%%rdi), %%xmm1\n\t"
        "movq 80(%%rdi), %%xmm2\n\t"
        "movq 88(%%rdi), %%xmm3\n\t"
        "call *%%rbx\n\t"
        "mov %%rax, 96(%%rdi)\n\t"
        "movq %%xmm0, 104(%%rdi)\n\t"
        "mov %%r12, %%rsp\n\t"
        : "+D"(fr)
        : "b"(fn)
        : "rax", "rcx", "rdx", "r8", "r9", "r10", "r11", "r12", "xmm0", "xmm1", "xmm2", "xmm3", "xmm4", "xmm5", "memory", "cc");
    return fr->rax;
}

static void w32(u32 v) { fwrite(&v, 4, 1, out); }
static void w64(u64 v) { fwrite(&v, 8, 1, out); }

u64 do_call(u64 va, int rk, u64 a0, u64 a1, u64 a2, u64 a3, u64 x0, u64 x1, u64 x2, u64 x3, u64 a4, u64 a5, u64 a6, u64 a7) {
    /* patch = 現アリーナ vs shadow (wasm 側が持っている状態) の差分 */
    size_t n = used;
    long pp = ftell(out); w32(0); u32 np = 0;
    for (size_t i = 0; i < n;) {
        u8 sv = i < shadow_used ? shadow[i] : 0;
        if (arena[i] == sv) { i++; continue; }
        size_t j = i, last = i;
        while (j < n && j - last <= 8) { u8 s2 = j < shadow_used ? shadow[j] : 0; if (arena[j] != s2) last = j; j++; }
        w32((u32)i); w32((u32)(last - i + 1)); fwrite(arena + i, 1, last - i + 1, out); np++;
        i = last + 1;
    }
    long pe = ftell(out); fseek(out, pp, SEEK_SET); w32(np); fseek(out, pe, SEEK_SET);
    Frame fr = {{a0, a1, a2, a3, a4, a5, a6, a7}, {x0, x1, x2, x3}, 0, 0};
    msx64_call(va, &fr);
    w64(va); for (int i = 0; i < 8; i++) w64(fr.a[i]); for (int i = 0; i < 4; i++) w64(fr.x[i]);
    w32(rk); w64(fr.rax); w64(fr.xmm0);
    w32((u32)used); fwrite(arena, 1, used, out);
    if (used > shadow_used) memset(shadow + shadow_used, 0, used - shadow_used);
    memcpy(shadow, arena, used); shadow_used = used;
    ncalls_cur++;
    return fr.rax;
}

int main(int argc, char** argv) {
    if (argc >= 3 && !strcmp(argv[2], "list")) { for (Scenario* s = SCEN_LIST; s->name; s++) puts(s->name); return 0; }
    if (argc < 6) { fprintf(stderr, "usage: native_ref <core> <scenario> <ntrials> <seed> <out.bin>\n"); return 2; }
    Scenario* sc = NULL;
    for (Scenario* s = SCEN_LIST; s->name; s++) if (!strcmp(s->name, argv[2])) sc = s;
    if (!sc) { fprintf(stderr, "unknown scenario %s\n", argv[2]); return 2; }
    int nt = atoi(argv[3]); u32 seed = (u32)strtoul(argv[4], 0, 0);
    map_image(argv[1]);
    arena = mmap((void*)ARENA_BASE, ARENA_SIZE, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (arena != (void*)ARENA_BASE) { fprintf(stderr, "cannot map arena\n"); return 3; }
    shadow = calloc(1, ARENA_SIZE);
    out = fopen(argv[5], "w+b");
    fwrite("KHV2", 1, 4, out); w32((u32)nt); w32(0);
    for (int t = 0; t < nt; t++) {
        /* trial 冒頭の zero 化: mgr slot 0x0400F020 (ARENA_CLEAR 内) を毎 trial 同じ初期状態にするため
         * used 累積ではなく固定窓を掩う (subscribe 経路が mgr ヒープ相当アドレスを使うため) */
        memset(arena, 0, ARENA_CLEAR); used = 0; memset(shadow, 0, shadow_used); shadow_used = 0; nreg = 0; ncalls_cur = 0;
        rng = seed * 2654435761u + (u32)t * 40503u + 12345u; if (!rng) rng = 1;
        for (int k = 0; k < 4; k++) R32();
        long p0 = ftell(out); w32(0); w32(0);          /* ncalls, nreg 後置 */
        long p1 = ftell(out);
        /* regions は trial 後に書けないので、先にダミーを書かず trial 末尾に置く: 形式上 calls の後ろ */
        (void)p1;
        sc->trial(t);
        w32((u32)nreg);
        for (int i = 0; i < nreg; i++) { w32(regs[i].off); w32(regs[i].len); u32 l = (u32)strlen(regs[i].name); w32(l); fwrite(regs[i].name, 1, l, out); }
        long pe = ftell(out); fseek(out, p0, SEEK_SET); w32((u32)ncalls_cur); w32(0); fseek(out, pe, SEEK_SET);
    }
    fclose(out);
    return 0;
}
