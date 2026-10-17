/* watch_g_ctrl_4308.c (#4308): watch_base_4308.c の陽性対照. 監視番地を g 本体 0x11f5fc0 (4B) に替えた同じ m11_sw.
 * store の範囲 [addr, addr+width) が [0x11f5fc0, +4) と重なる書込みを [wb] で出す. 陽性 (1 件以上) なら計装は g 本体への書込みを拾える. */
#include <stdio.h>
#include <stdint.h>
typedef unsigned int u32;
typedef unsigned long long u64;
static u64 n_hit = 0;
#define LOG_MAX 4000
void m11_sw(u32 addr, u32 val, u32 site, u32 width) {
    u32 w = 0x11f5fc0u;
    if (addr + width <= w || addr >= w + 4) return;
    n_hit++;
    if (n_hit <= LOG_MAX)
        fprintf(stderr, "[wb] site=%u addr=%x val=%x width=%u hit=%llu\n", site, addr, val, width, n_hit);
}
