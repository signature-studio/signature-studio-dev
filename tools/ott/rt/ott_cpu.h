/* ott_cpu.h — lifted x86-64 code runtime (tools/ott/lift): CPU 状態 + 命令 helper。
 * 方針: 命令を 1:1 で C 文に写す (RetDec のような意味解析/最適化はしない)。guest pointer = wasm linear address。
 * image VA 0x180000000+X は lift 時に 0x30000000+X へ shift 済み (data は ott_data_install で同アドレスに敷設)。 */
#ifndef OTT_CPU_H
#define OTT_CPU_H
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>

typedef union { uint8_t b[16]; int8_t sb[16]; uint16_t w[8]; int16_t sw[8]; uint32_t d[4]; int32_t sd[4];
                uint64_t q[2]; int64_t sq[2]; float f[4]; double df[2]; } X128;
extern uint64_t R[16];
/* X[0..15] = xmm0..15, XH[0..15] = ymm_k の上位 128bit (CAB-135: VEX/AVX 対応)。
 * VEX.128 命令は dest の上位 128bit をゼロ化 (XZ(i))、legacy SSE 命令は X のみ触り (上位保存)。 */
extern X128 X[16];
extern X128 XH[16];
extern uint8_t fZF, fSF, fCF, fOF, fPF, fDF;
enum { RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI, R8, R9, R10, R11, R12, R13, R14, R15 };

typedef uint8_t __attribute__((aligned(1))) u8u;
typedef uint16_t __attribute__((aligned(1))) u16u;
typedef uint32_t __attribute__((aligned(1))) u32u;
typedef uint64_t __attribute__((aligned(1))) u64u;
typedef float __attribute__((aligned(1))) f32u;
typedef double __attribute__((aligned(1))) f64u;
#ifdef OTT_CHK
void ott_chk(uint64_t a, int line);
#define A_(a) ((uintptr_t)(ott_chk((uint64_t)(a), __LINE__), (a)))
#else
#define A_(a) ((uintptr_t)(a))
#endif
#define LD8(a) (*(u8u*)A_(a))
#define LD16(a) (*(u16u*)A_(a))
#define LD32(a) (*(u32u*)A_(a))
#define LD64(a) (*(u64u*)A_(a))
#define LDF32(a) (*(f32u*)A_(a))
#define LDF64(a) (*(f64u*)A_(a))
#define ST8(a, v) (*(u8u*)A_(a) = (uint8_t)(v))
#define ST16(a, v) (*(u16u*)A_(a) = (uint16_t)(v))
#define ST32(a, v) (*(u32u*)A_(a) = (uint32_t)(v))
#define ST64(a, v) (*(u64u*)A_(a) = (uint64_t)(v))
#define STF32(a, v) (*(f32u*)A_(a) = (float)(v))
#define STF64(a, v) (*(f64u*)A_(a) = (double)(v))
static inline X128 LDX(uint64_t a) { X128 x; memcpy(&x, (void*)A_(a), 16); return x; }
static inline void STX(uint64_t a, X128 x) { memcpy((void*)A_(a), &x, 16); }
static inline X128 xz(void) { X128 x; memset(&x, 0, sizeof x); return x; }

/* CAB-135: segment (gs/fs) の shadow base。Win64 は gs = TEB。実行 coverage 内の gs 参照は
 * gs:[0x10] = TEB.StackLimit (スタック余裕判定) のみ → 全 0 の静的ブロックを指せば
 * 「スタック溢れなし」の意味になり native と揃う (guest stack は emcc 2MB)。 */
extern uint64_t ott_gsbase, ott_fsbase;
extern uint64_t ott_gbase;   /* 相対化モード: guest image の wasm 上の base (ott_glue.c) */

/* CAB-135: 256bit (ymm) レジスタ i のメモリ load/store (X+XH の組) と VEX.128 dest の上位ゼロ化 */
static inline void LDY(int i, uint64_t a) { memcpy(&X[i], (const void*)A_(a), 16); memcpy(&XH[i], (const void*)A_(a + 16), 16); }
static inline void STY(int i, uint64_t a) { memcpy((void*)A_(a), &X[i], 16); memcpy((void*)A_(a + 16), &XH[i], 16); }
#define XZ(i) (XH[i].q[0] = XH[i].q[1] = 0)

/* CAB-135 probe: VEX 命令の実行 coverage (probe build = -DOTT_VEXCOV のみ本体を持つ) */
#ifdef OTT_VEXCOV
void ott_vexhit(uint64_t va);
#define OTT_VEXCOV_HIT(a) ott_vexhit(a)
#else
#define OTT_VEXCOV_HIT(a) ((void)0)
#endif

#define PAR8(x) (!__builtin_parity((uint8_t)(x)))
#define SETZSP(W, r) do { fZF = ((uint##W##_t)(r) == 0); fSF = (((uint##W##_t)(r)) >> (W - 1)) & 1; fPF = PAR8(r); } while (0)
#define FL_ADD(W, a, b, r) do { fCF = ((uint##W##_t)(r) < (uint##W##_t)(a)); fOF = (((~((a) ^ (b))) & ((a) ^ (r))) >> (W - 1)) & 1; SETZSP(W, r); } while (0)
#define FL_ADC(W, a, b, r, c) do { fCF = (c) ? ((uint##W##_t)(r) <= (uint##W##_t)(a)) : ((uint##W##_t)(r) < (uint##W##_t)(a)); fOF = (((~((a) ^ (b))) & ((a) ^ (r))) >> (W - 1)) & 1; SETZSP(W, r); } while (0)
#define FL_SUB(W, a, b, r) do { fCF = ((uint##W##_t)(a) < (uint##W##_t)(b)); fOF = ((((a) ^ (b)) & ((a) ^ (r))) >> (W - 1)) & 1; SETZSP(W, r); } while (0)
#define FL_SBB(W, a, b, r, c) do { fCF = (c) ? ((uint##W##_t)(a) <= (uint##W##_t)(b)) : ((uint##W##_t)(a) < (uint##W##_t)(b)); fOF = ((((a) ^ (b)) & ((a) ^ (r))) >> (W - 1)) & 1; SETZSP(W, r); } while (0)
#define FL_LOGIC(W, r) do { fCF = 0; fOF = 0; SETZSP(W, r); } while (0)

/* 条件 (capstone cc 名) */
#define CC_E (fZF)
#define CC_NE (!fZF)
#define CC_B (fCF)
#define CC_AE (!fCF)
#define CC_BE (fCF || fZF)
#define CC_A (!fCF && !fZF)
#define CC_S (fSF)
#define CC_NS (!fSF)
#define CC_P (fPF)
#define CC_NP (!fPF)
#define CC_O (fOF)
#define CC_NO (!fOF)
#define CC_L (fSF != fOF)
#define CC_GE (fSF == fOF)
#define CC_LE (fZF || (fSF != fOF))
#define CC_G (!fZF && (fSF == fOF))

/* SSE compare → EFLAGS */
static inline void comis_f(double a, double b, int unordered_ok) {
    (void)unordered_ok;
    if (a != a || b != b) { fZF = 1; fPF = 1; fCF = 1; }
    else if (a > b) { fZF = 0; fPF = 0; fCF = 0; }
    else if (a < b) { fZF = 0; fPF = 0; fCF = 1; }
    else { fZF = 1; fPF = 0; fCF = 0; }
    fOF = 0; fSF = 0;
}
/* cmpss/cmpsd predicate 0..7 */
static inline int cmp_pred_f(int p, double a, double b) {
    int un = (a != a) || (b != b);
    switch (p & 7) {
    case 0: return !un && a == b;
    case 1: return !un && a < b;
    case 2: return !un && a <= b;
    case 3: return un;
    case 4: return un || a != b;
    case 5: return un || !(a < b);
    case 6: return un || !(a <= b);
    default: return !un;
    }
}
/* 変換 (MXCSR 既定 = round-nearest-even, 例外 mask) */
static inline int32_t cvtt_d2i32(double v) { if (v != v || v >= 2147483648.0 || v < -2147483648.0) return INT32_MIN; return (int32_t)v; }
static inline int64_t cvtt_d2i64(double v) { if (v != v || v >= 9223372036854775808.0 || v < -9223372036854775808.0) return INT64_MIN; return (int64_t)v; }
static inline int32_t cvt_d2i32(double v) { double r = nearbyint(v); if (r != r || r >= 2147483648.0 || r < -2147483648.0) return INT32_MIN; return (int32_t)r; }
static inline int64_t cvt_d2i64(double v) { double r = nearbyint(v); if (r != r || r >= 9223372036854775808.0 || r < -9223372036854775808.0) return INT64_MIN; return (int64_t)r; }

/* 実行制御 */
void ott_unsup(uint64_t addr, const char* what) __attribute__((noreturn));
void ott_unlifted(uint64_t va) __attribute__((noreturn));
void ott_badjump(uint64_t addr, uint64_t target) __attribute__((noreturn));
void ott_dispatch(uint64_t target);   /* 間接 call: shifted VA → lifted 関数 */
extern uint64_t ott_xrip;             /* デバッグ: 直近 call 元 */
extern uint32_t ott_mxcsr;            /* CAB-138: MXCSR software shadow (既定 0x1f80, ldmxcsr/stmxcsr 用) */

/* ---- CAB-135: VEX/AVX 対応 (本体は x64c.py 側: X[16+k] = ymm 上位, xz() = 0 化) ----
 * FMA (vfmadd 等 → IEEE 正しく丸められる 1 回丸め)。libc fma() は NaN 入力で quiet bit を立てない
 * 場合がある (musl 実測: 3M 中 374 件, payload は一致) — x86 FMA は入力 NaN を quiet 化して伝播する
 * ので quiet bit を強制して一致させる (avx/fma_fuzz.c で native vfmadd213sd と 0/3M 突合)。
 * FMA3 経路の bit 突合で NaN が現れたら fma()/fmaf() をこれに差し替える。 */
static inline double ott_fma_d(double a, double b, double c) {
    double r = fma(a, b, c);
    if (r != r) { uint64_t u; memcpy(&u, &r, 8); u |= 1ULL << 51; memcpy(&r, &u, 8); }
    return r;
}
static inline float ott_fma_s(float a, float b, float c) {
    float r = fmaf(a, b, c);
    if (r != r) { uint32_t u; memcpy(&u, &r, 4); u |= 1u << 22; memcpy(&r, &u, 4); }
    return r;
}

/* vroundsd/vroundss の imm8: 0=RNE 1=down 2=up 3=trunc。bit2 = MXCSR の丸め (本 shadow は
 * 常に round-nearest 固定ゆえ nearbyint = RNE と同じ) */
static inline double ott_round_d(int imm, double v) {
    switch (imm & 3) {
    case 0: return nearbyint(v);
    case 1: return floor(v);
    case 2: return ceil(v);
    default: return (imm & 4) ? nearbyint(v) : trunc(v);
    }
}

/* PCMPISTRI control 0x40 (unsigned byte / equal-any / positive / implicit length)。
 * intel 第 1 operand = 「文字の集合 (SET)」、第 2 = 「データ (DATA)」:
 *   mask[i] = (i < ld) && (DATA[i] ∈ SET[0..ls-1])   (ls/ld = 各々の NULL 終端位置 = 有効長)
 *   ECX = mask の最上位 set bit (control bit6 = 1 → MSB first)。無ければ 16。
 *   ZF = DATA 内に NULL あり (ld < 16) / CF = mask != 0 / SF = SET 内に NULL あり (ls < 16) / OF = mask bit0
 *   (実機 150k case 突合済, work/avx/pcfuzz2.c — ZF/CF は jae/je で使用) */
static inline uint32_t ott_pcmpistri40(const uint8_t* set, uint64_t da) {
    const uint8_t* data = (const uint8_t*)A_(da);
    int ls = 16, ld = 16;
    for (int i = 0; i < 16; i++) if (set[i] == 0) { ls = i; break; }
    for (int i = 0; i < 16; i++) if (data[i] == 0) { ld = i; break; }
    uint32_t mask = 0;
    for (int i = 0; i < ld; i++)
        for (int j = 0; j < ls; j++) if (set[j] == data[i]) { mask |= 1u << i; break; }
    fZF = (uint8_t)(ld < 16);
    fCF = mask ? 1 : 0;
    fSF = (uint8_t)(ls < 16);
    fOF = (uint8_t)(mask & 1);
    fPF = 0;
    return mask ? (31u - (unsigned)__builtin_clz(mask)) : 16u;
}

#endif
