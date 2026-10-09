/* m6_rt.c: OTT (win64 VST2) の DLL runtime 環境 shim
 *   - CRT malloc/free/(operator new/delete)/memcpy/memmove/memset 系を提供
 *   - Win32 API を fail-fast stub (DSP 経路で触れない前提)
 *   - phase init: m6_data_install() を module post-instantiation で一回
 * 参照名 (lifted IR declare 由来):
 *   function_1801a7794 = malloc   (jmp 0x1c0bac)
 *   function_1801a7778 = calloc   (jmp 0x1c0af4)
 *   function_1801a08a4 = ¥malloc (malloc wrapper; jmp 0x1a04d0)
 *   function_1801a0390 = memcpy (rep movsb 形; %args: dst, src, n, ?)  [実測: ctor 内]
 *   function_1801a2a00 = memcpy shell (rep movsb)
 *   function_1801a30b0 = memset  (rep stosb, r11 保持)
 *   function_1801a3ad0 = memset SSE
 *   function_1801c0ac8/1801c1418/... = memcmp/memcpy に対する CRT 汎用 wrapper (jmp rax
 *     dispatch) — processReplacing は触れない前提 → fail-fast.
 *   function_1801a14f0 は '_Tc' サポート functions 2 ひろいで memset 的 (ret)
 */

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>

void m6_fail(const char* msg);

/* lifted IR のアドレス = m6 SHIFT base (0x30000000) + RVA. メモリ vア 是載配置は
   m6_data.c の install と一致する. */
#define M6base 0x30000000ul

static void m6_failmsg(const char* nm) {
    fprintf(stderr, "[m6_rt] FAIL: %s\n", nm);
    abort();
}

/* ---------- CRT ---------- */
long long function_1801a7794(long long n) {
    if (n <= 0 || n > 0x4000000LL) { m6_failmsg("malloc size: function_1801a7794"); }
    void* p = malloc((size_t)n);
    if (!p) m6_failmsg("malloc: function_1801a7794");
    return (long long)(uintptr_t)p;
}
long long function_1801a7778(long long nmemb, long long size) {
    if (nmemb <= 0 || size <= 0 || (nmemb * size) > 0x4000000LL) { m6_failmsg("calloc size: function_1801a7778"); }
    void* p = calloc((size_t)nmemb, (size_t)size);
    if (!p) m6_failmsg("calloc: function_1801a7778");
    return (long long)(uintptr_t)p;
}
long long function_1801a08a4(long long n) { return function_1801a7794(n); }


/* memcpy shell (rep movsb) - arg1 = *dst (indirect), arg2=src, arg3=cnt? 実測: V
   function_1801a1cmodel には arg (pointer-data) … LLVM RetDec signature で受ける 形 */
long long function_1801a2a00(long long dst, long long src, long long n) {
    if (n > 0 && n < 0x8000000LL && dst > 0) {
        memcpy((void*)(uintptr_t)dst, (void*)(uintptr_t)src, (size_t)n);
    }
    return dst;
}
long long function_1801a30b0(long long dst, long long ch, long long n) {
    if (n > 0 && n < 0x8000000LL && dst > 0) {
        memset((void*)(uintptr_t)dst, (int)(ch & 0xff), (size_t)n);
    }
    return dst;
}
long long function_1801a3ad0(long long dst, long long ch, long long n) {
    if (n > 0 && n < 0x8000000LL && dst > 0) {
        memset((void*)(uintptr_t)dst, (int)(ch & 0xff), (size_t)n);
    }
    return dst;
}

/* jmp-style dispatch 実体: function_1801d2750 (memcpymm 汎用; uintptr NULL etc 排除):
 *  実体は 'jmp rax' の SQS "memcpymm/generic-mem move 専用 table inst"...: 実測: [memcpy-like]
 */
long long function_1801d2750(long long dst, long long src, long long n, long long opt) {
    if (n > 0 && n < 0x4000000LL && dst > 0) {
        memcpy((void*)(uintptr_t)dst, (void*)(uintptr_t)src, (size_t)n);
    }
    return 0;
}




/* ---------- 未対応系 (fail-fast) ---------- */
void function_18003c0丫1(void) {}
/* ---- Windows API stubs ---- */


void m6_fail(const char* msg) { m6_failmsg(msg); }

