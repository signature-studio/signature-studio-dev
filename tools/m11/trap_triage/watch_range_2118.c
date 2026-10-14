/* watch_range_2118.c (#2118 / M11-N139): watch_store_682.py が全 store の直後に入れる m11_sw の範囲版.
 * 監視範囲 [M11_WATCH_LO, M11_WATCH_HI) と store の範囲 [addr, addr+width) が重なる書込みを stderr に出す:
 *   `[rw] site=<id> addr=<書込み先> val=<書込み後の値> width=<幅> hit=<通算>`
 * site は sites.json で fn・IR 行に戻す。監視は読取りのみ (IR の値・分岐は不変)。 */
#include <stdio.h>
#include <stdint.h>
typedef unsigned int u32;
typedef unsigned long long u64;
#ifndef M11_WATCH_LO
#define M11_WATCH_LO 0xfa5108u
#endif
#ifndef M11_WATCH_HI
#define M11_WATCH_HI 0xfa5c68u
#endif
static u64 n_hit = 0;
#define LOG_MAX 20000
void m11_sw(u32 addr, u32 val, u32 site, u32 width) {
    if (addr + width <= M11_WATCH_LO || addr >= M11_WATCH_HI) return;
    n_hit++;
    if (n_hit <= LOG_MAX)
        fprintf(stderr, "[rw] site=%u addr=%x val=%x width=%u hit=%llu\n", site, addr, val, width, n_hit);
}
