/* liftdiff 共有コア: native ランナと wasm ランナの両方に #include される (同一ソース = 同一ロジック)。
 *  - 領域 (image / arena / heap) の pristine 保存・復元・差分 (8B ブロック単位)
 *  - IAT import スタブの「応答モデル」(native/wasm で同じ応答を返す) と呼出ログ
 *  - 関数 entry トレース記録
 *  - 1 行プロトコル (LAYOUT / WR / BLOB / CASE) のパース、結果 JSON 生成
 * プラットフォーム固有部 (関数呼出し・シグナル・wasm 例外) は ld_native.c / ld_wasm.c / ld_runner.mjs。
 */
#ifndef LD_CORE_H
#define LD_CORE_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint64_t u64;
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;

/* ---------------- 領域 ---------------- */
#define LD_MAX_WR 16
#define LD_MAX_BLOBS 32
#define LD_HEAP_RESERVED 0x10000ull   /* heap 先頭 64KB = 偽 TEB / TLS 配列 (モデルが初期化) */
#define LD_TEB_OFF 0ull
#define LD_TLS_OFF 0x1000ull

typedef struct { u64 rva, len; u8* pristine; } ld_wr_t;
static ld_wr_t ld_wr[LD_MAX_WR];
static int ld_nwr;
static u8 *ld_img;            /* image 先頭 (RVA 0) のアドレス (プラットフォーム固有) */
static u8 *ld_arena, *ld_heap;
static u64 ld_arena_size, ld_heap_size;
static u64 ld_delta;          /* native - wasm の address ずれ (ポインタ正規化用, レポートに出力) */
static u64 ld_heap_used;      /* heap バンプ使用量 */
static u64 ld_heap_hw;        /* heap の high-water */
static u8* ld_heap_pristine; static u64 ld_heap_pristine_len, ld_heap_pristine_used;

typedef struct { char name[24]; u8* data; u64 len; u64* fix; int nfix; } ld_blob_t;
static ld_blob_t ld_blobs[LD_MAX_BLOBS];
static int ld_nblobs;
static u64 ld_arena_dirty_hw;   /* arena のうち blob で埋めた長さ (差分比較範囲) */
static u8* ld_arena_pristine;

/* ---------------- 呼出ログ / トレース ---------------- */
typedef struct { const char* name; u64 a[6]; u64 ret; } ld_call_t;
#define LD_MAX_CALLS 16384   /* CAB-233: boot 完走追跡のため entry 1 case で 2.6k+ 呼出を全記録 (旧 2048) */
static ld_call_t ld_calls[LD_MAX_CALLS];
static int ld_ncalls, ld_calls_over;

typedef struct { u64 va; u32 np; u64 a[8]; u64 x[4]; } ld_tr_t;
#define LD_MAX_TR 16384
static ld_tr_t ld_trs[LD_MAX_TR];
static int ld_ntr, ld_tr_over;
static int ld_trace_on;
/* LD-64 (#1854): IR basic block 入口の VA 列 (blk=1 の case のみ記録。compare は読まない)。
 * static 配列にすると wasm の data 配置が変わり、既存の static (ld_wr 等) と重なって結果が変わるため malloc で持つ。 */
#define LD_MAX_BLK 65536
static u64* ld_blks;
static int ld_nblk, ld_blk_over, ld_blk_on;

/* ---------------- 応答モデル ---------------- */
static u64 ld_tick, ld_qpc, ld_lasterr, ld_tls_next;
static u64 ld_tls_vals[1088];

/* ---- CAB-233: boot 拡張 stub (native 全起動の参照化) ----
 * 既存の応答 (上書きしない) に boot 完走に必要な応答を追加する。native/wasm が同じ
 * ld_core を共有するため全応答は両側で同一 (比較の公平性は不変)。 */
static u64 ld_fakemod_h[32];        /* 仮モジュールハンドル (LoadLibraryW 系の応答) */
static char ld_fakemod_n[32][64];
static int ld_nfakemod;
static struct { u64 mod; char name[96]; } ld_fakeprocs[256];
static int ld_nfakeproc;
static u64 ld_fake_atom;            /* RegisterClipboardFormatW / atom / handle 系の連番 */

/* CAB-233: 出力ポインタ (第1〜4引数に来る dst) の妥当性検査。
 * guest の不正 state 由来の garbage ポインタへの書込みが native ランナ自体を壊すため、
 * 書込み前に範囲を見る (wasm も同一規約 = 比較の公平性不変)。 */
static int ld_dst_ok(u64 p, u64 n) {
  if (!p || n > 0x100000ull) return 0;
  if (p >= (u64)(uintptr_t)ld_img && p + n <= (u64)(uintptr_t)ld_img + 0x1800000ull) return 1;   /* image (.data/.bss) */
  if (ld_arena && p >= (u64)(uintptr_t)ld_arena && p + n <= (u64)(uintptr_t)ld_arena + ld_arena_size) return 1;
  if (ld_heap && p >= (u64)(uintptr_t)ld_heap && p + n <= (u64)(uintptr_t)ld_heap + ld_heap_size) return 1;
  if (p >= 0x7f0000000000ull && p < 0x800000000000ull) return 1;   /* native host stack (guest stack) */
  return 0;
}

/* 仮 proc のアドレス規約: native も wasm も同じ「値」を使い (状態移送で散らからない)、
 * native 側だけその番地に実行可能 thunk を敷く (ld_native.c)。wasm は間接 call が
 * ott_dispatch → lift 集合外 → unlifted ret-0 に落ちる (m11 route も同様の ret-0 系)。 */
#define LD_FAKEPROC_BASE 0x50010000ull
#define LD_FAKEPROC_MARK 0x40000000ull   /* thunk → ld_stub_c に渡す index の目印 */
#define LD_FAKEPROC_SZ   32
/* LD-48 (#1398): fvm の VMT slot 専用の仮 proc index 域。GetProcAddress 側 (0..255) と重ならせ、
 * ld_nfakeproc を増やさない (増やすと以後の GetProcAddress 応答の index がずれる)。 */
#define LD_VMT_IDX0      256
#define LD_VMT_SLOTS     8
static const char* ld_vmslot_names[LD_VMT_SLOTS] = {"?vmslot0", "?vmslot1", "?vmslot2", "?vmslot3", "?vmslot4", "?vmslot5", "?vmslot6", "?vmslot7"};

static u64 ld_fake_ptr(u64 i);      /* プラットフォーム固有 (ld_native.c = 実行可能 thunk / wasm = 値のみ) */
static int ld_fakeproc_valid(u64 i) { return i < (u64)ld_nfakeproc || (i >= LD_VMT_IDX0 && i < LD_VMT_IDX0 + LD_VMT_SLOTS); }
static const char* ld_fakeproc_name(u64 i) {
  if (i >= LD_VMT_IDX0 && i < LD_VMT_IDX0 + LD_VMT_SLOTS) return ld_vmslot_names[i - LD_VMT_IDX0];
  return i < (u64)ld_nfakeproc ? ld_fakeprocs[i].name : "?freeproc";
}

static u64 ld_heap_alloc(u64 size, u64 align, int zero);   /* 前方宣言 (下段で定義) */
/* CAB-233: コマンドライン/環境ブロックは「ゲスト有効ポインタ」(ld_heap 内) を返す。
 * ホスト静的アドレスを返すと Delphi 側が image base 相対の算術をして不正 call になる (実測)。 */
static u64 ld_cmdline_ptr(int w) {
  static u64 hp;
  if (!hp && ld_heap) {
    hp = ld_heap_alloc(64, 16, 1);
    if (w) { const char* s = "\"FL64.exe\""; for (int i = 0; s[i]; i++) ((uint16_t*)(uintptr_t)hp)[i] = (uint16_t)s[i]; }
    else { const char* s = "\"FL64.exe\""; memcpy((void*)(uintptr_t)hp, s, 11); }
  }
  return hp;
}
static u64 ld_env_ptr(int w) {
  static u64 hp;
  if (!hp && ld_heap) hp = ld_heap_alloc(64, 16, 1);   /* 空環境ブロック (double-NUL) */
  return hp;
}


static u64 ld_read_strW(u64 p, char* out, int max) {   /* UTF-16 → ASCII (名前取得用) */
  int k = 0; const uint16_t* s = (const uint16_t*)(uintptr_t)p;
  if (!s) { out[0] = 0; return 0; }
  while (k < max - 1 && s[k]) { out[k] = (char)s[k]; k++; }
  out[k] = 0; return k;
}
static u64 ld_read_strA(u64 p, char* out, int max) {
  int k = 0; const char* s = (const char*)(uintptr_t)p;
  if (!s) { out[0] = 0; return 0; }
  while (k < max - 1 && s[k]) { out[k] = s[k]; k++; }
  out[k] = 0; return k;
}
/* 仮モジュール (名前で同一視). 戻り: ハンドル */
static u64 ld_fakemod_get(const char* nm) {
  for (int i = 0; i < ld_nfakemod; i++) if (strcmp(ld_fakemod_n[i], nm) == 0) return ld_fakemod_h[i];
  if (ld_nfakemod >= 32) return 0x5000f000ull;
  snprintf(ld_fakemod_n[ld_nfakemod], sizeof ld_fakemod_n[0], "%s", nm);
  ld_fakemod_h[ld_nfakemod] = 0x50000000ull + 0x10000ull * ld_nfakemod;
  return ld_fakemod_h[ld_nfakemod++];
}
/* 仮 proc: (mod, name) で同一視 → ld_fake_ptr(i) (native = 実行可能 stub, wasm = 不透明値) */
static u64 ld_fakeproc_get(u64 mod, const char* nm) {
  for (int i = 0; i < ld_nfakeproc; i++) if (ld_fakeprocs[i].mod == mod && strcmp(ld_fakeprocs[i].name, nm) == 0) return ld_fake_ptr(i);
  if (ld_nfakeproc >= LD_VMT_IDX0) { fprintf(stderr, "[ld_core] 仮 proc が上限 %d を超えた (VMT 域と衝突するため中止)\n", LD_VMT_IDX0); abort(); }
  ld_fakeprocs[ld_nfakeproc].mod = mod;
  snprintf(ld_fakeprocs[ld_nfakeproc].name, sizeof ld_fakeprocs[0].name, "%s", nm);
  return ld_fake_ptr(ld_nfakeproc++);
}
/* .rsrc の RT_STRING (type 6) から LoadStringW 用の文字列を引く. 戻り: wchar 長 (0 = 見つからず) */
static u64 ld_rsrc_string(u64 id, uint16_t* dst, u64 cch) {
  const u8* img = ld_img;
  if (!img) return 0;
  u32 pe = 0; memcpy(&pe, img + 0x3c, 4);
  if (pe + 24 + 96 > 0x10000000ull) return 0;
  u16 nsec = 0; memcpy(&nsec, img + pe + 6, 2);
  u16 optsz = 0; memcpy(&optsz, img + pe + 20, 2);
  u32 rsrc_rva = 0, rsrc_sz = 0;
  memcpy(&rsrc_rva, img + pe + 24 + 112 + 8 * 2, 4);   /* DD[2] = リソース */
  memcpy(&rsrc_sz, img + pe + 24 + 112 + 8 * 2 + 4, 4);
  if (!rsrc_rva) return 0;
  /* セクション .rsrc の先頭 (RVA→ファイル配置はセクション VA に等置なので RVA==offset) */
  u32 sec_rva = 0, sec_raw = 0, sec_vsz = 0;
  for (int i = 0; i < nsec; i++) {
    const u8* s = img + pe + 24 + optsz + 40 * (u32)i;
    if (memcmp(s, ".rsrc", 5) == 0) {
      memcpy(&sec_vsz, s + 8, 4); memcpy(&sec_rva, s + 12, 4); memcpy(&sec_raw, s + 20, 4);
      break;
    }
  }
  if (!sec_rva) return 0;
  /* ディレクトリ歩き: type 6 → name = id/16+1 → lang → DATA_ENTRY(rva,size) */
  u32 level_id[3] = { 6, id / 16 + 1, 0 };
  u32 off = rsrc_rva;
  for (int lvl = 0; lvl < 3; lvl++) {
    u16 nn = 0, nn2 = 0;
    memcpy(&nn, img + off + 12, 2); memcpy(&nn2, img + off + 14, 2);
    int total = nn + nn2, found = -1;
    for (int i = 0; i < total; i++) {
      u32 nm = 0; memcpy(&nm, img + off + 16 + 8 * (u32)i, 4);
      u32 idv = nm & 0x7fffffffu;
      if (lvl == 2) { found = i; break; }   /* 言語は最初の entry */
      if (idv == level_id[lvl]) { found = i; break; }
    }
    if (found < 0) return 0;
    u32 sub = 0; memcpy(&sub, img + off + 20 + 8 * (u32)found, 4);
    if (sub & 0x80000000u) { off = rsrc_rva + (sub & 0x7fffffffu); continue; }
    /* DATA_ENTRY: RVA, size → RT_STRING ブロック (u16 len + len wchars ×16 個) */
    u32 drva = 0;
    memcpy(&drva, img + rsrc_rva + sub, 4);
    const u8* p = img + drva;
    for (int j = 0; j < (int)(id % 16); j++) {
      u16 l2 = 0; memcpy(&l2, p, 2);
      p += 2 + 2 * (u64)l2;
    }
    u16 len = 0; memcpy(&len, p, 2);
    if (cch) {
      u64 n = len < cch - 1 ? len : (cch ? cch - 1 : 0);
      for (u64 k = 0; k < n; k++) { uint16_t ch = 0; memcpy(&ch, p + 2 + k * 2, 2); dst[k] = ch; }
      if (cch) dst[n] = 0;
      return n;
    }
    return len;
  }
  return 0;
}

static void ld_model_reset(void) {
  ld_tick = 1000; ld_qpc = 100000; ld_lasterr = 0; ld_tls_next = 1;
  memset(ld_tls_vals, 0, sizeof ld_tls_vals);
  if (ld_heap) {
    u64 z = ld_heap_hw > LD_HEAP_RESERVED ? ld_heap_hw : LD_HEAP_RESERVED;
    if (ld_heap_pristine) {
      memcpy(ld_heap, ld_heap_pristine, ld_heap_pristine_len);
      if (z > ld_heap_pristine_len) memset(ld_heap + ld_heap_pristine_len, 0, z - ld_heap_pristine_len);
      ld_heap_hw = ld_heap_pristine_len; ld_heap_used = ld_heap_pristine_used;
    } else {
      memset(ld_heap, 0, z);
      ld_heap_hw = LD_HEAP_RESERVED; ld_heap_used = 0;
      /* 偽 TEB: +0x30 = self, +0x58 = TLS 配列 */
      u64* teb = (u64*)(ld_heap + LD_TEB_OFF);
      teb[0x30 / 8] = (u64)(uintptr_t)teb;
      teb[0x58 / 8] = (u64)(uintptr_t)(ld_heap + LD_TLS_OFF);
      teb[0x08 / 8] = (u64)(uintptr_t)(ld_heap + LD_HEAP_RESERVED);
    }
  }
}
static u64 ld_heap_alloc(u64 size, u64 align, int zero) {
  if (align < 16) align = 16;
  u64 off = (LD_HEAP_RESERVED + ld_heap_used + align - 1) & ~(align - 1);
  u64 end = off + size;
  if (!ld_heap || end > ld_heap_size) return 0;
  ld_heap_used = end - LD_HEAP_RESERVED;
  if (end > ld_heap_hw) ld_heap_hw = end;
  (void)zero;   /* heap は常に 0 クリア済 (case 毎に high-water まで memset) */
  return (u64)(uintptr_t)(ld_heap + off);
}
static int ld_streq(const char* a, const char* b) { return strcmp(a, b) == 0; }

/* WIN-9 (#2760): LD_CATALOG_MO=<.mo の path> 指定時だけ、*.moe の属性・open・seek・read を実カタログで応答する (実験).
 * 未指定と wasm (__EMSCRIPTEN__) は従来の応答のまま。既定の 0 応答では size 0 → 確保 NULL → rip 0x4e0fab の null 読み
 * (tools/liftdiff/REPORT_WIN7_2718.md §1.2)。 */
#define LD_CAT_H 0x65000001ull
static u8* ld_cat_buf; static u64 ld_cat_len, ld_cat_pos; static int ld_cat_tried;
static int ld_cat_on(void) {
#ifndef __EMSCRIPTEN__
  if (!ld_cat_tried) {
    const char* p = getenv("LD_CATALOG_MO"); FILE* f = p ? fopen(p, "rb") : NULL; long l = 0;
    ld_cat_tried = 1;
    if (f) {
      fseek(f, 0, SEEK_END); l = ftell(f); fseek(f, 0, SEEK_SET);
      if (l > 0) { ld_cat_buf = (u8*)malloc((size_t)l); if (ld_cat_buf && fread(ld_cat_buf, 1, (size_t)l, f) == (size_t)l) ld_cat_len = (u64)l; else { free(ld_cat_buf); ld_cat_buf = NULL; } }
      fclose(f);
    }
  }
#endif
  return ld_cat_buf != NULL;
}
static int ld_cat_path(u64 a) { char nm[160]; u64 l = ld_read_strW(a, nm, sizeof nm); return l >= 4 && strcmp(nm + l - 4, ".moe") == 0; }

/* name = import 名 (kernel32 等の区別はしない), a[] = 位置引数 (ms64 先頭 4 つ) */
static u64 ld_model_call(const char* n, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5) {
  (void)a4; (void)a5;   /* 第5/6引数: 6引数 API (MultiByteToWideChar 等) が CAB-233 で使用 */
  /* ---- CAB-233: boot 拡張 (native 全起動の参照化). 既存応答は下で維持 ---- */
  { char nm[96];
    if (ld_streq(n, "LoadLibraryW") || ld_streq(n, "LoadLibraryExW") || ld_streq(n, "LoadLibraryA") || ld_streq(n, "LoadLibraryExA")) {
      if (n[12] == 'W' || n[12] == 'E') ld_read_strW(a0, nm, sizeof nm); else ld_read_strA(a0, nm, sizeof nm);
      if (!nm[0]) snprintf(nm, sizeof nm, "mod%d", ld_nfakemod);
      return ld_fakemod_get(nm);
    }
    if (ld_streq(n, "FreeLibrary")) return 1;
    if (ld_streq(n, "GetProcAddress")) {
      u64 mod = a0 ? a0 : (u64)(uintptr_t)ld_img;
      const char* mn = "?";
      for (int i = 0; i < ld_nfakemod; i++) if (ld_fakemod_h[i] == mod) mn = ld_fakemod_n[i];
      char pn[80];
      if ((a1 >> 16) == 0 && (a1 & 0xffff)) snprintf(pn, sizeof pn, "#%u", (unsigned)(a1 & 0xffff));   /* ordinal */
      else ld_read_strA(a1, pn, sizeof pn);
      char full[96 + 96];
      snprintf(full, sizeof full, "%s!%s", mn, pn);
      return ld_fakeproc_get(mod, full);
    }
    if (ld_streq(n, "GetModuleHandleW") || ld_streq(n, "GetModuleHandleA")) {
      if (a0) {
        if (n[strlen(n) - 1] == 'W') ld_read_strW(a0, nm, sizeof nm); else ld_read_strA(a0, nm, sizeof nm);
        for (int i = 0; i < ld_nfakemod; i++) if (strcmp(ld_fakemod_n[i], nm) == 0) return ld_fakemod_h[i];
        return 0;
      }
      return (u64)(uintptr_t)ld_img;
    }
    if (ld_streq(n, "acmMetrics")) { if (a2 && ld_dst_ok(a2, 4)) *(u32*)(uintptr_t)a2 = 1; return 0; }
    if (ld_streq(n, "GetLocaleInfoW") || ld_streq(n, "GetLocaleInfoA")) {
      /* 既定の書式設定 (en-US 相当の決定値). cch=0 は必要長を返す */
      static const struct { u32 ty; const char* s; } T[] = {
        {0x0009, "0409"}, {0x000a, "1"}, {0x000b, "2"}, {0x000e, "."}, {0x000f, ","}, {0x0010, "3;0"},
        {0x0012, "1"}, {0x0014, "$"}, {0x0016, "."}, {0x0017, ","}, {0x001b, "2"}, {0x001c, ";"},
        {0x001d, "/"}, {0x001e, ":"}, {0x001f, "M/d/yyyy"}, {0x0020, "dddd, MMMM dd, yyyy"},
        {0x1003, "h:mm:ss tt"}, {0x100c, "6"}, {0x100d, "0"}, {0x1010, "1"}, {0x1013, "0123456789"},
        {0x1022, "+"}, {0x101b, "-"}, {0x1004, "en-US"},
      };
      const char* s = "0";
      u32 ty = (u32)a1;
      for (unsigned i = 0; i < sizeof T / sizeof T[0]; i++) if (T[i].ty == ty) { s = T[i].s; break; }
      u64 l = strlen(s);
      if (n[strlen(n) - 1] == 'A') {   /* ANSI 版: そのまま書く */
        if (a2 && a3 && ld_dst_ok(a2, l + 2)) { u64 nn = l < a3 - 1 ? l : a3 - 1; memcpy((void*)(uintptr_t)a2, s, nn); ((char*)(uintptr_t)a2)[nn] = 0; return (u64)(int)(a3 ? nn + 1 : 0); }
        return l + 1;
      }
      if (a2 && a3 && ld_dst_ok(a2, l * 2 + 2)) { u64 nn = l < a3 - 1 ? l : a3 - 1; for (u64 k = 0; k < nn; k++) ((uint16_t*)(uintptr_t)a2)[k] = (uint16_t)s[k]; ((uint16_t*)(uintptr_t)a2)[nn] = 0; return (u64)(int)(a3 ? nn + 1 : 0); }
      return l + 1;
    }
    if (ld_streq(n, "GetModuleFileNameW") || ld_streq(n, "GetModuleFileNameA")) {
      const char* s = (a0 == 0 || a0 == (u64)(uintptr_t)ld_img) ? "FL64.exe" : "FLEngine_x64.dll";
      u64 l = strlen(s);
      if (n[strlen(n) - 1] == 'A') { if (a1 && a2 && ld_dst_ok(a1, l + 2)) { u64 nn = l < a2 - 1 ? l : a2 - 1; memcpy((void*)(uintptr_t)a1, s, nn); ((char*)(uintptr_t)a1)[nn] = 0; return nn; } return 0; }
      if (a1 && a2 && ld_dst_ok(a1, l * 2 + 2)) { u64 nn = l < a2 - 1 ? l : a2 - 1; for (u64 k = 0; k < nn; k++) ((uint16_t*)(uintptr_t)a1)[k] = (uint16_t)s[k]; ((uint16_t*)(uintptr_t)a1)[nn] = 0; return nn; }
      return 0;
    }
    if (ld_cat_on()) {   /* WIN-9 (#2760) 実験: LD_CATALOG_MO 指定時のみ */
      if (ld_streq(n, "GetFileAttributesW") && ld_cat_path(a0)) return 0x80;   /* FILE_ATTRIBUTE_NORMAL */
      if (ld_streq(n, "CreateFileW") && ld_cat_path(a0)) { ld_cat_pos = 0; return LD_CAT_H; }
      if (ld_streq(n, "SetFilePointer") && (u32)a0 == (u32)LD_CAT_H) {
        u32 m = (u32)a3; u64 np = m == 0 ? (u64)(int64_t)(int32_t)a1 : m == 1 ? ld_cat_pos + (u64)(int64_t)(int32_t)a1 : ld_cat_len + (u64)(int64_t)(int32_t)a1;
        ld_cat_pos = np;
        if (a2 && ld_dst_ok(a2, 4)) *(u32*)(uintptr_t)a2 = 0;
        return (u32)np;
      }
      if (ld_streq(n, "ReadFile") && (u32)a0 == (u32)LD_CAT_H) {
        u64 k = ld_cat_pos < ld_cat_len ? ld_cat_len - ld_cat_pos : 0;
        if (k > (u32)a2) k = (u32)a2;
        if (a1 && k && ld_dst_ok(a1, k)) memcpy((void*)(uintptr_t)a1, ld_cat_buf + ld_cat_pos, k);
        ld_cat_pos += k;
        if (a3 && ld_dst_ok(a3, 4)) *(u32*)(uintptr_t)a3 = (u32)k;
        return 1;
      }
    }
    if (ld_streq(n, "GetFileAttributesW") || ld_streq(n, "GetFileAttributesA")) return (u64)-1;   /* FILE NOT FOUND */
    if (ld_streq(n, "GetFileAttributesExW") || ld_streq(n, "GetFileAttributesExA")) {
      if (a2 && ld_dst_ok(a2, 24)) { u32* q = (u32*)(uintptr_t)a2; q[0] = 0x80; q[1] = 0; q[2] = 0; q[3] = 0; q[4] = 0; q[5] = 0; }   /* attrib=NORMAL, sizes/times=0 */
      return 1;
    }
    if (ld_streq(n, "RegOpenKeyExW") || ld_streq(n, "RegOpenKeyExA") || ld_streq(n, "RegCreateKeyExW") || ld_streq(n, "RegCreateKeyA") || ld_streq(n, "RegDeleteKeyW") || ld_streq(n, "RegDeleteValueW") || ld_streq(n, "RegQueryValueExW") || ld_streq(n, "RegQueryValueW")) return 2;   /* ERROR_FILE_NOT_FOUND (レジストリ空扱い, m11 #12 同一) */
    if (ld_streq(n, "RegEnumKeyExW") || ld_streq(n, "RegEnumKeyW") || ld_streq(n, "RegEnumValueW")) return 259;   /* ERROR_NO_MORE_ITEMS */
    if (ld_streq(n, "RegCloseKey") || ld_streq(n, "RegFlushKey")) return 0;
    if (ld_streq(n, "RegisterClipboardFormatW") || ld_streq(n, "RegisterClipboardFormatA") || ld_streq(n, "RegisterWindowMessageW") || ld_streq(n, "RegisterWindowMessageA") || ld_streq(n, "GlobalAddAtomW") || ld_streq(n, "GlobalAddAtomA")) return 0xC000ull + (++ld_fake_atom);
    if (ld_streq(n, "GlobalFindAtomW") || ld_streq(n, "GlobalFindAtomA")) return 0;
    if (ld_streq(n, "GlobalDeleteAtom")) return 0;
    if (ld_streq(n, "GlobalLock")) return a0;
    if (ld_streq(n, "GlobalUnlock")) return 1;
    if (ld_streq(n, "CreateEventW") || ld_streq(n, "CreateEventA") || ld_streq(n, "CreateMutexW") || ld_streq(n, "CreateMutexA") || ld_streq(n, "CreateSemaphoreW") || ld_streq(n, "CreateSemaphoreA") || ld_streq(n, "CreateWaitableTimerW")) return 0x60000000ull + (++ld_fake_atom);
    if (ld_streq(n, "SetEvent") || ld_streq(n, "ResetEvent") || ld_streq(n, "PulseEvent") || ld_streq(n, "SetWaitableTimer")) return 1;
    if (ld_streq(n, "WaitForSingleObject") || ld_streq(n, "WaitForSingleObjectEx") || ld_streq(n, "SignalObjectAndWait")) return 0;   /* WAIT_OBJECT_0 */
    if (ld_streq(n, "WaitForMultipleObjects") || ld_streq(n, "WaitForMultipleObjectsEx")) return 0;
    if (ld_streq(n, "GetDC") || ld_streq(n, "GetDCEx") || ld_streq(n, "GetWindowDC")) return 0x61000000ull + (++ld_fake_atom);
    if (ld_streq(n, "ReleaseDC")) return 1;
    if (ld_streq(n, "GetDeviceCaps")) {
      u32 i = (u32)a1;
      if (i == 8 || i == 118) return 1920;    /* HORZRES / DESKTOPHORZRES */
      if (i == 10) return 1080;               /* VERTRES */
      if (i == 12) return 32;                 /* BITSPIXEL */
      if (i == 14) return 1;                  /* PLANES */
      if (i == 88 || i == 90) return 96;      /* LOGPIXELSX/Y */
      if (i == 116) return 60;                /* VREFRESH */
      if (i == 2) return 2;                   /* TECHNOLOGY = DT_RASDISPLAY */
      return 0;
    }
    if (ld_streq(n, "GetStockObject")) return 0x62000000ull + a0;
    if (ld_streq(n, "LoadImageW") || ld_streq(n, "LoadImageA") || ld_streq(n, "LoadIconW") || ld_streq(n, "LoadIconA") || ld_streq(n, "LoadCursorW") || ld_streq(n, "LoadCursorA") || ld_streq(n, "CopyImage")) return 0x63000000ull + (++ld_fake_atom);
    if (ld_streq(n, "DestroyIcon") || ld_streq(n, "DestroyCursor")) return 1;
    if (ld_streq(n, "GetVersionExW") || ld_streq(n, "GetVersionExA")) {
      if (a0 && ld_dst_ok(a0, 0x120)) {
        u32* q = (u32*)(uintptr_t)a0;
        u32 cb = q[0];
        q[1] = 6; q[2] = 1; q[3] = 7601; q[4] = 2;   /* Win7 SP1 */
        /* szCSDVersion = "Service Pack 1" (Win7 SP1 相当) */
        if (n[strlen(n) - 1] == 'W') { uint16_t* sp = (uint16_t*)(uintptr_t)(a0 + 0x14); for (int i = 0; i < 64; i++) sp[i] = i < 14 ? (uint16_t)"Service Pack 1"[i] : 0; }
        else { char* sp = (char*)(uintptr_t)(a0 + 0x14); snprintf(sp, 128, "Service Pack 1"); }
        (void)cb;
      }
      return 1;
    }
    if (ld_streq(n, "GetNativeSystemInfo") || ld_streq(n, "GetSystemInfo")) {
      if (a0 && ld_dst_ok(a0, 48)) {
        u16* w = (u16*)(uintptr_t)a0; u32* d = (u32*)(uintptr_t)a0; u64* q = (u64*)(uintptr_t)a0;
        w[0] = 9; w[1] = 0;              /* wProcessorArchitecture = PROCESSOR_ARCHITECTURE_AMD64 */
        d[1] = 4096;                     /* dwPageSize */
        q[1] = 0x10000; q[2] = 0x7ffeffffull;   /* lpMinimum/MaximumApplicationAddress */
        q[3] = 0xff;                     /* dwActiveProcessorMask */
        d[8] = 8; d[9] = 8664; d[10] = 0x10000; /* dwNumberOfProcessors / dwProcessorType / dwAllocationGranularity */
        w[22] = 6; w[23] = 0x3c00;       /* wProcessorLevel / wProcessorRevision (仮) */
      }
      return 0;
    }
    if (ld_streq(n, "VerSetConditionMask")) {
      u64 m = a0; u32 t = (u32)a1; u8 c = (u8)(a2 & 7);
      static const u32 bits[8] = { 0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80 };
      for (int i = 0; i < 8; i++) if (t & bits[i]) return m | ((u64)c << (8 * i));
      return m;
    }
    if (ld_streq(n, "GetCPInfo")) { if (a1 && ld_dst_ok(a1, 20)) { u32* q = (u32*)(uintptr_t)a1; q[0] = 1; ((u8*)q)[4] = '?'; ((u8*)q)[5] = 0; memset((u8*)q + 6, 0, 12); } return 1; }
    if (ld_streq(n, "GetACP")) return 1252;
    if (ld_streq(n, "GetOEMCP")) return 437;
    if (ld_streq(n, "SetThreadErrorMode")) { if (a1 && ld_dst_ok(a1, 4)) *(u32*)(uintptr_t)a1 = 0; return 1; }
    if (ld_streq(n, "SetErrorMode")) return 0;
    if (ld_streq(n, "CharLowerBuffW")) { if (!ld_dst_ok(a0, a1 * 2 + 2)) return a1; uint16_t* p = (uint16_t*)(uintptr_t)a0; for (u64 i = 0; p && i < a1; i++) if (p[i] >= 'A' && p[i] <= 'Z') p[i] += 32; return a1; }
    if (ld_streq(n, "CharUpperBuffW")) { if (!ld_dst_ok(a0, a1 * 2 + 2)) return a1; uint16_t* p = (uint16_t*)(uintptr_t)a0; for (u64 i = 0; p && i < a1; i++) if (p[i] >= 'a' && p[i] <= 'z') p[i] -= 32; return a1; }
    if (ld_streq(n, "MultiByteToWideChar")) {   /* CAB-233: dst (第5/6引数) への書込みあり (cp 0/1252 = Latin-1 相当) */
      char big[1024];
      int64_t sl = (int64_t)a3;
      u64 need;
      const u8* s = (const u8*)(uintptr_t)a2;
      if (sl < 0) { u64 l = ld_read_strA(a2, big, sizeof big); need = l + 1; s = (const u8*)big; sl = (int64_t)l; }
      else need = (u64)sl;
      if (!ld_dst_ok(a4, need * 2 + 2)) return need;
      u64 n2 = need < a5 ? need : a5;
      for (u64 i = 0; i < n2; i++) ((uint16_t*)(uintptr_t)a4)[i] = s[i];
      return n2;
    }
    if (ld_streq(n, "WideCharToMultiByte")) {
      char big[2048];
      int64_t wl = (int64_t)a3;
      u64 need;
      const uint16_t* s = (const uint16_t*)(uintptr_t)a2;
      if (wl < 0) { u64 l = ld_read_strW(a2, big, sizeof big); need = l + 1; s = (const uint16_t*)big; wl = (int64_t)l; }
      else need = (u64)wl;
      if (!ld_dst_ok(a4, need + 1)) return need;
      u64 n2 = need < a5 ? need : a5;
      for (u64 i = 0; i < n2; i++) { uint16_t ch = s[i]; ((u8*)(uintptr_t)a4)[i] = (u8)(ch < 256 ? ch : '?'); }
      return n2;
    }
    if (ld_streq(n, "IsDebuggerPresent")) return 0;
    if (ld_streq(n, "CheckRemoteDebuggerPresent")) { if (a1 && ld_dst_ok(a1, 4)) *(u32*)(uintptr_t)a1 = 0; return 1; }
    if (ld_streq(n, "IsWow64Process")) { if (a1 && ld_dst_ok(a1, 4)) *(u32*)(uintptr_t)a1 = 0; return 1; }
    if (ld_streq(n, "GetStartupInfoW") || ld_streq(n, "GetStartupInfoA")) { if (a0 && ld_dst_ok(a0, 104)) memset((void*)(uintptr_t)(a0 + 4), 0, 64); return 0; }
    if (ld_streq(n, "GetCommandLineW") || ld_streq(n, "GetCommandLineA")) return ld_cmdline_ptr(n[strlen(n) - 1] == 'W');
    if (ld_streq(n, "GetEnvironmentStringsW") || ld_streq(n, "GetEnvironmentStringsA") || ld_streq(n, "GetEnvironmentStrings")) return ld_env_ptr(n[strlen(n) - 1] == 'W');
    if (ld_streq(n, "GetCurrentDirectoryW") || ld_streq(n, "GetCurrentDirectoryA")) {
      const char* s = "C:\\";
      if (n[strlen(n) - 1] == 'W') { if (a1 && a2 && ld_dst_ok(a1, 10)) { for (u64 k = 0; k < 3 && k + 1 < a2; k++) ((uint16_t*)(uintptr_t)a1)[k] = (uint16_t)s[k]; ((uint16_t*)(uintptr_t)a1)[3] = 0; return 3; } return 4; }
      if (a1 && a2 && ld_dst_ok(a1, 6)) { u64 nn = 3 < a2 - 1 ? 3 : a2 - 1; memcpy((void*)(uintptr_t)a1, s, nn); ((char*)(uintptr_t)a1)[nn] = 0; return nn; }
      return 4;
    }
    if (ld_streq(n, "SetCurrentDirectoryW") || ld_streq(n, "SetCurrentDirectoryA")) return 1;
    if (ld_streq(n, "GetSystemDirectoryW") || ld_streq(n, "GetWindowsDirectoryW") || ld_streq(n, "GetTempPathW")) {
      const char* s = ld_streq(n, "GetWindowsDirectoryW") ? "C:\\Windows" : ld_streq(n, "GetTempPathW") ? "C:\\Temp\\" : "C:\\Windows\\system32";
      u64 l = strlen(s);
      if (a0 && a1 && ld_dst_ok(a0, l * 2 + 2)) { for (u64 k = 0; k < l && k + 1 < a1; k++) ((uint16_t*)(uintptr_t)a0)[k] = (uint16_t)s[k]; ((uint16_t*)(uintptr_t)a0)[l < a1 - 1 ? l : a1 - 1] = 0; return l; }
      return l + 1;
    }
    if (ld_streq(n, "HeapCreate")) return 0x64000000ull + (++ld_fake_atom);
    if (ld_streq(n, "HeapDestroy") || ld_streq(n, "HeapSetInformation") || ld_streq(n, "HeapValidate")) return 1;
    if (ld_streq(n, "InitializeCriticalSectionAndSpinCount")) return 1;
    if (ld_streq(n, "GetCurrentProcessorNumber")) return 0;
    /* ファイル系 (CreateFileW/FindFirstFileW/SetFilePointer) は既定 0 を返す (下段従来動作)。
     * 実測 (CAB-233): (1) INVALID_HANDLE_VALUE (-1) にすると entry が unit 159 の別地点 (0x2690dc) に落ち
     * 906/942 に後退、(2) CreateFileW 仮ハンドル (0x65000001) + ReadFile 失敗 (0) でも unit 830/895/898 の
     * .moe loader (rip 0x4e0fab) は救えない (= ReadFile が実バイトを返せないのが根源)。
     * (3) 実カタログ供給実験 (win64extracted/block25158_DATA.bin = gettext .mo 先頭 magic 0x950412de, 47,405B を
     *     CreateFileW→仮 handle + ReadFile で読ませる): magic check (0x4e1a3c) は通るが、catalog iteration loop
     *     (0x513da9 の VMT 仮想 call Get(i)) から rbp ごと破壊されて戻る (rbp=0x7fff00000000, rdx=.mo の host バッファ)
     *     → unit 830/895/898 は embodiment 深层の stub ギャップが残る。0 応答で 928/942 が最良。
     * 真正ファイル I/O 接続 (System/Languages/LC_MESSAGES/default.moe = block25158) は下流タスクへ。 */
  }
  if (ld_streq(n, "VirtualAlloc")) { if (a0) return a0; return ld_heap_alloc((u32)a1 ? (a1 & 0xffffffffull) : 0x1000, 0x10000, 1); }
  if (ld_streq(n, "VirtualFree") || ld_streq(n, "HeapFree") || ld_streq(n, "CloseHandle") || ld_streq(n, "TlsFree")) return 1;
  if (ld_streq(n, "VirtualProtect")) { if (a3) *(u32*)(uintptr_t)a3 = 4; return 1; }
  if (ld_streq(n, "VirtualQuery")) return a2;
  if (ld_streq(n, "GetProcessHeap")) return 0x1000;
  if (ld_streq(n, "HeapAlloc")) return ld_heap_alloc(a2, 16, (a1 & 8) != 0);
  if (ld_streq(n, "LocalAlloc") || ld_streq(n, "GlobalAlloc")) return ld_heap_alloc(a1, 16, 1);
  if (ld_streq(n, "LocalFree") || ld_streq(n, "GlobalFree")) return 0;
  if (ld_streq(n, "GetLastError")) return ld_lasterr;
  if (ld_streq(n, "SetLastError")) { ld_lasterr = (u32)a0; return 0; }
  if (ld_streq(n, "QueryPerformanceCounter")) { ld_qpc += 1000; if (a0) *(u64*)(uintptr_t)a0 = ld_qpc; return 1; }
  if (ld_streq(n, "QueryPerformanceFrequency")) { if (a0) *(u64*)(uintptr_t)a0 = 10000000ull; return 1; }
  if (ld_streq(n, "GetTickCount") || ld_streq(n, "timeGetTime")) { ld_tick += 16; return ld_tick; }
  if (ld_streq(n, "TlsAlloc")) return ld_tls_next++;
  if (ld_streq(n, "TlsGetValue")) return ld_heap ? *(u64*)(ld_heap + LD_TLS_OFF + (a0 & 1023) * 8) : ld_tls_vals[a0 & 1023];
  if (ld_streq(n, "TlsSetValue")) { if (ld_heap) *(u64*)(ld_heap + LD_TLS_OFF + (a0 & 1023) * 8) = a1; else ld_tls_vals[a0 & 1023] = a1; return 1; }
  if (ld_streq(n, "GetCurrentThreadId") || ld_streq(n, "GetCurrentProcessId")) return 0x1234;
  if (ld_streq(n, "GetCurrentProcess") || ld_streq(n, "GetCurrentThread")) return (u64)-1;
  if (ld_streq(n, "GetModuleHandleW")) return a0 ? 0 : (u64)(uintptr_t)ld_img;
  if (ld_streq(n, "lstrlenW")) { const uint16_t* p = (const uint16_t*)(uintptr_t)a0; u64 k = 0; if (p) while (p[k]) k++; return k; }
  if (ld_streq(n, "MulDiv")) { int64_t d = (int32_t)a2; if (!d) return (u64)-1; int64_t v = (int64_t)(int32_t)a0 * (int32_t)a1; return (u64)(int32_t)((v + (v < 0 ? -d / 2 : d / 2)) / d); }
  if (ld_streq(n, "GetVersion")) return 0x0a00;
  if (ld_streq(n, "SysAllocStringLen") || ld_streq(n, "SysReAllocStringLen")) {   /* BSTR: [len bytes u32][chars][NUL] */
    u64 len = a1 & 0xffffffffull; u64 b = ld_heap_alloc(4 + 2 * len + 2 + 8, 8, 1); if (!b) return 0;
    u8* p = (u8*)(uintptr_t)b; *(u32*)p = (u32)(len * 2);
    const uint16_t* src = (const uint16_t*)(uintptr_t)(ld_streq(n, "SysAllocStringLen") ? a0 : a1);
    u64 cnt = ld_streq(n, "SysAllocStringLen") ? len : (a2 & 0xffffffffull); (void)cnt;
    if (src && ld_streq(n, "SysAllocStringLen")) memcpy(p + 4, src, len * 2);
    return b + 4;
  }
  if (ld_streq(n, "SysStringLen")) return a0 ? *(u32*)(uintptr_t)(a0 - 4) / 2 : 0;
  return 0;   /* 既定: 0 を返す (全 import で native/wasm 同一) */
}
static u64 ld_stub(const char* n, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5) {
  u64 r = ld_model_call(n, a0, a1, a2, a3, a4, a5);
  if (ld_ncalls < LD_MAX_CALLS) {
    ld_call_t* c = &ld_calls[ld_ncalls++];
    c->name = n; c->a[0] = a0; c->a[1] = a1; c->a[2] = a2; c->a[3] = a3; c->a[4] = a4; c->a[5] = a5; c->ret = r;
  } else ld_calls_over++;
  return r;
}
static void ld_blk_rec(u64 va) {
  if (!ld_blk_on) return;
  if (ld_nblk >= LD_MAX_BLK) { ld_blk_over++; return; }
  if (!ld_blks) ld_blks = (u64*)malloc(LD_MAX_BLK * sizeof(u64));
  ld_blks[ld_nblk++] = va;
}
static void ld_trace_rec(u64 va, u32 np, const u64* a, const u64* x) {
  if (!ld_trace_on) return;
  if (ld_ntr >= LD_MAX_TR) { ld_tr_over++; return; }
  ld_tr_t* t = &ld_trs[ld_ntr++];
  t->va = va; t->np = np;
  memcpy(t->a, a, sizeof t->a); memcpy(t->x, x, sizeof t->x);
}

/* ---------------- pristine / 復元 / 差分 ---------------- */
static void ld_add_wr(u64 rva, u64 len) {
  if (ld_nwr >= LD_MAX_WR) return;
  ld_wr[ld_nwr].rva = rva; ld_wr[ld_nwr].len = len; ld_wr[ld_nwr].pristine = NULL; ld_nwr++;
}
/* VMT slot の仮 proc 番地を snapshot 前に生成 (native は thunk 敷設) し、cases.make_blob_vm の値と一致しなければ中止 */
static void ld_fakeproc_vmt_init(void) {
  for (u64 k = 0; k < LD_VMT_SLOTS; k++) {
    u64 i = LD_VMT_IDX0 + k;
    if (ld_fake_ptr(i) != LD_FAKEPROC_BASE + i * LD_FAKEPROC_SZ) {
      fprintf(stderr, "[ld_core] VMT slot %llu の仮 proc 番地が不一致 (fvm の silent miscompile になるため中止)\n", (unsigned long long)k);
      abort();
    }
  }
}
/* LD-153: 仮 proc の thunk は GetProcAddress 登録時にしか敷かれない。boot state を別プロセスへ移送すると、
 * 状態中の仮 proc 値 (index<LD_VMT_IDX0) が未生成の 0 埋めページを指し、実行で addr 0 に segv する。
 * snapshot 時に GetProcAddress 域の thunk も全部敷く (名前は別プロセスでは "?freeproc" になる)。 */
static void ld_fakeproc_thunks_init(void) {
  for (u64 i = 0; i < LD_VMT_IDX0; i++) ld_fake_ptr(i);
}
static void ld_snapshot(void) {
  ld_fakeproc_thunks_init();
  ld_fakeproc_vmt_init();
  for (int i = 0; i < ld_nwr; i++) {
    free(ld_wr[i].pristine);
    ld_wr[i].pristine = (u8*)malloc(ld_wr[i].len);
    memcpy(ld_wr[i].pristine, ld_img + ld_wr[i].rva, ld_wr[i].len);
  }
  free(ld_arena_pristine); ld_arena_pristine = (u8*)calloc(1, ld_arena_size);
  if (ld_heap_hw == 0) ld_model_reset();   /* 初回: TEB 初期化 */
  free(ld_heap_pristine); ld_heap_pristine_len = ld_heap_hw > LD_HEAP_RESERVED ? ld_heap_hw : LD_HEAP_RESERVED;
  ld_heap_pristine = (u8*)malloc(ld_heap_pristine_len); memcpy(ld_heap_pristine, ld_heap, ld_heap_pristine_len);
  ld_heap_pristine_used = ld_heap_used;
}
static void ld_restore_all(void) {
  for (int i = 0; i < ld_nwr; i++) memcpy(ld_img + ld_wr[i].rva, ld_wr[i].pristine, ld_wr[i].len);
  memset(ld_arena, 0, ld_arena_size);
  ld_model_reset();
}

/* JSON 出力バッファ */
static char* ld_out; static size_t ld_outn, ld_outcap;
static void ld_ob_reset(void) { if (!ld_out) { ld_outcap = 256u << 20; ld_out = (char*)malloc(ld_outcap); } ld_outn = 0; ld_out[0] = 0; }
static void ld_ob(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
#include <stdarg.h>
static void ld_ob(const char* fmt, ...) {
  va_list ap; va_start(ap, fmt);
  if (ld_outcap - ld_outn < 4096) { va_end(ap); return; }
  int k = vsnprintf(ld_out + ld_outn, ld_outcap - ld_outn - 1, fmt, ap);
  va_end(ap);
  if (k > 0) ld_outn += (size_t)k;
}
static void ld_hex(const u8* p, int n) { for (int i = 0; i < n; i++) ld_ob("%02x", p[i]); }

#define LD_MAX_BLOCKS 3000
static int ld_nblk_total;
/* region 内 [cur, pri) の 8B ブロック差分を {"r":..,"o":..,"b":pre,"a":post} で出力 */
static void ld_diff_region(const char* rname, const u8* cur, const u8* pri, u64 off0, u64 len, int* first, int* trunc) {
  u64 i = 0;
  while (i < len) {
    /* 高速スキップ: 64B 単位 */
    if (i + 64 <= len && memcmp(cur + i, pri + i, 64) == 0) { i += 64; continue; }
    u64 bi = i & ~7ull;
    u64 e = bi + 8 <= len ? 8 : len - bi;
    if (memcmp(cur + bi, pri + bi, e) != 0) {
      if (ld_nblk_total >= LD_MAX_BLOCKS) { *trunc = 1; ld_nblk_total++; return; }
      ld_nblk_total++;
      ld_ob("%s{\"r\":\"%s\",\"o\":\"0x%llx\",\"b\":\"", *first ? "" : ",", rname, (unsigned long long)(off0 + bi)); *first = 0;
      u8 t[8] = {0}; memcpy(t, pri + bi, e); ld_hex(t, 8);
      ld_ob("\",\"a\":\""); memcpy(t, cur + bi, e); ld_hex(t, 8);
      ld_ob("\"}");
    }
    i = bi + 8;
  }
}

/* ---------------- プロトコル ---------------- */
typedef struct {
  char id[64];
  u64 fn;               /* VA (アドレスは image base 込みではなく「VA」。native/wasm は ld_img からの RVA で解決) */
  char blob[24];
  int nargs; char kind[16]; u64 val[16];   /* 位置引数: kind 'i'(int/ptr) 'd'(f64 bits) 'f'(f32 bits) */
  u64 rax;
  int trace, xfill, stkfill, keep, blk, audit;
  u64 left_n, left_first, left_last;   /* LD-96 (#2258): audit=1 のとき case 開始時に、高水位より外側へ残った heap の非 0 バイト数 */
  int npatch; struct { int region; u64 off; u8 data[64]; int len; } patch[16];
  char abi[16];
} ld_case_t;
static ld_case_t ld_case;

static u64 ld_parse_val(const char* s) {
  if (s[0] == 'a' && s[1] == ':') return (u64)(uintptr_t)ld_arena + strtoull(s + 2, NULL, 0);
  if (s[0] == 'h' && s[1] == ':') return (u64)(uintptr_t)ld_heap + strtoull(s + 2, NULL, 0);
  if (s[0] == 'i' && s[1] == ':') return (u64)(uintptr_t)ld_img + strtoull(s + 2, NULL, 0);
  return strtoull(s, NULL, 0);
}
static int ld_hv(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }
static int ld_unhex(const char* s, u8* out, int max) {
  int n = 0;
  while (s[0] && s[1] && n < max) {
    int a = ld_hv(s[0]), b = ld_hv(s[1]); if (a < 0 || b < 0) break;
    out[n++] = (u8)(a * 16 + b); s += 2;
  }
  return n;
}
static ld_blob_t* ld_find_blob(const char* name) {
  for (int i = 0; i < ld_nblobs; i++) if (strcmp(ld_blobs[i].name, name) == 0) return &ld_blobs[i];
  return NULL;
}
/* BLOB <name> <hex>  |  FIX <name> off,off,...  (arena 先頭相対; qword に arena base を加算) */
static void ld_cmd_blob(const char* name, const char* hex) {
  ld_blob_t* b = ld_find_blob(name);
  if (!b) { if (ld_nblobs >= LD_MAX_BLOBS) return; b = &ld_blobs[ld_nblobs++]; memset(b, 0, sizeof *b); snprintf(b->name, sizeof b->name, "%s", name); }
  free(b->data); size_t hl = strlen(hex); b->data = (u8*)malloc(hl / 2 + 8);
  b->len = (u64)ld_unhex(hex, b->data, (int)(hl / 2));
}
static void ld_cmd_fix(const char* name, const char* list) {
  ld_blob_t* b = ld_find_blob(name); if (!b) return;
  free(b->fix); b->nfix = 0;
  size_t n = 1; for (const char* p = list; *p; p++) if (*p == ',') n++;
  b->fix = (u64*)malloc(n * 8);
  char* d = strdup(list); char* sv; for (char* t = strtok_r(d, ",", &sv); t; t = strtok_r(NULL, ",", &sv)) b->fix[b->nfix++] = strtoull(t, NULL, 16);
  free(d);
}
static u8* ld_region_ptr(int r) { return r == 0 ? ld_img : r == 1 ? ld_arena : ld_heap; }
/* CASE の 1 行をパース: key=value 空白区切り. args=<k>:<v>,<k>:<v>... (v は 0x.. / a:0x.. / h:0x.. / i:0x..) */
static int ld_parse_case(char* line) {
  memset(&ld_case, 0, sizeof ld_case);
  snprintf(ld_case.abi, sizeof ld_case.abi, "ms64");
  ld_case.rax = 0xCAFEBABE0BADF00Dull;
  char* sv;
  for (char* t = strtok_r(line, " \t\r\n", &sv); t; t = strtok_r(NULL, " \t\r\n", &sv)) {
    char* eq = strchr(t, '='); if (!eq) continue; *eq = 0; char* v = eq + 1;
    if (!strcmp(t, "id")) snprintf(ld_case.id, sizeof ld_case.id, "%s", v);
    else if (!strcmp(t, "fn")) ld_case.fn = strtoull(v, NULL, 16);
    else if (!strcmp(t, "blob")) snprintf(ld_case.blob, sizeof ld_case.blob, "%s", v);
    else if (!strcmp(t, "abi")) snprintf(ld_case.abi, sizeof ld_case.abi, "%s", v);
    else if (!strcmp(t, "rax")) ld_case.rax = strtoull(v, NULL, 0);
    else if (!strcmp(t, "trace")) ld_case.trace = atoi(v);
    else if (!strcmp(t, "stkfill")) ld_case.stkfill = (int)strtol(v, NULL, 16);
    else if (!strcmp(t, "keep")) ld_case.keep = atoi(v);
    else if (!strcmp(t, "blk")) ld_case.blk = atoi(v);
    else if (!strcmp(t, "audit")) ld_case.audit = atoi(v);
    else if (!strcmp(t, "xfill")) ld_case.xfill = atoi(v);
    else if (!strcmp(t, "args")) {
      char* s2; for (char* a = strtok_r(v, ",", &s2); a && ld_case.nargs < 16; a = strtok_r(NULL, ",", &s2)) {
        ld_case.kind[ld_case.nargs] = a[0];
        ld_case.val[ld_case.nargs] = ld_parse_val(a + 2);
        ld_case.nargs++;
      }
    } else if (!strcmp(t, "p")) {   /* region:off:hex;... (region = i/a/h) */
      char* s2; for (char* a = strtok_r(v, ";", &s2); a && ld_case.npatch < 16; a = strtok_r(NULL, ";", &s2)) {
        char r = a[0]; char* c1 = strchr(a, ':'); if (!c1) continue; char* c2 = strchr(c1 + 1, ':'); if (!c2) continue; *c2 = 0;
        int k = ld_case.npatch++;
        ld_case.patch[k].region = r == 'i' ? 0 : r == 'a' ? 1 : 2;
        ld_case.patch[k].off = strtoull(c1 + 1, NULL, 0);
        if (c2[1] == 'q' && c2[2] == '=') { u64 qv = ld_parse_val(c2 + 3); memcpy(ld_case.patch[k].data, &qv, 8); ld_case.patch[k].len = 8; }
        else ld_case.patch[k].len = ld_unhex(c2 + 1, ld_case.patch[k].data, 64);
      }
    }
  }
  return 0;
}
/* image への patch は pristine を更新して差分から除外 */
static void ld_case_patch_image_pristine(void) {
  for (int i = 0; i < ld_case.npatch; i++) if (ld_case.patch[i].region == 0) {
    for (int w = 0; w < ld_nwr; w++) {
      u64 o = ld_case.patch[i].off;
      if (o >= ld_wr[w].rva && o + ld_case.patch[i].len <= ld_wr[w].rva + ld_wr[w].len)
        memcpy(ld_wr[w].pristine + (o - ld_wr[w].rva), ld_case.patch[i].data, ld_case.patch[i].len);
    }
  }
}
/* case 開始: 全領域を pristine へ復元 → blob 展開 → patch 適用 → ログ初期化 */
static void ld_case_begin(void) {
  if (ld_case.keep) {   /* 状態を引き継ぐ連続実行: 復元・blob 展開をしない */
    ld_ncalls = 0; ld_calls_over = 0; ld_ntr = 0; ld_tr_over = 0; ld_trace_on = ld_case.trace;
    ld_nblk = 0; ld_blk_over = 0; ld_blk_on = ld_case.blk;
    return;
  }
  ld_case.left_n = 0; ld_case.left_first = 0; ld_case.left_last = 0;
  if (ld_case.audit && ld_heap) {   /* LD-96: 復元の前に、前 case の書込みで高水位より外側に残った非 0 バイトを数える */
    u64 z = ld_heap_hw > LD_HEAP_RESERVED ? ld_heap_hw : LD_HEAP_RESERVED;
    u64 probe = (z + 7) & ~7ull;
    if (ld_case.audit == 2) ld_heap[probe] = 0x5a;   /* 対照: 既知の 1 B を高水位より外に置く (計数の後に消す) */
    for (u64 i = z; i < ld_heap_size; i += 8) {
      u64 n8 = ld_heap_size - i < 8 ? ld_heap_size - i : 8, wv = 0;   /* 末尾が 8 の倍数でない heap も数える */
      memcpy(&wv, ld_heap + i, n8);
      if (!wv) continue;
      for (u64 k = 0; k < n8; k++) if (ld_heap[i + k]) {
        if (!ld_case.left_n) ld_case.left_first = i + k;
        ld_case.left_last = i + k; ld_case.left_n++;
      }
    }
    if (ld_case.audit == 2) ld_heap[probe] = 0;
  }
  ld_restore_all();
  memset(ld_arena_pristine, 0, ld_arena_size);
  ld_arena_dirty_hw = 0;
  if (ld_case.blob[0] && strcmp(ld_case.blob, "-")) {
    ld_blob_t* b = ld_find_blob(ld_case.blob);
    if (b) {
      u64 n = b->len < ld_arena_size ? b->len : ld_arena_size;
      memcpy(ld_arena, b->data, n);
      for (int i = 0; i < b->nfix; i++) if (b->fix[i] + 8 <= n) { u64* q = (u64*)(ld_arena + b->fix[i]); *q += (u64)(uintptr_t)ld_arena; }
      memcpy(ld_arena_pristine, ld_arena, n);
      ld_arena_dirty_hw = n;
    }
  }
  /* patch は pristine にも反映しない (= 「呼出し前に与えた入力」であり差分に出さない) ため arena のみ pristine にも書く */
  for (int i = 0; i < ld_case.npatch; i++) {
    u8* base = ld_region_ptr(ld_case.patch[i].region);
    memcpy(base + ld_case.patch[i].off, ld_case.patch[i].data, ld_case.patch[i].len);
    if (ld_case.patch[i].region == 1) memcpy(ld_arena_pristine + ld_case.patch[i].off, ld_case.patch[i].data, ld_case.patch[i].len);
  }
  ld_ncalls = 0; ld_calls_over = 0; ld_ntr = 0; ld_tr_over = 0;
  ld_trace_on = ld_case.trace;
  ld_nblk = 0; ld_blk_over = 0; ld_blk_on = ld_case.blk;
  ld_case_patch_image_pristine();
}
/* native ランナが呼出し所要 ms を入れる (wasm ランナは -1 のまま = 出力しない)。liftdiff の「native が長い case」判定用 (LD-11 / #548) */
static double ld_native_ms = -1.0;
/* case 終了: 結果 JSON を ld_out に作る. status: "ok" 等. 戻り値 = JSON 文字列 */
static const char* ld_case_end(const char* status, const char* detail, u64 fault_addr, u64 fault_rip, u64 rax, u64 rdx, u64 x0, u64 x1, int has_ret) {
  ld_ob_reset();
  ld_ob("{\"id\":\"%s\",\"fn\":\"0x%llx\",\"status\":\"%s\"", ld_case.id, (unsigned long long)ld_case.fn, status);
  if (detail && detail[0]) {
    ld_ob(",\"detail\":\"");
    for (const char* p = detail; *p && ld_outcap - ld_outn > 8192; p++) { if (*p == '"' || *p == '\\') ld_ob("\\%c", *p); else if ((unsigned char)*p < 0x20) ld_ob(" "); else ld_ob("%c", *p); }
    ld_ob("\"");
  }
  if (fault_addr || fault_rip) ld_ob(",\"fault\":{\"addr\":\"0x%llx\",\"rip\":\"0x%llx\"}", (unsigned long long)fault_addr, (unsigned long long)fault_rip);
  if (ld_native_ms >= 0) ld_ob(",\"ms\":%.3f", ld_native_ms);
  if (has_ret) ld_ob(",\"rax\":\"0x%llx\",\"rdx\":\"0x%llx\",\"x0\":\"0x%llx\",\"x1\":\"0x%llx\"", (unsigned long long)rax, (unsigned long long)rdx, (unsigned long long)x0, (unsigned long long)x1);
  /* 呼出ログ */
  ld_ob(",\"calls\":[");
  for (int i = 0; i < ld_ncalls; i++) {
    ld_call_t* c = &ld_calls[i];
    ld_ob("%s{\"n\":\"%s\",\"a\":[\"0x%llx\",\"0x%llx\",\"0x%llx\",\"0x%llx\",\"0x%llx\",\"0x%llx\"],\"r\":\"0x%llx\"}", i ? "," : "", c->name,
          (unsigned long long)c->a[0], (unsigned long long)c->a[1], (unsigned long long)c->a[2], (unsigned long long)c->a[3],
          (unsigned long long)c->a[4], (unsigned long long)c->a[5], (unsigned long long)c->ret);
  }
  ld_ob("],\"calls_over\":%d", ld_calls_over);
  if (ld_case.trace) {
    ld_ob(",\"trace\":[");
    for (int i = 0; i < ld_ntr; i++) {
      ld_tr_t* t = &ld_trs[i];
      ld_ob("%s[\"0x%llx\",%u", i ? "," : "", (unsigned long long)t->va, t->np);
      for (int k = 0; k < 8; k++) ld_ob(",\"0x%llx\"", (unsigned long long)t->a[k]);
      for (int k = 0; k < 4; k++) ld_ob(",\"0x%llx\"", (unsigned long long)t->x[k]);
      ld_ob("]");
    }
    ld_ob("],\"trace_over\":%d", ld_tr_over);
  }
  if (ld_case.blk) {
    ld_ob(",\"blk\":[");
    for (int i = 0; i < ld_nblk; i++) ld_ob("%s\"0x%llx\"", i ? "," : "", (unsigned long long)ld_blks[i]);
    ld_ob("],\"blk_over\":%d", ld_blk_over);
  }
  /* メモリ差分 */
  ld_ob(",\"mem\":[");
  int first = 1, trunc = 0; ld_nblk_total = 0;
  for (int i = 0; i < ld_nwr; i++) ld_diff_region("image", ld_img + ld_wr[i].rva, ld_wr[i].pristine, ld_wr[i].rva, ld_wr[i].len, &first, &trunc);
  ld_diff_region("arena", ld_arena, ld_arena_pristine, 0, ld_arena_size, &first, &trunc);
  { u8* ref = (u8*)calloc(1, ld_heap_hw + 8);
    memcpy(ref, ld_heap_pristine, ld_heap_pristine_len < ld_heap_hw ? ld_heap_pristine_len : ld_heap_hw);
    ld_diff_region("heap", ld_heap + LD_HEAP_RESERVED, ref + LD_HEAP_RESERVED, LD_HEAP_RESERVED, ld_heap_hw - LD_HEAP_RESERVED, &first, &trunc);
    free(ref); }
  ld_ob("],\"mem_blocks\":%d,\"mem_trunc\":%d,\"heap_used\":%llu", ld_nblk_total, trunc, (unsigned long long)ld_heap_used);
  if (ld_case.audit) ld_ob(",\"heap_left\":{\"n\":%llu,\"first\":\"0x%llx\",\"last\":\"0x%llx\"}", (unsigned long long)ld_case.left_n, (unsigned long long)ld_case.left_first, (unsigned long long)ld_case.left_last);
  ld_ob("}");
  return ld_out;
}

/* ---------------- 状態の保存/移送 (boot 済みメモリ状態を native → wasm に載せ替える) ---------------- */
/* STATE: 現在の image(書込可能範囲)差分 + heap 内容を JSON 1 行で返す. */
static const char* ld_state_dump(void) {
  ld_ob_reset();
  ld_ob("{\"img\":[");
  int first = 1;
  for (int w = 0; w < ld_nwr; w++) {
    const u8* cur = ld_img + ld_wr[w].rva; const u8* pri = ld_wr[w].pristine; u64 len = ld_wr[w].len;
    u64 i = 0;
    while (i < len) {
      if (i + 64 <= len && memcmp(cur + i, pri + i, 64) == 0) { i += 64; continue; }
      if (cur[i] == pri[i]) { i++; continue; }
      u64 j = i, last = i;
      while (j < len && j - last < 32) { if (cur[j] != pri[j]) last = j; j++; }
      u64 st = i & ~7ull, en = (last | 7ull); if (en >= len) en = len - 1;
      if (ld_outcap - ld_outn < (en - st + 1) * 2 + 4096) break;
      ld_ob("%s[\"0x%llx\",\"", first ? "" : ",", (unsigned long long)(ld_wr[w].rva + st)); first = 0;
      ld_hex(cur + st, (int)(en - st + 1)); ld_ob("\"]");
      i = en + 1;
    }
  }
  ld_ob("],\"heap\":\"");
  u64 hn = ld_heap_hw > LD_HEAP_RESERVED ? ld_heap_hw : LD_HEAP_RESERVED;
  if (ld_outcap - ld_outn > hn * 2 + 4096) ld_hex(ld_heap, (int)hn);
  ld_ob("\",\"heap_used\":%llu,\"hw\":%llu}", (unsigned long long)ld_heap_used, (unsigned long long)ld_heap_hw);
  return ld_out;
}
/* SIMG <rva-hex> <hex> : image に書込 / SHEAP <hex> : heap 全体を置換 / SMODEL <used> <hw> / SSNAP : 現在状態を pristine に昇格 */
static void ld_state_cmd(const char* cmd, const char* a, const char* b) {
  if (!strcmp(cmd, "SIMG")) { u64 rva = strtoull(a, NULL, 16); size_t n = strlen(b) / 2; ld_unhex(b, ld_img + rva, (int)n); }
  else if (!strcmp(cmd, "SHEAP")) { size_t n = strlen(a) / 2; if (n <= ld_heap_size) ld_unhex(a, ld_heap, (int)n); }
  else if (!strcmp(cmd, "SMODEL")) { ld_heap_used = strtoull(a, NULL, 10); ld_heap_hw = strtoull(b, NULL, 10); }
  else if (!strcmp(cmd, "SSNAP")) { ld_snapshot(); }
}
#endif
