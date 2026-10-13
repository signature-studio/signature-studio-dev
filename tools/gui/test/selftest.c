/* selftest.c — gui shim の native 単体テスト (headless host + gcc)。1 コマンド: bash tools/gui/test/selftest.sh */
#define _GNU_SOURCE
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#include "gui_api.h"
#include "gui_internal.h"
#include "gui_headless.h"
#include "gui_simd.h"

extern GuiShared *gui_shared_native(void);
static int g_pass, g_fail;
#define CHK(c, ...) do { if (c) g_pass++; else { g_fail++; printf("  FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)
#define SECTION(s) printf("[selftest] %s\n", s)

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

/* ---- テスト用 wndproc: 受けたメッセージを記録 ---- */
static uint32_t g_log[256]; static int g_nlog; static int64_t g_lastw, g_lastl; static int64_t g_lastmsg_l[256];
static int g_paint_mode; static int g_erase_default;
static void rec(uint32_t m, int64_t l) { if (g_nlog < 256) { g_lastmsg_l[g_nlog] = l; g_log[g_nlog++] = m; } }
static int find_msg(uint32_t m, int from) { for (int i = from; i < g_nlog; i++) if (g_log[i] == m) return i; return -1; }
static int64_t tproc(int64_t h, int64_t m, int64_t w, int64_t l) {
  if (m != WM_SETCURSOR && m != WM_NCHITTEST && m != WM_GETMINMAXINFO) rec((uint32_t)m, l);
  g_lastw = w; g_lastl = l;
  switch ((uint32_t)m) {
    case WM_PAINT: {
      WPAINTSTRUCT ps; int64_t dc = BeginPaint(h, (int64_t)(uintptr_t)&ps);
      WRECT r = { 5, 5, 25, 25 };
      int64_t br = CreateSolidBrush(0x0000FF);  /* COLORREF 赤 */
      FillRect(dc, (int64_t)(uintptr_t)&r, br); DeleteObject(br);
      EndPaint(h, (int64_t)(uintptr_t)&ps);
      return 0;
    }
    case WM_USER + 9: return 4242;
  }
  return DefWindowProcA(h, m, w, l);
}
static int64_t reg(const char *name, uint32_t style, uint64_t bgbrush) {
  WWNDCLASS wc; memset(&wc, 0, sizeof wc);
  wc.style = style; wc.lpfnWndProc = (uint64_t)(uintptr_t)tproc; wc.lpszClassName = (uint64_t)(uintptr_t)name; wc.hbrBackground = bgbrush;
  return RegisterClassA((int64_t)(uintptr_t)&wc);
}
static int pump_until(uint32_t msgid, int ms_budget) {  /* GetMessage で msgid が来るまで dispatch */
  WMSG m; uint32_t t0 = gui_now_ms();
  while (gui_now_ms() - t0 < (uint32_t)ms_budget) {
    if (!PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE)) { gui_futex_wait(&gui_shared_native()->doorbell, gui_shared_native()->doorbell, 5); continue; }
    int hit = m.message == msgid;
    DispatchMessageA((int64_t)(uintptr_t)&m);
    if (hit) return 1;
  }
  return 0;
}
static void pump_idle(void) { WMSG m; while (PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE)) { TranslateMessage((int64_t)(uintptr_t)&m); DispatchMessageA((int64_t)(uintptr_t)&m); } }

static void *poster(void *a) {
  int64_t h = (int64_t)(intptr_t)a;
  PostMessageA(h, WM_USER + 3, 33, 44);
  int64_t r = SendMessageA(h, WM_USER + 9, 0, 0);   /* GUI スレッドが pump している間に同期完了 */
  g_lastl = r;
  return (void *)(intptr_t)(r == 4242);
}

/* icall hook (m11_icall 相当): lpfnWndProc/コールバックは「呼べない VA 整数」で、hook が解決・呼出する */
static int g_hook_calls, g_enum_hits; static uint64_t g_hook_last;
static uint64_t ihook(uint64_t t, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3) {
  g_hook_calls++; g_hook_last = t;
  if (t == 0x20000123ull) return (uint64_t)tproc((int64_t)a0, (int64_t)a1, (int64_t)a2, (int64_t)a3);
  if (t == 0x20000124ull) { g_enum_hits++; return 1; }
  return 0;
}

static uint32_t rgb(int r, int g, int b) { return (uint32_t)(r << 16 | g << 8 | b); }
static uint32_t cref(int r, int g, int b) { return (uint32_t)(r | g << 8 | b << 16); }

#include "selftest_p1.inc"
#include "selftest_gui5.inc"
#include "selftest_fd.inc"
#include "selftest_help.inc"

int main(void) {
  gui_hl_start(640, 480, 1);
  GuiShared *S = gui_shared_native();

  SECTION("window / class / creation messages");
  CHK(reg("T1", 0, 6) != 0, "RegisterClass T1");
  CHK(reg("T1", 0, 6) == 0, "duplicate RegisterClass must fail");
  int64_t h = CreateWindowExA(0, (int64_t)(uintptr_t)"T1", (int64_t)(uintptr_t)"w1", WS_POPUP | WS_VISIBLE, 10, 20, 100, 80, 0, 0, 0x400000, 0);
  CHK(h != 0, "CreateWindowEx");
  CHK(IsWindow(h) && IsWindowVisible(h), "visible");
  int a = find_msg(WM_NCCREATE, 0), b = find_msg(WM_CREATE, 0), c = find_msg(WM_SIZE, 0), d = find_msg(WM_ACTIVATE, 0), e = find_msg(WM_SETFOCUS, 0);
  CHK(a == 0 && b > a && c > b && d > c && e > d, "creation order NCCREATE=%d CREATE=%d SIZE=%d ACTIVATE=%d SETFOCUS=%d", a, b, c, d, e);
  CHK(GetActiveWindow() == h && GetFocus() == h, "active/focus");
  WRECT rc; GetClientRect(h, (int64_t)(uintptr_t)&rc);
  CHK(rc.right == 100 && rc.bottom == 80, "client rect");
  GetWindowRect(h, (int64_t)(uintptr_t)&rc);
  CHK(rc.left == 10 && rc.top == 20 && rc.right == 110, "window rect");
  WPOINT p = { 3, 4 }; ClientToScreen(h, (int64_t)(uintptr_t)&p);
  CHK(p.x == 13 && p.y == 24, "ClientToScreen");

  SECTION("post/peek order, WM_PAINT + paint to surface");
  g_nlog = 0;
  PostMessageA(h, WM_USER + 1, 1, 2); PostMessageA(h, WM_USER + 2, 3, 4);
  WMSG m;
  CHK(PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_NOREMOVE) && m.message == WM_USER + 1, "peek noremove");
  CHK(PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE) && m.message == WM_USER + 1 && m.wParam == 1 && m.lParam == 2, "FIFO 1");
  DispatchMessageA((int64_t)(uintptr_t)&m);
  CHK(PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE) && m.message == WM_USER + 2, "FIFO 2");
  CHK(PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE) && m.message == WM_PAINT, "WM_PAINT after posted (initial invalidate)");
  DispatchMessageA((int64_t)(uintptr_t)&m);
  flush_wait();
  CHK(desk(10 + 5, 20 + 5) == rgb(255, 0, 0), "painted red at (15,25): %06x", desk(15, 25));
  CHK(desk(10 + 24, 20 + 24) == rgb(255, 0, 0) && desk(10 + 25, 20 + 25) != rgb(255, 0, 0), "FillRect right/bottom exclusive");
  CHK(desk(10 + 50, 20 + 50) == rgb(255, 255, 255), "WM_ERASEBKGND via DefWindowProc class brush (COLOR_WINDOW): %06x", desk(60, 70));
  CHK(!PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE), "queue empty after paint validated");

  SECTION("seqlock wseq (GUI-4): 描画で奇数, flush で偶数");
  {
    CHK((S->surf[0].wseq & 1) == 0, "wseq even after flush: %u", S->surf[0].wseq);
    uint32_t w0 = S->surf[0].wseq;
    int64_t sdc = GetDC(h); WRECT sr = { 60, 60, 70, 70 };
    int64_t sbr = CreateSolidBrush(0x00FF00); FillRect(sdc, (int64_t)(uintptr_t)&sr, sbr); DeleteObject(sbr);
    CHK(S->surf[0].wseq == w0 + 1 && (S->surf[0].wseq & 1), "wseq odd after window DC draw (before flush): %u -> %u", w0, S->surf[0].wseq);
    GdiFlush();
    CHK(S->surf[0].wseq == w0 + 2 && !(S->surf[0].wseq & 1), "wseq even again after flush (+2 per frame): %u", S->surf[0].wseq);
    ReleaseDC(h, sdc);
    flush_wait();
    CHK(S->surf[0].wseq == w0 + 2, "no spurious bump without drawing: %u", S->surf[0].wseq);
    CHK(desk(10 + 65, 20 + 65) == rgb(0, 255, 0), "seqlock does not alter pixels: %06x", desk(75, 85));
  }

  SECTION("timers");
  g_nlog = 0;
  CHK(SetTimer(h, 7, 15, 0) == 7, "SetTimer returns id");
  CHK(pump_until(WM_TIMER, 2000) && g_lastw == 7, "WM_TIMER wParam=7");
  CHK(KillTimer(h, 7) == 1 && KillTimer(h, 7) == 0, "KillTimer");

  SECTION("input routing: hit-test, child windows, capture, cursor");
  int64_t ch = CreateWindowExA(0, (int64_t)(uintptr_t)"T1", 0, WS_CHILD | WS_VISIBLE, 50, 10, 20, 20, h, 99, 0x400000, 0);
  CHK(ch != 0 && GetParent(ch) == h, "child window");
  pump_idle(); g_nlog = 0;
  gui_hl_input(GUI_IN_MOUSE_DOWN, 0, 30, 40, 0, 0);  /* desktop (30,40) -> client (20,20) of h */
  pump_until(WM_LBUTTONDOWN, 1000);
  CHK((g_lastl & 0xFFFF) == 20 && ((g_lastl >> 16) & 0xFFFF) == 20, "LBUTTONDOWN client coords (20,20): l=%llx", (long long)g_lastl);
  gui_hl_input(GUI_IN_MOUSE_UP, 0, 30, 40, 0, 0); pump_until(WM_LBUTTONUP, 1000);
  g_nlog = 0;
  gui_hl_input(GUI_IN_MOUSE_DOWN, 0, 10 + 55, 20 + 15, 0, 0);  /* child (50,10)+(5,5) */
  pump_until(WM_LBUTTONDOWN, 1000);
  CHK((g_lastl & 0xFFFF) == 5 && ((g_lastl >> 16) & 0xFFFF) == 5, "child hit client coords (5,5): l=%llx", (long long)g_lastl);
  gui_hl_input(GUI_IN_MOUSE_UP, 0, 65, 35, 0, 0); pump_until(WM_LBUTTONUP, 1000);
  CHK(SetCapture(h) == 0 && GetCapture() == h, "SetCapture");
  gui_hl_input(GUI_IN_MOUSE_MOVE, 0, 500, 400, 0, 0);
  CHK(pump_until(WM_MOUSEMOVE, 1000), "captured mousemove outside window delivered");
  CHK((int16_t)(g_lastl & 0xFFFF) == 490 && (int16_t)((g_lastl >> 16) & 0xFFFF) == 380, "captured coords relative (490,380): %lld,%lld", (long long)(int16_t)(g_lastl & 0xFFFF), (long long)(int16_t)(g_lastl >> 16));
  WPOINT cp; GetCursorPos((int64_t)(uintptr_t)&cp);
  CHK(cp.x == 500 && cp.y == 400, "GetCursorPos");
  ScreenToClient(h, (int64_t)(uintptr_t)&cp);
  CHK(cp.x == 490 && cp.y == 380, "ScreenToClient");
  ReleaseCapture();
  CHK(GetCapture() == 0, "ReleaseCapture");
  CHK(WindowFromPoint(((int64_t)35 << 32) | 65) == ch, "WindowFromPoint(65,35) = child (%llx vs %llx)", (long long)WindowFromPoint(((int64_t)35 << 32) | 65), (long long)ch);

  SECTION("keyboard");
  g_nlog = 0;
  gui_hl_input(GUI_IN_KEY_DOWN, 0, 0, 0, 0x41, 0); gui_hl_input(GUI_IN_CHAR, 0, 0, 0, 'A', 0); gui_hl_input(GUI_IN_KEY_UP, 0, 0, 0, 0x41, 0);
  pump_until(WM_KEYUP, 1000);
  int kd = find_msg(WM_KEYDOWN, 0), ca = find_msg(WM_CHAR, 0), ku = find_msg(WM_KEYUP, 0);
  CHK(kd >= 0 && ca > kd && ku > ca, "KEYDOWN<CHAR<KEYUP order %d %d %d", kd, ca, ku);
  CHK(GetKeyState(0x41) == 0, "key released state");

  SECTION("GDI: memory DC / DIB section / primitives");
  int64_t memdc = CreateCompatibleDC(0);
  WBMIH bi; memset(&bi, 0, sizeof bi); bi.biSize = 40; bi.biWidth = 16; bi.biHeight = -16; bi.biPlanes = 1; bi.biBitCount = 32;
  uint64_t bitsp = 0;
  int64_t dib = CreateDIBSection(0, (int64_t)(uintptr_t)&bi, 0, (int64_t)(uintptr_t)&bitsp, 0, 0);
  CHK(dib != 0 && bitsp != 0, "CreateDIBSection");
  uint32_t *bits = (uint32_t *)(uintptr_t)bitsp;
  int64_t oldb = SelectObject(memdc, dib);
  CHK(oldb != 0, "SelectObject bitmap returns default");
  WRECT all = { 0, 0, 16, 16 };
  int64_t brb = CreateSolidBrush(cref(10, 20, 30));
  FillRect(memdc, (int64_t)(uintptr_t)&all, brb);
  CHK((bits[0] & 0xFFFFFF) == rgb(10, 20, 30) && (bits[255] & 0xFFFFFF) == rgb(10, 20, 30), "FillRect into DIB (BGRA)");
  bits[3 * 16 + 4] = 0xFF112233;
  CHK(GetPixel(memdc, 4, 3) == cref(0x11, 0x22, 0x33), "GetPixel reads direct DIB write");
  SetPixelV(memdc, 12, 2, cref(200, 100, 50));
  CHK((bits[2 * 16 + 12] & 0xFFFFFF) == rgb(200, 100, 50), "SetPixelV");
  int64_t pen = CreatePen(PS_SOLID, 1, cref(255, 255, 255));
  SelectObject(memdc, pen);
  MoveToEx(memdc, 0, 15, 0); LineTo(memdc, 10, 15);
  CHK((bits[15 * 16 + 0] & 0xFFFFFF) == 0xFFFFFF && (bits[15 * 16 + 9] & 0xFFFFFF) == 0xFFFFFF && (bits[15 * 16 + 10] & 0xFFFFFF) == rgb(10, 20, 30), "LineTo excludes end point");
  MoveToEx(memdc, 0, 0, 0); LineTo(memdc, 8, 8);
  CHK((bits[4 * 16 + 4] & 0xFFFFFF) == 0xFFFFFF, "diagonal LineTo");
  SelectObject(memdc, GetStockObject(BLACK_PEN)); DeleteObject(pen);
  /* Rectangle: pen yellow, brush blue */
  int64_t p2 = CreatePen(PS_SOLID, 1, cref(255, 255, 0)), b2 = CreateSolidBrush(cref(0, 0, 255));
  SelectObject(memdc, p2); SelectObject(memdc, b2);
  Rectangle(memdc, 2, 9, 7, 14);
  CHK((bits[9 * 16 + 2] & 0xFFFFFF) == rgb(255, 255, 0) && (bits[13 * 16 + 6] & 0xFFFFFF) == rgb(255, 255, 0) && (bits[11 * 16 + 4] & 0xFFFFFF) == rgb(0, 0, 255), "Rectangle outline+fill");
  SelectObject(memdc, GetStockObject(BLACK_PEN)); SelectObject(memdc, GetStockObject(WHITE_BRUSH)); DeleteObject(p2); DeleteObject(b2);
  /* BitBlt memdc -> window DC */
  int64_t wdc = GetDC(h);
  CHK(wdc != 0, "GetDC");
  BitBlt(wdc, 60, 40, 16, 16, memdc, 0, 0, SRCCOPY);
  ReleaseDC(h, wdc); flush_wait();
  CHK(desk(10 + 60, 20 + 40 + 1) == rgb(10, 20, 30) && desk(10 + 60 + 12, 20 + 40 + 2) == rgb(200, 100, 50), "BitBlt memdc->window -> desktop");
  /* GetDC(NULL) = 画面 DC (#174: 実 FLEngine の unit 初期化が呼ぶ。以前は fail-fast) */
  {
    int64_t sdc0 = GetDC(0);
    CHK(sdc0 != 0, "GetDC(NULL) screen DC");
    CHK(GetDeviceCaps(sdc0, HORZRES) > 0 && GetDeviceCaps(sdc0, BITSPIXEL) == 32, "screen DC GetDeviceCaps");
    int64_t cb0 = CreateCompatibleBitmap(sdc0, 8, 8);
    CHK(cb0 != 0, "CreateCompatibleBitmap(screen DC)");
    CHK(ReleaseDC(0, sdc0) == 1, "ReleaseDC(NULL, screen DC)");
    CHK(DeleteDC(sdc0) == 0, "released screen DC handle is invalid (double release rejected)");
    DeleteObject(cb0);
  }
  /* StretchBlt 2x + flip */
  wdc = GetDC(h);
  StretchBlt(wdc, 0, 0, 32, 32, memdc, 0, 0, 16, 16, SRCCOPY);
  StretchBlt(wdc, 32, 32, 32, -32, memdc, 0, 0, 16, 16, SRCCOPY);  /* 垂直反転 : dest y 0..31 */
  ReleaseDC(h, wdc); flush_wait();
  CHK(desk(10 + 24, 20 + 4) == rgb(200, 100, 50) && desk(10 + 25, 20 + 5) == rgb(200, 100, 50) && desk(10 + 26, 20 + 4) == rgb(10, 20, 30), "StretchBlt 2x nearest (pixel(12,2) -> 2x2 block)");
  /* flip check: src row 15 (white line) appears at top of the flipped dest */
  CHK(desk(10 + 32 + 0, 20 + 0) == 0xFFFFFF, "vertical flip puts last src row at top: %06x", desk(42, 20));
  /* clip: IntersectClipRect restricts fill */
  wdc = GetDC(h);
  IntersectClipRect(wdc, 70, 50, 80, 60);
  WRECT big = { 60, 40, 100, 80 }; int64_t gb = CreateSolidBrush(cref(0, 255, 0));
  FillRect(wdc, (int64_t)(uintptr_t)&big, gb); DeleteObject(gb);
  ReleaseDC(h, wdc); flush_wait();
  CHK(desk(10 + 75, 20 + 55) == rgb(0, 255, 0) && desk(10 + 65, 20 + 45) != rgb(0, 255, 0) && desk(10 + 85, 20 + 65) != rgb(0, 255, 0), "IntersectClipRect");
  /* region clip */
  wdc = GetDC(h);
  int64_t r1 = CreateRectRgn(0, 60, 10, 70), r2 = CreateRectRgn(20, 60, 30, 70), ru = CreateRectRgn(0, 0, 0, 0);
  CHK(CombineRgn(ru, r1, r2, RGN_OR) == COMPLEXREGION, "CombineRgn OR -> complex");
  SelectClipRgn(wdc, ru);
  WRECT bar = { 0, 60, 40, 70 }; gb = CreateSolidBrush(cref(1, 2, 3)); FillRect(wdc, (int64_t)(uintptr_t)&bar, gb); DeleteObject(gb);
  ReleaseDC(h, wdc); flush_wait();
  CHK(desk(10 + 5, 20 + 65) == rgb(1, 2, 3) && desk(10 + 25, 20 + 65) == rgb(1, 2, 3) && desk(10 + 15, 20 + 65) != rgb(1, 2, 3), "SelectClipRgn complex region");
  /* SaveDC/RestoreDC + SetWindowOrgEx */
  wdc = GetDC(h);
  int64_t sv = SaveDC(wdc); SetBkColor(wdc, cref(9, 9, 9)); SetWindowOrgEx(wdc, -50, -50, 0);
  WRECT sm = { 0, 0, 4, 4 }; gb = CreateSolidBrush(cref(77, 88, 99)); FillRect(wdc, (int64_t)(uintptr_t)&sm, gb); DeleteObject(gb);
  CHK(RestoreDC(wdc, sv) == 1 && GetBkColor(wdc) == 0xFFFFFF, "SaveDC/RestoreDC restores bk color");
  ReleaseDC(h, wdc); flush_wait();
  CHK(desk(10 + 50, 20 + 50) == rgb(77, 88, 99), "SetWindowOrgEx(-50,-50) shifts drawing: %06x", desk(60, 70));
  /* StretchDIBits bottom-up */
  uint32_t src[4] = { 0xFF0000FF, 0xFF0000FF, 0xFF00FF00, 0xFF00FF00 };  /* bottom-up : row0=bottom(blue-ish 0000FF), row1=top(green) */
  WBMIH sb; memset(&sb, 0, sizeof sb); sb.biSize = 40; sb.biWidth = 2; sb.biHeight = 2; sb.biPlanes = 1; sb.biBitCount = 32;
  wdc = GetDC(h);
  StretchDIBits(wdc, 0, 0, 4, 4, 0, 0, 2, 2, (int64_t)(uintptr_t)src, (int64_t)(uintptr_t)&sb, 0, SRCCOPY);
  ReleaseDC(h, wdc); flush_wait();
  CHK(desk(10 + 0, 20 + 0) == rgb(0, 255, 0) && desk(10 + 3, 20 + 3) == rgb(0, 0, 255), "StretchDIBits bottom-up orientation (top row = last data row): %06x %06x", desk(10, 20), desk(13, 23));
  /* AlphaBlend 50% constant */
  { WBMIH ab; memset(&ab, 0, sizeof ab); ab.biSize = 40; ab.biWidth = 2; ab.biHeight = -2; ab.biPlanes = 1; ab.biBitCount = 32; uint64_t bp2 = 0;
    int64_t d2 = CreateDIBSection(0, (int64_t)(uintptr_t)&ab, 0, (int64_t)(uintptr_t)&bp2, 0, 0); int64_t m2 = CreateCompatibleDC(0); SelectObject(m2, d2);
    uint32_t *b2p = (uint32_t *)(uintptr_t)bp2; for (int i = 0; i < 4; i++) b2p[i] = 0xFFFFFFFF;
    uint32_t *bd = bits; for (int i = 0; i < 256; i++) bd[i] = 0xFF000000;
    AlphaBlend(memdc, 0, 0, 2, 2, m2, 0, 0, 2, 2, (128u << 16));
    CHK((bd[0] & 0xFF) >= 127 && (bd[0] & 0xFF) <= 129, "AlphaBlend 50%% constant: %u", bd[0] & 0xFF);
    DeleteDC(m2); DeleteObject(d2); }
  /* text: 'A' glyph pixel check against font table */
  wdc = GetDC(h);
  SetBkMode(wdc, TRANSPARENT_); SetTextColor(wdc, cref(0, 0, 0));
  TextOutA(wdc, 0, 50, (int64_t)(uintptr_t)"A", 1);
  ReleaseDC(h, wdc); flush_wait();
  { int on = 0; for (int y = 0; y < 8; y++) for (int x = 0; x < 8; x++) if (desk(10 + x, 20 + 50 + y) == 0x000000) on++;
    CHK(on > 8 && on < 40, "TextOutA draws 'A' (%d lit pixels)", on); }
  WSIZE sz; GetTextExtentPoint32A(memdc, (int64_t)(uintptr_t)"hello", 5, (int64_t)(uintptr_t)&sz);
  CHK(sz.cx == 40 && sz.cy == 8, "GetTextExtentPoint32");
  SelectObject(memdc, oldb); DeleteObject(dib); DeleteObject(brb); DeleteDC(memdc);

  SECTION("z-order across top-level windows");
  int64_t hb = CreateWindowExA(0, (int64_t)(uintptr_t)"T1", 0, WS_POPUP | WS_VISIBLE, 60, 60, 100, 80, 0, 0, 0x400000, 0);  /* h(10..110,20..100) と重なる */
  pump_idle(); flush_wait();
  CHK(GetActiveWindow() == hb, "new window activated");
  CHK(desk(10 + 90, 20 + 70) == rgb(255, 255, 255) || desk(100, 90) == rgb(255, 255, 255) || desk(65, 65) == rgb(255, 0, 0), "upper window composited over lower (%06x)", desk(65, 65));
  /* 下の h を再描画 → 上の hb の領域は維持される */
  int64_t wdc2 = GetDC(h); WRECT whole = { 0, 0, 100, 80 }; int64_t yb = CreateSolidBrush(cref(250, 250, 0)); FillRect(wdc2, (int64_t)(uintptr_t)&whole, yb); DeleteObject(yb);
  ReleaseDC(h, wdc2); flush_wait();
  CHK(desk(20, 30) == rgb(250, 250, 0), "lower window repaint visible where not covered");
  CHK(desk(80, 80) != rgb(250, 250, 0), "lower window repaint does not overwrite higher window (%06x)", desk(80, 80));
  DestroyWindow(hb); pump_idle(); flush_wait();
  CHK(!IsWindow(hb), "DestroyWindow");
  CHK(GetActiveWindow() == h, "activation falls back to remaining window");
  CHK(desk(80, 80) == rgb(250, 250, 0), "lower window visible after upper destroyed (%06x)", desk(80, 80));

  SECTION("window props / class info / enumeration / scroll / reparent");
  { uint16_t pn[] = { 'M', 'y', 'P', 0 };
    CHK(SetPropW(h, (int64_t)(uintptr_t)pn, 0x1234) == 1 && GetPropW(h, (int64_t)(uintptr_t)pn) == 0x1234, "SetProp/GetProp");
    CHK(RemovePropW(h, (int64_t)(uintptr_t)pn) == 0x1234 && GetPropW(h, (int64_t)(uintptr_t)pn) == 0, "RemoveProp");
    uint16_t cn[16]; int n = GetClassNameW(h, (int64_t)(uintptr_t)cn, 16); CHK(n == 2 && cn[0] == 'T' && cn[1] == '1', "GetClassNameW");
    uint16_t t1[] = { 'T', '1', 0 };
    CHK(FindWindowW((int64_t)(uintptr_t)t1, 0) != 0, "FindWindowW by class"); }
  CHK(GetDlgItem(h, 99) == ch, "GetDlgItem (child id)");
  CHK(GetTopWindow(h) == ch, "GetTopWindow");
  { int64_t c2 = CreateWindowExA(0, (int64_t)(uintptr_t)"T1", 0, WS_CHILD | WS_VISIBLE, 0, 0, 5, 5, h, 100, 0x400000, 0);
    CHK(GetWindow(c2, 3) == 0 && GetWindow(ch, 3) == c2, "z-order: later child is on top (GW_HWNDPREV of ch = c2)");
    CHK(GetWindow(h, 5) == c2, "GW_CHILD = topmost child");
    int64_t c3 = CreateWindowExA(0, (int64_t)(uintptr_t)"T1", 0, WS_CHILD | WS_VISIBLE, 0, 0, 5, 5, ch, 7, 0x400000, 0);
    CHK(SetParent(c3, c2) == (int64_t)ch && GetParent(c3) == c2, "SetParent child->child");
    DestroyWindow(c2); CHK(!IsWindow(c3), "destroying parent destroys children"); }
  { wdc = GetDC(h);
    int64_t gb2 = CreateSolidBrush(cref(5, 6, 7)); WRECT zr = { 0, 0, 20, 10 }; FillRect(wdc, (int64_t)(uintptr_t)&zr, gb2); DeleteObject(gb2); ReleaseDC(h, wdc);
    WRECT area = { 0, 0, 30, 30 }; ScrollWindow(h, 10, 0, (int64_t)(uintptr_t)&area, 0);
    flush_wait();
    CHK(desk(10 + 10, 20 + 5) == rgb(5, 6, 7) && desk(10 + 29, 20 + 5) == rgb(5, 6, 7), "ScrollWindow moves pixels right by 10: %06x", desk(20, 25));
    WRECT ur; GetUpdateRect(h, (int64_t)(uintptr_t)&ur, 0); CHK(ur.left == 0 && ur.right >= 10, "ScrollWindow invalidates exposed strip (%d..%d)", ur.left, ur.right); }
  { struct { int64_t hh; } enumctx = { 0 }; (void)enumctx; }

  SECTION("icall hook (m11_icall 経由のコールバック解決)");
  gui_set_icall_hook(ihook);
  { WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = 0x20000123ull; wc.lpszClassName = (uint64_t)(uintptr_t)"THK";
    CHK(RegisterClassA((int64_t)(uintptr_t)&wc) != 0, "RegisterClass with non-callable VA as lpfnWndProc");
    g_hook_calls = 0; g_nlog = 0;
    int64_t hk = CreateWindowExA(0, (int64_t)(uintptr_t)"THK", (int64_t)(uintptr_t)"hk", WS_POPUP, 300, 300, 40, 40, 0, 0, 0x400000, 0);
    CHK(hk != 0 && g_hook_calls >= 3 && find_msg(WM_NCCREATE, 0) == 0 && find_msg(WM_CREATE, 0) > 0, "creation messages delivered through hook (calls=%d)", g_hook_calls);
    CHK(SendMessageA(hk, WM_USER + 9, 0, 0) == 4242 && g_hook_last == 0x20000123ull, "SendMessage -> hook(target=VA) -> 4242");
    CHK(CallWindowProcA(0x20000123ull, hk, WM_USER + 9, 0, 0) == 4242, "CallWindowProc through hook");
    CHK(CreateWindowExA(0, (int64_t)(uintptr_t)"THK", (int64_t)(uintptr_t)"c", WS_CHILD | WS_VISIBLE, 0, 0, 5, 5, hk, 0, 0x400000, 0) != 0
        && EnumChildWindows(hk, 0x20000124ull, 0) == 1 && g_enum_hits == 1, "2-arg callback (EnumChildWindows) through hook (hits=%d)", g_enum_hits);
    DestroyWindow(hk); }
  gui_set_icall_hook(NULL);

  run_p1(h);
  run_gui5(h);

  SECTION("SendMessage / cross-thread");
  CHK(SendMessageA(h, WM_USER + 9, 0, 0) == 4242, "SendMessage direct");
  pthread_t th; pthread_create(&th, NULL, poster, (void *)(intptr_t)h);
  g_nlog = 0;
  int got3 = 0;
  { uint32_t t0 = gui_now_ms(); WMSG mm; void *res = NULL;
    for (;;) {
      if (PeekMessageA((int64_t)(uintptr_t)&mm, 0, 0, 0, PM_REMOVE)) { if (mm.message == WM_USER + 3) got3 = 1; DispatchMessageA((int64_t)(uintptr_t)&mm); }
      else gui_futex_wait(&S->doorbell, S->doorbell, 5);
      if (got3 && g_lastl == 4242) break;
      if (gui_now_ms() - t0 > 3000) break;
    }
    pthread_join(th, &res);
    CHK(got3 && res == (void *)1, "cross-thread PostMessage + sync SendMessage (got3=%d res=%p)", got3, res); }

  run_fd_bounds();
  run_help_wiring();

  SECTION("quit / destroy messages");
  g_nlog = 0;
  DestroyWindow(h);
  int dd = find_msg(WM_DESTROY, 0), nd = find_msg(WM_NCDESTROY, 0);
  CHK(dd >= 0 && nd > dd && !IsWindow(h), "WM_DESTROY<WM_NCDESTROY, handle invalid");
  PostQuitMessage(7);
  CHK(GetMessageA((int64_t)(uintptr_t)&m, 0, 0, 0) == 0 && m.message == WM_QUIT && m.wParam == 7, "GetMessage returns 0 on WM_QUIT");

  SECTION("fail-fast on unimplemented API");
  int pfd[2]; pipe(pfd);
  pid_t pid = fork();
  if (pid == 0) { dup2(pfd[1], 2); close(pfd[0]); Ellipse(0, 0, 0, 0, 0); _exit(0); }
  close(pfd[1]);
  char buf[512] = {0}; ssize_t nr = read(pfd[0], buf, sizeof buf - 1); (void)nr;
  int st = 0; waitpid(pid, &st, 0);
  CHK(WIFSIGNALED(st) && WTERMSIG(st) == SIGABRT, "unimplemented API aborts");
  CHK(strstr(buf, "FAIL-FAST: unimplemented Win32 API: Ellipse") != NULL, "fail-fast names the API: %s", buf);

  gui_hl_stop();
  printf("[selftest] %d passed, %d failed\n", g_pass, g_fail);
  return g_fail ? 1 : 0;
}
