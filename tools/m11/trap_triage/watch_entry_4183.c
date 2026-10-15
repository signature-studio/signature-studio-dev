/* watch_entry_4183.c (#4183): entry_obj_4183.py が入れた関数入口の m11_entry(第1引数, site) を stderr に出す.
 * 監視 ON (m11_watch_on(1)) の間だけ出力する。出力: `[ob] site=<id> val=<値> hit=<通算>`. */
#include <stdio.h>
#include <stdint.h>
typedef unsigned long long u64;
typedef unsigned int u32;
static u64 n_ob = 0;
static int ob_on = 0;
void m11_watch_on(int on) { ob_on = on; }
__attribute__((noinline)) void m11_entry(u64 val, u32 site) {
    if (!ob_on) return;
    n_ob++;
    fprintf(stderr, "[ob] site=%u val=%llx hit=%llu\n", site, val, n_ob);
}
