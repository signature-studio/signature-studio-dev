/* text_golden.c — GUI-9 (#186): shim の GDI テキスト (FreeType エンジン) シーンを描き PPM + metrics 表 (TSV) に書く。
 * 期待値は独立オラクル golden/ft_oracle.c (shim 非依存の native FreeType 直叩き) が作る。
 * usage: text_golden <fontdir> <out.ppm> <out.tsv>
 * 環境変数 (ネガティブコントロール): TEXT_FAULT=1 = シーン 1 のフォント高さを 1 ずらす / TEXT_NOENGINE=1 = engine 未登録 (8x8 フォールバック) */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gui_api.h"
#include "gui_internal.h"
#include "gui_headless.h"
#include "gui_ft.h"
#define PTR(x) ((int64_t)(uintptr_t)(x))
#define W 320
#define H 120
static uint8_t *slurp(const char *dir, const char *f, size_t *n) {
  char p[512]; snprintf(p, sizeof p, "%s/%s", dir, f); FILE *fp = fopen(p, "rb"); if (!fp) { fprintf(stderr, "cannot open %s\n", p); exit(2); }
  fseek(fp, 0, SEEK_END); *n = (size_t)ftell(fp); fseek(fp, 0, SEEK_SET); uint8_t *b = malloc(*n); if (fread(b, 1, *n, fp) != *n) exit(2); fclose(fp); return b;
}
#include "text_scene.inc"
static void emit_line(void *u, const char *l) { fprintf((FILE *)u, "%s\n", l); }
static int g_enum_n; static char g_enum_names[8][32];
static int64_t enum_cb(int64_t elf, int64_t ntm, int64_t type, int64_t lp) {
  (void)ntm; (void)lp; const uint16_t *nm = (const uint16_t *)((const uint8_t *)P_(elf) + 28);
  if (g_enum_n < 8) { for (int i = 0; i < 31; i++) g_enum_names[g_enum_n][i] = (char)nm[i]; g_enum_n++; }
  return type == 4 ? 1 : 0;
}
int main(int argc, char **argv) {
  if (argc < 4) return 2;
  int fault = getenv("TEXT_FAULT") && atoi(getenv("TEXT_FAULT")), noeng = getenv("TEXT_NOENGINE") && atoi(getenv("TEXT_NOENGINE"));
  size_t n1, n2; uint8_t *os = slurp(argv[1], "OpenSans-Regular.ttf", &n1), *ba = slurp(argv[1], "Barlow-Regular.ttf", &n2);
  gui_ft_register_face("Open Sans", os, n1); gui_ft_register_face("Barlow", ba, n2);
  gui_ft_alias("Segoe UI", "Open Sans"); gui_ft_alias("Tahoma", "Open Sans");
  if (!noeng) gui_set_text_engine(gui_ft_engine());
  gui_hl_start(640, 480, 1);
  uint8_t *dummy; (void)dummy;
  WBMIH bi; memset(&bi, 0, sizeof bi); bi.biSize = 40; bi.biWidth = W; bi.biHeight = -H; bi.biPlanes = 1; bi.biBitCount = 32; uint64_t pv = 0;
  int64_t hb = CreateDIBSection(0, PTR(&bi), 0, PTR(&pv), 0, 0), dc = CreateCompatibleDC(0); SelectObject(dc, hb);
  text_scene_draw(dc, fault);
  FILE *o = fopen(argv[2], "wb"); fprintf(o, "P6\n%d %d\n255\n", W, H);
  for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) { uint32_t p = ((uint32_t *)(uintptr_t)pv)[y * W + x]; fputc((p >> 16) & 255, o); fputc((p >> 8) & 255, o); fputc(p & 255, o); }
  fclose(o);
  /* metrics 表 */
  FILE *t = fopen(argv[3], "w"); text_scene_metrics(dc, emit_line, t); fclose(t);
  /* EnumFontFamiliesEx: 全 face 列挙 + 名指定 */
  WRECT dummy_r; (void)dummy_r; uint8_t lf[92]; memset(lf, 0, sizeof lf);
  EnumFontFamiliesExW(dc, PTR(lf), PTR(enum_cb), 0, 0);
  int all_n = g_enum_n; g_enum_n = 0; uint16_t nm[32] = { 0 }; w16(nm, "barlow"); memcpy(lf + 28, nm, sizeof nm);
  EnumFontFamiliesExW(dc, PTR(lf), PTR(enum_cb), 0, 0);
  printf("enum all=%d named=%d first=%s\n", noeng ? 0 : all_n, g_enum_n, g_enum_n ? g_enum_names[0] : "-");
  return 0;
}
