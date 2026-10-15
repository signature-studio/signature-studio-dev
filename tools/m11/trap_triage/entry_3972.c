/* entry_3972.c (#3972): entry_3972.py が関数入口に入れる m11_wprobe(id, a1, a2, a3) の受け側.
 * 監視 ON の間だけ、引数と監視番地 WATCH_ADDR の現在値 (8 バイト) を stderr に出す。読み取りだけ。 */
#include <stdio.h>
#include <stdint.h>
#ifndef M11_WATCH_ADDR_OVR
#define M11_WATCH_ADDR_OVR 0x10aa1428u
#endif
extern int m11_watch_on_state(void);
static unsigned long long n_in = 0;
void m11_wprobe(unsigned id, unsigned long long a1, unsigned long long a2, unsigned long long a3) {
    if (!m11_watch_on_state()) return;
    unsigned char *p = (unsigned char *)(uintptr_t)M11_WATCH_ADDR_OVR;
    n_in++;
    fprintf(stderr, "[wp] id=%u n=%llu a1=%llx a2=%llx a3=%llx watch=%02x%02x%02x%02x%02x%02x%02x%02x\n",
            id, n_in, a1, a2, a3, p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]);
}
