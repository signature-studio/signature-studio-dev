/* adapt_test.c — wasm32 署名 adapter (integ/gen_adapt.py 産 gui_adapt_w32.c) の native wiring 検証 + 到達ログ + ハンドル 31bit。
 * shim 本体は gui_rename.h で gui_impl_<Name> に改名済み。ここでは IR 署名 (ptr/i32/i1/%tagPOINT 値渡し) で公開名を呼ぶ。
 * (native の ptr は 64bit のため zero-extend の 32bit 化自体は検証しない — それは sigprobe.sh + Chrome で担保) */
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include "gui_internal.h"
#include "gui_headless.h"

static int g_pass, g_fail;
#define CHK(c, ...) do { if (c) g_pass++; else { g_fail++; printf("  FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

/* IR 署名 (fixture と一致) のプロトタイプ */
void *CreateRectRgn(int32_t, int32_t, int32_t, int32_t);
int32_t GetRgnBox(void *, void *);
_Bool OffsetRect(void *, int32_t, int32_t);
_Bool IntersectRect(void *, void *, void *);
_Bool UnionRect(void *, void *, void *);
_Bool RectInRegion(void *, void *);
int32_t GetSysColor(int32_t);
void *CreateCompatibleDC(void *);
_Bool DeleteDC(void *);
int32_t SetBkColor(void *, int32_t);
void *WindowFromPoint(int32_t, int32_t);
void PostQuitMessage(int32_t);
void *GetStockObject(int32_t);
void *CreateSolidBrush(int32_t);
int32_t MapVirtualKeyW(int32_t, int32_t);
int64_t gui_impl_CreateBitmap(int64_t, int64_t, int64_t, int64_t, int64_t);
int64_t gui_impl_CreatePen(int64_t, int64_t, int64_t);
int64_t gui_impl_CreateFontIndirectW(int64_t);
int64_t gui_impl_CreatePalette(int64_t);
int64_t gui_impl_LoadCursorW(int64_t, int64_t);
int64_t gui_impl_LoadIconW(int64_t, int64_t);
int64_t gui_impl_RegisterClassA(int64_t);
int64_t gui_impl_CreateWindowExA(int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t);
int64_t gui_impl_GetDC(int64_t);
int64_t gui_impl_BeginDeferWindowPos(int64_t);
int64_t gui_impl_DefWindowProcA(int64_t, int64_t, int64_t, int64_t);
int gui_reach_distinct(void);
int gui_reach_calls(const char *);

static int64_t wp(int64_t h, int64_t m, int64_t w, int64_t l) { return gui_impl_DefWindowProcA(h, m, w, l); }

int main(void) {
  gui_hl_start(640, 480, 1);

  void *rgn = CreateRectRgn(1, 2, 11, 12);
  int32_t rc[4] = { 0 };
  CHK(GetRgnBox(rgn, rc) == SIMPLEREGION && rc[0] == 1 && rc[1] == 2 && rc[2] == 11 && rc[3] == 12, "CreateRectRgn/GetRgnBox via adapter");
  int32_t r1[4] = { 10, 10, 20, 20 }, r2[4] = { 15, 5, 30, 18 }, o[4];
  CHK(OffsetRect(r1, -5, 3) && r1[0] == 5 && r1[1] == 13 && r1[2] == 15 && r1[3] == 23, "OffsetRect with negative i32 (sign-extend)");
  memset(o, 0xAA, sizeof o);
  CHK(!IntersectRect(o, r1, r2) && o[0] == 0 && o[3] == 0, "IntersectRect i1 false (r1.right == r2.left -> empty, out zeroed)");
  int32_t r3[4] = { 0, 0, 10, 10 }, r4[4] = { 5, 5, 20, 20 };
  CHK(IntersectRect(o, r3, r4) && o[0] == 5 && o[1] == 5 && o[2] == 10 && o[3] == 10, "IntersectRect overlap");
  CHK(UnionRect(o, r3, r4) && o[0] == 0 && o[2] == 20, "UnionRect");
  int32_t inr[4] = { 2, 3, 4, 5 };
  CHK(RectInRegion(rgn, inr) == 1, "RectInRegion i1 true");
  CHK(GetSysColor(5) == 0xFFFFFF, "GetSysColor");
  void *dc = CreateCompatibleDC(NULL);
  CHK(SetBkColor(dc, 0xFF00FF) == 0xFFFFFF && SetBkColor(dc, 0) == 0xFF00FF, "SetBkColor i32 arg/ret through adapter");
  CHK(WindowFromPoint(5, 5) == NULL, "WindowFromPoint (struct by value packed into int64) with no window");
  CHK(MapVirtualKeyW(0x41, 2) == 0x41, "MapVirtualKeyW");
  PostQuitMessage(3);   /* void 戻り */
  CHK(DeleteDC(dc), "DeleteDC i1");

  CHK(gui_reach_calls("OffsetRect") == 1 && gui_reach_calls("IntersectRect") == 2 && gui_reach_calls("SetBkColor") == 2, "reach counts via adapter (%d %d %d)",
      gui_reach_calls("OffsetRect"), gui_reach_calls("IntersectRect"), gui_reach_calls("SetBkColor"));
  CHK(gui_reach_calls("WindowFromPoint") == 1 && gui_reach_calls("NoSuchApi") == -1, "reach lookup (unknown name = -1)");
  int d0 = gui_reach_distinct();
  gui_impl_CreateBitmap(1, 1, 1, 32, 0);   /* 改名側を直接叩いても計数されない */
  CHK(gui_reach_distinct() == d0 && gui_reach_calls("CreateBitmap") == 0, "internal/impl calls are not counted");

  /* ---- ハンドル 31bit : 全 HType の発行値が < 2^31 (wasm32 の i32/ptr に潰れても同一値) ---- */
  WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)wp; wc.lpszClassName = (uint64_t)(uintptr_t)"H31";
  gui_impl_RegisterClassA((int64_t)(uintptr_t)&wc);
  int64_t hw = gui_impl_CreateWindowExA(0, (int64_t)(uintptr_t)"H31", (int64_t)(uintptr_t)"t", WS_POPUP | WS_VISIBLE, 0, 0, 40, 40, 0, 0, 0, 0);
  WLOGBRUSH dummy; (void)dummy; uint8_t lf[92]; memset(lf, 0, sizeof lf);
  struct { const char *n; int64_t h; } hs[] = {
    { "WND", hw }, { "DC(window)", gui_impl_GetDC(hw) }, { "DC(mem)", (int64_t)(uintptr_t)CreateCompatibleDC(NULL) },
    { "BMP", gui_impl_CreateBitmap(4, 4, 1, 32, 0) }, { "BRUSH", (int64_t)(uintptr_t)CreateSolidBrush(0x123456) }, { "PEN", gui_impl_CreatePen(0, 1, 0) },
    { "FONT", gui_impl_CreateFontIndirectW((int64_t)(uintptr_t)lf) }, { "RGN", (int64_t)(uintptr_t)rgn }, { "PAL", gui_impl_CreatePalette(0) },
    { "stock(WHITE)", (int64_t)(uintptr_t)GetStockObject(0) }, { "stock(SYSFONT)", (int64_t)(uintptr_t)GetStockObject(13) },
    { "CURSOR", gui_impl_LoadCursorW(0, 32512) }, { "ICON", gui_impl_LoadIconW(0, 32512) }, { "DEFER", gui_impl_BeginDeferWindowPos(2) },
  };
  for (unsigned i = 0; i < sizeof hs / sizeof hs[0]; i++)
    CHK(hs[i].h > 0 && (uint64_t)hs[i].h < 0x80000000ull && (int64_t)(int32_t)hs[i].h == hs[i].h, "handle %s = 0x%llx is a positive 31-bit value", hs[i].n, (unsigned long long)hs[i].h);

  gui_hl_stop();
  printf("[adapt_test] %d passed, %d failed\n", g_pass, g_fail);
  return g_fail ? 1 : 0;
}
