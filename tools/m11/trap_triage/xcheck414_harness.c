/* xcheck414_harness.c (#764): function_414ad0 の C 版 / IR 版 / LStr 版を、xcheck414.py と同じ入力・同じ外部スタブで実行する。
 * ビルド: -DBODY_C (body_c.c = m11_ov.c の UStr 分岐) / -DBODY_LSTR (body_lstr.c = #else 側) / 無指定 (IR オブジェクトとリンク)。
 * 実行: harness cases.bin G_WORD。cases.bin = u32 件数, 各 case は i32 n + 32KiB のアリーナ。
 * 出力は 1 case 1 行: fault ret fnv1a64(arena) bump。外部スタブの仕様は xcheck414.py の unicorn 側と同一。 */
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
#include <signal.h>
#include <sys/mman.h>

typedef uint64_t u64;
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;
typedef int32_t i32;
typedef int64_t i64;
#define Q(lva) (*(volatile u64*)(uintptr_t)(lva))
#define D(lva) (*(volatile u32*)(uintptr_t)(lva))

#define ARENA_BASE 0x20000000ULL
#define ARENA_SIZE 0x8000ULL
#define HEAP0 (ARENA_BASE + 0x3000ULL)
#define EMPTY (ARENA_BASE + 0x2010ULL)

static u64 bump;
static int fault;
static u16 G_WORD;
static sigjmp_buf jb;
static u64 sz_ptr[256], sz_val[256];
static int nsz;

static void do_fault(void) { fault = 1; siglongjmp(jb, 1); }

static void on_sig(int sig) { (void)sig; do_fault(); }

static u64 alloc_blk(u64 n) {
    if (bump + n > ARENA_BASE + ARENA_SIZE) do_fault();
    u64 p = bump;
    bump += (n + 15) & ~15ULL;
    if (nsz < 256) { sz_ptr[nsz] = p; sz_val[nsz] = n; nsz++; }
    return p;
}

static u64 lookup_sz(u64 p) {
    for (int i = 0; i < nsz; i++) if (sz_ptr[i] == p) return sz_val[i];
    return 0;
}

u64 function_414850(u64 p) { return p ? p : EMPTY; }

u64 function_412d60(u64 dest, u64 unused) {
    (void)unused;
    u64 old = Q(dest);
    if (old) {
        u64 hdr = old - 0x10;
        Q(dest) = 0;
        i32 rc = (i32)D(hdr + 8);
        if (rc > 0) D(hdr + 8) = (u32)(rc - 1);
    }
    return dest;
}

u64 function_409470(void* pv, u64 newsize) {
    u64 cur = *(volatile u64*)pv;
    u64 nw = 0;
    if (cur) {
        if ((i64)newsize > 0) {
            nw = alloc_blk(newsize);
            u64 osz = lookup_sz(cur);
            u64 m = osz < newsize ? osz : newsize;
            memmove((void*)(uintptr_t)nw, (void*)(uintptr_t)cur, (size_t)m);
        }
    } else if ((i64)newsize > 0) {
        nw = alloc_blk(newsize);
    }
    *(volatile u64*)pv = nw;
    return nw;
}

u64 function_412c20(u64 ecx) {
    i32 n = (i32)(u32)ecx;
    if (n <= 0) return 0;
    u64 sz = (u64)((i64)n + 1) * 2 + 16;
    u64 c = alloc_blk(sz);
    D(c + 0xc) = (u32)n;
    D(c + 8) = 1;
    *(volatile u16*)(uintptr_t)(c + 6) = 2;
    *(volatile u16*)(uintptr_t)(c + 4) = G_WORD;
    *(volatile u16*)(uintptr_t)(c + 16 + (u64)((i64)n * 2)) = 0;
    return c + 16;
}

u64 function_409c80(u64 src, u64 dst, u64 n) {
    if ((i64)n > 0) memmove((void*)(uintptr_t)dst, (void*)(uintptr_t)src, (size_t)n);
    return 0;
}

u64 function_40f560(u64 a, u64 b) { (void)a; (void)b; do_fault(); return 0; }

#ifdef BODY_C
#include "body_c.c"
#elif defined(BODY_LSTR)
#include "body_lstr.c"
#else
extern u64 function_414ad0(u64 arg1, u64 arg2);
#endif

static u64 fnv(const u8* p, size_t n) {
    u64 h = 1469598103934665603ULL;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
    return h;
}

int main(int argc, char** argv) {
    if (argc != 3) return 2;
    G_WORD = (u16)strtoul(argv[2], NULL, 10);
    FILE* f = fopen(argv[1], "rb");
    if (!f) return 2;
    u32 count;
    if (fread(&count, 4, 1, f) != 1) return 2;
    void* a = mmap((void*)ARENA_BASE, ARENA_SIZE, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    if (a != (void*)ARENA_BASE) return 3;
    u8* img = malloc(ARENA_SIZE);
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_sig;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
    for (u32 c = 0; c < count; c++) {
        i32 n;
        if (fread(&n, 4, 1, f) != 1) return 2;
        if (fread(img, 1, ARENA_SIZE, f) != ARENA_SIZE) return 2;
        memcpy(a, img, ARENA_SIZE);
        bump = HEAP0;
        nsz = 0;
        fault = 0;
        u64 ret = 0;
        if (sigsetjmp(jb, 1) == 0) {
            ret = function_414ad0(ARENA_BASE + 0x80, (u64)(u32)n);
        } else {
            fault = 1;
        }
        printf("%d %llu %016llx %llu\n", fault, (unsigned long long)(fault ? 0 : ret),
               (unsigned long long)fnv((const u8*)a, ARENA_SIZE), (unsigned long long)bump);
    }
    return 0;
}
