/* bench.c — shim の GDI 転送スループット (native -O2, 参考値; wasm は別途 e2e で実測) */
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include "gui_api.h"
#include "gui_internal.h"
#include "gui_headless.h"
static double now(void) { return gui_now_ms() / 1000.0; }
static int64_t mkdib(int w, int h, uint32_t **bits) {
  WBMIH bi; memset(&bi, 0, sizeof bi); bi.biSize = 40; bi.biWidth = w; bi.biHeight = -h; bi.biPlanes = 1; bi.biBitCount = 32;
  uint64_t bp = 0; int64_t d = CreateDIBSection(0, (int64_t)(uintptr_t)&bi, 0, (int64_t)(uintptr_t)&bp, 0, 0); *bits = (uint32_t *)(uintptr_t)bp; return d;
}
static void report(const char *n, int w, int h, int it, double t) { printf("[bench] %-34s %4dx%-4d %6.1f Mpx/s  (%.2f ms/frame, %.0f fps)\n", n, w, h, (double)w * h * it / t / 1e6, t / it * 1e3, it / t); }
int main(void) {
  gui_hl_start(1920, 1080, 1);
  WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)DefWindowProcA; wc.lpszClassName = (uint64_t)(uintptr_t)"B";
  RegisterClassA((int64_t)(uintptr_t)&wc);
  int64_t h = CreateWindowExA(0, (int64_t)(uintptr_t)"B", 0, WS_POPUP | WS_VISIBLE, 0, 0, 1920, 1080, 0, 0, 0, 0);
  uint32_t *b1, *b2; int64_t d1 = mkdib(1920, 1080, &b1), d2 = mkdib(1920, 1080, &b2);
  int64_t m1 = CreateCompatibleDC(0), m2 = CreateCompatibleDC(0); SelectObject(m1, d1); SelectObject(m2, d2);
  for (int i = 0; i < 1920 * 1080; i++) b1[i] = 0xFF000000u | i;
  int64_t wdc = GetDC(h); double t; int it = 30;
  t = now(); for (int i = 0; i < it; i++) BitBlt(m2, 0, 0, 1920, 1080, m1, 0, 0, SRCCOPY); report("BitBlt SRCCOPY mem->mem (memmove)", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) BitBlt(wdc, 0, 0, 1920, 1080, m1, 0, 0, SRCCOPY); report("BitBlt SRCCOPY mem->window", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) BitBlt(m2, 0, 0, 1920, 1080, m1, 0, 0, SRCINVERT); report("BitBlt SRCINVERT (per-pixel)", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) StretchBlt(m2, 0, 0, 1920, 1080, m1, 0, 0, 960, 540, SRCCOPY); report("StretchBlt 2x nearest", 1920, 1080, it, now() - t);
  WBMIH bi; memset(&bi, 0, sizeof bi); bi.biSize = 40; bi.biWidth = 1920; bi.biHeight = -1080; bi.biPlanes = 1; bi.biBitCount = 32;
  t = now(); for (int i = 0; i < it; i++) StretchDIBits(m2, 0, 0, 1920, 1080, 0, 0, 1920, 1080, (int64_t)(uintptr_t)b1, (int64_t)(uintptr_t)&bi, 0, SRCCOPY); report("StretchDIBits 1:1 (per-pixel)", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) AlphaBlend(m2, 0, 0, 1920, 1080, m1, 0, 0, 1920, 1080, (1u << 24) | (128u << 16)); report("AlphaBlend per-pixel alpha (sca=128)", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) AlphaBlend(m2, 0, 0, 1920, 1080, m1, 0, 0, 1920, 1080, (128u << 16)); report("AlphaBlend const (sca=128)", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) BitBlt(m2, 0, 0, 1920, 1080, m1, 0, 0, SRCPAINT); report("BitBlt SRCPAINT (per-pixel)", 1920, 1080, it, now() - t);
#ifdef BENCH_BPP   /* GUI-5: 24/8bpp 源 (旧実装では fail-fast のため after のみ) */
  { uint8_t *p24 = (uint8_t *)malloc((size_t)1920 * 3 * 1080), *p8 = (uint8_t *)malloc((size_t)1920 * 1080); memset(p24, 0x5A, (size_t)1920 * 3 * 1080); memset(p8, 7, (size_t)1920 * 1080);
    WBMIH b24 = bi; b24.biBitCount = 24; struct { WBMIH h; uint32_t c[256]; } b8; memset(&b8, 0, sizeof b8); b8.h = bi; b8.h.biBitCount = 8; b8.h.biClrUsed = 256; for (int i = 0; i < 256; i++) b8.c[i] = i * 0x010101;
    t = now(); for (int i = 0; i < it; i++) StretchDIBits(m2, 0, 0, 1920, 1080, 0, 0, 1920, 1080, (int64_t)(uintptr_t)p24, (int64_t)(uintptr_t)&b24, 0, SRCCOPY); report("StretchDIBits 24bpp 1:1", 1920, 1080, it, now() - t);
    t = now(); for (int i = 0; i < it; i++) StretchDIBits(m2, 0, 0, 1920, 1080, 0, 0, 1920, 1080, (int64_t)(uintptr_t)p8, (int64_t)(uintptr_t)&b8, 0, SRCCOPY); report("StretchDIBits 8bpp 1:1", 1920, 1080, it, now() - t);
    WBMIH s24 = bi; s24.biBitCount = 24; uint64_t pv = 0; int64_t d24 = CreateDIBSection(0, (int64_t)(uintptr_t)&s24, 0, (int64_t)(uintptr_t)&pv, 0, 0), m24 = CreateCompatibleDC(0); SelectObject(m24, d24);
    t = now(); for (int i = 0; i < it; i++) BitBlt(m2, 0, 0, 1920, 1080, m24, 0, 0, SRCCOPY); report("BitBlt SRCCOPY from 24bpp DIB section", 1920, 1080, it, now() - t);
    t = now(); for (int i = 0; i < it; i++) BitBlt(m24, 0, 0, 1920, 1080, m1, 0, 0, SRCCOPY); report("BitBlt SRCCOPY into 24bpp DIB section", 1920, 1080, it, now() - t); }
#endif
  WRECT r = { 0, 0, 1920, 1080 }; int64_t br = CreateSolidBrush(0x123456);
  t = now(); for (int i = 0; i < it; i++) FillRect(m2, (int64_t)(uintptr_t)&r, br); report("FillRect solid", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) { BitBlt(wdc, 0, 0, 1920, 1080, m1, 0, 0, SRCCOPY); GdiFlush(); } report("BitBlt->window + present(headless)", 1920, 1080, it, now() - t);
  gui_hl_stop(); return 0;
}
