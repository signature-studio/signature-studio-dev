/* simd_test.c — gui_simd.h の SIMD 行カーネルと scalar 参照の画素完全一致検査。
 * 要 -msimd128 (emcc + node)。SIMD 無効ビルド (GUI_HAVE_SIMD=0) では gs_* が scalar になり検査が成立しないため exit 2。
 * 検査: 全 ROP 15 種 x 長さ 0..70 x アライメント差 0..3 x 乱数 src/dst/pat、AlphaBlend const/src-alpha x sca 全 256 値 (長さ 0..70)、
 *       不透明化コピー、2x 拡大。さらに 1080p 1 行 (1920 画素) の全 ROP / alpha を乱数 3 回。 */
#include <stdio.h>
#include <stdlib.h>
#include "gui_simd.h"
#if !GUI_HAVE_SIMD
int main(void) { puts("simd_test: built without wasm SIMD128 (need -msimd128)"); return 2; }
#else
static uint64_t g_rng = 0x9E3779B97F4A7C15ull;
static uint32_t rnd(void) { g_rng ^= g_rng << 13; g_rng ^= g_rng >> 7; g_rng ^= g_rng << 17; return (uint32_t)(g_rng >> 16); }
static const uint32_t ROPS[] = { GS_SRCCOPY, GS_SRCPAINT, GS_SRCAND, GS_SRCINVERT, GS_SRCERASE, GS_NOTSRCCOPY, GS_NOTSRCERASE, GS_MERGECOPY,
  GS_MERGEPAINT, GS_PATCOPY, GS_PATINVERT, GS_PATPAINT, GS_DSTINVERT, GS_BLACKNESS, GS_WHITENESS };
#define NR (int)(sizeof ROPS / sizeof ROPS[0])
static int g_cases, g_bad;
static void fill(uint32_t *p, size_t n) { for (size_t i = 0; i < n; i++) p[i] = rnd() ^ (rnd() << 16); }
static void report(const char *k, size_t n, int aux, const uint32_t *a, const uint32_t *b, size_t m) {
  g_cases++;
  if (memcmp(a, b, m * 4) == 0) return;
  g_bad++;
  if (g_bad <= 10) { size_t i = 0; while (a[i] == b[i]) i++; printf("MISMATCH %s n=%zu aux=%d at %zu: scalar=%08x simd=%08x\n", k, n, aux, i, a[i], b[i]); }
}
int main(void) {
  enum { MAXN = 2048 };
  static uint32_t S[MAXN + 8], D0[MAXN + 8], DA[MAXN + 8], DB[MAXN + 8];
  for (int r = 0; r < NR; r++) for (size_t n = 0; n <= 70; n++) for (int al = 0; al < 4; al++) {
    fill(S, MAXN + 8); fill(D0, MAXN + 8); uint32_t pat = rnd();
    memcpy(DA, D0, sizeof DA); memcpy(DB, D0, sizeof DB);
    gs_rop_row_scalar(ROPS[r], DA + al, S + al, n, pat); gs_rop_row_simd(ROPS[r], DB + al, S + al, n, pat);
    report("rop", n, r, DA, DB, MAXN + 8);
  }
  for (int af = 0; af < 2; af++) for (uint32_t sca = 0; sca < 256; sca++) for (size_t n = 0; n <= 9; n++) {
    fill(S, 16); fill(D0, 16); memcpy(DA, D0, 64); memcpy(DB, D0, 64);
    gs_alpha_row_scalar(DA + 1, S + 1, n, sca, af); gs_alpha_row_simd(DB + 1, S + 1, n, sca, af);
    report("alpha", n, (int)(af * 256 + sca), DA, DB, 16);
  }
  for (int af = 0; af < 2; af++) for (size_t n = 0; n <= 70; n++) for (int it = 0; it < 40; it++) {
    uint32_t sca = it < 4 ? (it == 0 ? 0 : it == 1 ? 255 : it == 2 ? 128 : 1) : rnd() & 255;
    fill(S, 80); fill(D0, 80); memcpy(DA, D0, 320); memcpy(DB, D0, 320);
    gs_alpha_row_scalar(DA, S, n, sca, af); gs_alpha_row_simd(DB, S, n, sca, af);
    report("alpha-rand", n, af, DA, DB, 80);
  }
  for (size_t n = 0; n <= 70; n++) for (int al = 0; al < 4; al++) {
    fill(S, 100); memset(DA, 0x55, 400); memset(DB, 0x55, 400);
    gs_opaque_copy_scalar(DA + al, S + al, n); gs_opaque_copy_simd(DB + al, S + al, n); report("opaque_copy", n, al, DA, DB, 100);
    gs_dup2_scalar(DA + al, S + al, n); gs_dup2_simd(DB + al, S + al, n); report("dup2", n, al, DA, DB, 100);   /* 2x: n_out 画素 (src は偶数開始) */
  }
  for (int it = 0; it < 3; it++) {
    for (int r = 0; r < NR; r++) {
      fill(S, 1920); fill(D0, 1920); uint32_t pat = rnd(); memcpy(DA, D0, 7680); memcpy(DB, D0, 7680);
      gs_rop_row_scalar(ROPS[r], DA, S, 1920, pat); gs_rop_row_simd(ROPS[r], DB, S, 1920, pat); report("rop-1920", 1920, r, DA, DB, 1920);
    }
    for (int af = 0; af < 2; af++) {
      fill(S, 1920); fill(D0, 1920); memcpy(DA, D0, 7680); memcpy(DB, D0, 7680);
      gs_alpha_row_scalar(DA, S, 1920, rnd() & 255, af); memcpy(DB, D0, 7680);
      /* 同じ sca で比較するため再計算 */
      uint32_t sca = rnd() & 255; memcpy(DA, D0, 7680); memcpy(DB, D0, 7680);
      gs_alpha_row_scalar(DA, S, 1920, sca, af); gs_alpha_row_simd(DB, S, 1920, sca, af); report("alpha-1920", 1920, af, DA, DB, 1920);
    }
  }
  printf("simd_test: %d cases, %d mismatches -> %s\n", g_cases, g_bad, g_bad ? "FAIL" : "PASS");
  return g_bad ? 1 : 0;
}
#endif
