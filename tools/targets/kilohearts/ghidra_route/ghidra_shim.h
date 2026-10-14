/* Ghidra decompile 出力 (work/ghidra/out/*.c) を emcc でビルドするための最小 shim (KH-5)。
 * Ghidra 固有の型名・組込み (undefined*, longlong, CONCAT44, 128bit ベクタ `auVarN._4_4_`) だけを定義する。
 * ghidra_to_c.py が `undefined1 auVarN [16]` → V128 / `X = auVarN << 0x20` → v128_store_shl32 に機械書換えする。 */
#ifndef GHIDRA_SHIM_H
#define GHIDRA_SHIM_H
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <emscripten.h>

typedef uint8_t undefined1;
typedef uint16_t undefined2;
typedef uint32_t undefined4;
typedef uint64_t undefined8;
typedef long long longlong;
typedef unsigned long long ulonglong;
typedef unsigned int uint;
typedef unsigned char byte;
typedef unsigned short ushort;

typedef struct { uint8_t v[12]; } B12;
typedef union {
    uint8_t b[16];
    struct { float _0_4_, _4_4_, _8_4_, _12_4_; };
    struct { uint64_t _0_8_, _8_8_; };
    struct { uint32_t _p4; B12 _4_12_; };
} V128;

static inline void v128_store_shl32(void* dst, V128 v) {
    float o[4] = {0.0f, v._0_4_, v._4_4_, v._8_4_};
    memcpy(dst, o, 16);
}
/* x86 MXCSR (制御/状態レジスタ) は wasm に無い。Resonator の callee 2 件 (180fd6498 読み・180fd662c 書き) が参照するため、
 * 状態変数として持つ。初期値 0x1F80 は x86 の既定値 (全例外マスク・丸め=最近接・FTZ/DAZ 無効)。意味は突合で検証する。 */
static uint MXCSR = 0x1F80;
/* Win API GetLastError/SetLastError (Resonator の 973/1001 行)。意味は未確定。状態変数として持ち、突合で検証する (REPORT 参照)。 */
static uint LastErrorState = 0;
static inline uint GetLastError(void) { return LastErrorState; }
static inline void SetLastError(uint v) { LastErrorState = v; }
static inline ulonglong CONCAT44(uint hi, uint lo) { return ((ulonglong)hi << 32) | lo; }
/* float 引数で CONCAT44(float, float) が出る場合 (ビット列として連結) */
#define CONCAT44F(hi, lo) CONCAT44(f2u(hi), f2u(lo))
static inline uint f2u(float f) { uint u; memcpy(&u, &f, 4); return u; }
static inline float u2f(uint u) { float f; memcpy(&f, &u, 4); return f; }
#endif
