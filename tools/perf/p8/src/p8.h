/* P8 合成 plugin カーネルの共通ヘッダ (lift 風: CPU 状態をグローバルに持つ 1:1 変換スタイル) */
#ifndef P8_H
#define P8_H
#include <stdint.h>
#include <string.h>
typedef union { uint8_t b[16]; uint32_t d[4]; uint64_t q[2]; float f[4]; double df[2]; } X128;
extern uint64_t R[16];
extern X128 X[16];
extern uint8_t fZF, fSF, fCF, fOF, fPF;
enum { RAX, RCX, RDX, RBX, RSP, RBP, RSI, RDI, R8, R9, R10, R11, R12, R13, R14, R15 };
typedef float __attribute__((aligned(1))) f32u;
typedef uint32_t __attribute__((aligned(1))) u32u;
#define LDF32(a) (*(f32u*)(uintptr_t)(a))
#define STF32(a, v) (*(f32u*)(uintptr_t)(a) = (float)(v))
#define LD32(a) (*(u32u*)(uintptr_t)(a))
#define ST32(a, v) (*(u32u*)(uintptr_t)(a) = (uint32_t)(v))
#define IMG_SIZE 0x10000u
#define OFF_IN 0x1000u
#define OFF_OUT 0x2000u
#define OFF_CF 0x3000u
#define OFF_ST 0x4000u
#endif
