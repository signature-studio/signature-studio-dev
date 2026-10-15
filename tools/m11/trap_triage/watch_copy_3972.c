/* watch_copy_3972.c (#3972): function_409c80 (copy) の入口で dst が [WA, WA+32) と重なるときだけ `[cp]` を出す。
 * copy は `store i128` (__asm_movups) で書くため store 計装 (watch_addr_2408.c) に映らない。
 * copy_watch_3972.py が入口に m11_copy_in(dst, src, n) を入れる。監視 ON/OFF は m11_watch_on (watch_addr_2408.c) に従う。 */
#include <stdio.h>
typedef unsigned long long u64;
#ifndef M11_WATCH_ADDR_OVR
#define M11_WATCH_ADDR_OVR 0x10aa1428u
#endif
extern int m11_watch_on_state(void);
#ifndef M11_CP_ALL
#define M11_CP_ALL 0
#endif
static const int cp_all = M11_CP_ALL;
void m11_copy_in(u64 dst, u64 src, u64 n) {
    if (!m11_watch_on_state()) return;
    u64 lo = M11_WATCH_ADDR_OVR, hi = lo + 32;
    if (!cp_all && (dst + n <= lo || dst >= hi)) return;
    fprintf(stderr, "[cp] dst=%llx src=%llx n=%llu%s\n", dst, src, n, (dst + n <= lo || dst >= hi) ? " (no-overlap)" : "");
}
