/* gui_headless.c — ブラウザ host の C 代替 (native テスト専用; wasm には含めない)
 * 役割は src/runtime/gui_worker.ts (描画) + gui.ts (入力) と同一: out ring を消費して desktop に合成、
 * 入力 ring へ投入。PROTOCOL.md のリファレンス実装。 */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include "gui_internal.h"
#include "gui_headless.h"

extern GuiShared *gui_shared_native(void);
extern int gui_surf_snapshot(int id, uint32_t **px, uint32_t *w, uint32_t *h);

static GuiShared *S;
static uint32_t *g_desk; static uint32_t g_dw, g_dh;
static pthread_t g_thr; static atomic_int g_stop;
static pthread_mutex_t g_mx = PTHREAD_MUTEX_INITIALIZER; static pthread_cond_t g_cv = PTHREAD_COND_INITIALIZER;
#define MAXLINES 4096
static char *g_lines[MAXLINES]; static int g_nlines, g_cursor;
static char g_cur[512]; static int g_curn;
static uint32_t g_in_seq;

static void blit_surf(int id, WRECT r /* surface coords */) {
  GuiSurface *s = &S->surf[id];
  if (!s->state || !s->visible) return;
  /* px/w/h は shim が公開する不変スナップショットから一組で取る (GUI-12)。処理中のレコードが ring head を通過するまで shim は free しない */
  uint32_t *px, sw, sh;
  if (!gui_surf_snapshot(id, &px, &sw, &sh)) return;
  WRECT sr = r_isect(r, (WRECT){ 0, 0, (int32_t)sw, (int32_t)sh });
  for (int y = sr.top; y < sr.bottom; y++) {
    int dy = s->y + y; if (dy < 0 || dy >= (int)g_dh) continue;
    for (int x = sr.left; x < sr.right; x++) {
      int dx = s->x + x; if (dx < 0 || dx >= (int)g_dw) continue;
      g_desk[(size_t)dy * g_dw + dx] = px[(size_t)y * sw + x] | 0xFF000000u;
    }
  }
}
static void recompose_all(void) {
  for (size_t i = 0; i < (size_t)g_dw * g_dh; i++) g_desk[i] = 0xFF000000u;
  for (int pass = 0; pass < (int)GUI_MAX_SURF; pass++) {
    int best = -1; uint32_t bz = 0xFFFFFFFFu;
    static uint8_t done[GUI_MAX_SURF]; if (pass == 0) memset(done, 0, sizeof done);
    for (int i = 0; i < (int)GUI_MAX_SURF; i++) if (S->surf[i].state && !done[i] && (best < 0 || S->surf[i].z < bz)) { best = i; bz = S->surf[i].z; }
    if (best < 0) break;
    done[best] = 1;
    blit_surf(best, (WRECT){ 0, 0, 0x7fffffff, 0x7fffffff });   /* blit_surf がスナップショットの w/h へ clip */
  }
}
static void present(int id, WRECT r) {
  GuiSurface *s = &S->surf[id];
  blit_surf(id, r);
  /* より前面の surface が重なる領域を再描画 (z-order 維持) */
  WRECT dr = { s->x + r.left, s->y + r.top, s->x + r.right, s->y + r.bottom };
  for (int i = 0; i < (int)GUI_MAX_SURF; i++) {
    GuiSurface *o = &S->surf[i];
    if (i == id || !o->state || !o->visible || o->z <= s->z) continue;
    WRECT inter = r_isect(dr, (WRECT){ o->x, o->y, o->x + (int32_t)o->w, o->y + (int32_t)o->h });
    if (r_empty(inter)) continue;
    blit_surf(i, (WRECT){ inter.left - o->x, inter.top - o->y, inter.right - o->x, inter.bottom - o->y });
  }
}
static void on_cmd(const uint32_t *r) {
  switch (r[0]) {
    case GUI_CMD_SURF_CREATE: case GUI_CMD_SURF_DESTROY: case GUI_CMD_SURF_CHANGE: recompose_all(); break;
    case GUI_CMD_PRESENT: present((int)r[1], (WRECT){ (int32_t)r[2], (int32_t)r[3], (int32_t)r[4], (int32_t)r[5] }); break;
    case GUI_CMD_FRAME_END: __atomic_store_n(&S->present_done_seq, r[1], __ATOMIC_SEQ_CST); gui_futex_wake(&S->present_done_seq);
      pthread_mutex_lock(&g_mx); pthread_cond_broadcast(&g_cv); pthread_mutex_unlock(&g_mx); break;
    case GUI_CMD_LOG: {
      int n = (int)(r[1] & 0xFF);
      pthread_mutex_lock(&g_mx);
      if (g_curn + n < (int)sizeof g_cur - 1) { memcpy(g_cur + g_curn, &r[2], (size_t)n); g_curn += n; }
      if ((r[1] & 0x100) && g_nlines < MAXLINES) { g_cur[g_curn] = 0; g_lines[g_nlines++] = strdup(g_cur); g_curn = 0; pthread_cond_broadcast(&g_cv); }
      pthread_mutex_unlock(&g_mx);
      break;
    }
    case GUI_CMD_EXIT: pthread_mutex_lock(&g_mx); pthread_cond_broadcast(&g_cv); pthread_mutex_unlock(&g_mx); break;
    default: break;
  }
}
void gui_hl_drain(void) {
  for (;;) {
    uint32_t head = S->out_ring.head, tail = __atomic_load_n(&S->out_ring.tail, __ATOMIC_ACQUIRE);
    if (head == tail) break;
    uint32_t rec[8]; memcpy(rec, S->out_recs[head & (GUI_OUT_RECS - 1)], 32);
    on_cmd(rec);
    __atomic_store_n(&S->out_ring.head, head + 1, __ATOMIC_RELEASE);
    gui_futex_wake(&S->out_ring.head);
  }
}
static void *render_thread(void *a) {
  (void)a;
  while (!atomic_load(&g_stop)) {
    gui_hl_drain();
    uint32_t tail = __atomic_load_n(&S->out_ring.tail, __ATOMIC_ACQUIRE);
    if (tail == S->out_ring.head) gui_futex_wait(&S->out_ring.tail, tail, 20);
  }
  gui_hl_drain();
  return NULL;
}
void gui_hl_start(uint32_t w, uint32_t h, int threaded) {
  S = gui_shared_native();
  g_dw = w; g_dh = h; g_desk = (uint32_t *)calloc((size_t)w * h, 4);
  for (size_t i = 0; i < (size_t)w * h; i++) g_desk[i] = 0xFF000000u;
  S->magic = GUI_MAGIC; S->version = GUI_VERSION; S->total_size = GUI_TOTAL_SIZE;
  gui_headless_attach(w, h);
  if (threaded) { atomic_store(&g_stop, 0); pthread_create(&g_thr, NULL, render_thread, NULL); }
  else gui_host_drain_cb = gui_hl_drain;
}
void gui_hl_stop(void) { atomic_store(&g_stop, 1); gui_futex_wake(&S->out_ring.tail); pthread_join(g_thr, NULL); }
void gui_hl_input(uint32_t type, uint32_t surf, int32_t x, int32_t y, uint32_t a, uint32_t b) {
  /* 状態 (host が先に更新) */
  if (type == GUI_IN_MOUSE_MOVE || type == GUI_IN_MOUSE_DOWN || type == GUI_IN_MOUSE_UP) {
    S->cursor_x = x; S->cursor_y = y;
    if (type == GUI_IN_MOUSE_DOWN) S->buttons |= (a == 0 ? 1u : a == 2 ? 2u : 4u);
    if (type == GUI_IN_MOUSE_UP) S->buttons &= ~(a == 0 ? 1u : a == 2 ? 2u : 4u);
  }
  uint32_t head = __atomic_load_n(&S->in_ring.head, __ATOMIC_ACQUIRE), tail = S->in_ring.tail;
  if (tail - head >= GUI_IN_RECS) { S->in_dropped++; return; }
  uint32_t *rec = S->in_recs[tail & (GUI_IN_RECS - 1)];
  rec[0] = type; rec[1] = surf; rec[2] = (uint32_t)x; rec[3] = (uint32_t)y; rec[4] = a; rec[5] = b; rec[6] = gui_now_ms(); rec[7] = ++g_in_seq;
  __atomic_store_n(&S->in_ring.tail, tail + 1, __ATOMIC_RELEASE);
  S->in_pushed++;
  __atomic_fetch_add(&S->doorbell, 1, __ATOMIC_SEQ_CST);
  gui_futex_wake(&S->doorbell);
}
int gui_hl_wait_line(const char *prefix, int timeout_ms) {
  struct timespec ts;
  pthread_mutex_lock(&g_mx);
  for (;;) {
    for (int i = g_cursor; i < g_nlines; i++)
      if (!strncmp(g_lines[i], prefix, strlen(prefix))) { g_cursor = i + 1; pthread_mutex_unlock(&g_mx); return 1; }
    clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += timeout_ms / 1000; ts.tv_nsec += (long)(timeout_ms % 1000) * 1000000L;
    if (ts.tv_nsec >= 1000000000L) { ts.tv_sec++; ts.tv_nsec -= 1000000000L; }
    if (pthread_cond_timedwait(&g_cv, &g_mx, &ts) != 0) { pthread_mutex_unlock(&g_mx); return 0; }
  }
}
const char *gui_hl_line(int i) { return (i >= 0 && i < g_nlines) ? g_lines[i] : NULL; }
int gui_hl_nlines(void) { return g_nlines; }
uint32_t *gui_hl_desktop(void) { return g_desk; }
void gui_hl_recompose(void) { recompose_all(); }
int gui_hl_dump_ppm(const char *path) {
  FILE *f = fopen(path, "wb"); if (!f) return 0;
  fprintf(f, "P6\n%u %u\n255\n", g_dw, g_dh);
  for (size_t i = 0; i < (size_t)g_dw * g_dh; i++) { uint32_t p = g_desk[i]; unsigned char c[3] = { (unsigned char)(p >> 16), (unsigned char)(p >> 8), (unsigned char)p }; fwrite(c, 1, 3, f); }
  fclose(f); return 1;
}
