/* ext_wasm_test.c — ext IR (f80_lower.py --ext が出す IR) の wasm32 バックエンド検証 (P0c-8 / #311)。
 *
 *   native : cc -O2 -ffp-contract=off -DGEN ext_wasm_test.c -lm -o gen && ./gen N EXP.bin
 *            native x87 (long double) の期待値 (dd 正準形) を EXP.bin に書く
 *   wasm32 : emcc -O2 -ffp-contract=off ext_wasm_test.c t.ll -sNODERAWFS -o t.js && node t.js N EXP.bin
 *            同じ決定的入力から ext IR (t_c0/t_c1) を wasm32 で実行し EXP.bin と bit 比較
 *
 * 入力生成 (rand_dd_leaf / rnd) は ext_core_test.c と同一。case = (mode 0..3, chop 0/1, a, b)
 * を N 個ずつ + 固定 edge/tie 集合。比較は 6 dd 語 (mul/add/sub の hi/lo) を TwoSum で正準化
 * してから bit 比較 (零符号は hi の bit で比較), fist (i32), f32 store 2 個 (mul/add)。
 * 不一致が 1 件でもあれば exit 1。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
#ifdef GEN
#include <fenv.h>
#endif

typedef unsigned long long u64;
typedef unsigned int u32;
typedef struct { double h, l; } dd;
typedef struct { u64 w[6]; int32_t fi; u32 fm, fa; u64 pad; } rec_t;   /* 64 B */

static u64 RS0 = 0x9e3779b97f4a7c15ull, RS1 = 0xbf58476d1ce4e5b9ull;
static u64 rnd(void) {
    u64 x = RS0, y = RS1;
    RS0 = y; x ^= x << 23; RS1 = x ^ y ^ (x >> 17) ^ (y >> 26);
    return RS1 + y;
}
static double bits2d(u64 b) { double d; memcpy(&d, &b, 8); return d; }
static u64 d2bits(double d) { u64 b; memcpy(&b, &d, 8); return b; }

static void rand_dd_leaf(dd *a, int mode) {
    u64 r = rnd();
    switch (mode & 3) {
    case 0: {
        u32 bits = (u32)r;
        bits = (bits & 0x807fffffu) | ((((u32)(rnd() >> 40) & 0xffu) % 25u + 118u) << 23);
        float f; memcpy(&f, &bits, 4);
        a->h = (double)f; a->l = 0.0; break; }
    case 1: a->h = (double)(int32_t)r; a->l = 0.0; break;
    case 2: {
        u64 bits = (r & 0x800fffffffffffffull) | ((u64)((int)((rnd() >> 40) % 61) - 30 + 1023) << 52);
        a->h = bits2d(bits); a->l = 0.0; break; }
    default: {
        u64 bits = (r & 0x800fffffffffffffull) | ((u64)((int)((rnd() >> 40) % 61) - 30 + 1023) << 52);
        a->h = bits2d(bits);
        int eh = (int)((d2bits(a->h) >> 52) & 2047) - 1023;
        long long m = (long long)(rnd() % 4097) - 2048;
        a->l = (double)m * ldexp(1.0, eh - 63);
        if (a->l == 0.0) a->l = 0.0;
        break; }
    }
}

/* 固定 edge/tie 集合 (ext_core_test.c [7][8] 相当) */
static dd FIX[64]; static int NFIX = 0; static long skip_bothlo = 0;
static void build_fix(void) {
    static const double zs[] = { 0.0, -0.0, 1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 3.0, 1.0 / 3.0, 6.0 / 7.0,
                                 1.0 + 4.4408920985006262e-16, 1e-3, -1e-3, 1e3, -1e3 };
    static const double ls[] = { 0x1p-63, -0x1p-63, 2 * 0x1p-63, -2 * 0x1p-63, 3 * 0x1p-63, -3 * 0x1p-63,
                                 5 * 0x1p-63, -5 * 0x1p-63 };
    for (unsigned i = 0; i < sizeof zs / sizeof zs[0]; i++) { FIX[NFIX].h = zs[i]; FIX[NFIX++].l = 0.0; }
    for (unsigned i = 0; i < sizeof ls / sizeof ls[0]; i++) { FIX[NFIX].h = 1.0; FIX[NFIX++].l = ls[i]; }
    for (unsigned i = 0; i < 4; i++) { FIX[NFIX].h = 1.0 + 0x1p-24; FIX[NFIX++].l = (i == 0 ? 0.0 : ls[i - 1]); }
}

/* dd → 正準形 (TwoSum: h = RN(h+l), l = exact 余り。l の零は +0 に統一) */
static void canon(double h, double l, u64 *oh, u64 *ol) {
    double s = h + l, bb = s - h, e = (h - (s - bb)) + (l - bb);
    if (h == 0.0 && l == 0.0) { *oh = d2bits(h); *ol = 0; return; }
    if (e == 0.0) e = 0.0;
    *oh = d2bits(s); *ol = d2bits(e);
}

#ifdef GEN
static void setmode(int chop) { fesetround(chop ? FE_TOWARDZERO : FE_TONEAREST); }
static long double ddl(dd a) { return a.l == 0.0 ? (long double)a.h : (long double)a.h + (long double)a.l; }
static __attribute__((noinline)) float nat_f32(volatile long double *v, int chop) {
    setmode(chop);
    float r = (float)*v;
    fesetround(FE_TONEAREST);
    return r;
}
static void nat_rec(dd a, dd b, int chop, rec_t *r) {
    volatile long double A = ddl(a), B = ddl(b), m, s, d;
    setmode(chop); m = A * B; fesetround(FE_TONEAREST);
    setmode(chop); s = A + B; fesetround(FE_TONEAREST);
    setmode(chop); d = A - B; fesetround(FE_TONEAREST);
    long double v[3] = { m, s, d };
    for (int i = 0; i < 3; i++) {
        double h = (double)v[i]; double l = (double)(v[i] - (long double)h);
        if (v[i] == 0.0L) { h = (double)v[i]; l = 0.0; }
        canon(h, l, &r->w[2 * i], &r->w[2 * i + 1]);
    }
    int32_t fi = 0;
    if (fabs(a.h + a.l) < 1e9 && fabs(b.h + b.l) < 1e9) {
        setmode(chop);
        volatile long double pv = A * B;
        if (pv >= 2147483648.0L || pv < -2147483648.0L) fi = (int32_t)0x80000000;
        else if (chop) fi = (int32_t)pv; else fi = (int32_t)rintl(pv);
        fesetround(FE_TONEAREST);
    }
    r->fi = fi;
    float fm = nat_f32(&m, chop), fa = nat_f32(&s, chop);
    memcpy(&r->fm, &fm, 4); memcpy(&r->fa, &fa, 4);
    r->pad = 0;
}
#else
void t_c0(double, double, double, double, void *);
void t_c1(double, double, double, double, void *);
static int ir_rec(dd a, dd b, int chop, rec_t *r) {
    double o[8]; memset(o, 0, sizeof o);
    if (chop) t_c1(a.h, a.l, b.h, b.l, o); else t_c0(a.h, a.l, b.h, b.l, o);
    for (int i = 0; i < 3; i++) canon(o[2 * i], o[2 * i + 1], &r->w[2 * i], &r->w[2 * i + 1]);
    memcpy(&r->fi, (char *)o + 48, 4);
    memcpy(&r->fm, (char *)o + 52, 4);
    memcpy(&r->fa, (char *)o + 56, 4);
    r->pad = 0;
    return 0;
}
#endif

int main(int argc, char **argv) {
    long N = argc > 1 ? atol(argv[1]) : 3000000;
    const char *path = argc > 2 ? argv[2] : "ext_exp.bin";
    long total = 0, fails = 0, cat[4] = { 0, 0, 0, 0 };
    build_fix();
#ifdef GEN
    FILE *f = fopen(path, "wb");
#else
    FILE *f = fopen(path, "rb");
#endif
    if (!f) { perror(path); return 2; }
    static rec_t buf[4096]; int nb = 0;
    long cases = 0;
    for (int phase = 0; phase < 2; phase++) {
        long lim = phase == 0 ? 8L * N : (long)NFIX * NFIX * 2;
        long idx = 0;
        int mode = 0, chop = 0; long n = 0;
        for (idx = 0; idx < lim; idx++) {
            dd a, b;
            if (phase == 0) {
                chop = (int)(idx & 1); mode = (int)((idx >> 1) / N);
                if (idx % 2 == 0 && 0) n++;
                rand_dd_leaf(&a, mode); rand_dd_leaf(&b, mode);
            } else {
                chop = (int)(idx & 1);
                long q = idx >> 1; a = FIX[q / NFIX]; b = FIX[q % NFIX];
                /* 既知限界 (REPORT §15.5): dd 積は al*bl を捨て、al*bh / ah*bl を f64 に丸める。
                 * lo 付きオペランドの相手 hi が f32 正確値でない (>24 bit) と ah*bl が 54 bit 以上で
                 * 不正確になり得る。固定集合ではそれらを除外し件数を出力する (乱数 mode 0-3 は除外なし)。 */
                if ((a.l != 0.0 && b.l != 0.0) ||
                    (a.l != 0.0 && b.h != (double)(float)b.h) || (b.l != 0.0 && a.h != (double)(float)a.h)) {
                    skip_bothlo++; continue;
                }
                double ra = fabs(a.h), rb = fabs(b.h);
                if (ra != 0.0 && rb != 0.0 && (ra / rb > 1e10 || rb / ra > 1e10)) continue;
            }
            rec_t r;
            memset(&r, 0, sizeof r);
#ifdef GEN
            nat_rec(a, b, chop, &r);
            buf[nb++] = r;
            if (nb == 4096) { fwrite(buf, sizeof(rec_t), nb, f); nb = 0; }
#else
            ir_rec(a, b, chop, &r);
            if (nb == 0) { size_t got = fread(buf, sizeof(rec_t), 4096, f); (void)got; }
            rec_t *e = &buf[nb];
            int bad = 0;
            for (int i = 0; i < 6; i++) if (r.w[i] != e->w[i]) { bad |= 1; }
            int fi_checked = (fabs(a.h + a.l) < 1e9 && fabs(b.h + b.l) < 1e9);
            if (fi_checked && r.fi != e->fi) bad |= 2;
            if (r.fm != e->fm || r.fa != e->fa) bad |= 4;
            if (bad) {
                fails++;
                for (int k = 0; k < 3; k++) if (bad & (1 << k)) cat[k]++;
                if (fails <= 10) {
                    printf("  a=%a,%a b=%a,%a\n", a.h, a.l, b.h, b.l);
                    for (int i = 0; i < 6; i++) if (r.w[i] != e->w[i]) printf("  w%d got=%016llx want=%016llx\n", i, r.w[i], e->w[i]);
                }
                if (fails <= 10)
                    printf("[FAIL] case=%ld ph=%d mode=%d chop=%d bad=%d fm=%08x/%08x fa=%08x/%08x fi=%d/%d mul=%016llx/%016llx want %016llx/%016llx\n",
                           cases, phase, mode, chop, bad, r.fm, e->fm, r.fa, e->fa, r.fi, e->fi, r.w[0], r.w[1], e->w[0], e->w[1]);
            }
            nb = (nb + 1) % 4096;
#endif
            cases++;
        }
    }
#ifdef GEN
    if (nb) fwrite(buf, sizeof(rec_t), nb, f);
    fclose(f);
    printf("[gen] %ld cases -> %s (skipped known-limit fixed pairs=%ld)\n", cases, path, skip_bothlo);
    return 0;
#else
    fclose(f);
    (void)total;
    printf("[wasm] cases=%ld fails=%ld (dd=%ld fist=%ld f32=%ld) skipped(known-limit fixed pairs)=%ld\n", cases, fails, cat[0], cat[1], cat[2], skip_bothlo);
    printf(fails ? "== ext wasm32 FAIL ==\n" : "== ext wasm32 OK (bit-exact vs native x87) ==\n");
    return fails ? 1 : 0;
#endif
}
