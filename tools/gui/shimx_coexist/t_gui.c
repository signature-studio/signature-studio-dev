/* gui 直呼び側 TU: gui_rename.h により <Name> が gui_impl_<Name> になる (公開名は t_main.c 側で shimx/adapter 解決に任せるため分離) */
#include "gui_rename.h"
#include "gui_api.h"
#include "gui_internal.h"

static int64_t wproc(int64_t h, int64_t m, int64_t w, int64_t l) { return DefWindowProcA(h, m, w, l); }
/* wasm の関数ポインタは小さな table index なので、本番同様 icall hook (m11_icall 相当) で WNDPROC を呼ぶ */
static uint64_t icall(uint64_t t, uint64_t a, uint64_t b, uint64_t c, uint64_t d) { return (uint64_t)((int64_t (*)(int64_t, int64_t, int64_t, int64_t))(uintptr_t)t)((int64_t)a, (int64_t)b, (int64_t)c, (int64_t)d); }
int64_t t_make_window(int x, int y, int w, int h) {
  gui_set_icall_hook(icall);
  WWNDCLASS wc; memset(&wc, 0, sizeof wc);
  wc.lpfnWndProc = (uint64_t)(uintptr_t)wproc; wc.lpszClassName = (uint64_t)(uintptr_t)"TCO";
  RegisterClassA((int64_t)(uintptr_t)&wc);
  return CreateWindowExA(0, (int64_t)(uintptr_t)"TCO", 0, WS_POPUP | WS_VISIBLE, x, y, w, h, 0, 0, 0x400000, 0);
}
int64_t t_make_child(int64_t parent, int x, int y, int w, int h) {
  return CreateWindowExA(0, (int64_t)(uintptr_t)"TCO", 0, WS_CHILD | WS_VISIBLE, x, y, w, h, parent, 7, 0x400000, 0);
}
void t_post_thread_msg(uint32_t m) { PostThreadMessageW(0, m, 1, 2); }
/* 1 = msg を取り出せた */
int t_peek(uint32_t *msg, int64_t *wp, int64_t *lp, int64_t *hwnd) {
  WMSG m;
  if (!PeekMessageA((int64_t)(uintptr_t)&m, 0, 0, 0, PM_REMOVE)) return 0;
  *msg = m.message; *wp = (int64_t)m.wParam; *lp = m.lParam; *hwnd = (int64_t)m.hwnd;
  return 1;
}
