/* T-SH-79 (#3412) 検証ハーネス: guest の GetProcAddress 相当 (qfc_gpa) が返す擬似トークンだけで FreeType 2.7 を呼ぶ。
 * (1) 表の 14 本はトークンを返し、表外 4 本は 0 を返すこと、(2) トークン経由の描画結果が直接呼出と一致すること を見る。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include "qfc_import.h"

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

static uint64_t tok_of(const char *nm) { return qfc_gpa(nm); }
static uint64_t call(uint64_t tok, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t a4) {
  uint64_t a[5] = { a0, a1, a2, a3, a4 }, r = 0;
  if (!qfc_gpa_call(tok, a, &r)) { puts("NG call: not a token"); exit(1); }
  return r;
}

int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: %s font.ttf\n", argv[0]); return 2; }
  int nok = 0, nabs = 0;
  for (size_t i = 0; i < sizeof need / sizeof need[0]; i++) if (tok_of(need[i]) >= QFC_GPA_TOK_BASE) nok++;
  for (size_t i = 0; i < sizeof absent / sizeof absent[0]; i++) if (tok_of(absent[i]) == 0) nabs++;
  printf("gpa table n=%zu tokens=%d/%zu absent_zero=%d/%zu\n", qfc_ft_count(), nok, sizeof need / sizeof need[0],
         nabs, sizeof absent / sizeof absent[0]);
  if (nok != 14 || nabs != 4) return 1;

  FILE *fp = fopen(argv[1], "rb");
  if (!fp) { puts("open fail"); return 1; }
  fseek(fp, 0, SEEK_END); long fsz = ftell(fp); fseek(fp, 0, SEEK_SET);
  FT_Byte *buf = malloc((size_t)fsz);
  if (!buf || fread(buf, 1, (size_t)fsz, fp) != (size_t)fsz) { puts("read fail"); return 1; }
  fclose(fp);

  /* トークン経由: init → new_memory_face(index 0) → select/set charmap → char size → 描画 (サイズ 16 の 'A' 'g' '@') */
  FT_Library lib = NULL;
  uint64_t rc = call(tok_of("FT_Init_FreeType"), (uint64_t)(uintptr_t)&lib, 0, 0, 0, 0);
  printf("init rc=%u\n", (unsigned)rc);
  FT_Face face = NULL;
  rc = call(tok_of("FT_New_Memory_Face"), (uint64_t)(uintptr_t)lib, (uint64_t)(uintptr_t)buf, (uint64_t)fsz, 0,
            (uint64_t)(uintptr_t)&face);
  printf("new_memory_face rc=%u\n", (unsigned)rc);
  rc = call(tok_of("FT_Select_Charmap"), (uint64_t)(uintptr_t)face, FT_ENCODING_UNICODE, 0, 0, 0);
  printf("select_charmap rc=%u\n", (unsigned)rc);
  rc = call(tok_of("FT_Set_Char_Size"), (uint64_t)(uintptr_t)face, 16 * 64, 16 * 64, 72, 72);
  printf("char_size rc=%u\n", (unsigned)rc);
  uint64_t total = 14695981039346656037ULL, tokA = 0;
  const unsigned chars[] = {'A', 'g', '@'};
  for (unsigned ci = 0; ci < 3; ci++) {
    uint64_t gi = call(tok_of("FT_Get_Char_Index"), (uint64_t)(uintptr_t)face, chars[ci], 0, 0, 0);
    rc = call(tok_of("FT_Load_Glyph"), (uint64_t)(uintptr_t)face, gi, FT_LOAD_DEFAULT, 0, 0);
    rc = call(tok_of("FT_Render_Glyph"), (uint64_t)(uintptr_t)face->glyph, FT_RENDER_MODE_NORMAL, 0, 0, 0);
    FT_Bitmap *b = &face->glyph->bitmap;
    uint64_t h = fnv(b->buffer, (size_t)abs(b->pitch) * b->rows, 14695981039346656037ULL);
    if (ci == 0) tokA = h;
    total = fnv((unsigned char *)&h, 8, total);
    printf("c=%x gi=%u rerr=%u w=%u h=%u hash=%016llx\n", chars[ci], (unsigned)gi, (unsigned)rc, b->width, b->rows,
           (unsigned long long)h);
  }
  /* 直接呼出 (表の fn ポインタ) で同じ 'A' の描画を取り、トークン経由と一致するかを見る */
  FT_UInt di = FT_Get_Char_Index(face, 'A');
  FT_Load_Glyph(face, di, FT_LOAD_DEFAULT);
  FT_Render_Glyph(face->glyph, FT_RENDER_MODE_NORMAL);
  FT_Bitmap *db = &face->glyph->bitmap;
  uint64_t directA = fnv(db->buffer, (size_t)abs(db->pitch) * db->rows, 14695981039346656037ULL);
  printf("direct c=A hash=%016llx\n", (unsigned long long)directA);
  printf("TOTAL %016llx\n", (unsigned long long)total);
  if (directA != tokA) { puts("NG token route != direct call"); return 1; }
  call(tok_of("FT_Done_Face"), (uint64_t)(uintptr_t)face, 0, 0, 0, 0);
  call(tok_of("FT_Done_FreeType"), (uint64_t)(uintptr_t)lib, 0, 0, 0, 0);
  free(buf);
  return 0;
}
