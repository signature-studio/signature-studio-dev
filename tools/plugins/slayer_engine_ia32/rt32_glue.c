/* rt32_glue.c: ia32 lift (x64c --arch ia32) を wasm から呼ぶ入口 (#1223) と、 KERNEL32 import の ia32 モデル (#3127)。
 * guest 値は VA そのまま (ia32 の lift は恒等写像)。 guest stack は VA 0x10F00000 (image の上の余白) に置く。
 * import は stdcall: 引数は ret 先の直上 (esp+4〜) に積まれ、 callee が pop する。 native_entry.c と同じ規約・同じモデル。
 * 既定の ott_cpu.c の imp_* は x64 規約 (R[RCX] 等) なので、 ここの定義を先に link して上書きする (diff_entry.py)。
 * 実装しない import は x64c の weak stub (ott_missing_import で abort = fail-fast)。 方針表は REPORT_APPENDIX_3127.md。 */
#include "ott_cpu.h"
uint64_t ott_gbase = 0x10000000ull;
#define GUEST_STACK_TOP 0x10F00000ull
#define H32_BASE 0x10800000u
#define HOST_BASE 0x00828000u
#define HOST_LEN 0x10000u
static uint32_t h32_top, g_lasterr, g_tls[64];

static void h32_reset(void) {
    h32_top = H32_BASE; g_lasterr = 0;
    memset(g_tls, 0, sizeof g_tls);
    memset((void *)(uintptr_t)H32_BASE, 0, 0x1000);
    memset((void *)(uintptr_t)HOST_BASE, 0, HOST_LEN);
}
static uint32_t h32_alloc(uint32_t sz) {
    uint32_t p = (h32_top + 8 + 7) & ~7u;
    h32_top = p + (((sz ? sz : 1) + 7) & ~7u);
    ST32(p - 8, sz);
    memset((void *)(uintptr_t)p, 0, sz);
    return p;
}
static uint32_t h32_realloc(uint32_t p, uint32_t sz) {
    if (!p) return h32_alloc(sz);
    uint32_t old = LD32(p - 8), n = h32_alloc(sz);
    memcpy((void *)(uintptr_t)n, (void *)(uintptr_t)p, old < sz ? old : sz);
    return n;
}
static uint32_t h32_valloc(uint32_t sz) {
    h32_top = (h32_top + 4095) & ~4095u;
    uint32_t p = h32_top;
    h32_top += (sz + 4095) & ~4095u;
    memset((void *)(uintptr_t)p, 0, sz);
    return p;
}

#define ARG(i) LD32(R[RSP] + 4 + 4 * (i))
#define RET(v, n) do { R[RAX] = (uint32_t)(v); R[RSP] += 4 + 4 * (n); } while (0)
void imp_EnterCriticalSection(void) { RET(0, 1); }
void imp_LeaveCriticalSection(void) { RET(0, 1); }
void imp_InitializeCriticalSection(void) { RET(0, 1); }
void imp_GetCurrentThreadId(void) { RET(0x1000, 0); }
void imp_GetLastError(void) { RET(g_lasterr, 0); }
void imp_SetLastError(void) { g_lasterr = ARG(0); RET(0, 1); }
void imp_TlsGetValue(void) { RET(g_tls[ARG(0) & 63], 1); }
void imp_TlsSetValue(void) { g_tls[ARG(0) & 63] = ARG(1); RET(1, 2); }
void imp_GetModuleFileNameA(void) { RET(0, 3); }
void imp_GetStdHandle(void) { RET(0x00020000u | (ARG(0) & 0xffff), 1); }
void imp_HeapAlloc(void) { RET(h32_alloc(ARG(2)), 3); }
void imp_HeapFree(void) { RET(1, 3); }
void imp_HeapReAlloc(void) { RET(h32_realloc(ARG(2), ARG(3)), 4); }
void imp_LoadLibraryA(void) { RET(0, 1); }
void imp_WriteFile(void) {
    if (ARG(3)) ST32(ARG(3), ARG(2));
    RET(1, 5);
}
void imp_VirtualAlloc(void) { RET(h32_valloc(ARG(1)), 4); }
void imp_VirtualFree(void) { RET(1, 3); }

uint32_t ott_call32(uint32_t va, uint32_t ecx, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3) {
    uint32_t args[4] = {a0, a1, a2, a3};
    h32_reset();
    R[RSP] = GUEST_STACK_TOP;
    for (int i = 3; i >= 0; i--) { R[RSP] -= 4; ST32(R[RSP], args[i]); }
    R[RSP] -= 4; ST32(R[RSP], 0xdead0000u);
    R[RCX] = ecx; R[RAX] = 0; R[RDX] = 0;   /* native 側 (native_entry.c) と同じ呼出し前の eax/edx = 0 */
    ott_dispatch(va);
    return (uint32_t)R[RAX];
}
