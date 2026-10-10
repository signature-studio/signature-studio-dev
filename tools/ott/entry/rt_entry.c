/* rt_entry.c — CAB-137: 入口 lift 版 wasm runtime の追加部 (override body + JS 向け export)。
 *
 * x64c.py の --override は「その VA の関数 body を C 実装に置換」する (f_<va> = { CNAME(); })。
 * override body は lifted ABI (CPU 状態 R/X) で動き、**末尾で ret 相当 R[RSP] += 8 を実行**する
 * こと (tools/ott/rt/ott_ovr.c の規約)。ここでは 2 つを置く:
 *
 *   ovr_editor_null (0x180120ff0):
 *     OTTEditor ctor を「NULL を返す」置換にする (GUI 対象外の surrogate)。
 *     native 側は同一箇所を `xor eax,eax; ret` (3 byte) に機械語 patch して同じ意味にする
 *     (entry_nat.py / native ハーネス)。createEffectInstance は editor=NULL を obj+0x10 に保存し、
 *     setParameter override や effEdit* は editor NULL 経路 (=0 を返す) に落ちる。双方一致。
 *
 *   ovr_am_shim (0x1802f8000):
 *     audioMaster 仮想入口。VSTPluginMain は host から貰った fn ポインタを `call rbx` で呼ぶ。
 *     native は実 fn ポインタ、wasm は ott_dispatch で解決できる **trampoline VA (0x2f8000)** を
 *     代わりに渡す。override body が MS x64 ABI の引数置き場 (R[RCX..R9] / [RSP+0x28] / [RSP+0x30])
 *     から読んで am_logic (am_host.h, native と共有) を実行し、RAX に戻す。
 */
#include "ott_cpu.h"
#include "am_host.h"

#define RET() (R[RSP] += 8)

void ovr_editor_null(void) {
    R[RAX] = 0;
    RET();
}

void ovr_am_shim(void) {
    int32_t op = (int32_t)R[RDX];
    int32_t idx = (int32_t)R[R8];
    int64_t val = (int64_t)R[R9];
    uint64_t ptr = LD64(R[RSP] + 0x28);          /* 第 5 位置引数 (スタック) */
    float opt = LDF32(R[RSP] + 0x30);            /* 第 6 位置引数 (スタック, float) */
    R[RAX] = (uint64_t)am_logic(op, idx, val, ptr, opt);
    RET();
}

/* 呼出回数表の先頭アドレス (JS から HEAPU32 で読む) */
uint32_t* ott_am_counts(void) { return am_counts_ptr(); }
