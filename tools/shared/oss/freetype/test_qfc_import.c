/* T-SH-33 (#1748) 検証ハーネス: qfc_import.c の表で解決した関数ポインタだけで FreeType 2.7 を呼ぶ。
 * 表の 14 本すべてが解決すること・表外の名前が NULL になること・描画結果が native / wasm32 / wasm64 で一致すること を見る。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include "qfc_import.h"

typedef FT_Error (*p_init)(FT_Library *);
typedef FT_Error (*p_done_ft)(FT_Library);
typedef FT_Error (*p_new_face)(FT_Library, const char *, FT_Long, FT_Face *);
typedef FT_Error (*p_new_mem_face)(FT_Library, const FT_Byte *, FT_Long, FT_Long, FT_Face *);
typedef FT_Error (*p_done_face)(FT_Face);
typedef FT_Error (*p_attach)(FT_Face, const char *);
typedef FT_UInt (*p_char_index)(FT_Face, FT_ULong);
typedef FT_Error (*p_kerning)(FT_Face, FT_UInt, FT_UInt, FT_UInt, FT_Vector *);
typedef FT_Error (*p_load_glyph)(FT_Face, FT_UInt, FT_Int32);
typedef FT_Error (*p_render)(FT_GlyphSlot, FT_Render_Mode);
typedef FT_Error (*p_select_cmap)(FT_Face, FT_Encoding);
typedef FT_Error (*p_char_size)(FT_Face, FT_F26Dot6, FT_F26Dot6, FT_UInt, FT_UInt);
typedef FT_Error (*p_set_cmap)(FT_Face, FT_CharMap);
typedef FT_Error (*p_pixel_sizes)(FT_Face, FT_UInt, FT_UInt);

static const char *need[] = {
  "FT_Attach_File", "FT_Done_Face", "FT_Done_FreeType", "FT_Get_Char_Index", "FT_Get_Kerning",
  "FT_Init_FreeType", "FT_Load_Glyph", "FT_New_Face", "FT_New_Memory_Face", "FT_Render_Glyph",
  "FT_Select_Charmap", "FT_Set_Char_Size", "FT_Set_Charmap", "FT_Set_Pixel_Sizes",
};
static const char *absent[] = { "FT_Alloc", "FT_Free", "FT_Realloc", "FT_Sqrt32" };

static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

#define RESOLVE(var, T, name) \
  T var = (T)qfc_ft_resolve(name); \
  if (!var) { printf("NG unresolved %s\n", name); return 1; }

int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: %s font.ttf\n", argv[0]); return 2; }
  int nres = 0, nfail = 0;
  for (size_t i = 0; i < sizeof need / sizeof need[0]; i++) {
    if (qfc_ft_resolve(need[i])) nres++; else { printf("NG unresolved %s\n", need[i]); nfail++; }
  }
  int nabs = 0;
  for (size_t i = 0; i < sizeof absent / sizeof absent[0]; i++) if (!qfc_ft_resolve(absent[i])) nabs++;
  printf("table n=%zu resolved=%d/%zu absent_null=%d/%zu\n", qfc_ft_count(), nres, sizeof need / sizeof need[0],
         nabs, sizeof absent / sizeof absent[0]);
  if (nfail || nabs != 4 || qfc_ft_count() != 14) return 1;

  RESOLVE(f_init, p_init, "FT_Init_FreeType");
  RESOLVE(f_done_ft, p_done_ft, "FT_Done_FreeType");
  RESOLVE(f_new_mem, p_new_mem_face, "FT_New_Memory_Face");
  RESOLVE(f_new_face, p_new_face, "FT_New_Face");
  RESOLVE(f_done_face, p_done_face, "FT_Done_Face");
  RESOLVE(f_attach, p_attach, "FT_Attach_File");
  RESOLVE(f_cidx, p_char_index, "FT_Get_Char_Index");
  RESOLVE(f_kern, p_kerning, "FT_Get_Kerning");
  RESOLVE(f_load, p_load_glyph, "FT_Load_Glyph");
  RESOLVE(f_render, p_render, "FT_Render_Glyph");
  RESOLVE(f_sel_cmap, p_select_cmap, "FT_Select_Charmap");
  RESOLVE(f_char_size, p_char_size, "FT_Set_Char_Size");
  RESOLVE(f_set_cmap, p_set_cmap, "FT_Set_Charmap");
  RESOLVE(f_pix, p_pixel_sizes, "FT_Set_Pixel_Sizes");

  FT_Library lib;
  if (f_init(&lib)) { puts("init fail"); return 1; }

  FILE *fp = fopen(argv[1], "rb");
  if (!fp) { puts("open fail"); return 1; }
  fseek(fp, 0, SEEK_END); long fsz = ftell(fp); fseek(fp, 0, SEEK_SET);
  FT_Byte *buf = malloc((size_t)fsz);
  if (!buf || fread(buf, 1, (size_t)fsz, fp) != (size_t)fsz) { puts("read fail"); return 1; }
  fclose(fp);

  FT_Face face;
  if (f_new_mem(lib, buf, fsz, 0, &face)) { puts("new_memory_face fail"); return 1; }
  printf("family=%s style=%s glyphs=%ld charmaps=%d\n", face->family_name, face->style_name,
         (long)face->num_glyphs, face->num_charmaps);
  printf("select_charmap rc=%d\n", f_sel_cmap(face, FT_ENCODING_UNICODE));
  if (face->num_charmaps > 0) printf("set_charmap rc=%d\n", f_set_cmap(face, face->charmaps[0]));
  printf("char_size rc=%d\n", f_char_size(face, 16 * 64, 16 * 64, 72, 72));
  printf("attach_file rc=%d\n", f_attach(face, argv[1]));

  const int sizes[] = {12, 16, 48};
  const unsigned chars[] = {'A', 'g', '8', '@', 'W', 0x3042};
  uint64_t total = 14695981039346656037ULL;
  for (unsigned si = 0; si < 3; si++) {
    f_pix(face, 0, sizes[si]);
    for (unsigned ci = 0; ci < sizeof(chars) / sizeof(chars[0]); ci++) {
      FT_UInt gi = f_cidx(face, chars[ci]);
      for (int fi = 0; fi < 2; fi++) {
        FT_Int32 lf = fi == 0 ? FT_LOAD_DEFAULT : FT_LOAD_NO_HINTING;
        FT_Render_Mode rm = fi == 0 ? FT_RENDER_MODE_NORMAL : FT_RENDER_MODE_LIGHT;
        if (f_load(face, gi, lf)) { printf("s=%d c=%x f=%d load_fail\n", sizes[si], chars[ci], fi); continue; }
        FT_Error re = f_render(face->glyph, rm);
        FT_Bitmap *b = &face->glyph->bitmap;
        uint64_t h = fnv(b->buffer, (size_t)abs(b->pitch) * b->rows, 14695981039346656037ULL);
        total = fnv((unsigned char *)&h, 8, total);
        printf("s=%d c=%x f=%d gi=%u rerr=%d w=%u h=%u pitch=%d left=%d top=%d adv=%ld hash=%016llx\n",
               sizes[si], chars[ci], fi, gi, re, b->width, b->rows, b->pitch, face->glyph->bitmap_left,
               face->glyph->bitmap_top, (long)face->glyph->advance.x, (unsigned long long)h);
      }
    }
    FT_Vector kv = {0, 0};
    FT_Error ke = f_kern(face, f_cidx(face, 'A'), f_cidx(face, 'W'), FT_KERNING_DEFAULT, &kv);
    printf("kern s=%d rc=%d x=%ld y=%ld\n", sizes[si], ke, (long)kv.x, (long)kv.y);
    int32_t kx = (int32_t)kv.x;
    total = fnv((unsigned char *)&kx, sizeof kx, total);
  }
  printf("TOTAL %016llx\n", (unsigned long long)total);
  f_done_face(face);
  f_done_ft(lib);
  free(buf);
  return 0;
}
