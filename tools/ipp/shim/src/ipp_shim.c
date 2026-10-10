#include "ipp_shim.h"
#include <string.h>

#define N 420
static uint32_t g_calls[N];
static uint8_t g_seen[N];
static int g_first[N], g_nfirst = 0, g_last = -1, g_mode = IPP_SHIM_SOFT;
static uint32_t g_stub_total = 0;
static const char g_module_tag[16] = "dsp_ippv2";

int ipp_shim_find(const char *name) {
  if (!name) return -1;
  if (!strncmp(name, "legacy90", 8)) name += 8;
  int lo = 0, hi = ipp_shim_table_count - 1;
  while (lo <= hi) {
    int m = (lo + hi) / 2, c = strcmp(name, ipp_shim_table[m].name);
    if (!c) return m;
    if (c < 0) hi = m - 1; else lo = m + 1;
  }
  return -1;
}
uint64_t ipp_shim_cookie(int idx) { return (idx >= 0 && idx < ipp_shim_table_count) ? (uint64_t)(uintptr_t)&ipp_shim_table[idx] : 0; }
uint64_t ipp_shim_getproc(const char *name) { return ipp_shim_cookie(ipp_shim_find(name)); }

static int ieq(char a, char b) { if (a >= 'A' && a <= 'Z') a += 32; if (b >= 'A' && b <= 'Z') b += 32; return a == b; }
uint64_t ipp_shim_load_library_w(const uint16_t *w) {
  char s[96]; int n = 0, base = 0;
  if (!w) return 0;
  for (; w[n] && n < 95; n++) { s[n] = w[n] < 128 ? (char)w[n] : '?'; if (s[n] == '/' || s[n] == '\\') base = n + 1; }
  s[n] = 0;
  const char *p = s + base; static const char *ok[] = {"dsp_ippv2", "dsp_ippv2_x64"}; static const char *ext[] = {"", ".dll", ".dylib"};
  for (int i = 0; i < 2; i++) for (int j = 0; j < 3; j++) {
    char full[48]; size_t a = strlen(ok[i]), b = strlen(ext[j]); memcpy(full, ok[i], a); memcpy(full + a, ext[j], b + 1);
    size_t L = a + b; if (strlen(p) != L) continue;
    size_t k = 0; while (k < L && ieq(p[k], full[k])) k++;
    if (k == L) return (uint64_t)(uintptr_t)g_module_tag;
  }
  return 0;
}
uint64_t ipp_shim_get_proc_address(uint64_t h, const char *name) { return h == (uint64_t)(uintptr_t)g_module_tag ? ipp_shim_getproc(name) : 0; }

int ipp_shim_owns(uint64_t t) {
  uint64_t base = (uint64_t)(uintptr_t)ipp_shim_table, sz = sizeof ipp_shim_table[0];
  return t >= base && t < base + sz * (uint64_t)ipp_shim_table_count && ((t - base) % sz) == 0;
}

int ipp_shim_dispatch(IppBlk *b) {
  if (!ipp_shim_owns(b->target)) return 0;
  int idx = (int)((b->target - (uint64_t)(uintptr_t)ipp_shim_table) / sizeof ipp_shim_table[0]);
  const IppShimEntry *e = &ipp_shim_table[idx];
  __atomic_fetch_add(&g_calls[idx], 1, __ATOMIC_RELAXED);   /* FL は音声スレッドからも呼ぶ: 採取は原子的に */
  if (e->blk) { e->blk(b); return 1; }
  __atomic_fetch_add(&g_stub_total, 1, __ATOMIC_RELAXED); __atomic_store_n(&g_last, idx, __ATOMIC_RELAXED);
  if (!__atomic_exchange_n(&g_seen[idx], 1, __ATOMIC_RELAXED)) { int k = __atomic_fetch_add(&g_nfirst, 1, __ATOMIC_RELAXED); g_first[k] = idx; }
  if (g_mode == IPP_SHIM_STRICT) __builtin_trap();
  b->rax = 0; b->xmm0ret = 0;
  return 1;
}

void ipp_shim_set_mode(int m) { g_mode = m; }
int ipp_shim_get_mode(void) { return g_mode; }
uint32_t ipp_shim_calls(int i) { return (i >= 0 && i < N) ? g_calls[i] : 0; }
uint32_t ipp_shim_stub_calls_total(void) { return g_stub_total; }
int ipp_shim_stub_distinct(void) { return g_nfirst; }
int ipp_shim_stub_first(int k) { return (k >= 0 && k < g_nfirst) ? g_first[k] : -1; }
int ipp_shim_last_stub(void) { return g_last; }
void ipp_shim_reset(void) { memset(g_calls, 0, sizeof g_calls); memset(g_seen, 0, sizeof g_seen); g_nfirst = 0; g_last = -1; g_stub_total = 0; }
