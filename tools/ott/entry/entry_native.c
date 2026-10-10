/* entry_native.c — CAB-137: VST 入口関数群の native (実機械語) 参照ハーネス。
 *
 * tools/ott/native/ott_native.c (PE 敷設 + IAT + ms_call trampoline) を **無改変で include** し、
 * VST 入口駆動に必要な最小の追加だけを持つ:
 *   - am_native: audioMaster callback (MS x64 ABI)。ロジックは am_host.h 共有 (wasm 側と同一)。
 *   - ott_am_addr / ott_am_counts: VSTPluginMain に渡す fn ポインタと呼出回数表の公開。
 *
 * 使い方 (entry_e2e.sh / entry_nat.py): 共有ライブラリとしてビルドし ctypes から ott_call を叩く。
 * 注意: 実行は ASLR 固定 (setarch -R) 前提 — ottnat/entry_nat.py が再 exec する。
 */
#define _GNU_SOURCE
/* オリジナルの参照ローダ (PE 敷設 / IAT / ott_call / coverage) をそのまま取り込む */
#include "../native/ott_native.c"
#include "am_host.h"

/* plugin → host upcall: MS x64 ABI で DLL 機械語から直接呼ばれる。
 * 引数は dispatcher 同様の 6 引数形: (eff, op, idx, value, ptr, opt)。
 * opt は第 6 位置引数 = スタック ([rsp+0x30] に載ってくる) — MS ABI では float の 5+ 引数は
 * レジスタ (xmm) でなくスタック渡しになる点に注意。 */
static MS uint64_t am_native(void* eff, int32_t op, int32_t idx, int64_t val, void* ptr, float opt) {
    (void)eff;
    return (uint64_t)am_logic(op, idx, val, (uint64_t)(uintptr_t)ptr, opt);
}

/* VSTPluginMain(audioMaster) に渡す fn ポインタ */
uint64_t ott_am_addr(void) { return (uint64_t)(uintptr_t)am_native; }
/* 呼出回数表 (op 64 個) */
uint32_t* ott_am_counts(void) { return am_counts_ptr(); }
