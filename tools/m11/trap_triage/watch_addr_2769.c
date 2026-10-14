/* watch_addr_2769.c (#2769): watch_addr_1046.c と同じ監視 (番地 W の 4B 範囲と重なる store を `[aw] site=...` で出す) に,
 * site ごとの呼出し回数の上限 (M11_SW_LIMIT) を足したもの. 上限を超えた site は `[sw-limit] site=<id> n=<回数>` を出し,
 * wasm trap (__builtin_trap) で現在の unit だけを打ち切る (survey_units.mjs は unit ごとに例外を捕まえて続行する).
 * 監視は読取り + 計数のみ (IR の値・分岐は不変). 上限に達した後は計数を 0 に戻すので, 同じ site は上限ごとに 1 回 trap する. */
#include <stdio.h>
#include <stdint.h>
typedef unsigned int u32;
typedef unsigned long long u64;
#ifndef M11_WATCH_ADDR
#define M11_WATCH_ADDR 0x1ac308u
#endif
#ifndef M11_SW_LIMIT
#define M11_SW_LIMIT 5000000u
#endif
#define SITE_MAX 60000
static u64 n_hit = 0;
static u32 site_n[SITE_MAX];
#define LOG_MAX 4000
void m11_sw(u32 addr, u32 val, u32 site, u32 width) {
    u32 w = M11_WATCH_ADDR;
    if (!(addr + width <= w || addr >= w + 8)) {
        n_hit++;
        if (n_hit <= LOG_MAX)
            fprintf(stderr, "[aw] site=%u addr=%x val=%x width=%u hit=%llu\n", site, addr, val, width, n_hit);
    }
    if (site < SITE_MAX && ++site_n[site] > M11_SW_LIMIT) {
        fprintf(stderr, "[sw-limit] site=%u n=%u\n", site, site_n[site]);
        site_n[site] = 0;
        __builtin_trap();
    }
}
