/* vmovaps_store_harness.c — VEX.256 vmovaps store 形 (`vmovaps ymmword ptr [m], ymm`) の native 突合 (vmovaps_store_check.py がリンクする)。
 * fn_store(src, dst) は kh_passes[storelow] が復元した IR (32B store) を呼ぶ。oracle = ホスト AVX2 の 32B ロード→ストア。
 * 判定は 32B 全 bit (NaN payload を含む)。dst の初期値は src と必ず異なるようにする (store が消えたら FAIL)。
 *   usage: vmovaps_store_harness N SEED   → "vmovaps_store calls=N bytes=32N mismatch=M"。M>0 なら exit 1。 */
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void fn_store(const void *src, void *dst);

static uint64_t st;
static uint8_t rnd(void) { st ^= st << 13; st ^= st >> 7; st ^= st << 17; return (uint8_t)st; }

int main(int argc, char **argv) {
    long n = argc > 1 ? atol(argv[1]) : 10000;
    st = argc > 2 ? strtoull(argv[2], NULL, 10) : 1;
    if (!st) st = 1;
    long mis = 0;
    for (long i = 0; i < n; i++) {
        uint8_t src[32] __attribute__((aligned(32))), dst[32], old[32], want[32];
        for (int j = 0; j < 32; j++) src[j] = rnd();
        for (int j = 0; j < 32; j++) old[j] = (uint8_t)(src[j] ^ (rnd() | 1));
        memcpy(dst, old, 32);
        fn_store(src, dst);
        _mm256_storeu_si256((__m256i *)want, _mm256_loadu_si256((const __m256i *)src));
        if (memcmp(dst, want, 32)) {
            if (mis < 3) printf("  MISMATCH i=%ld got=%02x%02x.. want=%02x%02x..\n", i, dst[0], dst[1], want[0], want[1]);
            mis++;
        }
    }
    printf("vmovaps_store calls=%ld bytes=%ld mismatch=%ld\n", n, n * 32, mis);
    return mis ? 1 : 0;
}
