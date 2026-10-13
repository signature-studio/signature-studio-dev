/* gui_gdi.c — gdi32/msimg32 相当: ソフトウェアラスタライザ (BGRA32 top-down surface / DIB section)
 * 方針: FL は描画をほぼ自前ビットマップで行い GDI は転送 (BitBlt/StretchDIBits) 経路が主 (IMPORTS.md)。
 * プリミティブ (線/矩形/文字) は最小限、テキストは内蔵 8x8 ビットマップフォント (決定論的)。 */
#include <stdio.h>
#include <stdarg.h>
#include "gui_internal.h"
#include "gui_font8x8.h"
#include "gui_simd.h"

#define API int64_t

/* Bmp: bits = 内部 BGRA32 surface (GDI の描画対象; 「shadow」)。bpp != 32 の DIB section は app から見えるネイティブ形式の nat (行 4B 境界) を別に持ち、
 * GDI 操作の前後で pull (nat -> shadow) / push (shadow -> nat) を行う (DDB は shadow のみ; mono = 1bpp DDB: 白 0xFFFFFFFF/黒 0xFF000000 を保持し、
 * 転送時に転送先 DC の bk/tc 色へ写像する)。pal は bpp<=8 の色テーブル (256 要素; 範囲外 index は黒)。 */
typedef struct Bmp { int w, h, stride, topdown, owns, sel, deleted; uint8_t *bits;
  int bpp, nstride, isdib, mono, npal; uint8_t *nat; uint32_t *pal; } Bmp;
typedef struct Brush { int hollow, stock, sysidx; uint32_t color; } Brush;
typedef struct Pen { int style, width, stock; uint32_t color; } Pen;
typedef struct Font { int height, stock; } Font;
typedef struct Rgn { RL rl; } Rgn;
typedef struct DCState {
  int dx_wox, wox, woy, vox, voy, bx, by; uint32_t bk, tc; int bkmode, rop2, align, stretch;
  U64 hbrush, hpen, hfont; WPOINT cur; RL user; int has_user; struct DCState *next;
} DCState;
typedef struct DC {
  int kind;               /* 1 window / 2 memory */
  int surf, ox, oy;       /* window: surface id + client 原点 */
  U64 hbmp;               /* memory: 選択中ビットマップ */
  struct Bmp *bp;         /* 同ポインタ (選択中に DeleteObject されてもハンドル失効後に解放できるよう保持) */
  int wox, woy, vox, voy, bx, by;
  RL base; int has_base;
  RL user; int has_user;
  RL eff; int eff_valid;
  U64 hbrush, hpen, hfont;
  uint32_t bk, tc; int bkmode, rop2, align, stretch;
  WPOINT cur;
  DCState *saved;
} DC;

static U64 g_stock[20]; static U64 g_def_bmp; static U64 g_def_pal;
static Bmp g_dummy_bmp;

static uint32_t sysbrush_color(int idx) {
  static const uint32_t t[] = { 0xC8D0D4, 0x6A240A, 0x800000, 0xC8D0D4, 0xC8D0D4, 0xFFFFFF, 0x000000, 0x000000, 0x000000, 0xFFFFFF };
  if (idx == 5) return 0xFFFFFF; if (idx == 15) return 0xF0F0F0;
  return idx >= 0 && idx < 10 ? t[idx] : 0xC0C0C0;
}
static U64 new_brush(uint32_t color, int hollow, int stock) {
  Brush *b = (Brush *)calloc(1, sizeof *b); b->color = color; b->hollow = hollow; b->stock = stock; b->sysidx = -1;
  return h_alloc(HT_BRUSH, b);
}
static U64 new_pen(int style, int width, uint32_t color, int stock) {
  Pen *p = (Pen *)calloc(1, sizeof *p); p->style = style; p->width = width < 1 ? 1 : width; p->color = color; p->stock = stock;
  return h_alloc(HT_PEN, p);
}
void gdi_init(void) {
  g_stock[WHITE_BRUSH] = new_brush(0xFFFFFF, 0, 1);
  g_stock[LTGRAY_BRUSH] = new_brush(0xC0C0C0, 0, 1);
  g_stock[GRAY_BRUSH] = new_brush(0x808080, 0, 1);
  g_stock[DKGRAY_BRUSH] = new_brush(0x404040, 0, 1);
  g_stock[BLACK_BRUSH] = new_brush(0x000000, 0, 1);
  g_stock[NULL_BRUSH] = new_brush(0, 1, 1);
  g_stock[WHITE_PEN] = new_pen(PS_SOLID, 1, 0xFFFFFF, 1);
  g_stock[BLACK_PEN] = new_pen(PS_SOLID, 1, 0x000000, 1);
  g_stock[NULL_PEN] = new_pen(PS_NULL, 1, 0, 1);
  Font *f = (Font *)calloc(1, sizeof *f); f->height = 8; f->stock = 1;
  g_stock[SYSTEM_FONT] = h_alloc(HT_FONT, f);
  g_stock[DEFAULT_GUI_FONT] = g_stock[SYSTEM_FONT]; g_stock[SYSTEM_FIXED_FONT] = g_stock[SYSTEM_FONT];
  g_stock[DEFAULT_PALETTE] = g_def_pal = h_alloc(HT_PAL, calloc(1, 8));
  g_stock[DC_BRUSH] = g_stock[WHITE_BRUSH]; g_stock[DC_PEN] = g_stock[BLACK_PEN];
  static uint32_t one; g_dummy_bmp.w = g_dummy_bmp.h = 1; g_dummy_bmp.stride = 4; g_dummy_bmp.topdown = 1; g_dummy_bmp.bits = (uint8_t *)&one;
  Bmp *b = (Bmp *)calloc(1, sizeof *b); b->w = b->h = 1; b->stride = 4; b->topdown = 1; b->owns = 1; b->bits = (uint8_t *)calloc(1, 4);
  g_def_bmp = h_alloc(HT_BMP, b);
}

/* ---------- DC ---------- */
static DC *dc_of(U64 h) { return (DC *)h_get(h, HT_DC); }
int gdi_dc_is_valid(U64 h) { return dc_of(h) != NULL; }
static DC *dc_new(int kind) {
  DC *d = (DC *)calloc(1, sizeof *d);
  d->kind = kind; d->hbrush = g_stock[WHITE_BRUSH]; d->hpen = g_stock[BLACK_PEN]; d->hfont = g_stock[SYSTEM_FONT];
  d->bk = 0xFFFFFF; d->tc = 0; d->bkmode = OPAQUE_; d->rop2 = 13; d->align = 0; d->stretch = 1;
  return d;
}
U64 gdi_get_dc_for_wnd(Wnd *w, int window_dc, const RL *clip) {
  DC *d = dc_new(1);
  int surf, ox, oy;
  if (!wnd_target(w, &surf, &ox, &oy)) gui_failfast("GetDC", "window has no surface");
  if (window_dc) wnd_window_origin(w, &ox, &oy);   /* GetWindowDC: 原点 = window rect 左上 */
  d->surf = surf; d->ox = ox; d->oy = oy;
  if (clip) { rl_copy(&d->base, clip); d->has_base = 1; }
  return h_alloc(HT_DC, d);
}
static void bmp_free(Bmp *b) { if (b->owns) free(b->bits); free(b->nat); free(b->pal); free(b); }
static void bmp_unref(Bmp *b) {
  if (!b) return;
  if (b->sel > 0) b->sel--;
  if (b->deleted && b->sel == 0) bmp_free(b);
}
static void dc_free(DC *d) {
  if (d->kind == 2) bmp_unref(d->bp ? d->bp : (Bmp *)h_get(d->hbmp, HT_BMP));
  rl_free(&d->base); rl_free(&d->user); rl_free(&d->eff);
  while (d->saved) { DCState *s = d->saved; d->saved = s->next; rl_free(&s->user); free(s); }
  free(d);
}
void gdi_release_dc(U64 h) {
  DC *d = dc_of(h); if (!d) return;
  h_free(h); dc_free(d);
}
API DeleteDC(I64 h) { DC *d = dc_of((U64)h); if (!d) return 0; h_free((U64)h); dc_free(d); return 1; }
API CreateCompatibleDC(I64 hdc) {
  gui_sh(); (void)hdc;
  DC *d = dc_new(2); d->hbmp = g_def_bmp;
  Bmp *b = (Bmp *)h_get(g_def_bmp, HT_BMP); b->sel++; d->bp = b;
  return (I64)h_alloc(HT_DC, d);
}

/* 描画先ビュー: row0 は論理 top 行, rowstep は符号付きバイト */
typedef struct { uint8_t *row0; int rowstep; int w, h; Bmp *bmp; int mono; } Tgt;
static int dc_tgt(DC *d, Tgt *t) {
  if (d->kind == 1) {
    SurfView v; if (!surf_view(d->surf, &v)) return 0;
    surf_wseq_begin(d->surf);
    t->row0 = v.px; t->rowstep = v.stride; t->w = v.w; t->h = v.h; t->bmp = NULL; t->mono = 0; return 1;
  }
  Bmp *b = (Bmp *)h_get(d->hbmp, HT_BMP);
  if (!b) b = &g_dummy_bmp;
  if (b->topdown) { t->row0 = b->bits; t->rowstep = b->stride; }
  else { t->row0 = b->bits + (size_t)(b->h - 1) * b->stride; t->rowstep = -b->stride; }
  t->w = b->w; t->h = b->h; t->bmp = b == &g_dummy_bmp ? NULL : b; t->mono = b->mono; return 1;
}
static inline uint32_t *px_at(const Tgt *t, int x, int y) { return (uint32_t *)(t->row0 + (ptrdiff_t)y * t->rowstep) + x; }
static int dev_dx(DC *d) { return (d->kind == 1 ? d->ox : 0) - d->wox + d->vox; }
static int dev_dy(DC *d) { return (d->kind == 1 ? d->oy : 0) - d->woy + d->voy; }
static RL *dc_eff(DC *d, const Tgt *t) {
  if (!d->eff_valid) {
    rl_clear(&d->eff);
    rl_add(&d->eff, (WRECT){ 0, 0, t->w, t->h });
    if (d->has_base) rl_intersect(&d->eff, &d->base);
    if (d->has_user) rl_intersect(&d->eff, &d->user);
    d->eff_valid = 1;
  }
  return &d->eff;
}
/* ---------- ネイティブ形式 DIB (24/8/4/1bpp) <-> BGRA shadow ---------- */
static inline int dib_stride(int bpp, int w) { return (int)((((int64_t)w * bpp + 31) / 32) * 4); }
static int dib_bpp_ok(int bpp) { return bpp == 1 || bpp == 4 || bpp == 8 || bpp == 24 || bpp == 32; }
/* 1 行デコード: ネイティブ行 (bpp 1/4/8/24/32) -> BGRA32 (alpha 0xFF; 32bpp のみ alpha を保持せず 0xFF 化)。pal は bpp<=8 で 2^bpp 要素以上 */
static void row_decode(int bpp, const uint8_t *in, int w, const uint32_t *pal, uint32_t *out) {
  switch (bpp) {
    case 32: for (int x = 0; x < w; x++) { uint32_t v; memcpy(&v, in + (size_t)x * 4, 4); out[x] = v | 0xFF000000u; } break;
    case 24: for (int x = 0; x < w; x++) { const uint8_t *p = in + (size_t)x * 3; out[x] = 0xFF000000u | ((uint32_t)p[2] << 16) | ((uint32_t)p[1] << 8) | p[0]; } break;
    case 8: for (int x = 0; x < w; x++) out[x] = pal[in[x]]; break;
    case 4: for (int x = 0; x < w; x++) out[x] = pal[(x & 1) ? (in[x >> 1] & 15) : (in[x >> 1] >> 4)]; break;
    case 1: for (int x = 0; x < w; x++) out[x] = pal[(in[x >> 3] >> (7 - (x & 7))) & 1]; break;
    default: { char m[40]; snprintf(m, sizeof m, "DIB bpp=%d", bpp); gui_failfast("gdi.dib", m); }
  }
}
/* パレット最近傍 (RGB 二乗距離; 完全一致は最初の index)。 */
static int pal_nearest(const uint32_t *pal, int n, uint32_t px) {
  int best = 0; int64_t bd = -1;
  for (int i = 0; i < n; i++) {
    int dr = (int)((px >> 16) & 255) - (int)((pal[i] >> 16) & 255), dg = (int)((px >> 8) & 255) - (int)((pal[i] >> 8) & 255), db = (int)(px & 255) - (int)(pal[i] & 255);
    int64_t d = (int64_t)dr * dr + (int64_t)dg * dg + (int64_t)db * db;
    if (bd < 0 || d < bd) { bd = d; best = i; if (!d) break; }
  }
  return best;
}
/* 1 行エンコード: BGRA32 -> ネイティブ行 (bpp 24/32 は無損失、<=8 はパレット最近傍)。out は呼出側がゼロ初期化済みであること (4/1bpp は OR で詰める) */
static void row_encode(int bpp, uint8_t *out, const uint32_t *in, int w, const uint32_t *pal, int npal) {
  uint32_t lastp = 0xFFFFFFFFu; int lasti = 0;
  switch (bpp) {
    case 32: memcpy(out, in, (size_t)w * 4); break;
    case 24: for (int x = 0; x < w; x++) { out[3 * x] = (uint8_t)in[x]; out[3 * x + 1] = (uint8_t)(in[x] >> 8); out[3 * x + 2] = (uint8_t)(in[x] >> 16); } break;
    default:
      for (int x = 0; x < w; x++) {
        uint32_t p = in[x] & 0xFFFFFF; if (p != lastp) { lasti = pal_nearest(pal, npal, p); lastp = p; }
        if (bpp == 8) out[x] = (uint8_t)lasti;
        else if (bpp == 4) out[x >> 1] |= (uint8_t)((x & 1) ? lasti : lasti << 4);
        else out[x >> 3] |= (uint8_t)(lasti << (7 - (x & 7)));
      }
  }
}
static uint32_t pal_at(const Bmp *b, int idx) { return b->pal[idx]; }
/* nat -> shadow (論理 top 基準の矩形)。nat を持たない Bmp では何もしない */
static void bmp_pull(Bmp *b, WRECT r) {
  if (!b || !b->nat) return;
  r = r_isect(r, (WRECT){ 0, 0, b->w, b->h }); if (r_empty(r)) return;
  uint32_t *tmp = (uint32_t *)malloc((size_t)b->w * 4);
  for (int y = r.top; y < r.bottom; y++) {
    int m = b->topdown ? y : b->h - 1 - y;
    row_decode(b->bpp, b->nat + (size_t)m * b->nstride, b->w, b->pal, tmp);
    memcpy((uint32_t *)(b->bits + (size_t)m * b->stride) + r.left, tmp + r.left, (size_t)(r.right - r.left) * 4);
  }
  free(tmp);
}
/* shadow -> nat。パレット DIB は「現在の index の色が shadow と同じなら index を変えない」(重複色パレットで app の index を壊さない) */
static void bmp_push(Bmp *b, WRECT r) {
  if (!b || !b->nat) return;
  r = r_isect(r, (WRECT){ 0, 0, b->w, b->h }); if (r_empty(r)) return;
  for (int y = r.top; y < r.bottom; y++) {
    int m = b->topdown ? y : b->h - 1 - y;
    const uint32_t *sp = (const uint32_t *)(b->bits + (size_t)m * b->stride);
    uint8_t *np = b->nat + (size_t)m * b->nstride;
    if (b->bpp == 24) { for (int x = r.left; x < r.right; x++) { np[3 * x] = (uint8_t)sp[x]; np[3 * x + 1] = (uint8_t)(sp[x] >> 8); np[3 * x + 2] = (uint8_t)(sp[x] >> 16); } continue; }
    uint32_t lastp = 0xFFFFFFFFu; int lasti = 0;
    for (int x = r.left; x < r.right; x++) {
      int cur = b->bpp == 8 ? np[x] : b->bpp == 4 ? ((x & 1) ? (np[x >> 1] & 15) : (np[x >> 1] >> 4)) : ((np[x >> 3] >> (7 - (x & 7))) & 1);
      uint32_t p = sp[x] & 0xFFFFFF;
      if (((pal_at(b, cur) ^ p) & 0xFFFFFF) == 0) continue;
      if (p != lastp) { lasti = pal_nearest(b->pal, b->npal, p); lastp = p; }
      if (b->bpp == 8) np[x] = (uint8_t)lasti;
      else if (b->bpp == 4) np[x >> 1] = (uint8_t)((x & 1) ? ((np[x >> 1] & 0xF0) | lasti) : ((np[x >> 1] & 0x0F) | (lasti << 4)));
      else np[x >> 3] = (uint8_t)((np[x >> 3] & ~(1 << (7 - (x & 7)))) | (lasti << (7 - (x & 7))));
    }
  }
}
static inline void tgt_pull(const Tgt *t, WRECT r) { if (t->bmp && t->bmp->nat) bmp_pull(t->bmp, r); }
/* mono DDB への書込みを白/黒へ正規化 (輝度 (30R+59G+11B)/100 >= 128 が白) */
static void mono_norm(Bmp *b, WRECT r) {
  r = r_isect(r, (WRECT){ 0, 0, b->w, b->h }); if (r_empty(r)) return;
  for (int y = r.top; y < r.bottom; y++) {
    int m = b->topdown ? y : b->h - 1 - y; uint32_t *p = (uint32_t *)(b->bits + (size_t)m * b->stride);
    for (int x = r.left; x < r.right; x++) { uint32_t c = p[x]; uint32_t l = (((c >> 16) & 255) * 30 + ((c >> 8) & 255) * 59 + (c & 255) * 11) / 100; p[x] = l >= 128 ? 0xFFFFFFFFu : 0xFF000000u; }
  }
}
static void dc_dirty(DC *d, WRECT dev) {
  if (d->kind == 1) { surf_dirty(d->surf, dev); return; }
  Bmp *b = (Bmp *)h_get(d->hbmp, HT_BMP); if (!b) return;
  if (b->nat) bmp_push(b, dev);
  else if (b->mono) mono_norm(b, dev);
}

/* ---------- ROP2 / ピクセル ---------- */
static uint32_t apply_rop2(uint32_t dst, uint32_t src, int rop2) {
  switch (rop2) {
    case 13: return src | 0xFF000000u;
    case 7: return ((dst ^ src) & 0xFFFFFF) | 0xFF000000u;
    case 6: return (~dst & 0xFFFFFF) | 0xFF000000u;
    case 1: return 0xFF000000u;
    case 16: return 0xFFFFFFFFu;
    case 11: return dst;
    case 9: return ((dst & src) & 0xFFFFFF) | 0xFF000000u;
    case 15: return ((dst | src) & 0xFFFFFF) | 0xFF000000u;
    case 4: return (~src & 0xFFFFFF) | 0xFF000000u;
  }
  char m[48]; snprintf(m, sizeof m, "SetROP2 mode %d", rop2); gui_failfast("gdi.rop2", m);
}
static void fill_dev(DC *d, WRECT r, uint32_t bgra, int rop2) {
  Tgt t; if (!dc_tgt(d, &t)) return;
  RL *eff = dc_eff(d, &t);
  tgt_pull(&t, r);
  for (int i = 0; i < eff->n; i++) {
    WRECT c = r_isect(r, eff->r[i]);
    for (int y = c.top; y < c.bottom; y++) {
      uint32_t *p = px_at(&t, c.left, y);
      if (rop2 == 13) for (int x = c.left; x < c.right; x++) *p++ = bgra | 0xFF000000u;
      else for (int x = c.left; x < c.right; x++, p++) *p = apply_rop2(*p, bgra, rop2);
    }
  }
  dc_dirty(d, r);
}
static void put_dev(DC *d, int x, int y, uint32_t bgra) { fill_dev(d, (WRECT){ x, y, x + 1, y + 1 }, bgra, d->rop2); }
void gdi_fill_rect_dc(U64 hdc, WRECT r, uint32_t colorref) {
  DC *d = dc_of(hdc); if (!d) return;
  int dx = dev_dx(d), dy = dev_dy(d);
  fill_dev(d, (WRECT){ r.left + dx, r.top + dy, r.right + dx, r.bottom + dy }, COLORREF_TO_BGRA(colorref), 13);
}
int gdi_brush_color(U64 h, uint32_t *col) {
  Brush *b = (Brush *)h_get(h, HT_BRUSH); if (!b || b->hollow) return 0;
  *col = b->color; return 1;
}

/* ---------- オブジェクト ---------- */
API GetStockObject(I64 i) { gui_sh(); return (i >= 0 && i < 20 && g_stock[i]) ? (I64)g_stock[i] : 0; }
API CreateSolidBrush(I64 c) { gui_sh(); return (I64)new_brush((uint32_t)c & 0xFFFFFF, 0, 0); }
API CreatePen(I64 style, I64 w, I64 c) {
  gui_sh();
  if (style != PS_SOLID && style != PS_NULL && style != 6) { char m[48]; snprintf(m, sizeof m, "CreatePen style %d", (int)style); gui_failfast("CreatePen", m); }
  return (I64)new_pen((int)style == 6 ? PS_SOLID : (int)style, (int)w, (uint32_t)c & 0xFFFFFF, 0);
}
API CreateFontIndirectW(I64 lf) { gui_sh(); Font *f = (Font *)calloc(1, sizeof *f); int32_t h = lf ? *(int32_t *)P_(lf) : 8; f->height = h < 0 ? -h : h; return (I64)h_alloc(HT_FONT, f); }
API CreateFontIndirectA(I64 lf) { return CreateFontIndirectW(lf); }
API CreateFontW(I64 h, I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g, I64 i, I64 j, I64 k, I64 l, I64 m, I64 n) {
  (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)i; (void)j; (void)k; (void)l; (void)m; (void)n;
  gui_sh(); Font *fo = (Font *)calloc(1, sizeof *fo); fo->height = (int)(h < 0 ? -h : h); return (I64)h_alloc(HT_FONT, fo);
}
API CreateFontA(I64 h, I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g, I64 i, I64 j, I64 k, I64 l, I64 m, I64 n) { return CreateFontW(h, a, b, c, d, e, f, g, i, j, k, l, m, n); }
API CreatePalette(I64 lp) { (void)lp; gui_sh(); return (I64)h_alloc(HT_PAL, calloc(1, 8)); }

static Bmp *bmp_new(int w, int h, int topdown) {
  Bmp *b = (Bmp *)calloc(1, sizeof *b);
  if (w < 0) w = -w; if (h < 0) h = -h;
  b->w = w; b->h = h; b->stride = w * 4; b->topdown = topdown; b->owns = 1; b->bpp = 32;
  b->bits = (uint8_t *)calloc((size_t)(w ? w : 1) * (h ? h : 1), 4);
  return b;
}
/* BITMAPINFO の色テーブル (RGBQUAD, ヘッダ直後) -> BGRA 256 要素 (未指定/範囲外は黒)。返値 = 有効エントリ数 */
static int bmi_palette(const WBMIH *bi, uint32_t pal[256]) {
  int bpp = bi->biBitCount, full = 1 << bpp, n = bi->biClrUsed ? (int)bi->biClrUsed : full;
  if (n > full) n = full;
  for (int i = 0; i < 256; i++) pal[i] = 0xFF000000u;
  const uint8_t *q = (const uint8_t *)bi + bi->biSize;
  for (int i = 0; i < n; i++) { uint32_t v; memcpy(&v, q + (size_t)i * 4, 4); pal[i] = v | 0xFF000000u; }
  return n;
}
API CreateCompatibleBitmap(I64 hdc, I64 w, I64 h) {
  gui_sh(); if (w <= 0 || h <= 0) return 0;
  Bmp *b = bmp_new((int)w, (int)h, 1);
  DC *d = dc_of((U64)hdc);
  if (d && d->kind == 2) { Bmp *cur = d->bp; if (cur && cur->mono) { b->mono = 1; b->bpp = 1; for (size_t i = 0; i < (size_t)b->w * b->h; i++) ((uint32_t *)b->bits)[i] = 0xFF000000u; } }   /* mono DC 互換 = mono DDB */
  return (I64)h_alloc(HT_BMP, b);
}
/* CreateBitmap: bpp=1 は mono DDB (bit 1 = 白)。bits の行は WORD (2B) 境界・top-down。24/32bpp は直接色。
 * 4/8/16bpp の初期 bits は論理パレット (DDB のシステムパレット) が必要なので fail-fast (bits なしの生成と、DIB section/SetDIBits 経由は可) */
API CreateBitmap(I64 w, I64 h, I64 planes, I64 bpp, I64 bits) {
  gui_sh();
  if (w <= 0 || h <= 0) return 0;
  if (planes != 1) { char m[64]; snprintf(m, sizeof m, "CreateBitmap planes=%d (only 1)", (int)planes); gui_failfast("CreateBitmap", m); }
  if (!(bpp == 1 || bpp == 4 || bpp == 8 || bpp == 16 || bpp == 24 || bpp == 32)) { char m[64]; snprintf(m, sizeof m, "CreateBitmap bpp=%d (1/4/8/16/24/32)", (int)bpp); gui_failfast("CreateBitmap", m); }
  if (bits && (bpp == 4 || bpp == 8 || bpp == 16)) { char m[96]; snprintf(m, sizeof m, "CreateBitmap bpp=%d with initial bits (needs a logical palette / 16bpp layout; use CreateDIBSection or SetDIBits)", (int)bpp); gui_failfast("CreateBitmap", m); }
  Bmp *b = bmp_new((int)w, (int)h, 1);
  if (bpp == 1) {
    b->mono = 1; b->bpp = 1;
    int ws = (int)((((int64_t)w + 15) / 16) * 2);
    for (int y = 0; y < b->h; y++) for (int x = 0; x < b->w; x++) {
      int bit = bits ? ((((const uint8_t *)P_(bits))[(size_t)y * ws + (x >> 3)] >> (7 - (x & 7))) & 1) : 0;
      ((uint32_t *)b->bits)[(size_t)y * b->w + x] = bit ? 0xFFFFFFFFu : 0xFF000000u;
    }
  } else if (bits && bpp == 24) {
    int ws = (int)((((int64_t)w * 24 + 15) / 16) * 2);
    for (int y = 0; y < b->h; y++) row_decode(24, (const uint8_t *)P_(bits) + (size_t)y * ws, b->w, NULL, (uint32_t *)b->bits + (size_t)y * b->w);
  } else if (bits && bpp == 32) memcpy(b->bits, P_(bits), (size_t)w * h * 4);
  b->bpp = (int)bpp;
  return (I64)h_alloc(HT_BMP, b);
}
API CreateDIBSection(I64 hdc, I64 bmi, I64 usage, I64 ppv, I64 hsec, I64 off) {
  (void)hdc; (void)off; gui_sh();
  const WBMIH *bi = (const WBMIH *)P_(bmi);
  if (hsec) gui_failfast("CreateDIBSection", "file-mapping backed DIB section not supported");
  int bpp = bi->biBitCount;
  if (!dib_bpp_ok(bpp) || !(bi->biCompression == BI_RGB || (bi->biCompression == BI_BITFIELDS && bpp == 32))) {
    char m[64]; snprintf(m, sizeof m, "DIB bpp=%d comp=%u (1/4/8/24 BI_RGB, 32 BI_RGB/BITFIELDS)", bpp, bi->biCompression); gui_failfast("CreateDIBSection", m);
  }
  if (bpp <= 8 && usage != DIB_RGB_COLORS) gui_failfast("CreateDIBSection", "DIB_PAL_COLORS (logical-palette indices) not supported");
  if (bi->biSize < 40) gui_failfast("CreateDIBSection", "BITMAPCOREHEADER not supported");
  Bmp *b = bmp_new(bi->biWidth, bi->biHeight, bi->biHeight < 0);
  b->isdib = 1; b->bpp = bpp;
  if (bpp != 32) {
    b->nstride = dib_stride(bpp, b->w);
    b->nat = (uint8_t *)calloc((size_t)b->nstride * (b->h ? b->h : 1), 1);
    if (bpp <= 8) { b->pal = (uint32_t *)malloc(256 * 4); b->npal = bmi_palette(bi, b->pal); }
    bmp_pull(b, (WRECT){ 0, 0, b->w, b->h });   /* shadow 初期化 (ゼロ index -> pal[0] / 24bpp -> 黒) */
  }
  if (ppv) *(U64 *)P_(ppv) = (U64)(uintptr_t)(b->nat ? b->nat : b->bits);
  return (I64)h_alloc(HT_BMP, b);
}
API DeleteObject(I64 h) {
  HType t = h_type((U64)h);
  switch (t) {
    case HT_BMP: { Bmp *b = (Bmp *)h_get((U64)h, HT_BMP); h_free((U64)h); b->deleted = 1; if (b->sel == 0) bmp_free(b); return 1; }
    case HT_BRUSH: { Brush *b = (Brush *)h_get((U64)h, HT_BRUSH); if (b->stock) return 1; h_free((U64)h); free(b); return 1; }
    case HT_PEN: { Pen *p = (Pen *)h_get((U64)h, HT_PEN); if (p->stock) return 1; h_free((U64)h); free(p); return 1; }
    case HT_FONT: { Font *f = (Font *)h_get((U64)h, HT_FONT); if (f->stock) return 1; h_free((U64)h); free(f); return 1; }
    case HT_RGN: { Rgn *r = (Rgn *)h_get((U64)h, HT_RGN); h_free((U64)h); rl_free(&r->rl); free(r); return 1; }
    case HT_PAL: { if ((U64)h == g_def_pal) return 1; void *p = h_get((U64)h, HT_PAL); h_free((U64)h); free(p); return 1; }
    default: return 0;
  }
}
API SelectObject(I64 hdc, I64 ho) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  U64 old = 0;
  switch (h_type((U64)ho)) {
    case HT_BRUSH: old = d->hbrush; d->hbrush = (U64)ho; break;
    case HT_PEN: old = d->hpen; d->hpen = (U64)ho; break;
    case HT_FONT: old = d->hfont; d->hfont = (U64)ho; break;
    case HT_BMP: {
      if (d->kind != 2) return 0;
      Bmp *nb = (Bmp *)h_get((U64)ho, HT_BMP);
      old = d->hbmp; Bmp *ob = d->bp ? d->bp : (Bmp *)h_get(old, HT_BMP);
      if (ob) bmp_unref(ob);
      nb->sel++; d->hbmp = (U64)ho; d->bp = nb; d->eff_valid = 0;
      break;
    }
    case HT_RGN: { extern API SelectClipRgn(I64, I64); return SelectClipRgn(hdc, ho); }
    default: return 0;
  }
  return (I64)old;
}
API SelectPalette(I64 hdc, I64 pal, I64 bg) { (void)bg; DC *d = dc_of((U64)hdc); if (!d) return 0; (void)pal; return (I64)g_def_pal; }
API RealizePalette(I64 hdc) { (void)hdc; return 0; }
API GetCurrentObject(I64 hdc, I64 type) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  switch ((int)type) { case 1: return (I64)d->hpen; case 2: return (I64)d->hbrush; case 6: return (I64)d->hfont; case 7: return (I64)d->hbmp; }
  return 0;
}
static int get_object_impl(I64 h, I64 n, I64 buf) {
  switch (h_type((U64)h)) {
    case HT_BMP: {
      Bmp *b = (Bmp *)h_get((U64)h, HT_BMP);
      if (!buf) return 104;
      if (n < 32) return 0;
      WBITMAP bm = { 0, b->w, b->h, b->nat ? b->nstride : b->stride, 1, (uint16_t)b->bpp, (U64)(uintptr_t)(b->nat ? b->nat : b->bits) };
      memset(P_(buf), 0, (size_t)(n < 104 ? n : 104));
      memcpy(P_(buf), &bm, 32);
      if (n >= 72) { WBMIH bi = { 40, b->w, b->topdown ? -b->h : b->h, 1, (uint16_t)b->bpp, 0, (uint32_t)((b->nat ? b->nstride : b->stride) * b->h), 0, 0, b->pal ? (uint32_t)b->npal : 0, 0 }; memcpy((uint8_t *)P_(buf) + 32, &bi, 40); return n >= 104 ? 104 : 32; }
      return 32;
    }
    case HT_BRUSH: { Brush *b = (Brush *)h_get((U64)h, HT_BRUSH); if (!buf) return 16; WLOGBRUSH lb = { b->hollow ? 1 : 0, b->color, 0 }; memcpy(P_(buf), &lb, 16); return 16; }
    case HT_PEN: { Pen *p = (Pen *)h_get((U64)h, HT_PEN); if (!buf) return 16; int32_t v[4] = { p->style, p->width, 0, (int32_t)p->color }; memcpy(P_(buf), v, 16); return 16; }
    case HT_FONT: { Font *f = (Font *)h_get((U64)h, HT_FONT); if (!buf) return 92; memset(P_(buf), 0, (size_t)(n < 92 ? n : 92)); *(int32_t *)P_(buf) = f->height; return (int)(n < 92 ? n : 92); }
    default: return 0;
  }
}
API GetObjectW(I64 h, I64 n, I64 buf) { return get_object_impl(h, n, buf); }
API GetObjectA(I64 h, I64 n, I64 buf) { return get_object_impl(h, n, buf); }

/* ---------- 状態 ---------- */
API SetBkColor(I64 hdc, I64 c) { DC *d = dc_of((U64)hdc); if (!d) return 0xFFFFFFFF; uint32_t o = d->bk; d->bk = (uint32_t)c & 0xFFFFFF; return o; }
API GetBkColor(I64 hdc) { DC *d = dc_of((U64)hdc); return d ? d->bk : 0xFFFFFFFF; }
API SetTextColor(I64 hdc, I64 c) { DC *d = dc_of((U64)hdc); if (!d) return 0xFFFFFFFF; uint32_t o = d->tc; d->tc = (uint32_t)c & 0xFFFFFF; return o; }
API GetTextColor(I64 hdc) { DC *d = dc_of((U64)hdc); return d ? d->tc : 0xFFFFFFFF; }
API SetBkMode(I64 hdc, I64 m) { DC *d = dc_of((U64)hdc); if (!d) return 0; int o = d->bkmode; d->bkmode = (int)m; return o; }
API SetROP2(I64 hdc, I64 m) { DC *d = dc_of((U64)hdc); if (!d) return 0; int o = d->rop2; d->rop2 = (int)m; return o; }
API SetStretchBltMode(I64 hdc, I64 m) { DC *d = dc_of((U64)hdc); if (!d) return 0; int o = d->stretch; d->stretch = (int)m; return o; }
API GetStretchBltMode(I64 hdc) { DC *d = dc_of((U64)hdc); return d ? d->stretch : 0; }
API SetTextAlign(I64 hdc, I64 a) { DC *d = dc_of((U64)hdc); if (!d) return 0; int o = d->align; d->align = (int)a; return o; }
API GetTextAlign(I64 hdc) { DC *d = dc_of((U64)hdc); return d ? d->align : 0; }
API SetMapMode(I64 hdc, I64 m) { (void)hdc; if (m != 1) gui_failfast("SetMapMode", "only MM_TEXT supported"); return 1; }
API SetBrushOrgEx(I64 hdc, I64 x, I64 y, I64 old) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  if (old) { WPOINT *p = (WPOINT *)P_(old); p->x = d->bx; p->y = d->by; }
  d->bx = (int)x; d->by = (int)y; return 1;
}
API GetBrushOrgEx(I64 hdc, I64 pt) { DC *d = dc_of((U64)hdc); if (!d || !pt) return 0; WPOINT *p = (WPOINT *)P_(pt); p->x = d->bx; p->y = d->by; return 1; }
API SetWindowOrgEx(I64 hdc, I64 x, I64 y, I64 old) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  if (old) { WPOINT *p = (WPOINT *)P_(old); p->x = d->wox; p->y = d->woy; }
  d->wox = (int)x; d->woy = (int)y; return 1;
}
API GetWindowOrgEx(I64 hdc, I64 pt) { DC *d = dc_of((U64)hdc); if (!d) return 0; WPOINT *p = (WPOINT *)P_(pt); p->x = d->wox; p->y = d->woy; return 1; }
API SetViewportOrgEx(I64 hdc, I64 x, I64 y, I64 old) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  if (old) { WPOINT *p = (WPOINT *)P_(old); p->x = d->vox; p->y = d->voy; }
  d->vox = (int)x; d->voy = (int)y; return 1;
}
API LPtoDP(I64 hdc, I64 pts, I64 n) { DC *d = dc_of((U64)hdc); if (!d) return 0; WPOINT *p = (WPOINT *)P_(pts); for (int i = 0; i < n; i++) { p[i].x += d->vox - d->wox; p[i].y += d->voy - d->woy; } return 1; }
API GetDeviceCaps(I64 hdc, I64 idx) {
  GuiShared *sh = gui_sh(); (void)hdc;
  switch ((int)idx) {
    case HORZRES: return sh->screen_w; case VERTRES: return sh->screen_h;
    case HORZSIZE: return sh->screen_w * 254 / 960; case VERTSIZE: return sh->screen_h * 254 / 960;
    case BITSPIXEL: return 32; case PLANES: return 1; case NUMCOLORS: return -1;
    case LOGPIXELSX: case LOGPIXELSY: return gui_dpi(); case SIZEPALETTE: case NUMRESERVED: return 0; case COLORRES: return 24;
    case RASTERCAPS: return 0x7E99 & ~0x100;  /* RC_PALETTE を立てない */
  }
  return 0;
}
API GdiFlush(void) { surf_flush(); return 1; }

/* ---------- クリップ / リージョン ---------- */
static U64 rgn_new(void) { Rgn *r = (Rgn *)calloc(1, sizeof *r); return h_alloc(HT_RGN, r); }
static int rgn_type(Rgn *r) { return r->rl.n == 0 ? NULLREGION : r->rl.n == 1 ? SIMPLEREGION : COMPLEXREGION; }
API CreateRectRgn(I64 l, I64 t, I64 r, I64 b) {
  gui_sh(); U64 h = rgn_new(); Rgn *g = (Rgn *)h_get(h, HT_RGN);
  int L = (int)l, T = (int)t, R = (int)r, B = (int)b;
  if (R < L) { int x = L; L = R; R = x; } if (B < T) { int x = T; T = B; B = x; }
  rl_add(&g->rl, (WRECT){ L, T, R, B }); return (I64)h;
}
void gdi_rgn_set_rl(U64 h, const RL *rl) { Rgn *g = (Rgn *)h_get(h, HT_RGN); if (g) rl_copy(&g->rl, rl); }
API CreateRectRgnIndirect(I64 rc) { const WRECT *r = (const WRECT *)P_(rc); return CreateRectRgn(r->left, r->top, r->right, r->bottom); }
API SetRectRgn(I64 h, I64 l, I64 t, I64 r, I64 b) { Rgn *g = (Rgn *)h_get((U64)h, HT_RGN); if (!g) return 0; rl_clear(&g->rl); rl_add(&g->rl, (WRECT){ (int)l, (int)t, (int)r, (int)b }); return 1; }
API CombineRgn(I64 hd, I64 h1, I64 h2, I64 mode) {
  Rgn *d = (Rgn *)h_get((U64)hd, HT_RGN), *a = (Rgn *)h_get((U64)h1, HT_RGN), *b = (Rgn *)h_get((U64)h2, HT_RGN);
  if (!d || !a) return ERROR_REGION;
  RL t = {0}; rl_copy(&t, &a->rl);
  switch ((int)mode) {
    case RGN_COPY: break;
    case RGN_AND: if (!b) goto bad; rl_intersect(&t, &b->rl); break;
    case RGN_OR: if (!b) goto bad; rl_union(&t, &b->rl); break;
    case RGN_DIFF: if (!b) goto bad; rl_subtract(&t, &b->rl); break;
    case RGN_XOR: { if (!b) goto bad; RL u = {0}; rl_copy(&u, &b->rl); rl_subtract(&u, &a->rl); rl_subtract(&t, &b->rl); rl_union(&t, &u); rl_free(&u); break; }
    default: bad: rl_free(&t); return ERROR_REGION;
  }
  rl_free(&d->rl); d->rl = t;
  return rgn_type(d);
}
API OffsetRgn(I64 h, I64 dx, I64 dy) {
  Rgn *g = (Rgn *)h_get((U64)h, HT_RGN); if (!g) return 0;
  for (int i = 0; i < g->rl.n; i++) { g->rl.r[i].left += (int)dx; g->rl.r[i].right += (int)dx; g->rl.r[i].top += (int)dy; g->rl.r[i].bottom += (int)dy; }
  return rgn_type(g);
}
API GetRgnBox(I64 h, I64 rc) { Rgn *g = (Rgn *)h_get((U64)h, HT_RGN); if (!g) return 0; rl_bbox(&g->rl, (WRECT *)P_(rc)); return rgn_type(g); }
API EqualRgn(I64 a, I64 b) {
  Rgn *x = (Rgn *)h_get((U64)a, HT_RGN), *y = (Rgn *)h_get((U64)b, HT_RGN); if (!x || !y) return 0;
  RL t1 = {0}, t2 = {0}; rl_copy(&t1, &x->rl); rl_copy(&t2, &y->rl);
  rl_subtract(&t1, &y->rl); rl_subtract(&t2, &x->rl);
  int eq = t1.n == 0 && t2.n == 0; rl_free(&t1); rl_free(&t2); return eq;
}
API PtInRegion(I64 h, I64 x, I64 y) { Rgn *g = (Rgn *)h_get((U64)h, HT_RGN); return g && rl_contains(&g->rl, (int)x, (int)y); }
API RectInRegion(I64 h, I64 rc) {
  Rgn *g = (Rgn *)h_get((U64)h, HT_RGN); if (!g) return 0;
  const WRECT *r = (const WRECT *)P_(rc);
  for (int i = 0; i < g->rl.n; i++) if (!r_empty(r_isect(*r, g->rl.r[i]))) return 1;
  return 0;
}
static void set_user_clip(DC *d, RL *rl_dev_owned, int has) {
  rl_free(&d->user); if (has) d->user = *rl_dev_owned; d->has_user = has; d->eff_valid = 0;
}
API SelectClipRgn(I64 hdc, I64 hrgn) {
  DC *d = dc_of((U64)hdc); if (!d) return ERROR_REGION;
  if (!hrgn) { set_user_clip(d, NULL, 0); return SIMPLEREGION; }
  Rgn *g = (Rgn *)h_get((U64)hrgn, HT_RGN); if (!g) return ERROR_REGION;
  RL t = {0}; rl_copy(&t, &g->rl);
  int dx = dev_dx(d), dy = dev_dy(d);
  for (int i = 0; i < t.n; i++) { t.r[i].left += dx; t.r[i].right += dx; t.r[i].top += dy; t.r[i].bottom += dy; }
  set_user_clip(d, &t, 1);
  return rgn_type(g);
}
API ExtSelectClipRgn(I64 hdc, I64 hrgn, I64 mode) {
  DC *d = dc_of((U64)hdc); if (!d) return ERROR_REGION;
  if (mode == RGN_COPY || !d->has_user) return SelectClipRgn(hdc, hrgn);
  Rgn *g = (Rgn *)h_get((U64)hrgn, HT_RGN); if (!g) return ERROR_REGION;
  RL t = {0}; rl_copy(&t, &g->rl);
  int dx = dev_dx(d), dy = dev_dy(d);
  for (int i = 0; i < t.n; i++) { t.r[i].left += dx; t.r[i].right += dx; t.r[i].top += dy; t.r[i].bottom += dy; }
  switch ((int)mode) {
    case RGN_AND: rl_intersect(&d->user, &t); break;
    case RGN_OR: rl_union(&d->user, &t); break;
    case RGN_DIFF: rl_subtract(&d->user, &t); break;
    default: rl_free(&t); gui_failfast("ExtSelectClipRgn", "RGN_XOR mode");
  }
  rl_free(&t); d->eff_valid = 0; return d->user.n ? COMPLEXREGION : NULLREGION;
}
static int ensure_user_clip(DC *d) {
  if (d->has_user) return 1;
  Tgt t; if (!dc_tgt(d, &t)) return 0;
  rl_clear(&d->user); rl_add(&d->user, (WRECT){ 0, 0, t.w, t.h });
  if (d->has_base) rl_intersect(&d->user, &d->base);
  d->has_user = 1; return 1;
}
API IntersectClipRect(I64 hdc, I64 l, I64 t, I64 r, I64 b) {
  DC *d = dc_of((U64)hdc); if (!d || !ensure_user_clip(d)) return ERROR_REGION;
  int dx = dev_dx(d), dy = dev_dy(d);
  rl_intersect_rect(&d->user, (WRECT){ (int)l + dx, (int)t + dy, (int)r + dx, (int)b + dy }); d->eff_valid = 0;
  return d->user.n ? (d->user.n == 1 ? SIMPLEREGION : COMPLEXREGION) : NULLREGION;
}
API ExcludeClipRect(I64 hdc, I64 l, I64 t, I64 r, I64 b) {
  DC *d = dc_of((U64)hdc); if (!d || !ensure_user_clip(d)) return ERROR_REGION;
  int dx = dev_dx(d), dy = dev_dy(d);
  rl_subtract_rect(&d->user, (WRECT){ (int)l + dx, (int)t + dy, (int)r + dx, (int)b + dy }); d->eff_valid = 0;
  return d->user.n ? (d->user.n == 1 ? SIMPLEREGION : COMPLEXREGION) : NULLREGION;
}
API GetClipBox(I64 hdc, I64 rc) {
  DC *d = dc_of((U64)hdc); Tgt t; if (!d || !dc_tgt(d, &t)) return ERROR_REGION;
  RL *e = dc_eff(d, &t); WRECT b; rl_bbox(e, &b);
  int dx = dev_dx(d), dy = dev_dy(d);
  WRECT *o = (WRECT *)P_(rc); o->left = b.left - dx; o->right = b.right - dx; o->top = b.top - dy; o->bottom = b.bottom - dy;
  return e->n ? (e->n == 1 ? SIMPLEREGION : COMPLEXREGION) : NULLREGION;
}
API SaveDC(I64 hdc) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  DCState *s = (DCState *)calloc(1, sizeof *s);
  s->wox = d->wox; s->woy = d->woy; s->vox = d->vox; s->voy = d->voy; s->bx = d->bx; s->by = d->by; s->bk = d->bk; s->tc = d->tc; s->bkmode = d->bkmode;
  s->rop2 = d->rop2; s->align = d->align; s->stretch = d->stretch; s->hbrush = d->hbrush; s->hpen = d->hpen; s->hfont = d->hfont;
  s->cur = d->cur; s->has_user = d->has_user; rl_copy(&s->user, &d->user);
  s->next = d->saved; d->saved = s;
  int n = 0; for (DCState *x = d->saved; x; x = x->next) n++;
  return n;
}
API RestoreDC(I64 hdc, I64 n) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  int depth = 0; for (DCState *x = d->saved; x; x = x->next) depth++;
  int pop = n < 0 ? (int)(-n) : depth - (int)n + 1;
  if (pop < 1 || pop > depth) return 0;
  DCState *s = NULL;
  while (pop--) { if (s) { rl_free(&s->user); free(s); } s = d->saved; d->saved = s->next; }
  d->wox = s->wox; d->woy = s->woy; d->vox = s->vox; d->voy = s->voy; d->bx = s->bx; d->by = s->by; d->bk = s->bk; d->tc = s->tc; d->bkmode = s->bkmode;
  d->rop2 = s->rop2; d->align = s->align; d->stretch = s->stretch; d->hbrush = s->hbrush; d->hpen = s->hpen; d->hfont = s->hfont;
  d->cur = s->cur; rl_free(&d->user); d->user = s->user; d->has_user = s->has_user; d->eff_valid = 0;
  free(s);
  return 1;
}

/* ---------- 矩形 / 線 ---------- */
static uint32_t brush_bgra(U64 h, int *hollow) {
  Brush *b = (Brush *)h_get(h, HT_BRUSH);
  *hollow = (!b || b->hollow);
  return b ? COLORREF_TO_BGRA(b->color) : 0xFF000000u;
}
API FillRect(I64 hdc, I64 rc, I64 hbr) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  const WRECT *r = (const WRECT *)P_(rc);
  uint32_t col;
  if (hbr > 0 && hbr <= 32) col = COLORREF_TO_BGRA(hbr == 6 ? 0xFFFFFF : hbr == 16 ? 0xF0F0F0 : 0xC8D0D4);
  else { int hol; col = brush_bgra((U64)hbr, &hol); if (hol) return 1; }
  int dx = dev_dx(d), dy = dev_dy(d);
  fill_dev(d, (WRECT){ r->left + dx, r->top + dy, r->right + dx, r->bottom + dy }, col, 13);
  return 1;
}
API FrameRect(I64 hdc, I64 rc, I64 hbr) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  const WRECT *r = (const WRECT *)P_(rc); int hol; uint32_t col = brush_bgra((U64)hbr, &hol); if (hol) return 1;
  int dx = dev_dx(d), dy = dev_dy(d); WRECT q = { r->left + dx, r->top + dy, r->right + dx, r->bottom + dy };
  fill_dev(d, (WRECT){ q.left, q.top, q.right, q.top + 1 }, col, 13);
  fill_dev(d, (WRECT){ q.left, q.bottom - 1, q.right, q.bottom }, col, 13);
  fill_dev(d, (WRECT){ q.left, q.top, q.left + 1, q.bottom }, col, 13);
  fill_dev(d, (WRECT){ q.right - 1, q.top, q.right, q.bottom }, col, 13);
  return 1;
}
API PatBlt(I64 hdc, I64 x, I64 y, I64 w, I64 h, I64 rop) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  int dx = dev_dx(d), dy = dev_dy(d);
  WRECT r = { (int)x + dx, (int)y + dy, (int)(x + w) + dx, (int)(y + h) + dy };
  int hol; uint32_t pc = brush_bgra(d->hbrush, &hol);
  switch ((uint32_t)rop) {
    case PATCOPY: if (!hol) fill_dev(d, r, pc, 13); return 1;
    case PATINVERT: fill_dev(d, r, hol ? 0 : pc, 7); return 1;
    case DSTINVERT: fill_dev(d, r, 0, 6); return 1;
    case BLACKNESS: fill_dev(d, r, 0xFF000000u, 13); return 1;
    case WHITENESS: fill_dev(d, r, 0xFFFFFFFFu, 13); return 1;
  }
  char m[48]; snprintf(m, sizeof m, "PatBlt rop 0x%08x", (unsigned)rop); gui_failfast("PatBlt", m);
}
API MoveToEx(I64 hdc, I64 x, I64 y, I64 old) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  if (old) *(WPOINT *)P_(old) = d->cur;
  d->cur.x = (int)x; d->cur.y = (int)y; return 1;
}
API GetCurrentPositionEx(I64 hdc, I64 pt) { DC *d = dc_of((U64)hdc); if (!d) return 0; *(WPOINT *)P_(pt) = d->cur; return 1; }
static void pen_dot(DC *d, int x, int y, int w, uint32_t col) {
  int o = w / 2;
  fill_dev(d, (WRECT){ x - o, y - o, x - o + w, y - o + w }, col, d->rop2);
}
API LineTo(I64 hdc, I64 x, I64 y) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  Pen *p = (Pen *)h_get(d->hpen, HT_PEN);
  int dx = dev_dx(d), dy = dev_dy(d);
  int x0 = d->cur.x + dx, y0 = d->cur.y + dy, x1 = (int)x + dx, y1 = (int)y + dy;
  d->cur.x = (int)x; d->cur.y = (int)y;
  if (!p || p->style == PS_NULL) return 1;
  uint32_t col = COLORREF_TO_BGRA(p->color);
  int adx = abs(x1 - x0), ady = abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, err = adx - ady;
  for (;;) {
    if (x0 == x1 && y0 == y1) break;   /* 終点は描かない (GDI 仕様) */
    pen_dot(d, x0, y0, p->width, col);
    int e2 = 2 * err;
    if (e2 > -ady) { err -= ady; x0 += sx; }
    if (e2 < adx) { err += adx; y0 += sy; }
  }
  return 1;
}
API Rectangle(I64 hdc, I64 l, I64 t, I64 r, I64 b) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  int dx = dev_dx(d), dy = dev_dy(d);
  WRECT q = { (int)l + dx, (int)t + dy, (int)r + dx, (int)b + dy };
  Pen *p = (Pen *)h_get(d->hpen, HT_PEN); int hol; uint32_t bc = brush_bgra(d->hbrush, &hol);
  int pen = p && p->style != PS_NULL;
  if (!hol) fill_dev(d, pen ? (WRECT){ q.left + 1, q.top + 1, q.right - 1, q.bottom - 1 } : q, bc, 13);
  if (pen) {
    uint32_t pc = COLORREF_TO_BGRA(p->color);
    fill_dev(d, (WRECT){ q.left, q.top, q.right, q.top + 1 }, pc, 13);
    fill_dev(d, (WRECT){ q.left, q.bottom - 1, q.right, q.bottom }, pc, 13);
    fill_dev(d, (WRECT){ q.left, q.top, q.left + 1, q.bottom }, pc, 13);
    fill_dev(d, (WRECT){ q.right - 1, q.top, q.right, q.bottom }, pc, 13);
  }
  return 1;
}
API SetPixelV(I64 hdc, I64 x, I64 y, I64 c) { DC *d = dc_of((U64)hdc); if (!d) return 0; put_dev(d, (int)x + dev_dx(d), (int)y + dev_dy(d), COLORREF_TO_BGRA((uint32_t)c)); return 1; }
API SetPixel(I64 hdc, I64 x, I64 y, I64 c) { return SetPixelV(hdc, x, y, c) ? (I64)((uint32_t)c & 0xFFFFFF) : -1; }
API GetPixel(I64 hdc, I64 x, I64 y) {
  DC *d = dc_of((U64)hdc); Tgt t; if (!d || !dc_tgt(d, &t)) return 0xFFFFFFFF;
  int px = (int)x + dev_dx(d), py = (int)y + dev_dy(d);
  if (px < 0 || py < 0 || px >= t.w || py >= t.h) return 0xFFFFFFFF;
  RL *e = dc_eff(d, &t); if (!rl_contains(e, px, py)) return 0xFFFFFFFF;
  tgt_pull(&t, (WRECT){ px, py, px + 1, py + 1 });
  return BGRA_TO_COLORREF(*px_at(&t, px, py));
}

/* ---------- BitBlt / StretchBlt ---------- */
static uint32_t rop_pix(uint32_t rop, uint32_t s, uint32_t dst, uint32_t pat) {
  if (!gs_rop_supported(rop)) { char m[48]; snprintf(m, sizeof m, "BitBlt rop 0x%08x", (unsigned)rop); gui_failfast("BitBlt", m); }
  return gs_rop_px(rop, s, dst, pat);
}
static int rop_needs_src(uint32_t rop) { return !(rop == PATCOPY || rop == PATINVERT || rop == DSTINVERT || rop == BLACKNESS || rop == WHITENESS); }
static int rop_reads_dst(uint32_t rop) {   /* dst を読まない ROP は SRCCOPY / NOTSRCCOPY / MERGECOPY / PATCOPY / BLACKNESS / WHITENESS */
  return !(rop == SRCCOPY || rop == NOTSRCCOPY || rop == MERGECOPY || rop == PATCOPY || rop == BLACKNESS || rop == WHITENESS);
}
/* 試験用: 1 なら BitBlt/StretchBlt を行カーネルを使わない画素単位の参照実装 (blit_core_ref) へ振り分ける。selftest が高速経路との一致検査に使う */
static int g_ref_blit;
void gdi_set_ref_blit(int on) { g_ref_blit = on; }

/* 参照実装 (画素単位・旧 blit_core そのまま + mono DDB の色写像): 論理座標 -> デバイス座標; sw/sh と dw/dh が異なれば nearest 拡縮 (src = rx*sw/adw), dw/dh 負は反転。
 * src 矩形の負幅/負高は未対応 (fail-fast)。同一バッファ重複は行/列方向を逆順にして memmove 同等。 */
static int blit_core_ref(DC *dd, int dx0, int dy0, int dw, int dh, DC *sd, int sx0, int sy0, int sw, int sh, uint32_t rop) {
  Tgt dt, st = {0};
  if (!dc_tgt(dd, &dt)) return 0;
  int need_src = rop_needs_src(rop);
  if (need_src) { if (!sd || !dc_tgt(sd, &st)) return 0; if (sw < 0 || sh < 0) gui_failfast("StretchBlt", "negative source extent"); }
  int hol = 0; uint32_t pat = 0;
  if (rop == PATCOPY || rop == PATINVERT || rop == MERGECOPY || rop == PATPAINT) pat = brush_bgra(dd->hbrush, &hol);
  dx0 += dev_dx(dd); dy0 += dev_dy(dd);
  if (need_src) { sx0 += dev_dx(sd); sy0 += dev_dy(sd); }
  int adw = dw < 0 ? -dw : dw, adh = dh < 0 ? -dh : dh;
  if (adw == 0 || adh == 0) return 1;
  int dl = dw < 0 ? dx0 + dw : dx0, dtp = dh < 0 ? dy0 + dh : dy0;
  RL *eff = dc_eff(dd, &dt);
  WRECT full = { dl, dtp, dl + adw, dtp + adh };
  if (need_src) tgt_pull(&st, (WRECT){ sx0, sy0, sx0 + sw, sy0 + sh });
  tgt_pull(&dt, full);
  int same = need_src && dt.row0 == st.row0;
  int rev_y = same && dy0 > sy0, rev_x = same && dy0 == sy0 && dx0 > sx0;
  uint32_t bkc = COLORREF_TO_BGRA(dd->bk), tcc = COLORREF_TO_BGRA(dd->tc), srcbk = need_src && sd ? (COLORREF_TO_BGRA(sd->bk) & 0xFFFFFF) : 0;
  if (rop == SRCCOPY && dw > 0 && dh > 0 && sw == dw && sh == dh && !st.mono && !dt.mono) {   /* 等倍コピー高速経路: 行 memmove, alpha もそのまま転送 */
    for (int i = 0; i < eff->n; i++) {
      WRECT c = r_isect(full, eff->r[i]);
      c = r_isect(c, (WRECT){ dl - sx0, dtp - sy0, dl - sx0 + st.w, dtp - sy0 + st.h });  /* 源の範囲内に限定 */
      if (r_empty(c)) continue;
      int n = c.right - c.left;
      for (int yy = 0; yy < c.bottom - c.top; yy++) {
        int y = rev_y ? c.bottom - 1 - yy : c.top + yy;
        memmove(px_at(&dt, c.left, y), px_at(&st, sx0 + (c.left - dl), sy0 + (y - dtp)), (size_t)n * 4);
      }
    }
    dc_dirty(dd, full);
    return 1;
  }
  for (int i = 0; i < eff->n; i++) {
    WRECT c = r_isect(full, eff->r[i]);
    if (r_empty(c)) continue;
    for (int yy = 0; yy < c.bottom - c.top; yy++) {
      int y = rev_y ? c.bottom - 1 - yy : c.top + yy;
      int ry = y - dtp; if (dh < 0) ry = adh - 1 - ry;
      int sy = need_src ? sy0 + (sh == adh ? ry : (int)(((int64_t)ry * sh) / adh)) : 0;
      if (need_src && (sy < 0 || sy >= st.h)) continue;
      for (int xx = 0; xx < c.right - c.left; xx++) {
        int x = rev_x ? c.right - 1 - xx : c.left + xx;
        uint32_t s = 0;
        if (need_src) {
          int rx = x - dl; if (dw < 0) rx = adw - 1 - rx;
          int sx = sx0 + (sw == adw ? rx : (int)(((int64_t)rx * sw) / adw));
          if (sx < 0 || sx >= st.w) continue;
          s = *px_at(&st, sx, sy);
          if (st.mono && !dt.mono) s = (s & 0xFFFFFF) ? bkc : tcc;                          /* mono -> color: 1(白) = 転送先 DC の bk 色, 0(黒) = text 色 */
          else if (!st.mono && dt.mono) s = ((s & 0xFFFFFF) == srcbk) ? 0xFFFFFFFFu : 0xFF000000u;   /* color -> mono: 転送元 DC の bk 色と一致 = 白 */
        }
        if ((rop == PATCOPY || rop == PATINVERT) && hol) continue;
        uint32_t *q = px_at(&dt, x, y);
        *q = rop_pix(rop, s, *q, pat) | 0xFF000000u;
      }
    }
  }
  dc_dirty(dd, full);
  return 1;
}
/* 転送先 x(論理 idx = 0..adw-1) -> 転送元 x の表。xm[idx] = -1 は範囲外。nearest 拡縮は単調なので有効範囲は連続区間 [*vlo,*vhi) */
static void build_xmap(int32_t *xm, int adw, int flip, int sx0, int sw, int src_w, int *vlo, int *vhi) {
  *vlo = adw; *vhi = 0;
  for (int idx = 0; idx < adw; idx++) {
    int rx = flip ? adw - 1 - idx : idx;
    int sx = sx0 + (sw == adw ? rx : (int)(((int64_t)rx * sw) / adw));
    if (sx < 0 || sx >= src_w) { xm[idx] = -1; continue; }
    xm[idx] = sx; if (idx < *vlo) *vlo = idx; *vhi = idx + 1;
  }
}
/* 行カーネル版 (BitBlt / StretchBlt の本体): xmap で除算を行ごと/画素ごとに排除し、ROP は gs_rop_row (wasm SIMD128)、
 * 等倍は連続行、整数 2x 拡大 (sw*2==adw, 反転なし) は gs_dup2 + 直前行の複製で処理する。mono DDB が絡む転送は参照実装へ。 */
static int blit_core(DC *dd, int dx0, int dy0, int dw, int dh, DC *sd, int sx0, int sy0, int sw, int sh, uint32_t rop) {
  if (g_ref_blit) return blit_core_ref(dd, dx0, dy0, dw, dh, sd, sx0, sy0, sw, sh, rop);
  Tgt dt, st = {0};
  if (!dc_tgt(dd, &dt)) return 0;
  int need_src = rop_needs_src(rop);
  if (need_src) { if (!sd || !dc_tgt(sd, &st)) return 0; if (sw < 0 || sh < 0) gui_failfast("StretchBlt", "negative source extent"); }
  if (dt.mono || st.mono) return blit_core_ref(dd, dx0, dy0, dw, dh, sd, sx0, sy0, sw, sh, rop);
  if (!gs_rop_supported(rop)) rop_pix(rop, 0, 0, 0);   /* 未対応 ROP は従来どおり fail-fast (API 名 BitBlt) */
  int hol = 0; uint32_t pat = 0;
  if (rop == PATCOPY || rop == PATINVERT || rop == MERGECOPY || rop == PATPAINT) pat = brush_bgra(dd->hbrush, &hol);
  dx0 += dev_dx(dd); dy0 += dev_dy(dd);
  if (need_src) { sx0 += dev_dx(sd); sy0 += dev_dy(sd); }
  int adw = dw < 0 ? -dw : dw, adh = dh < 0 ? -dh : dh;
  if (adw == 0 || adh == 0) return 1;
  int dl = dw < 0 ? dx0 + dw : dx0, dtp = dh < 0 ? dy0 + dh : dy0;
  RL *eff = dc_eff(dd, &dt);
  WRECT full = { dl, dtp, dl + adw, dtp + adh };
  if (need_src) tgt_pull(&st, (WRECT){ sx0, sy0, sx0 + sw, sy0 + sh });
  tgt_pull(&dt, full);
  int same = need_src && dt.row0 == st.row0;
  int rev_y = same && dy0 > sy0;
  uint32_t *snap = NULL;   /* 同一サーフェス: 1:1 かつ単一クリップ矩形は行順 (rev_y) + 行スナップショットで memmove 同等。それ以外 (拡縮/反転/複数クリップ矩形) は転送元矩形を先にコピーする */
  if (same && (eff->n > 1 || !(dw > 0 && dh > 0 && sw == dw && sh == dh))) {
    WRECT sr = r_isect((WRECT){ sx0, sy0, sx0 + sw, sy0 + sh }, (WRECT){ 0, 0, st.w, st.h });
    if (r_empty(sr)) { dc_dirty(dd, full); return 1; }
    int cw = sr.right - sr.left, ch = sr.bottom - sr.top;
    snap = (uint32_t *)malloc((size_t)cw * ch * 4);
    for (int yy = 0; yy < ch; yy++) memcpy(snap + (size_t)yy * cw, px_at(&st, sr.left, sr.top + yy), (size_t)cw * 4);
    st.row0 = (uint8_t *)snap; st.rowstep = cw * 4; st.w = cw; st.h = ch; sx0 -= sr.left; sy0 -= sr.top; same = 0; rev_y = 0;
  }
  int copy_ident = rop == SRCCOPY && dw > 0 && dh > 0 && sw == dw && sh == dh;   /* alpha もそのまま転送 (旧高速経路と同一) */
  int ident_x = dw > 0 && sw == adw, dup2_x = dw > 0 && sw * 2 == adw && !ident_x;
  int32_t *xm = NULL; uint32_t *tmp = NULL; int vlo = 0, vhi = adw;
  if (need_src) {
    xm = (int32_t *)malloc((size_t)adw * 4); build_xmap(xm, adw, dw < 0, sx0, sw, st.w, &vlo, &vhi);
    tmp = (uint32_t *)malloc((size_t)adw * 4);
  }
  if (!((rop == PATCOPY || rop == PATINVERT) && hol)) {
    for (int i = 0; i < eff->n; i++) {
      WRECT c = r_isect(full, eff->r[i]);
      if (r_empty(c)) continue;
      int xa = c.left, xb = c.right;
      if (need_src) { if (xa < dl + vlo) xa = dl + vlo; if (xb > dl + vhi) xb = dl + vhi; }
      if (xb <= xa) continue;
      int n = xb - xa;
      for (int yy = 0; yy < c.bottom - c.top; yy++) {
        int y = rev_y ? c.bottom - 1 - yy : c.top + yy;
        uint32_t *dst = px_at(&dt, xa, y);
        if (!need_src) { gs_rop_row(rop, dst, dst, (size_t)n, pat); continue; }
        int ry = y - dtp; if (dh < 0) ry = adh - 1 - ry;
        int sy = sy0 + (sh == adh ? ry : (int)(((int64_t)ry * sh) / adh));
        if (sy < 0 || sy >= st.h) continue;
        const uint32_t *srow = px_at(&st, 0, sy), *src;
        if (ident_x) {
          src = srow + xm[xa - dl];
          if (copy_ident) { memmove(dst, src, (size_t)n * 4); continue; }
          if (same) { memcpy(tmp, src, (size_t)n * 4); src = tmp; }
        } else {
          int o = xa - dl;
          if (dup2_x && !same && (o & 1) == 0) { gs_dup2(tmp, srow + xm[o], (size_t)n); }
          else for (int k = 0; k < n; k++) tmp[k] = srow[xm[o + k]];
          src = tmp;
        }
        if (rop == SRCCOPY) gs_opaque_copy(dst, src, (size_t)n); else gs_rop_row(rop, dst, src, (size_t)n, pat);
      }
    }
  }
  free(xm); free(tmp); free(snap);
  dc_dirty(dd, full);
  return 1;
}
API BitBlt(I64 hd, I64 x, I64 y, I64 w, I64 h, I64 hs, I64 sx, I64 sy, I64 rop) {
  DC *dd = dc_of((U64)hd); if (!dd) return 0;
  DC *sd = hs ? dc_of((U64)hs) : NULL;
  if (hs && !sd) return 0;
  return blit_core(dd, (int)x, (int)y, (int)w, (int)h, sd, (int)sx, (int)sy, (int)w, (int)h, (uint32_t)rop);
}
API StretchBlt(I64 hd, I64 x, I64 y, I64 w, I64 h, I64 hs, I64 sx, I64 sy, I64 sw, I64 sh, I64 rop) {
  DC *dd = dc_of((U64)hd); if (!dd) return 0;
  DC *sd = hs ? dc_of((U64)hs) : NULL;
  if (hs && !sd) return 0;
  return blit_core(dd, (int)x, (int)y, (int)w, (int)h, sd, (int)sx, (int)sy, (int)sw, (int)sh, (uint32_t)rop);
}

/* DIB 入力 (BITMAPINFO + bits; 1/4/8/24/32bpp) -> 描画先へ nearest 転送 (SRCCOPY のみ)。<=8bpp は bmiColors (DIB_RGB_COLORS) の色テーブル */
static int dib_to_dc(DC *d, int xd, int yd, int wd, int hd, int xs, int ys, int ws, int hs, const void *bits, const WBMIH *bi, uint32_t rop, uint32_t usage, const char *api) {
  if (rop != SRCCOPY) gui_failfast(api, "rop other than SRCCOPY");
  if (bi->biCompression != BI_RGB && bi->biCompression != BI_BITFIELDS) gui_failfast(api, "compressed DIB");
  int bpp = bi->biBitCount;
  if (!dib_bpp_ok(bpp)) { char m[48]; snprintf(m, sizeof m, "DIB source bpp=%d", bpp); gui_failfast(api, m); }
  if (bpp <= 8 && usage != DIB_RGB_COLORS) gui_failfast(api, "DIB_PAL_COLORS (logical-palette indices) not supported");
  uint32_t pal[256]; if (bpp <= 8) bmi_palette(bi, pal);
  Tgt t; if (!dc_tgt(d, &t)) return 0;
  RL *eff = dc_eff(d, &t);
  int dx = dev_dx(d), dy = dev_dy(d);
  int adw = wd < 0 ? -wd : wd, adh = hd < 0 ? -hd : hd;
  if (adw == 0 || adh == 0) return 1;
  int dl = (wd < 0 ? xd + wd : xd) + dx, dtp = (hd < 0 ? yd + hd : yd) + dy;
  int bw = bi->biWidth, bh = bi->biHeight < 0 ? -bi->biHeight : bi->biHeight;
  if (bw <= 0 || bh == 0) return 1;
  int sy_top = (bi->biHeight < 0) ? ys : (bh - ys - hs);   /* 源矩形 (DIB 座標: StretchDIBits の ySrc は下原点) */
  WRECT full = { dl, dtp, dl + adw, dtp + adh };
  tgt_pull(&t, full);
  size_t bstride = (size_t)dib_stride(bpp, bw);
  int32_t *xm = (int32_t *)malloc((size_t)adw * 4); int vlo, vhi;
  build_xmap(xm, adw, wd < 0, xs, ws, bw, &vlo, &vhi);
  uint32_t *tmp = (uint32_t *)malloc((size_t)adw * 4), *rowbuf = bpp == 32 ? NULL : (uint32_t *)malloc((size_t)bw * 4);
  int cached_sy = -1; const uint32_t *srow = NULL;
  int ident_x = wd > 0 && ws == adw;
  for (int i = 0; i < eff->n; i++) {
    WRECT c = r_isect(full, eff->r[i]);
    if (r_empty(c)) continue;
    int xa = c.left, xb = c.right; if (xa < dl + vlo) xa = dl + vlo; if (xb > dl + vhi) xb = dl + vhi;
    if (xb <= xa) continue;
    int n = xb - xa;
    for (int y = c.top; y < c.bottom; y++) {
      int ry = y - dtp; if (hd < 0) ry = adh - 1 - ry;
      int sy = sy_top + (hs == adh ? ry : (int)(((int64_t)ry * hs) / adh));
      if (sy < 0 || sy >= bh) continue;
      if (sy != cached_sy) {
        int row = bi->biHeight < 0 ? sy : (bh - 1 - sy);
        const uint8_t *rp = (const uint8_t *)bits + (size_t)row * bstride;
        if (bpp == 32) srow = (const uint32_t *)rp;   /* 32bpp は変換不要: 行を直接参照し kernel が alpha を 0xFF 化 */
        else { row_decode(bpp, rp, bw, pal, rowbuf); srow = rowbuf; }
        cached_sy = sy;
      }
      uint32_t *dst = px_at(&t, xa, y); const uint32_t *src;
      if (ident_x) src = srow + xm[xa - dl];
      else { for (int k = 0; k < n; k++) tmp[k] = srow[xm[xa - dl + k]]; src = tmp; }
      gs_opaque_copy(dst, src, (size_t)n);
    }
  }
  free(xm); free(tmp); free(rowbuf);
  dc_dirty(d, full);
  return 1;
}
API StretchDIBits(I64 hdc, I64 xd, I64 yd, I64 wd, I64 hd, I64 xs, I64 ys, I64 ws, I64 hs, I64 bits, I64 bmi, I64 usage, I64 rop) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  return dib_to_dc(d, (int)xd, (int)yd, (int)wd, (int)hd, (int)xs, (int)ys, (int)ws, (int)hs, P_(bits), (const WBMIH *)P_(bmi), (uint32_t)rop, (uint32_t)usage, "StretchDIBits") ? (int)(hd < 0 ? -hd : hd) : 0;
}
API SetDIBitsToDevice(I64 hdc, I64 xd, I64 yd, I64 w, I64 h, I64 xs, I64 ys, I64 start, I64 lines, I64 bits, I64 bmi, I64 usage) {
  (void)start; (void)lines;
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  return dib_to_dc(d, (int)xd, (int)yd, (int)w, (int)h, (int)xs, (int)ys, (int)w, (int)h, P_(bits), (const WBMIH *)P_(bmi), SRCCOPY, (uint32_t)usage, "SetDIBitsToDevice") ? (int)h : 0;
}
/* GetDIBits で bpp<=8 を要求されたときの色テーブル: DIB section は自身のテーブル (同 bpp のとき)、それ以外は決定論的な既定表
 * (1bpp = 黒/白, 4bpp = VGA16, 8bpp = 3-3-2 を 8bit へ拡張) */
static int default_palette(int bpp, uint32_t pal[256]) {
  static const uint32_t vga[16] = { 0x000000, 0x800000, 0x008000, 0x808000, 0x000080, 0x800080, 0x008080, 0xC0C0C0, 0x808080, 0xFF0000, 0x00FF00, 0xFFFF00, 0x0000FF, 0xFF00FF, 0x00FFFF, 0xFFFFFF };
  for (int i = 0; i < 256; i++) pal[i] = 0xFF000000u;
  if (bpp == 1) { pal[0] = 0xFF000000u; pal[1] = 0xFFFFFFFFu; return 2; }
  if (bpp == 4) { for (int i = 0; i < 16; i++) pal[i] = 0xFF000000u | vga[i]; return 16; }
  for (int i = 0; i < 256; i++) { uint32_t r = (uint32_t)((i >> 5) & 7) * 255 / 7, g = (uint32_t)((i >> 2) & 7) * 255 / 7, b = (uint32_t)(i & 3) * 255 / 3; pal[i] = 0xFF000000u | (r << 16) | (g << 8) | b; }
  return 256;
}
API GetDIBits(I64 hdc, I64 hbm, I64 start, I64 lines, I64 bits, I64 bmi, I64 usage) {
  (void)hdc;
  Bmp *b = (Bmp *)h_get((U64)hbm, HT_BMP); if (!b) return 0;
  WBMIH *bi = (WBMIH *)P_(bmi);
  int req = bi->biBitCount;
  if (!bits) {   /* ヘッダ問合せ: biBitCount == 0 なら DIB section は自身の bpp、それ以外は 32 */
    int bpp = req ? req : (b->isdib ? b->bpp : 32);
    if (!dib_bpp_ok(bpp)) gui_failfast("GetDIBits", "requested bpp not in 1/4/8/24/32");
    bi->biSize = 40; bi->biWidth = b->w; bi->biHeight = b->h; bi->biPlanes = 1; bi->biBitCount = (uint16_t)bpp; bi->biCompression = BI_RGB;
    bi->biSizeImage = (uint32_t)(dib_stride(bpp, b->w) * b->h); return b->h;
  }
  if (!dib_bpp_ok(req)) { char m[48]; snprintf(m, sizeof m, "requested bpp=%d (1/4/8/24/32)", req); gui_failfast("GetDIBits", m); }
  if (req <= 8 && usage != DIB_RGB_COLORS) gui_failfast("GetDIBits", "DIB_PAL_COLORS not supported");
  uint32_t pal[256]; int npal = 0;
  if (req <= 8) {
    if (b->pal && b->bpp == req) { memcpy(pal, b->pal, 256 * 4); npal = b->npal; } else npal = default_palette(req, pal);
    uint8_t *q = (uint8_t *)bi + (bi->biSize ? bi->biSize : 40);
    for (int i = 0; i < npal; i++) { uint32_t v = pal[i] & 0xFFFFFF; memcpy(q + (size_t)i * 4, &v, 4); }   /* RGBQUAD: rgbReserved = 0 */
    bi->biClrUsed = (uint32_t)npal; bi->biCompression = BI_RGB;
  }
  bmp_pull(b, (WRECT){ 0, 0, b->w, b->h });
  size_t ostride = (size_t)dib_stride(req, b->w);
  bi->biWidth = b->w; bi->biPlanes = 1; bi->biSizeImage = (uint32_t)(ostride * b->h);
  int n = 0;
  for (int i = 0; i < (int)lines && start + i < b->h; i++) {
    int y = (int)start + i;                      /* DIB 行 (bottom-up 想定 : biHeight>0) */
    int top = bi->biHeight < 0 ? y : b->h - 1 - y;
    int mrow = b->topdown ? top : b->h - 1 - top;
    uint8_t *out = (uint8_t *)P_(bits) + (size_t)i * ostride;
    if (req != 32) memset(out, 0, ostride);
    row_encode(req, out, (const uint32_t *)(b->bits + (size_t)mrow * b->stride), b->w, pal, npal);
    n++;
  }
  return n;
}
API SetDIBits(I64 hdc, I64 hbm, I64 start, I64 lines, I64 bits, I64 bmi, I64 usage) {
  (void)hdc;
  Bmp *b = (Bmp *)h_get((U64)hbm, HT_BMP); if (!b) return 0;
  const WBMIH *bi = (const WBMIH *)P_(bmi);
  int bpp = bi->biBitCount;
  if (!dib_bpp_ok(bpp)) { char m[48]; snprintf(m, sizeof m, "source bpp=%d (1/4/8/24/32)", bpp); gui_failfast("SetDIBits", m); }
  if (bpp <= 8 && usage != DIB_RGB_COLORS) gui_failfast("SetDIBits", "DIB_PAL_COLORS not supported");
  uint32_t pal[256]; if (bpp <= 8) bmi_palette(bi, pal);
  size_t istride = (size_t)dib_stride(bpp, b->w);
  uint32_t *tmp = (uint32_t *)malloc((size_t)b->w * 4);
  int n = 0;
  for (int i = 0; i < (int)lines && start + i < b->h; i++) {
    int y = (int)start + i; int top = bi->biHeight < 0 ? y : b->h - 1 - y; int mrow = b->topdown ? top : b->h - 1 - top;
    if (bpp == 32) memcpy(b->bits + (size_t)mrow * b->stride, (const uint8_t *)P_(bits) + (size_t)i * istride, (size_t)b->w * 4);   /* 旧挙動: alpha も保持 */
    else { row_decode(bpp, (const uint8_t *)P_(bits) + (size_t)i * istride, b->w, pal, tmp); memcpy(b->bits + (size_t)mrow * b->stride, tmp, (size_t)b->w * 4); }
    n++;
  }
  free(tmp);
  if (b->nat) bmp_push(b, (WRECT){ 0, 0, b->w, b->h });
  else if (b->mono) mono_norm(b, (WRECT){ 0, 0, b->w, b->h });
  return n;
}
/* hdc に選択された DIB section (bpp<=8) の色テーブル。Set は shadow を作り直す */
static Bmp *dc_dib_pal(I64 hdc) { DC *d = dc_of((U64)hdc); if (!d || d->kind != 2) return NULL; Bmp *b = (Bmp *)h_get(d->hbmp, HT_BMP); return b && b->pal ? b : NULL; }
API GetDIBColorTable(I64 hdc, I64 start, I64 n, I64 out) {
  Bmp *b = dc_dib_pal(hdc); if (!b || start < 0 || start >= (1 << b->bpp) || !out) return 0;
  int cnt = (int)n; if (start + cnt > (1 << b->bpp)) cnt = (1 << b->bpp) - (int)start;
  for (int i = 0; i < cnt; i++) { uint32_t v = b->pal[start + i] & 0xFFFFFF; memcpy((uint8_t *)P_(out) + (size_t)i * 4, &v, 4); }
  return cnt;
}
API SetDIBColorTable(I64 hdc, I64 start, I64 n, I64 in) {
  Bmp *b = dc_dib_pal(hdc); if (!b || start < 0 || start >= (1 << b->bpp) || !in) return 0;
  int cnt = (int)n; if (start + cnt > (1 << b->bpp)) cnt = (1 << b->bpp) - (int)start;
  for (int i = 0; i < cnt; i++) { uint32_t v; memcpy(&v, (const uint8_t *)P_(in) + (size_t)i * 4, 4); b->pal[start + i] = v | 0xFF000000u; }
  if (start + cnt > b->npal) b->npal = (int)start + cnt;
  bmp_pull(b, (WRECT){ 0, 0, b->w, b->h });
  return cnt;
}
API AlphaBlend(I64 hd, I64 x, I64 y, I64 w, I64 h, I64 hs, I64 sx, I64 sy, I64 sw, I64 sh, I64 blend) {
  DC *dd = dc_of((U64)hd), *sd = dc_of((U64)hs); if (!dd || !sd) return 0;
  if (w <= 0 || h <= 0 || sw <= 0 || sh <= 0) return 0;
  uint32_t bf = (uint32_t)blend; uint32_t sca = (bf >> 16) & 0xFF, afmt = (bf >> 24) & 0xFF;
  Tgt dt, st; if (!dc_tgt(dd, &dt) || !dc_tgt(sd, &st)) return 0;
  RL *eff = dc_eff(dd, &dt);
  int dx = (int)x + dev_dx(dd), dy = (int)y + dev_dy(dd), ssx = (int)sx + dev_dx(sd), ssy = (int)sy + dev_dy(sd);
  int adw = (int)w;
  WRECT full = { dx, dy, dx + adw, dy + (int)h };
  tgt_pull(&st, (WRECT){ ssx, ssy, ssx + (int)sw, ssy + (int)sh });
  tgt_pull(&dt, full);
  int same = dt.row0 == st.row0;
  int32_t *xm = (int32_t *)malloc((size_t)adw * 4); int vlo, vhi;
  build_xmap(xm, adw, 0, ssx, (int)sw, st.w, &vlo, &vhi);
  uint32_t *tmp = (uint32_t *)malloc((size_t)adw * 4);
  int ident_x = (int)sw == adw;
  int rev_y = same && dy > ssy;
  for (int i = 0; i < eff->n; i++) {
    WRECT c = r_isect(full, eff->r[i]);
    if (r_empty(c)) continue;
    int xa = c.left, xb = c.right; if (xa < dx + vlo) xa = dx + vlo; if (xb > dx + vhi) xb = dx + vhi;
    if (xb <= xa) continue;
    int n = xb - xa;
    for (int yy = 0; yy < c.bottom - c.top; yy++) {
      int yv = rev_y ? c.bottom - 1 - yy : c.top + yy;
      int sy2 = ssy + (int)(((int64_t)(yv - dy) * sh) / h); if (sy2 < 0 || sy2 >= st.h) continue;
      const uint32_t *srow = px_at(&st, 0, sy2), *src;
      if (ident_x && !same) src = srow + xm[xa - dx];
      else { for (int k = 0; k < n; k++) tmp[k] = srow[xm[xa - dx + k]]; src = tmp; }
      gs_alpha_row(px_at(&dt, xa, yv), src, (size_t)n, sca, afmt);
    }
  }
  free(xm); free(tmp);
  dc_dirty(dd, full);
  return 1;
}

/* ---------- テキスト (内蔵 8x8 フォント) ---------- */
static int glyph_scale(DC *d) { (void)d; return 1; }
static int draw_text_run(DC *d, int x, int y, const uint16_t *w16, const char *a8, int n, int opaque_rect_only, int *advance) {
  int sc = glyph_scale(d), gw = 8 * sc, gh = 8 * sc;
  *advance = n * gw;
  int ax = x, ay = y;
  if ((d->align & 6) == 6) ax -= (n * gw) / 2; else if ((d->align & 6) == 2) ax -= n * gw;   /* TA_CENTER=6, TA_RIGHT=2 */
  if ((d->align & 24) == 24) ay -= 7 * sc; else if ((d->align & 24) == 8) ay -= gh;           /* TA_BASELINE=24, TA_BOTTOM=8 */
  if (opaque_rect_only) return 1;
  uint32_t fg = COLORREF_TO_BGRA(d->tc), bg = COLORREF_TO_BGRA(d->bk);
  if (d->bkmode == OPAQUE_) fill_dev(d, (WRECT){ ax, ay, ax + n * gw, ay + gh }, bg, 13);
  for (int i = 0; i < n; i++) {
    uint32_t c = w16 ? w16[i] : (uint8_t)a8[i];
    if (c >= 128) c = '?';
    for (int row = 0; row < 8; row++) {
      uint8_t bits = gui_font8x8[c][row];
      for (int col = 0; col < 8; col++) if ((bits >> col) & 1)
        fill_dev(d, (WRECT){ ax + i * gw + col * sc, ay + row * sc, ax + i * gw + (col + 1) * sc, ay + (row + 1) * sc }, fg, 13);
    }
  }
  dc_dirty(d, (WRECT){ ax, ay, ax + n * gw, ay + gh });
  return 1;
}
static int wlen(const uint16_t *s) { int n = 0; while (s[n]) n++; return n; }
static API textout_impl(I64 hdc, I64 x, I64 y, I64 str, I64 n, int wide) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  int adv;
  int px = (int)x + dev_dx(d), py = (int)y + dev_dy(d);
  draw_text_run(d, px, py, wide ? (const uint16_t *)P_(str) : NULL, wide ? NULL : (const char *)P_(str), (int)n, 0, &adv);
  if (d->align & 1) d->cur.x = (int)x + adv;  /* TA_UPDATECP */
  return 1;
}
API TextOutA(I64 hdc, I64 x, I64 y, I64 s, I64 n) { return textout_impl(hdc, x, y, s, n, 0); }
API TextOutW(I64 hdc, I64 x, I64 y, I64 s, I64 n) { return textout_impl(hdc, x, y, s, n, 1); }
static API exttextout_impl(I64 hdc, I64 x, I64 y, I64 opts, I64 rc, I64 str, I64 n, I64 dxs, int wide) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  if (dxs) gui_failfast("ExtTextOut", "lpDx spacing array not supported");
  if ((opts & ETO_OPAQUE) && rc) {
    const WRECT *r = (const WRECT *)P_(rc); int ddx = dev_dx(d), ddy = dev_dy(d);
    fill_dev(d, (WRECT){ r->left + ddx, r->top + ddy, r->right + ddx, r->bottom + ddy }, COLORREF_TO_BGRA(d->bk), 13);
  }
  if (!str || n <= 0) return 1;
  int adv, px = (int)x + dev_dx(d), py = (int)y + dev_dy(d);
  int sb = d->bkmode; if (opts & ETO_OPAQUE) d->bkmode = TRANSPARENT_;
  draw_text_run(d, px, py, wide ? (const uint16_t *)P_(str) : NULL, wide ? NULL : (const char *)P_(str), (int)n, 0, &adv);
  d->bkmode = sb;
  return 1;
}
API ExtTextOutA(I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g, I64 h) { return exttextout_impl(a, b, c, d, e, f, g, h, 0); }
API ExtTextOutW(I64 a, I64 b, I64 c, I64 d, I64 e, I64 f, I64 g, I64 h) { return exttextout_impl(a, b, c, d, e, f, g, h, 1); }
static API extent_impl(I64 hdc, I64 s, I64 n, I64 sz) { (void)hdc; (void)s; WSIZE *z = (WSIZE *)P_(sz); z->cx = (int)n * 8; z->cy = 8; return 1; }
API GetTextExtentPoint32A(I64 a, I64 b, I64 c, I64 d) { return extent_impl(a, b, c, d); }
API GetTextExtentPoint32W(I64 a, I64 b, I64 c, I64 d) { return extent_impl(a, b, c, d); }
API GetTextExtentPointA(I64 a, I64 b, I64 c, I64 d) { return extent_impl(a, b, c, d); }
API GetTextExtentPointW(I64 a, I64 b, I64 c, I64 d) { return extent_impl(a, b, c, d); }
static API metrics_impl(I64 hdc, I64 p, int wide) {
  (void)hdc; WTEXTMETRIC_HEAD h = { 8, 7, 1, 0, 0, 8, 8, 400, 0, 96, 96 };
  memset(P_(p), 0, wide ? 60 : 56); memcpy(P_(p), &h, sizeof h);
  if (wide) { uint16_t *u = (uint16_t *)((uint8_t *)P_(p) + 44); u[0] = 32; u[1] = 126; u[2] = '?'; u[3] = ' '; ((uint8_t *)P_(p))[56] = 1; }
  else { uint8_t *u = (uint8_t *)P_(p) + 44; u[0] = 32; u[1] = 126; u[2] = '?'; u[3] = ' '; ((uint8_t *)P_(p))[51] = 1; }
  return 1;
}
API GetTextMetricsA(I64 hdc, I64 p) { return metrics_impl(hdc, p, 0); }
API GetTextMetricsW(I64 hdc, I64 p) { return metrics_impl(hdc, p, 1); }
static API drawtext_impl(I64 hdc, I64 str, I64 n, I64 rc, I64 fmt, int wide) {
  DC *d = dc_of((U64)hdc); if (!d) return 0;
  WRECT *r = (WRECT *)P_(rc);
  int len = (int)n < 0 ? (wide ? wlen((const uint16_t *)P_(str)) : (int)strlen((const char *)P_(str))) : (int)n;
  /* 行分割 */
  int nl = 1, maxw = 0, curw = 0;
  for (int i = 0; i < len; i++) { uint32_t c = wide ? ((const uint16_t *)P_(str))[i] : ((const uint8_t *)P_(str))[i]; if (c == '\n' && !(fmt & DT_SINGLELINE)) { nl++; if (curw > maxw) maxw = curw; curw = 0; } else if (c != '\r') curw++; }
  if (curw > maxw) maxw = curw;
  int tw = maxw * 8, th = nl * 8;
  if (fmt & DT_CALCRECT) { r->right = r->left + tw; r->bottom = r->top + th; return th; }
  int x0 = r->left, y0 = r->top;
  if (fmt & DT_CENTER) x0 = r->left + ((r->right - r->left) - tw) / 2; else if (fmt & DT_RIGHT) x0 = r->right - tw;
  if (fmt & DT_VCENTER) y0 = r->top + ((r->bottom - r->top) - th) / 2; else if (fmt & DT_BOTTOM) y0 = r->bottom - th;
  int line = 0, start = 0, adv;
  for (int i = 0; i <= len; i++) {
    uint32_t c = i < len ? (wide ? ((const uint16_t *)P_(str))[i] : ((const uint8_t *)P_(str))[i]) : '\n';
    if (c == '\n' && (i == len || !(fmt & DT_SINGLELINE))) {
      int cnt = i - start;
      draw_text_run(d, x0 + dev_dx(d), y0 + line * 8 + dev_dy(d), wide ? (const uint16_t *)P_(str) + start : NULL, wide ? NULL : (const char *)P_(str) + start, cnt, 0, &adv);
      line++; start = i + 1;
    }
  }
  return th;
}
API DrawTextA(I64 hdc, I64 s, I64 n, I64 rc, I64 fmt) { return drawtext_impl(hdc, s, n, rc, fmt, 0); }
API DrawTextW(I64 hdc, I64 s, I64 n, I64 rc, I64 fmt) { return drawtext_impl(hdc, s, n, rc, fmt, 1); }

/* ======================================================================================
 * P1 拡張 (CAB-159): 3D 枠/フレームコントロール/フォーカス矩形・リージョン取得・画面 DC・DDB 生成・アイコン描画
 * ====================================================================================== */
extern API GetSysColor(I64);
extern GuiResProvider gui_get_resource_provider(void);
#define g_gdi_res (gui_get_resource_provider())
static void px_cref(U64 hdc, int x, int y, uint32_t cref) { gdi_fill_rect_dc(hdc, (WRECT){ x, y, x + 1, y + 1 }, cref); }
static void edge_fill(U64 hdc, int l, int t, int r, int b, int sysidx) { if (sysidx >= 0 && r > l && b > t) gdi_fill_rect_dc(hdc, (WRECT){ l, t, r, b }, (uint32_t)GetSysColor(sysidx)); }

/* DrawEdge: 外枠層 (BDR_*OUTER) → 内枠層 (BDR_*INNER) の各 1px を左上(LT)/右下(RB)色で描く。色は Windows の標準/SOFT/FLAT/MONO 規則。
 * COLOR_* : BTNFACE=15 BTNSHADOW=16 BTNHIGHLIGHT=20 3DDKSHADOW=21 3DLIGHT=22 WINDOWFRAME=6。SOFT は 3DDKSHADOW→BTNSHADOW / 3DLIGHT→BTNHIGHLIGHT の近似。 */
enum { BF_LEFT_ = 1, BF_TOP_ = 2, BF_RIGHT_ = 4, BF_BOTTOM_ = 8, BF_DIAGONAL_ = 0x10, BF_MIDDLE_ = 0x800, BF_SOFT_ = 0x1000, BF_ADJUST_ = 0x2000, BF_FLAT_ = 0x4000, BF_MONO_ = 0x8000 };
static int edge_color(int layer /*0 outer,1 inner*/, int lt, int kind /*1 raised, 2 sunken*/, int flags) {
  static const int oLT[3] = { -1, 22, 16 }, oRB[3] = { -1, 21, 20 }, iLT[3] = { -1, 20, 21 }, iRB[3] = { -1, 16, 22 };
  if (flags & BF_MONO_) return layer == 0 ? 6 : -1;
  if (flags & BF_FLAT_) return layer == 0 ? 16 : 15;
  int c = layer == 0 ? (lt ? oLT[kind] : oRB[kind]) : (lt ? iLT[kind] : iRB[kind]);
  if (flags & BF_SOFT_) { if (c == 21) c = 16; else if (c == 22) c = 20; }
  return c;
}
API DrawEdge(I64 hdc, I64 qrc, I64 edge, I64 flags) {
  if (!dc_of((U64)hdc) || !qrc) return 0;
  WRECT *q = (WRECT *)P_(qrc); WRECT r = *q; int f = (int)flags, e = (int)edge;
  if (f & BF_DIAGONAL_) gui_failfast("DrawEdge", "BF_DIAGONAL");
  int sl = (f & BF_LEFT_) != 0, st = (f & BF_TOP_) != 0, sr = (f & BF_RIGHT_) != 0, sb = (f & BF_BOTTOM_) != 0;
  for (int layer = 0; layer < 2; layer++) {
    int kind = (e >> (layer * 2)) & 3;   /* bit0/2 = RAISED, bit1/3 = SUNKEN */
    if (!kind) continue;
    int cl = edge_color(layer, 1, kind, f), cr = edge_color(layer, 0, kind, f);
    /* LT: 左列 (上辺が有効なら 1 行下から) と上行 (右辺が有効なら右端手前まで) / RB: 右列 (下辺が有効なら下端手前まで) と下行 (全幅) */
    if (sl) edge_fill((U64)hdc, r.left, st ? r.top + 1 : r.top, r.left + 1, r.bottom, cl);
    if (st) edge_fill((U64)hdc, r.left, r.top, sr ? r.right - 1 : r.right, r.top + 1, cl);
    if (sr) edge_fill((U64)hdc, r.right - 1, r.top, r.right, sb ? r.bottom - 1 : r.bottom, cr);
    if (sb) edge_fill((U64)hdc, r.left, r.bottom - 1, r.right, r.bottom, cr);
    if (sl) { r.left++; }
    if (st) { r.top++; }
    if (sr) { r.right--; }
    if (sb) { r.bottom--; }
  }
  if (f & BF_MIDDLE_) edge_fill((U64)hdc, r.left, r.top, r.right, r.bottom, (f & BF_MONO_) ? 5 : 15);
  if (f & BF_ADJUST_) *q = r;
  return 1;
}

/* DrawFrameControl: ボタン (押し/チェック/ラジオ)・スクロール矢印・キャプションボタン・メニュー記号。外観は簡略 (形状は Windows 標準の近似) */
enum { DFC_CAPTION_ = 1, DFC_MENU_ = 2, DFC_SCROLL_ = 3, DFC_BUTTON_ = 4, DFC_POPUPMENU_ = 5 };
enum { DFCS_PUSHED_ = 0x200, DFCS_CHECKED_ = 0x400, DFCS_INACTIVE_ = 0x100, DFCS_FLAT_ = 0x4000, DFCS_MONO_ = 0x8000 };
static void tri(U64 hdc, int cx, int cy, int dir, int n, uint32_t col) {   /* 向き 0 上 1 下 2 左 3 右 の三角 (高さ n) */
  for (int i = 0; i < n; i++) {
    int half = i;   /* 先端から i 段目: 幅 2*i+1 */
    switch (dir) {
      case 0: gdi_fill_rect_dc(hdc, (WRECT){ cx - half, cy - n / 2 + i, cx + half + 1, cy - n / 2 + i + 1 }, col); break;
      case 1: gdi_fill_rect_dc(hdc, (WRECT){ cx - half, cy + n / 2 - i, cx + half + 1, cy + n / 2 - i + 1 }, col); break;
      case 2: gdi_fill_rect_dc(hdc, (WRECT){ cx - n / 2 + i, cy - half, cx - n / 2 + i + 1, cy + half + 1 }, col); break;
      default: gdi_fill_rect_dc(hdc, (WRECT){ cx + n / 2 - i, cy - half, cx + n / 2 - i + 1, cy + half + 1 }, col); break;
    }
  }
}
API DrawFrameControl(I64 hdc, I64 prc, I64 type, I64 state) {
  if (!dc_of((U64)hdc) || !prc) return 0;
  WRECT r = *(WRECT *)P_(prc); int st = (int)state, sub = st & 0xFF;
  uint32_t ink = (uint32_t)GetSysColor((st & DFCS_INACTIVE_) ? 17 : 18);
  int cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
  int flat = (st & DFCS_FLAT_) ? BF_FLAT_ : 0, mono = (st & DFCS_MONO_) ? BF_MONO_ : 0;
  int pushed = (st & DFCS_PUSHED_) != 0;
  switch ((int)type) {
    case DFC_BUTTON_: {
      if (sub == 0x10 /* DFCS_BUTTONPUSH */) {
        WRECT q = r; DrawEdge(hdc, H_(&q), pushed ? 10 : 5, 15 | BF_MIDDLE_ | flat | mono); return 1;
      }
      int radio = (sub == 4 || sub == 1 || sub == 2), sz = 13;
      WRECT b = { cx - sz / 2, cy - sz / 2, cx - sz / 2 + sz, cy - sz / 2 + sz };
      if (!radio) {   /* チェックボックス / 3STATE */
        WRECT q = b; DrawEdge(hdc, H_(&q), 10, 15 | BF_ADJUST_ | flat | mono);
        edge_fill((U64)hdc, q.left, q.top, q.right, q.bottom, (st & (DFCS_INACTIVE_ | DFCS_PUSHED_)) ? 15 : 5);
        if (st & DFCS_CHECKED_) {   /* ✓ */
          static const int8_t ck[][2] = { { 0, 2 }, { 1, 3 }, { 2, 4 }, { 3, 3 }, { 4, 2 }, { 5, 1 }, { 6, 0 } };
          for (int i = 0; i < 7; i++) { px_cref((U64)hdc, b.left + 2 + ck[i][0], b.top + 4 + ck[i][1], ink); px_cref((U64)hdc, b.left + 2 + ck[i][0], b.top + 5 + ck[i][1], ink); px_cref((U64)hdc, b.left + 2 + ck[i][0], b.top + 6 + ck[i][1], ink); }
        }
      } else {   /* ラジオ: 外周 = 影(左上)/ハイライト(右下)、内部 = 白、チェック時は中心 4x4 */
        int R = sz / 2;
        for (int y = -R; y <= R; y++) for (int x = -R; x <= R; x++) {
          int d2 = x * x + y * y; if (d2 > R * R + R) continue;
          uint32_t col = d2 > (R - 1) * (R - 1) + (R - 1) ? (uint32_t)GetSysColor((x + y) <= 0 ? 16 : 20) : (uint32_t)GetSysColor((st & (DFCS_INACTIVE_ | DFCS_PUSHED_)) ? 15 : 5);
          px_cref((U64)hdc, cx + x, cy + y, col);
        }
        if (st & DFCS_CHECKED_) gdi_fill_rect_dc((U64)hdc, (WRECT){ cx - 2, cy - 2, cx + 2, cy + 2 }, ink);
      }
      return 1;
    }
    case DFC_SCROLL_: {
      WRECT q = r; DrawEdge(hdc, H_(&q), pushed ? 10 : 5, 15 | BF_MIDDLE_ | flat | mono);
      int dir = sub & 3; if (sub == 5 /* COMBOBOX */) dir = 1; if (sub == 8 /* SIZEGRIP */) { for (int i = 1; i <= 3; i++) for (int k = 0; k < i; k++) px_cref((U64)hdc, r.right - 2 - k * 4, r.bottom - 2 - (3 - i) * 4, (uint32_t)GetSysColor(16)); return 1; }
      tri(hdc, cx + (pushed ? 1 : 0), cy + (pushed ? 1 : 0), dir, 4, ink); return 1;
    }
    case DFC_CAPTION_: {
      WRECT q = r; DrawEdge(hdc, H_(&q), pushed ? 10 : 5, 15 | BF_MIDDLE_ | flat | mono);
      int o = pushed ? 1 : 0;
      switch (sub) {
        case 0: for (int i = -3; i <= 3; i++) { px_cref((U64)hdc, cx + i + o, cy + i + o, ink); px_cref((U64)hdc, cx + i + o + 1, cy + i + o, ink); px_cref((U64)hdc, cx + i + o, cy - i + o, ink); px_cref((U64)hdc, cx + i + o + 1, cy - i + o, ink); } break;   /* 閉じる X */
        case 1: gdi_fill_rect_dc((U64)hdc, (WRECT){ cx - 4 + o, cy + 2 + o, cx + 4 + o, cy + 4 + o }, ink); break;                                         /* 最小化 */
        case 2: gdi_fill_rect_dc((U64)hdc, (WRECT){ cx - 4 + o, cy - 4 + o, cx + 5 + o, cy - 2 + o }, ink); edge_fill((U64)hdc, cx - 4 + o, cy - 2 + o, cx - 3 + o, cy + 4 + o, -1); break;  /* 最大化 */
        default: gdi_fill_rect_dc((U64)hdc, (WRECT){ cx - 2 + o, cy - 4 + o, cx + 4 + o, cy - 2 + o }, ink); gdi_fill_rect_dc((U64)hdc, (WRECT){ cx - 4 + o, cy - 1 + o, cx + 2 + o, cy + 1 + o }, ink); break;   /* 復元/ヘルプ */
      }
      return 1;
    }
    case DFC_MENU_: case DFC_POPUPMENU_: {
      uint32_t col = (uint32_t)GetSysColor(18);
      if (sub == 0 || sub == 4) tri(hdc, cx - 1, cy, 3, 4, col);                    /* MENUARROW / ARROWRIGHT */
      else if (sub == 1) { for (int i = 0; i < 3; i++) { px_cref((U64)hdc, cx - 3 + i, cy + i, col); px_cref((U64)hdc, cx - 3 + i, cy + i + 1, col); } for (int i = 0; i < 4; i++) { px_cref((U64)hdc, cx + i, cy + 2 - i, col); px_cref((U64)hdc, cx + i, cy + 3 - i, col); } }   /* CHECK */
      else gdi_fill_rect_dc((U64)hdc, (WRECT){ cx - 2, cy - 2, cx + 2, cy + 2 }, col);                                                                                   /* BULLET */
      return 1;
    }
  }
  gui_set_last_error(87); return 0;
}

/* DrawFocusRect: 外周 1px の点線 (座標 (x+y) が偶数の画素) を反転 (2 回で元に戻る = PATINVERT の性質) */
API DrawFocusRect(I64 hdc, I64 prc) {
  DC *d = dc_of((U64)hdc); if (!d || !prc) return 0;
  WRECT r = *(const WRECT *)P_(prc); int dx = dev_dx(d), dy = dev_dy(d);
  for (int x = r.left; x < r.right; x++) for (int k = 0; k < 2; k++) {
    int y = k ? r.bottom - 1 : r.top; if (k && r.bottom - 1 == r.top) continue;
    if (((x + y) & 1) == 0) fill_dev(d, (WRECT){ x + dx, y + dy, x + dx + 1, y + dy + 1 }, 0xFFFFFFFFu, 7);
  }
  for (int y = r.top + 1; y < r.bottom - 1; y++) for (int k = 0; k < 2; k++) {
    int x = k ? r.right - 1 : r.left; if (k && r.right - 1 == r.left) continue;
    if (((x + y) & 1) == 0) fill_dev(d, (WRECT){ x + dx, y + dy, x + dx + 1, y + dy + 1 }, 0xFFFFFFFFu, 7);
  }
  return 1;
}

/* ---------- リージョン取得 ---------- */
static void rgn_set_shifted(Rgn *g, const RL *src, int dx, int dy) {
  rl_clear(&g->rl);
  for (int i = 0; i < src->n; i++) rl_add(&g->rl, (WRECT){ src->r[i].left + dx, src->r[i].top + dy, src->r[i].right + dx, src->r[i].bottom + dy });
}
API GetClipRgn(I64 hdc, I64 hrgn) {   /* 1 = アプリクリップあり (論理座標で hrgn へコピー) / 0 = なし / -1 = エラー */
  DC *d = dc_of((U64)hdc); Rgn *g = (Rgn *)h_get((U64)hrgn, HT_RGN); if (!d || !g) return -1;
  if (!d->has_user) return 0;
  rgn_set_shifted(g, &d->user, -dev_dx(d), -dev_dy(d)); return 1;
}
API GetRandomRgn(I64 hdc, I64 hrgn, I64 which) {   /* CLIPRGN=1 (デバイス = DC 原点基準), SYSRGN=4 (画面座標の可視領域), その他は領域なし (0) */
  DC *d = dc_of((U64)hdc); Rgn *g = (Rgn *)h_get((U64)hrgn, HT_RGN); if (!d || !g) return -1;
  if (which == 1) { if (!d->has_user) return 0; rgn_set_shifted(g, &d->user, d->kind == 1 ? -d->ox : 0, d->kind == 1 ? -d->oy : 0); return 1; }
  if (which == 4) {
    Tgt t; if (!dc_tgt(d, &t)) return -1;
    RL v = {0}; rl_add(&v, (WRECT){ 0, 0, t.w, t.h }); if (d->has_base) rl_intersect(&v, &d->base);
    int sx = 0, sy = 0; if (d->kind == 1) { GuiShared *sh = gui_sh(); sx = sh->surf[d->surf].x; sy = sh->surf[d->surf].y; }
    rgn_set_shifted(g, &v, sx, sy); rl_free(&v); return 1;
  }
  return 0;
}
static int rect_cmp(const void *a, const void *b) {
  const WRECT *x = (const WRECT *)a, *y = (const WRECT *)b;
  return x->top != y->top ? x->top - y->top : x->left - y->left;
}
API GetRegionData(I64 hrgn, I64 count, I64 pdata) {   /* RGNDATA = RGNDATAHEADER(32B: dwSize,iType=1,nCount,nRgnSize,rcBound) + RECT[nCount] */
  Rgn *g = (Rgn *)h_get((U64)hrgn, HT_RGN); if (!g) return 0;
  uint32_t need = 32 + 16 * (uint32_t)g->rl.n;
  if (!pdata) return need;
  if ((uint32_t)count < need) return 0;
  uint32_t *h = (uint32_t *)P_(pdata); WRECT bb; rl_bbox(&g->rl, &bb);
  h[0] = 32; h[1] = 1; h[2] = (uint32_t)g->rl.n; h[3] = 16 * (uint32_t)g->rl.n;
  if (!g->rl.n) memset(&bb, 0, sizeof bb);
  memcpy(h + 4, &bb, 16);
  WRECT *o = (WRECT *)(h + 8); memcpy(o, g->rl.r, 16 * (size_t)g->rl.n); qsort(o, (size_t)g->rl.n, sizeof(WRECT), rect_cmp);
  return (I64)count;
}

/* CreateDCW: "DISPLAY" (または driver NULL + デバイス名) の画面 DC = 画面寸法を返す互換 DC (描画は破棄される 1x1 ビットマップ宛; GetDeviceCaps/CreateCompatibleBitmap 用途)。それ以外のドライバ (印刷等) は fail-fast */
API CreateDCW(I64 drv, I64 dev, I64 out, I64 pdm) {
  (void)out; (void)pdm; gui_sh();
  const uint16_t *s = drv ? (const uint16_t *)P_(drv) : (const uint16_t *)P_(dev);
  static const char want[] = "DISPLAY"; int ok = (s == NULL);
  if (s) { ok = 1; for (int i = 0; want[i] && ok; i++) { uint16_t c = s[i]; if (c >= 'a' && c <= 'z') c -= 32; if (c != (uint16_t)want[i]) ok = 0; } }
  if (!ok && drv == 0 && dev) { const char pre[] = "\\\\.\\DISPLAY"; ok = 1; for (int i = 0; pre[i] && ok; i++) if (s[i] != (uint16_t)pre[i]) ok = 0; }
  if (!ok) gui_failfast("CreateDCW", "non-DISPLAY device (printer DC)");
  return CreateCompatibleDC(0);
}

/* ---------- DDB 生成 / 資源ビットマップ ---------- */
static int dib_bits_offset(const WBMIH *bi) {   /* ヘッダ + (BITFIELDS マスク) + パレット */
  int colors = bi->biBitCount <= 8 ? (bi->biClrUsed ? (int)bi->biClrUsed : 1 << bi->biBitCount) : 0;
  return (int)bi->biSize + (bi->biCompression == BI_BITFIELDS && bi->biSize == 40 ? 12 : 0) + colors * 4;
}
static void dib_fill_bmp(Bmp *b, const WBMIH *bi, const uint8_t *bits, const char *api) {
  int bpp = bi->biBitCount;
  if (!dib_bpp_ok(bpp)) { char m[48]; snprintf(m, sizeof m, "DIB source bpp=%d (1/4/8/24/32)", bpp); gui_failfast(api, m); }
  if (bi->biCompression != BI_RGB && bi->biCompression != BI_BITFIELDS) gui_failfast(api, "compressed DIB");
  uint32_t pal[256]; if (bpp <= 8) bmi_palette(bi, pal);
  int sh = bi->biHeight < 0 ? -bi->biHeight : bi->biHeight, w = b->w < bi->biWidth ? b->w : bi->biWidth;
  size_t stride = (size_t)dib_stride(bpp, bi->biWidth);
  uint32_t *tmp = (uint32_t *)malloc((size_t)(bi->biWidth > 0 ? bi->biWidth : 1) * 4);
  for (int y = 0; y < b->h && y < sh; y++) {
    int row = bi->biHeight < 0 ? y : (sh - 1 - y);
    row_decode(bpp, bits + (size_t)row * stride, bi->biWidth, pal, tmp);
    memcpy(b->bits + (size_t)y * b->stride, tmp, (size_t)w * 4);
  }
  free(tmp);
}
#define CBM_INIT_ 4
API CreateDIBitmap(I64 hdc, I64 pbih, I64 init, I64 pbits, I64 pbmi, I64 usage) {
  (void)hdc; (void)usage; gui_sh();
  const WBMIH *bih = (const WBMIH *)P_(pbih); if (!bih || bih->biSize < 40 || bih->biWidth <= 0 || bih->biHeight == 0) { gui_set_last_error(87); return 0; }
  Bmp *b = bmp_new(bih->biWidth, bih->biHeight, 1);
  if ((init & CBM_INIT_) && pbits && pbmi) {
    const WBMIH *bi = (const WBMIH *)P_(pbmi);
    if (bi->biWidth != b->w) { bmp_free(b); gui_failfast("CreateDIBitmap", "lpbmi width != lpbmih width"); }
    Bmp tmp = *b; tmp.h = bi->biHeight < 0 ? -bi->biHeight : bi->biHeight; if (tmp.h > b->h) tmp.h = b->h;
    dib_fill_bmp(&tmp, bi, (const uint8_t *)P_(pbits), "CreateDIBitmap");
  }
  return (I64)h_alloc(HT_BMP, b);
}
API LoadBitmapW(I64 hinst, I64 name) {
  gui_sh();
  if ((U64)name >= 0x10000) gui_failfast("LoadBitmapW", "named (string) bitmap resource");
  if (!hinst && name >= 32700 && name <= 32767) {   /* OBM_*: 実ビットマップは未同梱。13x13 の白地プレースホルダ */
    Bmp *b = bmp_new(13, 13, 1); memset(b->bits, 0xFF, (size_t)b->stride * b->h); return (I64)h_alloc(HT_BMP, b);
  }
  const void *data = NULL; uint32_t sz = 0;
  if (!g_gdi_res || !g_gdi_res((U64)hinst, 2 /* RT_BITMAP */, (uint32_t)name, &data, &sz)) { gui_set_last_error(1813); return 0; }   /* ERROR_RESOURCE_TYPE_NOT_FOUND */
  const WBMIH *bi = (const WBMIH *)data; Bmp *b = bmp_new(bi->biWidth, bi->biHeight, 1);
  dib_fill_bmp(b, bi, (const uint8_t *)data + dib_bits_offset(bi), "LoadBitmapW");
  if (bi->biBitCount == 1) { b->mono = 1; b->bpp = 1; mono_norm(b, (WRECT){ 0, 0, b->w, b->h }); }   /* 1bpp 資源 = mono DDB */
  return (I64)h_alloc(HT_BMP, b);
}

/* ---------- アイコン / カーソル (擬似ハンドルの標準アイコン・カーソルのみ; 画像は 32x32 のプレースホルダ生成) ---------- */
static int icon_kind(I64 h) { return (h >= 0x7E000000 && h < 0x7E010000) ? 1 : (h >= 0x7F000000 && h < 0x7F010000) ? 2 : 0; }
static void icon_pixels(I64 h, uint32_t px[32 * 32], int *hx, int *hy) {   /* BGRA, 透明 = 0 */
  memset(px, 0, 32 * 32 * 4); *hx = *hy = 0;
  if (icon_kind(h) == 1) {
    for (int y = 0; y < 32; y++) for (int x = 0; x < 32; x++) px[y * 32 + x] = (x == 0 || y == 0 || x == 31 || y == 31) ? 0xFF404040u : 0xFFC0C0C0u;
    return;
  }
  if (h - 0x7F000000 == 32512) {   /* IDC_ARROW : 黒縁白塗りの矢印 */
    for (int y = 0; y < 19; y++) for (int x = 0; x <= (y * 12) / 19 + 1 && x < 13; x++) px[y * 32 + x] = (x == 0 || x >= (y * 12) / 19 || y == 18) ? 0xFF000000u : 0xFFFFFFFFu;
    return;
  }
  *hx = *hy = 15;   /* それ以外のカーソル = 十字 */
  for (int i = 4; i < 28; i++) { px[15 * 32 + i] = 0xFF000000u; px[i * 32 + 15] = 0xFF000000u; }
}
API GetIconInfo(I64 hicon, I64 pii) {   /* ICONINFO (Win64 32B): fIcon@0 xHotspot@4 yHotspot@8 hbmMask@16 hbmColor@24。2 枚のビットマップは呼出側が DeleteObject する */
  if (!icon_kind(hicon) || !pii) { gui_set_last_error(1402); return 0; }
  uint32_t px[32 * 32]; int hx, hy; icon_pixels(hicon, px, &hx, &hy);
  Bmp *c = bmp_new(32, 32, 1), *m = bmp_new(32, 32, 1);
  for (int i = 0; i < 32 * 32; i++) { ((uint32_t *)c->bits)[i] = px[i]; ((uint32_t *)m->bits)[i] = (px[i] >> 24) ? 0xFF000000u : 0xFFFFFFFFu; }   /* AND マスク: 不透明 = 黒 */
  uint8_t *o = (uint8_t *)P_(pii); memset(o, 0, 32);
  *(uint32_t *)o = icon_kind(hicon) == 1; *(uint32_t *)(o + 4) = (uint32_t)hx; *(uint32_t *)(o + 8) = (uint32_t)hy;
  *(U64 *)(o + 16) = h_alloc(HT_BMP, m); *(U64 *)(o + 24) = h_alloc(HT_BMP, c);
  return 1;
}
API DrawIconEx(I64 hdc, I64 x, I64 y, I64 hicon, I64 cx, I64 cy, I64 step, I64 hbr, I64 flags) {
  (void)step; (void)hbr; DC *d = dc_of((U64)hdc);
  if (!d || !icon_kind(hicon)) { gui_set_last_error(icon_kind(hicon) ? 6 : 1402); return 0; }
  uint32_t px[32 * 32]; int hx, hy; icon_pixels(hicon, px, &hx, &hy);
  int w = (flags & 8) || cx <= 0 ? 32 : (int)cx, h = (flags & 8) || cy <= 0 ? 32 : (int)cy, f = (int)flags & 3; if (!f) f = 3;
  int dx = dev_dx(d), dy = dev_dy(d);
  for (int j = 0; j < h; j++) for (int i = 0; i < w; i++) {
    uint32_t p = px[(j * 32 / h) * 32 + (i * 32 / w)]; if (!(p >> 24)) continue;
    uint32_t col = (f == 1) ? 0xFF000000u : p;   /* DI_MASK だけなら黒 (AND マスクの不透明部) */
    fill_dev(d, (WRECT){ (int)x + i + dx, (int)y + j + dy, (int)x + i + dx + 1, (int)y + j + dy + 1 }, col, 13);
  }
  return 1;
}
API DrawIcon(I64 hdc, I64 x, I64 y, I64 hicon) { return DrawIconEx(hdc, x, y, hicon, 0, 0, 0, 0, 3 | 4 | 8); }
int gdi_stock_count(void) {   /* GetStockObject 群の重複を除いた数 + 既定ビットマップ */
  int stock = 1;
  for (int i = 0; i < 20; i++) { if (!g_stock[i]) continue; int dup = 0; for (int j = 0; j < i; j++) if (g_stock[j] == g_stock[i]) dup = 1; if (!dup) stock++; }
  return stock;
}
int gdi_object_count(void) {   /* ストックを除く生存 GDI オブジェクト数 */
  static const HType ts[] = { HT_DC, HT_BMP, HT_BRUSH, HT_PEN, HT_FONT, HT_RGN, HT_PAL };
  int n = 0; for (unsigned i = 0; i < sizeof ts / sizeof ts[0]; i++) n += h_count(ts[i]);
  int stock = gdi_stock_count();
  return n > stock ? n - stock : 0;
}
