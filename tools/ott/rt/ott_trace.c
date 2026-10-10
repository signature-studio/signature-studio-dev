/* ott_trace.c: IR 関数 entry hook (passes/trace_entry.py が各 define 先頭に挿入)。
 * ログ: 0x34000000 に {u32 count, u32 enable, u32 cap, u32 pad} + record{u64 va, a0..a3}。
 * enable は JS 側が HEAPU32[0x34000004/4] で切替。 */
#include <stdint.h>
#define TR_HDR ((volatile uint32_t*)0x34000000)
#define TR_CAP 400000u
void ott_trace(uint64_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3) {
    if (!TR_HDR[1]) return;
    uint32_t c = TR_HDR[0];
    if (c >= TR_CAP) return;
    volatile uint64_t* r = (volatile uint64_t*)(0x34000010ull + (uint64_t)c * 40);
    r[0] = va; r[1] = a0; r[2] = a1; r[3] = a2; r[4] = a3;
    TR_HDR[0] = c + 1;
}
