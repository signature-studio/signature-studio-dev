/* qfc_imp.c — QuickFontCache boot 用に実装した import (rt の fle_cpu.c / fle_glue.c に無いもの)。
 * gen_soft_imp.py はここに実装のある名前を soft stub から除く。 */
#include <stdlib.h>
#include "fle_cpu.h"

/* HLOCAL LocalAlloc(UINT uFlags, SIZE_T uBytes): LMEM_ZEROINIT の有無によらず calloc (0 初期化) */
void imp_LocalAlloc(void) { void *p = calloc(1, R[RDX] ? R[RDX] : 1); R[RAX] = (uint64_t)(uintptr_t)p; R[RSP] += 8; }
/* HLOCAL LocalFree(HLOCAL): 成功で NULL。解放は行わない (boot 測定のため) */
void imp_LocalFree(void) { R[RAX] = 0; R[RSP] += 8; }
