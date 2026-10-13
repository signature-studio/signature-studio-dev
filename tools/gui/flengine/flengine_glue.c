/* GUI-3 (#174): m11 closure に tools/gui shim を結線する薄い糊 (-pthread, node 向け headless host 内蔵)。
 *   - 起動前 (constructor): host_ready=1 (gui_headless_attach) / out ring は host 不在なので満杯時に破棄 / WNDPROC は m11_icall へ。
 *   - 到達 API ログは gui_reach_dump が出す GUI-REACH 行を JS ハーネスが回収する。 */
#include <stdint.h>
#include <stdio.h>
#include <emscripten.h>
#include "gui_internal.h"
#include "gui_proto.h"

extern uint64_t m11_icall(uint64_t t, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t a4, uint64_t a5, uint64_t a6, uint64_t a7);
extern void gui_headless_attach(uint32_t w, uint32_t h);

/* WNDCLASS.lpfnWndProc が DefWindowProc の import thunk (gen_thunks.py の表) なら shim の DefWindowProc へ。それ以外は m11_icall (VA→trampoline) */
extern const unsigned long long gf_thunk_va[]; extern const int gf_thunk_kind[]; extern const int gf_thunk_n;
extern int64_t gui_impl_DefWindowProcW(int64_t, int64_t, int64_t, int64_t);
extern int64_t gui_impl_DefWindowProcA(int64_t, int64_t, int64_t, int64_t);
static uint32_t g_icall_calls, g_thunk_calls;
static uint64_t gf_icall(uint64_t t, uint64_t a, uint64_t b, uint64_t c, uint64_t d) {
  g_icall_calls++;
  for (int i = 0; i < gf_thunk_n; i++) if (gf_thunk_va[i] == t) {
    g_thunk_calls++;
    return (uint64_t)(gf_thunk_kind[i] == 1 ? gui_impl_DefWindowProcW((int64_t)a, (int64_t)b, (int64_t)c, (int64_t)d)
                                            : gui_impl_DefWindowProcA((int64_t)a, (int64_t)b, (int64_t)c, (int64_t)d));
  }
  return m11_icall(t, a, b, c, d, 0, 0, 0, 0);
}

static uint32_t g_discarded;
static void gf_drain(void) {   /* host (ブラウザ) 不在: out ring を捨てて進める */
  GuiShared *sh = gui_sh();
  uint32_t t = __atomic_load_n(&sh->out_ring.tail, __ATOMIC_ACQUIRE);
  g_discarded += t - sh->out_ring.head;
  __atomic_store_n(&sh->out_ring.head, t, __ATOMIC_RELEASE);
}

__attribute__((constructor)) static void gf_init(void) {
  gui_headless_attach(1920, 1080);
  gui_host_drain_cb = gf_drain;
  gui_set_icall_hook(gf_icall);
}

/* gui_failfast は abort() で wasm を止めてしまい、unit 単位の隔離 survey や「到達した未実装 API の集計」ができない。
 * リンク時 --wrap=gui_failfast でここへ向け、同じ FAIL-FAST 行を出してから JS 例外で呼出元 (ハーネス) へ脱出する。 */
EM_JS(void, gf_throw, (const char *api, const char *why), {
  const e = new Error("gui_failfast: " + UTF8ToString(api) + (why ? " : " + UTF8ToString(why) : ""));
  e.gui_failfast = UTF8ToString(api);
  throw e;
});
static uint32_t g_failfast;
void __wrap_gui_failfast(const char *api, const char *why) {
  g_failfast++;
  fprintf(stderr, "FAIL-FAST: unimplemented Win32 API: %s%s%s\n", api, why ? " : " : "", why ? why : "");
  gf_throw(api, why);
  __builtin_unreachable();
}

/* --soft ビルド: 未実装 (STUB) API は 0 を返して継続。FAIL-FAST と区別できる行を出す */
static uint32_t g_soft;
int64_t gf_soft_stub(const char *api) {
  g_soft++;
  fprintf(stderr, "SOFT-STUB: unimplemented Win32 API: %s\n", api);
  return 0;
}

EMSCRIPTEN_KEEPALIVE uint32_t gf_thunk_count(void) { return g_thunk_calls; }
EMSCRIPTEN_KEEPALIVE uint32_t gf_icall_count(void) { return g_icall_calls; }
EMSCRIPTEN_KEEPALIVE uint32_t gf_ring_discarded(void) { return g_discarded; }
EMSCRIPTEN_KEEPALIVE uint32_t gf_failfast_count(void) { return g_failfast; }
EMSCRIPTEN_KEEPALIVE uint32_t gf_soft_stub_count(void) { return g_soft; }
