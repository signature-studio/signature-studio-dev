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
typedef struct { const char* name; u64 a[4]; u64 ret; } ld_call_t;
#define LD_MAX_CALLS 2048
static ld_call_t ld_calls[LD_MAX_CALLS];
static int ld_ncalls, ld_calls_over;

typedef struct { u64 va; u32 np; u64 a[8]; u64 x[4]; } ld_tr_t;
#define LD_MAX_TR 16384
static ld_tr_t ld_trs[LD_MAX_TR];
static int ld_ntr, ld_tr_over;
static int ld_trace_on;

/* ---------------- 応答モデル ---------------- */
static u64 ld_tick, ld_qpc, ld_lasterr, ld_tls_next;
static u64 ld_tls_vals[1088];

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

/* name = import 名 (kernel32 等の区別はしない), a[] = 位置引数 (ms64 先頭 4 つ) */
static u64 ld_model_call(const char* n, u64 a0, u64 a1, u64 a2, u64 a3) {
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
  if (ld_streq(n, "TlsGetValue")) return ld_tls_vals[a0 & 1023];
  if (ld_streq(n, "TlsSetValue")) { ld_tls_vals[a0 & 1023] = a1; return 1; }
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
static u64 ld_stub(const char* n, u64 a0, u64 a1, u64 a2, u64 a3) {
  u64 r = ld_model_call(n, a0, a1, a2, a3);
  if (ld_ncalls < LD_MAX_CALLS) {
    ld_call_t* c = &ld_calls[ld_ncalls++];
    c->name = n; c->a[0] = a0; c->a[1] = a1; c->a[2] = a2; c->a[3] = a3; c->ret = r;
  } else ld_calls_over++;
  return r;
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
static void ld_snapshot(void) {
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
static void ld_ob_reset(void) { if (!ld_out) { ld_outcap = 16u << 20; ld_out = (char*)malloc(ld_outcap); } ld_outn = 0; ld_out[0] = 0; }
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
  int trace, xfill, stkfill, keep;
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
    return;
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
  ld_case_patch_image_pristine();
}
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
  if (has_ret) ld_ob(",\"rax\":\"0x%llx\",\"rdx\":\"0x%llx\",\"x0\":\"0x%llx\",\"x1\":\"0x%llx\"", (unsigned long long)rax, (unsigned long long)rdx, (unsigned long long)x0, (unsigned long long)x1);
  /* 呼出ログ */
  ld_ob(",\"calls\":[");
  for (int i = 0; i < ld_ncalls; i++) {
    ld_call_t* c = &ld_calls[i];
    ld_ob("%s{\"n\":\"%s\",\"a\":[\"0x%llx\",\"0x%llx\",\"0x%llx\",\"0x%llx\"],\"r\":\"0x%llx\"}", i ? "," : "", c->name,
          (unsigned long long)c->a[0], (unsigned long long)c->a[1], (unsigned long long)c->a[2], (unsigned long long)c->a[3], (unsigned long long)c->ret);
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
  /* メモリ差分 */
  ld_ob(",\"mem\":[");
  int first = 1, trunc = 0; ld_nblk_total = 0;
  for (int i = 0; i < ld_nwr; i++) ld_diff_region("image", ld_img + ld_wr[i].rva, ld_wr[i].pristine, ld_wr[i].rva, ld_wr[i].len, &first, &trunc);
  ld_diff_region("arena", ld_arena, ld_arena_pristine, 0, ld_arena_size, &first, &trunc);
  { u8* ref = (u8*)calloc(1, ld_heap_hw + 8);
    memcpy(ref, ld_heap_pristine, ld_heap_pristine_len < ld_heap_hw ? ld_heap_pristine_len : ld_heap_hw);
    ld_diff_region("heap", ld_heap + LD_HEAP_RESERVED, ref + LD_HEAP_RESERVED, LD_HEAP_RESERVED, ld_heap_hw - LD_HEAP_RESERVED, &first, &trunc);
    free(ref); }
  ld_ob("],\"mem_blocks\":%d,\"mem_trunc\":%d,\"heap_used\":%llu}", ld_nblk_total, trunc, (unsigned long long)ld_heap_used);
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
