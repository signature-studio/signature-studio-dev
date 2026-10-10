/* gui_app_ff.c — fail-fast 検証用: 未実装 API (Ellipse) に到達する最小アプリ */
#include <windows.h>
static WNDCLASSA wc;
static MSG msg;
static LRESULT CALLBACK WndProc(HWND h, UINT m, WPARAM w, LPARAM l) {
  if (m == WM_CREATE) {
    HDC dc = GetDC(h);
    Ellipse(dc, 0, 0, 10, 10);
    return 0;
  }
  return DefWindowProcA(h, m, w, l);
}
static int WINAPI WinMain_(HINSTANCE hi) {
  wc.lpfnWndProc = WndProc;
  wc.hInstance = hi;
  wc.lpszClassName = "FF";
  RegisterClassA(&wc);
  CreateWindowExA(0, "FF", "ff", WS_POPUP | WS_VISIBLE, 0, 0, 64, 64, NULL, NULL, hi, NULL);
  while (GetMessageA(&msg, NULL, 0, 0)) { TranslateMessage(&msg); DispatchMessageA(&msg); }
  return 0;
}
void entry(void) { ExitProcess(WinMain_(GetModuleHandleA(NULL))); }
