#include <stdint.h>
#define SZ (64u << 20)
static uint32_t big[SZ / 4];
static uint32_t hot[1024];
typedef uint32_t (*fn_t)(const uint32_t *, uint32_t);
static uint32_t __attribute__((noinline)) leaf(const uint32_t *p, uint32_t k) { return p[k & 255] * 31u + p[(k + 1) & 255]; }
static uint32_t __attribute__((noinline)) leaf2(const uint32_t *p, uint32_t k) { return p[k & 255] ^ (k * 7u); }
static fn_t tbl[2] = { leaf, leaf2 };
__attribute__((export_name("init"))) uint32_t init(void) { uint32_t x = 7; for (uint32_t i = 0; i < SZ / 4; i++) { x = x * 1664525u + 1013904223u; big[i] = x; } return 0; }
/* A: 呼び出しあり・store なし */
__attribute__((export_name("call_nostore"))) uint32_t call_nostore(uint32_t n) { uint32_t s = 0; for (uint32_t i = 0; i < n; i++) s += leaf(&big[(i * 64u) & (SZ / 4 - 1024)], i); return s; }
/* B: store あり・呼び出しなし */
__attribute__((export_name("store_nocall"))) uint32_t store_nocall(uint32_t n) { uint32_t s = 0; for (uint32_t i = 0; i < n; i++) { s += big[(i * 64u) & (SZ / 4 - 1024)] + i; hot[i & 1023] ^= s; } return s; }
/* C: 間接呼び出し (VMT 風) */
__attribute__((export_name("call_indirect"))) uint32_t call_indirect(uint32_t n) { uint32_t s = 0; for (uint32_t i = 0; i < n; i++) s += tbl[i & 1](&big[(i * 64u) & (SZ / 4 - 1024)], i); return s; }
/* D: 呼び出し + store (元 call_mix) */
__attribute__((export_name("call_store"))) uint32_t call_store(uint32_t n) { uint32_t s = 0; for (uint32_t i = 0; i < n; i++) { s += leaf(&big[(i * 64u) & (SZ / 4 - 1024)], i); hot[i & 1023] ^= s; } return s; }
