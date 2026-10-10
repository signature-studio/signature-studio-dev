/* fma_fuzz.c — CAB-135: FMA の bit-exact 性検証 (native vfmadd213sd vs wasm libc fma())。
 * 同一 PRNG 列 (xorshift64) で (a,b,c) を生成し、各ビルドの fma 結果を 1 行 16 進で stdout に出す。
 * native ビルドは加えて hw_fma (vfmadd intrinsic) と fma() の内部照合も行う (参照の健全性)。
 * wasm 側は libc fma() に NaN quiet-bit 補正 (ott_fma_d と同一 — musl fma は quiet bit を
 * 立てない事が 3M case 実測で判明, payload は一致) を施したもの = lift 実行時に使う形と一致。
 * avx_e2e.sh が native/wasm の出力を diff する。
 *   native: gcc -O2 -mavx2 -mfma (hw 内部照合付き)
 *   wasm  : emcc -O1 ...
 * usage: fma_fuzz <ncases> <seed> */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#if defined(__x86_64__) && !defined(EMSCRIPTEN)
#include <immintrin.h>
#define OTT_HW 1
#endif

#ifdef OTT_HW
/* ハードウェア FMA (DLL の vfmadd213sd と同一意味 = IEEE 正しく丸められる fma) */
static double hw_fma(double a, double b, double c) {
    return _mm_cvtsd_f64(_mm_fmadd_sd(_mm_set_sd(a), _mm_set_sd(b), _mm_set_sd(c)));
}
#define REF_FMA(a, b, c) fma(a, b, c)
#else
/* wasm (musl): quiet bit 補正付き fma = lift 実行時の ott_fma_d と同一 */
static double ref_fma_q(double a, double b, double c) {
    double r = fma(a, b, c);
    if (r != r) { uint64_t u; memcpy(&u, &r, 8); u |= 1ULL << 51; memcpy(&r, &u, 8); }
    return r;
}
#define REF_FMA(a, b, c) ref_fma_q(a, b, c)
#endif

static uint64_t bits_of(double v) { uint64_t u; memcpy(&u, &v, 8); return u; }
static double dbl_of(uint64_t u) { double v; memcpy(&v, &u, 8); return v; }

/* PRNG (xorshift64) — 両ビルドで同一列を出すため libc rand を使わない */
static uint64_t s;
static uint64_t nx(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s; }

int main(int argc, char** argv) {
    long n = (argc > 1) ? atol(argv[1]) : 2000000;
    s = (argc > 2) ? strtoull(argv[2], 0, 10) : 12345;
    long bad = 0;
    for (long i = 0; i < n; i++) {
        uint64_t ua, ub, uc;
        if (i % 4 == 3) {
            /* 丸め 1 回の差が出る領域: a*b と c が同オーダー */
            ua = (nx() & 0x000fffffffffffffULL) | 0x3ff0000000000000ULL;   /* [1,2) */
            ub = (nx() & 0x000fffffffffffffULL) | 0x3ff0000000000000ULL;
            uc = bits_of(dbl_of(ua) * dbl_of(ub)) + (nx() % 7) - 3;        /* 積の近傍 */
        } else if (i % 4 == 1) {
            /* 非正規/オーバーフロー境界 */
            ua = (nx() & 0x000fffffffffffffULL) | (nx() % 2 ? 0x0010000000000000ULL : 0x7fe0000000000000ULL);
            ub = (nx() & 0x000fffffffffffffULL) | (nx() % 2 ? 0x0010000000000000ULL : 0x3e70000000000000ULL);
            uc = nx();
        } else {
            ua = nx(); ub = nx(); uc = nx();
        }
        double a = dbl_of(ua), b = dbl_of(ub), c = dbl_of(uc);
        double r = REF_FMA(a, b, c);
#ifdef OTT_HW
        double hw = hw_fma(a, b, c);
        if (bits_of(hw) != bits_of(r)) {
            if (bad < 8)
                fprintf(stderr, "fma mismatch (hw vs fma()): a=%016llx b=%016llx c=%016llx hw=%016llx fma=%016llx\n",
                        (unsigned long long)ua, (unsigned long long)ub, (unsigned long long)uc,
                        (unsigned long long)bits_of(hw), (unsigned long long)bits_of(r));
            bad++;
        }
#endif
        printf("%016llx\n", (unsigned long long)bits_of(r));
    }
    /* 特異点 (非正規・±0・オーバーフロー境界) */
    { double sp[][3] = {{0.0, 0.0, 0.0}, {0.0, 0.0, -0.0}, {5e-324, 0.5, 0.0}, {5e-324, 0.5, -5e-324},
                        {1.7976931348623157e308, 2.0, -1.7976931348623157e308}, {1e-308, 1e-10, 0.0},
                        {0.5, 0.0, 1.0}, {0.0, 1.0, 0.5}, {1.0, 0.0, 0.5},
                        {-1.5, 2.0, 3.0}, {1.5, -2.0, 3.0}, {1.5, 2.0, -3.0}};
      for (unsigned k = 0; k < sizeof(sp) / sizeof(sp[0]); k++) {
          double r = REF_FMA(sp[k][0], sp[k][1], sp[k][2]);
#ifdef OTT_HW
          double hw = hw_fma(sp[k][0], sp[k][1], sp[k][2]);
          if (bits_of(hw) != bits_of(r)) { fprintf(stderr, "fma special mismatch %d: hw=%016llx fma=%016llx\n", k,
              (unsigned long long)bits_of(hw), (unsigned long long)bits_of(r)); bad++; }
#endif
          printf("%016llx\n", (unsigned long long)bits_of(r));
      } }
    fflush(stdout);
#ifdef OTT_HW
    if (bad) { fprintf(stderr, "[fma_fuzz] native internal hw-vs-fma mismatches: %ld\n", bad); return 1; }
#endif
    return 0;
}
