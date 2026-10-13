/* simd_bench.c — 1080p 行カーネルの ms/frame (emcc + node)。-msimd128 の有無で gs_* が simd/scalar に切り替わる。
 * 使い方: simd_e2e.sh が 2 ビルド (scalar / simd) を作って各 5 回実行し min-max を表示する。 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "gui_simd.h"
enum { W = 1920, H = 1080 };
static double now_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e3 + t.tv_nsec / 1e6; }
static uint32_t rnd(void) { static uint64_t s = 88172645463325252ull; s ^= s << 13; s ^= s >> 7; s ^= s << 17; return (uint32_t)(s >> 11); }
static volatile uint32_t sink;
int main(void) {
  uint32_t *S = malloc((size_t)W * H * 4), *D = malloc((size_t)W * H * 4), *R = malloc((size_t)W * 4);
  for (size_t i = 0; i < (size_t)W * H; i++) { S[i] = rnd(); D[i] = rnd(); }
  const int IT = 20; double t;
#define BENCH(name, STMT) do { t = now_ms(); for (int it = 0; it < IT; it++) for (int y = 0; y < H; y++) { uint32_t *d = D + (size_t)y * W; const uint32_t *s = S + (size_t)y * W; STMT; } \
    printf("%-34s %8.3f ms/frame\n", name, (now_ms() - t) / IT); sink += D[12345]; } while (0)
  printf("mode=%s\n", GUI_HAVE_SIMD ? "simd128" : "scalar");
  BENCH("ROP SRCINVERT 1920x1080", gs_rop_row(GS_SRCINVERT, d, s, W, 0));
  BENCH("ROP PATPAINT 1920x1080", gs_rop_row(GS_PATPAINT, d, s, W, 0x00FF8040u));
  BENCH("AlphaBlend const(sca=128)", gs_alpha_row(d, s, W, 128, 0));
  BENCH("AlphaBlend per-pixel alpha", gs_alpha_row(d, s, W, 200, 1));
  BENCH("StretchDIBits 1:1 (opaque copy)", gs_opaque_copy(d, s, W));
  BENCH("StretchBlt 2x row (dup2 960->1920)", gs_dup2(d, s, W));
  (void)R; return 0;
}
