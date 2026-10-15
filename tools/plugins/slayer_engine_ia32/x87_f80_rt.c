/* x87_f80_rt.c — f80 ↔ f64 変換 (tools/ott/rt/ott_x87.h の x87_f80_to_f64 / x87_f64_to_f80) の往復試験 (#2967)。
 * 参照は実 x87 (fldt/fstpl・fldl/fstpt)。 x87_diff.py --roundtrip が work/x87/roundtrip/ に作って実行する。
 *   R1 f64->f80: 実 x87 と lowered の 10 byte が一致するか (類ごと)
 *   R2 f80->f64: 実 x87 と lowered の double の bit が一致するか (類ごと)
 *   R3 f64->f80->f64: lowered だけの往復で元の bit に戻るか (類ごと)
 *   R4 f80->f64->f80: lowered だけの往復で元の 10 byte に戻るか (類ごと)
 * 出力は 1 行 1 類 (n と bad = 不一致件数)。 乱数は xorshift 固定 seed。 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "ott_x87.h"

enum { NORM, OUT, ZERO, INF, QNAN, SNAN, DEN, NCLS };
static const char* cname[NCLS] = {"normal", "exp_out_of_f64", "zero", "inf", "qnan", "snan", "denormal"};
static uint64_t rs = 0x9e3779b97f4a7c15ULL;

static uint64_t rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return rs; }

static void nat_f80_to_f64(const uint8_t* p, double* d) {
    __asm__ volatile("fldt (%0)\n\tfstpl (%1)" :: "r"(p), "r"(d) : "memory");
}

static void nat_f64_to_f80(double d, uint8_t* p) {
    __asm__ volatile("fldl (%0)\n\tfstpt (%1)" :: "r"(&d), "r"(p) : "memory");
}

/* 有効な f80 符号化だけを作る (非正規の指数は 0、正規の指数は bit63 = 1) */
static void gen80(uint8_t* p, int c) {
    uint64_t sig = 0;
    uint16_t se = (uint16_t)((rnd() & 1) << 15);
    memset(p, 0, 16);
    switch (c) {
    case NORM: se |= (uint16_t)(16383 - 1000 + rnd() % 2000); sig = (1ULL << 63) | (rnd() >> 1); break;
    case OUT:
        se |= (rnd() & 1) ? (uint16_t)(17408 + rnd() % (0x7ffe - 17408 + 1)) : (uint16_t)(1 + rnd() % 15360);
        sig = (1ULL << 63) | (rnd() >> 1);
        break;
    case ZERO: break;
    case INF: se |= 0x7fff; sig = 1ULL << 63; break;
    case QNAN: se |= 0x7fff; sig = (1ULL << 63) | (1ULL << 62) | (rnd() & ((1ULL << 62) - 1)); break;
    case SNAN: se |= 0x7fff; sig = (1ULL << 63) | ((rnd() & ((1ULL << 62) - 1)) | 1); break;
    default: sig = (rnd() >> 1) | 1; break;   /* DEN: 指数 0・bit63 = 0・仮数 ≠ 0 */
    }
    memcpy(p, &sig, 8);
    memcpy(p + 8, &se, 2);
}

/* f64 の類 (指数域の外は作らない)。 */
static uint64_t gen64(int c) {
    uint64_t sg = (rnd() & 1) << 63, m = rnd() & ((1ULL << 52) - 1);
    switch (c) {
    case NORM: return sg | ((1 + rnd() % 2046) << 52) | m;
    case ZERO: return sg;
    case INF: return sg | (0x7ffULL << 52);
    case QNAN: return sg | (0x7ffULL << 52) | (1ULL << 51) | m;
    case SNAN: return sg | (0x7ffULL << 52) | ((m & ((1ULL << 51) - 1)) | 1);
    default: return sg | (m | 1);            /* DEN: 指数 0・仮数 ≠ 0 */
    }
}

int main(int argc, char** argv) {
    long n = argc > 1 ? atol(argv[1]) : 100000;
    uint8_t p[16], bn[16], bl[16], r[16];
    int c;
    for (c = 0; c < NCLS; c++) {
        long bad2 = 0, bad4 = 0;
        for (long i = 0; i < n; i++) {
            double dn, dl;
            gen80(p, c);
            nat_f80_to_f64(p, &dn);
            dl = x87_f80_to_f64(p);
            if (memcmp(&dn, &dl, 8)) bad2++;
            x87_f64_to_f80(dl, r);
            if (memcmp(r, p, 10)) bad4++;
        }
        printf("R2 f80->f64 native-vs-lowered class=%s n=%ld bad=%ld\n", cname[c], n, bad2);
        printf("R4 f80->f64->f80 lowered class=%s n=%ld bad=%ld\n", cname[c], n, bad4);
    }
    for (c = 0; c < NCLS; c++) {
        long bad1 = 0, bad3 = 0;
        if (c == OUT) continue;
        for (long i = 0; i < n; i++) {
            uint64_t u = gen64(c);
            double d, back;
            memcpy(&d, &u, 8);
            memset(bn, 0, sizeof bn);
            memset(bl, 0, sizeof bl);
            nat_f64_to_f80(d, bn);
            x87_f64_to_f80(d, bl);
            if (memcmp(bn, bl, 10)) bad1++;
            back = x87_f80_to_f64(bl);
            if (memcmp(&back, &d, 8)) bad3++;
        }
        printf("R1 f64->f80 native-vs-lowered class=%s n=%ld bad=%ld\n", cname[c], n, bad1);
        printf("R3 f64->f80->f64 lowered class=%s n=%ld bad=%ld\n", cname[c], n, bad3);
    }
    return 0;
}
