/* rex_glue.c: REX 最小閉包 (REXGetCreatorInfo / REXGetInfo) の wasm 側入口。fle_cpu.c (flelift runtime) の上に載る。
 * native_ref.c と同じ入力規約・同じ import スタブ (成功を返す) で、戻り値 RAX と import 呼出回数を返す。
 * guest 補助 (TEB 等) は fle_cpu.c の FLE_* 定数 (0x1D00000 付近) を使う。 */
#include "fle_cpu.h"

static uint8_t guest_stack[1 << 16] __attribute__((aligned(16)));
#define STACK_TOP ((uint64_t)(uintptr_t)guest_stack + sizeof(guest_stack) - 0x100)
static uint64_t rex_hits;

uint64_t rex_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3) {
    R[RSP] = STACK_TOP;
    R[RCX] = a0; R[RDX] = a1; R[R8] = a2; R[R9] = a3;
    R[RAX] = 0xFEEDFACE5EED0000ULL;
    R[RSP] -= 8; ST64(R[RSP], 0xdead0000ull);
    ott_dispatch(va);
    return R[RAX];
}

void rex_reset(void) {
    memset(R, 0, sizeof(R)); memset(X, 0, sizeof(X)); memset(YL, 0, sizeof(YL));
    memset(M, 0, sizeof(M));
    fZF = fSF = fCF = fOF = fPF = fAF = fDF = 0;
    x87_cw = 0x037f; x87_sw = 0; mxcsr = 0x1f80;
    fle_install_teb();
    rex_hits = 0;
}

uint64_t rex_hits_get(void) { return rex_hits; }

void imp_WaitForSingleObject(void) { rex_hits++; R[RAX] = 0; R[RSP] += 8; }
void imp_ReleaseMutex(void) { rex_hits++; R[RAX] = 1; R[RSP] += 8; }
void imp_RtlPcToFileHeader(void) { rex_hits++; R[RAX] = 0; R[RSP] += 8; }
