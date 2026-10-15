#ifndef QFC_IMPORT_H
#define QFC_IMPORT_H
#include <stddef.h>
#include <stdint.h>

/* QuickFontCache が GetProcAddress で解決する FT_* 14 本の名前 → FreeType 2.7 関数。表に無い名前は NULL。 */
void *qfc_ft_resolve(const char *name);
size_t qfc_ft_count(void);

/* guest 側 GetProcAddress の擬似トークン (#3412)。表で解決できる名前だけ QFC_GPA_TOK_BASE + 表の index を返し、
 * 表に無い名前は 0。guest の間接 call はトークン値を ott_dispatch 相当へ渡すので、qfc_gpa_call がその呼出を実行する。 */
#define QFC_GPA_TOK_BASE 0x7F200000u
uint64_t qfc_gpa(const char *name);
/* a[0..3] = Win64 の RCX/RDX/R8/R9、a[4] = 第 5 引数 (stack)。戻り値は RAX。トークンでなければ 0 を返し *rax は触らない。 */
int qfc_gpa_call(uint64_t tok, const uint64_t a[5], uint64_t *rax);

#endif
