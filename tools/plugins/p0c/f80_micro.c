/* f80_micro.c — x87 f80 (long double) vs f64 lowering (double) の bit 差分実測 (CAB-196 P0c)
 *
 * 目的: f80→f64 lowering pass を適用した場合に bit-exact が崩れる kernel / 崩れない kernel を
 *       実測で分類し、soft-float80 要否判定の根拠とする。
 * 方法:
 *   (A) long double 版 = x87 80bit 実装 (Linux x86-64 gcc は long double を x87 命令で実行, PC=64bit)
 *       → 実機械語 kernel 4 本と bit 比較して A 側の妥当性を先に検証
 *   (B) double 版   = f80→f64 lowering pass が生成する演算列 (-ffp-contract=off で FMA 化を防止)
 *   A vs B / native vs A / native vs B の bit 一致数・最大 ULP 差を pattern ごとに実測。
 * 実機械語: block18983 (Fruity Balance) を VA 0x400000 に MAP_FIXED 敷設 (lift/t0_balance/native_ref.c 方式)
 *   0x5df210: out[i] = (f32)(x87) a[i]*b[i]        (rcx=a f32, rdx=out, r8=b, r9d=n)
 *   0x5e0330: out[2i]=out[2i+1]=(i64)(x87)fild(src[i]) (rcx=src i64, rdx=out i64, r8=n)
 *   0x5de820: out[i] = (f32)(x87) a[i]*c1 + b[i]   (rcx=a, rdx=b, r8=out, r9=n; c1/c2 は stack arg9/10)
 *   0x5de390: arr[i] = max87(|arr[i]|, c)          (rcx=arr f64, edx=n, c は [rip+0x121bd7])
 * usage: f80_micro <block18983_PE.bin> [nrand]
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>

#define REBASE 0x400000UL
typedef uint64_t (__attribute__((ms_abi)) *fn4)(uint64_t, uint64_t, uint64_t, uint64_t);
typedef uint64_t (__attribute__((ms_abi)) *fn10)(uint64_t, uint64_t, uint64_t, uint64_t,
                                                 uint64_t, uint64_t, uint64_t, uint64_t,
                                                 uint64_t, uint64_t);

static void map_image(const char* path) {
    int fd = open(path, O_RDONLY); if (fd < 0) { perror("open PE"); exit(2); }
    off_t sz = lseek(fd, 0, SEEK_END);
    uint8_t* f = mmap(NULL, sz, PROT_READ, MAP_PRIVATE, fd, 0);
    uint32_t pe; memcpy(&pe, f + 0x3c, 4);
    uint16_t nsec, optsz; memcpy(&nsec, f + pe + 6, 2); memcpy(&optsz, f + pe + 20, 2);
    uint32_t imgsz; memcpy(&imgsz, f + pe + 24 + 56, 4);
    void* b = mmap((void*)REBASE, imgsz, imgsz ? (PROT_READ|PROT_WRITE|PROT_EXEC) : 0, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED|MAP_NORESERVE, -1, 0);
    if (b != (void*)REBASE) { fprintf(stderr, "MAP_FIXED 0x400000 失敗\n"); exit(3); }
    uint32_t so = pe + 24 + optsz;
    for (int i = 0; i < nsec; i++) {
        uint32_t vs, va, rs, rp; uint8_t* e = f + so + 40 * i;
        memcpy(&vs, e + 8, 4); memcpy(&va, e + 12, 4); memcpy(&rs, e + 16, 4); memcpy(&rp, e + 20, 4);
        uint32_t n = rs < vs ? rs : vs;
        if (n) memcpy((void*)(REBASE + va), f + rp, n);
    }
}

/* ---- xorshift128+ (シード固定で再現可能) ---- */
static uint64_t S0 = 0x9e3779b97f4a7c15ull, S1 = 0xbf58476d1ce4e5b9ull;
static uint64_t rnd(void) {
    uint64_t x = S0, y = S1;
    S0 = y; x ^= x << 23; S1 = x ^ y ^ (x >> 17) ^ (y >> 26);
    return S1 + y;
}
static inline float bits2f(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }
static inline double bits2d(uint32_t lo, uint32_t hi) { double d; uint64_t u = (uint64_t)lo | ((uint64_t)hi << 32); memcpy(&d, &u, 8); return d; }

/* ---- パターン実装: LD = long double (x87), D = double (f64 lowering) ---- */

/* P1: f32 mul — kernel 0x5df210 主ループ (fld dword / fmul dword / fstp dword) */
static void p_f32mul_ld(const float* a, const float* b, float* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { long double t = (long double)a[i] * (long double)b[i]; o[i] = (float)t; }
}
static void p_f32mul_d (const float* a, const float* b, float* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { double t = (double)a[i] * (double)b[i]; o[i] = (float)t; }
}
/* P2: f32 add */
static void p_f32add_ld(const float* a, const float* b, float* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { long double t = (long double)a[i] + (long double)b[i]; o[i] = (float)t; }
}
static void p_f32add_d (const float* a, const float* b, float* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { double t = (double)a[i] + (double)b[i]; o[i] = (float)t; }
}
/* P3: f32 mul+add — kernel 0x5de820 本体 (ステレオ対, 8B ストライド):
 *   偶数 ch: fld x; fmul st(2)=[rbp+0x30](arg5=cL); fadd [rdx]; fstp
 *   奇数 ch: fld x; fmul st(1)=[rbp+0x38](arg6=cR); fadd [rdx+4]; fstp */
static void p_f32fma_ld(const float* a, const float* b, float* o, uint32_t npair, float cL, float cR) {
    for (uint32_t i = 0; i < npair; i++) {
        long double t = ((long double)a[2*i] * (long double)cL) + (long double)b[2*i];   o[2*i] = (float)t;
        long double u = ((long double)a[2*i+1] * (long double)cR) + (long double)b[2*i+1]; o[2*i+1] = (float)u;
    }
}
static void p_f32fma_d (const float* a, const float* b, float* o, uint32_t npair, float cL, float cR) {
    for (uint32_t i = 0; i < npair; i++) {
        double t = ((double)a[2*i] * (double)cL) + (double)b[2*i];     o[2*i] = (float)t;
        double u = ((double)a[2*i+1] * (double)cR) + (double)b[2*i+1]; o[2*i+1] = (float)u;
    }
}
/* P4: f64 mul — 出力自体 f64 (fld qword / fmul / fstp qword) */
static void p_f64mul_ld(const double* a, const double* b, double* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { long double t = (long double)a[i] * (long double)b[i]; o[i] = (double)t; }
}
static void p_f64mul_d (const double* a, const double* b, double* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) o[i] = a[i] * b[i];
}
/* P5: i64 → x87 → i64 (kernel 0x5e0330: fild q / fld st0 / fistp q ×2, RC=nearest) */
static void p_i64rt_ld(const int64_t* s, int64_t* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { volatile long double t = (long double)s[i]; int64_t v = (int64_t)t; o[2*i] = v; o[2*i+1] = v; }
}
static void p_i64rt_d (const int64_t* s, int64_t* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) { volatile double t = (double)s[i]; int64_t v = (int64_t)t; o[2*i] = v; o[2*i+1] = v; }
}
/* P6: fistp RC=chop (fldcw 0x0F3F — kernel 0x5dfbe0/0x5dfdb0/0x5dfc90 が使用) vs C trunc cast */
static uint16_t cw_save;
static inline void rc_push_chop(void) { __asm__ volatile("fstcw %0" : "=m"(cw_save)); uint16_t cw = 0x0F3F; __asm__ volatile("fldcw %0" :: "m"(cw)); }
static inline void rc_pop(void)       { __asm__ volatile("fldcw %0" :: "m"(cw_save)); }
static void p_fist_chop_x87(const float* s, int32_t* o, uint32_t n) {
    rc_push_chop();
    for (uint32_t i = 0; i < n; i++) {
        volatile long double t = (long double)s[i];
        int32_t v; __asm__ volatile("fldt %1\n\tfistpl %0" : "=m"(v) : "m"(t));
        o[i] = v;
    }
    rc_pop();
}
static void p_fist_chop_d(const float* s, int32_t* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++) o[i] = (int32_t)s[i];  /* C cast = trunc == chop */
}
/* P7: kernel 0x5dfae0 の超越列 — 2^T を frndint / f2xm1 / fscale で計算 (x87 ハードウェアアルゴリズム)。
 *     D 側は exp2() libm (lowering 後に LLVM が選ぶ形の代用)。 */
static inline long double pow87_ld(long double T) {
    long double K = rintl(T);                 /* frndint (RC=nearest) */
    long double F = T - K;                    /* fsub st(1),st(0) */
    long double y = F;
    __asm__ volatile("f2xm1" : "+t"(y));      /* 2^F-1 (x87 HW アルゴリズム) */
    return ldexpl(y + 1.0L, (long)K);         /* fld1;faddp;fscale 相当 (K は整数, fscale と等価) */
}
static inline double pow87_d(double T) {
    double K = nearbyint(T);   /* frndint 相当 */
    return exp2(T);            /* f2xm1+fscale の代用 (libm) */
}
static void p_pow_ld(const float* t, float m, float* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++)
        o[i] = (float)(1.0L - pow87_ld((long double)t[i]));
}
static void p_pow_d(const float* t, float m, float* o, uint32_t n) {
    for (uint32_t i = 0; i < n; i++)
        o[i] = (float)(1.0 - pow87_d((double)t[i]));
}
/* P8: f64 ノイズゲート — kernel 0x5de390 (fucompi+fcmovb: |x|<c や unordered は st(2)=fldz の +0.0 採用) */
static void p_gate_ld(double* a, uint32_t n, float c) {
    for (uint32_t i = 0; i < n; i++) { long double x = (long double)a[i]; if (!(fabsl(x) >= (long double)c)) x = 0.0L; a[i] = (double)x; }
}
static void p_gate_d(double* a, uint32_t n, float c) {
    for (uint32_t i = 0; i < n; i++) { double x = a[i]; if (!(fabs(x) >= (double)c)) x = 0.0; a[i] = x; }
}

/* ---- 統計 (NaN はビット差を数えない: x87 real indefinite と C の NaN 伝播でペイロードが違うだけの cases を分離) ---- */
typedef struct { const char* name; uint32_t n; uint32_t diff; uint32_t nandiff; double maxulp; } stat_t;
static stat_t ST[32]; static int NST = 0;
static double ulp32f(float x, float y) {
    float lo = fabsf(x) < fabsf(y) ? x : y;
    if (!isfinite(lo)) return 0;
    float nx = nextafterf(lo, INFINITY);
    double u = (double)nx - (double)lo;
    return fabs((double)x - (double)y) / (u > 0 ? u : 1e-45);
}
static double ulp64d(double x, double y) {
    double lo = fabs(x) < fabs(y) ? x : y;
    if (!isfinite(lo)) return 0;
    double u = nextafter(lo, INFINITY) - lo;
    return fabs(x - y) / (u > 0 ? u : 4.9e-324);
}
static void cmp32(const char* name, const float* x, const float* y, uint32_t n) {
    uint32_t df = 0, nd = 0; double mu = 0;
    for (uint32_t i = 0; i < n; i++) {
        if (isnan(x[i]) && isnan(y[i])) { nd++; continue; }
        if (memcmp(&x[i], &y[i], 4)) { df++; double u = ulp32f(x[i], y[i]); if (u > mu) mu = u; }
    }
    stat_t* s = &ST[NST++]; s->name = name; s->n = n; s->diff = df; s->nandiff = nd; s->maxulp = mu;
}
static void cmp64(const char* name, const double* x, const double* y, uint32_t n) {
    uint32_t df = 0, nd = 0; double mu = 0;
    for (uint32_t i = 0; i < n; i++) {
        if (isnan(x[i]) && isnan(y[i])) { nd++; continue; }
        if (memcmp(&x[i], &y[i], 8)) { df++; double u = ulp64d(x[i], y[i]); if (u > mu) mu = u; }
    }
    stat_t* s = &ST[NST++]; s->name = name; s->n = n; s->diff = df; s->nandiff = nd; s->maxulp = mu;
}
static void cmpi64(const char* name, const int64_t* x, const int64_t* y, uint32_t n) {
    uint32_t df = 0;
    for (uint32_t i = 0; i < n; i++) if (x[i] != y[i]) df++;
    stat_t* s = &ST[NST++]; s->name = name; s->n = n; s->diff = df; s->nandiff = 0; s->maxulp = df ? 1 : 0;
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: f80_micro <block18983_PE.bin> [nrand]\n"); return 2; }
    map_image(argv[1]);
    uint32_t N = argc > 2 ? (uint32_t)strtoul(argv[2], NULL, 0) : 2000000;
    fn4  k_mul  = (fn4 )(REBASE + (0x5df210 - 0x400000));
    fn4  k_i64  = (fn4 )(REBASE + (0x5e0330 - 0x400000));
    fn10 k_fma  = (fn10)(REBASE + (0x5de820 - 0x400000));
    fn4  k_fmax = (fn4 )(REBASE + (0x5de390 - 0x400000));
    float kc = *(float*)(REBASE + (0x5de39f + 6 + 0x121bd7 - 0x400000));   /* fld dword [rip+disp32] (6B) の target */

    /* 入力生成: 全ビットランダム f32 + 指数集中 + 日常値 */
    float *a  = aligned_alloc(64, (size_t)N * 4),  *b  = aligned_alloc(64, (size_t)N * 4);
    float *o1 = aligned_alloc(64, (size_t)N * 4),  *o2 = aligned_alloc(64, (size_t)N * 4), *oN = aligned_alloc(64, (size_t)N * 4);
    for (uint32_t i = 0; i < N; i++) {
        uint32_t r = (uint32_t)rnd();
        switch ((rnd() >> 33) % 5) {
            case 0: case 1: case 2: a[i] = bits2f(r); break;
            case 3: a[i] = bits2f((r & 0x807fffffu) | (((rnd() >> 40) % 254u) << 23)); break;
            case 4: a[i] = (float)((int64_t)(rnd() % 2000001) - 1000000) / 1000.0f; break;
        }
        uint32_t r2 = (uint32_t)rnd();
        b[i] = bits2f(((rnd() >> 33) % 3 == 0) ? r2 : ((r2 & 0x807fffffu) | (((rnd() >> 40) % 254u) << 23)));
    }

    /* P1/P2/P3: f32 out 系 */
    p_f32mul_ld(a, b, o1, N); p_f32mul_d(a, b, o2, N); cmp32("P1 f32 mul->f32", o1, o2, N);
    p_f32add_ld(a, b, o1, N); p_f32add_d(a, b, o2, N); cmp32("P2 f32 add->f32", o1, o2, N);
    float c1 = bits2f(0x3f800000u | ((uint32_t)rnd() & 0x7fffffu));
    float c2 = bits2f(0x3f800000u | ((uint32_t)rnd() & 0x7fffffu));
    p_f32fma_ld(a, b, o1, N / 2, c1, c2); p_f32fma_d(a, b, o2, N / 2, c1, c2); cmp32("P3 f32 mul+add->f32 (stereo)", o1, o2, N);

    /* P4: f64 mul — 出力自体 f64。入力は真の f64 ランダムビット (53bit 仮数全エントロピー) */
    double *da = aligned_alloc(64, (size_t)N * 8), *db = aligned_alloc(64, (size_t)N * 8);
    double *do1 = aligned_alloc(64, (size_t)N * 8), *do2 = aligned_alloc(64, (size_t)N * 8);
    for (uint32_t i = 0; i < N; i++) {
        uint64_t x = rnd(), y = rnd();
        da[i] = bits2d((uint32_t)x, (uint32_t)(x >> 32));
        db[i] = bits2d((uint32_t)y, (uint32_t)(y >> 32));
        if (!isfinite(da[i])) da[i] = (double)(int64_t)x / 4096.0;   /* 非有限は通常値に差し替え (桁溢れテストは別途 mul で発生) */
        if (!isfinite(db[i])) db[i] = (double)(int64_t)y / 4096.0;
    }
    p_f64mul_ld(da, db, do1, N); p_f64mul_d(da, db, do2, N); cmp64("P4 f64 mul->f64 (f64 entropy)", do1, do2, N);

    /* P5: i64 roundtrip */
    int64_t *is = aligned_alloc(64, (size_t)N * 8), *io1 = aligned_alloc(64, (size_t)N * 16), *io2 = aligned_alloc(64, (size_t)N * 16), *ioN = aligned_alloc(64, (size_t)N * 16);
    for (uint32_t i = 0; i < N; i++) {
        uint64_t r = rnd();
        switch ((rnd() >> 60) % 3) {
            case 0: is[i] = (int64_t)(r % 2000000000ull) - 1000000000ll; break;
            case 1: is[i] = (int64_t)(r % 1000000000000000000ull) - 500000000000000000ll; break;
            case 2: is[i] = (int64_t)r; break;
        }
    }
    p_i64rt_ld(is, io1, N); p_i64rt_d(is, io2, N); cmpi64("P5 i64 fild/fistp->i64", io1, io2, N * 2);

    /* P6: fistp RC=chop vs trunc */
    p_fist_chop_x87(a, (int32_t*)o1, N); p_fist_chop_d(a, (int32_t*)o2, N);
    cmpi64("P6 f32->i32 chop vs trunc", (int64_t*)o1, (int64_t*)o2, (N + 1) / 2);

    /* P7: pow 列 (自己検証: |pow87_ld(T) - ldexpl(2,floor)| < 1e-3 を確認してから本計測) */
    for (long double T = -3.0L; T <= 3.0L; T += 0.375L) {
        long double ref = exp2l(T);
        long double got = pow87_ld(T);
        if (fabsl(got - ref) / ref > 1e-3L) { fprintf(stderr, "pow87 self-check FAIL T=%.3Lf got=%.6Lf ref=%.6Lf\n", T, got, ref); return 4; }
    }
    {
        uint32_t n7 = 200000;
        /* T を case ごとにランダム化 (kernel 0x5dfae0 の T = (d0-m)*d8*log2e の範囲を模擬) */
        float *t7 = aligned_alloc(64, (size_t)n7 * 4);
        for (uint32_t i = 0; i < n7; i++) t7[i] = (float)(((int64_t)(rnd() % 400001) - 200000) / 10000.0);  /* T' ∈ [-20,20] */
        p_pow_ld(t7, 0, o1, n7); p_pow_d(t7, 0, o2, n7);
        cmp32("P7 pow f2xm1/fscale->f32", o1, o2, n7);
        free(t7);
    }

    /* P8: f64 max (unordered 含む) */
    {
        uint32_t n8 = 100000;
        for (uint32_t i = 0; i < n8; i++) { da[i] = (double)a[i]; if ((rnd() >> 58) == 0x1Full) da[i] = NAN; }
        memcpy(do1, da, (size_t)n8 * 8); memcpy(do2, da, (size_t)n8 * 8);
        p_gate_ld(do1, n8, kc); p_gate_d(do2, n8, kc); cmp64("P8 f64 noise-gate unordered->f64", do1, do2, n8);
    }

    /* ===== 実機械語 kernel 4 本 ===== */
    const uint32_t NK = 300000;
    for (uint32_t i = 0; i < NK; i++) { a[i] = bits2f((uint32_t)rnd()); b[i] = bits2f((uint32_t)rnd()); }
    memset(o1, 0, (size_t)NK * 4); memset(o2, 0, (size_t)NK * 4); memset(oN, 0, (size_t)NK * 4);
    k_mul((uint64_t)a, (uint64_t)oN, (uint64_t)b, NK);
    p_f32mul_ld(a, b, o1, NK); p_f32mul_d(a, b, o2, NK);
    cmp32("K5df210 native vs LD(f80)", oN, o1, NK);
    cmp32("K5df210 native vs D(f64) ", oN, o2, NK);

    for (uint32_t i = 0; i < NK; i++) {
        uint64_t r = rnd();
        switch (i % 3) {   /* 小整数 + 2^53 超 (f64 丸み発生域) + 全範囲 */
            case 0: is[i] = (int64_t)(r % 2000000000ull) - 1000000000ll; break;
            case 1: is[i] = (int64_t)(r % 1000000000000000000ull) - 500000000000000000ll; break;
            case 2: is[i] = (int64_t)r; break;
        }
    }
    memset(io1, 0, (size_t)NK * 16); memset(io2, 0, (size_t)NK * 16); memset(ioN, 0, (size_t)NK * 16);
    k_i64((uint64_t)is, (uint64_t)ioN, NK, 0);
    p_i64rt_ld(is, io1, NK); p_i64rt_d(is, io2, NK);
    cmpi64("K5e0330 native vs LD(f80)", ioN, io1, NK * 2);
    cmpi64("K5e0330 native vs D(f64) ", ioN, io2, NK * 2);

    /* k0x5de820: ステレオ対 (8B ストライド) — native は 2*NK float 書込, mul 定数は L=arg5 / R=arg6 */
    float cc1 = 0.7071067811865476f, cc2 = 0.3535533905932738f;
    float *a2 = aligned_alloc(64, (size_t)NK * 8), *b2 = aligned_alloc(64, (size_t)NK * 8);
    float *o3a = aligned_alloc(64, (size_t)NK * 8), *o3b = aligned_alloc(64, (size_t)NK * 8), *o3N = aligned_alloc(64, (size_t)NK * 8);
    for (uint32_t i = 0; i < 2 * NK; i++) { a2[i] = bits2f((uint32_t)rnd()); b2[i] = bits2f((uint32_t)rnd()); }
    memset(o3a, 0, (size_t)NK * 8); memset(o3b, 0, (size_t)NK * 8); memset(o3N, 0, (size_t)NK * 8);
    k_fma((uint64_t)a2, (uint64_t)b2, (uint64_t)o3N, NK, (uint64_t)*(uint32_t*)&cc1, (uint64_t)*(uint32_t*)&cc2, 0, 0, 0, 0);
    p_f32fma_ld(a2, b2, o3a, NK, cc1, cc2); p_f32fma_d(a2, b2, o3b, NK, cc1, cc2);
    cmp32("K5de820 native vs LD(f80)", o3N, o3a, 2 * NK);
    cmp32("K5de820 native vs D(f64) ", o3N, o3b, 2 * NK);
    free(a2); free(b2); free(o3a); free(o3b); free(o3N);

    for (uint32_t i = 0; i < NK; i++) { da[i] = (double)bits2f((uint32_t)rnd()); if ((rnd() >> 58) == 0x1Full) da[i] = NAN; }
    double *dN = aligned_alloc(64, (size_t)NK * 8);
    memcpy(dN, da, (size_t)NK * 8); memcpy(do1, da, (size_t)NK * 8); memcpy(do2, da, (size_t)NK * 8);
    k_fmax((uint64_t)dN, NK, 0, 0);
    p_gate_ld(do1, NK, kc); p_gate_d(do2, NK, kc);
    cmp64("K5de390 native vs LD(f80)", dN, do1, NK);
    cmp64("K5de390 native vs D(f64) ", dN, do2, NK);

    printf("pattern,ncases,bit-diff,nan-bit-diff,diff%%,maxulp_dest\n");
    for (int i = 0; i < NST; i++)
        printf("%s,%u,%u,%u,%.4f,%.3f\n", ST[i].name, ST[i].n, ST[i].diff, ST[i].nandiff, 100.0 * ST[i].diff / ST[i].n, ST[i].maxulp);
    return 0;
}
