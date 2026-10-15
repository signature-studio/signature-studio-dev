/* xmm0_check.c — kh_xmm0.h の helper を native 実行 (HeartCore.core_64 の callee) と突合する (KH-74・#3853)。
 *   gcc -O1 -ffp-contract=off -o xmm0_check xmm0_check.c -lm
 *   ./xmm0_check <HeartCore.core_64> <trials> <seed>
 * 比較: rax (四分象限) と xmm0 (縮約値) の bit 一致。NaN 同士は一致扱いで件数だけ別に出す。 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include "kh_xmm0.h"

#define IMG 0x180000000UL
typedef uint64_t u64;
typedef uint32_t u32;
typedef uint8_t u8;

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

/* native_ref.c と同じ呼出し形: 引数 xmm0 のみ、戻り rax と xmm0 を回収 */
typedef struct { u64 x0, rax, xmm0; } Frame;
static void call_xmm0(u64 fn, Frame* fr) {
    __asm__ volatile(
        "mov %%rsp, %%r12\n\t"
        "sub $128, %%rsp\n\t"
        "and $-16, %%rsp\n\t"
        "sub $0x20, %%rsp\n\t"
        "movq 0(%%rdi), %%xmm0\n\t"
        "call *%%rbx\n\t"
        "mov %%rax, 8(%%rdi)\n\t"
        "movq %%xmm0, 16(%%rdi)\n\t"
        "mov %%r12, %%rsp\n\t"
        : "+D"(fr)
        : "b"(fn)
        : "rax", "rcx", "rdx", "r8", "r9", "r10", "r11", "r12", "xmm0", "xmm1", "xmm2", "xmm3", "xmm4", "xmm5", "memory", "cc");
}

static u64 rs_state;
static u64 rnd(void) { rs_state ^= rs_state << 13; rs_state ^= rs_state >> 7; rs_state ^= rs_state << 17; return rs_state; }
static double gen(int mode) {
    u64 b;
    switch (mode) {
    case 0: b = rnd(); return *(double*)&b;                                  /* 全ビット乱数 (NaN・Inf・非正規を含む) */
    case 1: return (double)(int64_t)(rnd() % 2000001) / 10.0 - 100000.0;      /* 一様 [-1e5, 1e5] */
    case 2: { double n = (double)(int64_t)(rnd() % 4000001) - 2000000.0;      /* k*pi/2 の近傍 (縮約の境界) */
              return n * 1.5707963267948966 + ((double)(int64_t)(rnd() % 2001) - 1000.0) * 1e-12; }
    default: { static const double sp[] = {0.0, -0.0, 1.0, -1.0, 1e300, -1e300, 4.9e-324, 2.2250738585072014e-308,
                                           1.0 / 0.0, -1.0 / 0.0, 0.0 / 0.0, 1e-20, 6.283185307179586, 3.141592653589793};
               return sp[rnd() % (sizeof sp / sizeof sp[0])]; }
    }
}

/* FUN_180fdc470 の定義域: native は 0<x<1 で table の外を読んで落ちる (指数 < 0)。負の入力と |x|>=1 のみ突合する。 */
static double gen470(void) {
    for (;;) {
        double x = gen((int)(rnd() % 5));
        if (x == x && (x < 0.0 || fabs(x) >= 1.0) && x != 0.0) return x;
    }
}

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: %s <HeartCore.core_64> <trials> <seed>\n", argv[0]); return 2; }
    map_image(argv[1]);
    long n = atol(argv[2]);
    rs_state = (u64)atoll(argv[3]) * 0x9E3779B97F4A7C15ULL + 1;
    const u64 fn = 0x180fdc660ULL, fn470 = 0x180fdc470ULL;
    long mis_rax = 0, mis_x = 0, nan_both = 0, nan_payload = 0;
    long mis_rax470 = 0, mis_x470 = 0, nan470 = 0;
    for (long t = 0; t < n; t++) {
        double x = gen((int)(t % 5));
        Frame fr = { 0 }; memcpy(&fr.x0, &x, 8);
        call_xmm0(fn, &fr);
        unsigned got = kh_fn_180fdc660(x);
        double gx = kh_xmm0_180fdc660;
        u64 gxb; memcpy(&gxb, &gx, 8);
        if ((u64)got != fr.rax) mis_rax++;
        if (gxb != fr.xmm0) {
            double nx; memcpy(&nx, &fr.xmm0, 8);
            if (isnan(gx) && isnan(nx)) { nan_both++; if (gxb != fr.xmm0) nan_payload++; }
            else mis_x++;
        }
        double y = gen470();
        Frame f2 = { 0 }; memcpy(&f2.x0, &y, 8);
        call_xmm0(fn470, &f2);
        unsigned g2 = kh_fn_180fdc470(y);
        double gy = kh_xmm0_180fdc470;
        u64 gyb; memcpy(&gyb, &gy, 8);
        if ((u64)g2 != f2.rax) mis_rax470++;
        if (gyb != f2.xmm0) {
            double ny; memcpy(&ny, &f2.xmm0, 8);
            if (isnan(gy) && isnan(ny)) nan470++;
            else mis_x470++;
        }
    }
    printf("xmm0_check 660: trials %ld | rax mismatch %ld | xmm0 mismatch %ld | NaN both (bit differs %ld)\n",
           n, mis_rax, mis_x, nan_payload);
    printf("xmm0_check 470: trials %ld | rax mismatch %ld | xmm0 mismatch %ld | NaN both %ld\n",
           n, mis_rax470, mis_x470, nan470);
    int ok = (mis_rax == 0 && mis_x == 0 && mis_rax470 == 0 && mis_x470 == 0);
    printf("kh_xmm0_check RESULT: %s\n", ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}
