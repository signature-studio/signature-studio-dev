/* wc_glue.c: ildsp WaveformColouring_CreateInstance の wasm 側入口。fle_cpu.c (flelift runtime) の上に載る (T-SH-52 / #3216)。
 * 呼出規約は tools/shared/lift/rex/rex_glue.c と同じ (ms_abi: rcx/rdx/r8/r9)。
 * import スタブは native_ref.c と同じ規約 (同じ bump heap・同じ戻り値・同じ呼出回数の数え方)。 */
#include "fle_cpu.h"
#include "wc_layout.h"

static uint8_t guest_stack[1 << 16] __attribute__((aligned(16)));
#define STACK_TOP ((uint64_t)(uintptr_t)guest_stack + sizeof(guest_stack) - 0x100)
static uint64_t wc_hits, wc_heap_top;

#define STUB_RET(v) do { R[RAX] = (uint64_t)(v); R[RSP] += 8; wc_hits++; } while (0)

uint64_t wc_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3) {
    R[RSP] = STACK_TOP;
    R[RCX] = a0; R[RDX] = a1; R[R8] = a2; R[R9] = a3;
    R[RAX] = 0xFEEDFACE5EED0000ULL;
    R[RSP] -= 8; ST64(R[RSP], 0xdead0000ull);
    ott_dispatch(va);
    return R[RAX];
}

void wc_reset(void) {
    memset(R, 0, sizeof(R)); memset(X, 0, sizeof(X)); memset(YL, 0, sizeof(YL));
    memset(M, 0, sizeof(M));
    fZF = fSF = fCF = fOF = fPF = fAF = fDF = 0;
    x87_cw = 0x037f; x87_sw = 0; mxcsr = 0x1f80;
    fle_install_teb();
    wc_hits = 0;
    wc_heap_top = WC_ARENA;
}

uint64_t wc_hits_get(void) { return wc_hits; }

void imp_HeapAlloc(void) {
    uint64_t n = (R[R8] + 15) & ~15ull;
    if (wc_heap_top + n > WC_ARENA + WC_ARENA_SZ) { STUB_RET(0); return; }
    uint64_t p = wc_heap_top; wc_heap_top += n;
    STUB_RET(p);
}
void imp_HeapFree(void) { STUB_RET(1); }
void imp_GetLastError(void) { STUB_RET(0); }
void imp_SetLastError(void) { STUB_RET(0); }
void imp_GetCurrentProcess(void) { STUB_RET(0xFFFFFFFFFFFFFFFFull); }
void imp_EnterCriticalSection(void) { STUB_RET(0); }
void imp_LeaveCriticalSection(void) { STUB_RET(0); }
void imp_FlsGetValue(void) { STUB_RET(0); }
void imp_FlsSetValue(void) { STUB_RET(1); }
void imp_IsProcessorFeaturePresent(void) { STUB_RET(0); }
void imp_RaiseException(void) { STUB_RET(0); }
void imp_RtlCaptureContext(void) { STUB_RET(0); }
void imp_RtlLookupFunctionEntry(void) { STUB_RET(0); }
void imp_RtlPcToFileHeader(void) { STUB_RET(0); }
void imp_RtlVirtualUnwind(void) { STUB_RET(0); }
void imp_SetUnhandledExceptionFilter(void) { STUB_RET(0); }
void imp_UnhandledExceptionFilter(void) { STUB_RET(0); }
void imp_TerminateProcess(void) { STUB_RET(0); }
