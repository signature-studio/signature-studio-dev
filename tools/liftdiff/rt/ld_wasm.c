/* liftdiff wasm ランナの C 側: 共有コア (ld_core.h) + wasm 固有の領域確保・エクスポート。
 * 関数呼出しは JS (ld_runner.mjs) が wasm の function_<VA> export を直接呼ぶ。 */
#include "ld_core.h"
#include <emscripten.h>
#include <emscripten/stack.h>

#define ARENA_SIZE (1u << 20)
#define HEAP_SIZE (96u << 20)
static u8 g_arena[ARENA_SIZE] __attribute__((aligned(4096)));
static u8 g_heap[HEAP_SIZE] __attribute__((aligned(65536)));
static char g_inbuf[192u << 20];   /* CAB-233: boot 状態の SHEAP (hybrid boot で数十MB heap) を載せるため 8MB→192MB */
static int32_t g_counter;

u64 ld_stub_x(const char* n, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5) { return ld_stub(n, a0, a1, a2, a3, a4, a5); }
/* CAB-233: 仮 proc アドレス (native と同一の値。wasm では実行されず ott_dispatch が unlifted ret-0 にする) */
u64 ld_fake_ptr(u64 i) { return LD_FAKEPROC_BASE + i * LD_FAKEPROC_SZ; }
void ld_trace(u64 va, u32 np, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7, u64 x0, u64 x1, u64 x2, u64 x3) {
  if (!ld_trace_on) return;
  u64 a[8] = { a0, a1, a2, a3, a4, a5, a6, a7 }, x[4] = { x0, x1, x2, x3 };
  ld_trace_rec(va, np, a, x);
}
/* LD-67 (#1906): IR block 入口は call ではなく volatile store で記録する (call を入れると wasm の戻り値が変わるため)。
 * IR 側は index を 65535 でマスクするため、ld_blk_n が 65536 を超えると古い要素が上書きされる (blk_over で検知する)。
 * ld_blk_sync() が case 終了時に ld_blks へ移す。 */
volatile u64 ld_blk_n;
volatile u64 ld_blk_arr[65536];
static void ld_blk_sync(void) {
  u64 n = ld_blk_n;
  ld_blk_n = 0;
  if (!ld_blk_on) return;
  if (n > 65536) { ld_blk_over += (int)(n - 65536); n = 65536; }
  for (u64 i = 0; i < n; i++) ld_blk_rec(ld_blk_arr[i]);
}
u64 __readgsqword(u64 off) { return *(u64*)(g_heap + LD_TEB_OFF + off); }
int32_t* m11_counter_ptr(void) { return &g_counter; }
void m11_probe(int i) { (void)i; }

EMSCRIPTEN_KEEPALIVE char* ld_w_inbuf(void) { return g_inbuf; }
EMSCRIPTEN_KEEPALIVE void ld_w_layout(u64* out) {
  out[0] = (u64)(uintptr_t)g_arena; out[1] = ARENA_SIZE; out[2] = (u64)(uintptr_t)g_heap; out[3] = HEAP_SIZE;
  out[4] = (u64)emscripten_stack_get_base(); out[5] = (u64)emscripten_stack_get_end();
}
EMSCRIPTEN_KEEPALIVE void ld_w_init(u64 origin, u64 delta) {
  ld_img = (u8*)(uintptr_t)origin; ld_delta = delta;
  ld_arena = g_arena; ld_arena_size = ARENA_SIZE; ld_heap = g_heap; ld_heap_size = HEAP_SIZE;
}
EMSCRIPTEN_KEEPALIVE void ld_w_add_wr(u64 rva, u64 len) { ld_add_wr(rva, len); }
/* LD-126 (#2723): case 間で持ち越す wasm 側の状態を候補ごとに snapshot 時点へ戻す (RESET mask)。
 * 1 = wasm スタック (SP は JS 側で戻す)・2 = C 静的変数 (g_heap・g_inbuf・g_arena を除く data/bss)・4 = image 全体 (線形 0 番地から imglen)。 */
extern char __global_base[];
#define LD_RST_STK 1
#define LD_RST_STA 2
#define LD_RST_IMG 4
typedef struct { int cat; u8* lo; u64 n; u8* pr; } ld_rst_t;
static ld_rst_t ld_rst[8];
static int ld_nrst;
/* 複製は全 malloc の後にまとめて行う (C 静的変数の複製には dlmalloc の管理情報と ld_rst 表自体が含まれるため) */
static void ld_rst_add(int cat, void* lo, u64 n) {
  ld_rst_t* r = &ld_rst[ld_nrst++];
  r->cat = cat; r->lo = (u8*)lo; r->n = n;
  r->pr = n ? (u8*)malloc(n) : 0;
}
static void ld_rst_take(void) {
  for (int i = 0; i < ld_nrst; i++) if (ld_rst[i].n) memcpy(ld_rst[i].pr, ld_rst[i].lo, ld_rst[i].n);
}
static void ld_rst_sta(void) {
  u8* big[3] = { (u8*)g_heap, (u8*)g_inbuf, (u8*)g_arena };
  u64 bn[3] = { HEAP_SIZE, sizeof g_inbuf, ARENA_SIZE };
  for (int i = 0; i < 3; i++) for (int j = i + 1; j < 3; j++) if (big[j] < big[i]) {
    u8* t = big[i]; big[i] = big[j]; big[j] = t; u64 k = bn[i]; bn[i] = bn[j]; bn[j] = k;
  }
  u8* cur = (u8*)__global_base;
  for (int i = 0; i < 3; i++) {
    if (big[i] > cur) ld_rst_add(LD_RST_STA, cur, (u64)(big[i] - cur));
    if (big[i] + bn[i] > cur) cur = big[i] + bn[i];
  }
  u8* end = (u8*)(uintptr_t)emscripten_stack_get_end();
  if (end > cur) ld_rst_add(LD_RST_STA, cur, (u64)(end - cur));
}
EMSCRIPTEN_KEEPALIVE void ld_w_snapshot(int imglen) {
  ld_snapshot();
  ld_nrst = 0;
  ld_rst_add(LD_RST_STK, (u8*)(uintptr_t)emscripten_stack_get_end(), (u64)(emscripten_stack_get_base() - emscripten_stack_get_end()));
  ld_rst_sta();
  ld_rst_add(LD_RST_IMG, (u8*)(uintptr_t)ld_img, (u64)imglen);
  ld_rst_take();
}
EMSCRIPTEN_KEEPALIVE void ld_w_reset(int mask) {
  for (int i = 0; i < ld_nrst; i++) if ((mask & ld_rst[i].cat) && ld_rst[i].n) memcpy(ld_rst[i].lo, ld_rst[i].pr, ld_rst[i].n);
}
/* inbuf に "name\0payload\0" を置いて呼ぶ */
EMSCRIPTEN_KEEPALIVE void ld_w_blob(void) { ld_cmd_blob(g_inbuf, g_inbuf + strlen(g_inbuf) + 1); }
EMSCRIPTEN_KEEPALIVE void ld_w_fix(void) { ld_cmd_fix(g_inbuf, g_inbuf + strlen(g_inbuf) + 1); }
/* inbuf = CASE 行 (key=value ...). パース + 復元 + ログ初期化 */
EMSCRIPTEN_KEEPALIVE void ld_w_case_begin(void) {
  ld_parse_case(g_inbuf);
  ld_case_begin();
  /* shadow stack 直下を 0 クリア (未初期化 local を決定的に) */
  u8* sp = (u8*)(uintptr_t)emscripten_stack_get_current();
  u8* lo = (u8*)(uintptr_t)emscripten_stack_get_end();
  size_t n = 128 * 1024; if ((size_t)(sp - lo) < n) n = (size_t)(sp - lo);
  memset(sp - n, ld_case.stkfill, n);
}
EMSCRIPTEN_KEEPALIVE u64 ld_w_fn(void) { return ld_case.fn; }
EMSCRIPTEN_KEEPALIVE u64 ld_w_arg(int i) { return ld_case.val[i]; }
EMSCRIPTEN_KEEPALIVE int ld_w_arg_kind(int i) { return ld_case.kind[i]; }
EMSCRIPTEN_KEEPALIVE int ld_w_nargs(void) { return ld_case.nargs; }
/* inbuf = "status\0detail\0rtype\0" */
EMSCRIPTEN_KEEPALIVE const char* ld_w_case_end(u64 rax, u64 rdx, u64 x0, u64 x1, int has_ret) {
  const char* st = g_inbuf; const char* det = st + strlen(st) + 1; const char* rt = det + strlen(det) + 1;
  ld_blk_sync();
  const char* j = ld_case_end(st, det, 0, 0, rax, rdx, x0, x1, has_ret);
  /* rtype を JSON 末尾に追加 (最後の '}' の前) */
  size_t n = strlen(ld_out);
  if (n > 1 && ld_out[n - 1] == '}') { ld_out[n - 1] = 0; ld_outn = n - 1; ld_ob(",\"rtype\":\"%s\"}", rt); }
  return j;
}

/* inbuf = "cmd\0a\0b\0": SIMG/SHEAP/SMODEL/SSNAP は状態を設定、STATE は JSON を返す */
EMSCRIPTEN_KEEPALIVE const char* ld_w_state(void) {
  const char* c = g_inbuf; const char* a = c + strlen(c) + 1; const char* b = a + strlen(a) + 1;
  if (!strcmp(c, "STATE")) return ld_state_dump();
  ld_state_cmd(c, a, b);
  return "";
}
