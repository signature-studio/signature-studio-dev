/* wc_glue.c: ildsp WaveformColouring_CreateInstance の wasm 側入口。fle_cpu.c (flelift runtime) の上に載る (T-SH-52 / #3216)。
 * 呼出規約は tools/shared/lift/rex/rex_glue.c と同じ (ms_abi: rcx/rdx/r8/r9)。
 * import スタブは wc_native_ref.c と同じ規約 (同じ bump heap・同じ戻り値・同じ呼出回数の数え方)。 */
#include "fle_cpu.h"
#include "wc_layout.h"

static uint8_t guest_stack[1 << 16] __attribute__((aligned(16)));
#define STACK_TOP ((uint64_t)(uintptr_t)guest_stack + sizeof(guest_stack) - 0x100)
static uint64_t wc_hits, wc_heap_top;
static uint8_t wc_covb[512];

void wc_cov(uint32_t i) { wc_covb[i] = 1; }
uint32_t wc_cov_get(uint32_t i) { return wc_covb[i]; }

#define STUB_RET(v) do { R[RAX] = (uint64_t)(v); R[RSP] += 8; wc_hits++; } while (0)

/* a4 は 5 番目の引数 (ms_abi で [rsp+0x28] = STACK_TOP+0x20 に置く)。wc_run5 だけが使う (#4302)。 */
uint64_t wc_run5(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t a4) {
    R[RSP] = STACK_TOP;
    ST64(STACK_TOP + 0x20, a4);
    R[RCX] = a0; R[RDX] = a1; R[R8] = a2; R[R9] = a3;
    R[RAX] = 0xFEEDFACE5EED0000ULL;
    R[RSP] -= 8; ST64(R[RSP], 0xdead0000ull);
    ott_dispatch(va);
    return R[RAX];
}

uint64_t wc_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3) {
    return wc_run5(va, a0, a1, a2, a3, 0);
}

void wc_reset(void) {
    memset(R, 0, sizeof(R)); memset(X, 0, sizeof(X)); memset(YL, 0, sizeof(YL));
    memset(M, 0, sizeof(M));
    fZF = fSF = fCF = fOF = fPF = fAF = fDF = 0;
    x87_cw = 0x037f; x87_sw = 0; mxcsr = 0x1f80;
    fle_install_teb();
    wc_hits = 0;
    memset(wc_covb, 0, sizeof wc_covb);
    wc_heap_top = WC_ARENA;
}

uint64_t wc_hits_get(void) { return wc_hits; }

#ifdef WC_HEAP_LOG
/* 診断 (WC_HEAP_LOG=1 でビルドし、wc_log_set(1) で有効化): native 側 (wc_native_ref.c) と同形式の [heap] 行を出す (#5162)。 */
static int wc_logon, wc_heap_n, wc_tag;
void wc_log_set(int on, int tag) { wc_logon = on; wc_tag = tag; wc_heap_n = 0; }
#else
void wc_log_set(int on, int tag) { (void)on; (void)tag; }
#endif

void imp_HeapAlloc(void) {
#ifdef WC_HEAP_LOG
    if (wc_logon) {
        fprintf(stderr, "[heap] tag=%d n=%d sz=%llu ret=%llx g3f5b80=%x\n", wc_tag, wc_heap_n, (unsigned long long)R[R8],
                (unsigned long long)(LD64(R[RSP]) - WC_BASE), (unsigned)(LD64(WC_BASE + 0x3f5b80) & 0xffffffffu));
        for (int i = 0; i < 64; i++) {
            uint64_t v = LD64(R[RSP] + i * 8);
            if (v >= WC_BASE && v < WC_BASE + WC_IMG_SIZE) fprintf(stderr, "[stk] tag=%d n=%d +%d %llx\n", wc_tag, wc_heap_n, i * 8, (unsigned long long)(v - WC_BASE));
        }
    }
    wc_heap_n++;
#endif
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
/* 据え置き (T-SH-154 #5789): CreateInstance 側 (ci_iat.c) の停止規約とは統一しない。WaveformColouring の既存の測定値を変えないため。 */
void imp_RaiseException(void) { STUB_RET(0); }
void imp_RtlCaptureContext(void) { STUB_RET(0); }
void imp_RtlLookupFunctionEntry(void) { STUB_RET(0); }
void imp_RtlPcToFileHeader(void) { STUB_RET(0); }
void imp_RtlVirtualUnwind(void) { STUB_RET(0); }
void imp_SetUnhandledExceptionFilter(void) { STUB_RET(0); }
void imp_UnhandledExceptionFilter(void) { STUB_RET(0); }
void imp_TerminateProcess(void) { STUB_RET(0); }
