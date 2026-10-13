/* shim_probe.c — KH-7 (#59): HeartCore (UIWindowWin32 の WndProc) の画面転送呼び出しを M7 GUI shim (tools/gui) へそのまま投入し、
 * 画素を独立オラクルと比較する。ui_present.py が逆アセンブルから復元した引数の形を使う:
 *   ps = BeginPaint(); SetDIBitsToDevice(ps.hdc, L, T, R-L, B-T, L, H-B, StartScan=0, cLines=H, bits, &{40,W,-H,1,32,BI_RGB,0}, DIB_RGB_COLORS); EndPaint()
 * オラクル: (a) 期待画素 = バックバッファ[y][x] (実 Windows で正しく表示されることが前提の HeartCore 側の意図),
 *           (b) Wine の nulldrv_SetDIBitsToDevice の式 src_top_row = startscan + lines - (ySrc + cy) が各ケースで top と一致すること。
 * 対照: 同じ形で bottom-up DIB (biHeight=+H) を渡す。
 * 終了コード: 0 = 全ケース一致 / 2 = HeartCore 形 (top-down) の不一致が残る (gap) / 1 = ハーネス異常 (対照・オラクル感度・式の不一致)
 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include "gui_internal.h"
#include "gui_headless.h"

extern GuiShared *gui_shared_native(void);
int64_t RegisterClassA(int64_t), CreateWindowExA(int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t);
int64_t GetDC(int64_t), ReleaseDC(int64_t, int64_t), BeginPaint(int64_t, int64_t), EndPaint(int64_t, int64_t), InvalidateRect(int64_t, int64_t, int64_t);
int64_t FillRect(int64_t, int64_t, int64_t), CreateSolidBrush(int64_t), DeleteObject(int64_t), GdiFlush(void);
int64_t SetDIBitsToDevice(int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t, int64_t);
int64_t PeekMessageA(int64_t, int64_t, int64_t, int64_t, int64_t), DispatchMessageA(int64_t), DefWindowProcA(int64_t, int64_t, int64_t, int64_t);

enum { W = 100, H = 80, OX = 10, OY = 20 };
static uint32_t g_back[H][W];     /* top-down 論理画像 (バックバッファ) */
static uint32_t g_buf_td[H * W];  /* top-down メモリ: 行 y = 論理行 y */
static uint32_t g_buf_bu[H * W];  /* bottom-up メモリ: 行 r = 論理行 H-1-r */
static int g_bottom_up, g_painted;
static WRECT g_rc_seen;
static int g_force_naive;         /* 1: ySrc を top にして呼ぶ (shim の top-down 解釈に合わせた呼び方) */

static uint32_t desk(int x, int y) { return gui_hl_desktop()[(size_t)y * 640 + x] & 0xFFFFFF; }
static void flush_wait(void) {
  GuiShared *S = gui_shared_native();
  GdiFlush();
  for (;;) {
    uint32_t done = __atomic_load_n(&S->present_done_seq, __ATOMIC_SEQ_CST), want = __atomic_load_n(&S->present_seq, __ATOMIC_SEQ_CST);
    uint32_t head = __atomic_load_n(&S->out_ring.head, __ATOMIC_SEQ_CST), tail = __atomic_load_n(&S->out_ring.tail, __ATOMIC_SEQ_CST);
    if (done >= want && head == tail) break;
    gui_futex_wait(&S->out_ring.head, head, 20);
  }
}

static int64_t wndproc(int64_t h, int64_t m, int64_t w, int64_t l) {
  if (m == WM_ERASEBKGND) return 1;
  if (m == WM_PAINT) {
    WPAINTSTRUCT ps; int64_t hdc = BeginPaint(h, (int64_t)(uintptr_t)&ps);
    WRECT rc = ps.rcPaint; g_rc_seen = rc;
    WBMIH bi; memset(&bi, 0, sizeof bi);
    bi.biSize = 40; bi.biWidth = W; bi.biHeight = g_bottom_up ? H : -H; bi.biPlanes = 1; bi.biBitCount = 32; bi.biCompression = 0; bi.biSizeImage = 0;
    int ysrc = g_force_naive ? rc.top : (H - rc.bottom);
    SetDIBitsToDevice(hdc, rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top, rc.left, ysrc, 0, H,
                      (int64_t)(uintptr_t)(g_bottom_up ? g_buf_bu : g_buf_td), (int64_t)(uintptr_t)&bi, 0);
    EndPaint(h, (int64_t)(uintptr_t)&ps);
    g_painted++;
    return 0;
  }
  return DefWindowProcA(h, m, w, l);
}

static void pump_paint(void) {
  WMSG m; int guard = 0;
  g_painted = 0;
  while (!g_painted && guard++ < 2000) {
    if (!PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE)) { usleep(2000); continue; }
    DispatchMessageA((int64_t)(uintptr_t)&m);
  }
}

typedef struct { const char *name; WRECT r; } Case;
static const Case CASES[] = {
  { "full (0,0,100,80)", { 0, 0, 100, 80 } },
  { "top-aligned (20,0,60,30)", { 20, 0, 60, 30 } },
  { "asymmetric (20,10,60,30)", { 20, 10, 60, 30 } },
  { "bottom-aligned (30,50,70,80)", { 30, 50, 70, 80 } },
  { "v-symmetric top+bottom=H (10,30,50,50)", { 10, 30, 50, 50 } },
  { "one row (0,5,100,6)", { 0, 5, 100, 6 } },
  { "one pixel (7,70,8,71)", { 7, 70, 8, 71 } },
};
enum { NCASE = sizeof CASES / sizeof CASES[0] };
static const uint32_t SENTINEL = 0x123456;

/* 戻り値: 矩形内の不一致画素数 + 矩形外の破壊画素数。corrupt=1 ならオラクルの期待値を 1 画素壊して感度を見る */
static int run_case(int64_t h, const Case *c, int corrupt, int *inside_wrong, int *outside_wrong, int *wine_row_ok) {
  int64_t dc = GetDC(h); WRECT all = { 0, 0, W, H }; int64_t br = CreateSolidBrush(0x563412 /* COLORREF BGR → RGB 0x123456 */);
  FillRect(dc, (int64_t)(uintptr_t)&all, br); DeleteObject(br); ReleaseDC(h, dc); flush_wait();
  InvalidateRect(h, (int64_t)(uintptr_t)&c->r, 0);
  pump_paint(); flush_wait();
  int in_w = 0, out_w = 0;
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      int inside = x >= c->r.left && x < c->r.right && y >= c->r.top && y < c->r.bottom;
      uint32_t want = inside ? (g_back[y][x] & 0xFFFFFF) : SENTINEL;
      if (corrupt && x == c->r.left && y == c->r.top) want ^= 1;
      uint32_t got = desk(OX + x, OY + y);
      if (got != want) { if (inside) in_w++; else out_w++; }
    }
  /* Wine 式: 描画される DIB 最上行 (top-down 行番号) = startscan + lines - (ySrc + cy) */
  int cy = c->r.bottom - c->r.top, ys = H - c->r.bottom;
  *wine_row_ok = (0 + H - (ys + cy)) == c->r.top && g_rc_seen.top == c->r.top && g_rc_seen.bottom == c->r.bottom && g_rc_seen.left == c->r.left && g_rc_seen.right == c->r.right;
  *inside_wrong = in_w; *outside_wrong = out_w;
  return in_w + out_w;
}

int main(void) {
  for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++) {
      uint32_t px = 0xFF000000u | ((uint32_t)(y + 1) << 16) | ((uint32_t)(x + 1) << 8) | 0x5A;   /* (x,y) ごとに一意 */
      g_back[y][x] = px; g_buf_td[y * W + x] = px; g_buf_bu[(H - 1 - y) * W + x] = px;
    }
  gui_hl_start(640, 480, 1);
  WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = (uint64_t)(uintptr_t)wndproc; wc.lpszClassName = (uint64_t)(uintptr_t)"KHProbe";
  if (!RegisterClassA((int64_t)(uintptr_t)&wc)) { printf("harness: RegisterClass failed\n"); return 1; }
  int64_t h = CreateWindowExA(0, (int64_t)(uintptr_t)"KHProbe", (int64_t)(uintptr_t)"kh", WS_POPUP | WS_VISIBLE, OX, OY, W, H, 0, 0, 0x400000, 0);
  if (!h) { printf("harness: CreateWindow failed\n"); return 1; }
  pump_paint(); flush_wait();   /* 初回 WM_PAINT を消化 */

  int fail_td = 0, fail_bu = 0, harness = 0;
  printf("== HeartCore 形 (top-down biHeight=-%d, ySrc=H-bottom, StartScan=0, cLines=H) ==\n", H);
  g_bottom_up = 0;
  for (int i = 0; i < NCASE; i++) {
    int iw, ow, wr; run_case(h, &CASES[i], 0, &iw, &ow, &wr);
    printf("  [%s] %-42s 矩形内不一致=%4d (矩形面積 %5d) 矩形外破壊=%d  wine式==top:%s\n", (iw + ow) ? "FAIL" : "PASS", CASES[i].name, iw,
           (CASES[i].r.right - CASES[i].r.left) * (CASES[i].r.bottom - CASES[i].r.top), ow, wr ? "yes" : "NO");
    if (iw + ow) fail_td++;
    if (!wr) harness++;
  }
  printf("== 対照: 同じ呼び方 + bottom-up DIB (biHeight=+%d) ==\n", H);
  g_bottom_up = 1;
  for (int i = 0; i < NCASE; i++) {
    int iw, ow, wr; run_case(h, &CASES[i], 0, &iw, &ow, &wr);
    printf("  [%s] %-42s 矩形内不一致=%4d 矩形外破壊=%d\n", (iw + ow) ? "FAIL" : "PASS", CASES[i].name, iw, ow);
    if (iw + ow) fail_bu++;
  }
  printf("== 対照: top-down で ySrc=top (shim の解釈に合わせた呼び方; 実 Windows/Wine の式とは異なる) ==\n");
  g_bottom_up = 0; g_force_naive = 1;
  int naive_fail = 0;
  for (int i = 0; i < NCASE; i++) {
    int iw, ow, wr; run_case(h, &CASES[i], 0, &iw, &ow, &wr);
    printf("  [%s] %-42s 矩形内不一致=%4d 矩形外破壊=%d\n", (iw + ow) ? "FAIL" : "PASS", CASES[i].name, iw, ow);
    if (iw + ow) naive_fail++;
  }
  g_force_naive = 0;
  printf("== オラクル感度 (ネガコン): bottom-up 対照の full ケースで期待値を 1 画素だけ壊す → 不一致 1 件を検出できること ==\n");
  g_bottom_up = 1;
  { int iw, ow, wr; int n = run_case(h, &CASES[0], 1, &iw, &ow, &wr);
    printf("  壊した期待値との不一致 = %d (期待 1)\n", n);
    if (n != 1) harness++; }
  gui_hl_stop();
  printf("summary: top-down(HeartCore形) FAIL=%d/%d, bottom-up対照 FAIL=%d/%d, top-down+ySrc=top FAIL=%d/%d, harness異常=%d\n", fail_td, NCASE, fail_bu, NCASE, naive_fail, NCASE, harness);
  if (harness || fail_bu) return 1;       /* 対照が壊れている = プローブ自体が信用できない */
  return fail_td ? 2 : 0;
}
