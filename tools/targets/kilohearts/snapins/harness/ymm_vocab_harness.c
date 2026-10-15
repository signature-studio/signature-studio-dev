/* ymm_vocab_harness.c — VEX.256 語彙 (vaddps / vsubps / vmulps / vmovaps) の native 突合 (ymm_vocab_check.py がリンクする)。
 * drv_<mnemonic>(a, b, r): gen_simd.py の i256 経路が出す IR 定義を呼ぶ driver (a/b/r = 32B の入出力)。
 * oracle = ホスト AVX2 命令 (_mm256_*_ps)。判定は 32B 全 bit (NaN payload を含む)。
 *   vmovaps (1 引数 = 移動) の oracle は値の恒等 (x86 の reg→reg 移動はビットを変えない)。
 *   usage: ymm_vocab_harness N SEED   → 語彙ごとに "<op> calls=N lanes=8N mismatch=M"。どれか M>0 なら exit 1。 */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void drv_vaddps(const void *a, const void *b, void *r);
void drv_vsubps(const void *a, const void *b, void *r);
void drv_vmulps(const void *a, const void *b, void *r);
void drv_vmovaps(const void *a, const void *b, void *r);

static uint64_t st;
static uint32_t rnd(void) { st ^= st << 13; st ^= st >> 7; st ^= st << 17; return (uint32_t)st; }

static const uint32_t SPECIAL[] = {0x00000000u, 0x80000000u, 0x3f800000u, 0xbf800000u, 0x7f800000u, 0xff800000u,
                                   0x7fc00000u, 0x7f7fffffu, 0x00800000u, 0x00000001u, 0x007fffffu, 0x40490fdbu, 0x3f000000u};

static uint32_t lane(void) {
    if (rnd() % 4 == 0) return SPECIAL[rnd() % (sizeof SPECIAL / sizeof SPECIAL[0])];
    return rnd();
}

static __m256 ref_add(__m256 a, __m256 b) { return _mm256_add_ps(a, b); }
static __m256 ref_sub(__m256 a, __m256 b) { return _mm256_sub_ps(a, b); }
static __m256 ref_mul(__m256 a, __m256 b) { return _mm256_mul_ps(a, b); }
static __m256 ref_mov(__m256 a, __m256 b) { (void)b; return a; }

int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 10000;
    st = argc > 2 ? strtoull(argv[2], NULL, 10) : 1;
    if (!st) st = 1;
    static const char *names[4] = {"vaddps", "vsubps", "vmulps", "vmovaps"};
    void (*drv[4])(const void *, const void *, void *) = {drv_vaddps, drv_vsubps, drv_vmulps, drv_vmovaps};
    __m256 (*ref[4])(__m256, __m256) = {ref_add, ref_sub, ref_mul, ref_mov};
    long total = 0;
    for (int k = 0; k < 4; k++) {
        long mis = 0;
        for (long i = 0; i < n; i++) {
            uint32_t a[8], b[8], r[8], o[8];
            for (int j = 0; j < 8; j++) { a[j] = lane(); b[j] = lane(); }
            drv[k](a, b, r);
            __m256 x = _mm256_loadu_ps((const float *)a), y = _mm256_loadu_ps((const float *)b);
            _mm256_storeu_ps((float *)o, ref[k](x, y));
            if (memcmp(r, o, sizeof r)) {
                if (mis < 3)
                    printf("  MISMATCH %s i=%ld a0=%08x b0=%08x got0=%08x want0=%08x\n", names[k], i, a[0], b[0], r[0], o[0]);
                mis++;
            }
        }
        printf("%s calls=%ld lanes=%ld mismatch=%ld\n", names[k], n, n * 8, mis);
        total += mis;
    }
    return total ? 1 : 0;
}
