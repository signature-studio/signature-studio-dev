/* approx_probe.c — 実機 (AMD Ryzen 9 9950X) の rcpps / rsqrtps 近似の構造推定・表抽出・完全再現検証。
 *
 * rcpps_probe.c (KH-6 REPORT §13-1 の依存性実測) の拡張。ここでは
 *   (1) 結果が (sign, exponent, mantissa 上位 12bit) のみで決まることの実測
 *   (2) 「16KB の mantissa 表 + 指数算術」への分解モデル化 (gen_simd.py の共有ヘルパと同一構造)
 *   (3) その emu_* が実機と bit 一致することの全グリッド + 乱数検証
 *   (4) 特殊値 (0 / Inf / NaN / 非正規) の実機挙動
 *
 * 分解モデル (実測で確定):
 *   rcpps  : result = sign | ((253 - e) << 23) | T_rcp[m]     (253-e <= 0 → ±0)
 *   rsqrtps: result = sign | ((190 - ((e+1)>>1)) << 23) | T_rsq[m]
 *   e = exponent field, m = mantissa 上位 12bit (mantissa >> 11)。T_*[m] = e=127 のときの
 *   mantissa field (23bit)。rsqrtps は指数が e/2 で非線形なので ceil が入る。
 *
 * レガシー SSE エンコーディング (VEX 無し) を -mno-avx で強制すること。
 *   cc -O2 -msse -mno-avx -o approx_probe approx_probe.c
 *   ./approx_probe verify [nrand]   全グリッド + 乱数で emu_* と実機を照合 (既定 200000)
 *   ./approx_probe table <0|1>      mantissa 表 (4096 エントリ) を JSON で
 *   ./approx_probe one <rcp|rsqrt> <hexbits>   単発
 *   ./approx_probe special          特殊値の挙動
 *   ./approx_probe size             表サイズの実測
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <emmintrin.h>

static uint32_t bitsf(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float fl(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }

static uint32_t rcp_lane0(uint32_t u) {
    __m128 v = _mm_set_ps(0.f, 0.f, 0.f, fl(u));
    float out[4] __attribute__((aligned(16)));
    _mm_store_ps(out, _mm_rcp_ps(v));
    return bitsf(out[0]);
}
static uint32_t rsqrt_lane0(uint32_t u) {
    __m128 v = _mm_set_ps(0.f, 0.f, 0.f, fl(u));
    float out[4] __attribute__((aligned(16)));
    _mm_store_ps(out, _mm_rsqrt_ps(v));
    return bitsf(out[0]);
}
static uint32_t (*FN[2])(uint32_t) = {rcp_lane0, rsqrt_lane0};

#define EXPF(b) (((b) >> 23) & 0xff)
#define MANF(b) ((b) & 0x7fffffu)
#define SGN(b)  ((b) >> 31)

/* ---- 実機表 (e=127 基準の mantissa field) ----
 * rsqrtps は e の偶奇で √2 因子が入り mantissa が変わるので 2 表持つ。
 *   odd  e (基準 127): T_rsq_odd[m]
 *   even e (基準 126): T_rsq_even[m] */
static uint32_t T_rcp[4096], T_rsq_odd[4096], T_rsq_even[4096];
static int tabs_ready = 0;
static void build_tabs(void) {
    if (tabs_ready) return;
    for (uint32_t m = 0; m < 4096; m++) {
        T_rcp[m] = MANF(FN[0]((127u << 23) | (m << 11)));
        T_rsq_odd[m] = MANF(FN[1]((127u << 23) | (m << 11)));
        T_rsq_even[m] = MANF(FN[1]((126u << 23) | (m << 11)));
    }
    tabs_ready = 1;
}

/* ---- 分解モデル = gen_simd.py が出力する C ヘルパの本質部分 ----
 * 特殊値 (実機 9950X で実測):
 *   ±0 / 非正規 (e==0)       → rcpps/rsqrtps とも ±Inf
 *   NaN  (e==255, mant!=0)   → quiet NaN: s | 0x7f800000 | (mant | 0x400000)
 *   rcpps  ±Inf              → ±0     (結果指数 t = 253-255 < 0 → ±0 と一致)
 *   rsqrtps +Inf             → +0  /  -Inf → NaN
 *   rsqrtps 負の有限値       → NaN (0xffc00000)
 * rcpps の結果指数が 0 以下 (e>=253) → ±0 (実機も 0) */
static uint32_t emu_rcp(uint32_t x) {
    build_tabs();
    uint32_t s = x & 0x80000000u, e = (x >> 23) & 0xff, m = (x >> 11) & 0xfff, man = x & 0x7fffff;
    if (e == 0) return s | 0x7f800000u;
    if (e == 0xff) return man ? (s | 0x7f800000u | (man | 0x400000u)) : s;
    int t = 253 - (int)e;
    return t <= 0 ? s : (s | ((uint32_t)t << 23) | T_rcp[m]);
}
static uint32_t emu_rsqrt(uint32_t x) {
    build_tabs();
    uint32_t s = x & 0x80000000u, e = (x >> 23) & 0xff, m = (x >> 11) & 0xfff, man = x & 0x7fffff;
    if (e == 0) return s | 0x7f800000u;
    if (e == 0xff) return man ? (s | 0x7f800000u | (man | 0x400000u)) : (s ? 0xffc00000u : 0u);
    if (s) return 0xffc00000u;
    return (((uint32_t)(190 - (int)((e + 1) >> 1)) << 23) | ((e & 1) ? T_rsq_odd[m] : T_rsq_even[m]));
}

/* 正常値 (e in 1..254) の全グリッド + 乱数で emu_* と実機を照合。戻り値 = 不一致数。 */
static long verify(int which, long nrand) {
    build_tabs();
    uint32_t (*emu)(uint32_t) = which ? emu_rsqrt : emu_rcp;
    uint32_t (*hw)(uint32_t) = FN[which];
    long bad = 0, grid = 0, rnd = 0;
    long cls_nan = 0, cls_inf = 0, cls_den = 0, cls_neg = 0, cls_zero = 0, cls_other = 0;
    for (uint32_t e = 1; e <= 254; e++)
        for (uint32_t m = 0; m < 4096; m++) {
            uint32_t x = (e << 23) | (m << 11);
            if (emu(x) != hw(x)) { if (bad < 8) printf("  grid mismatch e=%u m=%u got=%08x want=%08x\n", e, m, emu(x), hw(x)); bad++; }
            grid++;
        }
    uint32_t st = 12345;
    for (long i = 0; i < nrand; i++) {
        st = st * 1664525u + 1013904223u;
        uint32_t x = st;
        uint32_t a = emu(x), b = hw(x);
        if (a == b) { rnd++; continue; }
        rnd++;
        uint32_t e = (x >> 23) & 0xff;
        int isnan = (e == 0xff) && (x & 0x7fffff);
        int isinf = (e == 0xff) && !(x & 0x7fffff);
        int isden = (e == 0);
        if (isnan) cls_nan++;
        else if (isinf) cls_inf++;
        else if (isden) cls_den++;
        else if (which && (x >> 31)) cls_neg++;
        else if (!(x & 0x7fffffff)) cls_zero++;
        else { cls_other++; if (bad < 8) printf("  UNCLASSIFIED x=%08x got=%08x want=%08x\n", x, a, b); }
        bad++;
    }
    printf("%s: grid=%ld rand=%ld mismatches=%ld  [nan=%ld inf=%ld denormal=%ld neg(rsqrt)=%ld zero=%ld other=%ld]\n",
           which ? "rsqrt" : "rcp", grid, rnd, bad, cls_nan, cls_inf, cls_den, cls_neg, cls_zero, cls_other);
    return bad;
}

int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "verify";
    if (!strcmp(mode, "verify")) {
        long nr = argc > 2 ? atol(argv[2]) : 200000;
        long b1 = verify(0, nr), b2 = verify(1, nr);
        printf("TOTAL mismatches: rcp=%ld rsqrt=%ld\n", b1, b2);
        return (b1 || b2) ? 1 : 0;
    }
    if (!strcmp(mode, "size")) {
        build_tabs();
        printf("table entries=%u bytes each=%zu total=%u B (rcp+rsqrt=%u B)\n",
               4096u, sizeof(uint32_t), 4096u * 4u, 2u * 4096u * 4u);
        return 0;
    }
    if (!strcmp(mode, "table")) {
        int which = argc > 2 ? atoi(argv[2]) : 0;   /* 0=rcp 1=rsqrt_odd 2=rsqrt_even */
        build_tabs();
        const uint32_t* T = which == 0 ? T_rcp : (which == 1 ? T_rsq_odd : T_rsq_even);
        printf("[");
        for (uint32_t m = 0; m < 4096; m++) printf("%s%u", m ? "," : "", T[m]);
        printf("]\n");
        return 0;
    }
    if (!strcmp(mode, "one")) {
        int w = strcmp(argv[2], "rsqrt") ? 0 : 1;
        uint32_t x = (uint32_t)strtoul(argv[3], 0, 16);
        printf("%08x\n", FN[w](x));
        return 0;
    }
    if (!strcmp(mode, "special")) {
        uint32_t xs[] = {0x00000000, 0x80000000, 0x00800000, 0x00000001, 0x007fffff, 0x80000001,
                         0x3f800000, 0xbf800000, 0x7f800000, 0xff800000, 0x7fc00000, 0xffc00000,
                         0x7f800001, 0x00000002, 0x40000000, 0x3f000000, 0xbf7fffff, 0xff800001};
        for (unsigned i = 0; i < sizeof(xs) / sizeof(xs[0]); i++)
            printf("%08x rcp=%08x rsqrt=%08x\n", xs[i], rcp_lane0(xs[i]), rsqrt_lane0(xs[i]));
        return 0;
    }
    if (!strcmp(mode, "formula")) {
        /* closed form の再現度: 実機表 vs 1/(1+m/4096) の正しい丸め (exp126 正規化) */
        int exact = 0, off1 = 0, off2 = 0, other = 0, maxulp = 0;
        for (uint32_t m = 0; m < 4096; m++) {
            uint32_t wf = bitsf((float)(1.0 / (1.0 + (double)m / 4096.0)));
            uint32_t got = FN[0]((127u << 23) | (m << 11));
            if (EXPF(wf) != 126) { other++; continue; }
            int d = (int32_t)MANF(got) - (int32_t)MANF(wf);
            if (d == 0) exact++; else if (d == 1 || d == -1) off1++;
            else if (d == 2 || d == -2) off2++;
            else { other++; if (abs(d) > maxulp) maxulp = abs(d); }
        }
        printf("rcp table vs round(1/(1+m/4096)) [exp126]: exact=%d +-1ulp=%d +-2ulp=%d other=%d maxulp=%d\n",
               exact, off1, off2, other, maxulp);
        return 0;
    }
    return 2;
}
