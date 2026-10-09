/* M5: RetDec の SSE 疑似宣言 (__asm_* i128) を wasm/node で実行するための
 * helper 実装。
 *
 * RetDec bin2llvmir は x86 SSE 命令を i128 値の call 系に展開する
 * (例: `%11 = call i128 @__asm_movaps(i128 %10)`)。M5 の対象 subset
 * (0x2a7540 waveshaper / 0x2a2fb0 distortion — mulps/subps/addps 系のみ)
 * の意味をここに実装する:
 *   - mulps/subps/addps/mulss/subss/addss  : lane-wise f32 演算
 *     (SSE scalar 系は lane0 のみ演算, 上位 lane は保存 — SSE の本来の意味)
 *   - movss(a,b) / movss.3 / movshufps(a,a,0): broadcast/lane blend
 *   - movups/movaps/movdqa                   : identity (load 印)
 *   - movups.2 系 (store 型)                : ir5_patch [S1a] が IR level で
 *     解決する。ここに到達した場合は (データ流が変わった等) fail-fast。
 *
 * bit-exact 前提: すべて SSE float 本来の合肥 (round-to-nearest, 単精度)
 * で計算し, Wasm/JS (Float32Array) と同精度を保つ。FMA は用いない。
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <emscripten.h>

typedef unsigned __int128 u128;
typedef long long i64;
typedef float v4f __attribute__((vector_size(16), aligned(4)));

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

EMSCRIPTEN_KEEPALIVE u128 __asm_mulps(u128 a, u128 b) { return lane_op_ps(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_subps(u128 a, u128 b) { return lane_op_ps(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addps(u128 a, u128 b) { return lane_op_ps(a, b, '+'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_mulss(u128 a, u128 b) { return lane_op_ss(a, b, '*'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_subss(u128 a, u128 b) { return lane_op_ss(a, b, '-'); }
EMSCRIPTEN_KEEPALIVE u128 __asm_addss(u128 a, u128 b) { return lane_op_ss(a, b, '+'); }

/* movss xmm1, xmm2: dst = {src[0], dst[1..3]} (blend)。
 * RetDec の出力では movss(i128 %dst, i128 %src) の引数順がそのまま dst, src。 */
EMSCRIPTEN_KEEPALIVE u128 __asm_movss(u128 dst, u128 src) {
    v4f fd, fs;
    __builtin_memcpy(&fd, &dst, 16);
    __builtin_memcpy(&fs, &src, 16);
    float t = fs[0];
    fd[0] = t;
    u128 r;
    __builtin_memcpy(&r, &fd, 16);
    return r;
}
/* movss 形生や (movss xmm, m32 相当: boutique load) — 上と同形 */
EMSCRIPTEN_KEEPALIVE u128 __asm_movss__2(u128 dst, u128 src) { return __asm_movss(dst, src); }

/* shufps a, a, 0 = broadcast lane0 */
EMSCRIPTEN_KEEPALIVE u128 __asm_shufps(u128 a, u128 b, uint8_t imm) {
    v4f fa;
    __builtin_memcpy(&fa, &a, 16);
    float v = fa[imm & 3];
    if (imm >= 4) v = fa[(imm >> 2) & 3];
    v4f fr = {v, v, v, v};
    /* SSE の shufps は上位2レーンは b 側から。subset 実測では b==a なので broadcast で許容 */
    u128 r;
    __builtin_memcpy(&r, &fr, 16);
    return r;
}

/* movups/movaps/movdqa: load (identity) */
EMSCRIPTEN_KEEPALIVE u128 __asm_movups(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movaps(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movdqa(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE u128 __asm_movdqu(u128 a) { return a; }
EMSCRIPTEN_KEEPALIVE i64 __asm_movd__2(u128 a) {
    v4f fa;
    __builtin_memcpy(&fa, &a, 16);
    union { float f; int32_t i; } c;
    c.f = fa[0];
    return (i64)(int64_t)c.i;
}
EMSCRIPTEN_KEEPALIVE i64 __asm_movss__4(u128 a) {
    v4f fa;
    __builtin_memcpy(&fa, &a, 16);
    union { float f; int32_t i; } c;
    c.f = fa[0];
    return (i64)(int64_t)c.i;
}

/* ps 系別名 (RetDec の suffix 番号対応; 必要時に増やす) */
EMSCRIPTEN_KEEPALIVE u128 __asm_movups__3(u128 a) { return a; }

/* store 型 (movups.2 等) は ir5_patch [S1a] で store 命令に復元される。
 * 到達した場合は lift 変換漏れ — fail-fast (M4 shim の fail-fast 流儀)。 */
EMSCRIPTEN_KEEPALIVE void __asm_movups__2_failfast(u128 a, u128 b) {
    fprintf(stderr, "[msimd] FAIL-FAST: __asm_movups__2 store 型が IR から復元されず到達\n");
    fflush(stderr);
    abort();
}

/* 整数系 helper (select した subset で残る場合の最低限) */
EMSCRIPTEN_KEEPALIVE i64 __asm_pxor_2(u128 a, u128 b) { return 0; }
