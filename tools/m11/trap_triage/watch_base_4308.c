/* watch_base_4308.c (#4308): watch_store_682.py が store の直後に入れる m11_sw (監視は読取りのみ).
 * g = [0x11f5fc0] (6cefb0 が読む構造体へのポインタ) を毎回読み, [g+8, g+20) = base (i64) と cnt (i32) への書込みを出す.
 * 判定は store の範囲 [addr, addr+width) と重なるかで行う. 出力の site は sites.json で fn・IR 行に戻す. */
#include <stdio.h>
#include <stdint.h>
typedef unsigned int u32;
typedef unsigned long long u64;
static u64 n_hit = 0;
#define LOG_MAX 4000
void m11_sw(u32 addr, u32 val, u32 site, u32 width) {
    u32 g = *(volatile u32*)(uintptr_t)0x11f5fc0u;
    if (!g) return;
    u32 w = g + 8;
    if (addr + width <= w || addr >= w + 12) return;
    n_hit++;
    if (n_hit <= LOG_MAX)
        fprintf(stderr, "[wb] site=%u addr=%x g=%x val=%x width=%u hit=%llu\n", site, addr, g, val, width, n_hit);
}
