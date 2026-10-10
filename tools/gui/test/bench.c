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
  WRECT r = { 0, 0, 1920, 1080 }; int64_t br = CreateSolidBrush(0x123456);
  t = now(); for (int i = 0; i < it; i++) FillRect(m2, (int64_t)(uintptr_t)&r, br); report("FillRect solid", 1920, 1080, it, now() - t);
  t = now(); for (int i = 0; i < it; i++) { BitBlt(wdc, 0, 0, 1920, 1080, m1, 0, 0, SRCCOPY); GdiFlush(); } report("BitBlt->window + present(headless)", 1920, 1080, it, now() - t);
  gui_hl_stop(); return 0;
}
