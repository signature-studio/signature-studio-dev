/* QuickFontCache_x64.dll が freetype.dll から名前で解決する FT_* 14 本の import 表 (T-SH-33 / #1748)。
 * 名前は tools/shared/REPORT_APPENDIX.md §B の UTF-16LE 走査結果と一致。欠落 17 本 (FT_Alloc 等) は表に入れない。 */
#include <string.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include "qfc_import.h"

typedef struct { const char *name; void *fn; } QfcImportEnt;

static const QfcImportEnt qfc_imports[] = {
  { "FT_Attach_File", (void *)FT_Attach_File },
  { "FT_Done_Face", (void *)FT_Done_Face },
  { "FT_Done_FreeType", (void *)FT_Done_FreeType },
  { "FT_Get_Char_Index", (void *)FT_Get_Char_Index },
  { "FT_Get_Kerning", (void *)FT_Get_Kerning },
  { "FT_Init_FreeType", (void *)FT_Init_FreeType },
  { "FT_Load_Glyph", (void *)FT_Load_Glyph },
  { "FT_New_Face", (void *)FT_New_Face },
  { "FT_New_Memory_Face", (void *)FT_New_Memory_Face },
  { "FT_Render_Glyph", (void *)FT_Render_Glyph },
  { "FT_Select_Charmap", (void *)FT_Select_Charmap },
  { "FT_Set_Char_Size", (void *)FT_Set_Char_Size },
  { "FT_Set_Charmap", (void *)FT_Set_Charmap },
  { "FT_Set_Pixel_Sizes", (void *)FT_Set_Pixel_Sizes },
};

void *qfc_ft_resolve(const char *name) {
  for (size_t i = 0; i < sizeof qfc_imports / sizeof qfc_imports[0]; i++)
    if (!strcmp(qfc_imports[i].name, name)) return qfc_imports[i].fn;
  return NULL;
}

size_t qfc_ft_count(void) { return sizeof qfc_imports / sizeof qfc_imports[0]; }
