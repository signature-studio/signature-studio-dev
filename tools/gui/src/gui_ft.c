/* gui_ft.c — FreeType 2.7 テキストエンジン (GUI-9 #186)。gui_gdi.c の GuiTextEngine 実装。
 * ヒンティングは FT 既定 (FT_LOAD_DEFAULT; 同一バージョンの native FreeType と bit 一致する: tools/shared/oss/freetype)。
 * advance は整数 px (hinted advance を四捨五入)。カーニング・ClearType・合成 bold/italic は未実装 (REPORT §11)。 */
#include <ctype.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_TRUETYPE_TABLES_H
#include "gui_ft.h"

#define MAXFACE 16
#define MAXALIAS 64
typedef struct { char name[64]; const uint8_t *data; size_t size; GuiFtLoader load; void *user; int tried; } FaceReg;
typedef struct { char alias[64]; int target; } AliasReg;
static FaceReg g_face[MAXFACE]; static int g_nface;
static AliasReg g_alias[MAXALIAS]; static int g_nalias;
static FT_Library g_lib;
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;

typedef struct { FT_Face face; int ppem; GuiTextMetrics m; } FtFont;

static void lower(char *d, const char *s, size_t n) { size_t i = 0; for (; s[i] && i + 1 < n; i++) d[i] = (char)tolower((unsigned char)s[i]); d[i] = 0; }
static int find_face(const char *name) { char k[64]; lower(k, name, sizeof k); for (int i = 0; i < g_nface; i++) { char f[64]; lower(f, g_face[i].name, sizeof f); if (!strcmp(f, k)) return i; } return -1; }

int gui_ft_register_face(const char *name, const uint8_t *data, size_t size) {
  if (g_nface >= MAXFACE || !data || !size || find_face(name) >= 0) return -1;
  FaceReg *f = &g_face[g_nface]; memset(f, 0, sizeof *f); snprintf(f->name, sizeof f->name, "%s", name); f->data = data; f->size = size; f->tried = 1;
  return g_nface++;
}
int gui_ft_register_lazy(const char *name, GuiFtLoader load, void *user) {
  if (g_nface >= MAXFACE || !load || find_face(name) >= 0) return -1;
  FaceReg *f = &g_face[g_nface]; memset(f, 0, sizeof *f); snprintf(f->name, sizeof f->name, "%s", name); f->load = load; f->user = user;
  return g_nface++;
}
int gui_ft_alias(const char *alias, const char *target) {
  int t = find_face(target); if (t < 0 || g_nalias >= MAXALIAS) return -1;
  snprintf(g_alias[g_nalias].alias, sizeof g_alias[0].alias, "%s", alias); g_alias[g_nalias].target = t; g_nalias++; return 0;
}
void gui_ft_reset(void) { g_nface = 0; g_nalias = 0; }

static int ft_resolve(const uint16_t *w) {
  if (g_nface == 0) return -1;
  char a[64]; size_t n = 0;
  if (w) for (; w[n] && n + 1 < sizeof a; n++) a[n] = w[n] < 128 ? (char)w[n] : '?';
  a[n] = 0;
  int i = find_face(a); if (i >= 0) return i;
  char k[64]; lower(k, a, sizeof k);
  for (int j = 0; j < g_nalias; j++) { char x[64]; lower(x, g_alias[j].alias, sizeof x); if (!strcmp(x, k)) return g_alias[j].target; }
  return 0;   /* 未解決名 (Windows の font substitution 相当) は最初に登録した face */
}
static int ft_nfaces(void) { return g_nface; }
static const char *ft_face_name(int i) { return i >= 0 && i < g_nface ? g_face[i].name : NULL; }

/* LOGFONT 規約の height -> ppem。<0: em px / >0: セル高 (ascent+descent) が h 以下になる最大 ppem / 0: 12 */
static int pick_ppem(FT_Face f, int height) {
  if (height < 0) return -height;
  if (height == 0) return 12;
  for (int p = height; p >= 1; p--) {
    FT_Set_Pixel_Sizes(f, 0, (FT_UInt)p);
    if ((f->size->metrics.ascender >> 6) - (f->size->metrics.descender >> 6) <= height) return p;
  }
  return 1;
}

static void *ft_open(const uint16_t *face16, int height, int weight, int italic) {
  (void)weight; (void)italic;
  pthread_mutex_lock(&g_mu);
  FtFont *r = NULL;
  int idx = ft_resolve(face16);
  if (idx >= 0) {
    FaceReg *fr = &g_face[idx];
    if (!fr->data && fr->load && !fr->tried) { fr->tried = 1; if (!fr->load(fr->name, &fr->data, &fr->size, fr->user)) fr->data = NULL; }
    if (fr->data && (g_lib || !FT_Init_FreeType(&g_lib))) {
      FT_Face face;
      if (!FT_New_Memory_Face(g_lib, fr->data, (FT_Long)fr->size, 0, &face)) {
        r = (FtFont *)calloc(1, sizeof *r); r->face = face;
        r->ppem = pick_ppem(face, height); FT_Set_Pixel_Sizes(face, 0, (FT_UInt)r->ppem);
        FT_Size_Metrics *sm = &face->size->metrics; GuiTextMetrics *m = &r->m;
        m->ascent = (int)(sm->ascender >> 6); m->descent = (int)(-(sm->descender >> 6)); m->height = m->ascent + m->descent;
        m->internal_leading = m->height - r->ppem;
        m->external_leading = (int)(sm->height >> 6) - m->height; if (m->external_leading < 0) m->external_leading = 0;
        TT_OS2 *os2 = (TT_OS2 *)FT_Get_Sfnt_Table(face, ft_sfnt_os2);
        m->avg_width = os2 ? (int)((FT_MulFix(os2->xAvgCharWidth, sm->x_scale) + 32) >> 6) : (int)(sm->max_advance >> 7);
        m->max_width = (int)(sm->max_advance >> 6);
        m->first = 32; m->last = 126; m->def_char = '?'; m->brk_char = ' ';
      }
    }
  }
  pthread_mutex_unlock(&g_mu);
  return r;
}
static void ft_close(void *p) { FtFont *f = (FtFont *)p; if (!f) return; pthread_mutex_lock(&g_mu); FT_Done_Face(f->face); pthread_mutex_unlock(&g_mu); free(f); }
static void ft_metrics(void *p, GuiTextMetrics *m) { *m = ((FtFont *)p)->m; }
static int ft_glyph(void *p, uint32_t cp, int render, GuiGlyph *g) {
  FtFont *f = (FtFont *)p; int ok = 0; memset(g, 0, sizeof *g);
  pthread_mutex_lock(&g_mu);
  if (!FT_Load_Glyph(f->face, FT_Get_Char_Index(f->face, cp), render ? FT_LOAD_DEFAULT | FT_LOAD_RENDER : FT_LOAD_DEFAULT)) {
    FT_GlyphSlot s = f->face->glyph; ok = 1;
    g->advance = (int)((s->advance.x + 32) >> 6);
    if (render && s->bitmap.pixel_mode == FT_PIXEL_MODE_GRAY && s->bitmap.width && s->bitmap.rows) {
      g->w = (int)s->bitmap.width; g->h = (int)s->bitmap.rows; g->left = s->bitmap_left; g->top = s->bitmap_top;
      g->cov = (uint8_t *)malloc((size_t)g->w * g->h);
      for (int y = 0; y < g->h; y++) memcpy(g->cov + (size_t)y * g->w, s->bitmap.buffer + (ptrdiff_t)y * s->bitmap.pitch, (size_t)g->w);
    }
  }
  pthread_mutex_unlock(&g_mu);
  return ok;
}

static const GuiTextEngine g_engine = { ft_open, ft_close, ft_metrics, ft_glyph, ft_resolve, ft_nfaces, ft_face_name };
const GuiTextEngine *gui_ft_engine(void) { return &g_engine; }
