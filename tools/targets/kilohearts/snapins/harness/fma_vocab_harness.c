/* fma_vocab_harness.c — FMA3 scalar 語彙 (census の xmm FMA 7 mnemonic) の native 突合 (fma_vocab_check.py がリンクする)。
 * __asm_<mn>(a0, a1, a2): gen_simd.py が出す C 実装を直接呼ぶ (a0 = dest, a1 = src2, a2 = src3; 128bit)。
 * oracle = ホスト FMA3 命令 (_mm_fmadd_ss 等)。上位 lane は dest から取る (_mm_move_ss / _mm_move_sd)。
 * vfmadd132sd の oracle だけは同じ命令形の inline asm を使う (_mm_fmadd_sd の引数順では clang -O1 が vfmadd213sd に畳み、
 *   NaN 被演算子の選択が変わる)。
 *   判定: 128bit 全 bit 一致 (NaN payload を含む・緩和なし)。
 *   usage: fma_vocab_harness N SEED → 語彙ごとに "<op> calls=N bits=128 mismatch=M"。M>0 なら exit 1。 */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned __int128 u128;
typedef union { u128 q; uint32_t w[4]; uint64_t d[2]; } V;
typedef u128 (*gen_fn)(u128, u128, u128);
typedef __m128i (*ref_fn)(__m128i, __m128i, __m128i);

u128 __asm_vfmadd213sd(u128, u128, u128);
u128 __asm_vfmadd213ss(u128, u128, u128);
u128 __asm_vfmsub213ss(u128, u128, u128);
u128 __asm_vfmadd231sd(u128, u128, u128);
u128 __asm_vfmadd231ss(u128, u128, u128);
u128 __asm_vfnmadd231sd(u128, u128, u128);
u128 __asm_vfmadd132sd(u128, u128, u128);

static uint64_t st;
static uint64_t rnd64(void) { st ^= st << 13; st ^= st >> 7; st ^= st << 17; return st; }
static uint32_t rnd(void) { return (uint32_t)rnd64(); }

static const uint32_t SP32[] = {0x00000000u, 0x80000000u, 0x3f800000u, 0xbf800000u, 0x7f800000u, 0xff800000u,
                                0x7fc00000u, 0xffc00000u, 0x7f800001u, 0x7f7fffffu, 0x00800000u, 0x00000001u,
                                0x007fffffu, 0x40490fdbu, 0x3f000000u};
static const uint64_t SP64[] = {0x0000000000000000ull, 0x8000000000000000ull, 0x3ff0000000000000ull, 0xbff0000000000000ull,
                                0x7ff0000000000000ull, 0xfff0000000000000ull, 0x7ff8000000000000ull, 0xfff8000000000000ull,
                                0x7ff0000000000001ull, 0x7fefffffffffffffull, 0x0010000000000000ull, 0x0000000000000001ull,
                                0x000fffffffffffffull, 0x400921fb54442d18ull, 0x3fe0000000000000ull};

/* 1/4 特殊値, 1/4 任意 bit (NaN/Inf/非正規を含む), 1/2 指数を 1 付近に寄せた通常域 (単精度・倍精度の丸め差が出やすい) */
static uint32_t val32(void) {
    switch (rnd() % 4) {
    case 0: return SP32[rnd() % (sizeof SP32 / sizeof SP32[0])];
    case 1: return rnd();
    default: return (rnd() & 0x80000000u) | ((127u + rnd() % 41u - 20u) << 23) | (rnd() & 0x7fffffu);
    }
}
static uint64_t val64(void) {
    switch (rnd() % 4) {
    case 0: return SP64[rnd() % (sizeof SP64 / sizeof SP64[0])];
    case 1: return rnd64();
    default: return ((uint64_t)(rnd() & 1) << 63) | ((1023ull + rnd() % 201ull - 100ull) << 52) | (rnd64() & 0xfffffffffffffull);
    }
}

/* ref: d = dest (上位 lane の源), s2 = op2, s3 = op3。Intel 順の意味を FMA3 命令で直接書く */
static __m128i ref_213ss(__m128i d, __m128i s2, __m128i s3) {
    __m128 D = _mm_castsi128_ps(d);
    return _mm_castps_si128(_mm_move_ss(D, _mm_fmadd_ss(_mm_castsi128_ps(s2), D, _mm_castsi128_ps(s3))));
}
static __m128i ref_213sd(__m128i d, __m128i s2, __m128i s3) {
    __m128d D = _mm_castsi128_pd(d);
    return _mm_castpd_si128(_mm_move_sd(D, _mm_fmadd_sd(_mm_castsi128_pd(s2), D, _mm_castsi128_pd(s3))));
}
static __m128i ref_sub213ss(__m128i d, __m128i s2, __m128i s3) {
    __m128 D = _mm_castsi128_ps(d);
    return _mm_castps_si128(_mm_move_ss(D, _mm_fmsub_ss(_mm_castsi128_ps(s2), D, _mm_castsi128_ps(s3))));
}
static __m128i ref_231sd(__m128i d, __m128i s2, __m128i s3) {
    __m128d D = _mm_castsi128_pd(d);
    return _mm_castpd_si128(_mm_move_sd(D, _mm_fmadd_sd(_mm_castsi128_pd(s2), _mm_castsi128_pd(s3), D)));
}
static __m128i ref_231ss(__m128i d, __m128i s2, __m128i s3) {
    __m128 D = _mm_castsi128_ps(d);
    return _mm_castps_si128(_mm_move_ss(D, _mm_fmadd_ss(_mm_castsi128_ps(s2), _mm_castsi128_ps(s3), D)));
}
static __m128i ref_nmadd231sd(__m128i d, __m128i s2, __m128i s3) {
    __m128d D = _mm_castsi128_pd(d);
    return _mm_castpd_si128(_mm_move_sd(D, _mm_fnmadd_sd(_mm_castsi128_pd(s2), _mm_castsi128_pd(s3), D)));
}
static __m128i ref_132sd(__m128i d, __m128i s2, __m128i s3) {
    __asm__("vfmadd132sd %2, %1, %0" : "+x"(d) : "x"(s2), "x"(s3));
    return d;
}

int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 20000;
    st = argc > 2 ? strtoull(argv[2], NULL, 10) : 1;
    if (!st) st = 1;
    static const char *names[7] = {"vfmadd213sd", "vfmadd213ss", "vfmsub213ss", "vfmadd231sd", "vfmadd231ss", "vfnmadd231sd", "vfmadd132sd"};
    static const int sd[7] = {1, 0, 0, 1, 0, 1, 1};
    gen_fn gen[7] = {__asm_vfmadd213sd, __asm_vfmadd213ss, __asm_vfmsub213ss, __asm_vfmadd231sd, __asm_vfmadd231ss, __asm_vfnmadd231sd, __asm_vfmadd132sd};
    ref_fn ref[7] = {ref_213sd, ref_213ss, ref_sub213ss, ref_231sd, ref_231ss, ref_nmadd231sd, ref_132sd};
    long total = 0;
    for (int k = 0; k < 7; k++) {
        long mis = 0;
        for (long i = 0; i < n; i++) {
            V d, s2, s3, got, want;
            for (int j = 0; j < 4; j++) { d.w[j] = val32(); s2.w[j] = val32(); s3.w[j] = val32(); }
            if (sd[k]) {
                for (int j = 0; j < 2; j++) { d.d[j] = val64(); s2.d[j] = val64(); s3.d[j] = val64(); }
            }
            got.q = gen[k](d.q, s2.q, s3.q);
            _mm_storeu_si128((__m128i *)&want, ref[k](_mm_loadu_si128((const __m128i *)&d),
                                                      _mm_loadu_si128((const __m128i *)&s2),
                                                      _mm_loadu_si128((const __m128i *)&s3)));
            if (memcmp(&got, &want, sizeof got)) {
                if (mis < 3)
                    printf("  MISMATCH %s i=%ld d0=%016llx s2=%016llx s3=%016llx got0=%016llx want0=%016llx\n", names[k], i,
                           (unsigned long long)(sd[k] ? d.d[0] : d.w[0]), (unsigned long long)(sd[k] ? s2.d[0] : s2.w[0]),
                           (unsigned long long)(sd[k] ? s3.d[0] : s3.w[0]), (unsigned long long)(sd[k] ? got.d[0] : got.w[0]),
                           (unsigned long long)(sd[k] ? want.d[0] : want.w[0]));
                mis++;
            }
        }
        printf("%s calls=%ld bits=128 mismatch=%ld\n", names[k], n, mis);
        total += mis;
    }
    return total ? 1 : 0;
}
