/* Ghidra decompile 出力 (work/ghidra/out/*.c) を emcc でビルドするための最小 shim (KH-5)。
 * Ghidra 固有の型名・組込み (undefined*, longlong, CONCAT44, 128bit ベクタ `auVarN._4_4_`) だけを定義する。
 * ghidra_to_c.py が `undefined1 auVarN [16]` → V128 / `X = auVarN << 0x20` → v128_store_shl32 に機械書換えする。 */
#ifndef GHIDRA_SHIM_H
#define GHIDRA_SHIM_H
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
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
typedef longlong (*code)();
typedef unsigned char undefined;
typedef signed char sbyte;

typedef struct { uint8_t v[12]; } B12;
typedef union {
    uint8_t b[16];
    struct { float _0_4_, _4_4_, _8_4_, _12_4_; };
    struct { uint64_t _0_8_, _8_8_; };
    struct { double _0_8_d, _8_8_d; };
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
/* double のビット列 (callee の ulonglong 引数 = xmm0 のビット列。patches.py ABI 規則が使う) */
static inline ulonglong d2u(double d) { ulonglong u; memcpy(&u, &d, 8); return u; }
static inline double u2d(ulonglong u) { double d; memcpy(&d, &u, 8); return d; }
/* Ghidra の ABS(double) = 符号ビット clear (stereo の機械語 btr r,0x3f と一致) = fabs */
static inline double ABS(double x) { return fabs(x); }
/* movd xmm,r32 相当: 32bit を下位レーンに置き、残りは 0 (stereo の ZEXT416) */
static inline V128 ZEXT416(uint v) { V128 r; memset(&r, 0, sizeof r); memcpy(r.b, &v, 4); return r; }
/* MAXPS dst,src (stereo 180fdc..81 `maxps xmm3,[rip+..]`): lane 毎に dst > src ? dst : src (非順序・NaN は src) */
static inline V128 maxps(V128 a, V128 b) {
    V128 r;
    for (int i = 0; i < 4; i++) {
        float x, y, z;
        memcpy(&x, a.b + 4 * i, 4);
        memcpy(&y, b.b + 4 * i, 4);
        z = (x > y) ? x : y;
        memcpy(r.b + 4 * i, &z, 4);
    }
    return r;
}
/* VPSRLDQ xmm,xmm,imm (128bit を imm バイト右シフト、上位は 0)。stereo 180fdc4cf `vpsrldq xmm0,xmm0,8` で確認 */
static inline V128 vpsrldq_avx(V128 s, int n) {
    V128 r; memset(&r, 0, sizeof r);
    for (int i = 0; i + n < 16; i++) r.b[i] = s.b[i + n];
    return r;
}
/* SUB84(x, off): x の byte 位置 off から 4 byte の切り出し (little-endian)。lvalue を取る。 */
static inline uint kh_sub84(const void *p, int off) { uint r; memcpy(&r, (const unsigned char *)p + off, 4); return r; }
#define SUB84(x, off) kh_sub84(&(x), (off))
/* ZEXT816(v): 64bit を下位に置き上位 64bit は 0 (movq xmm,r64) */
static inline V128 ZEXT816(ulonglong v) { V128 r; memset(&r, 0, sizeof r); memcpy(r.b, &v, 8); return r; }
/* MINPS dst,src: lane 毎に dst < src ? dst : src (NaN は src)。maxps と対称 */
static inline V128 minps(V128 a, V128 b) {
    V128 r;
    for (int i = 0; i < 4; i++) {
        float x, y, z;
        memcpy(&x, a.b + 4 * i, 4);
        memcpy(&y, b.b + 4 * i, 4);
        z = (x < y) ? x : y;
        memcpy(r.b + 4 * i, &z, 4);
    }
    return r;
}
/* VPSUBQ / VPSUBD (src1 - src2, lane 毎・wrap)。Ghidra の pcodeop は vvvv (src1) を先頭に取る */
static inline V128 vpsubq_avx(V128 a, V128 b) {
    V128 r;
    for (int i = 0; i < 2; i++) { uint64_t x, y, z; memcpy(&x, a.b + 8 * i, 8); memcpy(&y, b.b + 8 * i, 8); z = x - y; memcpy(r.b + 8 * i, &z, 8); }
    return r;
}
static inline V128 vpsubd_avx(V128 a, V128 b) {
    V128 r;
    for (int i = 0; i < 4; i++) { uint32_t x, y, z; memcpy(&x, a.b + 4 * i, 4); memcpy(&y, b.b + 4 * i, 4); z = x - y; memcpy(r.b + 4 * i, &z, 4); }
    return r;
}
/* VPAND / VPOR (128bit 論理積・論理和) */
static inline V128 vpand_avx(V128 a, V128 b) { V128 r; for (int i = 0; i < 16; i++) r.b[i] = a.b[i] & b.b[i]; return r; }
static inline V128 vpor_avx(V128 a, V128 b) { V128 r; for (int i = 0; i < 16; i++) r.b[i] = a.b[i] | b.b[i]; return r; }
/* VPSRLQ xmm,xmm,imm8: 64bit lane 毎の論理右シフト。imm >= 64 は 0 */
static inline V128 vpsrlq_avx(V128 s, int n) {
    V128 r;
    for (int i = 0; i < 2; i++) {
        uint64_t x, z;
        memcpy(&x, s.b + 8 * i, 8);
        z = (n >= 0 && n < 64) ? (x >> n) : 0;
        memcpy(r.b + 8 * i, &z, 8);
    }
    return r;
}
/* VCVTDQ2PD: 下位 2 個の int32 を 2 個の double へ (lane 0 が下位) */
static inline V128 vcvtdq2pd_avx(V128 s) {
    V128 r; int32_t a, b; double d0, d1;
    memcpy(&a, s.b, 4); memcpy(&b, s.b + 4, 4);
    d0 = (double)a; d1 = (double)b;
    memcpy(r.b, &d0, 8); memcpy(r.b + 8, &d1, 8);
    return r;
}
/* VCVTPD2DQ: 2 個の double を現在の丸め (既定 = 最近接偶数) で int32 へ。NaN・範囲外は 0x80000000 (integer indefinite)。上位 64bit は 0 */
static inline int32_t kh_cvt_d2i(double d) {
    double r = rint(d);
    if (isnan(d) || r < -2147483648.0 || r > 2147483647.0) return INT32_MIN;
    return (int32_t)r;
}
static inline V128 vcvtpd2dq_avx(V128 s) {
    V128 r; double d0, d1; int32_t i0, i1;
    memcpy(&d0, s.b, 8); memcpy(&d1, s.b + 8, 8);
    i0 = kh_cvt_d2i(d0); i1 = kh_cvt_d2i(d1);
    memset(&r, 0, sizeof r);
    memcpy(r.b, &i0, 4); memcpy(r.b + 4, &i1, 4);
    return r;
}
/* VSHUFPS dst,src1,src2,imm8: dst[0]=a[imm1:0]・dst[1]=a[imm3:2]・dst[2]=b[imm5:4]・dst[3]=b[imm7:6] */
static inline V128 vshufps_avx(V128 a, V128 b, int imm) {
    V128 r; uint32_t sa[4], sb[4], d[4];
    memcpy(sa, a.b, 16); memcpy(sb, b.b, 16);
    d[0] = sa[imm & 3]; d[1] = sa[(imm >> 2) & 3]; d[2] = sb[(imm >> 4) & 3]; d[3] = sb[(imm >> 6) & 3];
    memcpy(r.b, d, 16);
    return r;
}
/* VPMOVSXDQ: 下位 2 個の int32 を符号拡張して 2 個の int64 へ */
static inline V128 vpmovsxdq_avx(V128 s) {
    V128 r; int32_t a, b; int64_t x, y;
    memcpy(&a, s.b, 4); memcpy(&b, s.b + 4, 4);
    x = a; y = b;
    memcpy(r.b, &x, 8); memcpy(r.b + 8, &y, 8);
    return r;
}
/* swi(n) = x86 の int n (int 3 = breakpoint, int 0x29 = __fastfail)。どちらも戻らない trap。到達時は abort (fail-fast) */
static inline void *kh_swi_fail(void) { abort(); return 0; }
#define swi(n) kh_swi_fail()
/* x86 `mul r64` (rdx:rax = rax × r64) を 128bit ベクタの `*` と印字した形 (stereo 180fdc470・180fdfdb0)。
 * 呼出し直前に両オペランドの上位 qword は 0 (`_8_8_ = 0`) なので、積は 64×64→128 の符号なし積。 */
static inline V128 v128_mul64(V128 a, V128 b) {
    unsigned __int128 p = (unsigned __int128)a._0_8_ * b._0_8_;
    V128 r; memcpy(r.b, &p, 16);
    return r;
}
/* 128bit 整数加算 (機械語の add/adc の繰上がりを含む)。 */
static inline V128 v128_add(V128 a, V128 b) {
    unsigned __int128 x, y;
    memcpy(&x, a.b, 16); memcpy(&y, b.b, 16);
    x += y;
    V128 r; memcpy(r.b, &x, 16);
    return r;
}
/* Ghidra SUBPIECE: SUB168(x, 0) = 下位 8 バイト, SUB168(x, 8) = 上位 8 バイト。 */
static inline ulonglong SUB168(V128 v, int off) { ulonglong r; memcpy(&r, v.b + off, 8); return r; }
#endif
