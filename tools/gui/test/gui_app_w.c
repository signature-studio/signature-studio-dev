/*
 * gui_app_w.c — FL 非依存の Unicode (W 版) Win32 テストゲスト (mingw-w64 で PE32+ にビルド → RetDec → shim)
 *
 * 窓・メッセージ系は W 版だけを呼ぶ (A 版は 0)。VCL の起動列 (tools/startup/STARTUP.md S19〜S22) に倣う:
 *   RegisterClassW("TApplication") + 不可視 CreateWindowExW(WS_EX_TOOLWINDOW) → SetWindowLongPtrW(GWLP_WNDPROC)
 *   で subclass → SendMessageW → CallWindowProcW → 主窓 RegisterClassW + CreateWindowExW (WM_NCCREATE/WM_CREATE で
 *   CREATESTRUCTW を読む) → ShowWindow/UpdateWindow → PeekMessageW/DispatchMessageW (空のとき MsgWaitForMultipleObjectsEx)
 *   → WM_PAINT で BeginPaint/FillRect/DIB への書込み/BitBlt/ExtTextOutW(ASCII)/EndPaint → SetWindowTextW・GetWindowTextW
 *   で BMP の非 ASCII (U+3042) を往復 → ESC で DestroyWindow → PostQuitMessage → ExitProcess。
 * 制約 (lifter 対策): CRT 無し (freestanding)・構造体は static 大域・ループは手で書く (tools/gui/REPORT.md §4)。
 * 進捗は OutputDebugStringW で host に通知する (driver の同期に使う)。FL の素材・FL 由来の文字列は使わない。
 */
#include <windows.h>

#define GW 320
#define GH 200

static WNDCLASSW wcapp;
static WNDCLASSW wcmain;
static MSG msg;
static PAINTSTRUCT ps;
static RECT rc;
static BITMAPINFO bmi;
static HDC memdc;
static HBITMAP dib;
static unsigned int *bits;
static LONG_PTR oldproc;
static HWND happ;
static HWND hmain;
static WCHAR tbuf[32];
static WCHAR ltext[12];

static void say(const WCHAR *s) { OutputDebugStringW(s); }

static void render(void) {
  int x, y;
  HBRUSH br;
  rc.left = 0; rc.top = 0; rc.right = GW; rc.bottom = GH;
  br = CreateSolidBrush(RGB(24, 40, 56));
  FillRect(memdc, &rc, br);
  DeleteObject(br);
  for (y = 20; y < 60; y++)
    for (x = 0; x < 160; x++)
      bits[y * GW + x] = 0xFF000000u | ((unsigned int)(x * 3) << 16) | ((unsigned int)(200 - y) << 8) | 64u;
  rc.left = 180; rc.top = 20; rc.right = 300; rc.bottom = 70;
  br = CreateSolidBrush(RGB(230, 120, 20));
  FillRect(memdc, &rc, br);
  DeleteObject(br);
  SetBkMode(memdc, TRANSPARENT);
  SetTextColor(memdc, RGB(255, 255, 255));
  ExtTextOutW(memdc, 12, 100, 0, NULL, ltext, 12, NULL);
}

static LRESULT CALLBACK SubWndProc(HWND h, UINT m, WPARAM w, LPARAM l) {
  if (m == WM_USER + 1) say(L"w: subclass ok");
  return CallWindowProcW((WNDPROC)oldproc, h, m, w, l);
}

static LRESULT CALLBACK WndProc(HWND h, UINT m, WPARAM w, LPARAM l) {
  CREATESTRUCTW *cs;
  HDC hdc;
  switch (m) {
  case WM_NCCREATE:
    cs = (CREATESTRUCTW *)l;
    say(cs->cx == GW ? L"w: nccreate ok" : L"w: nccreate NG");
    return DefWindowProcW(h, m, w, l);
  case WM_CREATE:
    cs = (CREATESTRUCTW *)l;
    say(cs->cy == GH ? L"w: cs ok" : L"w: cs NG");
    bmi.bmiHeader.biSize = 40;
    bmi.bmiHeader.biWidth = GW;
    bmi.bmiHeader.biHeight = -GH;
    bmi.bmiHeader.biPlanes = 1;
    bmi.bmiHeader.biBitCount = 32;
    bmi.bmiHeader.biCompression = BI_RGB;
    dib = CreateDIBSection(NULL, &bmi, DIB_RGB_COLORS, (void **)&bits, NULL, 0);
    memdc = CreateCompatibleDC(NULL);
    SelectObject(memdc, dib);
    say(L"w: created");
    return 0;
  case WM_ERASEBKGND:
    return 1;
  case WM_PAINT:
    hdc = BeginPaint(h, &ps);
    render();
    BitBlt(hdc, 0, 0, GW, GH, memdc, 0, 0, SRCCOPY);
    EndPaint(h, &ps);
    say(L"w: paint");
    return 0;
  case WM_KEYDOWN:
    if (w == VK_ESCAPE) DestroyWindow(h);
    return 0;
  case WM_DESTROY:
    say(L"w: destroy");
    PostQuitMessage(0);
    return 0;
  }
  return DefWindowProcW(h, m, w, l);
}

static int WINAPI WinMain_(HINSTANCE hi) {
  HWND h;
  int i;
  wcapp.style = 0;
  wcapp.lpfnWndProc = WndProc;
  wcapp.cbClsExtra = 0;
  wcapp.cbWndExtra = 0;
  wcapp.hInstance = hi;
  wcapp.hIcon = NULL;
  wcapp.hCursor = NULL;
  wcapp.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
  wcapp.lpszMenuName = NULL;
  wcapp.lpszClassName = L"TApplication";
  RegisterClassW(&wcapp);
  happ = CreateWindowExW(WS_EX_TOOLWINDOW, L"TApplication", L"Application", WS_POPUP, 0, 0, 0, 0, NULL, NULL, hi, NULL);
  oldproc = SetWindowLongPtrW(happ, GWLP_WNDPROC, (LONG_PTR)SubWndProc);
  SendMessageW(happ, WM_USER + 1, 0, 0);

  wcmain.style = 0;
  wcmain.lpfnWndProc = WndProc;
  wcmain.cbClsExtra = 0;
  wcmain.cbWndExtra = 0;
  wcmain.hInstance = hi;
  wcmain.hIcon = NULL;
  wcmain.hCursor = NULL;
  wcmain.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
  wcmain.lpszMenuName = NULL;
  wcmain.lpszClassName = L"GuiPocW";
  RegisterClassW(&wcmain);
  hmain = CreateWindowExW(0, L"GuiPocW", L"Signature GUI PoC W", WS_POPUP | WS_VISIBLE, 0, 0, GW, GH, NULL, NULL, hi, NULL);
  if (hmain == NULL) return 1;
  ShowWindow(hmain, SW_SHOW);
  UpdateWindow(hmain);

  ltext[0] = 'W'; ltext[1] = 'i'; ltext[2] = 'd'; ltext[3] = 'e'; ltext[4] = ' ';
  ltext[5] = 'T'; ltext[6] = 'e'; ltext[7] = 'x'; ltext[8] = 't'; ltext[9] = ' ';
  ltext[10] = '4'; ltext[11] = '2';
  SetWindowTextW(hmain, L"Sig \x3042");
  i = GetWindowTextW(hmain, tbuf, 32);
  say((i == 5 && tbuf[4] == 0x3042 && tbuf[0] == 'S') ? L"w: roundtrip ok" : L"w: roundtrip NG");

  for (;;) {
    if (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
      if (msg.message == WM_QUIT) break;
      TranslateMessage(&msg);
      DispatchMessageW(&msg);
    } else {
      MsgWaitForMultipleObjectsEx(0, NULL, 10, QS_ALLINPUT, 0);
    }
  }
  return (int)msg.wParam;
}

void entry(void) { ExitProcess(WinMain_(GetModuleHandleW(NULL))); }
