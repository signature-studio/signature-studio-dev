/* wbench_shim.c — bench.c (API 単位 bench) を emcc + node で動かすための薄い shim。
 *  - gui_platform.c は wasm では gui_shared_native を公開しない (gui_shared_ptr のみ) ため、同じ実体を返す。
 *  - wasm の関数ポインタは table index (小整数) で gui_resolve_fn が fail-fast するため、DefWindowProcA を fnmap に登録する。 */
#include "gui_api.h"
#include "gui_internal.h"
extern uint32_t gui_shared_ptr(void);
GuiShared *gui_shared_native(void) { return (GuiShared *)(uintptr_t)gui_shared_ptr(); }

static GuiFnMap g_map[1];
__attribute__((constructor)) static void wb_init(void) { g_map[0].va = (uint64_t)(uintptr_t)DefWindowProcA; g_map[0].fn = (void *)DefWindowProcA; gui_register_fnmap(g_map, 1); }
