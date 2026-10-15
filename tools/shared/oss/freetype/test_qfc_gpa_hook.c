/* T-SH-83 (#3434) 検証ハーネス: guest の imp_GetProcAddress (fle_cpu.c) → fle_gpa_hook (qfc_imp.c) → qfc_gpa トークン、
 * 続く間接 call (ott_unlifted → fle_ff_hook → qfc_gpa_call) が FreeType の FT_* を呼ぶ経路を native で通す。
 * boot (DllMain) は通さない。表の名前 = トークン / 表外 = 0 / トークン call の戻り値 (FT_Get_Char_Index) を見る。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ft2build.h>
#include FT_FREETYPE_H
#include "fle_cpu.h"
#include "qfc_import.h"

void imp_GetProcAddress(void);
void ott_unlifted(uint64_t va);

static int fails;
#define CHECK(c, msg) do { if (!(c)) { printf("NG %s\n", msg); fails++; } } while (0)

int main(int argc, char **argv) {
  if (argc < 2) { puts("usage: test_qfc_gpa_hook <font.ttf>"); return 2; }
  FT_Library lib; FT_Face face;
  if (FT_Init_FreeType(&lib) || FT_New_Face(lib, argv[1], 0, &face)) { puts("NG font"); return 1; }

  /* guest の stack を模した領域 (ott_unlifted は [RSP] を retaddr として pop し、qfc_ff は [RSP+0x28] を読む) */
  static uint64_t stk[32];
  uint64_t *rsp = &stk[8];
  R[RSP] = (uint64_t)(uintptr_t)rsp;

  /* 1. imp_GetProcAddress: lpProcName (RDX) = 名前、戻り値 RAX */
  const char *nm = "FT_Get_Char_Index";
  R[RCX] = 0x1234; R[RDX] = (uint64_t)(uintptr_t)nm; R[RSP] = (uint64_t)(uintptr_t)rsp; rsp[0] = 0xdead;
  imp_GetProcAddress();
  uint64_t tok = R[RAX];
  CHECK(tok == qfc_gpa(nm) && tok >= QFC_GPA_TOK_BASE && tok < QFC_GPA_TOK_BASE + 14, "GetProcAddress table name -> token");
  printf("gpa FT_Get_Char_Index tok=0x%llx\n", (unsigned long long)tok);

  R[RDX] = (uint64_t)(uintptr_t)"FT_Alloc"; R[RSP] = (uint64_t)(uintptr_t)rsp; rsp[0] = 0xdead;
  imp_GetProcAddress();
  CHECK(R[RAX] == 0, "GetProcAddress absent name -> 0");

  /* 2. 間接 call: ott_unlifted(tok) → fle_ff_hook("unlifted", tok) → qfc_gpa_call。引数は Win64 の RCX/RDX、戻りは RAX */
  R[RCX] = (uint64_t)(uintptr_t)face; R[RDX] = 'A';
  R[RSP] = (uint64_t)(uintptr_t)rsp; rsp[0] = 0xdead;
  uint64_t before = R[RSP];
  ott_unlifted(tok);
  CHECK(R[RSP] == before + 8, "token call pops retaddr");
  uint32_t gi_hook = (uint32_t)R[RAX];

  FT_UInt gi_direct = FT_Get_Char_Index(face, 'A');
  printf("call FT_Get_Char_Index('A') hook=%u direct=%u\n", gi_hook, gi_direct);
  CHECK(gi_hook == gi_direct && gi_direct != 0, "token call result == direct call");

  printf("%s: qfc_imp hook route (gpa + unlifted token call)\n", fails ? "FAIL" : "PASS");
  FT_Done_Face(face); FT_Done_FreeType(lib);
  return fails ? 1 : 0;
}
