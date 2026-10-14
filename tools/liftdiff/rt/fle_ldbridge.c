/* fle_ldbridge.c — flelift (x64c lift = C 産物, tools/flelift CAB-226) を liftdiff ランナ プロトコルへ接続する
 * wasm 側ブリッジ (CAB-232)。ld_core.h (native と同一の復元/差分/応答モデル/プロトコル) を共有し、
 * 関数呼出しだけを flelift の CPU 状態モデル (R[16]/X[16]/ott_dispatch) に変換する。
 *
 * レイアウト (target flelift.json: wasm_origin=0x400000, delta=0 — 恒等写像 wasm linear == VA):
 *   image  = 0x400000..        (fle_data_install が敷設, WR 範囲は ld_core が pristine 復元)
 *   heap   = 0x1D00000 (0xE300000) — TEB (gs) を heap+0 に置く (ld_native.c と同一規約)
 *   arena  = 0x20000000 (1MB)  — blob / a: 引数領域 (flelift spot harness の scratch と同一 VA)
 *   guest stack = 本ファイル静的 2MB (ネイティブのホストスタック相当)
 * 関数呼出し: ld_case の引数を Win64 ABI (rcx,rdx,r8,r9 / xmm0-3 / [rsp+0x28+8k]) で R/X/guest stack に
 * 置き ott_dispatch(va) → f_<VA>() (fle_lifted.c)。entry トレースは fle_lifted.c の各 f_ 冒頭に挿入した
 * ld_fle_trace() が記録する (np は nptab.c のテーブル = m11 IR sig 由来、TRACESET 外は記録しない)。
 * import: 生成 imps.c の強い imp_<名前> が fle_lifted.c の weak 既定 / fle_cpu.c (-D リネーム) を上書きし、
 * ld_core の ld_stub (native ld_native.c と同一応答モデル) で応答 + 呼出しログを残す。
 */
#include "ld_core.h"
#include "fle_cpu.h"
#include <emscripten.h>
#include <emscripten/stack.h>

#define FLE_ARENA     0x20000000ull
#define FLE_ARENA_SZ  (1u << 20)
#define FLE_HEAP      0x1D00000ull
#define FLE_HEAP_SZ   0xE300000ull

static u8 g_inbuf[192u << 20];   /* CAB-233: boot 状態の SHEAP (hybrid boot で 33MB heap → 66MB hex) を載せるため 8MB→192MB */
/* guest stack: 32MB — emcc C スタック (8MB) より大きくし、深い再帰では C スタックが先に
 * 枯渇して「投げられる abort」になるようにする (guest stack 枯渇は静的領域を破壊し
 * サイレント死亡/badjson になるため)。CAB-232 全数採点で 2MB では 0x737e00 等が
 * node ごと落ちることを実測 (12,901 case が badjson 化)。 */
static u8 g_stack[32u << 20] __attribute__((aligned(16)));
#define LD_STACK_TOP ((u64)(uintptr_t)g_stack + sizeof g_stack - 0x100)

/* nptab.c (生成): ソート済 {va, np}。lift 集合 ∩ m11 IR defined の関数のみ (TRACESET 相当)。np = IR 署名引数数 */
typedef struct { u64 va; u32 np; } fle_nptab_t;
extern const fle_nptab_t fle_nptab[];
extern const int fle_nptab_n;

/* ---------------- entry トレース (fle_lifted.c の f_ 冒頭から呼ばれる) ---------------- */
/* CAB-233: 仮 proc アドレス (native と同一の値。実行は ott_dispatch → unlifted ret-0 に落ちる) */
u64 ld_fake_ptr(u64 i) { return LD_FAKEPROC_BASE + i * LD_FAKEPROC_SZ; }

void ld_fle_trace(u64 va) {
  if (!ld_trace_on) return;
  int lo = 0, hi = fle_nptab_n - 1, np = -1;
  while (lo <= hi) {
    int m = (lo + hi) >> 1;
    if (fle_nptab[m].va == va) { np = (int)fle_nptab[m].np; break; }
    if (fle_nptab[m].va < va) lo = m + 1; else hi = m - 1;
  }
  if (np < 0) return;   /* lift 集合外 (native 側も INT3 未設置) → 記録しない */
  u64 a[8], x[4];
  a[0] = R[1]; a[1] = R[2]; a[2] = R[8]; a[3] = R[9];   /* rcx,rdx,r8,r9 */
  for (int j = 0; j < 4; j++) a[4 + j] = LD64(R[4] + 0x28 + 8 * (u64)j);   /* [rsp+0x28+8k] */
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

/* ---------------- case 実行 (flelift 呼出し規約への変換) ---------------- */
/* lift 集合外 VA 呼出し (ott_unlifted を ret-0 継続で潰した回数) と guest stack 範囲外 push
 * の検出数。ld_core.h を変更せずブリッジ独自の static として持ち、case 結果 JSON には
 * ld_w_case_end で末尾追記する (m11 など既存 target のメモリレイアウトを一切動かさない)。 */
static int ld_nunlifted;
static u64 ld_unlifted_va;
static int ld_gstack_ovf;

static double g_xf[4] = { 1.25, 2.25, 3.25, 4.25 };

EMSCRIPTEN_KEEPALIVE void ld_w_case_begin(void) {
  ld_parse_case(g_inbuf);
  ld_case_begin();
  ld_nunlifted = 0; ld_unlifted_va = 0; ld_gstack_ovf = 0;
  /* native ld_native.c run_case と同一の初期化: guest stack を stkfill で埋め、CPU 状態を 0 に */
  memset(g_stack, ld_case.stkfill, sizeof g_stack);
  memset(R, 0, sizeof R); memset(X, 0, sizeof X); memset(YL, 0, sizeof YL); memset(M, 0, sizeof M);
  fZF = fSF = fCF = fOF = fPF = fAF = fDF = 0;
  x87_cw = 0x037f; x87_sw = 0; mxcsr = 0x1f80;
  SEG_GS = FLE_TEB; SEG_FS = FLE_TEB;
  u64 gpr[4] = { 0 }, xmm[4] = { 0 };
  for (int i = 0; i < ld_case.nargs && i < 16; i++) {
    if (i < 4) { if (ld_case.kind[i] == 'i') gpr[i] = ld_case.val[i]; else xmm[i] = ld_case.val[i]; }
  }
  if (ld_case.xfill) {   /* native run_case と同一: 署名に無い位置にも決定値 */
    for (int i = 0; i < 4; i++) {
      int isint = (i >= ld_case.nargs) || ld_case.kind[i] == 'i';
      if (isint) memcpy(&xmm[i], &g_xf[i], 8);
      else if (gpr[i] == 0) gpr[i] = 0x11 + i;
    }
  }
  R[4] = LD_STACK_TOP;                       /* rsp (fle_glue.fle_run と同一: +0x20+8k が第 5 引数以降) */
  R[1] = gpr[0]; R[2] = gpr[1]; R[8] = gpr[2]; R[9] = gpr[3];
  for (int i = 0; i < 4; i++) X[i].q[0] = xmm[i];
  for (int i = 4; i < ld_case.nargs && i < 16; i++)
    ST64(LD_STACK_TOP + 0x20 + 8 * (u64)(i - 4), ld_case.val[i]);
  R[4] -= 8; ST64(R[4], 0xdead0000ull);      /* 疑似リターンアドレス (fle_run と同一): entry rsp = STACK_TOP-8,
                                              * 第 5 引数 = [rsp+0x28] = STACK_TOP+0x20 → native と一致 */
  R[0] = ld_case.rax;                        /* native ld_ms_call の rax_init (sentinel) と同一 */
}

EMSCRIPTEN_KEEPALIVE u64 fle_ld_run(void) {
  ott_dispatch(ld_case.fn);
  return R[0];
}
EMSCRIPTEN_KEEPALIVE u64 fle_ld_xmm0(void) { return X[0].q[0]; }

/* dispatch が lift 集合外 VA に着地した場合 (VMT/関数ポインタ経由の間接呼び)。
 * fle_cpu.c 既定は abort → ランナ全体が死ぬため、m11 route の unresolved_callee (stub が
 * 0 を返して継続) と同一挙動「ret 0」に差し替える (fle_cpu.c 側は -Dott_unlifted= でリネーム)。
 * 呼出し数と最終 VA は case 結果 JSON の "unlifted"/"unlifted_va" に記録し、分類 (classify) で
 * unlifted_callee タグを付ける。callee が本物なら native 側は実行するので差分は trace/値に出る。 */
void ott_unlifted(u64 va) {
  ld_nunlifted++;
  ld_unlifted_va = va;
  R[0] = 0;
  R[4] += 8;   /* lifted ret: 呼出し側が push した retaddr を pop して継続 */
}

/* ott_dispatch のラッパ: guest stack (R[RSP]) が g_stack 範囲外なら wasm trap で cleanly 落とす。
 * fle_lifted.c 側は -Dott_dispatch=flelift_dispatch_impl でリネームしてある。
 * 範囲外 = guest stack 枯渇 (深い再帰) — 放置すると静的領域を破壊しランナがサイレント死亡する。
 * CAB-233: GetProcAddress の仮 proc (LD_FAKEPROC_BASE 番地, native は実行可能 thunk → ld_stub 応答)
 * も wasm 側で同一の ld_stub 応答に振り向ける (native/wasm 同一応答モデルの維持。未対応 index は
 * 従来どおり ott_unlifted = ret-0)。 */
void flelift_dispatch_impl(u64 t);
void ott_dispatch(u64 t) {
  if ((u64)(uintptr_t)g_stack + 0x100 > R[4] || R[4] >= LD_STACK_TOP) {
    ld_gstack_ovf++;
    __builtin_trap();   /* wasm unreachable → JS で捕まる (case は trap 扱い) */
  }
  if (t >= LD_FAKEPROC_BASE && t < LD_FAKEPROC_BASE + LD_FAKEPROC_SZ * (LD_VMT_IDX0 + LD_VMT_SLOTS) &&
      (t - LD_FAKEPROC_BASE) % LD_FAKEPROC_SZ == 0) {
    u64 idx = (t - LD_FAKEPROC_BASE) / LD_FAKEPROC_SZ;
    if (ld_fakeproc_valid(idx)) {
      R[0] = ld_stub(ld_fakeproc_name(idx), R[1], R[2], R[8], R[9], LD64(R[4] + 0x28), LD64(R[4] + 0x30));
      R[4] += 8;   /* thunk は callee 側 ret (native ld_stub_common と同一) */
      return;
    }
  }
  flelift_dispatch_impl(t);
}

/* inbuf = "status\0detail\0rtype\0" — ld_wasm.c と同一 (+ clift 固有フィールドの末尾追記) */
EMSCRIPTEN_KEEPALIVE const char* ld_w_case_end(u64 rax, u64 rdx, u64 x0, u64 x1, int has_ret) {
  const char* st = g_inbuf; const char* det = st + strlen(st) + 1; const char* rt = det + strlen(det) + 1;
  const char* j = ld_case_end(st, det, 0, 0, rax, rdx, x0, x1, has_ret);
  /* rtype と clift 固有計数を JSON 末尾に追加 (最後の '}' の前) */
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

/* 生成 import (clift.py の imps.inc): 強い imp_<名前> が fle_lifted.c の weak 既定と
 * fle_cpu.c の既定 (-D リネーム) を上書きし、native と同一の ld_core 応答モデル + 呼出しログ
 * を提供する。ブリッジと同一翻訳単位に含める (ld_core の static 状態 = 呼出しログを共有)。 */
#include "imps.inc"
