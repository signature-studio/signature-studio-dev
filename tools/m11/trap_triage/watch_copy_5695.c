/* watch_copy_5695.c (#5695): copy (409c80) と rep 系 helper の入口で、宛先が e3ef60 の arg1 (0x12ba808) の監視範囲と重なるときだけ出す.
 * 監視範囲 [M11_WATCH_LO, M11_WATCH_HI) は watch_arg1_5695.c と同じ (+0x778〜+0x814)。
 * copy_watch_3972.py / rep_watch_3972.py が入れる入口 (m11_copy_in / m11_rep_in) の範囲版。監視は読取りのみ。 */
#include <stdio.h>
typedef unsigned long long u64;
#ifndef M11_WATCH_LO
#define M11_WATCH_LO 0x12ba808ull + 0x778ull
#endif
#ifndef M11_WATCH_HI
#define M11_WATCH_HI 0x12ba808ull + 0x814ull
#endif
static u64 n_cp = 0, n_rp = 0;
void m11_copy_in(u64 dst, u64 src, u64 n) {
    if (n > (1ull << 40)) return;
    if (dst + n <= (u64)(M11_WATCH_LO) || dst >= (u64)(M11_WATCH_HI)) return;
    n_cp++;
    if (n_cp <= 2000)
        fprintf(stderr, "[a1cp] dst=%llx src=%llx n=%llu hit=%llu\n", dst, src, n, n_cp);
}
void m11_rep_in(u64 dst, u64 bytes, u64 site) {
    if (bytes > (1ull << 40)) return;
    if (dst + bytes <= (u64)(M11_WATCH_LO) || dst >= (u64)(M11_WATCH_HI)) return;
    n_rp++;
    if (n_rp <= 2000)
        fprintf(stderr, "[a1rp] site=%llu dst=%llx bytes=%llu hit=%llu\n", site, dst, bytes, n_rp);
}
