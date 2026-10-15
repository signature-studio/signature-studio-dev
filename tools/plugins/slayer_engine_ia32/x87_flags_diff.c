/* x87_flags_diff.c: x87 の例外フラグ (IE/DE/ZE/OE/UE/PE/SF) と C1 を、実 x87 (native) と模型 (ott_x87.h) で突合する (#5046)。
 * native = 実 x87。 演算ごとに fninit + fldcw (FCW を指定) → 入力を積む → 演算 → fnstsw の順で FSW を読む。
 *   FCW は 2 通り: 0x037f (拡張 64bit = fninit の既定。実プログラムの設定) と 0x027f (f64 = 模型の精度)。
 *   模型は精度制御を f64 に固定する (ott_x87.h 制限 1) ので、0x027f の表が模型との比較の本命。 0x037f の表は PE の精度差の寄与を見る。
 * model = ott_x87.h の x87_* を呼んだ後の ott_fsw の flags/C1 ビット。 模型は flags を持たず、C1 は fxam・比較の後だけ持つ (制限 6)。
 *   よって模型の観測値は fxam・fcompp の C1 以外では 0 になり、native の立てた flag は「模型に無い」として数える。
 * 正の対照: 1/0 で native が ZE を立てること (読みが機能すること)。 fxam の C1 (符号) は native と模型が一致すること。
 * usage: x87_flags_diff   (出力は FCW ごとの演算別の表。 対照が崩れたら exit 1)
 */
#include "ott_cpu.h"
#include "ott_x87.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <math.h>

uint64_t ott_gbase;   /* ott_cpu.c の参照先 (試験は相対化モードを使わない) */

#define CL "st", "st(1)", "st(2)", "st(3)", "st(4)", "st(5)", "st(6)", "st(7)"
#define OBS_MASK 0x027fu   /* 観測する FSW: IE DE ZE OE UE PE SF (bit 0..6) と C1 (bit 9)。 ES (bit 7)・C0/C2/C3 は含めない */
#define C1_BIT 0x0200u

static const double VALS[] = {
    0.0, -0.0, 1.0, -1.0, 3.0, 0.1, 1e300, -1e300, 1e-300, 1e-310, 4.9406564584124654e-324,
    9007199254740993.0, 1e308, 2.2250738585072014e-308,
};
#define NV ((int)(sizeof VALS / sizeof VALS[0]))
static const uint64_t SPECIAL[] = {
    0x7ff0000000000000ULL, 0xfff0000000000000ULL,   /* +inf / -inf */
    0x7ff8000000000000ULL, 0xfff8000000000000ULL,   /* qNaN / -qNaN */
    0x7ff0000000000001ULL,                          /* sNaN */
};
#define NS ((int)(sizeof SPECIAL / sizeof SPECIAL[0]))
#define NA (NV + NS)

static double input(int i) {
    if (i < NV) return VALS[i];
    uint64_t b = SPECIAL[i - NV]; double d; memcpy(&d, &b, 8); return d;
}

enum { OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_SQRT, OP_FCOMPP, OP_FXAM, OP_FISTP32, OP_FSTPS, OP_COUNT };
static const char *OP_NAME[] = {"fadd", "fsub", "fmul", "fdiv", "fsqrt", "fcompp", "fxam", "fistp m32", "fstp m32"};
static const int OP_TWO[] = {1, 1, 1, 1, 0, 1, 0, 0, 0};

static uint16_t g_cw;

static void fpu_init(void) {
    uint16_t cw = g_cw;
    __asm__ volatile("fninit\n\tfldcw %0" :: "m"(cw) : "memory");
}

/* native: 結果 (value) と FSW を返す。 OP_TWO の演算は b を使う */
static uint16_t nat_run(int kind, double a, double b, double *val) {
    double r = 0; uint16_t s = 0; float f = 0; int32_t iv = 0;
    fpu_init();
    switch (kind) {
    case OP_ADD:
        __asm__ volatile("fldl %2\n\tfaddl %3\n\tfstpl %0\n\tfnstsw %1" : "=m"(r), "=m"(s) : "m"(a), "m"(b) : CL, "memory");
        break;
    case OP_SUB:
        __asm__ volatile("fldl %2\n\tfsubl %3\n\tfstpl %0\n\tfnstsw %1" : "=m"(r), "=m"(s) : "m"(a), "m"(b) : CL, "memory");
        break;
    case OP_MUL:
        __asm__ volatile("fldl %2\n\tfmull %3\n\tfstpl %0\n\tfnstsw %1" : "=m"(r), "=m"(s) : "m"(a), "m"(b) : CL, "memory");
        break;
    case OP_DIV:
        __asm__ volatile("fldl %2\n\tfdivl %3\n\tfstpl %0\n\tfnstsw %1" : "=m"(r), "=m"(s) : "m"(a), "m"(b) : CL, "memory");
        break;
    case OP_SQRT:
        __asm__ volatile("fldl %2\n\tfnclex\n\tfsqrt\n\tfstpl %0\n\tfnstsw %1" : "=m"(r), "=m"(s) : "m"(a) : CL, "memory");
        break;
    case OP_FCOMPP:
        __asm__ volatile("fldl %3\n\tfldl %2\n\tfnclex\n\tfcompp\n\tfnstsw %1" : "=m"(r), "=m"(s) : "m"(a), "m"(b) : CL, "memory");
        break;
    case OP_FXAM:
        __asm__ volatile("fldl %2\n\tfnclex\n\tfxam\n\tfnstsw %1\n\tfstp %%st(0)" : "=m"(r), "=m"(s) : "m"(a) : CL, "memory");
        break;
    case OP_FISTP32:
        __asm__ volatile("fldl %2\n\tfnclex\n\tfistpl %0\n\tfnstsw %1" : "=m"(iv), "=m"(s) : "m"(a) : CL, "memory");
        r = (double)iv;
        break;
    default:
        __asm__ volatile("fldl %2\n\tfnclex\n\tfstps %0\n\tfnstsw %1" : "=m"(f), "=m"(s) : "m"(a) : CL, "memory");
        r = (double)f;
        break;
    }
    *val = r;
    return s;
}

/* model: 同じ演算を ott_x87 で行い、観測対象の ott_fsw ビットと値を返す */
static uint16_t mod_run(int kind, double a, double b, double *val) {
    double r = 0;
    ott_ftop = 0; ott_fsw = 0; ott_fcw = g_cw;
    ott_fst[0] = a; ott_fst[1] = b;
    switch (kind) {
    case OP_ADD: x87_arith(X87_ADD, 0, b, 0); r = x87_st(0); break;
    case OP_SUB: x87_arith(X87_SUB, 0, b, 0); r = x87_st(0); break;
    case OP_MUL: x87_arith(X87_MUL, 0, b, 0); r = x87_st(0); break;
    case OP_DIV: x87_arith(X87_DIV, 0, b, 0); r = x87_st(0); break;
    case OP_SQRT: x87_set(0, sqrt(a)); r = x87_st(0); break;
    case OP_FCOMPP: x87_fcom(a, b); break;
    case OP_FXAM: x87_fxam(); break;
    case OP_FISTP32: r = (double)x87_fist32(a); break;
    default: r = (double)(float)a; break;
    }
    *val = r;
    return (uint16_t)(ott_fsw & OBS_MASK);
}

/* スタック例外 (SF・C1): native のみ測る。 模型はスタックの over/underflow を持たない (ott_x87.h 制限 4) ので、模型の観測は 0 */
enum { ST_UNDER_FADD, ST_UNDER_FSTP, ST_OVER8, ST_OVER9, ST_COUNT };
static const char *ST_NAME[] = {"空スタック fadd", "空スタック fstp", "8 段 push (対照)", "9 段 push"};
#define P1 "fldl %1\n\t"
#define P2 P1 P1
#define P4 P2 P2
#define P8 P4 P4
#define P9 P8 P1

static uint16_t nat_stack(int kind, double a) {
    uint16_t s = 0;
    fpu_init();
    switch (kind) {
    case ST_UNDER_FADD:
        __asm__ volatile("fnclex\n\tfadd %%st(0),%%st\n\tfnstsw %0\n\tfninit" : "=m"(s) :: CL, "memory");
        break;
    case ST_UNDER_FSTP:
        __asm__ volatile("fnclex\n\tfstp %%st(0)\n\tfnstsw %0\n\tfninit" : "=m"(s) :: CL, "memory");
        break;
    case ST_OVER8:
        __asm__ volatile("fnclex\n\t" P8 "fnstsw %0\n\tfninit" : "=m"(s) : "m"(a) : CL, "memory");
        break;
    default:
        __asm__ volatile("fnclex\n\t" P9 "fnstsw %0\n\tfninit" : "=m"(s) : "m"(a) : CL, "memory");
        break;
    }
    return s;
}

static uint64_t bits(double d) { uint64_t u; memcpy(&u, &d, 8); return u; }

static const char *FNAME[] = {"IE", "DE", "ZE", "OE", "UE", "PE", "SF", "C1"};
static const unsigned FBIT[] = {0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, C1_BIT};

static long modonly_total;

static int run_table(uint16_t cw, int verbose) {
    int bad_ctl = 0;
    g_cw = cw;
    printf("[flags] === FCW 0x%04x (%s) ===\n", cw, cw == 0x027f ? "f64: 模型と同じ精度" : "拡張 64bit: fninit 既定");
    /* 正の対照: 1/0 は native で ZE */
    double v; uint16_t s = nat_run(OP_DIV, 1.0, 0.0, &v);
    if (!(s & 0x04)) { printf("[flags] control FAIL: native 1/0 が ZE を立てない (fsw %04x)\n", s); bad_ctl++; }
    else printf("[flags] control PASS: native 1/0 で ZE (fsw %04x)\n", s);
    /* 正の対照: fxam の C1 (符号) は native と模型が一致 */
    long fx_n = 0, fx_bad = 0;
    for (int i = 0; i < NA; i++) {
        double a = input(i), nv, mv;
        uint16_t ns = nat_run(OP_FXAM, a, 0, &nv), ms = mod_run(OP_FXAM, a, 0, &mv);
        fx_n++;
        if ((ns & C1_BIT) != (ms & C1_BIT)) fx_bad++;
    }
    printf("[flags] control fxam C1 (sign): rows %ld, C1 mismatch %ld (expect 0)\n", fx_n, fx_bad);
    if (fx_bad) bad_ctl++;

    for (int k = 0; k < OP_COUNT; k++) {
        long rows = 0, mism_row = 0, nat_any = 0, mod_any = 0, val_bad = 0;
        long natonly[8] = {0}, modonly[8] = {0};
        int have = 0; double fa = 0, fb = 0; uint16_t first_ns = 0, first_ms = 0;
        int nB = OP_TWO[k] ? NA : 1;
        for (int i = 0; i < NA; i++) for (int j = 0; j < nB; j++) {
            double a = input(i), b = OP_TWO[k] ? input(j) : 0, nv, mv;
            uint16_t ns = nat_run(k, a, b, &nv) & OBS_MASK;
            uint16_t ms = mod_run(k, a, b, &mv) & OBS_MASK;
            rows++;
            if (ns) nat_any++;
            if (ms) mod_any++;
            if (ns != ms) {
                mism_row++;
                if (!have) { have = 1; fa = a; fb = b; first_ns = ns; first_ms = ms; }
            }
            for (int f = 0; f < 8; f++) {
                unsigned bit = FBIT[f];
                if ((ns & bit) && !(ms & bit)) natonly[f]++;
                if ((ms & bit) && !(ns & bit)) modonly[f]++;
            }
            if (k != OP_FCOMPP && k != OP_FXAM && bits(nv) != bits(mv) && !(nv != nv && mv != mv)) val_bad++;
        }
        printf("[flags] %-10s rows %ld  native-any %ld  model-any %ld  flag/C1 mismatch rows %ld  value bit-diff %ld\n",
               OP_NAME[k], rows, nat_any, mod_any, mism_row, val_bad);
        if (verbose) {
            printf("        native が立て model が立てない bit:");
            for (int f = 0; f < 8; f++) if (natonly[f]) printf(" %s:%ld", FNAME[f], natonly[f]);
            printf(" | model が立て native が立てない bit (模型の誤り):");
            for (int f = 0; f < 8; f++) if (modonly[f]) printf(" %s:%ld", FNAME[f], modonly[f]);
            printf("\n");
            for (int f = 0; f < 8; f++) modonly_total += modonly[f];
            if (have) printf("        first mismatch: a=%.17g b=%.17g native=%04x model=%04x\n", fa, fb, first_ns, first_ms);
        }
    }
    return bad_ctl;
}

int main(void) {
    int bad = run_table(0x037f, 1);
    bad += run_table(0x027f, 1);
    /* スタック例外: 空スタックの読み (fadd/fstp) と 9 段 push は SF、8 段 push は SF 無し (対照) */
    static const int ST_SF[] = {1, 1, 0, 1};
    long st_sf_rows = 0, st_bad = 0;
    for (int k = 0; k < ST_COUNT; k++) {
        uint16_t s = nat_stack(k, 1.0);
        int sf = (s & 0x0040) != 0;
        st_sf_rows += sf;
        printf("[flags] stack %-18s native fsw %04x SF=%d IE=%d C1=%d\n", ST_NAME[k], s, sf, (s & 0x01) != 0, (s & C1_BIT) != 0);
        if (sf != ST_SF[k]) st_bad++;
    }
    printf("[flags] stack SF expectation mismatch %ld (expect 0); native SF rows %ld; model SF rows 0 (model has no stack flags)\n", st_bad, st_sf_rows);
    bad += (int)st_bad;
    printf("[flags] model-only bits (模型の誤り) total %ld (expect 0)\n", modonly_total);
    if (modonly_total) bad++;
    printf("[flags] %s\n", bad ? "FAIL (control broken or model sets a bit native does not)" : "PASS (controls hold; model sets no bit native lacks; native-only bits are the model's limit)");
    return bad ? 1 : 0;
}
