/* watch_addr_2099.c (#2099 copy): watch_addr_1046.c の unit 範囲つき版. 監視の ON/OFF は m11_watch_on(flag) で切る
 * (store_watch_1046b.sh が unit 境界で呼ぶ。既定 OFF)。監視は読取りのみ (IR の値・分岐は不変). */
#include <stdio.h>
#include <stdint.h>
typedef unsigned int u32;
typedef unsigned long long u64;
#ifndef M11_WATCH_ADDR_OVR
#define M11_WATCH_ADDR_OVR 0x10bd4c20u
#endif
#define M11_WATCH_ADDR M11_WATCH_ADDR_OVR
static u64 n_hit = 0;
static int watch_on = 0;
void m11_watch_on(int on) { watch_on = on; }
void m11_sw(u32 addr, u32 val, u32 site, u32 width) {
    u32 w = M11_WATCH_ADDR;
    if (!watch_on) return;
    if (addr + width <= w || addr >= w + 32) return;
    n_hit++;
    fprintf(stderr, "[aw] site=%u addr=%x val=%x width=%u hit=%llu\n", site, addr, val, width, n_hit);
}
