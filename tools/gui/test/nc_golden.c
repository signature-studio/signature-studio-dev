/* nc_golden.c — GUI-7 (#183) FL 非依存部: popup / tooltip surface・NC 領域 (WM_NCCALCSIZE/NCPAINT/NCHITTEST)・無効領域の複数矩形・DPI。
 * shim を直接呼ぶ (bpp_golden.c と同形式)。期待画像は独立 Python オラクル golden/gen_golden_nc.py。
 * 環境変数 NC_FAULT=1: tooltip を TOPMOST にしない (z-order 欠陥) / NC_FAULT=2: 2 矩形でなく外接矩形を無効化 (単一矩形化の欠陥) — ネガティブコントロール。 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gui_api.h"
#include "gui_internal.h"
#include "gui_headless.h"
#define PTR(x) ((int64_t)(uintptr_t)(x))
#define CR(r, g, b) ((uint32_t)((r) | (g) << 8 | (b) << 16))
#define DW 200
#define DH 140
extern GuiShared *gui_shared_native(void);
static int g_pass, g_fail;
#define CHK(c, ...) do { if (c) g_pass++; else { g_fail++; printf("  FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
static uint32_t g_main_col = CR(50, 50, 60);
static int g_nclbd, g_ncl_ht;
static int64_t fill_client(int64_t h, uint32_t col) {
  WPAINTSTRUCT ps; int64_t dc = BeginPaint(h, PTR(&ps)); WRECT r = { 0, 0, 4000, 4000 };
  int64_t b = CreateSolidBrush(col); FillRect(dc, PTR(&r), b); DeleteObject(b); EndPaint(h, PTR(&ps)); return 0;
}
static int64_t main_proc(int64_t h, int64_t m, int64_t w, int64_t l) {
  if (m == WM_PAINT) return fill_client(h, g_main_col);
  if (m == 0xA1) { g_nclbd++; g_ncl_ht = (int)w; return 0; }   /* WM_NCLBUTTONDOWN */
  return DefWindowProcA(h, m, w, l);
}
static int64_t popup_proc(int64_t h, int64_t m, int64_t w, int64_t l) { if (m == WM_PAINT) return fill_client(h, CR(30, 60, 200)); return DefWindowProcA(h, m, w, l); }
static int64_t tip_proc(int64_t h, int64_t m, int64_t w, int64_t l) {
  if (m == WM_PAINT) return fill_client(h, CR(255, 255, 225));
  if (m == WM_NCHITTEST) return -1;   /* HTTRANSPARENT */
  return DefWindowProcA(h, m, w, l);
}
static void reg(const char *n, int64_t (*p)(int64_t, int64_t, int64_t, int64_t)) {
  WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)p; wc.lpszClassName = (uint64_t)(uintptr_t)n; RegisterClassA(PTR(&wc));
}
static void pump(void) { WMSG m; while (PeekMessageA(PTR(&m), 0, 0, 0, PM_REMOVE)) DispatchMessageA(PTR(&m)); GdiFlush(); }
static void settle(void) {
  GuiShared *S = gui_shared_native(); GdiFlush();
  for (;;) {
    uint32_t done = __atomic_load_n(&S->present_done_seq, __ATOMIC_SEQ_CST), want = __atomic_load_n(&S->present_seq, __ATOMIC_SEQ_CST);
    uint32_t head = __atomic_load_n(&S->out_ring.head, __ATOMIC_SEQ_CST), tail = __atomic_load_n(&S->out_ring.tail, __ATOMIC_SEQ_CST);
    if (done >= want && head == tail) break;
    gui_futex_wait(&S->out_ring.head, head, 20);
  }
}
static int64_t hit(int64_t h, int x, int y) { return (int32_t)SendMessageA(h, WM_NCHITTEST, 0, ((int64_t)(uint16_t)y << 16) | (uint16_t)x); }
int main(int argc, char **argv) {
  if (argc < 2) return 2;
  int fault = getenv("NC_FAULT") ? atoi(getenv("NC_FAULT")) : 0;
  gui_hl_start(DW, DH, 1);
  reg("NCmain", main_proc); reg("NCpop", popup_proc); reg("NCtip", tip_proc);
  const int32_t CAP = 0x00C00000, THICK = 0x00040000, TOPMOST = 8, NOACT = 0x08000000, TRANSP = 0x20;
  int64_t hm = CreateWindowExA(0, PTR("NCmain"), PTR("main"), WS_VISIBLE | CAP | THICK, 10, 10, 130, 113, 0, 0, 0x400000, 0);   /* window rect 130x113 = client 120x80 + NC (5,28,5,5) */
  pump();
  WRECT cr, wr; GetClientRect(hm, PTR(&cr)); GetWindowRect(hm, PTR(&wr));
  CHK(cr.right == 120 && cr.bottom == 80, "client rect %dx%d (want 120x80)", cr.right, cr.bottom);
  CHK(wr.left == 10 && wr.top == 10 && wr.right == 140 && wr.bottom == 123, "window rect (%d,%d,%d,%d)", wr.left, wr.top, wr.right, wr.bottom);
  WPOINT pt = { 0, 0 }; ClientToScreen(hm, PTR(&pt)); CHK(pt.x == 15 && pt.y == 38, "client origin (%d,%d) want (15,38)", pt.x, pt.y);
  /* tooltip (TOPMOST|NOACTIVATE|TRANSPARENT) を popup より先に作っても、popup の後も最前面のまま */
  int64_t ht = CreateWindowExA(TRANSP | NOACT | (fault == 1 ? 0 : TOPMOST), PTR("NCtip"), 0, WS_POPUP | WS_VISIBLE, 70, 40, 60, 14, 0, 0, 0x400000, 0);
  CHK(GetActiveWindow() == hm, "NOACTIVATE tooltip must not take activation");
  int64_t hp = CreateWindowExA(0, PTR("NCpop"), 0, WS_POPUP | WS_VISIBLE, 90, 50, 80, 50, 0, 0, 0x400000, 0);
  CHK(GetActiveWindow() == hp, "popup takes activation");
  pump();
  /* 無効領域の複数矩形: 全面を別色で塗る WM_PAINT でも、無効な 2 矩形 (client 座標) だけが更新される */
  g_main_col = CR(200, 40, 40);
  WRECT A = { 10, 10, 40, 30 }, B = { 70, 50, 110, 70 }, U = { 10, 10, 110, 70 };
  if (fault == 2) InvalidateRect(hm, PTR(&U), 0); else { InvalidateRect(hm, PTR(&A), 0); InvalidateRect(hm, PTR(&B), 0); }
  WRECT ur; GetUpdateRect(hm, PTR(&ur), 0);
  CHK(ur.left == 10 && ur.top == 10 && ur.right == 110 && ur.bottom == 70, "GetUpdateRect = bbox (%d,%d,%d,%d)", ur.left, ur.top, ur.right, ur.bottom);
  int64_t rg = CreateRectRgn(0, 0, 0, 0); int rt = (int)GetUpdateRgn(hm, rg, 0);
  CHK(fault == 2 ? rt == 2 : rt == 3, "GetUpdateRgn complexity %d (want 3 = COMPLEXREGION for 2 rects)", rt);
  CHK(PtInRegion(rg, 20, 20) && PtInRegion(rg, 80, 60) && !PtInRegion(rg, 60, 20) || fault == 2, "update region membership");
  pump(); settle();
  /* WM_NCHITTEST (DefWindowProc の NC 判定) */
  CHK(hit(hm, 60, 60) == 1, "client -> HTCLIENT");
  CHK(hit(hm, 60, 20) == 2, "caption -> HTCAPTION (got %d)", (int)hit(hm, 60, 20));
  CHK(hit(hm, 12, 60) == 18, "left frame -> HTBORDER (got %d)", (int)hit(hm, 12, 60));
  CHK(hit(hm, 5, 60) == 0, "outside -> HTNOWHERE");
  { WPOINT p = { 100, 52 }; int64_t w = WindowFromPoint(((int64_t)p.y << 32) | (uint32_t)p.x);
    CHK(w == hp, "tooltip is HTTRANSPARENT: WindowFromPoint under it reaches popup (got %llx want %llx)", (long long)w, (long long)hp); }
  /* NC 入力: caption 上のクリックは WM_NCLBUTTONDOWN(HTCAPTION) として届く (client 入力にはならない) */
  gui_hl_input(GUI_IN_MOUSE_DOWN, 0, 40, 20, 0, 0); gui_hl_input(GUI_IN_MOUSE_UP, 0, 40, 20, 0, 0);
  for (int i = 0; i < 50 && !g_nclbd; i++) { pump(); gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); }
  CHK(g_nclbd == 1 && g_ncl_ht == 2, "WM_NCLBUTTONDOWN delivered once with HTCAPTION (n=%d ht=%d)", g_nclbd, g_ncl_ht);
  settle();
  gui_hl_dump_ppm(argv[1]);
  /* DPI: 非対応スレッド = 96 / 対応 = dpr*96 にシステムメトリクス・NC 幅・LOGPIXELS が比例 */
  GuiShared *S = gui_shared_native(); S->dpr_x100 = 200;
  CHK(GetDpiForWindow(hm) == 96 && GetSystemMetrics(SM_CYCAPTION) == 23 && !IsProcessDPIAware(), "unaware thread sees 96 dpi");
  CHK(SetThreadDpiAwarenessContext(-4) == -1, "SetThreadDpiAwarenessContext returns the previous context");
  CHK(GetDpiForWindow(hm) == 192 && GetDpiForSystem() == 192 && GetSystemMetrics(SM_CYCAPTION) == 46 && GetSystemMetrics(SM_CXFRAME) == 8, "aware thread sees 192 dpi (caption %lld)", (long long)GetSystemMetrics(SM_CYCAPTION));
  { int64_t dc = GetDC(hm); CHK(GetDeviceCaps(dc, LOGPIXELSX) == 192, "GetDeviceCaps(LOGPIXELSX) follows dpi"); ReleaseDC(hm, dc); }
  { WRECT r = { 0, 0, 100, 100 }; AdjustWindowRectEx(PTR(&r), CAP | THICK, 0, 0);
    CHK(r.left == -10 && r.top == -56 && r.right == 110 && r.bottom == 110, "AdjustWindowRectEx at 192 dpi (%d,%d,%d,%d)", r.left, r.top, r.right, r.bottom); }
  int64_t h2 = CreateWindowExA(0, PTR("NCmain"), 0, CAP | THICK, 0, 0, 200, 200, 0, 0, 0x400000, 0);
  { WRECT c2; GetClientRect(h2, PTR(&c2)); CHK(c2.right == 180 && c2.bottom == 200 - 56 - 10, "NC width scales with dpi at creation (client %dx%d)", c2.right, c2.bottom); }
  CHK(SetThreadDpiAwarenessContext(-1) == -4 && GetDpiForWindow(hm) == 96, "restore unaware");
  CHK(SetThreadDpiAwarenessContext(7) == 0, "invalid context rejected");
  { WRECT r = { 0, 0, 100, 100 }; AdjustWindowRectEx(PTR(&r), CAP | THICK, 0, 0); CHK(r.left == -5 && r.top == -28 && r.right == 105 && r.bottom == 105, "AdjustWindowRectEx at 96 dpi"); }
  printf("[nc_golden] asserts: %d passed, %d failed\n", g_pass, g_fail);
  gui_hl_stop(); return g_fail ? 1 : 0;
}
