/* watch_addr_2408.c (#2408): watch_addr_2099.c の fast path 版. 監視 OFF / 範囲外の呼出しでは C の線形スタックに何も書かない
 * (-O2 でコンパイルし, 出力は noinline の sw_hit に分ける). -O0 の m11_sw は引数を自分のフレームへ退避するため,
 * 全 store に call を入れると IR の未初期化 alloca が読むスタック残骸を上書きして挙動を変える (REPORT_1676 §14). */
#include <stdio.h>
#include <stdint.h>
typedef unsigned int u32;
typedef unsigned long long u64;
#ifndef M11_WATCH_ADDR_OVR
#define M11_WATCH_ADDR_OVR 0x10bd4c20u
#endif
static u64 n_hit = 0;
static int watch_on = 0;
void m11_watch_on(int on) { watch_on = on; }
__attribute__((noinline)) static void sw_hit(u32 addr, u32 val, u32 site, u32 width) {
    n_hit++;
    fprintf(stderr, "[aw] site=%u addr=%x val=%x width=%u hit=%llu\n", site, addr, val, width, n_hit);
}
void m11_sw(u32 addr, u32 val, u32 site, u32 width) {
    if (!watch_on) return;
    if (addr + width <= M11_WATCH_ADDR_OVR || addr >= M11_WATCH_ADDR_OVR + 32) return;
    sw_hit(addr, val, site, width);
}
