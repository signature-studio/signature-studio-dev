/* msimd_core.h — __asm_* i128 helper の共通実装 (inline 用)
 * (tools/m5/msimd.c の本体; RetDec SSE 疑似宣言の f32 語義だけを提供)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#if defined(__EMSCRIPTEN__)
#include <emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

typedef unsigned __int128 u128;
typedef long long i64;
typedef int i32;
typedef signed char int8_t_;
typedef float v4f __attribute__((vector_size(16)));

static inline u128 lane_op_ps(u128 a, u128 b, char op) {
    v4f fa, fb, fr;
    __builtin_memcpy(&fa, &a, 16);
    __builtin_memcpy(&fb, &b, 16);
    for (int i = 0; i < 4; i++) {
        if (op == '*') fr[i] = fa[i] * fb[i];
        else if (op == '-') fr[i] = fa[i] - fb[i];
        else fr[i] = fa[i] + fb[i];
    }
    u128 r;
    __builtin_memcpy(&r, &fr, 16);
    return r;
}
static inline u128 lane_op_ss(u128 a, u128 b, char op) {
    v4f fa, fb, fr;
    __builtin_memcpy(&fa, &a, 16);
    __builtin_memcpy(&fb, &b, 16);
    if (op == '*') fr[0] = fa[0] * fb[0];
    else if (op == '-') fr[0] = fa[0] - fb[0];
    else fr[0] = fa[0] + fb[0];
    for (int i = 1; i < 4; i++) fr[i] = fa[i];
    u128 r;
    __builtin_memcpy(&r, &fr, 16);
    return r;
}
static inline float lane_extract0(u128 a) {
    v4f fa; __builtin_memcpy(&fa, &a, 16); return fa[0];
}
static inline u128 lane_blend0(u128 dst, u128 src) {
    v4f fd, fs; __builtin_memcpy(&fd, &dst, 16); __builtin_memcpy(&fs, &src, 16);
    fd[0] = fs[0];
    u128 r; __builtin_memcpy(&r, &fd, 16); return r;
}
static inline u128 lane_broadcast0(u128 a) {
    v4f fa, fr; __builtin_memcpy(&fa, &a, 16);
    fr = (v4f){fa[0], fa[0], fa[0], fa[0]};
    u128 r; __builtin_memcpy(&r, &fr, 16); return r;
}
static inline i64 lane_to_i64_l0(u128 a) {
    union { float f; int32_t i; } c; c.f = lane_extract0(a);
    return (i64)c.i;
}
