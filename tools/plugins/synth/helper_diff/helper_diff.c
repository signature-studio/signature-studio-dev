/* helper_diff.c — #535 の helper 7 件 + i256 (ymm) 経路の単体差分試験。 native = この CPU で実命令を実行 (cmpps/movmskps/prefetcht0/
 * rep movsd/rep stosb は asm、vaddps 系は同名 intrinsic = 1 命令)。 被検側 = m11_simd2.py の生成 C / fix_avx256.py が lower した IR。
 * 不一致が 1 件でもあれば exit 1 (run 毎の件数を最後に出す)。 NaN は「NaN どうし」を同一視する (算術の NaN payload は wasm で不定。 比較は bit 一致 or 両方 NaN)。
 *   build: helper_diff.sh が行う (clang -O1 -mavx2)。 */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned __int128 u128;
typedef unsigned long long u64;
typedef unsigned int u32;
typedef unsigned char u8;

u128 __asm_cmpnltps(u128, u128);
u32 __asm_movmskps(u128);
void __asm_prefetcht0(u32);
void __asm_rep_movsd_memcpy(void*, void*, u64);
void __asm_rep_stosb_memset(void*, u32, u64);
/* IR 側 (fix_avx256 後)。 i256 は呼出境界に出さず、ptr 経由の薄い関数にしてある */
void t_vmovaps(void*, void*);
void t_vaddps(void*, void*, void*);
void t_vsubps(void*, void*, void*);
void t_vmulps(void*, void*, void*);
void t_vdivps(void*, void*, void*);
void t_vminps(void*, void*, void*);
void t_vmaxps(void*, void*, void*);
void t_vext0(void*, void*);
void t_vext1(void*, void*);
void t_vstore256(void*, void*);
void t_vstore128(void*, void*);

static u64 s0 = 0x9e3779b97f4a7c15ull, s1 = 0xbf58476d1ce4e5b9ull;
static u64 rnd(void) { u64 x = s0, y = s1; s0 = y; x ^= x << 23; s1 = x ^ y ^ (x >> 17) ^ (y >> 26); return s1 + y; }
static u32 rf(void) {   /* 特殊値を厚めに混ぜた f32 bit */
    switch (rnd() % 12) {
    case 0: return 0; case 1: return 0x80000000u; case 2: return 0x7f800000u; case 3: return 0xff800000u;
    case 4: return 0x7fc00000u; case 5: return 0x7f800001u; case 6: return 0x00000001u; case 7: return 0x3f800000u;
    default: return (u32)rnd();
    }
}
static long fails;
static long cnt;
#define CHECK(c, ...) do { cnt++; if (!(c)) { if (fails < 20) { printf("MISMATCH " __VA_ARGS__); printf("\n"); } fails++; } } while (0)
static int same_f32(u32 a, u32 b) { float x, y; memcpy(&x, &a, 4); memcpy(&y, &b, 4); return a == b || (x != x && y != y); }

int main(int argc, char** argv) {
    long N = argc > 1 ? atol(argv[1]) : 200000;
    /* cmpnltps / movmskps (128bit, 4 lane) */
    for (long i = 0; i < N; i++) {
        u32 a[4], b[4];
        for (int k = 0; k < 4; k++) { a[k] = rf(); b[k] = rf(); }
        __m128 x, y; memcpy(&x, a, 16); memcpy(&y, b, 16);
        __m128 nr = _mm_cmpnlt_ps(x, y);
        u128 h = __asm_cmpnltps(*(u128*)a, *(u128*)b), n; memcpy(&n, &nr, 16);
        CHECK(h == n, "cmpnltps");
        u32 mm = (u32)_mm_movemask_ps(nr);
        CHECK(__asm_movmskps(h) == mm, "movmskps(cmp)");
        u128 r; u32 rr[4]; for (int k = 0; k < 4; k++) rr[k] = rf(); memcpy(&r, rr, 16);
        __m128 rx; memcpy(&rx, rr, 16);
        CHECK(__asm_movmskps(r) == (u32)_mm_movemask_ps(rx), "movmskps(raw)");
    }
    /* prefetcht0: 状態を変えない。 native も hint (呼んでも副作用なし) */
    { u8 buf[64] = {1}; u8 c0[64]; memcpy(c0, buf, 64); __asm__ volatile("prefetcht0 (%0)" :: "r"(buf)); __asm_prefetcht0((u32)(uintptr_t)buf & 0xff); CHECK(!memcmp(buf, c0, 64), "prefetcht0"); }
    /* rep movsd / rep stosb: 重なり (dst > src, dst < src) と長さ 0 を含む */
    for (long i = 0; i < N / 10; i++) {
        u8 A[512], Bn[512], Bh[512];
        for (int k = 0; k < 512; k++) A[k] = (u8)rnd();
        memcpy(Bn, A, 512); memcpy(Bh, A, 512);
        u64 cnt32 = rnd() % 40; size_t so = rnd() % 64, d_o = rnd() % 64;
        if (rnd() % 3 == 0) d_o = so + (rnd() % 8);          /* 近接重なり (dst >= src) */
        void *s = Bn + so, *d = Bn + d_o; u64 c = cnt32;
        __asm__ volatile("cld; rep movsl" : "+D"(d), "+S"(s), "+c"(c) :: "memory");
        __asm_rep_movsd_memcpy(Bh + d_o, Bh + so, cnt32);
        CHECK(!memcmp(Bn, Bh, 512), "rep_movsd so=%zu do=%zu n=%llu", so, d_o, (unsigned long long)cnt32);
        u8 SN[300], SH[300]; for (int k = 0; k < 300; k++) SN[k] = SH[k] = (u8)rnd();
        u8 v = (u8)rnd(); u64 n2 = rnd() % 200; size_t o2 = rnd() % 64; void* dd = SN + o2; u64 cc = n2;
        __asm__ volatile("cld; rep stosb" : "+D"(dd), "+c"(cc) : "a"(v) : "memory");
        __asm_rep_stosb_memset(SH + o2, (u32)v | ((u32)(rnd() & 0xffffff) << 8), n2);   /* al だけが意味を持つ (上位ビットは無視されること) */
        CHECK(!memcmp(SN, SH, 300), "rep_stosb o=%zu n=%llu v=%u", o2, (unsigned long long)n2, v);
    }
    /* ymm 経路 (IR lower) */
    for (long i = 0; i < N; i++) {
        u32 a[8], b[8], o[8], e[8];
        for (int k = 0; k < 8; k++) { a[k] = rf(); b[k] = rf(); }
        __m256 x, y, r; memcpy(&x, a, 32); memcpy(&y, b, 32);
#define OPT(NAME, INTR) r = INTR(x, y); memcpy(e, &r, 32); memset(o, 0xcc, 32); t_##NAME(a, b, o); \
        for (int k = 0; k < 8; k++) CHECK(same_f32(o[k], e[k]), #NAME " lane%d a=%08x b=%08x got=%08x exp=%08x", k, a[k], b[k], o[k], e[k]);
        OPT(vaddps, _mm256_add_ps) OPT(vsubps, _mm256_sub_ps) OPT(vmulps, _mm256_mul_ps)
        OPT(vdivps, _mm256_div_ps) OPT(vminps, _mm256_min_ps) OPT(vmaxps, _mm256_max_ps)
        u8 mv[32]; memset(mv, 0xcc, 32); t_vmovaps(a, mv); CHECK(!memcmp(mv, a, 32), "vmovaps load form");
        u32 h[4] = {0xcc, 0xcc, 0xcc, 0xcc};
        __m128 lo = _mm256_extractf128_ps(x, 0), hi = _mm256_extractf128_ps(x, 1);
        t_vext0(a, h); CHECK(!memcmp(h, &lo, 16), "vextractf128 0");
        t_vext1(a, h); CHECK(!memcmp(h, &hi, 16), "vextractf128 1");
        u8 dst[32]; memset(dst, 0x11, 32); t_vstore256(dst, a); CHECK(!memcmp(dst, a, 32), "vmovaps store ymm");
        memset(dst, 0x11, 32); t_vstore128(dst, a); CHECK(!memcmp(dst, a, 16) && dst[16] == 0x11 && dst[31] == 0x11, "vmovaps store xmm (後続 16B を壊さない)");
    }
    printf("[helper_diff] checks=%ld mismatches=%ld\n", cnt, fails);
    if (cnt == 0) { printf("[helper_diff] FAIL: 検査 0 件\n"); return 1; }
    return fails ? 1 : 0;
}
