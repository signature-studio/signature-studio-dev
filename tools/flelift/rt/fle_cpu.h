/* fle_cpu.h — flelift (CAB-226) lifted x86-64 code runtime: CPU 状態 + 命令 helper。
 * 原型 = tools/ott/rt/ott_cpu.h (OTT で bit-exact 実績)。FLEngine 用の拡張:
 *   - DF flag (string 命令の方向), AF flag (sahf/lahf/cmpxchg 系)
 *   - Y[16]: ymm の上位 128bit (X[16] と対)
 *   - x87_cw/x87_sw (x87 制御命令モデル), mxcsr, XCR0 (xgetbv 用固定値)
 *   - SEG_GS/SEG_FS (TEB モデル), IMP_VA_BASE (IAT pseudo-VA)
 * guest pointer = wasm linear address。FLEngine は恒等写像 (VA = 0x400000+RVA がそのままアドレス)。 */
#ifndef FLE_CPU_H
#define FLE_CPU_H
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>

typedef union { uint8_t b[16]; int8_t sb[16]; uint16_t w[8]; int16_t sw[8]; uint32_t d[4]; int32_t sd[4];
                uint64_t q[2]; int64_t sq[2]; float f[4]; double df[2]; } X128;
typedef union { uint8_t b[8]; int8_t sb[8]; uint16_t w[4]; int16_t sw[4]; uint32_t d[2]; int32_t sd[2];
                uint64_t q; int64_t sq; float f[2]; } MM64;
extern uint64_t R[16];
extern X128 X[16];
extern X128 YL[16];              /* ymm 上位 128bit */
extern uint64_t M[8];            /* MMX (実機では XMM と別レジスタファイル — 実測で確認、alias しない) */
extern uint8_t fZF, fSF, fCF, fOF, fPF, fAF, fDF;
extern uint16_t x87_cw, x87_sw;
extern uint32_t mxcsr, XCR0;
extern uint64_t SEG_GS, SEG_FS;  /* TEB base (gs) / 旧形 fs */
enum { RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI, R8, R9, R10, R11, R12, R13, R14, R15 };

/* guest 補助領域 (wasm linear / native 両側で同一 VA に敷設。image 上限 0x1cc0000 と
 * emcc static base 0x10000000 の間の空き) */
#define FLE_TEB       0x1D00000ULL   /* TEB (gs base)。self 参照 + TLS */
#define FLE_TLSARRAY  0x1D10000ULL   /* TlsSlots (64 本) */
#define FLE_TLSBLOCK  0x1D20000ULL   /* 各 TLS slot の指す先 (64KB) */
#define IMP_VA_BASE   0x1D80000ULL   /* IAT slot に敷設する pseudo-VA 基準 */
#define FLE_ALOG      0x1DC0000ULL   /* alloc log (u32 count + {u32 ptr,u32 size} 列) */

typedef uint8_t __attribute__((aligned(1))) u8u;
typedef uint16_t __attribute__((aligned(1))) u16u;
typedef uint32_t __attribute__((aligned(1))) u32u;
typedef uint64_t __attribute__((aligned(1))) u64u;
typedef float __attribute__((aligned(1))) f32u;
typedef double __attribute__((aligned(1))) f64u;
#ifdef FLE_CHK
void fle_chk(uint64_t a, int line);
#define A_(a) ((uintptr_t)(fle_chk((uint64_t)(a), __LINE__), (a)))
#else
#define A_(a) ((uintptr_t)(a))
#endif
#ifdef FLE_RWATCH
/* 読出し監視 (診断用・既定無効・#4426)。読出し範囲が [FLE_RWATCH_LO, FLE_RWATCH_HI) に重なるときだけ fle_rwatch が出す (fle_cpu.c)。
 * LD* の a は RW_ と A_ で評価されるので、一時変数に取ってから使う。 */
void fle_rwatch(uint64_t a, uint32_t n, const char* file, int line);
#define RW_(a, n) fle_rwatch((uint64_t)(a), (n), __FILE__, __LINE__)
#define LD8(a) ({ uint64_t ra_ = (uint64_t)(a); RW_(ra_, 1); (*(u8u*)A_(ra_)); })
#define LD16(a) ({ uint64_t ra_ = (uint64_t)(a); RW_(ra_, 2); (*(u16u*)A_(ra_)); })
#define LD32(a) ({ uint64_t ra_ = (uint64_t)(a); RW_(ra_, 4); (*(u32u*)A_(ra_)); })
#define LD64(a) ({ uint64_t ra_ = (uint64_t)(a); RW_(ra_, 8); (*(u64u*)A_(ra_)); })
#define LDF32(a) ({ uint64_t ra_ = (uint64_t)(a); RW_(ra_, 4); (*(f32u*)A_(ra_)); })
#define LDF64(a) ({ uint64_t ra_ = (uint64_t)(a); RW_(ra_, 8); (*(f64u*)A_(ra_)); })
#else
#define LD8(a) (*(u8u*)A_(a))
#define LD16(a) (*(u16u*)A_(a))
#define LD32(a) (*(u32u*)A_(a))
#define LD64(a) (*(u64u*)A_(a))
#define LDF32(a) (*(f32u*)A_(a))
#define LDF64(a) (*(f64u*)A_(a))
#endif
#ifdef FLE_WWATCH
/* 書込み監視 (診断用・既定無効)。書込み先が監視 slot に重なるときだけ fle_wwatch が stderr に出す (fle_cpu.c)。
 * 書込み値は一時変数に取ってから監視して store する (値の式を 2 回評価しない)。
 * ST* の a は WW_ と A_ で 2 回評価されるので、副作用の無い式であること (x64c の生成アドレス式は純粋式)。 */
void fle_wwatch(uint64_t a, uint32_t n, const void* src, const char* file, int line);
#define WW_(a, n, p) fle_wwatch((uint64_t)(a), (n), (p), __FILE__, __LINE__)
#define ST8(a, v) ({ uint8_t wv_ = (uint8_t)(v); WW_(a, 1, &wv_); (*(u8u*)A_(a) = wv_); })
#define ST16(a, v) ({ uint16_t wv_ = (uint16_t)(v); WW_(a, 2, &wv_); (*(u16u*)A_(a) = wv_); })
#define ST32(a, v) ({ uint32_t wv_ = (uint32_t)(v); WW_(a, 4, &wv_); (*(u32u*)A_(a) = wv_); })
#define ST64(a, v) ({ uint64_t wv_ = (uint64_t)(v); WW_(a, 8, &wv_); (*(u64u*)A_(a) = wv_); })
#define STF32(a, v) ({ float wv_ = (float)(v); WW_(a, 4, &wv_); (*(f32u*)A_(a) = wv_); })
#define STF64(a, v) ({ double wv_ = (double)(v); WW_(a, 8, &wv_); (*(f64u*)A_(a) = wv_); })
#else
#define ST8(a, v) (*(u8u*)A_(a) = (uint8_t)(v))
#define ST16(a, v) (*(u16u*)A_(a) = (uint16_t)(v))
#define ST32(a, v) (*(u32u*)A_(a) = (uint32_t)(v))
#define ST64(a, v) (*(u64u*)A_(a) = (uint64_t)(v))
#define STF32(a, v) (*(f32u*)A_(a) = (float)(v))
#define STF64(a, v) (*(f64u*)A_(a) = (double)(v))
#endif
static inline X128 LDX(uint64_t a) {
    X128 x;
#ifdef FLE_RWATCH
    RW_(a, 16);
#endif
    memcpy(&x, (void*)A_(a), 16); return x;
}
static inline void STX(uint64_t a, X128 x) {
#ifdef FLE_WWATCH
    WW_(a, 16, &x);
#endif
    memcpy((void*)A_(a), &x, 16);
}
/* ymm (32B): lo = X[i], hi = YL[i] */
static inline void LDYSPLIT(uint64_t a, X128* lo, X128* hi) {
#ifdef FLE_RWATCH
    RW_(a, 32);
#endif
    memcpy(lo, (void*)A_(a), 16); memcpy(hi, (void*)(A_(a) + 16), 16);
}
static inline void STY(uint64_t a, X128 lo, X128 hi) {
#ifdef FLE_WWATCH
    WW_(a, 16, &lo); WW_(a + 16, 16, &hi);
#endif
    memcpy((void*)A_(a), &lo, 16); memcpy((void*)(A_(a) + 16), &hi, 16);
}

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

/* 飽和 helper (SSE2 整数 pack/加減算) */
static inline uint8_t sat_u8(int v) { return v < 0 ? 0 : (v > 255 ? 255 : (uint8_t)v); }
static inline uint16_t sat_u16(uint32_t v) { return v > 0xffff ? 0xffff : (uint16_t)v; }
static inline int16_t sat_i16(int32_t v) { return v < -32768 ? -32768 : (v > 32767 ? 32767 : (int16_t)v); }

/* 近似命令 rsqrtps: 実機 (9950X) の 12bit 近似表で bit 一致する。実体は fle_cpu.c */
uint32_t fle_rsqrt_exact(uint32_t x);

/* SSE compare → EFLAGS (comis/ucomis: ZF/PF/CF 由来, OF/SF/AF は 0 — HW も 0 を返す) */
static inline void comis_f(double a, double b, int unordered_ok) {
    (void)unordered_ok;
    if (a != a || b != b) { fZF = 1; fPF = 1; fCF = 1; }
    else if (a > b) { fZF = 0; fPF = 0; fCF = 0; }
    else if (a < b) { fZF = 0; fPF = 0; fCF = 1; }
    else { fZF = 1; fPF = 0; fCF = 0; }
    fOF = 0; fSF = 0; fAF = 0;
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
/* VEX FMA: 1 回丸め (fma)。x86 は NaN 結果の bit51 (単精度 bit22) を立てるため musl 側の NaN payload を合わせる */
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

/* 実行制御 (FLE-2 boot: hook により「戻る」経路があるため noreturn は付けない) */
void ott_unsup(uint64_t addr, const char* what);
void ott_unlifted(uint64_t va);
void ott_badjump(uint64_t addr, uint64_t target);
void ott_dispatch(uint64_t target);   /* 間接 call/jmp: VA → lifted 関数 or IAT pseudo-VA */
void imp_by_index(int k);
void ott_missing_import(const char* nm);
void fle_install_teb(void);
void fle_alog(void* p, uint64_t n);
void cpuid_model(void);
void rdtsc_model(void);
extern uint64_t ott_xrip;             /* デバッグ: 直近 call 元 */

/* FLE-2 boot: 非 0 なら fail-fast 系 (unlifted/badjump/missing import/unsup) を abort の代わりに
 * 通知する (実装は JS 例外を投げて戻らない。未設定 = 従来どおり abort)。 */
extern void (*fle_ff_hook)(const char* kind, uint64_t a);
/* FLE-2 boot: 間接 dispatch (ott_dispatch) の全呼出を観測する probe (未設定 = 何もしない)。
 * x64c.py が生成する ott_dispatch 冒頭から呼ばれる。VMT 経路/FastMM 入口/unit proc の計数に使う。 */
extern void (*fle_dispatch_probe)(uint64_t t);
/* GetProcAddress の結線 hook (未設定 = 0 を返す従来挙動)。hModule = RCX、lpProcName = RDX の値を受け、戻り値を RAX に入れる。 */
extern uint64_t (*fle_gpa_hook)(uint64_t h, uint64_t nm);

#endif
