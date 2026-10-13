/* P8 合成 plugin カーネル。lift 風 (R[]/X[]/flag をグローバル経由、guest pointer = 整数 → ポインタ、
 * guest 間接 call = 関数 table 経由)。process = 2ch x 128f を NST 段の biquad で処理。
 * ADDR_ABS : guest image は固定 linear address GBASE (現行 lift: guest VA == wasm linear address)
 * ADDR_BASED: guest image は module 内の配列 (相対配置可能 = SIDE_MODULE 向け。rebase 済み lift を模す)
 * PFX      : 静的に N 個リンクするときの symbol 接頭辞 */
#include "p8.h"
#define CAT_(a, b) a##b
#define CAT(a, b) CAT_(a, b)
#ifndef PFX
#define PFX
#endif
#define N_(x) CAT(PFX, x)
#ifndef PID
#define PID 0
#endif
#ifndef NST
#define NST 32
#endif

#if defined(ADDR_ABS)
#define GIMG ((uintptr_t)(GBASE))
#else
static uint8_t N_(guest)[IMG_SIZE] __attribute__((aligned(64)));
#define GIMG ((uintptr_t)N_(guest))
#endif
#define GA(off) (GIMG + (off))

/* 1 stage = lift された 1 関数。引数は R[RSI]=in va, R[RDI]=out va, R[RDX]=係数 va, R[RCX]=frames, R[R8]=状態 va */
#define STAGE_BODY(K) do { \
  R[RAX] = 0; \
  do { \
    X[0].f[0] = LDF32(R[RSI] + R[RAX] * 4);                       /* movss xmm0,[rsi+rax*4] */ \
    X[1].f[0] = LDF32(R[RDX]);                                    /* movss xmm1,[b0] */ \
    X[1].f[0] = X[1].f[0] * X[0].f[0];                            /* mulss */ \
    X[2].f[0] = LDF32(R[R8]);                                     /* movss xmm2,[z1] */ \
    X[1].f[0] = X[1].f[0] + X[2].f[0];                            /* addss */ \
    X[3].f[0] = LDF32(R[RDX] + 4);                                /* b1 */ \
    X[3].f[0] = X[3].f[0] * X[0].f[0]; \
    X[4].f[0] = LDF32(R[RDX] + 8);                                /* a1 */ \
    X[4].f[0] = X[4].f[0] * X[1].f[0]; \
    X[3].f[0] = X[3].f[0] - X[4].f[0];                            /* subss */ \
    X[5].f[0] = LDF32(R[R8] + 4);                                 /* z2 */ \
    X[3].f[0] = X[3].f[0] + X[5].f[0]; \
    STF32(R[R8], X[3].f[0]);                                      /* movss [z1],xmm3 */ \
    X[6].f[0] = LDF32(R[RDX] + 12) * X[0].f[0] - LDF32(R[RDX] + 16) * X[1].f[0]; \
    STF32(R[R8] + 4, X[6].f[0]); \
    STF32(R[RDI] + R[RAX] * 4, X[1].f[0] + (float)((K) + PID * 256) * 1e-30f);  /* movss [rdi+rax*4],xmm1 */ \
    R[RAX] = R[RAX] + 1;                                          /* inc rax */ \
    { uint64_t a_ = R[RAX], b_ = R[RCX], r_ = a_ - b_; fZF = (r_ == 0); fCF = (a_ < b_); fSF = (r_ >> 63) & 1; fOF = 0; fPF = !__builtin_parity((uint8_t)r_); } /* cmp rax,rcx */ \
  } while (!fZF);                                                 /* jne */ \
} while (0)

#include "stages.h" /* STAGE(n) x 256 と tab[] (生成物) */

__attribute__((used, visibility("default"))) void N_(plg_init)(void) {
  memset((void*)GA(0), 0, IMG_SIZE);
  for (int s = 0; s < NST; s++) {
    ST32(GA(OFF_CF + s * 32 + 0), 0x3f000000u); ST32(GA(OFF_CF + s * 32 + 4), 0x3e800000u);
    ST32(GA(OFF_CF + s * 32 + 8), 0xbe000000u); ST32(GA(OFF_CF + s * 32 + 12), 0x3d800000u);
    ST32(GA(OFF_CF + s * 32 + 16), 0xbd000000u);
  }
}
__attribute__((used, visibility("default"))) uint32_t N_(plg_in)(void) { return (uint32_t)GA(OFF_IN); }
__attribute__((used, visibility("default"))) uint32_t N_(plg_out)(void) { return (uint32_t)GA(OFF_OUT); }

__attribute__((used, visibility("default"))) void N_(plg_process)(void) {
  for (int ch = 0; ch < 2; ch++) {
    uint64_t src = GA(OFF_IN + ch * 512), dst = GA(OFF_OUT + ch * 512);
    for (int s = 0; s < NST; s++) {
      R[RSI] = (s == 0) ? src : dst; R[RDI] = dst; R[RDX] = GA(OFF_CF + s * 32);
      R[RCX] = 128; R[R8] = GA(OFF_ST + (ch * NST + s) * 8);
      N_(tab)[(s * 31) & 255]();
    }
  }
}
