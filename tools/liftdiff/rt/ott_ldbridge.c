/* ott_ldbridge.c — OTT (x64c lift = C 産物, tools/ott/lift) を liftdiff ランナ プロトコルへ接続する wasm 側ブリッジ (LD-247)。
 * fle_ldbridge.c と同じ構造。差分は CPU 状態モデルだけ: ott_cpu.h (R/X/XH/fZF 系・ott_mxcsr・ott_gsbase) に合わせる。
 * 関数名 (fle_ld_run・fle_ld_xmm0・ld_w_*) は clift.py の export 群と共通にする。
 *
 * レイアウト (target: wasm_origin=0x30000000, delta=pe.base-origin)。
 *   image  = 0x30000000..    (ott_data_install が敷設)
 *   heap   = 0x1D00000 (0xE300000) — ld_core が使う補助領域
 *   arena  = 0x20000000 (1MB)
 *   guest stack = 本ファイル静的 32MB
 * 関数呼出し: ld_case の引数を Win64 ABI (rcx,rdx,r8,r9 / xmm0-3 / [rsp+0x28+8k]) で R/X/guest stack に置き
 * ott_dispatch_impl(va) → f_<VA>() (ott_lifted.c)。entry トレースは計装された f_ 冒頭の ld_fle_trace が記録する。
 */
#include "ld_core.h"
#include "ott_cpu.h"
#include <emscripten.h>
#include <emscripten/stack.h>

#define FLE_ARENA     0x20000000ull
#define FLE_ARENA_SZ  (1u << 20)
#define FLE_HEAP      0x1D00000ull
#define FLE_HEAP_SZ   0xE300000ull

static u8 g_inbuf[192u << 20];
static u8 g_stack[32u << 20] __attribute__((aligned(16)));
#define LD_STACK_TOP ((u64)(uintptr_t)g_stack + sizeof g_stack - 0x100)

typedef struct { u64 va; u32 np; } fle_nptab_t;
extern const fle_nptab_t fle_nptab[];
extern const int fle_nptab_n;

/* ---------------- entry トレース (ott_lifted.c の f_ 冒頭から呼ばれる) ---------------- */
u64 ld_fake_ptr(u64 i) { return LD_FAKEPROC_BASE + i * LD_FAKEPROC_SZ; }

void ld_fle_trace(u64 va) {
  if (!ld_trace_on) return;
  int lo = 0, hi = fle_nptab_n - 1, np = -1;
  while (lo <= hi) {
    int m = (lo + hi) >> 1;
    if (fle_nptab[m].va == va) { np = (int)fle_nptab[m].np; break; }
    if (fle_nptab[m].va < va) lo = m + 1; else hi = m - 1;
  }
  if (np < 0) return;
  u64 a[8], x[4];
  a[0] = R[1]; a[1] = R[2]; a[2] = R[8]; a[3] = R[9];
  for (int j = 0; j < 4; j++) a[4 + j] = LD64(R[4] + 0x28 + 8 * (u64)j);
  for (int j = 0; j < 4; j++) x[j] = X[j].q[0];
  ld_trace_rec(va, (u32)np, a, x);
}

/* ---------------- ld_wasm.c と同一のエクスポート群 ---------------- */
EMSCRIPTEN_KEEPALIVE char* ld_w_inbuf(void) { return (char*)g_inbuf; }
EMSCRIPTEN_KEEPALIVE void ld_w_layout(u64* out) {
  out[0] = FLE_ARENA; out[1] = FLE_ARENA_SZ; out[2] = FLE_HEAP; out[3] = FLE_HEAP_SZ;
  out[4] = LD_STACK_TOP + 0x100; out[5] = (u64)(uintptr_t)g_stack;
}
EMSCRIPTEN_KEEPALIVE void ld_w_init(u64 origin, u64 delta) {
  ld_img = (u8*)(uintptr_t)origin; ld_delta = delta;
  ld_arena = (u8*)(uintptr_t)FLE_ARENA; ld_arena_size = FLE_ARENA_SZ;
  ld_heap = (u8*)(uintptr_t)FLE_HEAP; ld_heap_size = FLE_HEAP_SZ;
}
EMSCRIPTEN_KEEPALIVE void ld_w_add_wr(u64 rva, u64 len) { ld_add_wr(rva, len); }
EMSCRIPTEN_KEEPALIVE void ld_w_snapshot(void) { ld_snapshot(); }
EMSCRIPTEN_KEEPALIVE void ld_w_blob(void) { ld_cmd_blob(g_inbuf, g_inbuf + strlen(g_inbuf) + 1); }
EMSCRIPTEN_KEEPALIVE void ld_w_fix(void) { ld_cmd_fix(g_inbuf, g_inbuf + strlen(g_inbuf) + 1); }

/* ---------------- case 実行 (OTT 呼出し規約への変換) ---------------- */
static int ld_nunlifted;
static u64 ld_unlifted_va;
static int ld_gstack_ovf;

static double g_xf[4] = { 1.25, 2.25, 3.25, 4.25 };

EMSCRIPTEN_KEEPALIVE void ld_w_case_begin(void) {
  ld_parse_case(g_inbuf);
  ld_case_begin();
  ld_nunlifted = 0; ld_unlifted_va = 0; ld_gstack_ovf = 0;
  memset(g_stack, ld_case.stkfill, sizeof g_stack);
  memset(R, 0, sizeof R); memset(X, 0, sizeof X); memset(XH, 0, sizeof XH);
  fZF = fSF = fCF = fOF = fPF = fDF = 0;
  ott_mxcsr = 0x1f80u;
  u64 gpr[4] = { 0 }, xmm[4] = { 0 };
  for (int i = 0; i < ld_case.nargs && i < 16; i++) {
    if (i < 4) { if (ld_case.kind[i] == 'i') gpr[i] = ld_case.val[i]; else xmm[i] = ld_case.val[i]; }
  }
  if (ld_case.xfill) {
    for (int i = 0; i < 4; i++) {
      int isint = (i >= ld_case.nargs) || ld_case.kind[i] == 'i';
      if (isint) memcpy(&xmm[i], &g_xf[i], 8);
      else if (gpr[i] == 0) gpr[i] = 0x11 + i;
    }
  }
  R[RSP] = LD_STACK_TOP;
  R[RCX] = gpr[0]; R[RDX] = gpr[1]; R[R8] = gpr[2]; R[R9] = gpr[3];
  for (int i = 0; i < 4; i++) X[i].q[0] = xmm[i];
  for (int i = 4; i < ld_case.nargs && i < 16; i++)
    ST64(LD_STACK_TOP + 0x20 + 8 * (u64)(i - 4), ld_case.val[i]);
  R[RSP] -= 8; ST64(R[RSP], 0xdead0000ull);
  R[RAX] = ld_case.rax;
}

/* case の fn は PE VA (0x1801xxxxx)。lift 産物の dispatch は wasm 番地 (0x301xxxxx) なので換算する (delta = ld_delta) */
EMSCRIPTEN_KEEPALIVE u64 fle_ld_run(void) {
  ott_dispatch(ld_case.fn - ld_delta);
  return R[RAX];
}
EMSCRIPTEN_KEEPALIVE u64 fle_ld_xmm0(void) { return X[0].q[0]; }

/* lift 集合外 VA 呼出し: ret 0 で継続 (ott_cpu.c の abort 既定は ottcpu_unlifted に退避。-Dott_unlifted=) */
void ott_unlifted(uint64_t va) {
  ld_nunlifted++;
  ld_unlifted_va = va;
  R[RAX] = 0;
  R[RSP] += 8;
}

/* ott_dispatch のラッパ: guest stack 範囲外なら trap。仮 proc の thunk は ld_stub 応答に振り向ける。 */
void ott_dispatch_impl(uint64_t t);
void ott_dispatch(uint64_t t) {
  if ((u64)(uintptr_t)g_stack + 0x100 > R[RSP] || R[RSP] >= LD_STACK_TOP) {
    ld_gstack_ovf++;
    __builtin_trap();
  }
  if (t >= LD_FAKEPROC_BASE && t < LD_FAKEPROC_BASE + LD_FAKEPROC_SZ * (LD_VMT_IDX0 + LD_VMT_SLOTS) &&
      (t - LD_FAKEPROC_BASE) % LD_FAKEPROC_SZ == 0) {
    u64 idx = (t - LD_FAKEPROC_BASE) / LD_FAKEPROC_SZ;
    if (ld_fakeproc_valid(idx)) {
      R[RAX] = ld_stub(ld_fakeproc_name(idx), R[RCX], R[RDX], R[R8], R[R9], LD64(R[RSP] + 0x28), LD64(R[RSP] + 0x30));
      R[RSP] += 8;
      return;
    }
  }
  ott_dispatch_impl(t);
}

/* block 入口記録 (clift.py の計装が ld_blk_arr へ volatile store する。ld_wasm.c の ld_blk_sync と同一規則)。
 * 既定版は書かない (ld_blk_on = 0 で同期が早期 return する)。 */
volatile u64 ld_blk_n;
volatile u64 ld_blk_arr[65536];
static void ott_blk_sync(void) {
  u64 n = ld_blk_n;
  ld_blk_n = 0;
  if (!ld_blk_on) return;
  if (n > 65536) { ld_blk_over += (int)(n - 65536); n = 65536; }
  for (u64 i = 0; i < n; i++) ld_blk_rec(ld_blk_arr[i]);
}

EMSCRIPTEN_KEEPALIVE const char* ld_w_case_end(u64 rax, u64 rdx, u64 x0, u64 x1, int has_ret) {
  ott_blk_sync();
  const char* st = g_inbuf; const char* det = st + strlen(st) + 1; const char* rt = det + strlen(det) + 1;
  const char* j = ld_case_end(st, det, 0, 0, rax, rdx, x0, x1, has_ret);
  size_t n = strlen(ld_out);
  if (n > 1 && ld_out[n - 1] == '}') {
    ld_out[n - 1] = 0; ld_outn = n - 1;
    if (ld_nunlifted) ld_ob(",\"unlifted\":%d,\"unlifted_va\":\"0x%llx\"", ld_nunlifted, (unsigned long long)ld_unlifted_va);
    if (ld_gstack_ovf) ld_ob(",\"gstack_ovf\":%d", ld_gstack_ovf);
    ld_ob(",\"rtype\":\"%s\"}", rt);
  }
  return j;
}

EMSCRIPTEN_KEEPALIVE const char* ld_w_state(void) {
  const char* c = g_inbuf; const char* a = c + strlen(c) + 1; const char* b = a + strlen(a) + 1;
  if (!strcmp(c, "STATE")) return ld_state_dump();
  ld_state_cmd(c, a, b);
  return "";
}

#include "imps.inc"
