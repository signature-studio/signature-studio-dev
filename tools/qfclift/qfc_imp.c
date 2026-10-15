/* qfc_imp.c — QuickFontCache boot 用に実装した import (rt の fle_cpu.c / fle_glue.c に無いもの)。
 * gen_soft_imp.py はここに実装のある名前を soft stub から除く。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fle_cpu.h"
#include "qfc_import.h"

/* HLOCAL LocalAlloc(UINT uFlags, SIZE_T uBytes): LMEM_ZEROINIT の有無によらず calloc (0 初期化) */
void imp_LocalAlloc(void) { void *p = calloc(1, R[RDX] ? R[RDX] : 1); R[RAX] = (uint64_t)(uintptr_t)p; R[RSP] += 8; }
/* HLOCAL LocalFree(HLOCAL): 成功で NULL。解放は行わない (boot 測定のため) */
void imp_LocalFree(void) { R[RAX] = 0; R[RSP] += 8; }

/* GetProcAddress: 表で解決できる FT_* 名だけトークン (qfc_gpa)。他は 0 (fle_cpu.c の既定と同じ) */
static uint64_t qfc_gpa_hook(uint64_t h, uint64_t nm) {
  (void)h;
  return nm >= 0x10000ull ? qfc_gpa((const char *)(uintptr_t)nm) : 0;
}
/* トークンへの間接 call (ott_unlifted → fle_ff_hook)。Win64 の第 5 引数は call 時の [rsp+0x28] */
static void qfc_ff(const char *kind, uint64_t a) {
  if (strcmp(kind, "unlifted")) return;
  uint64_t arg[5] = { R[RCX], R[RDX], R[R8], R[R9], LD64(R[RSP] + 0x28) }, rax = 0;
  if (qfc_gpa_call(a, arg, &rax)) { R[RAX] = rax; R[RSP] += 8; return; }
  fprintf(stderr, "[fle] call to UNLIFTED function %#llx ret=%#llx\n", (unsigned long long)a, (unsigned long long)LD64(R[RSP])); abort();
}
__attribute__((constructor)) static void qfc_install(void) { fle_gpa_hook = qfc_gpa_hook; fle_ff_hook = qfc_ff; }
