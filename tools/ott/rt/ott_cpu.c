/* ott_cpu.c: lifted code の CPU 状態 + 実行時 fail-fast + Win32 import (DSP 経路で実使用される最小集合) */
#include "ott_cpu.h"
#include <stdio.h>
uint64_t R[16];
X128 X[16];
uint8_t fZF, fSF, fCF, fOF, fPF;
uint64_t ott_xrip;
uint32_t ott_mxcsr = 0x1f80u;   /* x86 既定 (全例外 mask, round-nearest)。ldmxcsr/stmxcsr はこの shadow を読み書き */

void ott_unsup(uint64_t addr, const char* what) {
    fprintf(stderr, "[ott] UNSUPPORTED instruction at %#llx: %s\n", (unsigned long long)addr, what); abort();
}
void ott_unlifted(uint64_t va) {
    fprintf(stderr, "[ott] call to UNLIFTED function %#llx (shifted VA; RVA %#llx) ret=%#llx\n", (unsigned long long)va, (unsigned long long)(va - 0x30000000ull), (unsigned long long)LD64(R[RSP])); abort();
}
void ott_badjump(uint64_t addr, uint64_t target) {
    fprintf(stderr, "[ott] bad jump at %#llx target %#llx\n", (unsigned long long)addr, (unsigned long long)target); abort();
}
void ott_missing_import(const char* nm) {
    fprintf(stderr, "[ott] MISSING IMPORT %s\n", nm); abort();
}
#ifdef OTT_CHK
void ott_chk(uint64_t a, int line) {
    if ((a >> 32) || a < 0x1000) { fprintf(stderr, "[ott] bad guest address %#llx (ott_cpu.h line %d)\n", (unsigned long long)a, line); abort(); }
}
#endif

/* ---- imports: callee 側が ret 相当 (R[RSP] += 8) を行う ---- */
#define IMP_RET() (R[RSP] += 8)
#define OTT_ALOG ((volatile uint32_t*)0x35f00000)
static void ott_alog(void* p, uint64_t n) {
    uint32_t c = OTT_ALOG[0];
    if (c < 0x8000u) { OTT_ALOG[2 + 2 * c] = (uint32_t)(uintptr_t)p; OTT_ALOG[3 + 2 * c] = (uint32_t)n; OTT_ALOG[0] = c + 1; }
}
void imp_HeapAlloc(void) {
    uint64_t flags = R[RDX] & 0xffffffff, sz = R[R8];
    void* p = (flags & 8) ? calloc(1, sz ? sz : 1) : malloc(sz ? sz : 1);
    if (!(flags & 8) && p) memset(p, 0, sz);     /* native 参照 (alloc 毎 zero) と揃える */
    ott_alog(p, sz);
    R[RAX] = (uint64_t)(uintptr_t)p; IMP_RET();
}
void imp_HeapFree(void) { R[RAX] = 1; IMP_RET(); }
void imp_GetProcessHeap(void) { R[RAX] = 0x1000; IMP_RET(); }
void imp_GetLastError(void) { R[RAX] = 0; IMP_RET(); }
void imp_SetLastError(void) { IMP_RET(); }
void imp_EnterCriticalSection(void) { IMP_RET(); }
void imp_LeaveCriticalSection(void) { IMP_RET(); }
