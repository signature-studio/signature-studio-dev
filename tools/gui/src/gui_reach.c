/* gui_reach.c — 到達 API ログ (CAB-156): 実結合時にどの GUI shim API が何回呼ばれたかを記録する。
 * 計数は reach ビルド (gen_api.py 生成の gui_wrap_i64.c / gen_adapt.py 生成の gui_adapt_w32.c を -DGUI_REACH_LOG で
 * リンク) の入口からのみ行う。通常ビルドでは hit が 0 件のまま (ExitProcess/failfast の dump も何も出さない)。
 * 出力: gui_log 経由 (stderr + LOG リング → host console)。1 行 1 API:
 *   GUI-REACH <到達順> <name> <calls> <IMPL|STUB> <P0..P3|P->
 *   GUI-MSG WM_PAINT <calls>     (WM_PAINT の window proc 配送。API と同じ到達順の位置に出る; #3510)
 *   GUI-REACH-SUMMARY reached=N impl=N stub=N
 * 表 (gui_reach_tab) は gen_api.py が生成 (名前昇順)。 */
#include <stdio.h>
#include <string.h>
#include "gui_internal.h"
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#define KEEP EMSCRIPTEN_KEEPALIVE
#else
#define KEEP
#endif

typedef struct { const char *name; uint8_t stub; int8_t prio; } GuiReachEnt;   /* prio: 0..3, -1 = FL 非 import */
extern const GuiReachEnt gui_reach_tab[];
extern const int gui_reach_n;

static uint32_t g_hits[2048];
static uint32_t g_order[2048];      /* 初回到達の通し番号 (1 起点) */
static uint32_t g_seq, g_distinct;
static uint32_t g_paint_hits, g_paint_order;   /* WM_PAINT 配送 (gui_reach_paint); g_order と同じ通し番号空間 */

void gui_reach_hit(int idx) {
  if (idx < 0 || idx >= gui_reach_n || idx >= 2048) return;
  if (__atomic_fetch_add(&g_hits[idx], 1, __ATOMIC_RELAXED) == 0) {
    g_order[idx] = __atomic_add_fetch(&g_seq, 1, __ATOMIC_RELAXED);
    __atomic_add_fetch(&g_distinct, 1, __ATOMIC_RELAXED);
  }
}
void gui_reach_paint(void) {
  if (__atomic_fetch_add(&g_paint_hits, 1, __ATOMIC_RELAXED) == 0)
    g_paint_order = __atomic_add_fetch(&g_seq, 1, __ATOMIC_RELAXED);
}
int gui_reach_index(const char *name) {
  int lo = 0, hi = gui_reach_n - 1;
  while (lo <= hi) {
    int mid = (lo + hi) >> 1, c = strcmp(gui_reach_tab[mid].name, name);
    if (!c) return mid;
    if (c < 0) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}
void gui_reach_hit_name(const char *name) { gui_reach_hit(gui_reach_index(name)); }
KEEP int gui_reach_distinct(void) { return (int)__atomic_load_n(&g_distinct, __ATOMIC_RELAXED); }
KEEP int gui_reach_calls(const char *name) { int i = gui_reach_index(name); return i < 0 ? -1 : (int)__atomic_load_n(&g_hits[i], __ATOMIC_RELAXED); }

static int order_cmp(const void *a, const void *b) { return (int)g_order[*(const int *)a] - (int)g_order[*(const int *)b]; }
KEEP void gui_reach_dump(void) {
  int ids[2048], n = 0, ni = 0, ns = 0, paint = g_paint_hits != 0;
  for (int i = 0; i < gui_reach_n && i < 2048; i++) if (g_hits[i]) ids[n++] = i;
  if (!n && !paint) return;
  qsort(ids, (size_t)n, sizeof ids[0], order_cmp);
  for (int k = 0; k < n; k++) {
    const GuiReachEnt *e = &gui_reach_tab[ids[k]];
    if (paint && g_paint_order < g_order[ids[k]]) { gui_logf("GUI-MSG WM_PAINT %u", (unsigned)g_paint_hits); paint = 0; }
    char p[4]; if (e->prio < 0) strcpy(p, "-"); else snprintf(p, sizeof p, "%d", e->prio);
    gui_logf("GUI-REACH %d %s %u %s P%s", k + 1, e->name, (unsigned)g_hits[ids[k]], e->stub ? "STUB" : "IMPL", p);
    if (e->stub) ns++; else ni++;
  }
  if (paint) gui_logf("GUI-MSG WM_PAINT %u", (unsigned)g_paint_hits);
  gui_logf("GUI-REACH-SUMMARY reached=%d impl=%d stub=%d", n, ni, ns);
}
/* JSON 取得 (host が直接読む用): {"name":calls,...} 到達順。戻り値 = 書込バイト数 (切詰め時は cap-1) */
KEEP int gui_reach_json(char *buf, int cap) {
  int ids[2048], n = 0, w = 0;
  for (int i = 0; i < gui_reach_n && i < 2048; i++) if (g_hits[i]) ids[n++] = i;
  qsort(ids, (size_t)n, sizeof ids[0], order_cmp);
  if (cap < 3) return 0;
  buf[w++] = '{';
  for (int k = 0; k < n; k++) {
    char t[96]; int m = snprintf(t, sizeof t, "%s\"%s\":%u", k ? "," : "", gui_reach_tab[ids[k]].name, (unsigned)g_hits[ids[k]]);
    if (w + m + 2 > cap) break;
    memcpy(buf + w, t, (size_t)m); w += m;
  }
  buf[w++] = '}'; buf[w] = 0;
  return w;
}
