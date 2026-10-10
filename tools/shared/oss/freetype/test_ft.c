/* FreeType 2.7 検証ハーネス: native / wasm で同一出力を比較する (FL が使う API 面: Init/New_Face/Set_Pixel_Sizes/Load_Char/Render) */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_GLYPH_H
#include FT_OUTLINE_H

static uint64_t fnv(const unsigned char *p, size_t n, uint64_t h) {
  for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
  return h;
}

int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: %s font.ttf\n", argv[0]); return 2; }
  FT_Library lib; FT_Int ma, mi, pa;
  if (FT_Init_FreeType(&lib)) { puts("init fail"); return 1; }
  FT_Library_Version(lib, &ma, &mi, &pa);
  printf("FreeType %d.%d.%d\n", ma, mi, pa);
  FT_Face face;
  if (FT_New_Face(lib, argv[1], 0, &face)) { puts("new_face fail"); return 1; }
  printf("family=%s style=%s glyphs=%ld upem=%d\n", face->family_name, face->style_name, (long)face->num_glyphs, face->units_per_EM);
  const int sizes[] = {12, 16, 48};
  const unsigned chars[] = {'A', 'g', '8', '@', 'W', 0x3042};
  uint64_t total = 14695981039346656037ULL;
  for (unsigned si = 0; si < 3; si++) {
    FT_Set_Pixel_Sizes(face, 0, sizes[si]);
    for (unsigned ci = 0; ci < sizeof(chars) / sizeof(chars[0]); ci++) {
      FT_UInt gi = FT_Get_Char_Index(face, chars[ci]);
      FT_Int32 flags[2] = {FT_LOAD_DEFAULT | FT_LOAD_RENDER, FT_LOAD_NO_HINTING | FT_LOAD_RENDER};
      for (int fi = 0; fi < 2; fi++) {
        if (FT_Load_Glyph(face, gi, flags[fi])) { printf("s=%d c=%x f=%d load_fail\n", sizes[si], chars[ci], fi); continue; }
        FT_GlyphSlot g = face->glyph; FT_Bitmap *b = &g->bitmap;
        uint64_t h = fnv(b->buffer, (size_t)abs(b->pitch) * b->rows, 14695981039346656037ULL);
        total = fnv((unsigned char *)&h, 8, total);
        printf("s=%d c=%x f=%d gi=%u w=%u h=%u pitch=%d left=%d top=%d adv=%ld hash=%016llx\n", sizes[si], chars[ci], fi, gi,
               b->width, b->rows, b->pitch, g->bitmap_left, g->bitmap_top, (long)g->advance.x, (unsigned long long)h);
      }
    }
  }
  /* stroker / outline bbox (FT_Outline_Get_CBox) も通す */
  FT_Set_Pixel_Sizes(face, 0, 64);
  FT_Load_Char(face, 'S', FT_LOAD_NO_BITMAP);
  FT_BBox bb; FT_Outline_Get_CBox(&face->glyph->outline, &bb);
  printf("cbox %ld %ld %ld %ld npts=%d\n", (long)bb.xMin, (long)bb.yMin, (long)bb.xMax, (long)bb.yMax, face->glyph->outline.n_points);
  printf("TOTAL %016llx\n", (unsigned long long)total);
  FT_Done_Face(face); FT_Done_FreeType(lib);
  return 0;
}
