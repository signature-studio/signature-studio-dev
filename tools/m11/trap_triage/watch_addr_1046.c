/* watch_addr_1046.c (#1046): watch_store_682.py が全 store の直後に入れる m11_sw の固定アドレス版.
 * 監視番地 W (定数 M11_WATCH_ADDR) の 4B 範囲 [W, W+4) と store の範囲 [addr, addr+width) が重なる書込みを
 * stderr に出す: `[aw] site=<id> addr=<書込み先> val=<書込み後の値 (val は store の値)> hit=<通算>`.
 * site は sites.json で fn・IR 行に戻す。監視は読取りのみ (IR の値・分岐は不変). */
#include <stdio.h>
#include <stdint.h>
typedef unsigned int u32;
typedef unsigned long long u64;
#ifndef M11_WATCH_ADDR
#define M11_WATCH_ADDR 0x10a9f910u
#endif
static u64 n_hit = 0;
#define LOG_MAX 4000
void m11_sw(u32 addr, u32 val, u32 site, u32 width) {
    u32 w = M11_WATCH_ADDR;
    if (addr + width <= w || addr >= w + 8) return;
    n_hit++;
    if (n_hit <= LOG_MAX)
        fprintf(stderr, "[aw] site=%u addr=%x val=%x width=%u hit=%llu\n", site, addr, val, width, n_hit);
}
