/* gui_core.c — user32 相当: クラス/ウィンドウ/メッセージ/タイマ/入力/surface present
 * 公開 API は lift ABI (int64_t 引数/戻り値) で定義する。生成 gui_api.h が宣言を提供。 */
#include <stdio.h>
#include <stdarg.h>
#include <strings.h>
#include <math.h>
#include "gui_internal.h"

#define API int64_t
#define NOT_IMPL(name) gui_failfast(name, NULL)

/* ================= 文字列 ================= */
static int u16_to_u8(const uint16_t *s, char *out, int cap) {  /* NUL 終端まで (BMP+surrogate) */
  int n = 0;
  for (; s && *s; s++) {
    uint32_t c = *s;
    if (c >= 0xD800 && c < 0xDC00 && s[1] >= 0xDC00 && s[1] < 0xE000) { c = 0x10000 + ((c - 0xD800) << 10) + (s[1] - 0xDC00); s++; }
    char tmp[4]; int k;
    if (c < 0x80) { tmp[0] = (char)c; k = 1; }
    else if (c < 0x800) { tmp[0] = (char)(0xC0 | (c >> 6)); tmp[1] = (char)(0x80 | (c & 63)); k = 2; }
    else if (c < 0x10000) { tmp[0] = (char)(0xE0 | (c >> 12)); tmp[1] = (char)(0x80 | ((c >> 6) & 63)); tmp[2] = (char)(0x80 | (c & 63)); k = 3; }
    else { tmp[0] = (char)(0xF0 | (c >> 18)); tmp[1] = (char)(0x80 | ((c >> 12) & 63)); tmp[2] = (char)(0x80 | ((c >> 6) & 63)); tmp[3] = (char)(0x80 | (c & 63)); k = 4; }
    if (n + k >= cap) break;
    memcpy(out + n, tmp, k); n += k;
  }
  if (cap > 0) out[n] = 0;
  return n;
}
/* trunc != NULL なら、cap に収まらず変換を打ち切ったとき *trunc = 1 (収まれば 0)。cap < 1 のときは何も書かない */
static int u8_to_u16x(const char *s, uint16_t *out, int cap, int *trunc) {
  int n = 0;
  while (s && *s && n + 2 < cap) {
    uint32_t c = (uint8_t)*s++;
    if (c >= 0xF0) { c = ((c & 7) << 18) | ((uint32_t)(s[0] & 63) << 12) | ((uint32_t)(s[1] & 63) << 6) | (s[2] & 63); s += 3; }
    else if (c >= 0xE0) { c = ((c & 15) << 12) | ((uint32_t)(s[0] & 63) << 6) | (s[1] & 63); s += 2; }
    else if (c >= 0xC0) { c = ((c & 31) << 6) | (s[0] & 63); s += 1; }
    if (c >= 0x10000) { c -= 0x10000; out[n++] = (uint16_t)(0xD800 + (c >> 10)); out[n++] = (uint16_t)(0xDC00 + (c & 1023)); }
    else out[n++] = (uint16_t)c;
  }
  if (trunc) *trunc = (s && *s) ? 1 : 0;
  if (cap > 0) out[n] = 0;
  return n;
}
static int u8_to_u16(const char *s, uint16_t *out, int cap) { return u8_to_u16x(s, out, cap, NULL); }
/* 引数文字列 (A/W/atom) を UTF-8 に */
static const char *str_in(U64 p, int wide, char *buf, int cap) {
  if (p < 0x10000) return NULL;  /* MAKEINTATOM / NULL */
  if (wide) { u16_to_u8((const uint16_t *)P_(p), buf, cap); return buf; }
  return (const char *)P_(p);
}

/* ================= 型 ================= */
typedef struct Class {
  char name[128]; uint32_t atom; uint32_t style; U64 wndproc; int cbcls, cbwnd;
  U64 hinst, hicon, hcursor, hbrbg; int wide; struct Class *next; uint8_t *extra;
} Class;

struct Wnd {
  U64 h; Wnd *parent, *first, *last, *prev, *next;
  Class *cls; uint32_t style, exstyle; int32_t x, y, w, hgt;
  U64 wndproc, userdata, id, hinst;
  int wide, destroying;
  char title[128];
  int has_inv; WRECT inv; RL invl; int erase;   /* invl = 無効領域 (client 座標の非重複矩形リスト), inv = その外接矩形 */
  int nl, nt, nr, nb; int nc_dirty;              /* 非クライアント領域の幅 (window rect と client rect の差) */
  int surf;                 /* top-level のみ */
  uint64_t tid; uint8_t *extra; int cbextra;
  int in_paint;
  struct Prop { char name[64]; U64 val; struct Prop *next; } *props;
};

static Class *g_classes; static uint32_t g_next_atom = 0xC001;
static Wnd *g_desktop;
static Wnd *g_focus, *g_active, *g_capture;
static void ptrlock_update(void);
static int g_quit_posted; static int g_quit_code;
static uint64_t g_gui_tid;
static uint32_t g_msg_time; static WPOINT g_msg_pt;

/* ================= surface / present ================= */
static RL g_dirty[GUI_MAX_SURF]; static uint8_t g_hasdirty[GUI_MAX_SURF];   /* dirty は非重複矩形リスト (8 超は外接矩形へ縮退) */ static volatile int g_any_dirty; static uint32_t g_last_flush;
static uint32_t g_ztop, g_ztop_tm = 0x40000000u;   /* TOPMOST は常に非 TOPMOST より前面 (z >= 0x40000000) */
static uint8_t *g_surf_ptr[GUI_MAX_SURF];   /* native(64bit) 用の実ポインタ。wasm32 では s->pixels と同値 */

/* host (headless render thread) 向けの不変スナップショット (px,w,h)。shim は surface の生成/再確保ごとに新しい SurfSnap を atomic に公開し、
 * 旧 SurfSnap・旧画素の free は「その変更を伝える out ring レコードを host が消費し終える (out_ring.head が通過)」まで遅延する (GUI-12)。
 * host は処理中の 1 レコードの間だけ参照し、その間は free されない。gui_lock を host が取る案は out ring 満杯時に shim (lock 保持で push 待ち) と
 * デッドロックするため採らない。 */
typedef struct SurfSnap { uint32_t *px; uint32_t w, h; } SurfSnap;
static SurfSnap *g_surf_snap[GUI_MAX_SURF];
int gui_surf_snapshot(int id, uint32_t **px, uint32_t *w, uint32_t *h) {
  SurfSnap *sn = __atomic_load_n(&g_surf_snap[id], __ATOMIC_ACQUIRE);
  if (!sn) return 0;
  *px = sn->px; *w = sn->w; *h = sn->h;
  return 1;
}
typedef struct Retired { void *a, *b; uint32_t pos; struct Retired *next; } Retired;
static Retired *g_retired;
/* gui_lock 下で、a/b を out ring の現 tail (= 直前に push した変更レコードを含む) を host が消費し終えてから free するよう登録する */
static void reap_locked(void);
static void retire_locked(void *a, void *b) {
#ifdef GUI12_NEGCTL_IMMEDIATE_FREE   /* ネガコン専用: 修正前の挙動 (即 free) に戻す。tools/gui/test/gui12_race.sh だけが定義する */
  free(a); free(b); return;
#endif
  reap_locked();
  Retired *r = (Retired *)malloc(sizeof *r);
  if (!r) gui_failfast("surface", "retire alloc failed");
  r->a = a; r->b = b; r->pos = __atomic_load_n(&gui_sh()->out_ring.tail, __ATOMIC_ACQUIRE);
  r->next = g_retired; g_retired = r;
}
static void reap_locked(void) {
  uint32_t head = __atomic_load_n(&gui_sh()->out_ring.head, __ATOMIC_ACQUIRE);
  Retired **pp = &g_retired;
  while (*pp) {
    Retired *r = *pp;
    if ((int32_t)(head - r->pos) >= 0) { *pp = r->next; free(r->a); free(r->b); free(r); }
    else pp = &r->next;
  }
}
uint32_t gui_surf_retired_count(void) {
  gui_lock(); reap_locked(); uint32_t n = 0;
  for (Retired *r = g_retired; r; r = r->next) n++;
  gui_unlock();
  return n;
}
static SurfSnap *snap_new(uint32_t *px, uint32_t w, uint32_t h) {
  SurfSnap *sn = (SurfSnap *)malloc(sizeof *sn);
  if (!sn) gui_failfast("surface", "snapshot alloc failed");
  sn->px = px; sn->w = w; sn->h = h;
  return sn;
}

int surf_view(int id, SurfView *v) {
  GuiShared *sh = gui_sh();
  if (id < 0 || id >= (int)GUI_MAX_SURF || !sh->surf[id].state) return 0;
  GuiSurface *s = &sh->surf[id];
  v->px = g_surf_ptr[id]; v->stride = (int)s->stride; v->w = (int)s->w; v->h = (int)s->h; v->gen = s->gen;
  return 1;
}
/* seqlock (GUI-4): host が surface 画素を読むときの tearing 検出用。奇数 = flush 後に shim が画素へ書込み中/書込み済み (未 flush)、
 * 偶数 = 静止。書込み前に begin (偶数→奇数)、PRESENT を push する前に end (奇数→偶数)。host は読出し前後で同じ偶数値を確認する。 */
void surf_wseq_begin(int id) {
  if (id < 0 || id >= (int)GUI_MAX_SURF) return;
  uint32_t *w = &gui_sh()->surf[id].wseq;
  uint32_t cur = __atomic_load_n(w, __ATOMIC_RELAXED);
  while (!(cur & 1)) if (__atomic_compare_exchange_n(w, &cur, cur + 1, 0, __ATOMIC_SEQ_CST, __ATOMIC_RELAXED)) break;
}
static void surf_wseq_end(int id) {
  uint32_t *w = &gui_sh()->surf[id].wseq;
  uint32_t cur = __atomic_load_n(w, __ATOMIC_RELAXED);
  while (cur & 1) if (__atomic_compare_exchange_n(w, &cur, cur + 1, 0, __ATOMIC_SEQ_CST, __ATOMIC_RELAXED)) break;
}
static void out_cmd(uint32_t cmd, uint32_t surf, uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e) {
  uint32_t rec[8] = { cmd, surf, a, b, c, d, e, 0 };
  gui_out_push(rec);
}
void surf_dirty(int id, WRECT r) {
  if (id < 0 || id >= (int)GUI_MAX_SURF) return;
  gui_lock();
  GuiSurface *s = &gui_sh()->surf[id];
  r = r_isect(r, (WRECT){ 0, 0, (int32_t)s->w, (int32_t)s->h });
  if (!r_empty(r)) {
    g_any_dirty = 1;
    RL t = {0}; rl_add(&t, r);
    if (!g_hasdirty[id]) { rl_clear(&g_dirty[id]); g_hasdirty[id] = 1; }
    rl_union(&g_dirty[id], &t); rl_free(&t);
    if (g_dirty[id].n > 8) { WRECT b; rl_bbox(&g_dirty[id], &b); rl_clear(&g_dirty[id]); rl_add(&g_dirty[id], b); }
  }
  gui_unlock();
}
void surf_flush(void) {
  GuiShared *sh = gui_sh();
  gui_lock();
  g_any_dirty = 0; g_last_flush = gui_now_ms();
  reap_locked();
  int any = 0;
  uint32_t seq = sh->present_seq + 1;
  for (int i = 0; i < (int)GUI_MAX_SURF; i++) if (sh->surf[i].state) surf_wseq_end(i);   /* PRESENT を見た host が読む前に静止を宣言 */
  for (int i = 0; i < (int)GUI_MAX_SURF; i++) {
    if (!g_hasdirty[i]) continue;
    g_hasdirty[i] = 0;
    if (!sh->surf[i].state) continue;
    for (int k = 0; k < g_dirty[i].n; k++) {
      WRECT r = g_dirty[i].r[k];
      out_cmd(GUI_CMD_PRESENT, (uint32_t)i, (uint32_t)r.left, (uint32_t)r.top, (uint32_t)r.right, (uint32_t)r.bottom, seq);
      any = 1;
    }
  }
  if (any) {
    out_cmd(GUI_CMD_FRAME_END, seq, 0, 0, 0, 0, 0);
    __atomic_store_n(&sh->present_seq, seq, __ATOMIC_SEQ_CST);
    sh->frames_flushed++;
  }
  gui_unlock();
}

static int surf_alloc(int x, int y, int w, int h, const char *title) {
  GuiShared *sh = gui_sh();
  gui_lock();
  for (int i = 0; i < (int)GUI_MAX_SURF; i++) {
    GuiSurface *s = &sh->surf[i];
    if (s->state) continue;
    if (w < 1) w = 1;
    if (h < 1) h = 1;
    uint32_t *px = (uint32_t *)calloc((size_t)w * h, 4);
    if (!px) gui_failfast("CreateWindowEx", "surface alloc failed");
    for (size_t k = 0; k < (size_t)w * h; k++) px[k] = 0xFF000000u;
    s->x = x; s->y = y; s->w = (uint32_t)w; s->h = (uint32_t)h; s->stride = (uint32_t)w * 4;
    s->pixels = (uint32_t)(uintptr_t)px; g_surf_ptr[i] = (uint8_t *)px; s->gen++; s->z = ++g_ztop; s->visible = 0;
    __atomic_store_n(&g_surf_snap[i], snap_new(px, (uint32_t)w, (uint32_t)h), __ATOMIC_RELEASE);
    snprintf(s->title, sizeof s->title, "%s", title ? title : "");
    __atomic_store_n(&s->state, 1, __ATOMIC_SEQ_CST);
    out_cmd(GUI_CMD_SURF_CREATE, (uint32_t)i, 0, 0, 0, 0, 0);
    gui_unlock();
    return i;
  }
  gui_unlock();
  gui_failfast("CreateWindowEx", "too many top-level windows (GUI_MAX_SURF)");
}
static void surf_free(int id) {
  GuiShared *sh = gui_sh();
  gui_lock();
  GuiSurface *s = &sh->surf[id];
  if (s->state) {
    out_cmd(GUI_CMD_SURF_DESTROY, (uint32_t)id, 0, 0, 0, 0, 0);
    __atomic_store_n(&s->state, 0, __ATOMIC_SEQ_CST);
    SurfSnap *osn = __atomic_exchange_n(&g_surf_snap[id], NULL, __ATOMIC_ACQ_REL);
    retire_locked(g_surf_ptr[id], osn);   /* host が SURF_DESTROY (と先行レコード) を消費するまで free しない */
    g_surf_ptr[id] = NULL; s->pixels = 0; g_hasdirty[id] = 0; rl_free(&g_dirty[id]);
  }
  gui_unlock();
}
static void surf_resize(int id, int w, int h) {
  GuiShared *sh = gui_sh();
  GuiSurface *s = &sh->surf[id];
  if (w < 1) w = 1;
  if (h < 1) h = 1;
  if ((uint32_t)w == s->w && (uint32_t)h == s->h) return;
  uint32_t *np = (uint32_t *)malloc((size_t)w * h * 4);
  for (size_t k = 0; k < (size_t)w * h; k++) np[k] = 0xFF000000u;
  surf_wseq_begin(id);
  uint32_t *op = (uint32_t *)g_surf_ptr[id];
  int cw = (int)(s->w < (uint32_t)w ? s->w : (uint32_t)w), ch = (int)(s->h < (uint32_t)h ? s->h : (uint32_t)h);
  for (int y = 0; y < ch; y++) memcpy(np + (size_t)y * w, op + (size_t)y * s->w, (size_t)cw * 4);
  gui_lock();
  s->w = (uint32_t)w; s->h = (uint32_t)h; s->stride = (uint32_t)w * 4; s->pixels = (uint32_t)(uintptr_t)np; g_surf_ptr[id] = (uint8_t *)np; s->gen++;
  SurfSnap *osn = __atomic_exchange_n(&g_surf_snap[id], snap_new(np, (uint32_t)w, (uint32_t)h), __ATOMIC_ACQ_REL);
  gui_unlock();
  out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)id, 0, 0, 0, 0, 0);
  gui_lock(); retire_locked(op, osn); gui_unlock();   /* SURF_CHANGE push 後の tail を host が消費し終えるまで旧画素を保持 */
}

/* ================= 関数ポインタ解決 (lift の VA -> 関数) ================= */
typedef struct { uint64_t va; void *fn; } GuiFnMap;
static const GuiFnMap *g_fnmap; static int g_fnmap_n;
void gui_register_fnmap(const GuiFnMap *m, int n) { g_fnmap = m; g_fnmap_n = n; }
void *gui_resolve_fn(U64 v) {
  for (int i = 0; i < g_fnmap_n; i++) if (g_fnmap[i].va == v) return g_fnmap[i].fn;
  if (v < 0x10000) gui_failfast("wndproc", "invalid function pointer value (not a VA in fnmap, looks like a small integer)");
  return (void *)(uintptr_t)v;
}

static GuiIcallHook g_icall_hook;
void gui_set_icall_hook(GuiIcallHook h) { g_icall_hook = h; }
I64 gui_call4(U64 t, I64 a0, I64 a1, I64 a2, I64 a3) {
  if (g_icall_hook) return (I64)g_icall_hook(t, (uint64_t)a0, (uint64_t)a1, (uint64_t)a2, (uint64_t)a3);
  return ((WNDPROC64)gui_resolve_fn(t))(a0, a1, a2, a3);
}
I64 gui_call3(U64 t, I64 a0, I64 a1, I64 a2) {
  if (g_icall_hook) return (I64)g_icall_hook(t, (uint64_t)a0, (uint64_t)a1, (uint64_t)a2, 0);
  return ((int64_t (*)(int64_t, int64_t, int64_t))gui_resolve_fn(t))(a0, a1, a2);
}
static GuiResProvider g_res_provider;
void gui_set_resource_provider(GuiResProvider p) { g_res_provider = p; }
GuiResProvider gui_get_resource_provider(void) { return g_res_provider; }
/* フック (gui_core_ext.inc): WH_* の内部ディスパッチ。id = WH_* (-1..14) */
static int hook_any(int id);
static I64 hook_run(int id, int code, U64 wp, I64 lp);
enum { WH_MSGFILTER = -1, WH_KEYBOARD = 2, WH_GETMESSAGE = 3, WH_CALLWNDPROC = 4, WH_MOUSE = 7, WH_CALLWNDPROCRET = 12 };
I64 gui_call2(U64 t, I64 a0, I64 a1) {
  if (g_icall_hook) return (I64)g_icall_hook(t, (uint64_t)a0, (uint64_t)a1, 0, 0);
  return ((int64_t (*)(int64_t, int64_t))gui_resolve_fn(t))(a0, a1);
}

/* ================= ウィンドウツリー ================= */
Wnd *wnd_from_h(U64 h) { return (Wnd *)h_get(h, HT_WND); }
static void link_child(Wnd *p, Wnd *w) {
  w->parent = p; w->prev = p->last; w->next = NULL;
  if (p->last) p->last->next = w; else p->first = w;
  p->last = w;
}
static void unlink_child(Wnd *w) {
  Wnd *p = w->parent;
  if (!p) return;
  if (w->prev) w->prev->next = w->next; else p->first = w->next;
  if (w->next) w->next->prev = w->prev; else p->last = w->prev;
  w->prev = w->next = NULL;
}
static int is_toplevel(Wnd *w) { return w->parent == g_desktop; }
static Wnd *toplevel_of(Wnd *w) { while (w && w->parent != g_desktop) w = w->parent; return w; }
static int is_visible(Wnd *w) {
  for (; w && w != g_desktop; w = w->parent) if (!(w->style & WS_VISIBLE)) return 0;
  return 1;
}
static int ww(Wnd *w) { return w->nl + w->w + w->nr; }
static int wh(Wnd *w) { return w->nt + w->hgt + w->nb; }
int wnd_target(Wnd *w, int *surf, int *ox, int *oy) {   /* top-level surface と w の client 原点 (surface 座標) */
  int x = 0, y = 0;
  while (w && w->parent != g_desktop) { x += w->x + w->nl; y += w->y + w->nt; w = w->parent; }
  if (!w) return 0;
  *surf = w->surf; *ox = x + w->nl; *oy = y + w->nt;
  return 1;
}
void wnd_client_size(Wnd *w, int *cw, int *ch) { *cw = w->w; *ch = w->hgt; }
static void to_screen_origin(Wnd *w, int *sx, int *sy) {
  int x = 0, y = 0;
  while (w && w != g_desktop) { x += w->x + w->nl; y += w->y + w->nt; w = w->parent; }
  *sx = x; *sy = y;
}
static void wnd_clip_impl(Wnd *w, RL *out, int win) {   /* win=1: window DC (NC を含む window rect) */
  rl_clear(out);
  if (!is_visible(w)) return;
  int surf, ox, oy;
  if (!wnd_target(w, &surf, &ox, &oy)) return;
  WRECT r = win ? (WRECT){ ox - w->nl, oy - w->nt, ox - w->nl + ww(w), oy - w->nt + wh(w) } : (WRECT){ ox, oy, ox + w->w, oy + w->hgt };
  /* 祖先 client に収める */
  int ax = ox, ay = oy;
  for (Wnd *a = w; a->parent != g_desktop; a = a->parent) {
    ax -= a->x + a->nl; ay -= a->y + a->nt;  /* a->parent の client 原点 (surface 座標) */
    Wnd *p = a->parent;
    if (p->parent == g_desktop || 1) {
      WRECT pc = { ax, ay, ax + p->w, ay + p->hgt };
      r = r_isect(r, pc);
    }
  }
  rl_add(out, r);
  if ((w->style & WS_CLIPSIBLINGS) && w->parent != g_desktop) {
    int px = ox - w->x - w->nl, py = oy - w->y - w->nt;
    for (Wnd *s = w->next; s; s = s->next)
      if (s->style & WS_VISIBLE) rl_subtract_rect(out, (WRECT){ px + s->x, py + s->y, px + s->x + ww(s), py + s->y + wh(s) });
  }
  if (w->style & WS_CLIPCHILDREN)
    for (Wnd *c = w->first; c; c = c->next)
      if (c->style & WS_VISIBLE) rl_subtract_rect(out, (WRECT){ ox + c->x, oy + c->y, ox + c->x + ww(c), oy + c->y + wh(c) });
}
void wnd_clip(Wnd *w, RL *out) { wnd_clip_impl(w, out, 0); }
void wnd_clip_window(Wnd *w, RL *out) { wnd_clip_impl(w, out, 1); }
void wnd_window_origin(Wnd *w, int *ox, int *oy) { int s; wnd_target(w, &s, ox, oy); *ox -= w->nl; *oy -= w->nt; }

/* ================= z-order / 非クライアント領域 ================= */
enum { WS_BORDER_ = 0x00800000, WS_DLGFRAME_ = 0x00400000, WS_THICKFRAME_ = 0x00040000, WS_EX_TOPMOST_ = 8, WS_EX_TRANSPARENT_ = 0x20,
       WS_EX_CLIENTEDGE_ = 0x200, WS_EX_NOACTIVATE_ = 0x08000000, HT_NOWHERE = 0, HT_CLIENT = 1, HT_CAPTION = 2, HT_BORDER = 18, HT_TRANSPARENT = -1 };
static uint32_t next_z(Wnd *w) { return (w->exstyle & WS_EX_TOPMOST_) ? ++g_ztop_tm : ++g_ztop; }
static void link_top(Wnd *w) {   /* desktop の子リスト (= z 順) の最前面へ。ただし非 TOPMOST は TOPMOST の下 */
  unlink_child(w);
  Wnd *p = g_desktop; w->parent = p;
  Wnd *at = p->last;
  if (!(w->exstyle & WS_EX_TOPMOST_)) while (at && (at->exstyle & WS_EX_TOPMOST_)) at = at->prev;
  w->prev = at; w->next = at ? at->next : p->first;
  if (at) at->next = w; else p->first = w;
  if (w->next) w->next->prev = w; else p->last = w;
}
/* DPI 方針 (PROTOCOL.md §12): canvas 内部解像度 = 物理 px。DPI 非対応 (既定) の context には 96 を見せ画素は 1:1、
 * 対応 (SYSTEM/PER_MONITOR 系) の context には dpr*96 を見せ、shim が決める寸法 (NC 幅・システムメトリクス) をその DPI に比例させる。
 * context はプロセス共通の 1 値 (SetThreadDpiAwarenessContext も同じ変数を書く。スレッド別には保持しない)。 */
static I64 g_dpi_ctx = -1;   /* DPI_AWARENESS_CONTEXT_UNAWARE */
int gui_dpi(void) { if (g_dpi_ctx == -1 || g_dpi_ctx == -5) return 96; uint32_t d = gui_sh()->dpr_x100; return (int)((96u * (d ? d : 100) + 50) / 100); }
static int dscale(int v) { return (v * gui_dpi() + 48) / 96; }
static I64 send_message(U64 h, uint32_t msg, U64 wp, I64 lp);
/* 非クライアント幅 (決定的な shim 規約: 実 Windows の DWM 枠とは一致しない。PROTOCOL.md §12) */
static void nc_metrics(uint32_t style, uint32_t ex, int *l, int *t, int *r, int *b) {
  int bw = 0;
  if (style & WS_THICKFRAME_) bw = dscale(5);                                   /* SM_CXFRAME 4 + SM_CXBORDER 1 */
  else if (style & WS_DLGFRAME_) bw = dscale(3);                                /* SM_CXDLGFRAME */
  else if (style & WS_BORDER_) bw = dscale(1);
  if (ex & WS_EX_CLIENTEDGE_) bw += dscale(2);
  int cap = ((style & WS_CAPTION) == WS_CAPTION) ? dscale(23) : 0;
  *l = *r = *b = bw; *t = bw + cap;
}
static WRECT *g_nc_cur;   /* 送信中の NCCALCSIZE_PARAMS.rgrc: lift 済み WndProc は lParam を int32 に切り詰める (REPORT §4-6) ため native (64bit) では下位 32bit 一致で復元 */
/* ウィンドウ矩形 (親 client 座標) を与え WM_NCCALCSIZE で client 寸法と NC 幅を確定 */
static void calc_nc(Wnd *w, int ww_, int wh_) {
  struct { WRECT r[3]; U64 pwp; } p;
  struct { U64 hwnd, after; int32_t x, y, cx, cy; uint32_t flags, _p; } wp = { w->h, 0, w->x, w->y, ww_, wh_, 0, 0 };
  WRECT win = { w->x, w->y, w->x + ww_, w->y + wh_ };
  p.r[0] = p.r[1] = p.r[2] = win; p.pwp = H_(&wp);
  WRECT *saved = g_nc_cur; g_nc_cur = p.r;
  send_message(w->h, WM_NCCALCSIZE, 1, H_(&p));
  g_nc_cur = saved;
  WRECT c = p.r[0];
  if (c.left < win.left) c.left = win.left;
  if (c.top < win.top) c.top = win.top;
  if (c.right > win.right) c.right = win.right;
  if (c.bottom > win.bottom) c.bottom = win.bottom;
  if (c.right < c.left) c.right = c.left;
  if (c.bottom < c.top) c.bottom = c.top;
  w->nl = c.left - win.left; w->nt = c.top - win.top; w->nr = win.right - c.right; w->nb = win.bottom - c.bottom;
  w->w = c.right - c.left; w->hgt = c.bottom - c.top;
  w->nc_dirty = (w->nl | w->nt | w->nr | w->nb) != 0;
}

/* ================= 呼出し ================= */
static int g_send_depth;
static I64 call_proc(Wnd *w, uint32_t msg, U64 wp, I64 lp) {
  g_send_depth++;
  I64 r = gui_call4(w->wndproc, (I64)w->h, (I64)msg, (I64)wp, lp);
  g_send_depth--;
  return r;
}
/* 他スレッド SendMessage 用同期要求 */
typedef struct SyncReq { U64 h; uint32_t msg; U64 wp; I64 lp; I64 result; volatile uint32_t done; } SyncReq;
typedef struct QMsg { U64 hwnd; uint32_t msg; U64 wp; I64 lp; uint32_t time; WPOINT pt; SyncReq *sync; } QMsg;
#define QCAP 8192
static QMsg g_q[QCAP]; static uint32_t g_qh, g_qt;  /* 全て gui_lock 下 */
static void q_push(QMsg m) {
  gui_lock();
  if (g_qt - g_qh >= QCAP) { gui_unlock(); gui_failfast("PostMessage", "message queue overflow (8192)"); }
  g_q[g_qt++ % QCAP] = m;
  gui_unlock();
  gui_doorbell();
}

/* SendMessage 経路の呼出し: WH_CALLWNDPROC / WH_CALLWNDPROCRET を挟む (キュー経由 = DispatchMessage には掛けない: Windows と同じ) */
static I64 call_proc_sent(Wnd *w, uint32_t msg, U64 wp, I64 lp) {
  if (!hook_any(WH_CALLWNDPROC) && !hook_any(WH_CALLWNDPROCRET)) return call_proc(w, msg, wp, lp);
  struct { I64 lParam; U64 wParam; uint32_t message, _pad; U64 hwnd; } cwp = { lp, wp, msg, 0, w->h };
  if (hook_any(WH_CALLWNDPROC)) hook_run(WH_CALLWNDPROC, 0, 1, (I64)(uintptr_t)&cwp);
  I64 r = call_proc(w, cwp.message, cwp.wParam, cwp.lParam);
  if (hook_any(WH_CALLWNDPROCRET)) {
    struct { I64 lResult; I64 lParam; U64 wParam; uint32_t message, _pad; U64 hwnd; } cwr = { r, cwp.lParam, cwp.wParam, cwp.message, 0, w->h };
    hook_run(WH_CALLWNDPROCRET, 0, 1, (I64)(uintptr_t)&cwr);
  }
  return r;
}
static I64 send_message(U64 h, uint32_t msg, U64 wp, I64 lp) {
  Wnd *w = wnd_from_h(h);
  if (!w) return 0;
  if (g_gui_tid && w->tid && w->tid != gui_thread_id()) {
    SyncReq rq = { h, msg, wp, lp, 0, 0 };
    QMsg m = { h, msg, wp, lp, 0, {0, 0}, &rq };
    q_push(m);
    while (!__atomic_load_n(&rq.done, __ATOMIC_ACQUIRE)) gui_futex_wait(&rq.done, 0, 10);
    return rq.result;
  }
  return call_proc_sent(w, msg, wp, lp);
}

/* ================= クラス ================= */
static Class *find_class(const char *name, U64 atom) {
  for (Class *c = g_classes; c; c = c->next) {
    if (name) { if (!strcasecmp(c->name, name)) return c; }
    else if (c->atom == atom) return c;
  }
  return NULL;
}
static const char *predefined[] = { "BUTTON", "STATIC", "EDIT", "LISTBOX", "COMBOBOX", "SCROLLBAR", "MDICLIENT",
                                    "#32768", "#32770", "ComboLBox", "tooltips_class32", "SysListView32", "msctls_trackbar32", NULL };

static API register_class_impl(const WWNDCLASS *c, U64 exsize, int wide) {
  char buf[256]; const char *n = str_in(c->lpszClassName, wide, buf, sizeof buf);
  (void)exsize;
  if (!n) gui_failfast("RegisterClass", "atom class names not supported");
  if (find_class(n, 0)) { gui_set_last_error(1410); return 0; }  /* ERROR_CLASS_ALREADY_EXISTS */
  Class *k = (Class *)calloc(1, sizeof *k);
  snprintf(k->name, sizeof k->name, "%s", n);
  k->atom = g_next_atom++; k->style = c->style; k->wndproc = c->lpfnWndProc; k->cbcls = c->cbClsExtra;
  k->cbwnd = c->cbWndExtra; k->hinst = c->hInstance; k->hicon = c->hIcon; k->hcursor = c->hCursor;
  k->hbrbg = c->hbrBackground; k->wide = wide;
  if (k->cbcls > 0) k->extra = (uint8_t *)calloc(1, (size_t)k->cbcls);
  gui_lock(); k->next = g_classes; g_classes = k; gui_unlock();
  return k->atom;
}
API RegisterClassA(I64 lpWndClass) { gui_sh(); return register_class_impl((const WWNDCLASS *)P_(lpWndClass), 0, 0); }
API RegisterClassW(I64 lpWndClass) { gui_sh(); return register_class_impl((const WWNDCLASS *)P_(lpWndClass), 0, 1); }
static API register_classex(I64 p, int wide) {
  gui_sh();
  const WWNDCLASSEX *e = (const WWNDCLASSEX *)P_(p);
  WWNDCLASS c = { e->style, 0, e->lpfnWndProc, e->cbClsExtra, e->cbWndExtra, e->hInstance, e->hIcon, e->hCursor,
                  e->hbrBackground, e->lpszMenuName, e->lpszClassName };
  return register_class_impl(&c, 0, wide);
}
API RegisterClassExA(I64 p) { return register_classex(p, 0); }
API RegisterClassExW(I64 p) { return register_classex(p, 1); }
static API unregister_class(I64 name, I64 hinst, int wide) {
  (void)hinst; char buf[256]; const char *n = str_in((U64)name, wide, buf, sizeof buf);
  gui_lock();
  for (Class **pp = &g_classes; *pp; pp = &(*pp)->next) {
    if ((n && !strcasecmp((*pp)->name, n)) || (!n && (*pp)->atom == (U64)name)) {
      Class *k = *pp; *pp = k->next; free(k->extra); free(k); gui_unlock(); return 1;
    }
  }
  gui_unlock(); gui_set_last_error(1411); return 0;
}
API UnregisterClassA(I64 n, I64 h) { return unregister_class(n, h, 0); }
API UnregisterClassW(I64 n, I64 h) { return unregister_class(n, h, 1); }
static API get_class_info(I64 hinst, I64 name, I64 out, int wide) {
  (void)hinst; char buf[256]; const char *n = str_in((U64)name, wide, buf, sizeof buf);
  Class *k = n ? find_class(n, 0) : find_class(NULL, (U64)name);
  if (!k) { gui_set_last_error(1411); return 0; }
  WWNDCLASS *c = (WWNDCLASS *)P_(out);
  memset(c, 0, sizeof *c);
  c->style = k->style; c->lpfnWndProc = k->wndproc; c->cbClsExtra = k->cbcls; c->cbWndExtra = k->cbwnd;
  c->hInstance = k->hinst; c->hIcon = k->hicon; c->hCursor = k->hcursor; c->hbrBackground = k->hbrbg;
  return k->atom;
}
API GetClassInfoA(I64 hi, I64 n, I64 o) { return get_class_info(hi, n, o, 0); }
API GetClassInfoW(I64 hi, I64 n, I64 o) { return get_class_info(hi, n, o, 1); }

/* ================= ウィンドウ ================= */
static void ensure_desktop(void) {
  GuiShared *sh = gui_sh();
  if (g_desktop) return;
  gui_lock();
  if (!g_desktop) {
    Wnd *d = (Wnd *)calloc(1, sizeof *d);
    d->w = (int32_t)sh->screen_w; d->hgt = (int32_t)sh->screen_h; d->style = WS_VISIBLE; d->surf = -1;
    d->h = h_alloc(HT_WND, d);
    snprintf(d->title, sizeof d->title, "Desktop");
    g_desktop = d;
  }
  gui_unlock();
}
API GetDesktopWindow(void) { ensure_desktop(); return (I64)g_desktop->h; }

static void invalidate(Wnd *w, const WRECT *r, int erase, int children);
static void activate(Wnd *top);
static void set_focus_internal(Wnd *w);

static void post_size_move(Wnd *w) {
  send_message(w->h, WM_SIZE, 0, ((I64)(w->hgt & 0xFFFF) << 16) | (w->w & 0xFFFF));
  send_message(w->h, WM_MOVE, 0, ((I64)(w->y & 0xFFFF) << 16) | (w->x & 0xFFFF));
}

static API create_window_impl(uint32_t exstyle, I64 cls, I64 name, uint32_t style, int32_t x, int32_t y, int32_t cx,
                              int32_t cy, I64 parent, I64 menu, I64 hinst, I64 param, int wide) {
  gui_sh(); ensure_desktop();
  char cbuf[256], nbuf[256];
  const char *cn = str_in((U64)cls, wide, cbuf, sizeof cbuf);
  const char *tn = str_in((U64)name, wide, nbuf, sizeof nbuf);
  Class *k = cn ? find_class(cn, 0) : find_class(NULL, (U64)cls);
  if (!k) {
    if (cn) for (const char **p = predefined; *p; p++)
      if (!strcasecmp(*p, cn)) { char m[200]; snprintf(m, sizeof m, "predefined window class \"%s\"", cn); gui_failfast("CreateWindowEx", m); }
    gui_set_last_error(1407); return 0;
  }
  Wnd *par = parent ? wnd_from_h((U64)parent) : NULL;
  if ((style & WS_CHILD) && !par) { gui_set_last_error(1400); return 0; }
  if (!(style & WS_CHILD)) par = NULL;
  if (!g_gui_tid) g_gui_tid = gui_thread_id();
  Wnd *w = (Wnd *)calloc(1, sizeof *w);
  w->cls = k; w->style = style & ~(uint32_t)WS_VISIBLE; w->exstyle = exstyle; w->wide = wide; w->surf = -1;
  w->wndproc = k->wndproc; w->hinst = (U64)hinst; w->tid = gui_thread_id();
  if (tn) snprintf(w->title, sizeof w->title, "%s", tn);
  if (x == (int32_t)0x80000000) x = 0;
  if (y == (int32_t)0x80000000) y = 0;
  if (cx == (int32_t)0x80000000) cx = 640;
  if (cy == (int32_t)0x80000000) cy = 480;
  w->x = x; w->y = y; w->w = cx < 0 ? 0 : cx; w->hgt = cy < 0 ? 0 : cy;   /* NC 確定 (WM_NCCALCSIZE) まで window rect = client */
  w->id = (style & WS_CHILD) ? (U64)menu : 0;
  w->cbextra = k->cbwnd; if (w->cbextra > 0) w->extra = (uint8_t *)calloc(1, (size_t)w->cbextra);
  w->h = h_alloc(HT_WND, w);
  if (par) link_child(par, w); else link_top(w);
  if (!par) { w->surf = surf_alloc(x, y, w->w, w->hgt, w->title); if (exstyle & WS_EX_TOPMOST_) gui_sh()->surf[w->surf].z = ++g_ztop_tm; }
  /* CREATESTRUCT (Win64 layout, 88B) */
  struct { U64 lpCreateParams, hInstance, hMenu, hwndParent; int32_t cy, cx, y, x; uint32_t style, _p; U64 lpszName, lpszClass;
           uint32_t dwExStyle, _p2; } cs = { (U64)param, (U64)hinst, (U64)menu, (U64)parent, cy, cx, y, x, style, 0,
                                           (U64)name, (U64)cls, exstyle, 0 };
  I64 r = send_message(w->h, WM_NCCREATE, 0, H_(&cs));
  if (!r) { Wnd *dead = w; send_message(dead->h, WM_NCDESTROY, 0, 0); unlink_child(dead); if (dead->surf >= 0) surf_free(dead->surf); h_free(dead->h); rl_free(&dead->invl); free(dead->extra); free(dead); return 0; }
  calc_nc(w, w->w, w->hgt);
  r = send_message(w->h, WM_CREATE, 0, H_(&cs));
  if ((int32_t)r == -1) {
    send_message(w->h, WM_DESTROY, 0, 0); send_message(w->h, WM_NCDESTROY, 0, 0);
    unlink_child(w); if (w->surf >= 0) surf_free(w->surf); h_free(w->h); rl_free(&w->invl); free(w->extra); free(w);
    return 0;
  }
  if (style & WS_VISIBLE) {
    w->style |= WS_VISIBLE;
    send_message(w->h, WM_SHOWWINDOW, 1, 0);
    post_size_move(w);
    if (!par) { GuiShared *sh = gui_sh(); sh->surf[w->surf].visible = 1; out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)w->surf, 0, 0, 0, 0, 0); if (!(exstyle & WS_EX_NOACTIVATE_)) activate(w); }
    invalidate(w, NULL, 1, 1);
  } else post_size_move(w);
  return (I64)w->h;
}
API CreateWindowExA(I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g, I64 h, I64 i, I64 j, I64 k, I64 l) {
  return create_window_impl((uint32_t)a, b, c, (uint32_t)d, (int32_t)e, (int32_t)f, (int32_t)g, (int32_t)h, i, j, k, l, 0);
}
API CreateWindowExW(I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g, I64 h, I64 i, I64 j, I64 k, I64 l) {
  return create_window_impl((uint32_t)a, b, c, (uint32_t)d, (int32_t)e, (int32_t)f, (int32_t)g, (int32_t)h, i, j, k, l, 1);
}

static void remove_timers_for(Wnd *w);
static void destroy_tree(Wnd *w) {
  w->destroying = 1;
  if (g_capture == w) g_capture = NULL;
  if (g_focus == w) g_focus = NULL;
  if (g_active == w) g_active = NULL;
  send_message(w->h, WM_DESTROY, 0, 0);
  while (w->first) destroy_tree(w->first);
  remove_timers_for(w);
  send_message(w->h, WM_NCDESTROY, 0, 0);
  unlink_child(w);
  if (w->surf >= 0) surf_free(w->surf);
  h_free(w->h);
  while (w->props) { struct Prop *p = w->props; w->props = p->next; free(p); }
  rl_free(&w->invl); free(w->extra); free(w);
}
API DestroyWindow(I64 h) {
  Wnd *w = wnd_from_h((U64)h);
  if (!w || w == g_desktop) return 0;
  if (w->destroying) return 1;
  if (w->tid != gui_thread_id()) gui_failfast("DestroyWindow", "cross-thread destroy not supported");
  int top = is_toplevel(w);
  destroy_tree(w);
  if (top) { /* 前面の別 window を active に */
    if (!g_active) for (Wnd *t = g_desktop->last; t; t = t->prev) if (t->style & WS_VISIBLE) { activate(t); break; }
  }
  return 1;
}
API IsWindow(I64 h) { return wnd_from_h((U64)h) != NULL; }
API IsWindowVisible(I64 h) { Wnd *w = wnd_from_h((U64)h); return w && is_visible(w); }
API IsWindowEnabled(I64 h) { Wnd *w = wnd_from_h((U64)h); return w && !(w->style & WS_DISABLED); }
API EnableWindow(I64 h, I64 en) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  int was = !!(w->style & WS_DISABLED);
  if ((en != 0) == was) { if (en) w->style &= ~(uint32_t)WS_DISABLED; else w->style |= WS_DISABLED; send_message(w->h, WM_ENABLE, en ? 1 : 0, 0); }
  return was;
}
API GetParent(I64 h) { Wnd *w = wnd_from_h((U64)h); return (w && w->parent && w->parent != g_desktop) ? (I64)w->parent->h : 0; }
API GetWindow(I64 h, I64 cmd) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  Wnd *r = NULL;
  switch ((int)cmd) {
    case 0: r = w->parent ? w->parent->last : NULL; break;   /* GW_HWNDFIRST : z 最上位 */
    case 1: r = w->parent ? w->parent->first : NULL; break;  /* GW_HWNDLAST : 最背面 */
    case 2: r = w->prev; break;                              /* GW_HWNDNEXT : z で一つ下 */
    case 3: r = w->next; break;                              /* GW_HWNDPREV : 一つ上 */
    case 5: r = w->last; break;                              /* GW_CHILD : 最前面の子 */
    default: r = NULL;                                       /* GW_OWNER 等 */
  }
  return r ? (I64)r->h : 0;
}
API GetAncestor(I64 h, I64 flags) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  if (flags == 2) return (I64)toplevel_of(w)->h;                    /* GA_ROOT */
  if (flags == 1) return (w->parent && w->parent != g_desktop) ? (I64)w->parent->h : 0; /* GA_PARENT */
  return (I64)toplevel_of(w)->h;
}
API IsChild(I64 hp, I64 hc) {
  Wnd *p = wnd_from_h((U64)hp), *c = wnd_from_h((U64)hc);
  for (; c; c = c->parent) if (c->parent == p && p) return 1;
  return 0;
}
API GetClientRect(I64 h, I64 rc) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  WRECT *r = (WRECT *)P_(rc); r->left = r->top = 0; r->right = w->w; r->bottom = w->hgt; return 1;
}
API GetWindowRect(I64 h, I64 rc) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  int sx, sy; to_screen_origin(w, &sx, &sy); sx -= w->nl; sy -= w->nt;
  WRECT *r = (WRECT *)P_(rc); r->left = sx; r->top = sy; r->right = sx + ww(w); r->bottom = sy + wh(w); return 1;
}
API ClientToScreen(I64 h, I64 pt) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  int sx, sy; to_screen_origin(w, &sx, &sy);
  WPOINT *p = (WPOINT *)P_(pt); p->x += sx; p->y += sy; return 1;
}
API ScreenToClient(I64 h, I64 pt) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  int sx, sy; to_screen_origin(w, &sx, &sy);
  WPOINT *p = (WPOINT *)P_(pt); p->x -= sx; p->y -= sy; return 1;
}
API MapWindowPoints(I64 hf, I64 ht, I64 pts, I64 n) {
  int fx = 0, fy = 0, tx = 0, ty = 0;
  Wnd *f = hf ? wnd_from_h((U64)hf) : NULL, *t = ht ? wnd_from_h((U64)ht) : NULL;
  if (f) to_screen_origin(f, &fx, &fy);
  if (t) to_screen_origin(t, &tx, &ty);
  WPOINT *p = (WPOINT *)P_(pts);
  for (int i = 0; i < (int)n; i++) { p[i].x += fx - tx; p[i].y += fy - ty; }
  return ((I64)(uint16_t)(fy - ty) << 16) | (uint16_t)(fx - tx);
}

static void apply_geometry(Wnd *w, int x, int y, int cw, int ch, int moved, int sized) {   /* cw, ch = window rect の寸法 */
  w->x = x; w->y = y;
  if (is_toplevel(w) && w->surf >= 0) {
    GuiSurface *s = &gui_sh()->surf[w->surf];
    s->x = x; s->y = y;
    if (sized) surf_resize(w->surf, cw, ch);
    out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)w->surf, 0, 0, 0, 0, 0);
  }
  if (sized) calc_nc(w, cw, ch); else { w->w = cw - w->nl - w->nr; w->hgt = ch - w->nt - w->nb; }
  if (sized) {
    send_message(w->h, WM_SIZE, 0, ((I64)(w->hgt & 0xFFFF) << 16) | (w->w & 0xFFFF));
    invalidate(w, NULL, 1, 1);
  }
  if (moved) send_message(w->h, WM_MOVE, 0, ((I64)(y & 0xFFFF) << 16) | (x & 0xFFFF));
  if (moved && !is_toplevel(w) && w->parent) invalidate(w->parent, NULL, 1, 0);
}
API MoveWindow(I64 h, I64 x, I64 y, I64 cw, I64 ch, I64 repaint) {
  (void)repaint;
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  apply_geometry(w, (int)x, (int)y, (int)cw, (int)ch, w->x != (int)x || w->y != (int)y, ww(w) != (int)cw || wh(w) != (int)ch);
  return 1;
}
static void show_internal(Wnd *w, int show);
static int g_noact;   /* SW_SHOWNA / SWP_NOACTIVATE 中は show で activate しない */
API SetWindowPos(I64 h, I64 after, I64 x, I64 y, I64 cx, I64 cy, I64 flags) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  int nx = (flags & SWP_NOMOVE) ? w->x : (int)x, ny = (flags & SWP_NOMOVE) ? w->y : (int)y;
  int nw = (flags & SWP_NOSIZE) ? ww(w) : (int)cx, nh = (flags & SWP_NOSIZE) ? wh(w) : (int)cy;
  if (!(flags & SWP_NOZORDER) && w->parent) {
    Wnd *p = w->parent;
    if (after == HWND_BOTTOM_ || after == HWND_TOP_ || after == -1 || after == -2) {
      if (after == -1 && is_toplevel(w)) w->exstyle |= WS_EX_TOPMOST_;   /* HWND_TOPMOST / HWND_NOTOPMOST */
      if ((after == -2 || after == HWND_BOTTOM_) && is_toplevel(w)) w->exstyle &= ~(uint32_t)WS_EX_TOPMOST_;   /* NOTOPMOST / BOTTOM は topmost を外す (MSDN) */
      unlink_child(w);
      if (after == HWND_BOTTOM_) { w->parent = p; w->next = p->first; w->prev = NULL; if (p->first) p->first->prev = w; else p->last = w; p->first = w; }
      else if (is_toplevel(w)) link_top(w);
      else link_child(p, w);
      if (is_toplevel(w) && w->surf >= 0) { gui_sh()->surf[w->surf].z = (after == HWND_BOTTOM_) ? 0 : next_z(w); out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)w->surf, 0, 0, 0, 0, 0); }
    } else if (wnd_from_h((U64)after)) {
      Wnd *a = wnd_from_h((U64)after);
      if (is_toplevel(w) && ((w->exstyle ^ a->exstyle) & WS_EX_TOPMOST_)) {   /* TOPMOST 群と非 TOPMOST 群は跨がない: 各群の先頭 (link_top) へ */
        link_top(w);
        if (w->surf >= 0) { gui_sh()->surf[w->surf].z = next_z(w); out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)w->surf, 0, 0, 0, 0, 0); }
      } else {
        unlink_child(w);
        w->parent = p; w->prev = a; w->next = a->next;
        if (a->next) a->next->prev = w; else p->last = w;
        a->next = w;
        if (is_toplevel(w) && w->surf >= 0) { gui_sh()->surf[w->surf].z = gui_sh()->surf[a->surf].z; out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)w->surf, 0, 0, 0, 0, 0); }
      }
    }
  }
  apply_geometry(w, nx, ny, nw, nh, w->x != nx || w->y != ny, ww(w) != nw || wh(w) != nh);
  g_noact = (flags & SWP_NOACTIVATE) != 0;
  if (flags & SWP_SHOWWINDOW) show_internal(w, 1);
  g_noact = 0;
  if (flags & SWP_HIDEWINDOW) show_internal(w, 0);
  return 1;
}

static void show_internal(Wnd *w, int show) {
  int was = !!(w->style & WS_VISIBLE);
  if (show == was) return;
  if (show) w->style |= WS_VISIBLE; else w->style &= ~(uint32_t)WS_VISIBLE;
  send_message(w->h, WM_SHOWWINDOW, show ? 1 : 0, 0);
  if (is_toplevel(w) && w->surf >= 0) {
    gui_sh()->surf[w->surf].visible = show ? 1 : 0;
    out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)w->surf, 0, 0, 0, 0, 0);
    if (show) { if (!(w->exstyle & WS_EX_NOACTIVATE_) && !g_noact) activate(w); }
    else if (g_active == w) { g_active = NULL; for (Wnd *t = g_desktop->last; t; t = t->prev) if ((t->style & WS_VISIBLE) && t != w) { activate(t); break; } }
  }
  if (show) invalidate(w, NULL, 1, 1);
  else if (w->parent && w->parent != g_desktop) invalidate(w->parent, NULL, 1, 0);
}
API ShowWindow(I64 h, I64 cmd) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  int was = !!(w->style & WS_VISIBLE);
  g_noact = (cmd == SW_SHOWNA || cmd == 4 /* SW_SHOWNOACTIVATE */);
  show_internal(w, cmd != SW_HIDE);
  g_noact = 0;
  return was;
}

/* ---- 属性 ---- */
static I64 get_long(Wnd *w, int idx) {
  switch (idx) {
    case GWL_STYLE: return (I64)(int32_t)w->style;
    case GWL_EXSTYLE: return (I64)(int32_t)w->exstyle;
    case GWLP_WNDPROC: return (I64)w->wndproc;
    case GWLP_HINSTANCE: return (I64)w->hinst;
    case GWLP_ID: return (I64)w->id;
    case GWLP_USERDATA: return (I64)w->userdata;
  }
  if (idx >= 0 && idx + 8 <= w->cbextra) { I64 v; memcpy(&v, w->extra + idx, 8); return v; }
  if (idx >= 0 && idx + 4 <= w->cbextra) { int32_t v; memcpy(&v, w->extra + idx, 4); return v; }
  gui_set_last_error(1413); return 0;
}
static I64 set_long(Wnd *w, int idx, I64 v) {
  I64 old = get_long(w, idx);
  switch (idx) {
    case GWL_STYLE: w->style = (uint32_t)v; return old;
    case GWL_EXSTYLE: w->exstyle = (uint32_t)v; return old;
    case GWLP_WNDPROC: w->wndproc = (U64)v; return old;
    case GWLP_HINSTANCE: w->hinst = (U64)v; return old;
    case GWLP_ID: w->id = (U64)v; return old;
    case GWLP_USERDATA: w->userdata = (U64)v; return old;
  }
  if (idx >= 0 && idx + 8 <= w->cbextra) { memcpy(w->extra + idx, &v, 8); return old; }
  if (idx >= 0 && idx + 4 <= w->cbextra) { int32_t t = (int32_t)v; memcpy(w->extra + idx, &t, 4); return old; }
  return 0;
}
API GetWindowLongPtrA(I64 h, I64 i) { Wnd *w = wnd_from_h((U64)h); return w ? get_long(w, (int)i) : 0; }
API GetWindowLongPtrW(I64 h, I64 i) { return GetWindowLongPtrA(h, i); }
API SetWindowLongPtrA(I64 h, I64 i, I64 v) { Wnd *w = wnd_from_h((U64)h); return w ? set_long(w, (int)i, v) : 0; }
API SetWindowLongPtrW(I64 h, I64 i, I64 v) { return SetWindowLongPtrA(h, i, v); }
API GetWindowLongA(I64 h, I64 i) { return (int32_t)GetWindowLongPtrA(h, i); }
API GetWindowLongW(I64 h, I64 i) { return (int32_t)GetWindowLongPtrA(h, i); }
API SetWindowLongA(I64 h, I64 i, I64 v) { return (int32_t)SetWindowLongPtrA(h, i, (int32_t)v); }
API SetWindowLongW(I64 h, I64 i, I64 v) { return (int32_t)SetWindowLongPtrA(h, i, (int32_t)v); }
static API set_text(I64 h, I64 s, int wide) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  char b[256]; const char *t = str_in((U64)s, wide, b, sizeof b);
  snprintf(w->title, sizeof w->title, "%s", t ? t : "");
  if (w->surf >= 0) { snprintf(gui_sh()->surf[w->surf].title, 64, "%s", w->title); out_cmd(GUI_CMD_SET_TITLE, (uint32_t)w->surf, 0, 0, 0, 0, 0); }
  return 1;
}
API SetWindowTextA(I64 h, I64 s) { return set_text(h, s, 0); }
API SetWindowTextW(I64 h, I64 s) { return set_text(h, s, 1); }
API GetWindowTextA(I64 h, I64 buf, I64 n) {
  Wnd *w = wnd_from_h((U64)h); if (!w || n <= 0) return 0;
  int k = (int)strlen(w->title); if (k >= n) k = (int)n - 1; memcpy(P_(buf), w->title, (size_t)k); ((char *)P_(buf))[k] = 0; return k;
}
API GetWindowTextW(I64 h, I64 buf, I64 n) {
  Wnd *w = wnd_from_h((U64)h); if (!w || n <= 0) return 0;
  return u8_to_u16(w->title, (uint16_t *)P_(buf), (int)n);
}
API GetWindowThreadProcessId(I64 h, I64 pid) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  if (pid) *(uint32_t *)P_(pid) = 1;
  return (I64)(w->tid & 0x7fffffff);
}
API AdjustWindowRectEx(I64 rc, I64 style, I64 menu, I64 ex) {
  (void)menu; WRECT *r = (WRECT *)P_(rc); int l, t, rr, b; nc_metrics((uint32_t)style, (uint32_t)ex, &l, &t, &rr, &b);
  r->left -= l; r->top -= t; r->right += rr; r->bottom += b; return 1;
}
API AdjustWindowRect(I64 rc, I64 style, I64 menu) { return AdjustWindowRectEx(rc, style, menu, 0); }

/* ================= 無効領域 / WM_PAINT ================= */
static void invalidate(Wnd *w, const WRECT *r, int erase, int children) {
  WRECT full = { 0, 0, w->w, w->hgt };
  WRECT x = r ? r_isect(*r, full) : full;
  if (!r_empty(x)) {
    if (!w->has_inv) rl_clear(&w->invl);
    RL t = {0}; rl_add(&t, x); rl_union(&w->invl, &t); rl_free(&t);   /* 複数矩形の無効領域 (非重複) */
    if (w->invl.n > 16) { WRECT b; rl_bbox(&w->invl, &b); rl_clear(&w->invl); rl_add(&w->invl, b); }
    rl_bbox(&w->invl, &w->inv); w->has_inv = 1;
    if (erase) w->erase = 1;
  }
  if (children) for (Wnd *c = w->first; c; c = c->next) invalidate(c, NULL, erase, 1);
  gui_doorbell();
}
API InvalidateRect(I64 h, I64 rc, I64 erase) {
  Wnd *w = wnd_from_h((U64)h);
  if (!w) { if (!h) { for (Wnd *t = g_desktop ? g_desktop->first : NULL; t; t = t->next) invalidate(t, NULL, (int)erase, 1); } return 1; }
  invalidate(w, rc ? (const WRECT *)P_(rc) : NULL, erase != 0, 0);
  return 1;
}
API InvalidateRgn(I64 h, I64 hrgn, I64 erase) { (void)hrgn; return InvalidateRect(h, 0, erase); }
API ValidateRect(I64 h, I64 rc) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 1;
  if (!rc) { w->has_inv = 0; w->erase = 0; return 1; }
  const WRECT *r = (const WRECT *)P_(rc);
  if (w->has_inv) {
    rl_subtract_rect(&w->invl, *r);
    if (rl_empty(&w->invl)) { w->has_inv = 0; w->erase = 0; } else rl_bbox(&w->invl, &w->inv);
  }
  return 1;
}
API GetUpdateRect(I64 h, I64 rc, I64 erase) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  if (rc) { WRECT *r = (WRECT *)P_(rc); if (w->has_inv) *r = w->inv; else memset(r, 0, sizeof *r); }
  (void)erase;
  return w->has_inv;
}
API RedrawWindow(I64 h, I64 rc, I64 rgn, I64 flags) {
  (void)rgn;
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  if (flags & RDW_VALIDATE) { ValidateRect(h, rc); if (flags & RDW_ALLCHILDREN) for (Wnd *c = w->first; c; c = c->next) ValidateRect((I64)c->h, 0); }
  if (flags & RDW_INVALIDATE) invalidate(w, rc ? (const WRECT *)P_(rc) : NULL, !!(flags & RDW_ERASE), !!(flags & RDW_ALLCHILDREN));
  if (flags & RDW_UPDATENOW) { extern API UpdateWindow(I64); UpdateWindow(h); }
  return 1;
}
API LockWindowUpdate(I64 h) { (void)h; return 1; }
static void erase_background(Wnd *w, U64 hdc) {
  I64 handled = send_message(w->h, WM_ERASEBKGND, hdc, 0);
  (void)handled;
}
static void nc_paint_if_needed(Wnd *w) {   /* 枠の再描画は WM_PAINT の前に WM_NCPAINT (wParam=1: 全域) */
  if (w->nc_dirty && is_visible(w)) { w->nc_dirty = 0; send_message(w->h, WM_NCPAINT, 1, 0); surf_flush(); }
}
static void do_paint_msg(Wnd *w) { nc_paint_if_needed(w); send_message(w->h, WM_PAINT, 0, 0); }
API UpdateWindow(I64 h) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  if (w->has_inv && is_visible(w)) do_paint_msg(w);
  return 1;
}
API BeginPaint(I64 h, I64 ps) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  WPAINTSTRUCT *p = (WPAINTSTRUCT *)P_(ps);
  memset(p, 0, sizeof *p);
  WRECT rc = w->has_inv ? w->inv : (WRECT){ 0, 0, w->w, w->hgt };
  RL clip = {0}; wnd_clip(w, &clip);
  int surf, ox, oy; wnd_target(w, &surf, &ox, &oy);
  if (w->has_inv) {   /* 無効領域 (複数矩形) だけを描画可能にする */
    RL inv = {0}; rl_copy(&inv, &w->invl);
    for (int i = 0; i < inv.n; i++) { inv.r[i].left += ox; inv.r[i].right += ox; inv.r[i].top += oy; inv.r[i].bottom += oy; }
    rl_intersect(&clip, &inv); rl_free(&inv);
  } else rl_intersect_rect(&clip, (WRECT){ ox + rc.left, oy + rc.top, ox + rc.right, oy + rc.bottom });
  U64 dc = gdi_get_dc_for_wnd(w, 0, &clip);
  rl_free(&clip);
  p->hdc = dc; p->rcPaint = rc;
  int er = w->erase; w->erase = 0; w->has_inv = 0; w->in_paint = 1;
  p->fErase = er;
  if (er) erase_background(w, dc);   /* WM_ERASEBKGND (DefWindowProc は class brush で塗る) */
  gui_sh()->paints++;
  return (I64)dc;
}
API EndPaint(I64 h, I64 ps) {
  Wnd *w = wnd_from_h((U64)h);
  WPAINTSTRUCT *p = (WPAINTSTRUCT *)P_(ps);
  if (w) w->in_paint = 0;
  gdi_release_dc(p->hdc);
  surf_flush();
  return 1;
}
API GetDC(I64 h) {
  gui_sh(); ensure_desktop();
  Wnd *w = h ? wnd_from_h((U64)h) : g_desktop;
  if (!w) return 0;
  if (w == g_desktop) return (I64)gdi_get_screen_dc();   /* GetDC(NULL): 画面 DC。描画は捨てる計測・互換 DC 用途 (#174) */
  RL clip = {0}; wnd_clip(w, &clip);
  U64 dc = gdi_get_dc_for_wnd(w, 0, &clip);
  rl_free(&clip);
  return (I64)dc;
}
API GetDCEx(I64 h, I64 rgn, I64 flags) { (void)rgn; (void)flags; return GetDC(h); }
API GetWindowDC(I64 h) {   /* 原点 = window rect 左上・可視領域は NC を含む */
  gui_sh(); ensure_desktop();
  Wnd *w = h ? wnd_from_h((U64)h) : g_desktop; if (!w) return 0;
  if (w == g_desktop) gui_failfast("GetWindowDC", "screen DC (GetWindowDC(NULL)) not implemented");
  RL clip = {0}; wnd_clip_window(w, &clip);
  U64 dc = gdi_get_dc_for_wnd(w, 1, &clip); rl_free(&clip);
  return (I64)dc;
}
API ReleaseDC(I64 h, I64 dc) { (void)h; gdi_release_dc((U64)dc); surf_flush(); return 1; }

/* ================= フォーカス / キャプチャ / アクティブ ================= */
static void activate(Wnd *top) {
  if (!top || g_active == top) return;
  Wnd *old = g_active; g_active = top;
  if (old) send_message(old->h, WM_ACTIVATE, 0, (I64)top->h);
  if (is_toplevel(top) && top->surf >= 0) {
    link_top(top);
    gui_sh()->surf[top->surf].z = next_z(top); out_cmd(GUI_CMD_SURF_CHANGE, (uint32_t)top->surf, 0, 0, 0, 0, 0);
  }
  send_message(top->h, WM_ACTIVATE, 1, 0);
  if (!g_focus || toplevel_of(g_focus) != top) set_focus_internal(top);
}
static void set_focus_internal(Wnd *w) {
  Wnd *old = g_focus;
  if (old == w) return;
  g_focus = w;
  if (old) send_message(old->h, WM_KILLFOCUS, w ? w->h : 0, 0);
  if (w) send_message(w->h, WM_SETFOCUS, old ? old->h : 0, 0);
}
API SetFocus(I64 h) {
  Wnd *w = h ? wnd_from_h((U64)h) : NULL; Wnd *old = g_focus;
  if (h && !w) return 0;
  set_focus_internal(w);
  return old ? (I64)old->h : 0;
}
API GetFocus(void) { return g_focus ? (I64)g_focus->h : 0; }
API SetActiveWindow(I64 h) { Wnd *w = wnd_from_h((U64)h); Wnd *old = g_active; if (w) activate(toplevel_of(w)); return old ? (I64)old->h : 0; }
API GetActiveWindow(void) { return g_active ? (I64)g_active->h : 0; }
API GetForegroundWindow(void) { return GetActiveWindow(); }
API SetForegroundWindow(I64 h) { Wnd *w = wnd_from_h((U64)h); if (w) activate(toplevel_of(w)); return w != NULL; }
API SetCapture(I64 h) {
  Wnd *w = wnd_from_h((U64)h); Wnd *old = g_capture; if (!w) return 0;
  g_capture = w;
  if (old && old != w) send_message(old->h, WM_CAPTURECHANGED, 0, (I64)w->h);
  ptrlock_update();
  return old ? (I64)old->h : 0;
}
API ReleaseCapture(void) {
  Wnd *old = g_capture; g_capture = NULL;
  if (old) send_message(old->h, WM_CAPTURECHANGED, 0, 0);
  ptrlock_update();
  return 1;
}
API GetCapture(void) { return g_capture ? (I64)g_capture->h : 0; }

/* ================= タイマ ================= */
typedef struct { U64 hwnd; U64 id; uint32_t interval, due; U64 proc; int used; } Timer;
static Timer g_timers[256]; static U64 g_next_timer_id = 1;
API SetTimer(I64 h, I64 id, I64 ms, I64 proc) {
  gui_sh();
  if (ms < 10) ms = 10;   /* USER_TIMER_MINIMUM */
  gui_lock();
  Timer *t = NULL;
  if (h) for (int i = 0; i < 256; i++) if (g_timers[i].used && g_timers[i].hwnd == (U64)h && g_timers[i].id == (U64)id) { t = &g_timers[i]; break; }
  if (!t) for (int i = 0; i < 256; i++) if (!g_timers[i].used) { t = &g_timers[i]; break; }
  if (!t) { gui_unlock(); gui_failfast("SetTimer", "timer table full (256)"); }
  t->used = 1; t->hwnd = (U64)h; t->id = h ? (U64)id : g_next_timer_id++; t->interval = (uint32_t)ms;
  t->due = gui_now_ms() + (uint32_t)ms; t->proc = (U64)proc;
  U64 rid = t->id;
  gui_unlock();
  gui_doorbell();
  return (I64)rid;
}
API KillTimer(I64 h, I64 id) {
  int ok = 0;
  gui_lock();
  for (int i = 0; i < 256; i++) if (g_timers[i].used && g_timers[i].hwnd == (U64)h && g_timers[i].id == (U64)id) { g_timers[i].used = 0; ok = 1; }
  gui_unlock();
  return ok;
}
static void remove_timers_for(Wnd *w) {
  gui_lock();
  for (int i = 0; i < 256; i++) if (g_timers[i].used && g_timers[i].hwnd == w->h) g_timers[i].used = 0;
  gui_unlock();
}

/* ================= メッセージ生成 ================= */
static int wnd_in_filter(U64 hwnd, U64 filt) {
  if (!filt) return 1;
  if (hwnd == filt) return 1;
  Wnd *w = wnd_from_h(hwnd), *f = wnd_from_h(filt);
  for (; w; w = w->parent) if (w == f) return 1;
  return 0;
}
static int g_hit_code = HT_CLIENT;   /* 直近 hit_test の WM_NCHITTEST 結果 */
static Wnd *hit_test(int x, int y, int *lx, int *ly) {
  ensure_desktop();
  g_hit_code = HT_CLIENT;
  for (Wnd *t = g_desktop->last; t; t = t->prev) {
    if (!(t->style & WS_VISIBLE)) continue;
    /* surface z-order : 同 z は後勝ち; ここでは sibling 順 = z 順 (TOPMOST は link_top で常に末尾側) */
    if (x < t->x || y < t->y || x >= t->x + ww(t) || y >= t->y + wh(t)) continue;
    int cx = x - t->x - t->nl, cy = y - t->y - t->nt;
    int inclient = cx >= 0 && cy >= 0 && cx < t->w && cy < t->hgt;
    I64 code = send_message(t->h, WM_NCHITTEST, 0, ((I64)(uint16_t)(int16_t)y << 16) | (uint16_t)(int16_t)x);
    if ((int32_t)code == HT_TRANSPARENT) continue;   /* ツールチップ等: 下の窓へ素通し */
    if (!inclient || (int32_t)code != HT_CLIENT) { g_hit_code = (int32_t)code == HT_CLIENT ? HT_BORDER : (int32_t)code; *lx = cx; *ly = cy; return t; }
    Wnd *cur = t;
    for (;;) {
      Wnd *hit = NULL;
      for (Wnd *c = cur->last; c; c = c->prev) {
        if (!(c->style & WS_VISIBLE)) continue;
        if (cx >= c->x && cy >= c->y && cx < c->x + ww(c) && cy < c->y + wh(c)) { hit = c; break; }
      }
      if (!hit) break;
      cur = hit; cx -= hit->x + hit->nl; cy -= hit->y + hit->nt;
    }
    *lx = cx; *ly = cy;
    return cur;
  }
  return NULL;
}
static void client_of_screen(Wnd *w, int sx, int sy, int *lx, int *ly) {
  int ox, oy; to_screen_origin(w, &ox, &oy); *lx = sx - ox; *ly = sy - oy;
}
static uint8_t g_kb[256];
static uint32_t cur_mods_wparam(GuiShared *sh) {
  uint32_t k = 0;
  if (sh->buttons & 1) k |= MK_LBUTTON;
  if (sh->buttons & 2) k |= MK_RBUTTON;
  if (sh->buttons & 4) k |= MK_MBUTTON;
  if (sh->mods & GUI_MOD_SHIFT) k |= MK_SHIFT;
  if (sh->mods & GUI_MOD_CTRL) k |= MK_CONTROL;
  return k;
}
static void q_push_move_coalesce(QMsg m) {
  gui_lock();
  if (g_qt != g_qh) {
    QMsg *last = &g_q[(g_qt - 1) % QCAP];
    if (last->msg == WM_MOUSEMOVE && last->hwnd == m.hwnd && !last->sync) { *last = m; gui_unlock(); return; }
  }
  gui_unlock();
  q_push(m);
}
static int g_cursor_shape = -1;
static uint32_t g_last_click_t; static int g_last_click_x, g_last_click_y, g_last_click_btn = -1;
static I64 mk_lparam(int x, int y) { return ((I64)(uint16_t)(int16_t)y << 16) | (uint16_t)(int16_t)x; }

static int mouse_hook_discard(Wnd *w, uint32_t msg, int x, int y) {
  if (!hook_any(WH_MOUSE)) return 0;
  struct { WPOINT pt; U64 hwnd; uint32_t hit, _pad; U64 extra; } mh = { { x, y }, w->h, 1 /* HTCLIENT */, 0, 0 };
  return hook_run(WH_MOUSE, 0, msg, (I64)(uintptr_t)&mh) != 0;
}
static void kbd_set_layout(uint32_t langid);                 /* gui_core_ext.inc */
static uint32_t kbd_layout_vk(uint32_t sc, int ext);
static void ime_input(const uint32_t *r);
static void touch_input(const uint32_t *r);
static void translate_input(const uint32_t *r) {
  GuiShared *sh = gui_sh();
  uint32_t type = r[0]; int x = (int32_t)r[2], y = (int32_t)r[3]; uint32_t a = r[4], b = r[5], t = r[6];
  g_msg_time = t; g_msg_pt.x = x; g_msg_pt.y = y;
  switch (type) {
    case GUI_IN_MOUSE_MOVE: case GUI_IN_MOUSE_DOWN: case GUI_IN_MOUSE_UP: case GUI_IN_WHEEL: {
      int lx = 0, ly = 0;
      if (type == GUI_IN_MOUSE_DOWN || type == GUI_IN_MOUSE_UP) ptrlock_update();
      Wnd *w = g_capture;
      if (w) client_of_screen(w, x, y, &lx, &ly);
      else w = hit_test(x, y, &lx, &ly);
      if (!w) return;
      if (!g_capture && g_hit_code != HT_CLIENT && type != GUI_IN_WHEEL) {   /* 非クライアント: WM_NCMOUSEMOVE / WM_NCLBUTTONDOWN|UP (wParam = HT*, lParam = screen) */
        uint32_t nm = type == GUI_IN_MOUSE_MOVE ? 0xA0u : (a == 0 ? 0xA1u : a == 1 ? 0xA7u : 0xA4u) + (type == GUI_IN_MOUSE_UP ? 1 : 0);
        if (type == GUI_IN_MOUSE_DOWN) { Wnd *tp = toplevel_of(w); if (tp != g_active && !(tp->exstyle & WS_EX_NOACTIVATE_)) activate(tp); }
        QMsg m = { w->h, nm, (U64)(int64_t)g_hit_code, mk_lparam(x, y), t, { x, y }, NULL };
        q_push(m); return;
      }
      if (type == GUI_IN_MOUSE_MOVE) {
        if (!g_capture) send_message(w->h, WM_SETCURSOR, w->h, (I64)(1 | (WM_MOUSEMOVE << 16)));
        if (mouse_hook_discard(w, WM_MOUSEMOVE, x, y)) return;
        QMsg m = { w->h, WM_MOUSEMOVE, cur_mods_wparam(sh), mk_lparam(lx, ly), t, { x, y }, NULL };
        q_push_move_coalesce(m);
      } else if (type == GUI_IN_WHEEL) {
        int sx = x, sy = y;
        Wnd *fw = g_focus ? g_focus : w; (void)fw;
        if (mouse_hook_discard(w, WM_MOUSEWHEEL, x, y)) return;
        QMsg m = { w->h, WM_MOUSEWHEEL, ((U64)(uint16_t)(int16_t)(int32_t)a << 16) | cur_mods_wparam(sh), mk_lparam(sx, sy), t, { x, y }, NULL };
        q_push(m);
      } else {
        int btn = (int)a;  /* DOM: 0 L, 1 M, 2 R */
        uint32_t base = btn == 0 ? WM_LBUTTONDOWN : btn == 1 ? WM_MBUTTONDOWN : WM_RBUTTONDOWN;
        uint32_t msg = base + (type == GUI_IN_MOUSE_UP ? 1 : 0);
        if (type == GUI_IN_MOUSE_DOWN) {
          if (!g_capture) { Wnd *tp = toplevel_of(w); if (tp != g_active && !(tp->exstyle & WS_EX_NOACTIVATE_)) activate(tp); }
          int dbl = w->cls && (w->cls->style & CS_DBLCLKS) && g_last_click_btn == btn && (t - g_last_click_t) <= 500 &&
                    abs(x - g_last_click_x) <= 4 && abs(y - g_last_click_y) <= 4;
          if (dbl) { msg = base + 2; g_last_click_btn = -1; }
          else { g_last_click_btn = btn; g_last_click_t = t; g_last_click_x = x; g_last_click_y = y; }
        }
        if (mouse_hook_discard(w, msg, x, y)) return;
        QMsg m = { w->h, msg, cur_mods_wparam(sh), mk_lparam(lx, ly), t, { x, y }, NULL };
        q_push(m);
      }
      return;
    }
    case GUI_IN_LAYOUT: kbd_set_layout(a & 0xFFFF); return;
    case GUI_IN_IME: ime_input(r); return;
    case GUI_IN_TOUCH: touch_input(r); return;
    case GUI_IN_POINTER_LOCK: return;   /* 成立は host 通知。shim 側の状態は持たない (要求は ptrlock_update が出す) */
    case GUI_IN_KEY_DOWN: case GUI_IN_KEY_UP: {
      uint32_t vk = a & 0xFF;
      { uint32_t lvk = kbd_layout_vk((b >> 8) & 0xFF, (b >> 1) & 1); if (lvk) vk = lvk; }   /* 物理キー (scancode) → 現配列の VK */
      if (type == GUI_IN_KEY_DOWN) g_kb[vk] |= 0x80; else g_kb[vk] &= 0x7f;
      Wnd *w = g_focus ? g_focus : g_active;
      if (!w) return;
      int alt = (sh->mods & GUI_MOD_ALT) != 0;
      uint32_t msg = type == GUI_IN_KEY_DOWN ? (alt ? WM_SYSKEYDOWN : WM_KEYDOWN) : (alt ? WM_SYSKEYUP : WM_KEYUP);
      uint32_t scan = (b >> 8) & 0xFF;
      I64 lp = 1 | ((I64)scan << 16) | ((b & 2) ? (1 << 24) : 0) | ((b & 1) ? (1 << 30) : 0) | (type == GUI_IN_KEY_UP ? (3u << 30) : 0) | (alt ? (1 << 29) : 0);
      if (hook_any(WH_KEYBOARD) && hook_run(WH_KEYBOARD, 0, vk, lp)) return;
      QMsg m = { w->h, msg, vk, lp, t, { x, y }, NULL };
      q_push(m);
      return;
    }
    case GUI_IN_CHAR: {
      Wnd *w = g_focus ? g_focus : g_active;
      if (!w) return;
      QMsg m = { w->h, WM_CHAR, a, 1, t, { x, y }, NULL };
      q_push(m);
      return;
    }
    case GUI_IN_FOCUS: {
      if (a) { if (g_active) { send_message(g_active->h, WM_ACTIVATE, 1, 0); } }
      else { memset(g_kb, 0, sizeof g_kb); if (g_active) send_message(g_active->h, WM_ACTIVATE, 0, 0); }
      return;
    }
    case GUI_IN_SCREEN: {
      ensure_desktop(); g_desktop->w = x; g_desktop->hgt = y; return;
    }
    case GUI_IN_CLOSE: {
      Wnd *w = NULL;
      if (r[1] < GUI_MAX_SURF) for (Wnd *tl = g_desktop->first; tl; tl = tl->next) if (tl->surf == (int)r[1]) w = tl;
      if (w) { QMsg m = { w->h, WM_CLOSE, 0, 0, t, {0, 0}, NULL }; q_push(m); }
      return;
    }
  }
}
static void pump_input(void) {
  GuiShared *sh = gui_sh();
  for (;;) {
    uint32_t head = sh->in_ring.head;
    uint32_t tail = __atomic_load_n(&sh->in_ring.tail, __ATOMIC_ACQUIRE);
    if (head == tail) break;
    uint32_t rec[8]; memcpy(rec, sh->in_recs[head & (GUI_IN_RECS - 1)], 32);
    __atomic_store_n(&sh->in_ring.head, head + 1, __ATOMIC_RELEASE);
    sh->in_consumed++;
    translate_input(rec);
  }
}

/* ================= Get/Peek/Dispatch ================= */
static int msg_match(const QMsg *m, U64 hwnd, uint32_t mn, uint32_t mx) {
  if (hwnd && !wnd_in_filter(m->hwnd, hwnd)) return 0;
  if (mn || mx) { if (m->msg < mn || (mx && m->msg > mx)) return 0; }
  return 1;
}
static void fill_msg(WMSG *o, U64 hwnd, uint32_t msg, U64 wp, I64 lp, uint32_t time, WPOINT pt) {
  o->hwnd = hwnd; o->message = msg; o->_pad = 0; o->wParam = wp; o->lParam = lp; o->time = time; o->pt = pt; o->lPrivate = 0;
}
static Wnd *find_paint_rec(Wnd *w, U64 hwnd) {
  if (!(w->style & WS_VISIBLE)) return NULL;
  if (w->has_inv && is_visible(w) && wnd_in_filter(w->h, hwnd)) return w;
  for (Wnd *ch = w->first; ch; ch = ch->next) { Wnd *r = find_paint_rec(ch, hwnd); if (r) return r; }
  return NULL;
}
static Wnd *find_paint(U64 hwnd) {
  ensure_desktop();
  for (Wnd *t = g_desktop->last; t; t = t->prev) { Wnd *r = find_paint_rec(t, hwnd); if (r) return r; }
  return NULL;
}
static int service_sync_requests(void) {
  /* 他スレッド SendMessage 要求を処理 */
  int did = 0;
  for (;;) {
    QMsg m; int found = 0;
    gui_lock();
    for (uint32_t i = g_qh; i != g_qt; i++) {
      QMsg *q = &g_q[i % QCAP];
      if (q->sync) { m = *q; found = 1; for (uint32_t j = i; j + 1 != g_qt; j++) g_q[j % QCAP] = g_q[(j + 1) % QCAP]; g_qt--; break; }
    }
    gui_unlock();
    if (!found) break;
    Wnd *w = wnd_from_h(m.hwnd);
    m.sync->result = w ? call_proc_sent(w, m.msg, m.wp, m.lp) : 0;
    __atomic_store_n(&m.sync->done, 1, __ATOMIC_RELEASE);
    gui_futex_wake(&m.sync->done);
    did = 1;
  }
  return did;
}
/* 見つかれば out に詰めて 1 */
static void pump_drops(void);   /* gui_core_ext.inc: host からの drop 要求を GUI スレッド上で配送 (#172) */
static int try_get(WMSG *out, U64 hwnd, uint32_t mn, uint32_t mx, int remove) {
  GuiShared *sh = gui_sh();
  if (g_any_dirty && gui_now_ms() - g_last_flush >= 16) surf_flush();   /* 描画しっぱなしでも ~60Hz で present */
  service_sync_requests();
  pump_input();
  pump_drops();
  gui_lock();
  for (uint32_t i = g_qh; i != g_qt; i++) {
    QMsg *q = &g_q[i % QCAP];
    if (q->sync || !msg_match(q, hwnd, mn, mx)) continue;
    Wnd *w = wnd_from_h(q->hwnd);
    if (q->hwnd && !w) { /* 死んだ window 宛は捨てる */
      for (uint32_t j = i; j + 1 != g_qt; j++) g_q[j % QCAP] = g_q[(j + 1) % QCAP];
      g_qt--; i--; continue;
    }
    fill_msg(out, q->hwnd, q->msg, q->wp, q->lp, q->time, q->pt);
    if (remove) {
      if (i == g_qh) g_qh++;
      else { for (uint32_t j = i; j + 1 != g_qt; j++) g_q[j % QCAP] = g_q[(j + 1) % QCAP]; g_qt--; }
    }
    gui_unlock();
    return 1;
  }
  gui_unlock();
  if (g_quit_posted && ((!mn && !mx) || (mn <= WM_QUIT && (!mx || mx >= WM_QUIT)))) {
    fill_msg(out, 0, WM_QUIT, (U64)g_quit_code, 0, gui_now_ms(), (WPOINT){0, 0});
    if (remove) g_quit_posted = 0;
    return 1;
  }
  if ((!mn && !mx) || (mn <= WM_PAINT && (!mx || mx >= WM_PAINT))) {
    Wnd *p = find_paint(hwnd);
    if (p) { fill_msg(out, p->h, WM_PAINT, 0, 0, gui_now_ms(), (WPOINT){0, 0}); return 1; }
  }
  if ((!mn && !mx) || (mn <= WM_TIMER && (!mx || mx >= WM_TIMER))) {
    uint32_t now = gui_now_ms();
    gui_lock();
    Timer *best = NULL;
    for (int i = 0; i < 256; i++) {
      Timer *t = &g_timers[i];
      if (!t->used || (int32_t)(now - t->due) < 0) continue;
      if (t->hwnd && !wnd_in_filter(t->hwnd, hwnd)) continue;
      if (!best || (int32_t)(t->due - best->due) < 0) best = t;
    }
    if (best) {
      fill_msg(out, best->hwnd, WM_TIMER, best->id, (I64)best->proc, now, (WPOINT){0, 0});
      if (remove) { best->due = now + best->interval; sh->timer_fires++; }
      gui_unlock();
      return 1;
    }
    gui_unlock();
  }
  return 0;
}
static int32_t next_timer_timeout(void) {
  uint32_t now = gui_now_ms(); int32_t best = -1;
  gui_lock();
  for (int i = 0; i < 256; i++) if (g_timers[i].used) {
    int32_t d = (int32_t)(g_timers[i].due - now); if (d < 0) d = 0;
    if (best < 0 || d < best) best = d;
  }
  gui_unlock();
  return best;
}
static API get_message_impl(I64 lpmsg, I64 hwnd, I64 mn, I64 mx) {
  GuiShared *sh = gui_sh();
  WMSG *m = (WMSG *)P_(lpmsg);
  for (;;) {
    uint32_t seen = __atomic_load_n(&sh->doorbell, __ATOMIC_SEQ_CST);
    if (try_get(m, (U64)hwnd, (uint32_t)mn, (uint32_t)mx, 1)) {
      g_msg_time = m->time; g_msg_pt = m->pt;
      if (hook_any(WH_GETMESSAGE)) hook_run(WH_GETMESSAGE, 0, PM_REMOVE, (I64)(uintptr_t)m);
      return m->message == WM_QUIT ? 0 : 1;
    }
    surf_flush();
    gui_futex_wait(&sh->doorbell, seen, next_timer_timeout());
  }
}
API GetMessageA(I64 a, I64 b, I64 c, I64 d) { return get_message_impl(a, b, c, d); }
API GetMessageW(I64 a, I64 b, I64 c, I64 d) { return get_message_impl(a, b, c, d); }
static API peek_message_impl(I64 lpmsg, I64 hwnd, I64 mn, I64 mx, I64 flags) {
  WMSG *m = (WMSG *)P_(lpmsg);
  gui_sh();
  int ok = try_get(m, (U64)hwnd, (uint32_t)mn, (uint32_t)mx, (flags & PM_REMOVE) != 0);
  if (!ok) surf_flush();
  else if (hook_any(WH_GETMESSAGE)) hook_run(WH_GETMESSAGE, 0, (flags & PM_REMOVE) ? PM_REMOVE : PM_NOREMOVE, (I64)(uintptr_t)m);
  return ok;
}
API PeekMessageA(I64 a, I64 b, I64 c, I64 d, I64 e) { return peek_message_impl(a, b, c, d, e); }
API PeekMessageW(I64 a, I64 b, I64 c, I64 d, I64 e) { return peek_message_impl(a, b, c, d, e); }
API WaitMessage(void) {
  GuiShared *sh = gui_sh();
  for (;;) {
    uint32_t seen = __atomic_load_n(&sh->doorbell, __ATOMIC_SEQ_CST);
    WMSG tmp;
    if (try_get(&tmp, 0, 0, 0, 0)) return 1;
    surf_flush();
    gui_futex_wait(&sh->doorbell, seen, next_timer_timeout());
  }
}
API TranslateMessage(I64 lpmsg) { const WMSG *m = (const WMSG *)P_(lpmsg); return m->message >= WM_KEYDOWN && m->message <= WM_SYSKEYUP; }
static API dispatch_impl(I64 lpmsg) {
  const WMSG *m = (const WMSG *)P_(lpmsg);
  gui_sh();
  gui_sh()->msgs_dispatched++;
  if (m->message == WM_TIMER && m->lParam) {
    return gui_call4((U64)m->lParam, (I64)m->hwnd, WM_TIMER, (I64)m->wParam, (I64)gui_now_ms());
  }
  if (!m->hwnd) return 0;
  Wnd *w = wnd_from_h(m->hwnd);
  if (!w) return 0;
  if (m->message == WM_PAINT && !w->has_inv) return 0;
  if (m->message == WM_PAINT) nc_paint_if_needed(w);
  I64 r = call_proc(w, m->message, m->wParam, m->lParam);
  if (m->message == WM_PAINT) surf_flush();
  return r;
}
API DispatchMessageA(I64 m) { return dispatch_impl(m); }
API DispatchMessageW(I64 m) { return dispatch_impl(m); }
API PostMessageA(I64 h, I64 msg, I64 wp, I64 lp) {
  gui_sh();
  if (h && !wnd_from_h((U64)h)) return 0;
  QMsg m = { (U64)h, (uint32_t)msg, (U64)wp, lp, gui_now_ms(), g_msg_pt, NULL };
  q_push(m); return 1;
}
API PostMessageW(I64 h, I64 msg, I64 wp, I64 lp) { return PostMessageA(h, msg, wp, lp); }
API PostThreadMessageW(I64 tid, I64 msg, I64 wp, I64 lp) { (void)tid; return PostMessageA(0, msg, wp, lp); }
API SendMessageA(I64 h, I64 msg, I64 wp, I64 lp) { gui_sh(); return send_message((U64)h, (uint32_t)msg, (U64)wp, lp); }
API SendMessageW(I64 h, I64 msg, I64 wp, I64 lp) { return SendMessageA(h, msg, wp, lp); }
API CallWindowProcA(I64 proc, I64 h, I64 msg, I64 wp, I64 lp) { return gui_call4((U64)proc, h, msg, wp, lp); }
API CallWindowProcW(I64 proc, I64 h, I64 msg, I64 wp, I64 lp) { return CallWindowProcA(proc, h, msg, wp, lp); }
API PostQuitMessage(I64 code) { gui_sh(); g_quit_posted = 1; g_quit_code = (int)code; gui_doorbell(); return 0; }
API GetMessagePos(void) { return ((I64)(uint16_t)g_msg_pt.y << 16) | (uint16_t)g_msg_pt.x; }
API GetMessageTime(void) { return g_msg_time; }
static char g_regnames[64][96]; static int g_nregnames;
static const char *regmsg_name(uint32_t id) { return (id >= 0xC000 && id < 0xC000u + (uint32_t)g_nregnames) ? g_regnames[id - 0xC000] : NULL; }
API RegisterWindowMessageA(I64 s) {
  const char *p = (const char *)P_(s);
  for (int i = 0; i < g_nregnames; i++) if (!strcmp(g_regnames[i], p)) return 0xC000 + i;
  if (g_nregnames >= 64) gui_failfast("RegisterWindowMessage", "table full");
  snprintf(g_regnames[g_nregnames], 96, "%s", p); return 0xC000 + g_nregnames++;
}
API RegisterWindowMessageW(I64 s) { char b[96]; u16_to_u8((const uint16_t *)P_(s), b, sizeof b); return RegisterWindowMessageA(H_(b)); }
API RegisterClipboardFormatW(I64 s) { return RegisterWindowMessageW(s); }

/* ================= DefWindowProc ================= */
static API defproc_impl(I64 h, I64 msg, I64 wp, I64 lp, int wide) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  switch ((uint32_t)msg) {
    case WM_NCCREATE: return 1;
    case WM_CLOSE: DestroyWindow(h); return 0;
    case WM_PAINT: { w->has_inv = 0; w->erase = 0; return 0; }
    case WM_ERASEBKGND: {
      U64 dc = (U64)wp; U64 br = w->cls ? w->cls->hbrbg : 0;
      if (!br) return 0;
      uint32_t col;
      if (br <= 32) {  /* COLOR_xxx + 1 */
        static const uint32_t sc[] = { 0xC8D0D4, 0x000000, 0x800000, 0x808080, 0xD4D0C8, 0xFFFFFF, 0x000000, 0x000000, 0x000000 };
        int idx = (int)br - 1; col = (idx >= 0 && idx < 9) ? sc[idx] : (idx == 15 ? 0xF0F0F0 : 0xC8D0D4);
        if (idx == COLOR_WINDOW) col = 0xFFFFFF; else if (idx == COLOR_BTNFACE) col = 0xF0F0F0;
      } else { extern int gdi_brush_color(U64, uint32_t *); if (!gdi_brush_color(br, &col)) return 0; }
      WRECT r = { 0, 0, w->w, w->hgt };
      gdi_fill_rect_dc(dc, r, col);
      return 1;
    }
    case WM_NCCALCSIZE: {   /* wParam=1: NCCALCSIZE_PARAMS (rgrc[0] = 新 window rect -> client rect)、0: RECT */
      WRECT *r = (g_nc_cur && (uint32_t)lp == (uint32_t)(uintptr_t)g_nc_cur) ? g_nc_cur : (WRECT *)P_(lp); int l, t, rr, b; nc_metrics(w->style, w->exstyle, &l, &t, &rr, &b);
      r->left += l; r->top += t; r->right -= rr; r->bottom -= b; return 0;
    }
    case WM_NCPAINT: {   /* window DC に枠 (4 辺) とキャプション帯を描く。client は塗らない */
      extern API GetWindowDC(I64); extern API ReleaseDC(I64, I64);
      I64 dc = GetWindowDC(h); if (!dc) return 0;
      int W_ = ww(w), HH = wh(w), bw = w->nl, cap = w->nt - bw; if (cap < 0) cap = 0;
      if (bw) {
        gdi_fill_rect_dc((U64)dc, (WRECT){ 0, 0, W_, bw }, 0x646464); gdi_fill_rect_dc((U64)dc, (WRECT){ 0, HH - w->nb, W_, HH }, 0x646464);
        gdi_fill_rect_dc((U64)dc, (WRECT){ 0, bw, w->nl, HH - w->nb }, 0x646464); gdi_fill_rect_dc((U64)dc, (WRECT){ W_ - w->nr, bw, W_, HH - w->nb }, 0x646464);
      }
      if (cap) gdi_fill_rect_dc((U64)dc, (WRECT){ w->nl, bw, W_ - w->nr, bw + cap }, 0xD1B499);
      ReleaseDC(h, dc); return 0;
    }
    case WM_NCHITTEST: {   /* lParam = screen 座標 */
      int px = (int16_t)(lp & 0xFFFF), py = (int16_t)((lp >> 16) & 0xFFFF), sx, sy; to_screen_origin(w, &sx, &sy);
      int cx = px - sx, cy = py - sy;
      if (cx >= 0 && cy >= 0 && cx < w->w && cy < w->hgt) return HT_CLIENT;
      if (cx < -w->nl || cy < -w->nt || cx >= w->w + w->nr || cy >= w->hgt + w->nb) return HT_NOWHERE;
      int bw = w->nl; return (w->nt > bw && cy < 0 && cy >= -(w->nt - bw)) ? HT_CAPTION : HT_BORDER;
    }
    case WM_SETCURSOR: {
      extern API SetCursor(I64);
      if (w->cls && w->cls->hcursor) SetCursor((I64)w->cls->hcursor);
      return 1;
    }
    case WM_MOUSEACTIVATE: return (w->exstyle & WS_EX_NOACTIVATE_) ? 3 /* MA_NOACTIVATE */ : 1;
    case WM_SHOWWINDOW: case WM_SIZE: case WM_MOVE: case WM_ACTIVATE: case WM_SETFOCUS: case WM_KILLFOCUS:
    case WM_DESTROY: case WM_NCDESTROY: case WM_CREATE: return 0;
    case WM_GETTEXTLENGTH: return (I64)strlen(w->title);
    case WM_GETTEXT: return wide ? GetWindowTextW(h, lp, wp) : GetWindowTextA(h, lp, wp);
    case WM_SETTEXT: return wide ? SetWindowTextW(h, lp) : SetWindowTextA(h, lp);
  }
  return 0;
}
API DefWindowProcA(I64 h, I64 msg, I64 wp, I64 lp) { return defproc_impl(h, msg, wp, lp, 0); }
API DefWindowProcW(I64 h, I64 msg, I64 wp, I64 lp) { return defproc_impl(h, msg, wp, lp, 1); }

/* ================= カーソル / 入力状態 ================= */
API GetCursorPos(I64 pt) { GuiShared *sh = gui_sh(); WPOINT *p = (WPOINT *)P_(pt); p->x = (int32_t)__atomic_load_n(&sh->cursor_x, __ATOMIC_RELAXED); p->y = (int32_t)__atomic_load_n(&sh->cursor_y, __ATOMIC_RELAXED); return 1; }
API GetPhysicalCursorPos(I64 pt) { return GetCursorPos(pt); }
static int g_cursor_cnt;   /* ShowCursor 表示カウンタ (マウス有りの初期値 0 = 表示) */
static int g_cursor_cnt_get(void) { return g_cursor_cnt; }
static WRECT g_cclip; static int g_cclip_on;
API SetCursorPos(I64 x, I64 y) {
  GuiShared *sh = gui_sh(); int32_t cx = (int32_t)x, cy = (int32_t)y;
  if (g_cclip_on) { if (cx < g_cclip.left) cx = g_cclip.left; if (cx >= g_cclip.right) cx = g_cclip.right - 1; if (cy < g_cclip.top) cy = g_cclip.top; if (cy >= g_cclip.bottom) cy = g_cclip.bottom - 1; }
  __atomic_store_n(&sh->cursor_x, cx, __ATOMIC_RELAXED); __atomic_store_n(&sh->cursor_y, cy, __ATOMIC_RELAXED); return 1;
}
API ClipCursor(I64 rc) {
  const WRECT *r = (const WRECT *)P_(rc);
  if (!r) { g_cclip_on = 0; out_cmd(GUI_CMD_CLIP_RECT, 0, 0, 0, 0, 0, 0); return 1; }
  if (r->right <= r->left || r->bottom <= r->top) { gui_set_last_error(87); return 0; }
  g_cclip = *r; g_cclip_on = 1;
  out_cmd(GUI_CMD_CLIP_RECT, 0, (uint32_t)r->left, (uint32_t)r->top, (uint32_t)r->right, (uint32_t)r->bottom, 0);
  return 1;
}
static int g_ptrlock_req;   /* shim が host へ要求中の Pointer Lock 状態 */
static void ptrlock_update(void) {
  int want = g_cursor_cnt_get() < 0 && (g_capture != NULL || (gui_sh()->buttons & 7));
  if (want != g_ptrlock_req) { g_ptrlock_req = want; out_cmd(GUI_CMD_POINTER_LOCK, 0, (uint32_t)want, 0, 0, 0, 0); }
}
API SetPhysicalCursorPos(I64 x, I64 y) { return SetCursorPos(x, y); }
API LoadCursorA(I64 hi, I64 name) { (void)hi; return name < 0x10000 ? (0x7F000000 + name) : 0x7F000000; }
API LoadCursorW(I64 hi, I64 name) { return LoadCursorA(hi, name); }
API LoadIconA(I64 hi, I64 name) { (void)hi; return name < 0x10000 ? (0x7E000000 + name) : 0x7E000001; }
API LoadIconW(I64 hi, I64 name) { return LoadIconA(hi, name); }
int64_t LoadBitmapW(int64_t, int64_t);   /* gui_gdi.c */
int64_t GetObjectW(int64_t, int64_t, int64_t);
/* LoadImageW: IMAGE_BITMAP (0) は LoadBitmapW へ委譲 (拡縮なし)、IMAGE_ICON (1) / IMAGE_CURSOR (2) は hinst=0 の擬似ハンドルのみ (name の ID 制限なしは LoadIconW / LoadCursorW と同じ)。
   LR_SHARED / LR_DEFAULTSIZE は擬似ハンドルが共有で既定寸 (32x32) のため無視してよい。それ以外は未実装として fail-fast。 */
static GUI_NORETURN void liw_fail(const char *why, I64 hinst, I64 name, I64 type, I64 cx, I64 cy, I64 load) {
  char m[192];
  snprintf(m, sizeof m, "%s (hinst=0x%llx name=0x%llx type=%lld cx=%lld cy=%lld load=0x%llx)", why, (unsigned long long)hinst, (unsigned long long)name,
           (long long)type, (long long)cx, (long long)cy, (unsigned long long)load);
  gui_failfast("LoadImageW", m);
}
API LoadImageW(I64 hinst, I64 name, I64 type, I64 cx, I64 cy, I64 load) {
  if ((U64)name >= 0x10000) liw_fail("string resource name", hinst, name, type, cx, cy, load);
  if (load & ~(I64)(0x0040 /* LR_DEFAULTSIZE */ | 0x8000 /* LR_SHARED */)) liw_fail("load flags", hinst, name, type, cx, cy, load);
  if (type == 0 /* IMAGE_BITMAP */) {
    I64 h = LoadBitmapW(hinst, name);
    if (h && (cx || cy)) {
      WBITMAP bm; GetObjectW(h, sizeof bm, (I64)(uintptr_t)&bm);
      if ((cx && cx != bm.bmWidth) || (cy && cy != bm.bmHeight)) liw_fail("IMAGE_BITMAP scaling", hinst, name, type, cx, cy, load);
    }
    return h;
  }
  if (type != 1 /* IMAGE_ICON */ && type != 2 /* IMAGE_CURSOR */) liw_fail("unknown image type", hinst, name, type, cx, cy, load);
  if (hinst) liw_fail("module icon/cursor resource (RT_GROUP_ICON decode not implemented)", hinst, name, type, cx, cy, load);
  if ((cx && cx != 32) || (cy && cy != 32)) liw_fail("icon/cursor scaling (native size 32x32)", hinst, name, type, cx, cy, load);
  return type == 1 ? LoadIconW(0, name) : LoadCursorW(0, name);
}
static I64 g_cur;
API SetCursor(I64 c) {
  I64 old = g_cur; g_cur = c;
  int shape = (c >= 0x7F000000 && c < 0x7F010000) ? (int)(c - 0x7F000000) : 0;
  if (shape != g_cursor_shape) { g_cursor_shape = shape; out_cmd(GUI_CMD_SET_CURSOR, 0, (uint32_t)shape, 0, 0, 0, 0); }
  return old;
}
API GetCursor(void) { return g_cur; }
API ShowCursor(I64 show) { g_cursor_cnt += show ? 1 : -1; ptrlock_update(); return g_cursor_cnt; }
API GetCursorInfo(I64 pci) {
  uint32_t *u = (uint32_t *)P_(pci);   /* CURSORINFO (Win64 24B): cbSize, flags, hCursor(8), ptScreenPos(8) */
  if (!u || u[0] != 24) { gui_set_last_error(87); return 0; }
  u[1] = g_cursor_cnt >= 0 ? 1 /* CURSOR_SHOWING */ : 0;
  *(U64 *)(u + 2) = (U64)g_cur;
  GetCursorPos(H_(u + 4)); return 1;
}
API GetKeyState(I64 vk) {
  GuiShared *sh = gui_sh(); vk &= 0xFF;
  if (vk == VK_LBUTTON) return (sh->buttons & 1) ? (int16_t)0x8000 : 0;
  if (vk == VK_RBUTTON) return (sh->buttons & 2) ? (int16_t)0x8000 : 0;
  if (vk == VK_MBUTTON) return (sh->buttons & 4) ? (int16_t)0x8000 : 0;
  if (vk == VK_SHIFT) return (sh->mods & GUI_MOD_SHIFT) ? (int16_t)0x8000 : 0;
  if (vk == VK_CONTROL) return (sh->mods & GUI_MOD_CTRL) ? (int16_t)0x8000 : 0;
  if (vk == VK_MENU) return (sh->mods & GUI_MOD_ALT) ? (int16_t)0x8000 : 0;
  return (g_kb[vk] & 0x80) ? (int16_t)0x8000 : 0;
}
API GetAsyncKeyState(I64 vk) {
  GuiShared *sh = gui_sh(); vk &= 0xFF;
  if (vk == VK_LBUTTON) return (sh->buttons & 1) ? (int16_t)0x8000 : 0;
  if (vk == VK_RBUTTON) return (sh->buttons & 2) ? (int16_t)0x8000 : 0;
  if (vk == VK_MBUTTON) return (sh->buttons & 4) ? (int16_t)0x8000 : 0;
  if (vk == VK_SHIFT) return (sh->mods & GUI_MOD_SHIFT) ? (int16_t)0x8000 : 0;
  if (vk == VK_CONTROL) return (sh->mods & GUI_MOD_CTRL) ? (int16_t)0x8000 : 0;
  if (vk == VK_MENU) return (sh->mods & GUI_MOD_ALT) ? (int16_t)0x8000 : 0;
  return (__atomic_load_n(&sh->key_down[vk >> 5], __ATOMIC_RELAXED) >> (vk & 31)) & 1 ? (int16_t)0x8000 : 0;
}
API GetDoubleClickTime(void) { return 500; }
API WindowFromPoint(I64 pt_packed_or_lo) {
  /* x64 ABI: POINT (8B) は値渡し -> 1 引数 (x | y<<32) */
  int x = (int32_t)(pt_packed_or_lo & 0xFFFFFFFF), y = (int32_t)((U64)pt_packed_or_lo >> 32), lx, ly;
  Wnd *w = hit_test(x, y, &lx, &ly); return w ? (I64)w->h : 0;
}
API GetSystemMetrics(I64 i) {
  GuiShared *sh = gui_sh();
  switch ((int)i) {
    case SM_CXSCREEN: case SM_CXVIRTUALSCREEN: case SM_CXFULLSCREEN: case SM_CXMAXIMIZED: return sh->screen_w;
    case SM_CYSCREEN: case SM_CYVIRTUALSCREEN: case SM_CYFULLSCREEN: case SM_CYMAXIMIZED: return sh->screen_h;
    case SM_XVIRTUALSCREEN: case SM_YVIRTUALSCREEN: return 0;
    case SM_CXVSCROLL: case SM_CYHSCROLL: return dscale(17);
    case SM_CYCAPTION: return dscale(23);
    case SM_CXBORDER: case SM_CYBORDER: return dscale(1);
    case SM_CXDOUBLECLK: case SM_CYDOUBLECLK: return 4;
    case SM_CXICON: case SM_CYICON: return 32;
    case SM_CXSMICON: case SM_CYSMICON: return 16;
    case SM_CXFRAME: case SM_CYFRAME: return dscale(4);
    case SM_CXDRAG: case SM_CYDRAG: return 4;
    case SM_CMONITORS: return 1;
    case SM_MOUSEPRESENT: return 1;
    case SM_SWAPBUTTON: return 0;
    case SM_CXMIN: case SM_CYMIN: return 100;
  }
  return 0;
}
API GetSysColor(I64 i) {   /* Windows 10 既定テーマの COLORREF (0x00BBGGRR) */
  static const uint32_t t[] = {
    0xC8C8C8, 0x000000, 0xD1B499, 0xDBCDBF, 0xF0F0F0, 0xFFFFFF, 0x646464, 0x000000,   /* SCROLLBAR..WINDOWTEXT */
    0x000000, 0x000000, 0xB4B4B4, 0xFCF7F4, 0xABABAB, 0xFF9933, 0xFFFFFF, 0xF0F0F0,   /* CAPTIONTEXT..BTNFACE */
    0xA0A0A0, 0x6D6D6D, 0x000000, 0x000000, 0xFFFFFF, 0x696969, 0xE3E3E3, 0x000000,   /* BTNSHADOW..INFOTEXT */
    0xE1FFFF, 0x000000, 0xCC6600, 0xEAD1B9, 0xF2E4D7, 0xFF9933, 0xF0F0F0 };            /* INFOBK..MENUBAR */
  return (i >= 0 && i < (I64)(sizeof t / sizeof t[0])) ? t[i] : 0;
}
API SystemParametersInfoW(I64 act, I64 p1, I64 p2, I64 fl) {
  (void)p1; (void)fl;
  GuiShared *sh = gui_sh();
  if (act == 0x30) { WRECT *r = (WRECT *)P_(p2); r->left = r->top = 0; r->right = (int32_t)sh->screen_w; r->bottom = (int32_t)sh->screen_h; return 1; } /* SPI_GETWORKAREA */
  if (act == 0x1004) { *(uint32_t *)P_(p2) = 0; return 1; }  /* SPI_GETMOUSEHOVERTIME 等は 0 */
  return 0;  /* 未対応 action は FALSE (Win32 の未対応 action 相当)。値を推定で埋めない */
}
API SystemParametersInfoA(I64 a, I64 b, I64 c, I64 d) { return SystemParametersInfoW(a, b, c, d); }
API GetKeyboardState(I64 buf) { memcpy(P_(buf), g_kb, 256); return 1; }
API SetKeyboardState(I64 buf) { memcpy(g_kb, P_(buf), 256); return 1; }
/* INPUT (Win64 40B): type@0, union@8 — MOUSEINPUT{dx,dy,mouseData,dwFlags,time,extra} / KEYBDINPUT{wVk,wScan,dwFlags,time,extra}。
 * host 入力リングを介さず translate_input へ直接注入する (host が書く buttons/mods/cursor はここでも更新; 次の実入力で host 値に上書きされる) */
static uint32_t vk_from_scan(uint32_t sc, int ext);
API SendInput(I64 n, I64 pin, I64 cb) {
  GuiShared *sh = gui_sh();
  if (cb != 40 || !pin || n < 0) { gui_set_last_error(87); return 0; }
  int done = 0;
  for (int i = 0; i < (int)n; i++) {
    const uint8_t *in = (const uint8_t *)P_(pin) + (size_t)i * 40;
    uint32_t type = *(const uint32_t *)in; uint32_t t = gui_now_ms();
    if (type == 1) {   /* INPUT_KEYBOARD */
      uint16_t vk = *(const uint16_t *)(in + 8), sc = *(const uint16_t *)(in + 10); uint32_t fl = *(const uint32_t *)(in + 12);
      int up = (fl & 2) != 0, ext = (fl & 1) != 0;
      if (fl & 4) { if (!up) { uint32_t r[8] = { GUI_IN_CHAR, 0, (uint32_t)sh->cursor_x, (uint32_t)sh->cursor_y, sc, 0, t, 0 }; translate_input(r); } done++; continue; }
      if (fl & 8) vk = (uint16_t)vk_from_scan(sc, ext);
      uint32_t bit = vk == VK_SHIFT ? GUI_MOD_SHIFT : vk == VK_CONTROL ? GUI_MOD_CTRL : vk == VK_MENU ? GUI_MOD_ALT : 0;
      if (bit) sh->mods = up ? (sh->mods & ~bit) : (sh->mods | bit);
      uint32_t r[8] = { up ? GUI_IN_KEY_UP : GUI_IN_KEY_DOWN, 0, (uint32_t)sh->cursor_x, (uint32_t)sh->cursor_y, vk, ((uint32_t)sc << 8) | (ext ? 2u : 0u), t, 0 };
      translate_input(r); done++;
    } else if (type == 0) {   /* INPUT_MOUSE */
      int32_t dx = *(const int32_t *)(in + 8), dy = *(const int32_t *)(in + 12); int32_t data = *(const int32_t *)(in + 16); uint32_t fl = *(const uint32_t *)(in + 20);
      if (fl & 1) {   /* MOVE */
        int nx, ny;
        if (fl & 0x8000) { nx = (int)((int64_t)dx * sh->screen_w / 65536); ny = (int)((int64_t)dy * sh->screen_h / 65536); }
        else { nx = sh->cursor_x + dx; ny = sh->cursor_y + dy; }
        sh->cursor_x = nx; sh->cursor_y = ny;
        uint32_t r[8] = { GUI_IN_MOUSE_MOVE, 0, (uint32_t)nx, (uint32_t)ny, sh->buttons, 0, t, 0 }; translate_input(r);
      }
      static const struct { uint32_t f; uint32_t dom; int up; uint32_t mask; } bt[] = { { 2, 0, 0, 1 }, { 4, 0, 1, 1 }, { 8, 2, 0, 2 }, { 0x10, 2, 1, 2 }, { 0x20, 1, 0, 4 }, { 0x40, 1, 1, 4 } };
      for (int k = 0; k < 6; k++) if (fl & bt[k].f) {
        sh->buttons = bt[k].up ? (sh->buttons & ~bt[k].mask) : (sh->buttons | bt[k].mask);
        uint32_t r[8] = { bt[k].up ? GUI_IN_MOUSE_UP : GUI_IN_MOUSE_DOWN, 0, (uint32_t)sh->cursor_x, (uint32_t)sh->cursor_y, bt[k].dom, sh->mods, t, 0 }; translate_input(r);
      }
      if (fl & 0x800) { uint32_t r[8] = { GUI_IN_WHEEL, 0, (uint32_t)sh->cursor_x, (uint32_t)sh->cursor_y, (uint32_t)data, sh->mods, t, 0 }; translate_input(r); }
      done++;
    } else { gui_set_last_error(87); break; }   /* INPUT_HARDWARE は未対応 */
  }
  return done;
}
API MessageBoxA(I64 h, I64 t, I64 c, I64 f) { (void)h; (void)f; gui_logf("MessageBox[%s]: %s", c ? (const char *)P_(c) : "", t ? (const char *)P_(t) : ""); return 1; }
API MessageBoxW(I64 h, I64 t, I64 c, I64 f) { char a[200], b[100]; u16_to_u8((const uint16_t *)P_(t), a, sizeof a); u16_to_u8((const uint16_t *)P_(c), b, sizeof b); return MessageBoxA(h, H_(a), H_(b), f); }
API NotifyWinEvent(I64 a, I64 b, I64 c, I64 d) { (void)a; (void)b; (void)c; (void)d; return 0; }
API SetThreadDpiAwarenessContext(I64 c) {   /* 戻り値 = 旧 context。不正値は 0 */
  if (!((c >= -5 && c <= -1))) { gui_set_last_error(87); return 0; }
  I64 old = g_dpi_ctx; g_dpi_ctx = c; return old;
}
API GetThreadDpiAwarenessContext(void) { return g_dpi_ctx; }
API GetDpiForSystem(void) { gui_sh(); return (g_dpi_ctx == -1 || g_dpi_ctx == -5) ? 96 : (I64)((96u * (gui_sh()->dpr_x100 ? gui_sh()->dpr_x100 : 100) + 50) / 100); }
API GetDpiForWindow(I64 h) { if (!wnd_from_h((U64)h)) return 0; return gui_dpi(); }
API IsProcessDPIAware(void) { return g_dpi_ctx != -1 && g_dpi_ctx != -5; }
API IsIconic(I64 h) { (void)h; return 0; }
API IsZoomed(I64 h) { (void)h; return 0; }

/* ================= RECT ユーティリティ ================= */
API SetRect(I64 p, I64 l, I64 t, I64 r, I64 b) { WRECT *x = (WRECT *)P_(p); x->left = (int32_t)l; x->top = (int32_t)t; x->right = (int32_t)r; x->bottom = (int32_t)b; return 1; }
API SetRectEmpty(I64 p) { memset(P_(p), 0, sizeof(WRECT)); return 1; }
API CopyRect(I64 d, I64 s) { *(WRECT *)P_(d) = *(WRECT *)P_(s); return 1; }
API OffsetRect(I64 p, I64 dx, I64 dy) { WRECT *r = (WRECT *)P_(p); r->left += (int32_t)dx; r->right += (int32_t)dx; r->top += (int32_t)dy; r->bottom += (int32_t)dy; return 1; }
API InflateRect(I64 p, I64 dx, I64 dy) { WRECT *r = (WRECT *)P_(p); r->left -= (int32_t)dx; r->right += (int32_t)dx; r->top -= (int32_t)dy; r->bottom += (int32_t)dy; return 1; }
API IsRectEmpty(I64 p) { return r_empty(*(WRECT *)P_(p)); }
API EqualRect(I64 a, I64 b) { return memcmp(P_(a), P_(b), sizeof(WRECT)) == 0; }
API PtInRect(I64 rc, I64 pt) {
  const WRECT *r = (const WRECT *)P_(rc);
  int x = (int32_t)(pt & 0xFFFFFFFF), y = (int32_t)((U64)pt >> 32);  /* POINT 値渡し (x64) */
  return x >= r->left && x < r->right && y >= r->top && y < r->bottom;
}
API IntersectRect(I64 d, I64 a, I64 b) {
  WRECT o = r_isect(*(WRECT *)P_(a), *(WRECT *)P_(b));
  if (r_empty(o)) { memset(P_(d), 0, sizeof o); return 0; }
  *(WRECT *)P_(d) = o; return 1;
}
API UnionRect(I64 d, I64 a, I64 b) {
  WRECT x = *(WRECT *)P_(a), y = *(WRECT *)P_(b), o;
  if (r_empty(x) && r_empty(y)) { memset(P_(d), 0, sizeof o); return 0; }
  if (r_empty(x)) o = y; else if (r_empty(y)) o = x;
  else { o.left = x.left < y.left ? x.left : y.left; o.top = x.top < y.top ? x.top : y.top; o.right = x.right > y.right ? x.right : y.right; o.bottom = x.bottom > y.bottom ? x.bottom : y.bottom; }
  *(WRECT *)P_(d) = o; return 1;
}
API SubtractRect(I64 d, I64 a, I64 b) {
  WRECT x = *(WRECT *)P_(a), y = *(WRECT *)P_(b), o = x;
  WRECT i = r_isect(x, y);
  if (!r_empty(i)) {
    if (i.top <= x.top && i.bottom >= x.bottom) { if (i.left <= x.left) o.left = i.right; else if (i.right >= x.right) o.right = i.left; }
    else if (i.left <= x.left && i.right >= x.right) { if (i.top <= x.top) o.top = i.bottom; else if (i.bottom >= x.bottom) o.bottom = i.top; }
  }
  *(WRECT *)P_(d) = o; return !r_empty(o);
}

/* ================= kernel32 最小 (テストアプリ/lift 用) =================
 * 実 FLEngine 結合では tools/shimx が同名を提供するため -DGUI_NO_K32 で除外する (CAB-156 / INTEGRATION.md §2)。
 * その場合の到達ログ dump は結合側の exit hook から gui_reach_dump() を呼ぶ。 */
#ifndef GUI_NO_K32
API ExitProcess(I64 code) {
  GuiShared *sh = gui_sh();
  surf_flush();
  gui_reach_dump();
  sh->exit_code = (uint32_t)code;
  __atomic_store_n(&sh->exited, 1, __ATOMIC_SEQ_CST);
  out_cmd(GUI_CMD_EXIT, (uint32_t)code, 0, 0, 0, 0, 0);
  exit((int)code);
}
API GetModuleHandleA(I64 name) { (void)name; return 0x00400000; }
API GetModuleHandleW(I64 name) { return GetModuleHandleA(name); }
API OutputDebugStringA(I64 s) { gui_log((const char *)P_(s)); return 0; }
API OutputDebugStringW(I64 s) { char b[256]; u16_to_u8((const uint16_t *)P_(s), b, sizeof b); gui_log(b); return 0; }
#endif /* GUI_NO_K32 */

/* ================= 補助 user32 (P0/P1 の残り; 簡易実装) ================= */
API SetParent(I64 h, I64 np) {
  Wnd *w = wnd_from_h((U64)h), *p = np ? wnd_from_h((U64)np) : g_desktop;
  if (!w || !p || !(w->style & WS_CHILD) || p == g_desktop) { if (w && is_toplevel(w) && !np) return 0; gui_failfast("SetParent", "only child->child reparent supported"); }
  Wnd *old = w->parent; unlink_child(w); link_child(p, w);
  if (w->surf >= 0) gui_failfast("SetParent", "toplevel->child reparent");
  invalidate(w, NULL, 1, 1); if (old && old != g_desktop) invalidate(old, NULL, 1, 0);
  return old && old != g_desktop ? (I64)old->h : 0;
}
API GetClipCursor(I64 rc) { GuiShared *sh = gui_sh(); WRECT *r = (WRECT *)P_(rc); if (g_cclip_on) { *r = g_cclip; return 1; } r->left = r->top = 0; r->right = (int32_t)sh->screen_w; r->bottom = (int32_t)sh->screen_h; return 1; }
static int vk_to_char(uint32_t vk, const uint8_t *st);   /* gui_core_ext.inc (US 配列) */
static int layout_to_char(uint32_t vk, uint32_t sc, const uint8_t *st);   /* gui_core_ext.inc */
API ToAscii(I64 vk, I64 sc, I64 state, I64 buf, I64 flags) {
  (void)flags; const uint8_t *st = (const uint8_t *)P_(state);
  int ch = layout_to_char((uint32_t)vk, (uint32_t)sc, st); if (ch < 0) ch = vk_to_char((uint32_t)vk, st);
  if (!ch || ch > 0xFF) return 0; *(uint16_t *)P_(buf) = (uint16_t)ch; return 1;
}
API PhysicalToLogicalPoint(I64 h, I64 pt) { (void)h; (void)pt; return 1; }
API LogicalToPhysicalPoint(I64 h, I64 pt) { (void)h; (void)pt; return 1; }
API GetMessageExtraInfo(void) { return 0; }
API AttachThreadInput(I64 a, I64 b, I64 c) { (void)a; (void)b; (void)c; return 1; }
API IsDialogMessageA(I64 h, I64 m) { (void)h; (void)m; return 0; }
API IsDialogMessageW(I64 h, I64 m) { (void)h; (void)m; return 0; }
API TranslateMDISysAccel(I64 h, I64 m) { (void)h; (void)m; return 0; }
API DefFrameProcW(I64 h, I64 c, I64 m, I64 w, I64 l) { (void)c; return DefWindowProcW(h, m, w, l); }
API DefMDIChildProcW(I64 h, I64 m, I64 w, I64 l) { return DefWindowProcW(h, m, w, l); }
API IsWindowUnicode(I64 h) { Wnd *w = wnd_from_h((U64)h); return w && w->wide; }
API GetLastActivePopup(I64 h) { return h; }
API ShowOwnedPopups(I64 h, I64 s) { (void)h; (void)s; return 1; }
API GetTopWindow(I64 h) { Wnd *w = h ? wnd_from_h((U64)h) : g_desktop; ensure_desktop(); if (!h) w = g_desktop; return (w && w->last) ? (I64)w->last->h : 0; }
API GetDlgItem(I64 h, I64 id) { Wnd *w = wnd_from_h((U64)h); if (!w) return 0; for (Wnd *c = w->first; c; c = c->next) if (c->id == (U64)id) return (I64)c->h; return 0; }
API SetWindowRgn(I64 h, I64 rgn, I64 redraw) { (void)h; (void)rgn; (void)redraw; return 1; }  /* 見た目のみ: 形状クリップは未反映 (benign no-op) */
API GetUpdateRgn(I64 h, I64 rgn, I64 erase) {
  extern API SetRectRgn(I64, I64, I64, I64, I64);
  (void)erase; Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  if (!w->has_inv) { SetRectRgn(rgn, 0, 0, 0, 0); return 1; }
  extern void gdi_rgn_set_rl(U64, const RL *);
  gdi_rgn_set_rl((U64)rgn, &w->invl); return w->invl.n > 1 ? 3 : 2;
}
API ValidateRgn(I64 h, I64 rgn) { (void)rgn; return ValidateRect(h, 0); }
API BeginDeferWindowPos(I64 n) { (void)n; return 0x7DEF0000; }
API DeferWindowPos(I64 hdwp, I64 h, I64 after, I64 x, I64 y, I64 cx, I64 cy, I64 flags) { SetWindowPos(h, after, x, y, cx, cy, flags); return hdwp; }
API EndDeferWindowPos(I64 hdwp) { (void)hdwp; return 1; }
API GetClassLongPtrW(I64 h, I64 idx) {
  Wnd *w = wnd_from_h((U64)h); if (!w || !w->cls) return 0;
  switch ((int)idx) { case -10: return (I64)w->cls->hbrbg; case -12: return (I64)w->cls->hcursor; case -14: return (I64)w->cls->hicon; case -16: return (I64)w->cls->hinst;
                      case -24: return (I64)w->cls->style; case -26: return (I64)w->cls->atom; case -8: return (I64)w->cls->wndproc; }
  if (idx >= 0 && idx + 8 <= w->cls->cbcls) { I64 v; memcpy(&v, w->cls->extra + idx, 8); return v; }
  return 0;
}
API SetClassLongPtrW(I64 h, I64 idx, I64 v) {
  Wnd *w = wnd_from_h((U64)h); if (!w || !w->cls) return 0; I64 old = GetClassLongPtrW(h, idx);
  switch ((int)idx) { case -10: w->cls->hbrbg = (U64)v; break; case -12: w->cls->hcursor = (U64)v; break; case -14: w->cls->hicon = (U64)v; break;
                      case -24: w->cls->style = (uint32_t)v; break; case -8: w->cls->wndproc = (U64)v; break;
                      default: if (idx >= 0 && idx + 8 <= w->cls->cbcls) memcpy(w->cls->extra + idx, &v, 8); }
  return old;
}
API GetClassNameW(I64 h, I64 buf, I64 n) { Wnd *w = wnd_from_h((U64)h); if (!w || !w->cls || n <= 0) return 0; return u8_to_u16(w->cls->name, (uint16_t *)P_(buf), (int)n); }
API GetClassNameA(I64 h, I64 buf, I64 n) { Wnd *w = wnd_from_h((U64)h); if (!w || !w->cls || n <= 0) return 0; int k = (int)strlen(w->cls->name); if (k >= n) k = (int)n - 1; memcpy(P_(buf), w->cls->name, (size_t)k); ((char *)P_(buf))[k] = 0; return k; }
static Wnd *find_by_class(Wnd *par, const char *cn, const char *title, Wnd *after) {
  int started = after == NULL;
  for (Wnd *c = par->first; c; c = c->next) {
    if (!started) { if (c == after) started = 1; continue; }
    if ((!cn || !strcasecmp(c->cls->name, cn)) && (!title || !strcmp(c->title, title))) return c;
  }
  return NULL;
}
static API findwindow_impl(I64 cls, I64 title, int wide) {
  ensure_desktop(); char cb[256], tb[256]; const char *cn = str_in((U64)cls, wide, cb, sizeof cb), *tn = str_in((U64)title, wide, tb, sizeof tb);
  Wnd *w = find_by_class(g_desktop, cn, tn, NULL); return w ? (I64)w->h : 0;
}
API FindWindowW(I64 c, I64 t) { return findwindow_impl(c, t, 1); }
API FindWindowA(I64 c, I64 t) { return findwindow_impl(c, t, 0); }
API FindWindowExW(I64 parent, I64 after, I64 cls, I64 title) {
  ensure_desktop(); char cb[256], tb[256]; const char *cn = str_in((U64)cls, 1, cb, sizeof cb), *tn = str_in((U64)title, 1, tb, sizeof tb);
  Wnd *p = parent ? wnd_from_h((U64)parent) : g_desktop; Wnd *a = after ? wnd_from_h((U64)after) : NULL; if (!p) return 0;
  Wnd *w = find_by_class(p, cn, tn, a); return w ? (I64)w->h : 0;
}
static API enum_children(Wnd *p, I64 proc, I64 lp, int recurse) {
  /* 列挙中の破棄に備え h を先に集める */
  U64 hs[512]; int n = 0;
  for (Wnd *c = p->last; c && n < 512; c = c->prev) hs[n++] = c->h;   /* z 順 (前面から) */
  for (int i = 0; i < n; i++) {
    if (!wnd_from_h(hs[i])) continue;
    if (!gui_call2((U64)proc, (I64)hs[i], lp)) return 0;
    if (recurse) { Wnd *c = wnd_from_h(hs[i]); if (c && !enum_children(c, proc, lp, 1)) return 0; }
  }
  return 1;
}
API EnumWindows(I64 proc, I64 lp) { ensure_desktop(); return enum_children(g_desktop, proc, lp, 0); }
API EnumChildWindows(I64 h, I64 proc, I64 lp) { Wnd *w = h ? wnd_from_h((U64)h) : g_desktop; ensure_desktop(); return w ? enum_children(w, proc, lp, 1) : 0; }
API EnumThreadWindows(I64 tid, I64 proc, I64 lp) { (void)tid; ensure_desktop(); return enum_children(g_desktop, proc, lp, 0); }
API SetPropW(I64 h, I64 name, I64 v) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0; char b[64]; const char *n = name < 0x10000 ? NULL : (u16_to_u8((const uint16_t *)P_(name), b, sizeof b), b);
  if (!n) { snprintf(b, sizeof b, "#atom%u", (unsigned)name); n = b; }
  for (struct Prop *p = w->props; p; p = p->next) if (!strcmp(p->name, n)) { p->val = (U64)v; return 1; }
  struct Prop *p = (struct Prop *)calloc(1, sizeof *p); snprintf(p->name, sizeof p->name, "%s", n); p->val = (U64)v; p->next = w->props; w->props = p; return 1;
}
API GetPropW(I64 h, I64 name) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0; char b[64]; const char *n;
  if (name < 0x10000) { snprintf(b, sizeof b, "#atom%u", (unsigned)name); n = b; } else { u16_to_u8((const uint16_t *)P_(name), b, sizeof b); n = b; }
  for (struct Prop *p = w->props; p; p = p->next) if (!strcmp(p->name, n)) return (I64)p->val;
  return 0;
}
API RemovePropW(I64 h, I64 name) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0; char b[64]; const char *n;
  if (name < 0x10000) { snprintf(b, sizeof b, "#atom%u", (unsigned)name); n = b; } else { u16_to_u8((const uint16_t *)P_(name), b, sizeof b); n = b; }
  for (struct Prop **pp = &w->props; *pp; pp = &(*pp)->next) if (!strcmp((*pp)->name, n)) { struct Prop *d = *pp; I64 v = (I64)d->val; *pp = d->next; free(d); return v; }
  return 0;
}
API GetWindowPlacement(I64 h, I64 wp) {
  Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  uint32_t *u = (uint32_t *)P_(wp);   /* WINDOWPLACEMENT : length,flags,showCmd,ptMin(2),ptMax(2),rcNormal(4) = 44B */
  u[0] = 44; u[1] = 0; u[2] = (w->style & WS_VISIBLE) ? SW_SHOWNORMAL : SW_HIDE; u[3] = u[4] = (uint32_t)-1; u[5] = u[6] = (uint32_t)-1;
  int sx, sy; to_screen_origin(w, &sx, &sy); u[7] = (uint32_t)sx; u[8] = (uint32_t)sy; u[9] = (uint32_t)(sx + w->w); u[10] = (uint32_t)(sy + w->hgt); return 1;
}
API SetWindowPlacement(I64 h, I64 wp) {
  const uint32_t *u = (const uint32_t *)P_(wp); Wnd *w = wnd_from_h((U64)h); if (!w) return 0;
  MoveWindow(h, (int32_t)u[7], (int32_t)u[8], (int32_t)u[9] - (int32_t)u[7], (int32_t)u[10] - (int32_t)u[8], 1);
  ShowWindow(h, u[2]); return 1;
}
/* MsgWaitForMultipleObjects[Ex] (#172 SHX-T5): shimx の weak 定義を置換する強定義。
 * kernel object の待機は shimx 担当 (WaitForMultipleObjects を弱参照で借りる)。リンクされていなければ従来どおり nCount==0 のみ。
 * 起床: GUI のメッセージ到着 = doorbell。kernel object の状態変化は shimx_set_notify_hook(gui_doorbell) (gui_shimx_attach) 経由で
 * 同じ doorbell を鳴らすため 1 本の futex で両方を待てる。hook 未接続で n>0 のときは 5ms 刻みの poll に縮退 (取りこぼし防止)。
 * 戻り: WAIT_OBJECT_0+i (i 番目 signaled; 低 index 優先) / WAIT_OBJECT_0+n (メッセージ) / WAIT_TIMEOUT / WAIT_FAILED。
 * MWMO_WAITALL(1) は「全 object signaled かつ入力あり」で WAIT_OBJECT_0 (入力を先に確認してから object を一括取得 = 取得だけ先走らない)。 */
extern uint32_t WaitForMultipleObjects(uint32_t n, const uint64_t *hs, int all, uint32_t ms) __attribute__((weak));
static int g_kernel_notify_attached;
static uint32_t msgwait_ex(uint32_t n, const uint64_t *hs, uint32_t ms, uint32_t flags) {
  GuiShared *sh = gui_sh();
  int all = (flags & 1u) != 0;
  if (n > 0 && (!hs || n > 63)) { gui_set_last_error(87); return 0xFFFFFFFFu; }
  if (n > 0 && !WaitForMultipleObjects) gui_failfast("MsgWaitForMultipleObjects", "waiting on kernel handles needs shimx (WaitForMultipleObjects unresolved)");
  uint32_t t0 = gui_now_ms();
  for (;;) {
    uint32_t seen = __atomic_load_n(&sh->doorbell, __ATOMIC_SEQ_CST); WMSG tmp;
    int have_msg = try_get(&tmp, 0, 0, 0, 0);
    if (n > 0 && (!all || have_msg)) {
      uint32_t r = WaitForMultipleObjects(n, hs, all, 0);
      if (r != 0x102u) return r;           /* signaled (WAIT_OBJECT_0+i / ABANDONED) または WAIT_FAILED */
    }
    if (have_msg && !all) return n;        /* WAIT_OBJECT_0 + nCount : メッセージ到着 */
    if (have_msg && n == 0) return 0;
    surf_flush();
    int32_t left = ms == 0xFFFFFFFFu ? -1 : (int32_t)(ms - (gui_now_ms() - t0));
    if (ms != 0xFFFFFFFFu && (left <= 0 || (uint32_t)(gui_now_ms() - t0) >= ms)) return 0x102;   /* WAIT_TIMEOUT */
    int32_t tm = next_timer_timeout(); if (left >= 0 && (tm < 0 || left < tm)) tm = left;
    if (n > 0 && !g_kernel_notify_attached && (tm < 0 || tm > 5)) tm = 5;
    gui_futex_wait(&sh->doorbell, seen, tm);
  }
}
API MsgWaitForMultipleObjects(I64 n, I64 handles, I64 all, I64 ms, I64 mask) { (void)mask; return msgwait_ex((uint32_t)n, (const uint64_t *)P_(handles), (uint32_t)ms, all ? 1u : 0u); }
API MsgWaitForMultipleObjectsEx(I64 n, I64 handles, I64 ms, I64 mask, I64 flags) { (void)mask; return msgwait_ex((uint32_t)n, (const uint64_t *)P_(handles), (uint32_t)ms, (uint32_t)flags); }
static API scroll_impl(Wnd *w, int dx, int dy, const WRECT *scroll, const WRECT *clip) {
  extern API BitBlt(I64, I64, I64, I64, I64, I64, I64, I64, I64);
  WRECT r = scroll ? *scroll : (WRECT){ 0, 0, w->w, w->hgt };
  if (clip) r = r_isect(r, *clip);
  RL cl = {0}; wnd_clip(w, &cl); int surf, ox, oy; wnd_target(w, &surf, &ox, &oy);
  U64 dc = gdi_get_dc_for_wnd(w, 0, &cl); rl_free(&cl);
  BitBlt((I64)dc, r.left + dx, r.top + dy, r.right - r.left, r.bottom - r.top, (I64)dc, r.left, r.top, SRCCOPY);
  gdi_release_dc(dc);
  /* 露出した帯を無効化 */
  if (dx > 0) invalidate(w, &(WRECT){ r.left, r.top, r.left + dx, r.bottom }, 1, 0); else if (dx < 0) invalidate(w, &(WRECT){ r.right + dx, r.top, r.right, r.bottom }, 1, 0);
  if (dy > 0) invalidate(w, &(WRECT){ r.left, r.top, r.right, r.top + dy }, 1, 0); else if (dy < 0) invalidate(w, &(WRECT){ r.left, r.bottom + dy, r.right, r.bottom }, 1, 0);
  return 1;
}
API ScrollWindow(I64 h, I64 dx, I64 dy, I64 rs, I64 rc) { Wnd *w = wnd_from_h((U64)h); return w ? scroll_impl(w, (int)dx, (int)dy, rs ? (const WRECT *)P_(rs) : NULL, rc ? (const WRECT *)P_(rc) : NULL) : 0; }
API ScrollWindowEx(I64 h, I64 dx, I64 dy, I64 rs, I64 rc, I64 rgn, I64 ru, I64 fl) { (void)rgn; (void)fl; if (ru) memset(P_(ru), 0, sizeof(WRECT)); return ScrollWindow(h, dx, dy, rs, rc); }
API ScrollDC(I64 hdc, I64 dx, I64 dy, I64 rs, I64 rc, I64 rgn, I64 ru) {
  extern API BitBlt(I64, I64, I64, I64, I64, I64, I64, I64, I64);
  (void)rgn; WRECT r = rs ? *(const WRECT *)P_(rs) : (WRECT){ 0, 0, 0, 0 };
  if (!rs) gui_failfast("ScrollDC", "lprcScroll == NULL");
  if (rc) r = r_isect(r, *(const WRECT *)P_(rc));
  BitBlt(hdc, r.left + dx, r.top + dy, r.right - r.left, r.bottom - r.top, hdc, r.left, r.top, SRCCOPY);
  if (ru) memset(P_(ru), 0, sizeof(WRECT));
  return 1;
}

/* ================= P1 拡張 (CAB-159): クリップボード/フック/モニタ/キャレット/入力補助/文字列 ================= */
#include "gui_core_ext.inc"
