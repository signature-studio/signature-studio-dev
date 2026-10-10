/* sx_cbboot.c — M11 shimx リンクへの shimx R2/R3 実体接続 boot (CAB-177)。
 *
 * tools/shimx/src/cbtrans.c (R2 トランポリン実体 + R3 lifttab) を **実リンク構成** で使うための
 * link 側 1 ファイル。旧 cb_adapt.c (--wrap=EnumCalendarInfoW/EnumSystemLocalesW の暫定アダプタ,
 * shimx_link REPORT §3-#3) を置き換える:
 *   - 全 variant (plain/trace × failfast/soft × --fix 有無) で constructor 実行
 *   - invoke = m11_icall (m11_ov.c の VA→関数表解決。uniform u64×8 ABI)
 *   - translator = shimx_cb_translator (VA ≥ intptr_limit(0x10000) → slot トランポリン / 未満は恒等)
 *   - proc_resolver = shimx_lifttab_proc_resolver (shell32 IL* 10 本 + kernel32 UI言語 3 本を
 *     lift 関数表から解決可能なトークン 0x7F000000+i へ)
 *   - --wrap=m11_icall: build.sh が付与。トークン → shimx_lifttab_trampoline (u64×8 thunk) →
 *     実 C 実装。それ以外は __real_m11_icall (従来の disp 表解決)。
 *     (現行 boot_final3 IR は間接 call を lift しないため実呼出は発生しない = icall 復元 route
 *      採用時に有効になる構え。往復の実証は tools/hostbridge/cb/ と tools/shimx/test/test_cbtrans.c)
 */
#include <stdint.h>
#include "../../shimx/src/shimx.h"

typedef unsigned long long u64x;

extern u64x m11_icall(u64x target, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7);

/* --wrap=m11_icall 由来の実体 (m11_ov.c の定義がリネームされる) */
extern u64x __real_m11_icall(u64x target, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7);

static int g_booted, g_wrap_hits;
u64x __wrap_m11_icall(u64x target, u64x a0, u64x a1, u64x a2, u64x a3, u64x a4, u64x a5, u64x a6, u64x a7) {
    shimx_lift_thunk_fn th = shimx_lifttab_trampoline((unsigned)target);
    if (th) { g_wrap_hits++; return th(a0, a1, a2, a3, a4, a5, a6, a7); }
    return __real_m11_icall(target, a0, a1, a2, a3, a4, a5, a6, a7);
}

__attribute__((constructor)) static void sx_cb_boot(void) {
    if (g_booted) return;
    shimx_cbtrans_set_invoke((shimx_cb_invoke_fn)m11_icall);   /* --wrap 経由で __wrap_m11_icall に解決される */
    shimx_cbtrans_install();
    shimx_set_proc_resolver(shimx_lifttab_proc_resolver);
    g_booted = 1;
}

/* 診断 (run_trace.mjs / RESULTS から参照) */
EMSCRIPTEN_KEEPALIVE int sx_cb_booted(void) { return g_booted; }
EMSCRIPTEN_KEEPALIVE int sx_cb_wrap_hits(void) { return g_wrap_hits; }
EMSCRIPTEN_KEEPALIVE int sx_cb_slots(void) { return shimx_cbtrans_slots(); }
EMSCRIPTEN_KEEPALIVE int sx_cb_calls(void) { return (int)shimx_cbtrans_calls(); }
