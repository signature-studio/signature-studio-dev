#include <stdint.h>
#include <stdlib.h>
#include <string.h>

extern unsigned char __icall_blk[0x200];
extern void __icall_dispatch(uint64_t site);

void probe_dispatch(uint64_t target, uint64_t site) {
    uint64_t *b = (uint64_t *)__icall_blk;
    unsigned char *buf = malloc(64);
    memset(buf, 0, 64);
    memset(__icall_blk, 0, 0x200);
    b[0] = target;
    b[2] = 19;
    b[3] = (uint64_t)(uintptr_t)buf;
    __icall_dispatch(site);
    free(buf);
}
