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
typedef void code;
typedef unsigned char undefined;
typedef signed char sbyte;

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
/* Win API GetLastError/SetLastError (Resonator の 973/1001 行)。native harness (scen_khmath/scen_khmaster) と同じく常に 0・SetLastError は無視。 */
static inline uint GetLastError(void) { return 0; }
static inline void SetLastError(uint v) { (void)v; }
/* LOCK()/UNLOCK(): Ghidra は x86 の lock 接頭辞付き命令の範囲を印字する (Delay 20 箇所)。wasm と native harness は
 * 単一スレッドで、範囲内のメモリ操作の原子性は観測できない。よって no-op。 */
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
/* Win API fail-fast stub (Delay で参照される 21 件)。到達時は abort する (突合で検出)。引数は評価しない
 * (abort で実行が止まるため副作用が観測されない)。意味は実装しない。 */
static inline longlong kh_api_fail(void) { abort(); return 0; }
#define HeapAlloc(...) ((void *)kh_api_fail())
#define HeapFree(...) ((int)kh_api_fail())
#define GetCurrentProcess(...) ((void *)kh_api_fail())
#define IsProcessorFeaturePresent(...) ((int)kh_api_fail())
#define TerminateProcess(...) ((int)kh_api_fail())
#define ExitProcess(...) ((void)kh_api_fail())
#define UnhandledExceptionFilter(...) ((long)kh_api_fail())
#define SetUnhandledExceptionFilter(...) ((void *)kh_api_fail())
#define RtlVirtualUnwind(...) ((void *)kh_api_fail())
#define RtlLookupFunctionEntry(...) ((void *)kh_api_fail())
#define RtlCaptureContext(...) ((void)kh_api_fail())
#define RtlPcToFileHeader(...) ((void *)kh_api_fail())
#define RaiseException(...) ((void)kh_api_fail())
#define GetProcAddress(...) ((ulonglong)kh_api_fail())
#define GetModuleHandleW(...) ((longlong)kh_api_fail())
#define GetModuleHandleExW(...) ((int)kh_api_fail())
#define LoadLibraryExW(...) ((longlong)kh_api_fail())
#define FreeLibrary(...) ((int)kh_api_fail())
#define IsDebuggerPresent(...) ((int)kh_api_fail())
#define EnterCriticalSection(...) ((void)kh_api_fail())
#define LeaveCriticalSection(...) ((void)kh_api_fail())
static inline ulonglong CONCAT44(uint hi, uint lo) { return ((ulonglong)hi << 32) | lo; }
/* float 引数で CONCAT44(float, float) が出る場合 (ビット列として連結) */
#define CONCAT44F(hi, lo) CONCAT44(f2u(hi), f2u(lo))
static inline uint f2u(float f) { uint u; memcpy(&u, &f, 4); return u; }
static inline float u2f(uint u) { float f; memcpy(&f, &u, 4); return f; }
#endif
