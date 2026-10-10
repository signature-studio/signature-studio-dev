/*
 * gui_app.c — Win32 GUI PoC テストアプリ (mingw-w64 で PE32+ にビルド → RetDec で lift → shim にリンク)
 *
 * 機能: クラス登録/ウィンドウ生成/メッセージループ/タイマ/マウスキャプチャ+ドラッグ/キー入力/
 *       メモリDC+DIBSection への直接書込/FillRect/Rectangle/LineTo/TextOut/StretchDIBits/BitBlt/WM_PAINT
 * 制約 (lifter 対策): CRT 無し (freestanding)・構造体は static 大域に置く (RetDec は stack 上の構造体
 *       フィールド store を落とすため; REPORT.md §lift 知見)。
 * 進捗は OutputDebugStringA で host に通知 (E2E ドライバが同期に使う)。
 */
#include <windows.h>

#define W 320
#define H 200

static WNDCLASSA wc;
static MSG msg;
static PAINTSTRUCT ps;
static RECT rc;
static BITMAPINFO bmi;
static POINT pt;
static HDC memdc;
static HBITMAP dib;
static unsigned int *bits;
static int cnt, tick, drag, evcount, sx, sy, lx, ly, haveline, nkeys;
static char keybuf[16];
static char line1[16];
static char line2[24];
static char logbuf[24];
static unsigned int checker[64];

static void say(const char *s) { OutputDebugStringA(s); }

static int put_num(char *p, int v) {
  int n = 0;
  if (v >= 10) { p[n++] = (char)('0' + (v / 10) % 10); }
  p[n++] = (char)('0' + v % 10);
  return n;
}

static void render(void) {
  int x, y, i, n;
  HBRUSH br;
  HPEN pen;
  rc.left = 0; rc.top = 0; rc.right = W; rc.bottom = H;
  br = CreateSolidBrush(RGB(32, 32, 48));
  FillRect(memdc, &rc, br);
  DeleteObject(br);

  for (y = 10; y < 26; y++)
    for (x = 0; x < 128; x++)
      bits[y * W + x] = 0xFF000000u | ((unsigned int)(x * 2) << 16) | ((unsigned int)(255 - x * 2) << 8) | 128u;

  pen = CreatePen(PS_SOLID, 1, RGB(255, 255, 0));
  br = CreateSolidBrush(RGB(0, 64, 128));
  SelectObject(memdc, pen);
  SelectObject(memdc, br);
  Rectangle(memdc, 10, 40, 110, 90);
  SelectObject(memdc, GetStockObject(BLACK_PEN));
  SelectObject(memdc, GetStockObject(WHITE_BRUSH));
  DeleteObject(pen);
  DeleteObject(br);

  rc.left = 120; rc.top = 40; rc.right = 220; rc.bottom = 90;
  br = CreateSolidBrush(RGB((cnt * 60) & 255, 128, 0));
  FillRect(memdc, &rc, br);
  DeleteObject(br);

  rc.left = 230; rc.top = 40; rc.right = 250; rc.bottom = 60;
  br = CreateSolidBrush(tick >= 3 ? RGB(0, 200, 0) : RGB(60, 60, 60));
  FillRect(memdc, &rc, br);
  DeleteObject(br);

  SetBkMode(memdc, TRANSPARENT);
  SetTextColor(memdc, RGB(255, 255, 255));
  n = 0;
  line1[n++] = 'C'; line1[n++] = 'o'; line1[n++] = 'u'; line1[n++] = 'n'; line1[n++] = 't'; line1[n++] = ':'; line1[n++] = ' ';
  n += put_num(line1 + n, cnt);
  TextOutA(memdc, 12, 100, line1, n);

  n = 0;
  line2[n++] = 'K'; line2[n++] = 'e'; line2[n++] = 'y'; line2[n++] = ':'; line2[n++] = ' ';
  for (i = 0; i < nkeys; i++) line2[n++] = keybuf[i];
  TextOutA(memdc, 12, 120, line2, n);

  if (haveline) {
    pen = CreatePen(PS_SOLID, 1, RGB(255, 255, 255));
    SelectObject(memdc, pen);
    MoveToEx(memdc, sx, sy, NULL);
    LineTo(memdc, lx, ly);
    SelectObject(memdc, GetStockObject(BLACK_PEN));
    DeleteObject(pen);
  }

  for (i = 0; i < 64; i++) checker[i] = (((i & 1) ^ ((i >> 3) & 1)) != 0) ? 0xFFFF8000u : 0xFF0080FFu;
  bmi.bmiHeader.biSize = 40;
  bmi.bmiHeader.biWidth = 8;
  bmi.bmiHeader.biHeight = -8;
  bmi.bmiHeader.biPlanes = 1;
  bmi.bmiHeader.biBitCount = 32;
  bmi.bmiHeader.biCompression = BI_RGB;
  StretchDIBits(memdc, 260, 100, 32, 32, 0, 0, 8, 8, checker, &bmi, DIB_RGB_COLORS, SRCCOPY);
}

static LRESULT CALLBACK WndProc(HWND h, UINT m, WPARAM w, LPARAM l) {
  int n;
  switch (m) {
  case WM_CREATE:
    bmi.bmiHeader.biSize = 40;
    bmi.bmiHeader.biWidth = W;
    bmi.bmiHeader.biHeight = -H;
    bmi.bmiHeader.biPlanes = 1;
    bmi.bmiHeader.biBitCount = 32;
    bmi.bmiHeader.biCompression = BI_RGB;
    dib = CreateDIBSection(NULL, &bmi, DIB_RGB_COLORS, (void **)&bits, NULL, 0);
    memdc = CreateCompatibleDC(NULL);
    SelectObject(memdc, dib);
    SetTimer(h, 1, 20, NULL);
    say("app: created");
    return 0;
  case WM_ERASEBKGND:
    return 1;
  case WM_PAINT:
    BeginPaint(h, &ps);
    render();
    BitBlt(ps.hdc, 0, 0, W, H, memdc, 0, 0, SRCCOPY);
    EndPaint(h, &ps);
    n = 0;
    logbuf[n++] = 'p'; logbuf[n++] = 'a'; logbuf[n++] = 'i'; logbuf[n++] = 'n'; logbuf[n++] = 't';
    logbuf[n++] = ' '; logbuf[n++] = 'e'; logbuf[n++] = 'v'; logbuf[n++] = '=';
    n += put_num(logbuf + n, evcount);
    logbuf[n] = 0;
    say(logbuf);
    return 0;
  case WM_LBUTTONDOWN:
    cnt++;
    drag = 1;
    haveline = 1;
    sx = lx = (short)(l & 0xFFFF);
    sy = ly = (short)((l >> 16) & 0xFFFF);
    SetCapture(h);
    evcount++;
    InvalidateRect(h, NULL, FALSE);
    return 0;
  case WM_MOUSEMOVE:
    if (drag) {
      GetCursorPos(&pt);
      ScreenToClient(h, &pt);
      lx = pt.x;
      ly = pt.y;
      evcount++;
      InvalidateRect(h, NULL, FALSE);
    }
    return 0;
  case WM_LBUTTONUP:
    if (drag) {
      ReleaseCapture();
      drag = 0;
      evcount++;
      InvalidateRect(h, NULL, FALSE);
    }
    return 0;
  case WM_TIMER:
    tick++;
    if (tick == 3) {
      KillTimer(h, 1);
      say("app: timer-done");
    }
    InvalidateRect(h, NULL, FALSE);
    return 0;
  case WM_CHAR:
    n = nkeys;
    if (n < 15) { keybuf[n] = (char)w; keybuf[n + 1] = 0; nkeys = n + 1; }
    evcount++;
    InvalidateRect(h, NULL, FALSE);
    return 0;
  case WM_KEYDOWN:
    if (w == VK_ESCAPE) DestroyWindow(h);
    return 0;
  case WM_DESTROY:
    say("app: destroy");
    PostQuitMessage(0);
    return 0;
  }
  return DefWindowProcA(h, m, w, l);
}

static int WINAPI WinMain_(HINSTANCE hi) {
  HWND h;
  wc.style = 0;
  wc.lpfnWndProc = WndProc;
  wc.cbClsExtra = 0;
  wc.cbWndExtra = 0;
  wc.hInstance = hi;
  wc.hIcon = NULL;
  wc.hCursor = NULL;
  wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
  wc.lpszMenuName = NULL;
  wc.lpszClassName = "GuiPoC";
  RegisterClassA(&wc);
  h = CreateWindowExA(0, "GuiPoC", "Signature GUI PoC", WS_POPUP | WS_VISIBLE, 0, 0, W, H, NULL, NULL, hi, NULL);
  if (h == NULL) return 1;
  while (GetMessageA(&msg, NULL, 0, 0)) {
    TranslateMessage(&msg);
    DispatchMessageA(&msg);
  }
  return (int)msg.wParam;
}

void entry(void) { ExitProcess(WinMain_(GetModuleHandleA(NULL))); }
