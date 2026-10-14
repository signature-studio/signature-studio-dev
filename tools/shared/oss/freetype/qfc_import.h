#ifndef QFC_IMPORT_H
#define QFC_IMPORT_H
#include <stddef.h>

/* QuickFontCache が GetProcAddress で解決する FT_* 14 本の名前 → FreeType 2.7 関数。表に無い名前は NULL。 */
void *qfc_ft_resolve(const char *name);
size_t qfc_ft_count(void);

#endif
