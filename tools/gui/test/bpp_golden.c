/* bpp_golden.c — GUI-5 (#181) の各 bpp シーンを shim で描画し PPM に書く (期待画像は独立 Python オラクル golden/gen_golden_bpp.py)。
 * 使い方: bpp_golden <out.ppm>。環境変数 BPP_FAULT=1 で故意の欠陥 (8bpp DIB section の色テーブルを 1 色差し替え) を入れる (ネガティブコントロール)。 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gui_api.h"
#include "gui_internal.h"
#include "gui_headless.h"
#define PTR(x) ((int64_t)(uintptr_t)(x))
#define CR(r, g, b) ((uint32_t)((r) | (g) << 8 | (b) << 16))
#define W 160
#define H 100
typedef struct { WBMIH h; uint32_t c[256]; } Bmi;
static void bmi(Bmi *b, int w, int h, int bpp, int ncol) { memset(b, 0, sizeof *b); b->h.biSize = 40; b->h.biWidth = w; b->h.biHeight = h; b->h.biPlanes = 1; b->h.biBitCount = (uint16_t)bpp; b->h.biClrUsed = (uint32_t)ncol; }
static uint32_t quad(int r, int g, int b) { return (uint32_t)(r << 16 | g << 8 | b); }
static int64_t dib(int w, int h, int bpp, const uint32_t *pal, int n, uint8_t **p, int64_t *dc) {
  Bmi b; bmi(&b, w, h, bpp, n); for (int i = 0; i < n; i++) b.c[i] = pal[i]; uint64_t pv = 0;
  int64_t hb = CreateDIBSection(0, PTR(&b), 0, PTR(&pv), 0, 0); *dc = CreateCompatibleDC(0); SelectObject(*dc, hb); *p = (uint8_t *)(uintptr_t)pv; return hb;
}
int main(int argc, char **argv) {
  if (argc < 2) return 2;
  int fault = getenv("BPP_FAULT") && atoi(getenv("BPP_FAULT"));
  gui_hl_start(640, 480, 1);
  uint8_t *cp; int64_t cdc; int64_t cbm = dib(W, -H, 32, 0, 0, &cp, &cdc); (void)cbm;
  WRECT all = { 0, 0, W, H }; int64_t bg = CreateSolidBrush(CR(32, 32, 48)); FillRect(cdc, PTR(&all), bg);
  /* 1. 24bpp StretchDIBits 8x6 bottom-up -> 16x12 at (4,4) */
  { uint8_t s[12 * 6 * 2]; memset(s, 0, sizeof s); int st = 24;   /* 8*3=24 -> stride 24 */
    for (int y = 0; y < 6; y++) for (int x = 0; x < 8; x++) { uint8_t *q = s + (5 - y) * st + x * 3; q[0] = (uint8_t)(x * 37 + y * 11); q[1] = (uint8_t)(x * 5 + y * 29); q[2] = (uint8_t)(x * 13 + y * 7); }
    Bmi b; bmi(&b, 8, 6, 24, 0); StretchDIBits(cdc, 4, 4, 16, 12, 0, 0, 8, 6, PTR(s), PTR(&b), 0, SRCCOPY); }
  /* 2. 8bpp StretchDIBits 8x6 bottom-up palette(8) -> 24x18 at (40,4) */
  { uint32_t pal[8]; for (int i = 0; i < 8; i++) pal[i] = quad(i * 32, 255 - i * 32, (i * 77) & 255);
    uint8_t s[8 * 6]; for (int y = 0; y < 6; y++) for (int x = 0; x < 8; x++) s[(5 - y) * 8 + x] = (uint8_t)((x + 2 * y) % 8);
    Bmi b; bmi(&b, 8, 6, 8, 8); for (int i = 0; i < 8; i++) b.c[i] = pal[i]; StretchDIBits(cdc, 40, 4, 24, 18, 0, 0, 8, 6, PTR(s), PTR(&b), 0, SRCCOPY); }
  /* 3. 4bpp 8x4 top-down -> 16x8 at (4,40) */
  { uint32_t pal[16]; for (int i = 0; i < 16; i++) pal[i] = quad(i * 17, i * 17, 255 - i * 17);
    uint8_t s[4 * 4]; memset(s, 0, sizeof s); for (int y = 0; y < 4; y++) for (int x = 0; x < 8; x++) { int v = (x * 3 + y) % 16; s[y * 4 + (x >> 1)] |= (uint8_t)((x & 1) ? v : v << 4); }
    Bmi b; bmi(&b, 8, -4, 4, 16); for (int i = 0; i < 16; i++) b.c[i] = pal[i]; StretchDIBits(cdc, 4, 40, 16, 8, 0, 0, 8, 4, PTR(s), PTR(&b), 0, SRCCOPY); }
  /* 4. 1bpp 16x8 top-down 1:1 at (40,40) */
  { uint32_t pal[2] = { quad(200, 40, 40), quad(40, 200, 40) }; uint8_t s[4 * 8]; memset(s, 0, sizeof s);
    for (int y = 0; y < 8; y++) for (int x = 0; x < 16; x++) if (((x >> 2) + (y >> 1)) & 1) s[y * 4 + (x >> 3)] |= (uint8_t)(0x80 >> (x & 7));
    Bmi b; bmi(&b, 16, -8, 1, 2); b.c[0] = pal[0]; b.c[1] = pal[1]; StretchDIBits(cdc, 40, 40, 16, 8, 0, 0, 16, 8, PTR(s), PTR(&b), 0, SRCCOPY); }
  /* 5. 24bpp DIB section 16x8 (app が native を直接書く + GDI FillRect/LineTo) -> BitBlt (80,4) */
  uint8_t *p24; int64_t d24; dib(16, 8, 24, 0, 0, &p24, &d24);
  for (int y = 0; y < 8; y++) for (int x = 0; x < 16; x++) { uint8_t *q = p24 + (7 - y) * 48 + x * 3; q[0] = 128; q[1] = (uint8_t)(y * 32); q[2] = (uint8_t)(x * 16); }   /* B,G,R ; bottom-up */
  { WRECT r = { 4, 2, 12, 6 }; int64_t b = CreateSolidBrush(CR(255, 255, 0)); FillRect(d24, PTR(&r), b); int64_t pen = CreatePen(PS_SOLID, 1, CR(0, 0, 0)); SelectObject(d24, pen); MoveToEx(d24, 0, 0, 0); LineTo(d24, 15, 7); }
  BitBlt(cdc, 80, 4, 16, 8, d24, 0, 0, SRCCOPY);
  /* 6. 8bpp DIB section 16x8 palette(4): native indices + FillRect (最近傍色) -> BitBlt (80,40) */
  uint32_t pal4[4] = { quad(0, 0, 0), quad(255, 0, 0), quad(0, 255, 0), quad(0, 0, 255) };
  uint8_t *p8; int64_t d8; dib(16, 8, 8, pal4, 4, &p8, &d8);
  for (int y = 0; y < 8; y++) for (int x = 0; x < 16; x++) p8[(7 - y) * 16 + x] = (uint8_t)((x + y) & 3);
  { WRECT r1 = { 2, 2, 10, 6 }, r2 = { 10, 2, 14, 6 }; int64_t b1 = CreateSolidBrush(CR(250, 10, 10)), b2 = CreateSolidBrush(CR(10, 10, 240)); FillRect(d8, PTR(&r1), b1); FillRect(d8, PTR(&r2), b2); }
  if (fault) { uint32_t c = quad(0, 255, 255); SetDIBColorTable(d8, 2, 1, PTR(&c)); }   /* 故意の欠陥: パレット index 2 を緑 -> シアンに */
  BitBlt(cdc, 80, 40, 16, 8, d8, 0, 0, SRCCOPY);
  /* 7. mono DDB 16x8 (WORD 行) -> text 赤 / bk 青 で (4,70) */
  { uint8_t mb[16]; for (int y = 0; y < 8; y++) { mb[y * 2] = (uint8_t)(0xA5 << (y & 3)); mb[y * 2 + 1] = (uint8_t)(0x3C >> (y & 3)); }
    int64_t hm = CreateBitmap(16, 8, 1, 1, PTR(mb)), mdc = CreateCompatibleDC(0); SelectObject(mdc, hm);
    SetTextColor(cdc, CR(255, 0, 0)); SetBkColor(cdc, CR(0, 0, 255)); BitBlt(cdc, 4, 70, 16, 8, mdc, 0, 0, SRCCOPY); }
  /* 8. 24bpp section を 2x SRCINVERT (40,70) / 9. 8bpp section を AlphaBlend sca=100 (80,70) */
  StretchBlt(cdc, 40, 70, 32, 16, d24, 0, 0, 16, 8, SRCINVERT);
  AlphaBlend(cdc, 80, 70, 16, 8, d8, 0, 0, 16, 8, (100u << 16));
  GdiFlush();
  FILE *f = fopen(argv[1], "wb"); fprintf(f, "P6\n%d %d\n255\n", W, H);
  for (int i = 0; i < W * H; i++) { uint32_t v = ((uint32_t *)cp)[i]; fputc((v >> 16) & 255, f); fputc((v >> 8) & 255, f); fputc(v & 255, f); }
  fclose(f); gui_hl_stop(); printf("bpp_golden: wrote %s (%dx%d)\n", argv[1], W, H); return 0;
}
