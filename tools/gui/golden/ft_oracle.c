/* ft_oracle.c — GUI-9 (#186) 独立オラクル。shim (gui_gdi.c / gui_ft.c) のコードを一切使わず、native FreeType 2.7 の API だけで
 * test/text_golden.c と同じシーン (仕様のみ共有) の期待 PPM と metrics 表 (TSV) を作る。
 * 共有する仕様: ppem 規約 (lfHeight<0 = em px / >0 = ascent-descent<=h の最大 ppem) / advance = 四捨五入した hinted advance /
 * 合成 = out = (fg*cov + dst*(255-cov) + 127)/255 (チャネル別) / TA_* と DT_* の配置規則。
 * usage: ft_oracle <fontdir> <out.ppm> <out.tsv> */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_TRUETYPE_TABLES_H
#define W 320
#define H 120
static uint8_t img[H][W][3];
static FT_Library lib;
typedef struct { FT_Face f; int ppem, asc, desc; } F;
static void fill(int x0, int y0, int x1, int y1, int r, int g, int b) { for (int y = y0; y < y1; y++) for (int x = x0; x < x1; x++) if (x >= 0 && y >= 0 && x < W && y < H) { img[y][x][0] = r; img[y][x][1] = g; img[y][x][2] = b; } }
static F openf(const char *dir, const char *file, int height) {
  char path[512]; snprintf(path, sizeof path, "%s/%s", dir, file); F o; memset(&o, 0, sizeof o);
  if (FT_New_Face(lib, path, 0, &o.f)) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
  int ppem;
  if (height < 0) ppem = -height; else if (height == 0) ppem = 12;
  else { ppem = 1; for (int p = height; p >= 1; p--) { FT_Set_Pixel_Sizes(o.f, 0, p); if ((o.f->size->metrics.ascender >> 6) - (o.f->size->metrics.descender >> 6) <= height) { ppem = p; break; } } }
  FT_Set_Pixel_Sizes(o.f, 0, ppem); o.ppem = ppem; o.asc = (int)(o.f->size->metrics.ascender >> 6); o.desc = (int)(-(o.f->size->metrics.descender >> 6));
  return o;
}
static int adv(F *f, unsigned c) { FT_Load_Glyph(f->f, FT_Get_Char_Index(f->f, c), FT_LOAD_DEFAULT); return (int)((f->f->glyph->advance.x + 32) >> 6); }
static int width(F *f, const char *s, int n) { int w = 0; for (int i = 0; i < n; i++) w += adv(f, (unsigned char)s[i]); return w; }
/* (x, ytop) = セル左上。ペンは (x, ytop + asc) のベースライン */
static void draw(F *f, int x, int ytop, const char *s, int n, int fr, int fg, int fb) {
  int pen = x, base = ytop + f->asc;
  for (int i = 0; i < n; i++) {
    FT_Load_Glyph(f->f, FT_Get_Char_Index(f->f, (unsigned char)s[i]), FT_LOAD_DEFAULT | FT_LOAD_RENDER);
    FT_GlyphSlot g = f->f->glyph; FT_Bitmap *bm = &g->bitmap;
    for (unsigned r = 0; r < bm->rows; r++) for (unsigned c = 0; c < bm->width; c++) {
      int a = bm->buffer[r * bm->pitch + c]; int px = pen + g->bitmap_left + (int)c, py = base - g->bitmap_top + (int)r;
      if (!a || px < 0 || py < 0 || px >= W || py >= H) continue;
      uint8_t *d = img[py][px]; d[0] = (fr * a + d[0] * (255 - a) + 127) / 255; d[1] = (fg * a + d[1] * (255 - a) + 127) / 255; d[2] = (fb * a + d[2] * (255 - a) + 127) / 255;
    }
    pen += (int)((g->advance.x + 32) >> 6);
  }
}
int main(int argc, char **argv) {
  if (argc < 4) return 2;
  const char *dir = argv[1];
  FT_Init_FreeType(&lib);
  fill(0, 0, W, H, 32, 32, 48);
  /* シーン (text_golden.c と同順) */
  { F f = openf(dir, "OpenSans-Regular.ttf", -12); const char *s = "Hello, World! gjpqy 0123"; draw(&f, 4, 4, s, (int)strlen(s), 255, 255, 255); }
  { F f = openf(dir, "Barlow-Regular.ttf", -14); const char *s = "Barlow OPAQUE"; int w = width(&f, s, (int)strlen(s)); fill(4, 24, 4 + w, 24 + f.asc + f.desc, 200, 40, 40); draw(&f, 4, 24, s, (int)strlen(s), 255, 255, 0); }
  { F f = openf(dir, "OpenSans-Regular.ttf", -16); const char *s = "Centered"; int w = width(&f, s, (int)strlen(s)), th = f.asc + f.desc;   /* DT_CENTER|DT_VCENTER|DT_SINGLELINE in (170,4)-(310,44) */
    draw(&f, 170 + (140 - w) / 2, 4 + (40 - th) / 2, s, (int)strlen(s), 0, 255, 128); }
  { F f = openf(dir, "OpenSans-Regular.ttf", 13); const char *l[2] = { "Line one", "second line" }; int th = f.asc + f.desc;   /* DT_LEFT 2 行 in (170,50)-(310,100); 高さ 13 = セル高 */
    for (int i = 0; i < 2; i++) draw(&f, 170, 50 + i * th, l[i], (int)strlen(l[i]), 255, 160, 0); }
  { F f = openf(dir, "OpenSans-Regular.ttf", -12); const char *s = "baseline"; int w = width(&f, s, (int)strlen(s));   /* TA_BASELINE|TA_RIGHT at (120, 70) *//* x = 120 - w, ベースライン y=70 */
    draw(&f, 120 - w, 70 - f.asc, s, (int)strlen(s), 255, 255, 255); }
  { F f = openf(dir, "Barlow-Regular.ttf", -20); const char *s = "TA_CENTER"; int w = width(&f, s, (int)strlen(s)); draw(&f, 80 - w / 2, 80, s, (int)strlen(s), 180, 220, 255); }
  FILE *o = fopen(argv[2], "wb"); fprintf(o, "P6\n%d %d\n255\n", W, H); fwrite(img, 1, sizeof img, o); fclose(o);
  /* metrics 表: face x height。列 = face height ascent descent height intlead extlead avg max | extent("The quick brown fox") */
  FILE *t = fopen(argv[3], "w"); const char *faces[2] = { "OpenSans-Regular.ttf", "Barlow-Regular.ttf" }; const char *names[2] = { "Open Sans", "Barlow" };
  int hs[] = { -8, -9, -10, -11, -12, -13, -14, -16, -18, -20, -24, -32, 12, 16, 20 };
  const char *probe = "The quick brown fox";
  for (int fi = 0; fi < 2; fi++) for (unsigned hi = 0; hi < sizeof hs / sizeof *hs; hi++) {
    F f = openf(dir, faces[fi], hs[hi]); FT_Size_Metrics *m = &f.f->size->metrics; TT_OS2 *os2 = FT_Get_Sfnt_Table(f.f, ft_sfnt_os2);
    int h = f.asc + f.desc, ext = (int)(m->height >> 6) - h; if (ext < 0) ext = 0;
    int avg = (int)((FT_MulFix(os2->xAvgCharWidth, m->x_scale) + 32) >> 6);
    fprintf(t, "%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n", names[fi], hs[hi], f.asc, f.desc, h, h - f.ppem, ext, avg, (int)(m->max_advance >> 6), width(&f, probe, (int)strlen(probe)));
    FT_Done_Face(f.f);
  }
  fclose(t); return 0;
}
