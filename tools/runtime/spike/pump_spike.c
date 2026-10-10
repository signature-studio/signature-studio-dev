// ブロッキング GetMessage 方式比較 spike の wasm 側 (libc 無し・freestanding)。
// 同一ソースから 4 variant を作る:
//   (既定)     import get_message を JS が実装  → Atomics.wait / Asyncify(wasm-opt) / JSPI(Suspending) の 3 方式で共用
//   -DNATIVE   wasm 自身が共有メモリ上の ring を memory.atomic.wait32 でブロック (pthread ビルド想定)
#include <stdint.h>
#define IMPORT(n) __attribute__((import_module("env"), import_name(n)))
#define EXPORT(n) __attribute__((export_name(n)))

typedef struct { uint32_t msg; uint32_t seq; uint64_t a; uint64_t b; double t_post; } MSG; /* 32B (非 NATIVE: JS が書く) */

IMPORT("get_message") int host_get_message(MSG *m);
IMPORT("ack") void host_ack(uint32_t seq);

/* ---- NATIVE 用 ring (src/runtime/worker_pump.ts の RING ABI と同一レイアウト) ---- */
#define CAP 1024
typedef struct { int32_t seq, message, hwnd_lo, hwnd_hi, w_lo, w_hi, l_lo, l_hi, time, ptx, pty, pad; double t_post; double pad2; } slot_t;
typedef struct { int32_t enq, deq, wake, quit, cap, dropped, pad[10]; } hdr_t;
typedef struct { hdr_t h; slot_t s[CAP]; } ring_t;
static ring_t ring __attribute__((aligned(64)));
static volatile int32_t ack_word __attribute__((aligned(64)));

EXPORT("ring_addr") uint32_t ring_addr(void) { return (uint32_t)(uintptr_t)&ring; }
EXPORT("ack_addr") uint32_t ack_addr(void) { return (uint32_t)(uintptr_t)&ack_word; }

static int ring_pop(MSG *out) {
  int32_t pos = __atomic_load_n(&ring.h.deq, __ATOMIC_ACQUIRE);
  slot_t *s = &ring.s[pos & (CAP - 1)];
  if (__atomic_load_n(&s->seq, __ATOMIC_ACQUIRE) - (pos + 1) != 0) return 0;
  out->msg = (uint32_t)s->message; out->seq = (uint32_t)s->ptx; out->t_post = s->t_post;
  __atomic_store_n(&s->seq, pos + CAP, __ATOMIC_RELEASE);
  __atomic_store_n(&ring.h.deq, pos + 1, __ATOMIC_RELEASE);
  return 1;
}
#ifdef NATIVE
static int get_message(MSG *m) {
  for (;;) {
    int32_t w = __atomic_load_n(&ring.h.wake, __ATOMIC_ACQUIRE);
    if (ring_pop(m)) return 1;
    __builtin_wasm_memory_atomic_wait32((int32_t *)&ring.h.wake, w, -1);
  }
}
static void ack(uint32_t seq) { __atomic_store_n(&ack_word, (int32_t)seq, __ATOMIC_SEQ_CST); __builtin_wasm_memory_atomic_notify((int32_t *)&ack_word, 1); }
#else
#define get_message host_get_message
#define ack host_ack
#endif

/* ---- メッセージ処理 (ネスト ポンプ: msg==2 で内側ループ, msg==4 で抜ける) ---- */
static uint32_t handled, depth, max_depth, checksum;
EXPORT("stats") uint32_t stats(uint32_t i) { return i == 0 ? handled : i == 1 ? max_depth : checksum; }
static void pump(void);
static void __attribute__((noinline)) work(uint32_t seq) { uint32_t x = seq; for (int i = 0; i < 64; i++) x = x * 1664525u + 1013904223u; checksum ^= x; }
static void dispatch(MSG *m) {
  handled++;
  work(m->seq);
  ack(m->seq);                   /* ack は内側ポンプに入る前に返す (ack 語の逆転防止) */
  if (m->msg == 2) { pump(); }   /* モーダルループ相当: ネストして GetMessage */
}
static void pump(void) {
  MSG m; depth++; if (depth > max_depth) max_depth = depth;
  while (get_message(&m)) { if (m.msg == 4) { ack(m.seq); break; } if (m.msg == 0xFFFF) { depth--; return; } dispatch(&m); }
  depth--;
}
/* 内側ループは msg==4 到達で ack して抜ける。外側は 0xFFFF(WM_QUIT 相当)で終了 */
EXPORT("run") int run(void) { MSG m; while (get_message(&m)) { if (m.msg == 0xFFFF) break; dispatch(&m); } return (int)handled; }

/* Asyncify 用データ領域 (JS が start/end を書く) */
static char asyncify_area[16384] __attribute__((aligned(16)));
EXPORT("asyncify_area") uint32_t asyncify_area_addr(void) { return (uint32_t)(uintptr_t)asyncify_area; }
EXPORT("asyncify_area_size") uint32_t asyncify_area_size(void) { return sizeof asyncify_area; }
/* 呼び出しスタック深さ模擬: 深い呼び出し鎖の先でブロック (Asyncify の unwind/rewind コスト測定用) */
static int __attribute__((noinline)) deep(int n) { if (n == 0) { MSG m; int r = get_message(&m); if (r) dispatch(&m); return r; } return deep(n - 1) + 1; }
EXPORT("run_deep") int run_deep(int d) { int c = 0; while (deep(d) > 0) c++; return c; }
