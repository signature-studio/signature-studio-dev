/* WIN-35 (#3618): native の RegisterClassW・CreateWindowExW を tools/gui の shim (gui_core) と headless host へ向ける。
 * ld_native を -DLD_GUI_HL で作り、実行時に LD_GUI_HL=1 のときだけ使う (既定の応答は変えない)。
 * guest の窓プロシージャは gui_set_icall_hook で ld_ms_call (MS x64 ABI) 経由に呼ぶ。
 * 窓 (surface) の統計は case ごとに 1 行ずつ ld_native から ld_gui_dump で出す (LD_GUI_OUT・既定は stderr)。 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "gui_internal.h"
#include "gui_headless.h"

extern void ld_ms_call(void* fn, const uint64_t* gpr4, const uint64_t* xmm4, const uint64_t* stk, long nstk, uint64_t* out4, uint64_t rax_init);
extern int gui_surf_snapshot(int id, uint32_t** px, uint32_t* w, uint32_t* h);
extern GuiShared* gui_shared_native(void);

/* 到達ログ表 (gui_reach.c が参照)。本ビルドは到達ログを使わないため件数 0 の空表 (生成表は gen_api.py の出力) */
typedef struct { const char* name; uint8_t stub; int8_t prio; } GuiReachEnt;
const GuiReachEnt gui_reach_tab[1] = { { "", 0, -1 } };
const int gui_reach_n = 0;

static uint64_t gui_icall(uint64_t t, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3) {
  uint64_t g[4] = { a0, a1, a2, a3 }, x[4] = { 0 }, stk[8] = { 0 }, o[4] = { 0 };
  ld_ms_call((void*)(uintptr_t)t, g, x, stk, 8, o, 0);
  return o[0];
}

void ld_gui_init(void) {
  gui_hl_start(1920, 1080, 0);
  gui_set_icall_hook(gui_icall);
}

void ld_gui_dump(FILE* f, const char* cid) {
  GuiShared* sh = gui_shared_native();
  for (int i = 0; i < (int)GUI_MAX_SURF; i++) {
    GuiSurface* s = &sh->surf[i];
    if (!s->state) continue;
    uint32_t *px = NULL, w = 0, h = 0;
    if (!gui_surf_snapshot(i, &px, &w, &h)) { fprintf(f, "gui case=%s surf=%d snapshot=fail\n", cid, i); continue; }
    GuiHlStats st; gui_hl_stats(px, w, h, 0xFF000000u, &st);
    fprintf(f, "gui case=%s surf=%d x=%d y=%d w=%u h=%u visible=%u title=\"%s\" nonbg=%llu colors=%u bg=0x%06x sha256=",
            cid, i, s->x, s->y, w, h, s->visible, s->title, (unsigned long long)st.nonbg, st.colors, st.bg);
    for (int k = 0; k < 32; k++) fprintf(f, "%02x", st.sha256[k]);
    fprintf(f, "\n");
  }
  fflush(f);
}
