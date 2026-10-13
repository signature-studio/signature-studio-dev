/* gui_ft_wasm.c — wasm ビルド (gui_wasm.sh) 用: FreeType エンジンの host 結線 (GUI-13 #615)。
 * host (JS) が gui_ft_add_face / gui_ft_add_alias を呼ぶと face を「遅延取得」で登録し text engine を有効化する。
 * 何も呼ばなければ engine 未登録のまま = 従来の内蔵 8x8 フォント (既存 e2e の挙動)。
 * フォント本体は同梱しない: 最初に open された時点で host call (GUI_HC_FETCH_FONT) で host が取得・sha256 検証し、wasm heap へ置いて ptr/size を返す
 *   (host 側は src/runtime/gui_hostcall.ts の HostCallEnv.loadFont。実配信は #22 VFS の遅延取得に接続する)。
 * 呼出規約: JS は app スレッドが host_ready 待ち (gui_sh) で止まっている間に呼ぶこと (登録表は排他しない)。 */
#include <stdint.h>
#include <string.h>
#include "gui_internal.h"
#include "gui_hostcall.h"
#include "gui_ft.h"
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

static int host_load(const char *name, const uint8_t **data, size_t *size, void *user) {
  (void)user;
  uint8_t out[8]; uint32_t n = 0;
  int rc = gui_hostcall(GUI_HC_FETCH_FONT, 0, name, (uint32_t)strlen(name) + 1, out, sizeof out, &n, 30000);
  if (rc <= 0 || n != 8) { gui_logf("gui_ft: font '%s' unavailable (hostcall rc=%d n=%u); falling back to 8x8", name, rc, n); return 0; }
  uint32_t p, s; memcpy(&p, out, 4); memcpy(&s, out + 4, 4);
  if (!p || !s) return 0;
  *data = (const uint8_t *)(uintptr_t)p; *size = s;
  return 1;
}

EMSCRIPTEN_KEEPALIVE int gui_ft_add_face(const char *name) {
  int r = gui_ft_register_lazy(name, host_load, NULL);
  if (r >= 0) gui_set_text_engine(gui_ft_engine());
  return r;
}
EMSCRIPTEN_KEEPALIVE int gui_ft_add_alias(const char *alias, const char *target) { return gui_ft_alias(alias, target); }
