/* ci_iat.c: ildsp CreateInstance closure の IAT 10 種の stub (T-SH-151 #5747)。
 * 規約は REPORT_APPENDIX_3276.md と同じ: HeapAlloc は calloc、RtlPcToFileHeader は ImageBase、
 * RaiseException は記録して停止 (非 0 終了)、それ以外は 0 を返して呼出し回数を数える。
 * 引数と戻り値の型は ci.rs.ll の declare に合わせる (i64* は wasm32 では pointer)。 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

enum { CI_GetLastError, CI_SetLastError, CI_EnterCriticalSection, CI_LeaveCriticalSection,
       CI_HeapAlloc, CI_HeapFree, CI_FlsGetValue, CI_FlsSetValue, CI_RaiseException,
       CI_RtlPcToFileHeader, CI_N };

static uint64_t ci_iat_n[CI_N];
uint64_t ci_iat_count(int i) { return ci_iat_n[i]; }

/* ImageBase は画像敷設 (T-SH-152 #5748) が設定する。未設定の間は NULL。 */
void *ci_image_base;
void ci_iat_set_image_base(void *b) { ci_image_base = b; }

int32_t GetLastError(void) { ci_iat_n[CI_GetLastError]++; return 0; }
void SetLastError(int32_t e) { (void)e; ci_iat_n[CI_SetLastError]++; }
void EnterCriticalSection(void *cs) { (void)cs; ci_iat_n[CI_EnterCriticalSection]++; }
void LeaveCriticalSection(void *cs) { (void)cs; ci_iat_n[CI_LeaveCriticalSection]++; }
void *HeapAlloc(void *heap, uint32_t flags, uint32_t n) {
    (void)heap; (void)flags; ci_iat_n[CI_HeapAlloc]++;
    return calloc(1, n);
}
int HeapFree(void *heap, uint32_t flags, void *p) { (void)heap; (void)flags; (void)p; ci_iat_n[CI_HeapFree]++; return 0; }
void *FlsGetValue(uint32_t idx) { (void)idx; ci_iat_n[CI_FlsGetValue]++; return 0; }
int FlsSetValue(uint32_t idx, void *v) { (void)idx; (void)v; ci_iat_n[CI_FlsSetValue]++; return 0; }
void RaiseException(uint32_t code, uint32_t flags, uint32_t nargs, uint32_t *args) {
    (void)flags; (void)nargs; (void)args;
    ci_iat_n[CI_RaiseException]++;
    fprintf(stderr, "[ci] RaiseException code=0x%08x: stop\n", code);
    exit(3);
}
void *RtlPcToFileHeader(void *pc, void **base) {
    (void)pc; ci_iat_n[CI_RtlPcToFileHeader]++;
    if (base) *base = ci_image_base;
    return ci_image_base;
}
