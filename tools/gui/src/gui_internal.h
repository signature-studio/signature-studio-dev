/* gui_internal.h — shim 内部共有定義 (外部公開 ABI は gui_api.h; 生成物) */
#ifndef GUI_INTERNAL_H
#define GUI_INTERNAL_H

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "gui_proto.h"
#include "gui_win32.h"

#define GUI_NORETURN __attribute__((noreturn))

/* ---- platform (gui_platform.c) ---- */
GuiShared *gui_sh(void);                 /* 初回呼出で init + host attach 待ち */
uint32_t gui_now_ms(void);
void gui_futex_wait(volatile uint32_t *a, uint32_t expect, int timeout_ms); /* <0 = 無期限 */
void gui_futex_wake(volatile uint32_t *a);
GUI_NORETURN void gui_failfast(const char *api, const char *why);
void gui_log(const char *s);             /* LOG コマンドへ (改行付与) */
void gui_logf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
void gui_out_push(const uint32_t rec[8]);
uint64_t gui_thread_id(void);
void gui_lock(void);
void gui_unlock(void);
void gui_doorbell(void);                 /* ++doorbell + wake (他スレッドからのメッセージ投函用) */
/* headless (native/node テスト) 用: out ring が満杯のとき同期ドレインするコールバック */
extern void (*gui_host_drain_cb)(void);
void gui_headless_attach(uint32_t w, uint32_t h);

/* ---- handle table ---- */
typedef enum { HT_NONE = 0, HT_WND, HT_DC, HT_BMP, HT_BRUSH, HT_PEN, HT_FONT, HT_RGN, HT_ICON, HT_CURSOR,
               HT_PAL, HT_MENU, HT_HOOK } HType;
U64 h_alloc(HType t, void *p);
void *h_get(U64 h, HType t);              /* 型/世代不一致は NULL */
HType h_type(U64 h);
void h_free(U64 h);
int  h_count(HType t);                    /* 生存ハンドル数 (GetGuiResources 用) */
int  h_peak(int user);                    /* GDI(0)/USER(1) グループの生存数ピーク */


/* ---- rect list (region の実体) ---- */
typedef struct { WRECT *r; int n, cap; } RL;
void rl_free(RL *l);
void rl_clear(RL *l);
void rl_add(RL *l, WRECT r);               /* 単純追加 (非重複を呼出側が保証) */
void rl_copy(RL *dst, const RL *src);
void rl_intersect_rect(RL *l, WRECT r);
void rl_subtract_rect(RL *l, WRECT r);
void rl_intersect(RL *l, const RL *o);
void rl_subtract(RL *l, const RL *o);
void rl_union(RL *l, const RL *o);
void rl_bbox(const RL *l, WRECT *out);
int  rl_empty(const RL *l);
int  rl_contains(const RL *l, int x, int y);
static inline int r_empty(WRECT r) { return r.right <= r.left || r.bottom <= r.top; }
static inline WRECT r_isect(WRECT a, WRECT b) {
  WRECT o = { a.left > b.left ? a.left : b.left, a.top > b.top ? a.top : b.top,
              a.right < b.right ? a.right : b.right, a.bottom < b.bottom ? a.bottom : b.bottom };
  return o;
}

/* ---- surface (gui_core.c が管理, gui_gdi.c が描画先として参照) ---- */
typedef struct { uint8_t *px; int stride, w, h; uint32_t gen; } SurfView;
int  surf_view(int id, SurfView *v);
void surf_dirty(int id, WRECT r);
uint32_t gui_surf_retired_count(void);   /* GUI-12: host 消費待ちで保留中の旧 surface バッファ数 (テスト用) */
void surf_wseq_begin(int id);            /* window surface へ画素を書く前に呼ぶ (seqlock; 偶数→奇数) */
void surf_flush(void);                    /* 溜まった dirty を PRESENT + FRAME_END として push */
void gui_pump_idle_flush(void);

/* ---- window <-> gdi 連携 (gui_core.c が実装) ---- */
typedef struct Wnd Wnd;
int  wnd_target(Wnd *w, int *surf, int *ox, int *oy);   /* top-level surf と client 原点 */
void wnd_clip_window(Wnd *w, RL *out);                   /* window DC (NC を含む) の可視領域 */
void wnd_window_origin(Wnd *w, int *ox, int *oy);        /* window rect 左上 (surface 座標) */
int  gui_dpi(void);                                      /* スレッドの DPI 対応状態に応じた論理 DPI (96 / dpr*96) */
void wnd_clip(Wnd *w, RL *out);                          /* window DC の可視領域 (surface 座標) */
Wnd *wnd_from_h(U64 h);
void wnd_client_size(Wnd *w, int *cw, int *ch);

/* ---- gdi (gui_gdi.c) ---- */
U64 gdi_get_dc_for_wnd(Wnd *w, int window_dc, const RL *clip_override);
void gdi_release_dc(U64 hdc);
U64 gdi_get_screen_dc(void);   /* GetDC(NULL)/GetWindowDC(NULL): 既定 1x1 ビットマップ選択済みのメモリ DC (ReleaseDC/DeleteDC で解放) */
void gdi_init(void);
void gdi_fill_rect_dc(U64 hdc, WRECT r, uint32_t colorref);
int  gdi_dc_is_valid(U64 hdc);

/* ---- テキストエンジン (GUI-9 #186; gui_ft.c が実装)。未登録なら gui_gdi.c は内蔵 8x8 フォントで描く ---- */
typedef struct { int ascent, descent, height, internal_leading, external_leading, avg_width, max_width, first, last, def_char, brk_char; } GuiTextMetrics;
typedef struct { int advance, w, h, left, top; uint8_t *cov; } GuiGlyph;   /* cov = w*h の 8bit coverage (malloc; 呼出側が free)。left/top = ペン原点(ベースライン)からの bitmap 左上 (top は上向き正) */
typedef struct GuiTextEngine {
  void *(*open)(const uint16_t *face16, int height, int weight, int italic);   /* height: LOGFONT 規約 (<0 = em px, >0 = cell px, 0 = 既定)。NULL = 解決不能 (8x8 へ) */
  void (*close)(void *f);
  void (*metrics)(void *f, GuiTextMetrics *m);
  int (*glyph)(void *f, uint32_t cp, int render, GuiGlyph *g);                 /* 1 = ok。render=0 は advance のみ */
  int (*resolve)(const uint16_t *face16);                                      /* face 名 -> 登録 index (<0 = 未解決)。alias 含む */
  int (*nfaces)(void);
  const char *(*face_name)(int idx);
} GuiTextEngine;
void gui_set_text_engine(const GuiTextEngine *e);

/* ---- 小物 ---- */
#define COLORREF_TO_BGRA(c) (0xFF000000u | (((c) & 0xFFu) << 16) | ((c) & 0xFF00u) | (((c) >> 16) & 0xFFu))
#define BGRA_TO_COLORREF(p) ((((p) >> 16) & 0xFFu) | ((p) & 0xFF00u) | (((p) & 0xFFu) << 16))

typedef int64_t (*WNDPROC64)(int64_t, int64_t, int64_t, int64_t);
void *gui_resolve_fn(U64 v);
/* コールバック呼出 (WNDPROC/TIMERPROC = 4 引数, EnumWindows 系 = 2 引数)。icall hook 未設定なら fnmap 経由の直接呼出 */
typedef uint64_t (*GuiIcallHook)(uint64_t target, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3);
void gui_set_icall_hook(GuiIcallHook h);
I64 gui_call4(U64 target, I64 a0, I64 a1, I64 a2, I64 a3);
I64 gui_call2(U64 target, I64 a0, I64 a1);
I64 gui_call3(U64 target, I64 a0, I64 a1, I64 a2);               /* HOOKPROC */
/* リソース供給 (LoadStringW/LoadBitmapW): 結合側が shimx のリソース供給 (FindResource/LoadResource 相当) を接続する。
 * type は RT_xxx の数値、id は整数 ID (MAKEINTRESOURCE)。見つかれば out 引数 data/size を設定して 1 を返す */
typedef int (*GuiResProvider)(uint64_t hinst, uint32_t type, uint32_t id, const void **data, uint32_t *size);
void gui_set_resource_provider(GuiResProvider p);
/* 到達 API ログ (gui_reach.c) */
void gui_reach_hit(int idx);
void gui_reach_paint(void);
void gui_reach_hit_name(const char *name);
int  gui_reach_index(const char *name);
void gui_reach_dump(void);
void gui_set_last_error(uint32_t e);

#endif
