/* x87_trans_direct.c: fsin/fcos/f2xm1/fyl2x/fprem を 1 命令ずつ比べる差分試験 (#3687)。
 * native = 実 x87 (f80 で計算し fstp m64 で f64 に丸める)。 lowered = tools/ott/rt/ott_x87.h の x87_* (double)。
 * 入力は f64 だけ (fld m64 で正確に載る)。 よって差は命令の計算 (f80 対 double) と定義域の外の扱いだけによる。
 * 比べる: 値の bit 一致と FSW の C0/C2/C3 (trig・f2xm1・fyl2x は C1 を除く・fprem は C1 も含む)。
 * 値の ulp 分布と、nextafter の歩進による ulp の検算 (cap 3)。
 * usage: x87_trans_direct N SEED   (出力は類ごとの 1 行)
 */
#include "ott_cpu.h"
#include "ott_x87.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

uint64_t ott_gbase;   /* ott_cpu.c の参照先 (試験は相対化モードを使わない) */

static uint64_t rs;
static uint64_t rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return rs; }
static double urand(void) { return (double)(rnd() >> 11) * (1.0 / 9007199254740992.0); }
static double rdbl(double lo, double hi) { return lo + (hi - lo) * urand(); }
static double rsign(void) { return (rnd() & 1) ? -1.0 : 1.0; }
/* 符号つき・仮数 [1,2)・指数 [emin, emax] */
static double rexp(int emin, int emax) {
    int e = emin + (int)(rnd() % (uint64_t)(emax - emin + 1));
    return rsign() * ldexp(1.0 + urand(), e);
}

#define CL "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"

static double nat_sin(double a, unsigned short *fsw) {
    double r; unsigned short s;
    __asm__ volatile("fninit\n\tfldl %2\n\tfsin\n\tfnstsw %1\n\tfstpl %0" : "=m"(r), "=m"(s) : "m"(a) : CL);
    *fsw = s; return r;
}
static double nat_cos(double a, unsigned short *fsw) {
    double r; unsigned short s;
    __asm__ volatile("fninit\n\tfldl %2\n\tfcos\n\tfnstsw %1\n\tfstpl %0" : "=m"(r), "=m"(s) : "m"(a) : CL);
    *fsw = s; return r;
}
static double nat_f2xm1(double a, unsigned short *fsw) {
    double r; unsigned short s;
    __asm__ volatile("fninit\n\tfldl %2\n\tf2xm1\n\tfnstsw %1\n\tfstpl %0" : "=m"(r), "=m"(s) : "m"(a) : CL);
    *fsw = s; return r;
}
/* fscale: ST(0) * 2^trunc(ST(1))。 f80 の結果の指数 (e80) も返す (f64 の指数域外の判定用) */
static double nat_fscale(double a, double n, unsigned short *fsw, unsigned *e80) {
    double r; unsigned short s; long double f;
    __asm__ volatile("fninit\n\tfldl %4\n\tfldl %3\n\tfscale\n\tfnstsw %1\n\tfstpt %2\n\tfldt %2\n\tfstpl %0" : "=m"(r), "=m"(s), "=m"(f) : "m"(a), "m"(n) : CL);
    unsigned short se; memcpy(&se, (char *)&f + 8, 2);
    *fsw = s; *e80 = se & 0x7fff; return r;
}
static double nat_fyl2x(double x, double y, unsigned short *fsw) {
    double r; unsigned short s;
    __asm__ volatile("fninit\n\tfldl %3\n\tfldl %2\n\tfyl2x\n\tfnstsw %1\n\tfstpl %0" : "=m"(r), "=m"(s) : "m"(x), "m"(y) : CL);
    *fsw = s; return r;
}
static double nat_fprem(double a, double b, unsigned short *fsw) {
    double r; unsigned short s;
    __asm__ volatile("fninit\n\tfldl %3\n\tfldl %2\n\tfprem\n\tfnstsw %1\n\tfstpl %0\n\tfstp %%st(0)" : "=m"(r), "=m"(s) : "m"(a), "m"(b) : CL);
    *fsw = s; return r;
}

static double low_fn(int which, double a, double b, uint16_t *fsw) {
    ott_ftop = 0; ott_fsw = 0; ott_fst[0] = a; ott_fst[1] = b;
    switch (which) {
    case 0: x87_trig(0); break;
    case 1: x87_trig(1); break;
    case 2: x87_f2xm1(); break;
    case 3: x87_fyl2x(); break;
    default: x87_fprem(); break;
    }
    *fsw = (uint16_t)(ott_fsw & 0x4700);
    return which == 3 ? x87_st(0) : ott_fst[0];
}

static uint64_t bits(double d) { uint64_t u; memcpy(&u, &d, 8); return u; }
/* 単調な符号付きキー (負の値は符号を反転。 -0 と +0 は同じ 0) */
static int64_t ukey(double d) {
    uint64_t u = bits(d);
    return (u >> 63) ? -(int64_t)(u & 0x7fffffffffffffffULL) : (int64_t)u;
}
static uint64_t ulp_dist(double a, double b) {
    if (a != a || b != b) return (a != a && b != b) ? 0 : (1ULL << 40);
    int64_t ka = ukey(a), kb = ukey(b);
    return ka > kb ? (uint64_t)ka - (uint64_t)kb : (uint64_t)kb - (uint64_t)ka;
}
static uint64_t ulp_step(double a, double b, int cap) {
    if (a == b || (a != a && b != b)) return 0;
    double x = a;
    for (int k = 1; k <= cap; k++) { x = nextafter(x, b); if (x == b) return (uint64_t)k; }
    return (uint64_t)cap;
}

typedef struct { const char *name; long n, ident, fsw_bad, hist[4], bad; unsigned mask; long nh[16], lh[16]; } st_t;

/* FSW の C1 C3 C2 C0 の 4 bit を 0..15 に */
static unsigned fsw_pat(unsigned f) { return ((f >> 8) & 1) | (((f >> 10) & 1) << 1) | (((f >> 14) & 1) << 2) | (((f >> 9) & 1) << 3); }

static void add(st_t *s, double nat, double low, unsigned short fn, uint16_t fl) {
    uint64_t u = ulp_dist(nat, low);
    s->n++;
    if (bits(nat) == bits(low)) s->ident++;
    if (((unsigned)fn & s->mask) != ((unsigned)fl & s->mask)) s->fsw_bad++;
    s->nh[fsw_pat((unsigned)fn & 0x4700)]++;
    s->lh[fsw_pat((unsigned)fl & 0x4700)]++;
    s->hist[u >= 3 ? 3 : u]++;
    if (nat == nat && low == low && u != ulp_step(nat, low, 3) && u < 3) s->bad++;
}

static void report(st_t *s) {
    printf("[trans] %-22s n=%ld bit-identical=%ld (%.2f%%) ulp 0/1/2/>=3 = %ld/%ld/%ld/%ld  FSW mismatch=%ld  ulp cross-check bad=%ld\n",
           s->name, s->n, s->ident, 100.0 * s->ident / (double)s->n, s->hist[0], s->hist[1], s->hist[2], s->hist[3],
           s->fsw_bad, s->bad);
    printf("        FSW C1C3C2C0 patterns: native");
    for (int p = 0; p < 16; p++) if (s->nh[p]) printf(" %d%d%d%d:%ld", (p >> 3) & 1, (p >> 2) & 1, (p >> 1) & 1, p & 1, s->nh[p]);
    printf(" | lowered");
    for (int p = 0; p < 16; p++) if (s->lh[p]) printf(" %d%d%d%d:%ld", (p >> 3) & 1, (p >> 2) & 1, (p >> 1) & 1, p & 1, s->lh[p]);
    printf("\n");
}

int main(int argc, char **argv) {
    long N = argc > 1 ? atol(argv[1]) : 100000;
    rs = argc > 2 ? (uint64_t)atoll(argv[2]) * 0x9E3779B97F4A7C15ULL + 1 : 88172645463325252ULL;
    st_t S[] = {
        {"fsin |a|<=2^20", 0, 0, 0, {0}, 0, 0x4500}, {"fsin 2^20<|a|<2^63", 0, 0, 0, {0}, 0, 0x4500},
        {"fsin |a|>=2^63 (C2)", 0, 0, 0, {0}, 0, 0x4500}, {"fcos |a|<=2^20", 0, 0, 0, {0}, 0, 0x4500},
        {"fcos 2^20<|a|<2^63", 0, 0, 0, {0}, 0, 0x4500}, {"fcos |a|>=2^63 (C2)", 0, 0, 0, {0}, 0, 0x4500},
        {"f2xm1 |a|<=1", 0, 0, 0, {0}, 0, 0x4500}, {"f2xm1 1<|a|<=8 (out)", 0, 0, 0, {0}, 0, 0x4500},
        {"fyl2x x>0 (e -20..20)", 0, 0, 0, {0}, 0, 0x4500}, {"fyl2x x<=0 (NaN/-inf)", 0, 0, 0, {0}, 0, 0x4500},
        {"fprem e<64 (complete)", 0, 0, 0, {0}, 0, 0x4700}, {"fprem e>=64 (partial)", 0, 0, 0, {0}, 0, 0x4700},
        {"fsin |a|<=pi/4", 0, 0, 0, {0}, 0, 0x4500}, {"fsin pi/4<|a|<=2^10", 0, 0, 0, {0}, 0, 0x4500},
        {"fscale (wide exp)", 0, 0, 0, {0}, 0, 0x4500},
    };
    long fs_ovf = 0, fs_unf = 0, fs_ovf_low_inf = 0;
    for (long i = 0; i < N; i++) {
        unsigned short fn; uint16_t fl; double nat, low;
        double a;
        a = rdbl(-(1 << 20), 1 << 20);
        nat = nat_sin(a, &fn); low = low_fn(0, a, 0, &fl); add(&S[0], nat, low, fn, fl);
        nat = nat_cos(a, &fn); low = low_fn(1, a, 0, &fl); add(&S[3], nat, low, fn, fl);
        a = rsign() * ldexp(1.0 + urand(), (int)(20 + rnd() % 43));
        nat = nat_sin(a, &fn); low = low_fn(0, a, 0, &fl); add(&S[1], nat, low, fn, fl);
        nat = nat_cos(a, &fn); low = low_fn(1, a, 0, &fl); add(&S[4], nat, low, fn, fl);
        a = rexp(63, 1000);
        nat = nat_sin(a, &fn); low = low_fn(0, a, 0, &fl); add(&S[2], nat, low, fn, fl);
        nat = nat_cos(a, &fn); low = low_fn(1, a, 0, &fl); add(&S[5], nat, low, fn, fl);
        a = rsign() * rdbl(0.0, 0.7853981633974483);
        nat = nat_sin(a, &fn); low = low_fn(0, a, 0, &fl); add(&S[12], nat, low, fn, fl);
        a = rsign() * rdbl(0.7853981633974483, 1024.0);
        nat = nat_sin(a, &fn); low = low_fn(0, a, 0, &fl); add(&S[13], nat, low, fn, fl);
        a = rdbl(-1.0, 1.0);
        nat = nat_f2xm1(a, &fn); low = low_fn(2, a, 0, &fl); add(&S[6], nat, low, fn, fl);
        a = rsign() * rdbl(1.0, 8.0);
        nat = nat_f2xm1(a, &fn); low = low_fn(2, a, 0, &fl); add(&S[7], nat, low, fn, fl);
        {
            double x = fabs(rexp(-20, 20)), y = rdbl(-1000.0, 1000.0);
            nat = nat_fyl2x(x, y, &fn); low = low_fn(3, x, y, &fl); add(&S[8], nat, low, fn, fl);
            x = (rnd() & 1) ? -fabs(rexp(-20, 20)) : 0.0;
            nat = nat_fyl2x(x, y, &fn); low = low_fn(3, x, y, &fl); add(&S[9], nat, low, fn, fl);
        }
        {
            int ea = (int)(rnd() % 41) - 20, eb = (int)(rnd() % 41) - 20;
            double ca = rsign() * ldexp(1.0 + urand(), ea), cb = rsign() * ldexp(1.0 + urand(), eb);
            nat = nat_fprem(ca, cb, &fn); low = low_fn(4, ca, cb, &fl); add(&S[10], nat, low, fn, fl);
            double pb = rsign() * ldexp(1.0 + urand(), ea - 64 - (int)(rnd() % 192));
            nat = nat_fprem(ca, pb, &fn); low = low_fn(4, ca, pb, &fl); add(&S[11], nat, low, fn, fl);
        }
        {
            double fa = rsign() * ldexp(1.0 + urand(), (int)(rnd() % 2201) - 1100);
            double fn2 = (double)((long)(rnd() % 140001) - 70000);
            unsigned e80;
            nat = nat_fscale(fa, fn2, &fn, &e80);
            if (e80 >= 16383 + 1024 && e80 < 0x7fff) fs_ovf++;
            if (e80 < 16383 - 1022 && e80 != 0) fs_unf++;
            ott_ftop = 0; ott_fsw = 0; ott_fst[0] = fa; ott_fst[1] = fn2; x87_fscale();
            low = ott_fst[0]; fl = (uint16_t)(ott_fsw & 0x4700);
            if (e80 >= 16383 + 1024 && e80 < 0x7fff && isinf(low)) fs_ovf_low_inf++;
            add(&S[14], nat, low, fn, fl);
        }
    }
    for (unsigned i = 0; i < sizeof(S) / sizeof(S[0]); i++) report(&S[i]);
    printf("[trans] fscale wide: native f80 finite but f64 out of range: overflow(inf) %ld, below f64 normal range %ld, lowered inf %ld\n",
           fs_ovf, fs_unf, fs_ovf_low_inf);
    return 0;
}
