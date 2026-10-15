/* stk_value_check.c — 5 引数以上の間接 call で stack 引数 (STKBUF 12 語) の値が被呼側に届くことを数値で確認する (ICALL-114)。
 *  - harness が ott_ms_call (tools/ott/native/ms_call.S) で 12 語の stk を注入し、MS ABI の被呼側 callee を間接 call (call *%r12) する。
 *  - callee は第 5〜16 引数 (stack 引数 12 語) を受け取り、期待値 (0x1111... + k) と一致するかを語ごとに数える。
 *  - ネガティブコントロール (NEG=1): 注入バッファを 1 語ずらす (stk[0] に期待値 1 語後の値を置く) と、一致数が 0 になり FAIL する。
 * 用法: stk_value_check [NEG=1]   exit 0 = 全 12 語一致 (PASS) / exit 1 = 不一致 (FAIL)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define NSTK 12
#define MS __attribute__((ms_abi))

extern uint64_t ott_ms_call(void* fn, const uint64_t* gpr4, const uint64_t* xmm4, const uint64_t* stk, long nstk, uint64_t* out2);

static uint64_t expect[NSTK];
static volatile int g_match;
static volatile uint64_t g_seen[NSTK];

static MS uint64_t callee(uint64_t a, uint64_t b, uint64_t c, uint64_t d,
                          uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                          uint64_t i, uint64_t j, uint64_t k, uint64_t l,
                          uint64_t m, uint64_t n, uint64_t o, uint64_t p) {
    uint64_t v[NSTK] = {e, f, g, h, i, j, k, l, m, n, o, p};
    (void)a; (void)b; (void)c; (void)d;
    for (int t = 0; t < NSTK; t++) {
        g_seen[t] = v[t];
        if (v[t] == expect[t]) g_match++;
    }
    return (uint64_t)g_match;
}

int main(void) {
    int neg = getenv("NEG") != NULL;
    uint64_t buf[NSTK];
    for (int t = 0; t < NSTK; t++) expect[t] = 0x1111000000000000ULL + (uint64_t)t * 0x101 + 0x40;
    /* 注入: 正常 = expect をそのまま渡す。NEG = 1 語ずらして渡す (被呼側は buf[t] = expect[t+1] を受ける) */
    for (int t = 0; t < NSTK; t++) buf[t] = neg ? (t + 1 < NSTK ? expect[t + 1] : 0) : expect[t];
    uint64_t gpr[4] = {1, 2, 3, 4}, xmm[4] = {0, 0, 0, 0}, out[2] = {0, 0};
    ott_ms_call((void*)callee, gpr, xmm, buf, NSTK, out);
    int ok = (g_match == NSTK) && (out[0] == NSTK);
    for (int t = 0; t < NSTK; t++)
        printf("stk[%2d] expect=%016llx seen=%016llx %s\n", t, (unsigned long long)expect[t],
               (unsigned long long)g_seen[t], g_seen[t] == expect[t] ? "match" : "MISMATCH");
    printf("RESULT %s%s matched=%d/%d\n", ok ? "PASS" : "FAIL", neg ? " (negative control)" : "", g_match, NSTK);
    return ok ? 0 : 1;
}
