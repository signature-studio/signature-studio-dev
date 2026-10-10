/* host_wasm.c — wasm 側 host: Win32 shim 外部関数 + 間接 call (host vtable) + memmove + stub trap。 */
#include <emscripten.h>
#include "fa_win_shim.h"
typedef unsigned __int128 u128;
typedef unsigned int u32;
#define X(name, body) EMSCRIPTEN_KEEPALIVE u64 win_kernel32_##name(u64 a, u64 b, u64 c, u64 d) { return body(a, b, c, d); }
FA_SHIM_TABLE(X)
#undef X
EMSCRIPTEN_KEEPALIVE u64 fa_memmove(u64 dst, u64 src, u64 n, u64 d) { memmove((void*)(uintptr_t)dst, (void*)(uintptr_t)src, (size_t)n); return dst; }
EMSCRIPTEN_KEEPALIVE void fa_stub_trap(long long va) { __builtin_trap(); }

/* fa_vector_grow — std::vector<float>::_Reallocate (0x1803ded20) の C 等価実装。
 * machine 側 (0x1803ded20 + 0x1803de3e0) の観測関数 (capacity 1.5 倍ポリシ, 要素 4B, prefix/elem/suffix の
 * 3 部 copy, 旧 buffer の HeapFree) を再現する。mlift lift 版の grow 経路で OOB が残るための差替え。
 *   rcx = vector {begin, end, cap}, rdx = 挿入位置 ptr, r8 = 挿入要素 ptr
 * 戻り: なし (vector を in-place 更新) */
EMSCRIPTEN_KEEPALIVE u64 fa_vector_grow(u64 vec, u64 ins, u64 elem, u64 d) {
    u64 begin = *(u64*)(uintptr_t)vec;
    u64 end = *(u64*)(uintptr_t)(vec + 8);
    u64 cap = *(u64*)(uintptr_t)(vec + 16);
    u64 count = (end - begin) >> 2;
    u64 need = count + 1;
    u64 newcap = cap + (cap >> 1);
    if (newcap < need) newcap = need;
    if (newcap == 0) newcap = 1;
    u64 nbuf = (u64)(uintptr_t)malloc((size_t)(newcap * 4));
    u64 off = (ins - begin) >> 2;                       /* 挿入 index */
    if (off > count) off = count;
    memcpy((void*)(uintptr_t)nbuf, (void*)(uintptr_t)begin, (size_t)(off * 4));
    *(u32*)(uintptr_t)(nbuf + off * 4) = *(u32*)(uintptr_t)elem;
    memcpy((void*)(uintptr_t)(nbuf + (off + 1) * 4), (void*)(uintptr_t)ins, (size_t)((count - off) * 4));
    if (begin) free((void*)(uintptr_t)begin);
    *(u64*)(uintptr_t)vec = nbuf;
    *(u64*)(uintptr_t)(vec + 8) = nbuf + (count + 1) * 4;
    *(u64*)(uintptr_t)(vec + 16) = nbuf + newcap * 4;
    return 0;
}

/* fa_mxcsr_get/set — stmxcsr/ldmxcsr (0x18106a3a0/0x18106a3ba) の C 等価 (丸めモード制御の差替え) */
static unsigned int g_mxcsr = 0x1f80;
EMSCRIPTEN_KEEPALIVE u64 fa_mxcsr_get(u64 a, u64 b, u64 c, u64 d) { return g_mxcsr; }
EMSCRIPTEN_KEEPALIVE u64 fa_mxcsr_set(u64 v, u64 b, u64 c, u64 d) { g_mxcsr = (unsigned int)v; return 0; }

/* host オブジェクトの仮想関数: token 0x7F000001 = 「this+8 の float を xmm0 に返す」 */
#define HOST_TOKEN_GETF 0x7F000001ULL
static u128 g_host_x0;
EMSCRIPTEN_KEEPALIVE long long fa_host_icall(long long t, long long a, long long b, long long c, long long d, u128 x0, u128 x1) {
    if ((u64)t == HOST_TOKEN_GETF) { float f; memcpy(&f, (char*)(uintptr_t)a + 8, 4); g_host_x0 = 0; memcpy(&g_host_x0, &f, 4); return 0; }
    __builtin_trap();
}
EMSCRIPTEN_KEEPALIVE u128 fa_host_icall_xmm0(void) { return g_host_x0; }
