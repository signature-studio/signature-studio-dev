/*
 * gui_nc_app.c — GUI-7 (#183) テスト PE: popup / tooltip surface・非クライアント (NC) 描画を含む Win32 アプリ。
 *   mingw-w64 で PE32+ にビルド → RetDec で lift → shim にリンク (gui_app.c と同じ経路)。
 * 窓: popup (90,50) 80x50 青 / main (10,10) 130x113 WS_POPUP|WS_CAPTION|WS_THICKFRAME (client 120x80, 枠 5px・caption 23px) /
 *     tooltip (70,40) 60x14 薄黄 WS_EX_TOPMOST|NOACTIVATE|TRANSPARENT (WM_NCHITTEST = HTTRANSPARENT)。
 * 作成順 popup -> main -> tooltip により z 順は popup < main < tooltip。期待画像は golden/gen_golden.py の NC シーン。
 * 制約 (lifter 対策): CRT 無し (freestanding)・構造体は static 大域に置く (gui_app.c と同じ)。
 */
#include <windows.h>

#define DW 200
#define DH 140

static WNDCLASSA wc_pop, wc_main, wc_tip;
static MSG msg;
static PAINTSTRUCT ps;
static RECT rc;
static int ticks;

static void say(const char *s) { OutputDebugStringA(s); }

static void fill_client(HWND h, COLORREF col) {
  HBRUSH br;
  BeginPaint(h, &ps);
  rc.left = 0; rc.top = 0; rc.right = 4000; rc.bottom = 4000;
  br = CreateSolidBrush(col);
  FillRect(ps.hdc, &rc, br);
  DeleteObject(br);
  EndPaint(h, &ps);
}

static LRESULT CALLBACK PopProc(HWND h, UINT m, WPARAM w, LPARAM l) {
  if (m == WM_PAINT) { fill_client(h, RGB(30, 60, 200)); return 0; }
  return DefWindowProcA(h, m, w, l);
}

static LRESULT CALLBACK MainProc(HWND h, UINT m, WPARAM w, LPARAM l) {
  switch (m) {
  case WM_CREATE:
    SetTimer(h, 1, 20, NULL);
    return 0;
  case WM_PAINT:
    fill_client(h, RGB(50, 50, 60));
    say("nc: paint");
    return 0;
  case WM_TIMER:
    ticks++;
    if (ticks == 3) {
      KillTimer(h, 1);
      say("nc: timer-done");
    }
    return 0;
  case WM_DESTROY:
    PostQuitMessage(0);
    return 0;
  }
  return DefWindowProcA(h, m, w, l);
}

static LRESULT CALLBACK TipProc(HWND h, UINT m, WPARAM w, LPARAM l) {
  if (m == WM_PAINT) { fill_client(h, RGB(255, 255, 225)); return 0; }
  if (m == WM_NCHITTEST) return HTTRANSPARENT;
  return DefWindowProcA(h, m, w, l);
}

static int WINAPI WinMain_(HINSTANCE hi) {
  HWND hp, hm, ht;
  wc_pop.lpfnWndProc = PopProc;
  wc_pop.hInstance = hi;
  wc_pop.lpszClassName = "NCpop";
  RegisterClassA(&wc_pop);
  wc_main.lpfnWndProc = MainProc;
  wc_main.hInstance = hi;
  wc_main.lpszClassName = "NCmain";
  RegisterClassA(&wc_main);
  wc_tip.lpfnWndProc = TipProc;
  wc_tip.hInstance = hi;
  wc_tip.lpszClassName = "NCtip";
  RegisterClassA(&wc_tip);
#ifdef NC_PE_FAULT_ZORDER
  /* 欠陥: tooltip を TOPMOST にせず main より先に作る -> main の下に隠れる (z 順欠陥のネガコン) */
  ht = CreateWindowExA(WS_EX_NOACTIVATE | WS_EX_TRANSPARENT, "NCtip", "", WS_POPUP | WS_VISIBLE, 70, 40, 60, 14, NULL, NULL, hi, NULL);
  hp = CreateWindowExA(0, "NCpop", "", WS_POPUP | WS_VISIBLE, 90, 50, 80, 50, NULL, NULL, hi, NULL);
  hm = CreateWindowExA(0, "NCmain", "main", WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_VISIBLE, 10, 10, 130, 113, NULL, NULL, hi, NULL);
#else
  hp = CreateWindowExA(0, "NCpop", "", WS_POPUP | WS_VISIBLE, 90, 50, 80, 50, NULL, NULL, hi, NULL);
  hm = CreateWindowExA(0, "NCmain", "main", WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_VISIBLE, 10, 10, 130, 113, NULL, NULL, hi, NULL);
  ht = CreateWindowExA(WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT, "NCtip", "", WS_POPUP | WS_VISIBLE, 70, 40, 60, 14, NULL, NULL, hi, NULL);
#endif
  say("nc: created");
  while (GetMessageA(&msg, NULL, 0, 0)) {
    TranslateMessage(&msg);
    DispatchMessageA(&msg);
  }
  return (int)msg.wParam;
}

void entry(void) { ExitProcess(WinMain_(GetModuleHandleA(NULL))); }
