/* ctxfuzz.h — Kilohearts snap-in 差分ハーネス共通 (native 参照側)。
 *
 * 方式: HeartCore.core_64 の x86-64 機械語を ImageBase 0x180000000 に VA 敷設 (ms_abi 直接実行) し、
 * 「アリーナ」(固定 0x04000000, wasm 側も同アドレス) 上に this/ctx/AudioBuffer/リングバッファを構築して
 * 関数を N 回呼ぶ。各 call の (a) 呼出前に scenario が書き換えたバイト差分 (b) 引数 (c) 呼出後アリーナ全体
 * (d) 戻り値 を vectors.bin に記録し、wasm 側 (compare.mjs) が同一手順で再生して全バイト突合する。
 * lift 側の成果物は一切参照しない (循環なし)。
 */
#ifndef CTXFUZZ_H
#define CTXFUZZ_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef uint64_t u64; typedef uint32_t u32; typedef uint8_t u8; typedef int32_t i32;

#define ARENA_BASE 0x04000000UL
#define ARENA_SIZE (8UL << 20)

enum { RET_NONE = 0, RET_I32 = 1, RET_F32 = 2, RET_I64 = 3, RET_F64 = 4 };

/* arena allocator (zero-filled, 16B aligned) */
void* A(size_t n);
/* 名前付き領域 (compare 側の不一致レポート用) */
void REGION(const char* name, const void* p, size_t n);
/* 乱数 (trial 毎に seed を切る) */
u32 R32(void);
float RF(float lo, float hi);              /* 一様 float */
int RI(int lo, int hi);                    /* [lo,hi] */
float RFSPECIAL(float lo, float hi);       /* たまに 0 / ±lo / ±hi / 非正規数 / 極小 を返す */
static inline u32 fbits(float f) { u32 u; memcpy(&u, &f, 4); return u; }
static inline float bitsf(u32 u) { float f; memcpy(&f, &u, 4); return f; }

/* 呼出: rcx,rdx,r8,r9 = a0..a3, xmm0..3 低 64bit = x0..x3 (float 引数は位置 k の xmm_k に fbits を入れる) */
u64 do_call(u64 va, int rk, u64 a0, u64 a1, u64 a2, u64 a3, u64 x0, u64 x1, u64 x2, u64 x3);
#define C1(va, rk, a0)                 do_call(va, rk, (u64)(a0), 0, 0, 0, 0, 0, 0, 0)
#define C2(va, rk, a0, a1)             do_call(va, rk, (u64)(a0), (u64)(a1), 0, 0, 0, 0, 0, 0)
#define C3(va, rk, a0, a1, a2)         do_call(va, rk, (u64)(a0), (u64)(a1), (u64)(a2), 0, 0, 0, 0, 0)
#define C1F(va, rk, a0, f1)            do_call(va, rk, (u64)(a0), 0, 0, 0, 0, fbits(f1), 0, 0)
static inline u64 dbits(double d) { u64 u; memcpy(&u, &d, 8); return u; }
#define CD0(va, rk, d0)                do_call(va, rk, 0, 0, 0, 0, dbits(d0), 0, 0, 0)       /* xmm0 = double */
#define CF0(va, rk, f0)                do_call(va, rk, 0, 0, 0, 0, fbits(f0), 0, 0, 0)       /* xmm0 = float */

typedef struct { const char* name; void (*trial)(int idx); int ncalls_hint; } Scenario;
extern Scenario SCEN_LIST[];

#endif
