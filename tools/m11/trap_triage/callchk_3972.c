/* callchk_3972.c (#3972): callchk_3972.py が各 call の直後に入れる m11_callchk(site) の受け側.
 * 監視番地 WATCH_ADDR の 8 バイトを前回の call からの値と比べ、変わったら site を stderr に出す。
 * 監視 OFF (m11_watch_on(0)) の間は何もしない。値の比較は読み取りだけ。 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#ifndef M11_WATCH_ADDR_OVR
#define M11_WATCH_ADDR_OVR 0x10aa1428u
#endif
extern int m11_watch_on_state(void);
static unsigned char prev[8];
static int primed = 0;
static unsigned long long n_chg = 0;
void m11_callchk(unsigned site) {
    if (!m11_watch_on_state()) return;
    unsigned char *p = (unsigned char *)(uintptr_t)M11_WATCH_ADDR_OVR;
    if (!primed) { memcpy(prev, p, 8); primed = 1; return; }
    if (memcmp(prev, p, 8) == 0) return;
    /* "he.d" (UTF-16LE 0x64002e00650068) の 8 バイトが現れたかを別に示す (#3972 の探索対象) */
    if (p[0] == 0x68 && p[1] == 0x00 && p[2] == 0x65 && p[3] == 0x00 && p[4] == 0x2e && p[5] == 0x00 && p[6] == 0x64 && p[7] == 0x00)
        fprintf(stderr, "[cc-he.d] site=%u\n", site);
    n_chg++;
    fprintf(stderr, "[cc] site=%u hit=%llu old=%02x%02x%02x%02x%02x%02x%02x%02x new=%02x%02x%02x%02x%02x%02x%02x%02x\n",
            site, n_chg,
            prev[0], prev[1], prev[2], prev[3], prev[4], prev[5], prev[6], prev[7],
            p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]);
    memcpy(prev, p, 8);
}
