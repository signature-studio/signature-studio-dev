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
/* alloc log (ott): 0x35f00000 = u32 count, 0x35f00008.. = {u32 ptr, u32 size} — native 参照との heap レイアウト再生用 */
#define OTT_ALOG ((volatile uint32_t*)0x35f00000)
static void ott_alog(void* p, long long n) {
    uint32_t c = OTT_ALOG[0];
    if (c < 0x8000u) { OTT_ALOG[2 + 2 * c] = (uint32_t)(uintptr_t)p; OTT_ALOG[3 + 2 * c] = (uint32_t)n; OTT_ALOG[0] = c + 1; }
}
long long function_1801a7794(long long n) {
    if (n <= 0 || n > 0x4000000LL) { m6_failmsg("malloc size: function_1801a7794"); }
    void* p = malloc((size_t)n);
    if (!p) m6_failmsg("malloc: function_1801a7794");
    ott_alog(p, n);
    return (long long)(uintptr_t)p;
}
long long function_1801a7778(long long nmemb, long long size) {
    if (nmemb <= 0 || size <= 0 || (nmemb * size) > 0x4000000LL) { m6_failmsg("calloc size: function_1801a7778"); }
    void* p = calloc((size_t)nmemb, (size_t)size);
    if (!p) m6_failmsg("calloc: function_1801a7778");
    ott_alog(p, nmemb * size);
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
/* function_1801a3ad0 — 宣言上は (i64,i64) の 2 引数 (function_1801c2674 から
 *   (ptr, 101) で call; 実体は strnlen 相当 byte-scan の可能性, closure 部分リフト
 *   では引数解析が破損)。DSP 経路外 → 到達時 fail-fast (signemature 一致のみ必須)。 */
long long function_1801a3ad0(long long a, long long b) {
    (void)a; (void)b;
    m6_failmsg("function_1801a3ad0 called (CRT str scan; DSP 経路未解析)");
    return 0;
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

/* ---------- M6b: CRT memmove/memset の C 実装化 (m6_memfix.py が IR define を
 * 取り除き, IR 呼出 site がこの実装へ outcall する) ----------
 * IR 呼出 site 実測:
 *   function_1801a2a20(a1, a2, a3, a4): 本体が `store a1→rcx, a2→rdx; n=a3` で
 *     32B ループを走る (ltr: rcx=dst, rdx=src, r8=n) → memmove(dst=a1, src=a2, n=a3)。
 *     IR 本体は i256 系 helper (C ABI 一致不可) と 0-arg 内部 call を残す破損 lift。
 *   function_1801a30d0(a1, a2, a3): 本体が `value=urem a2,256 → movq/punpcklbw で
 *     16B broadcast` を 129B 以上の n=a3 に走らせる (rcx=dst) → memset(a1, a2&0xff, a3)。 */
long long function_1801a2a20(long long dst, long long src, long long n, long long unused4) {
    if (n > 0) {
        if (dst <= 0 || src < 0 || n > 0x8000000LL) m6_failmsg("memmove (function_1801a2a20): bad range");
        memmove((void*)(uintptr_t)dst, (void*)(uintptr_t)src, (size_t)n);
    }
    return dst;
}
long long function_1801a30d0(long long dst, int value, long long n) {
    if (n > 0) {
        if (dst <= 0 || n > 0x8000000LL) m6_failmsg("memset (function_1801a30d0): bad range");
        memset((void*)(uintptr_t)dst, (int)(value & 0xff), (size_t)n);
    }
    return dst;
}




/* ---------- 未対応系 (fail-fast) ---------- */
void function_18003c0f1(void) {}
/* ---- Windows API stubs ---- */


void m6_fail(const char* msg) { m6_failmsg(msg); }

