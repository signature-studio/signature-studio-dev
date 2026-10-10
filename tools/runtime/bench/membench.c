// wasm32 vs wasm64 メモリアクセスマイクロベンチ。ポインタ引数なし (BigInt 差を排除) / 全関数が checksum を返す。
#include <stdint.h>
#include <stddef.h>
#define SZ (64u << 20)             /* 64MB: L3 を超える */
static uint32_t big[SZ / 4];       /* .bss */
static uint32_t hot[1024];         /* 4KB: L1 */
typedef struct node { struct node *next; uint32_t pad[14]; } __attribute__((aligned(64))) node_t; /* 64B 固定 */
static node_t pool_[1u << 20];
static node_t *nodes;
#define NN (1u << 20)              /* 1M nodes × stride */
static uint32_t perm[NN];

__attribute__((export_name("init"))) uint32_t init(void) {
  uint32_t x = 12345;
  for (uint32_t i = 0; i < SZ / 4; i++) { x = x * 1664525u + 1013904223u; big[i] = x; }
  for (uint32_t i = 0; i < 1024; i++) hot[i] = i * 2654435761u;
  // pointer chase: ランダム巡回順 (Sattolo)
  for (uint32_t i = 0; i < NN; i++) perm[i] = i;
  for (uint32_t i = NN - 1; i > 0; i--) { x = x * 1664525u + 1013904223u; uint32_t j = x % i; uint32_t t = perm[i]; perm[i] = perm[j]; perm[j] = t; }
  nodes = pool_;                   /* 64B stride × 1M = 64MB (big とは別領域) */
  for (uint32_t i = 0; i < NN; i++) nodes[perm[i]].next = &nodes[perm[(i + 1) % NN]];
  return 0;
}
__attribute__((export_name("seq_sum"))) uint32_t seq_sum(uint32_t reps) {
  uint32_t s = 0; for (uint32_t r = 0; r < reps; r++) for (uint32_t i = 0; i < SZ / 4; i++) s += big[i] ^ r; return s; }
__attribute__((export_name("rand_rmw"))) uint32_t rand_rmw(uint32_t n) {
  uint32_t x = 1, s = 0; for (uint32_t i = 0; i < n; i++) { x = x * 1664525u + 1013904223u; uint32_t k = (x >> 4) & (SZ / 4 - 1); big[k] += i; s ^= big[k]; } return s; }
__attribute__((export_name("chase"))) uint32_t chase(uint32_t n) {
  node_t *p = &nodes[0]; for (uint32_t i = 0; i < n; i++) p = p->next; return (uint32_t)(uintptr_t)p; }
__attribute__((export_name("hot_loop"))) uint32_t hot_loop(uint32_t n) {
  uint32_t s = 0; for (uint32_t r = 0; r < n; r++) for (uint32_t i = 1; i < 1023; i++) { hot[i] = hot[i - 1] + hot[i + 1] + (hot[i] >> 1); s += hot[i]; } return s; }
// 間接参照 + 呼び出し多め (lifted コード風: i64 地址算術を経由)
static uint32_t __attribute__((noinline)) leaf(const uint32_t *p, uint32_t k) { return p[k & 255] * 31u + p[(k + 1) & 255]; }
__attribute__((export_name("call_mix"))) uint32_t call_mix(uint32_t n) {
  uint32_t s = 0; for (uint32_t i = 0; i < n; i++) { s += leaf(&big[(i * 64u) & (SZ / 4 - 1024)], i); hot[i & 1023] ^= s; } return s; }
