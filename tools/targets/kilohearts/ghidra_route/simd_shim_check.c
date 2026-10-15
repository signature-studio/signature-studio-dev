/* ghidra_shim.h の SIMD 疑似関数 (実装した規則) を、ホストの x86 intrinsics (実機命令) と乱数入力で突合する (#3095)。
 * 検査: gcc -O1 -mavx2 -I ghidra_route -I <emscripten.h スタブ> simd_shim_check.c -lm && ./a.out
 * ネガティブコントロール: -DKH_NEG=1 で vpsubq の参照を逆順 (b - a) にする。FAIL (exit 1) になることを確認する。 */
#include <immintrin.h>
#include <stdio.h>
#include "ghidra_shim.h"

static uint64_t rs = 0x9e3779b97f4a7c15ull;
static uint64_t rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return rs; }
static V128 rv(void) { V128 v; for (int i = 0; i < 2; i++) { uint64_t x = rnd(); memcpy(v.b + 8 * i, &x, 8); } return v; }
/* _mm_shuffle_ps は即値が定数必須のため、代表 16 通りの即値で参照を引く */
static __m128 shuf_ref(__m128 a, __m128 b, int imm) {
    switch (imm) {
        case 0x00: return _mm_shuffle_ps(a, b, 0x00);
        case 0x01: return _mm_shuffle_ps(a, b, 0x01);
        case 0x08: return _mm_shuffle_ps(a, b, 0x08);
        case 0x1b: return _mm_shuffle_ps(a, b, 0x1b);
        case 0x39: return _mm_shuffle_ps(a, b, 0x39);
        case 0x44: return _mm_shuffle_ps(a, b, 0x44);
        case 0x4e: return _mm_shuffle_ps(a, b, 0x4e);
        case 0x72: return _mm_shuffle_ps(a, b, 0x72);
        case 0x87: return _mm_shuffle_ps(a, b, 0x87);
        case 0x93: return _mm_shuffle_ps(a, b, 0x93);
        case 0xb1: return _mm_shuffle_ps(a, b, 0xb1);
        case 0xc6: return _mm_shuffle_ps(a, b, 0xc6);
        case 0xd8: return _mm_shuffle_ps(a, b, 0xd8);
        case 0xe4: return _mm_shuffle_ps(a, b, 0xe4);
        case 0xff: return _mm_shuffle_ps(a, b, 0xff);
        case 0x5a: return _mm_shuffle_ps(a, b, 0x5a);
    default: return _mm_setzero_ps();
    }
}

static int fails = 0;
static void check(const char *name, V128 got, __m128i ref, long i) {
    if (memcmp(&got, &ref, 16) != 0) { if (fails < 5) printf("FAIL %s trial %ld\n", name, i); fails++; }
}
static void checkd(const char *name, V128 got, __m128d ref, long i) {
    if (memcmp(&got, &ref, 16) != 0) { if (fails < 5) printf("FAIL %s trial %ld\n", name, i); fails++; }
}
static void checkps(const char *name, V128 got, __m128 ref, long i) {
    if (memcmp(&got, &ref, 16) != 0) { if (fails < 5) printf("FAIL %s trial %ld\n", name, i); fails++; }
}

int main(void) {
    const long N = 200000;
    long cnt[16] = {0};
    for (long i = 0; i < N; i++) {
        V128 a = rv(), b = rv();
        __m128i A = _mm_loadu_si128((const __m128i *)a.b), B = _mm_loadu_si128((const __m128i *)b.b);
        __m128 Af = _mm_castsi128_ps(A), Bf = _mm_castsi128_ps(B);
        __m128d Ad = _mm_castsi128_pd(A);
        /* minps: dst = a, src = b。NaN は src */
        checkps("minps", minps(a, b), _mm_min_ps(Af, Bf), i); cnt[0]++;
#ifdef KH_NEG
        check("vpsubq", vpsubq_avx(a, b), _mm_sub_epi64(B, A), i); cnt[1]++;
#else
        check("vpsubq", vpsubq_avx(a, b), _mm_sub_epi64(A, B), i); cnt[1]++;
#endif
        check("vpsubd", vpsubd_avx(a, b), _mm_sub_epi32(A, B), i); cnt[2]++;
        check("vpand", vpand_avx(a, b), _mm_and_si128(A, B), i); cnt[3]++;
        check("vpor", vpor_avx(a, b), _mm_or_si128(A, B), i); cnt[4]++;
        int n = (int)(rnd() % 80);
        check("vpsrlq", vpsrlq_avx(a, n), _mm_srl_epi64(A, _mm_cvtsi32_si128(n)), i); cnt[5]++;
        /* 任意ビットの double (NaN・Inf・範囲外を含む) */
        checkd("vcvtdq2pd", vcvtdq2pd_avx(a), _mm_cvtepi32_pd(A), i); cnt[6]++;
        __m128d Dv = _mm_castsi128_pd(B);
        V128 dv; _mm_storeu_pd((double *)dv.b, Dv);
        check("vcvtpd2dq", vcvtpd2dq_avx(dv), _mm_cvtpd_epi32(Dv), i); cnt[7]++;
        static const int IMM[16] = {0x00,0x01,0x08,0x1b,0x39,0x44,0x4e,0x72,0x87,0x93,0xb1,0xc6,0xd8,0xe4,0xff,0x5a};
        int imm = IMM[rnd() & 15];
        checkps("vshufps", vshufps_avx(a, b, imm), shuf_ref(Af, Bf, imm), i); cnt[8]++;
        check("vpmovsxdq", vpmovsxdq_avx(a), _mm_cvtepi32_epi64(A), i); cnt[9]++;
        /* SUB168 (8 byte 切り出し): 0 = 下位 64bit, 8 = 上位 64bit */
        ulonglong lo = SUB168(a, 0), hi = SUB168(a, 8);
        if (lo != (ulonglong)_mm_cvtsi128_si64(A) || hi != (ulonglong)_mm_extract_epi64(A, 1)) { if (fails < 5) printf("FAIL SUB168 trial %ld\n", i); fails++; }
        cnt[10]++;
        /* SUB84 (4 byte 切り出し): double の下位 4 byte */
        double d = _mm_cvtsd_f64(Dv);
        uint s84 = SUB84(d, 0), s84b = (uint)_mm_cvtsi128_si32(_mm_castpd_si128(Dv));
        if (s84 != s84b) { if (fails < 5) printf("FAIL SUB84 trial %ld\n", i); fails++; }
        cnt[11]++;
        /* ZEXT816: 下位 64bit に値、上位 0 */
        check("ZEXT816", ZEXT816(lo), _mm_cvtsi64_si128((long long)lo), i); cnt[12]++;
    }
    printf("trials per function (N=%ld): minps %ld, vpsubq %ld, vpsubd %ld, vpand %ld, vpor %ld, vpsrlq %ld, vcvtdq2pd %ld, vcvtpd2dq %ld, vshufps %ld, vpmovsxdq %ld, SUB168 %ld, SUB84 %ld, ZEXT816 %ld\n",
           N, cnt[0], cnt[1], cnt[2], cnt[3], cnt[4], cnt[5], cnt[6], cnt[7], cnt[8], cnt[9], cnt[10], cnt[11], cnt[12]);
    printf("mismatches: %d\n", fails);
    return fails ? 1 : 0;
}
