/* pcfuzz.c — CAB-135: PCMPISTRI control 0x40 の実機意味の確定 (index + ZF/CF)。
 * 実機 (inline asm) vs モデル (ott_cpu.h の ott_pcmpistri40 と同一定義をここに複製して比較)。
 * usage: pcfuzz <ncases> <seed> → stdout に "idx zf cf" 行列、モデル不一致は stderr。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static uint32_t model_idx(const uint8_t* a, const uint8_t* b, uint8_t* zf, uint8_t* cf) {
    /* control 0x40: byte / equal-each / positive / implicit length (EOS scan)。
     * 実機実測 (pcfuzz): mask[i] = (i<la && i<lb && a[i]==b[i]); idx = 最初の一致 (LSB, 無ければ 16);
     * CF = mask != 0 (一致あり); ZF = EOS が第 2 operand (b) にある (lb < 16); SF/OF/PF/AF = 0。 */
    int la = 16, lb = 16;
    for (int i = 0; i < 16; i++) if (a[i] == 0) { la = i; break; }
    for (int i = 0; i < 16; i++) if (b[i] == 0) { lb = i; break; }
    uint32_t mask = 0;
    for (int i = 0; i < 16; i++) if (i < la && i < lb && a[i] == b[i]) mask |= 1u << i;
    *zf = (lb < 16) ? 1 : 0;
    *cf = mask ? 1 : 0;
    return mask ? __builtin_ctz(mask) : 16;
}

static uint64_t s;
static uint64_t nx(void) { s ^= s << 13; s ^= s >> 7; s ^= s << 17; return s; }

static void hw_run(const uint8_t* a, const uint8_t* b, uint32_t* idx, uint8_t* zf, uint8_t* cf) {
    uint64_t fl; uint32_t ix;
    __asm__ volatile(
        "movdqu (%[pa]), %%xmm0\n\t"
        "movdqu (%[pb]), %%xmm1\n\t"
        "pcmpistri $0x40, %%xmm1, %%xmm0\n\t"
        "pushfq\n\t"
        "popq %[fl]\n\t"
        "movl %%ecx, %[ix]\n\t"
        : [fl] "=r"(fl), [ix] "=r"(ix)
        : [pa] "r"(a), [pb] "r"(b)
        : "xmm0", "xmm1", "ecx", "cc");
    *idx = ix; *zf = (fl >> 6) & 1; *cf = fl & 1;
}

int main(int argc, char** argv) {
    long n = (argc > 1) ? atol(argv[1]) : 200000;
    s = (argc > 2) ? strtoull(argv[2], 0, 10) : 777;
    long bad = 0;
    uint8_t a[16], b[16];
    for (long i = 0; i < n; i++) {
        for (int k = 0; k < 16; k++) {
            unsigned v = nx() & 0xff;
            if ((nx() % 4) == 0) v = 0;                     /* EOS を頻出させる */
            a[k] = (uint8_t)v;
            v = nx() & 0xff; if ((nx() % 4) == 0) v = 0;
            b[k] = (uint8_t)v;
        }
        uint32_t hi, mi; uint8_t hz, hc, mz, mc;
        hw_run(a, b, &hi, &hz, &hc);
        mi = model_idx(a, b, &mz, &mc);
        printf("%u %u %u\n", hi, hz, hc);
        if (hi != mi || hz != mz || hc != mc) {
            if (bad < 6) {
                fprintf(stderr, "mismatch: a=%.*s| b=%.*s| hw=%u,%u,%u model=%u,%u,%u\n",
                        16, (const char*)a, 16, (const char*)b, hi, hz, hc, mi, mz, mc);
            }
            bad++;
        }
    }
    fflush(stdout);
    if (bad) { fprintf(stderr, "[pcfuzz] mismatches %ld / %ld\n", bad, n); return 1; }
    fprintf(stderr, "[pcfuzz] model == hw (%ld cases)\n", n);
    return 0;
}
