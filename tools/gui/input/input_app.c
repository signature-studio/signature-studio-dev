/* input_app.c — GUI-6 e2e 用ゲスト (RetDec 不要: shim API を直接呼ぶ C を emcc で wasm 化)。受けたメッセージを LOG へ "G6 ..." 形式で出す。
 * lpfnWndProc は wasm の関数表 index (小整数) ではなく疑似 VA を使い、gui_lift_fnmap で解決する (lift 済み PE と同じ経路)。 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "gui_internal.h"
#include "gui_api.h"
#define VA_WNDPROC 0x140001000ULL
typedef struct { int32_t x, y; uint64_t src; uint32_t id, flags, mask, time; uint64_t extra; uint32_t cx, cy; } TouchIn;
typedef struct { uint32_t cbSize, dwFlags, dwID, _p; uint64_t hwnd; int16_t px, py; uint32_t inst, seq; uint64_t args; uint32_t cbExtra, _q; } GestInfo;
#define L(...) do { char b[160]; snprintf(b, sizeof b, __VA_ARGS__); OutputDebugStringA((int64_t)(intptr_t)b); } while (0)
static int g_lock_drag;
static int64_t wndproc(int64_t h, int64_t m, int64_t w, int64_t l) {
  switch ((uint32_t)m) {
    case 0x100: case 0x104: { uint16_t c[4] = { 0 }; uint8_t st[256]; GetKeyboardState((int64_t)(intptr_t)st);
      int n = (int)ToUnicode(w, (l >> 16) & 0xFF, (int64_t)(intptr_t)st, (int64_t)(intptr_t)c, 4, 0);
      L("G6 KEYDOWN vk=%llx sc=%x ext=%d uni=%x n=%d", (long long)w, (unsigned)((l >> 16) & 0xFF), (int)((l >> 24) & 1), n ? c[0] : 0, n); return 0; }
    case 0x101: L("G6 KEYUP vk=%llx", (long long)w); return 0;
    case 0x102: L("G6 CHAR %llx", (long long)w); return 0;
    case 0x10D: L("G6 IME START"); return 0;
    case 0x10E: L("G6 IME END"); return 0;
    case 0x10F: { int64_t hc = ImmGetContext(h); uint16_t b[64]; int n;
      if (l & 0x8) { n = (int)ImmGetCompositionStringW(hc, 0x8, (int64_t)(intptr_t)b, sizeof b) / 2; char o[120] = { 0 }; int k = 0; for (int i = 0; i < n && k < 100; i++) k += snprintf(o + k, 20, "%04x", b[i]); L("G6 IME COMP n=%d u=%s cur=%d", n, o, (int)ImmGetCompositionStringW(hc, 0x80, 0, 0)); }
      if (l & 0x800) { n = (int)ImmGetCompositionStringW(hc, 0x800, (int64_t)(intptr_t)b, sizeof b) / 2; char o[120] = { 0 }; int k = 0; for (int i = 0; i < n && k < 100; i++) k += snprintf(o + k, 20, "%04x", b[i]); L("G6 IME RESULT n=%d u=%s", n, o); }
      ImmReleaseContext(h, hc); return 0; }
    case 0x240: { TouchIn t[10]; int n = (int)w; if (n > 10) n = 10; GetTouchInputInfo(l, w, (int64_t)(intptr_t)t, sizeof(TouchIn));
      for (int i = 0; i < n; i++) L("G6 TOUCH id=%u x=%d y=%d fl=%x", t[i].id, t[i].x / 100, t[i].y / 100, t[i].flags); CloseTouchInputHandle(l); return 0; }
    case 0x119: { GestInfo g; memset(&g, 0, sizeof g); g.cbSize = sizeof g; GetGestureInfo(l, (int64_t)(intptr_t)&g); L("G6 GESTURE id=%u fl=%u arg=%llu", g.dwID, g.dwFlags, (unsigned long long)g.args); CloseGestureInfoHandle(l); return 0; }
    case 0x201: L("G6 LBUTTONDOWN x=%d y=%d", (int)(l & 0xFFFF), (int)((l >> 16) & 0xFFFF)); g_lock_drag = 1; SetCapture(h); ShowCursor(0); return 0;
    case 0x202: L("G6 LBUTTONUP x=%d y=%d", (int)(l & 0xFFFF), (int)((l >> 16) & 0xFFFF)); if (g_lock_drag) { g_lock_drag = 0; ShowCursor(1); ReleaseCapture(); } return 0;
    case 0x200: if (g_lock_drag) { int32_t p[2]; GetCursorPos((int64_t)(intptr_t)p); L("G6 DRAGMOVE x=%d y=%d cur=%d,%d", (int)(int16_t)(l & 0xFFFF), (int)(int16_t)((l >> 16) & 0xFFFF), p[0], p[1]); } return 0;
    case 0x2: PostQuitMessage(0); return 0;
  }
  return DefWindowProcA(h, m, w, l);
}
const GuiFnMap gui_lift_fnmap[] = { { VA_WNDPROC, (void *)wndproc } };
const int gui_lift_fnmap_n = 1;
int64_t gui_lift_entry(void) {
  WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = VA_WNDPROC; wc.lpszClassName = (uint64_t)(uintptr_t)"G6APP"; wc.hbrBackground = 6;
  RegisterClassA((int64_t)(intptr_t)&wc);
  int64_t h = CreateWindowExA(0, (int64_t)(intptr_t)"G6APP", (int64_t)(intptr_t)"g6", 0x10000000 | (int)0x80000000, 0, 0, 320, 200, 0, 0, 0x400000, 0);
  RegisterTouchWindow(h, 0);
  uint32_t gc[3] = { 3, 1, 0 }; SetGestureConfig(h, 0, 1, (int64_t)(intptr_t)gc, 12);
  L("G6 READY layout=%llx", (long long)GetKeyboardLayout(0));
  WMSG m;
  while (GetMessageA((int64_t)(intptr_t)&m, 0, 0, 0)) { TranslateMessage((int64_t)(intptr_t)&m); DispatchMessageA((int64_t)(intptr_t)&m); }
  ExitProcess(0); return 0;
}
