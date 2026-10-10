/* pcfuzz2.c — PCMPISTRI 0x40 の実機意味の確定 v2 (needle = movd 形 la<=2 前提 + 一般) */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static uint32_t model(const unsigned char* a, const unsigned char* b, uint8_t* zf, uint8_t* cf, uint8_t* sf, uint8_t* of) {
    int la = 16, lb = 16;
    for (int i = 0; i < 16; i++) if (a[i] == 0) { la = i; break; }
    for (int i = 0; i < 16; i++) if (b[i] == 0) { lb = i; break; }
    uint32_t mask = 0;
    for (int j = 0; j < lb; j++)
        for (int i = 0; i < la; i++)
            if (a[i] == b[j]) { mask |= 1u << j; break; }
    *zf = (lb < 16); *cf = (mask != 0); *sf = (la < 16); *of = (mask & 1);
    return mask ? (31u - (uint32_t)__builtin_clz(mask)) : 16;
}
static uint64_t s; static uint64_t nx(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s; }
static void hw(const unsigned char* a, const unsigned char* b, uint32_t* ix, uint64_t* fl) {
    __asm__ volatile("movdqu (%[pa]), %%xmm0\n\tmovdqu (%[pb]), %%xmm1\n\t"
        "pcmpistri $0x40, %%xmm1, %%xmm0\n\tpushfq\n\tpopq %[fl]\n\tmovl %%ecx, %[ix]\n\t"
        : [fl] "=r"(*fl), [ix] "=r"(*ix) : [pa] "r"(a), [pb] "r"(b) : "xmm0", "xmm1", "ecx", "cc");
}
int main(int argc, char** argv) {
    long n = (argc > 1) ? atol(argv[1]) : 200000;
    s = (argc > 2) ? strtoull(argv[2], 0, 10) : 4242;
    long bad = 0;
    unsigned char a[16], b[16];
    for (long t = 0; t < n; t++) {
        int mode = t % 3;
        memset(a, 0xcc, 16); memset(b, 0xdd, 16);
        if (mode == 0) { /* movd needle: byte0 = char, rest 0 */
            a[0] = nx(); memset(a + 1, 0, 15);
        } else if (mode == 1) { /* 2byte needle + EOS */
            a[0] = nx(); a[1] = nx(); memset(a + 2, 0, 14);
        } else { /* general random with EOS */
            for (int k = 0; k < 16; k++) { unsigned v = nx() & 0xff; if ((nx() % 4) == 0) v = 0; a[k] = v; }
        }
        for (int k = 0; k < 16; k++) { unsigned v = nx() & 0xff; if ((nx() % 4) == 0) v = 0; b[k] = v; }
        uint32_t hi, mi; uint64_t fl;
        hw(a, b, &hi, &fl);
        uint8_t hz = (fl >> 6) & 1, hc = fl & 1, hs = (fl >> 7) & 1, ho = (fl >> 11) & 1;
        uint8_t mz, mc, ms, mo;
        mi = model(a, b, &mz, &mc, &ms, &mo);
        if (hi != mi || hz != mz || hc != mc || hs != ms || ho != mo) {
            if (bad < 8) fprintf(stderr, "mismatch t=%ld a=%16ph b=%16ph hw=%u,%u%u%u%u model=%u,%u%u%u%u\n",
                t, a, b, hi, hz, hc, hs, ho, mi, mz, mc, ms, mo);
            bad++;
        }
    }
    fprintf(stderr, "[pcfuzz2] %s (%ld cases, mode0=movd needle / mode1=2byte / mode2=general)\n", bad ? "MISMATCH" : "model == hw", n);
    return bad != 0;
}
