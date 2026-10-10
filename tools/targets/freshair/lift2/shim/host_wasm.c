/* host_wasm.c — wasm 側 host: Win32 shim 外部関数 + 間接 call (host vtable) + memmove + stub trap。
 * FA_WIN_STUBS 定義時は gen_win_stubs.py 生成の weak 既定 (PE import 表の全 API, 0 戻り) も有効化
 * (FA-2c: framework closure が多数の未対応 API を呼ぶため。特定実装は strong で上書き)。 */
#include <emscripten.h>
#include "fa_win_shim.h"
typedef unsigned __int128 u128;
typedef unsigned int u32;
#define X(name, body) EMSCRIPTEN_KEEPALIVE u64 win_kernel32_##name(u64 a, u64 b, u64 c, u64 d) { return body(a, b, c, d); }
FA_SHIM_TABLE(X)
#undef X
EMSCRIPTEN_KEEPALIVE u64 fa_memmove(u64 dst, u64 src, u64 n, u64 d) { memmove((void*)(uintptr_t)dst, (void*)(uintptr_t)src, (size_t)n); return dst; }
EMSCRIPTEN_KEEPALIVE void fa_heap_zero(int v) { g_heap_zero = v; }
EMSCRIPTEN_KEEPALIVE void fa_stub_trap(long long va) { __builtin_trap(); }

/* fa_vector_grow は削除 (FA-2b): 旧実装は harness の canary 内部ポインタを free する OOB と
 * 容量計算 (vec+16 のポインタ値を容量と混同) の 2 重の欠陥を抱えていた。根因修復 (comp_harness.mjs の
 * vbuf を plain malloc へ) により machine 側 grow (0x1803ded20 → 0x1803de100 → 0x1803de3e0) を
 * lift 済みコードのまま実行できており, C 差替えは不要になった (REPORT §5.1)。
 * 教訓: C「等価」差替えは機械語の意味論を正確に写像しないと新たな破れを生む — machine lift を優先する。 */

/* fa_mxcsr_get/set — stmxcsr/ldmxcsr (0x18106a3a0/0x18106a3ba) の C 等価 (丸めモード制御の差替え) */
static unsigned int g_mxcsr = 0x1f80;
EMSCRIPTEN_KEEPALIVE u64 fa_mxcsr_get(u64 a, u64 b, u64 c, u64 d) { return g_mxcsr; }
EMSCRIPTEN_KEEPALIVE u64 fa_mxcsr_set(u64 v, u64 b, u64 c, u64 d) { g_mxcsr = (unsigned int)v; return 0; }

/* host オブジェクトの仮想関数: token 0x7F000001 = 「this+8 の float を xmm0 に返す」 */
#define HOST_TOKEN_GETF 0x7F000001ULL
static u128 g_host_x0;
EMSCRIPTEN_KEEPALIVE void fa_icall_site(long long va) { fprintf(stderr, "icall site %llx\n", (unsigned long long)va); }
EMSCRIPTEN_KEEPALIVE long long fa_host_icall(long long t, long long a, long long b, long long c, long long d, u128 x0, u128 x1) {
    if ((u64)t == HOST_TOKEN_GETF) { float f; memcpy(&f, (char*)(uintptr_t)a + 8, 4); g_host_x0 = 0; memcpy(&g_host_x0, &f, 4); return 0; }
    fprintf(stderr, "icall unknown t=%llx a=%llx b=%llx c=%llx\n", (unsigned long long)t, (unsigned long long)a, (unsigned long long)b, (unsigned long long)c);
    /* FA_ICALL_SOFT=1: 未解決 icall を 0 戻りで続行 (「あとどの VA が必要か」を 1 回の実行で列挙する診断用) */
    if (getenv("FA_ICALL_SOFT")) return 0;
    __builtin_trap();
}
EMSCRIPTEN_KEEPALIVE u128 fa_host_icall_xmm0(void) { return g_host_x0; }
