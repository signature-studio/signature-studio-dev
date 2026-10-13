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
#define CR(r, g, b) ((uint32_t)((r) | (g) << 8 | (b) << 16))
#define W 320
#define H 120
static uint8_t *slurp(const char *dir, const char *f, size_t *n) {
  char p[512]; snprintf(p, sizeof p, "%s/%s", dir, f); FILE *fp = fopen(p, "rb"); if (!fp) { fprintf(stderr, "cannot open %s\n", p); exit(2); }
  fseek(fp, 0, SEEK_END); *n = (size_t)ftell(fp); fseek(fp, 0, SEEK_SET); uint8_t *b = malloc(*n); if (fread(b, 1, *n, fp) != *n) exit(2); fclose(fp); return b;
}
static void w16(uint16_t *d, const char *s) { while ((*d++ = (uint8_t)*s++)); }
static int64_t mkfont(int h, const char *face) { uint16_t n[32] = { 0 }; w16(n, face); return CreateFontW(h, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, PTR(n)); }
static void wstr(uint16_t *d, const char *s) { w16(d, s); }
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
  WRECT all = { 0, 0, W, H }; FillRect(dc, PTR(&all), CreateSolidBrush(CR(32, 32, 48)));
  uint16_t s[64];
  SetBkMode(dc, 1 /* TRANSPARENT */);
  /* 1 */ SelectObject(dc, mkfont(fault ? -13 : -12, "Open Sans")); SetTextColor(dc, CR(255, 255, 255)); wstr(s, "Hello, World! gjpqy 0123"); TextOutW(dc, 4, 4, PTR(s), 24);
  /* 2 */ SelectObject(dc, mkfont(-14, "Barlow")); SetBkMode(dc, 2 /* OPAQUE */); SetBkColor(dc, CR(200, 40, 40)); SetTextColor(dc, CR(255, 255, 0)); wstr(s, "Barlow OPAQUE"); TextOutW(dc, 4, 24, PTR(s), 13); SetBkMode(dc, 1);
  /* 3 face 名 "Segoe UI" -> alias で Open Sans */
  SelectObject(dc, mkfont(-16, "Segoe UI")); SetTextColor(dc, CR(0, 255, 128)); wstr(s, "Centered"); WRECT r3 = { 170, 4, 310, 44 }; DrawTextW(dc, PTR(s), -1, PTR(&r3), DT_CENTER | DT_VCENTER | DT_SINGLELINE);
  /* 4 */ SelectObject(dc, mkfont(13, "Open Sans")); SetTextColor(dc, CR(255, 160, 0)); wstr(s, "Line one\nsecond line"); WRECT r4 = { 170, 50, 310, 100 }; DrawTextW(dc, PTR(s), -1, PTR(&r4), DT_LEFT);
  /* 5 */ SelectObject(dc, mkfont(-12, "Open Sans")); SetTextColor(dc, CR(255, 255, 255)); SetTextAlign(dc, 24 | 2); wstr(s, "baseline"); TextOutW(dc, 120, 70, PTR(s), 8); SetTextAlign(dc, 0);
  /* 6 TA_CENTER 相当は x 計算をオラクルと揃えるため TA_CENTER で描く */
  SelectObject(dc, mkfont(-20, "Barlow")); SetTextColor(dc, CR(180, 220, 255)); SetTextAlign(dc, 6); wstr(s, "TA_CENTER"); TextOutW(dc, 80, 80, PTR(s), 9); SetTextAlign(dc, 0);
  FILE *o = fopen(argv[2], "wb"); fprintf(o, "P6\n%d %d\n255\n", W, H);
  for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) { uint32_t p = ((uint32_t *)(uintptr_t)pv)[y * W + x]; fputc((p >> 16) & 255, o); fputc((p >> 8) & 255, o); fputc(p & 255, o); }
  fclose(o);
  /* metrics 表 */
  FILE *t = fopen(argv[3], "w"); const char *names[2] = { "Open Sans", "Barlow" }; int hs[] = { -8, -9, -10, -11, -12, -13, -14, -16, -18, -20, -24, -32, 12, 16, 20 };
  wstr(s, "The quick brown fox");
  for (int fi = 0; fi < 2; fi++) for (unsigned hi = 0; hi < sizeof hs / sizeof *hs; hi++) {
    SelectObject(dc, mkfont(hs[hi], names[fi])); uint8_t tm[64]; memset(tm, 0, sizeof tm); GetTextMetricsW(dc, PTR(tm));
    int32_t *m = (int32_t *)tm; WSIZE z; GetTextExtentPoint32W(dc, PTR(s), 19, PTR(&z));
    fprintf(t, "%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n", names[fi], hs[hi], m[1], m[2], m[0], m[3], m[4], m[5], m[6], z.cx);
  }
  fclose(t);
  /* EnumFontFamiliesEx: 全 face 列挙 + 名指定 */
  WRECT dummy_r; (void)dummy_r; uint8_t lf[92]; memset(lf, 0, sizeof lf);
  EnumFontFamiliesExW(dc, PTR(lf), PTR(enum_cb), 0, 0);
  int all_n = g_enum_n; g_enum_n = 0; uint16_t nm[32] = { 0 }; w16(nm, "barlow"); memcpy(lf + 28, nm, sizeof nm);
  EnumFontFamiliesExW(dc, PTR(lf), PTR(enum_cb), 0, 0);
  printf("enum all=%d named=%d first=%s\n", noeng ? 0 : all_n, g_enum_n, g_enum_n ? g_enum_names[0] : "-");
  return 0;
}
