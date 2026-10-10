/* hs_dbg_tr.c — CAB-195 デバッグ用: fw_dbg_enter (wasm 内の関数入口 call trace).
 * fw_table.c の dispatch trace ([dispatch] site=.. -> target=..) は **間接** 呼出しか
 * 追えないため, IR 上の direct call 連鎖 (0x6bdde0 → 0x6bd210 → 0x6bd150 → RTL) は
 * 本 trace で追う。0x6bdde0 を観測したら記録開始 (Phase A とは別 module なので無干渉)。
 *
 * 追加 (CAB-195 §デバッグ 2): 0x40e800 系の「RetDec 定数折畳みで rsi=&stack slot が
 * `@50` ("$") になり load が linear memory 先頭を叩く」破れを観測するため,
 * fw_dbg_fold(addr, want) で cell 内容を上書きできる (hostshim の fold cell と同原理)。
 */
#include <stdint.h>
#include <stdio.h>

int g_fw_dbg_on = 0;
unsigned long long g_fw_dbg_n = 0;
uint64_t g_dbg_fold_addr = 0, g_dbg_fold_val = 0;

void fw_dbg_enter(uint32_t va) {
    if (va == 0x6bdde0u) { g_fw_dbg_on = 1; g_fw_dbg_n = 0; }
    if (!g_fw_dbg_on) return;
    if (g_fw_dbg_n < 40000u) {
        g_fw_dbg_n++;
        fprintf(stderr, "[dbg] -> 0x%x\n", va);
    }
}

void fw_dbg_fold(uint64_t addr, uint64_t val) {
    g_dbg_fold_addr = addr;
    g_dbg_fold_val = val;
}

uint64_t fw_dbg_fold_read(uint64_t addr) {
    if (addr == g_dbg_fold_addr) return g_dbg_fold_val;
    return *(volatile uint64_t *)(uintptr_t)addr;
}
