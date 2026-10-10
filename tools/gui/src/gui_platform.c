/* gui_platform.c — 共有領域 init / futex / ring / log / fail-fast / handle table / rect list */
#define _GNU_SOURCE
#include <stdarg.h>
#include <stdatomic.h>
#include <stdio.h>
#include <math.h>
#include <time.h>
#include "gui_internal.h"

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#include <emscripten/threading.h>
#include <pthread.h>
#else
#include <errno.h>
#include <linux/futex.h>
#include <pthread.h>
#include <sys/syscall.h>
#include <unistd.h>
#endif

/* host が置いた共有領域。外部 (JS) からは gui_shared_ptr() で位置を得る */
static GuiShared g_sh __attribute__((aligned(64)));
void (*gui_host_drain_cb)(void);

#ifdef __EMSCRIPTEN__
EMSCRIPTEN_KEEPALIVE uint32_t gui_shared_ptr(void) { return (uint32_t)(uintptr_t)&g_sh; }
EMSCRIPTEN_KEEPALIVE uint32_t gui_shared_size(void) { return (uint32_t)sizeof(g_sh); }
#else
uint32_t gui_shared_size(void) { return (uint32_t)sizeof(g_sh); }
GuiShared *gui_shared_native(void) { return &g_sh; }
#endif

uint32_t gui_now_ms(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint32_t)(ts.tv_sec * 1000u + ts.tv_nsec / 1000000u);
}

void gui_futex_wait(volatile uint32_t *a, uint32_t expect, int timeout_ms) {
#ifdef __EMSCRIPTEN__
#ifdef __EMSCRIPTEN_PTHREADS__
  emscripten_futex_wait((void *)a, expect, timeout_ms < 0 ? INFINITY : (double)timeout_ms);
#else
  (void)a; (void)expect; (void)timeout_ms;
  gui_failfast("gui_futex_wait", "single-thread build cannot block (build with -pthread)");
#endif
#else
  struct timespec ts, *tp = NULL;
  if (timeout_ms >= 0) { ts.tv_sec = timeout_ms / 1000; ts.tv_nsec = (long)(timeout_ms % 1000) * 1000000L; tp = &ts; }
  syscall(SYS_futex, a, FUTEX_WAIT_PRIVATE, expect, tp, NULL, 0);
#endif
}

void gui_futex_wake(volatile uint32_t *a) {
#ifdef __EMSCRIPTEN__
#ifdef __EMSCRIPTEN_PTHREADS__
  emscripten_futex_wake((void *)a, 0x7fffffff);
#else
  (void)a;
#endif
#else
  syscall(SYS_futex, a, FUTEX_WAKE_PRIVATE, 0x7fffffff, NULL, NULL, 0);
#endif
}

uint64_t gui_thread_id(void) { return (uint64_t)(uintptr_t)pthread_self(); }

/* ---- 粗い spinlock (短い臨界区間専用) ---- */
static atomic_flag g_lk = ATOMIC_FLAG_INIT;
static uint64_t g_lk_owner; static int g_lk_depth;
void gui_lock(void) {
  uint64_t me = gui_thread_id();
  if (g_lk_depth && g_lk_owner == me) { g_lk_depth++; return; }
  while (atomic_flag_test_and_set_explicit(&g_lk, memory_order_acquire)) {}
  g_lk_owner = me; g_lk_depth = 1;
}
void gui_unlock(void) {
  if (--g_lk_depth == 0) { g_lk_owner = 0; atomic_flag_clear_explicit(&g_lk, memory_order_release); }
}

void gui_doorbell(void) {
  __atomic_fetch_add(&g_sh.doorbell, 1, __ATOMIC_SEQ_CST);
  gui_futex_wake(&g_sh.doorbell);
}

/* ---- out ring (MPSC: 内部 spinlock, 消費者は host 1 本) ---- */
static atomic_flag g_out_lk = ATOMIC_FLAG_INIT;
void gui_out_push(const uint32_t rec[8]) {
  while (atomic_flag_test_and_set_explicit(&g_out_lk, memory_order_acquire)) {}
  for (;;) {
    uint32_t head = __atomic_load_n(&g_sh.out_ring.head, __ATOMIC_ACQUIRE);
    uint32_t tail = g_sh.out_ring.tail;
    if (tail - head < GUI_OUT_RECS) {
      memcpy(g_sh.out_recs[tail & (GUI_OUT_RECS - 1)], rec, 32);
      __atomic_store_n(&g_sh.out_ring.tail, tail + 1, __ATOMIC_RELEASE);
      __atomic_fetch_add(&g_sh.out_pushed, 1, __ATOMIC_RELAXED);
      gui_futex_wake(&g_sh.out_ring.tail);
      break;
    }
    __atomic_fetch_add(&g_sh.out_full_waits, 1, __ATOMIC_RELAXED);
    if (gui_host_drain_cb) { gui_host_drain_cb(); continue; }
    gui_futex_wait(&g_sh.out_ring.head, head, 5);
  }
  atomic_flag_clear_explicit(&g_out_lk, memory_order_release);
}

void gui_log(const char *s) {
  size_t n = strlen(s);
  fprintf(stderr, "[gui] %s\n", s);
  do {
    uint32_t rec[8] = { GUI_CMD_LOG, 0, 0, 0, 0, 0, 0, 0 };
    size_t k = n > 24 ? 24 : n;
    memcpy(&rec[2], s, k);
    rec[1] = (uint32_t)k | (k == n ? 0x100u : 0);
    gui_out_push(rec);
    s += k; n -= k;
  } while (n > 0);
}
void gui_logf(const char *fmt, ...) {
  char buf[256];
  va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof buf, fmt, ap); va_end(ap);
  gui_log(buf);
}

GUI_NORETURN void gui_failfast(const char *api, const char *why) {
  fprintf(stderr, "FAIL-FAST: unimplemented Win32 API: %s%s%s\n", api, why ? " : " : "", why ? why : "");
  fflush(stderr);
  g_sh.exit_code = 0xFA11;
  __atomic_store_n(&g_sh.exited, 2, __ATOMIC_SEQ_CST);
  { uint32_t rec[8] = { GUI_CMD_EXIT, 0xFA11, 0, 0, 0, 0, 0, 0 }; gui_out_push(rec); }
  abort();
}

void gui_headless_attach(uint32_t w, uint32_t h) {
  g_sh.screen_w = w; g_sh.screen_h = h; g_sh.dpr_x100 = 100;
  g_sh.focused = 1; g_sh.page_visible = 1;
  __atomic_store_n(&g_sh.host_ready, 1, __ATOMIC_SEQ_CST);
}

static atomic_int g_init_state;  /* 0 未, 1 実行中, 2 完了 */
static void init_shared(void) {
  g_sh.magic = GUI_MAGIC; g_sh.version = GUI_VERSION; g_sh.total_size = GUI_TOTAL_SIZE;
}
GuiShared *gui_sh(void) {
  if (atomic_load_explicit(&g_init_state, memory_order_acquire) == 2) return &g_sh;
  int exp = 0;
  if (atomic_compare_exchange_strong(&g_init_state, &exp, 1)) {
    init_shared();
    if (!__atomic_load_n(&g_sh.host_ready, __ATOMIC_ACQUIRE)) {
#ifdef __EMSCRIPTEN__
      /* host (ブラウザ) が screen 寸法を書いて host_ready=1 にするのを待つ。最大 30 秒で fail-fast */
      uint32_t t0 = gui_now_ms();
      while (!__atomic_load_n(&g_sh.host_ready, __ATOMIC_ACQUIRE)) {
        gui_futex_wait(&g_sh.host_ready, 0, 100);
        if (gui_now_ms() - t0 > 30000) gui_failfast("gui_host_attach", "host not attached within 30s");
      }
#else
      gui_headless_attach(640, 480);
#endif
    }
    gdi_init();
    atomic_store_explicit(&g_init_state, 2, memory_order_release);
  } else {
    while (atomic_load_explicit(&g_init_state, memory_order_acquire) != 2) {}
  }
  return &g_sh;
}

/* ---- handle table ----
 * handle = gen(7bit)<<24 | type(4bit)<<20 | idx(20bit)  (< 2^31 : lifter が int32 に潰しても壊れない) */
typedef struct { void *p; uint8_t type, gen; } HEnt;
static HEnt *g_ht; static uint32_t g_ht_n, g_ht_cap; static uint32_t *g_ht_free; static uint32_t g_ht_nfree, g_ht_freecap;

U64 h_alloc(HType t, void *p) {
  gui_lock();
  uint32_t idx;
  if (g_ht_nfree) idx = g_ht_free[--g_ht_nfree];
  else {
    if (g_ht_n + 1 >= g_ht_cap) {
      g_ht_cap = g_ht_cap ? g_ht_cap * 2 : 1024;
      if (g_ht_cap > (1u << 20)) gui_failfast("h_alloc", "handle table exhausted (1M objects)");
      g_ht = (HEnt *)realloc(g_ht, g_ht_cap * sizeof(HEnt));
      memset(g_ht + g_ht_n, 0, (g_ht_cap - g_ht_n) * sizeof(HEnt));
      if (g_ht_n == 0) g_ht_n = 1;  /* idx 0 は無効 */
    }
    idx = g_ht_n++;
  }
  HEnt *e = &g_ht[idx];
  e->p = p; e->type = (uint8_t)t; e->gen = (uint8_t)((e->gen + 1) & 0x7f); if (!e->gen) e->gen = 1;
  U64 h = ((U64)e->gen << 24) | ((U64)t << 20) | idx;
  gui_unlock();
  return h;
}
static HEnt *h_ent(U64 h) {
  if (h < 0x1000000ull || h >= 0x80000000ull) return NULL;
  uint32_t idx = (uint32_t)(h & 0xFFFFF);
  if (idx == 0 || idx >= g_ht_n) return NULL;
  HEnt *e = &g_ht[idx];
  if (e->type == 0) return NULL;
  if ((uint8_t)((h >> 24) & 0x7f) != e->gen) return NULL;
  if (((h >> 20) & 0xF) != e->type) return NULL;
  return e;
}
void *h_get(U64 h, HType t) {
  gui_lock();
  HEnt *e = h_ent(h);
  void *p = (e && (t == HT_NONE || e->type == t)) ? e->p : NULL;
  gui_unlock();
  return p;
}
HType h_type(U64 h) { gui_lock(); HEnt *e = h_ent(h); HType t = e ? (HType)e->type : HT_NONE; gui_unlock(); return t; }
void h_free(U64 h) {
  gui_lock();
  HEnt *e = h_ent(h);
  if (e) {
    uint32_t idx = (uint32_t)(h & 0xFFFFF);
    e->type = 0; e->p = NULL;
    if (g_ht_nfree >= g_ht_freecap) { g_ht_freecap = g_ht_freecap ? g_ht_freecap * 2 : 256; g_ht_free = (uint32_t *)realloc(g_ht_free, g_ht_freecap * 4); }
    g_ht_free[g_ht_nfree++] = idx;
  }
  gui_unlock();
}

/* ---- rect list ---- */
void rl_free(RL *l) { free(l->r); l->r = NULL; l->n = l->cap = 0; }
void rl_clear(RL *l) { l->n = 0; }
void rl_add(RL *l, WRECT r) {
  if (r_empty(r)) return;
  if (l->n >= l->cap) { l->cap = l->cap ? l->cap * 2 : 8; l->r = (WRECT *)realloc(l->r, l->cap * sizeof(WRECT)); }
  l->r[l->n++] = r;
}
void rl_copy(RL *d, const RL *s) { d->n = 0; for (int i = 0; i < s->n; i++) rl_add(d, s->r[i]); }
void rl_intersect_rect(RL *l, WRECT r) {
  int k = 0;
  for (int i = 0; i < l->n; i++) { WRECT o = r_isect(l->r[i], r); if (!r_empty(o)) l->r[k++] = o; }
  l->n = k;
}
void rl_subtract_rect(RL *l, WRECT s) {
  int n0 = l->n;
  for (int i = 0; i < n0; i++) {
    WRECT a = l->r[i], o = r_isect(a, s);
    if (r_empty(o)) continue;
    l->r[i].right = l->r[i].left;  /* 元を空に */
    WRECT p;
    p = (WRECT){ a.left, a.top, a.right, o.top };       rl_add(l, p);
    p = (WRECT){ a.left, o.bottom, a.right, a.bottom }; rl_add(l, p);
    p = (WRECT){ a.left, o.top, o.left, o.bottom };     rl_add(l, p);
    p = (WRECT){ o.right, o.top, a.right, o.bottom };   rl_add(l, p);
  }
  int k = 0;
  for (int i = 0; i < l->n; i++) if (!r_empty(l->r[i])) l->r[k++] = l->r[i];
  l->n = k;
}
void rl_intersect(RL *l, const RL *o) {
  RL out = {0};
  for (int i = 0; i < l->n; i++)
    for (int j = 0; j < o->n; j++) { WRECT r = r_isect(l->r[i], o->r[j]); rl_add(&out, r); }
  rl_free(l); *l = out;
}
void rl_subtract(RL *l, const RL *o) { for (int j = 0; j < o->n; j++) rl_subtract_rect(l, o->r[j]); }
void rl_union(RL *l, const RL *o) {
  RL t = {0}; rl_copy(&t, o);
  rl_subtract(&t, l);
  for (int i = 0; i < t.n; i++) rl_add(l, t.r[i]);
  rl_free(&t);
}
void rl_bbox(const RL *l, WRECT *out) {
  WRECT b = {0, 0, 0, 0};
  for (int i = 0; i < l->n; i++) {
    if (i == 0) b = l->r[0];
    else {
      if (l->r[i].left < b.left) b.left = l->r[i].left;
      if (l->r[i].top < b.top) b.top = l->r[i].top;
      if (l->r[i].right > b.right) b.right = l->r[i].right;
      if (l->r[i].bottom > b.bottom) b.bottom = l->r[i].bottom;
    }
  }
  *out = b;
}
int rl_empty(const RL *l) { return l->n == 0; }
int rl_contains(const RL *l, int x, int y) {
  for (int i = 0; i < l->n; i++)
    if (x >= l->r[i].left && x < l->r[i].right && y >= l->r[i].top && y < l->r[i].bottom) return 1;
  return 0;
}

static uint32_t g_last_error;
void gui_set_last_error(uint32_t e) { g_last_error = e; }
int64_t GetLastError_gui(void) { return g_last_error; }
