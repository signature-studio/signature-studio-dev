/* watch_store_682.c (#682): watch_store_682.py が全 store の直後に入れる m11_sw (監視は読取りのみ).
 * [esc]  : 値が shadow stack の範囲 (emscripten_stack_get_end..get_base) を指す store で, 書込み先が stack の外のもの
 *          = stack の番地が heap / 静的領域へ逃げた書込み. 範囲判定は実行時の stack 位置に従うので配置非依存.
 * [sw]   : 監視番地 w = [[g+8]+8] (g = [0x11f26a0]) の 8B 範囲に掛かる store (g・T の時点の値で判定).
 * 出力の site は sites.json で fn・IR 行に戻す. unit 境界は `unit N` 行 (SV_PROG). */
#include <stdio.h>
#include <stdint.h>
#include <emscripten/stack.h>
typedef unsigned int u32;
typedef unsigned long long u64;
static u64 n_esc = 0, n_hit = 0;
static u32 w_last = 0, v_last = 0xdeadbeefu;
#define LOG_MAX 4000
void m11_sw(u32 addr, u32 val, u32 site) {
    u32 lo = (u32)(uintptr_t)emscripten_stack_get_end(), hi = (u32)(uintptr_t)emscripten_stack_get_base();
    if (val >= lo && val < hi && !(addr >= lo && addr < hi)) {
        n_esc++;
        if (n_esc <= LOG_MAX) fprintf(stderr, "[esc] site=%u addr=%x val=%x esc=%llu\n", site, addr, val, n_esc);
    }
    u32 g = *(volatile u32*)(uintptr_t)0x11f26a0u;
    if (!g) return;
    u32 t = *(volatile u32*)(uintptr_t)(g + 8);
    if (!t) return;
    u32 w = t + 8;
    if (addr + 8 <= w || addr >= w + 8) return;
    u32 v = *(volatile u32*)(uintptr_t)w;
    n_hit++;
    if (n_hit <= LOG_MAX)
        fprintf(stderr, "[sw] site=%u addr=%x w=%x val=%x hit=%llu%s\n", site, addr, w, v, n_hit, (v != v_last || w != w_last) ? " CHG" : "");
    w_last = w; v_last = v;
}
