/* edge_3972.c (#3972): edge_3972.py が関数の入口・ret 直前に入れる m11_eprobe(id, site) の受け側.
 * 監視 ON の間だけ、監視番地 WATCH_ADDR の現在値 (8 バイト) を stderr に出す。読み取りだけ。
 * 値が前回の出力と変わったときだけ出す (変化点の site を拾う)。 */
#include <stdio.h>
#include <stdint.h>
#ifndef M11_WATCH_ADDR_OVR
#define M11_WATCH_ADDR_OVR 0x10aa1428u
#endif
extern int m11_watch_on_state(void);
static unsigned long long last = 0, n_chg = 0, n_all = 0;
void m11_eprobe(unsigned id, unsigned site) {
    if (!m11_watch_on_state()) return;
    unsigned char *p = (unsigned char *)(uintptr_t)M11_WATCH_ADDR_OVR;
    unsigned long long v = 0;
    for (int k = 7; k >= 0; k--) v = (v << 8) | p[k];
    n_all++;
    if (v == last) return;
    n_chg++;
    fprintf(stderr, "[ep] n=%llu id=%u site=%u old=%016llx new=%016llx\n", n_chg, id, site, last, v);
    last = v;
}
