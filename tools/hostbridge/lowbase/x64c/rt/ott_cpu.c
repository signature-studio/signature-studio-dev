/* ott_cpu.c: lifted code の CPU 状態 + 実行時 fail-fast + Win32 import (DSP 経路で実使用される最小集合) */
#include "ott_cpu.h"
#include <stdio.h>
/* lowbase: LB_IMG_BASE は -D で渡す (V-shift 先). alloc log は固定アドレスではなく静的配列 (小 memory 化) */
#ifndef LB_IMG_BASE
#define LB_IMG_BASE 0x30000000u
#endif
uint64_t R[16];
X128 X[16];
X128 XH[16];   /* CAB-135: ymm 上位 128bit (VEX.256 / VEX zeroing 用) — tools/ott/rt/ott_cpu.c と同等 */
uint32_t ott_mxcsr = 0x1f80u;   /* CAB-138: MXCSR software shadow (既定 0x1f80, ldmxcsr/stmxcsr 用) */
uint8_t fZF, fSF, fCF, fOF, fPF;
uint64_t ott_xrip;

void ott_unsup(uint64_t addr, const char* what) {
    fprintf(stderr, "[ott] UNSUPPORTED instruction at %#llx: %s\n", (unsigned long long)addr, what); abort();
}
void ott_unlifted(uint64_t va) {
    fprintf(stderr, "[ott] call to UNLIFTED function %#llx (shifted VA; RVA %#llx) ret=%#llx\n", (unsigned long long)va, (unsigned long long)(va - (uint64_t)LB_IMG_BASE), (unsigned long long)LD64(R[RSP])); abort();
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
static uint32_t ott_alog_buf[2 + 2 * 0x8000];
#define OTT_ALOG ((volatile uint32_t*)ott_alog_buf)
uint32_t ott_alog_addr(void) { return (uint32_t)(uintptr_t)ott_alog_buf; }
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
