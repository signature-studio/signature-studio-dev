/* text_wasm_app.c — GUI-13 (#615): ブラウザ (wasm) 上の GDI テキスト描画 e2e 用ゲスト。RetDec を要さない lifted.c の代替
 * (gui_lift_main.c が要求する gui_lift_entry / gui_lift_fnmap を自前で提供し、`gui_wasm.sh test/text_wasm_app.c <out>` でそのまま wasm 化できる)。
 * 流れ: ウィンドウ作成 → WM_PAINT で test/text_scene.inc のシーンをメモリ DC へ描いて BitBlt → metrics 表を "TM\t..." 行で LOG へ → "text: done"。
 * face の登録は host (JS) が gui_ft_add_face で行う。登録が無ければ shim は内蔵 8x8 フォントで描く (既存 e2e の経路)。 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "gui_api.h"
#include "gui_internal.h"
#define PTR(x) ((int64_t)(uintptr_t)(x))
#define W 320
#define H 120
#include "text_scene.inc"

#define APP_WNDPROC_VA 0x401000u
static void emit_tm(void *u, const char *l) { (void)u; char b[200]; snprintf(b, sizeof b, "TM\t%s", l); gui_log(b); }

static int64_t g_memdc;
static int64_t wndproc(int64_t h, int64_t m, int64_t w, int64_t l) {
  if (m == WM_ERASEBKGND) return 1;
  if (m == WM_CREATE) {
    WBMIH bi; memset(&bi, 0, sizeof bi); bi.biSize = 40; bi.biWidth = W; bi.biHeight = -H; bi.biPlanes = 1; bi.biBitCount = 32; uint64_t pv = 0;
    int64_t hb = CreateDIBSection(0, PTR(&bi), 0, PTR(&pv), 0, 0); g_memdc = CreateCompatibleDC(0); SelectObject(g_memdc, hb);
    gui_log("text: created");
    return 0;
  }
  if (m == WM_PAINT) {
    WPAINTSTRUCT ps; BeginPaint(h, PTR(&ps));
    text_scene_draw(g_memdc, 0);
    BitBlt(ps.hdc, 0, 0, W, H, g_memdc, 0, 0, SRCCOPY);
    EndPaint(h, PTR(&ps));
    static int done; if (!done) { done = 1; text_scene_metrics(g_memdc, emit_tm, NULL); gui_log("text: done"); gui_reach_dump(); }
    return 0;
  }
  if (m == WM_DESTROY) { PostQuitMessage(0); return 0; }
  return DefWindowProcA(h, m, w, l);
}

const GuiFnMap gui_lift_fnmap[] = { { APP_WNDPROC_VA, (void *)wndproc } };
const int gui_lift_fnmap_n = 1;
int64_t gui_lift_entry(void) {
  WWNDCLASS wc; memset(&wc, 0, sizeof wc); wc.lpfnWndProc = APP_WNDPROC_VA; wc.lpszClassName = PTR("TextWasm");
  RegisterClassA(PTR(&wc));
  int64_t h = CreateWindowExA(0, PTR("TextWasm"), PTR("text"), WS_POPUP | WS_VISIBLE, 0, 0, W, H, 0, 0, 0x400000, 0);
  if (!h) return 1;
  WMSG msg;
  while (GetMessageA(PTR(&msg), 0, 0, 0)) { TranslateMessage(PTR(&msg)); DispatchMessageA(PTR(&msg)); }
  ExitProcess(0);
  return 0;
}
