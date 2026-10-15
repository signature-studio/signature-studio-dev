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

#define QFC_N (sizeof qfc_imports / sizeof qfc_imports[0])

uint64_t qfc_gpa(const char *name) {
  for (size_t i = 0; i < QFC_N; i++)
    if (!strcmp(qfc_imports[i].name, name)) return QFC_GPA_TOK_BASE + i;
  return 0;
}

/* Win64 の引数は a[0..4] (RCX/RDX/R8/R9 + stack)。long は Win64 で 32bit なので FT_Long 系は下位 32bit を符号拡張して渡す。
 * 関数は表の fn ポインタを型付きに cast して呼ぶ (トークン → 表 → FreeType の経路を 1 本にする)。 */
#define GPA_P(i) ((void *)(uintptr_t)a[i])
#define GPA_L(i) ((long)(int32_t)a[i])
int qfc_gpa_call(uint64_t tok, const uint64_t a[5], uint64_t *rax) {
  if (tok < QFC_GPA_TOK_BASE || tok >= QFC_GPA_TOK_BASE + QFC_N) return 0;
  size_t k = (size_t)(tok - QFC_GPA_TOK_BASE);
  void *f = qfc_imports[k].fn;
  uint32_t r = 0;
  switch (k) {
  case 0: r = ((FT_Error (*)(FT_Face, const char *))f)(GPA_P(0), GPA_P(1)); break;
  case 1: r = ((FT_Error (*)(FT_Face))f)(GPA_P(0)); break;
  case 2: r = ((FT_Error (*)(FT_Library))f)(GPA_P(0)); break;
  case 3: r = ((FT_UInt (*)(FT_Face, FT_ULong))f)(GPA_P(0), (FT_ULong)(uint32_t)a[1]); break;
  case 4: r = ((FT_Error (*)(FT_Face, FT_UInt, FT_UInt, FT_UInt, FT_Vector *))f)(
                GPA_P(0), (FT_UInt)a[1], (FT_UInt)a[2], (FT_UInt)a[3], (FT_Vector *)GPA_P(4)); break;
  case 5: r = ((FT_Error (*)(FT_Library *))f)(GPA_P(0)); break;
  case 6: r = ((FT_Error (*)(FT_Face, FT_UInt, FT_Int32))f)(GPA_P(0), (FT_UInt)a[1], (FT_Int32)(int32_t)a[2]); break;
  case 7: r = ((FT_Error (*)(FT_Library, const char *, FT_Long, FT_Face *))f)(GPA_P(0), GPA_P(1), GPA_L(2), GPA_P(3)); break;
  case 8: r = ((FT_Error (*)(FT_Library, const FT_Byte *, FT_Long, FT_Long, FT_Face *))f)(
                GPA_P(0), GPA_P(1), GPA_L(2), GPA_L(3), GPA_P(4)); break;
  case 9: r = ((FT_Error (*)(FT_GlyphSlot, FT_Render_Mode))f)(GPA_P(0), (FT_Render_Mode)(int32_t)a[1]); break;
  case 10: r = ((FT_Error (*)(FT_Face, FT_Encoding))f)(GPA_P(0), (FT_Encoding)(int32_t)a[1]); break;
  case 11: r = ((FT_Error (*)(FT_Face, FT_F26Dot6, FT_F26Dot6, FT_UInt, FT_UInt))f)(
                GPA_P(0), GPA_L(1), GPA_L(2), (FT_UInt)a[3], (FT_UInt)a[4]); break;
  case 12: r = ((FT_Error (*)(FT_Face, FT_CharMap))f)(GPA_P(0), GPA_P(1)); break;
  case 13: r = ((FT_Error (*)(FT_Face, FT_UInt, FT_UInt))f)(GPA_P(0), (FT_UInt)a[1], (FT_UInt)a[2]); break;
  default: return 0;
  }
  *rax = (uint64_t)r;   /* x64 では 32bit 戻り値は eax 書込みで上位が 0 になる */
  return 1;
}
#undef GPA_P
#undef GPA_L
