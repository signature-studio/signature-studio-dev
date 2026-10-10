/* M11 runtime: VirtualAlloc/VirtualFree/VirtualProtect shim + m11 boot anchor + 状態照会.
 * 対応: FLEngine_x64.dll 部分起動 PoC (オーディオ/GUIなし)
 * - VirtualAlloc: Emscripten malloc 上に 64KB (4KB page) アラインの連続領域を渡し,
 *   FastMM (lift された function_407a50/407e20) が wasm linear memory 上で動くようにする.
 * - VirtualFree: malloc に返す (管理テーブル小規模; PoC では leak 計測も価値ありで残す)
 * - VirtualProtect: no-op (PAGE_保護は wasm には無い) で 0 を返すのみ.
 * - fail-fast (tools/m11/側に置く; tools/shim/src/failfast.c は読取のみ使う)
 *
 * (shim 実装統合の規約: tools/shim/src/heap.c の HeapAlloc/HeapFree 等を静的リンクで併用)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten.h>

#define PAGE daunting_nop = 0  /* (未使用のプレース保留は書かない) */

extern void* HeapAlloc(void* heap, unsigned flags, unsigned long long bytes);
extern int   HeapFree(void* heap, unsigned flags, void* p);
extern void* malloc(size_t n);
extern void  free(void* p);

/* ---- Virtual memory shim ----
 * VirtualAlloc: 要求ごとに calloc(size + 64KB) で確保し 64KB 境界へ揃える (wasm には ページ予約/保護が無い).
 *   addr 指定 (commit 追加) は既に確保済領域内とみなし addr をそのまま返す.
 *   VirtualFree/Protect は no-op (PoC; 計測のため leak を許容).
 * 旧版の「64MB arena + 超過時は arena 末尾を返す」は大きな要求 (339MB) で arena 外を返し OOB を起こしていた (修正済).
 */
int m11_trace_flag = 0;   /* m11_ov.c の m11_set_trace が設定 */
static unsigned long long g_va_used = 0;
static unsigned long long g_va_calls = 0;
static unsigned long long g_va_freed_cnt = 0;

EMSCRIPTEN_KEEPALIVE
void *VirtualAlloc(void* addr, unsigned size, unsigned type, unsigned protect) {
    if (g_va_calls < 8) fprintf(stderr, "[m11][VA] #%llu addr=%p size=%u (0x%x) type=0x%x prot=0x%x\n", g_va_calls, addr, size, size, type, protect);
    if (m11_trace_flag && g_va_calls < 3) EM_ASM({ console.error('[m11][VA-stack]\n' + new Error().stack.split('\n').slice(2, 12).join('\n')); });
    g_va_calls++;
    if (addr) return addr;
    unsigned long long need = ((unsigned long long)size + 0xffffULL) & ~0xffffULL;
    unsigned char* raw = (unsigned char*)calloc(1, (size_t)(need + 0x10000ULL));
    if (!raw) {
        fprintf(stderr, "[m11][VA] OOM want=%.1fMB used=%.1fMB (NULL を返す)\n", need / 1e6, g_va_used / 1e6);
        return 0;
    }
    unsigned long long p = (unsigned long long)raw;
    unsigned long long off = (0x10000ULL - (p & 0xffffULL)) & 0xffffULL;
    g_va_used += need;
    return raw + off;
}

int VirtualFree(void* p, unsigned size, unsigned type) {
    (void)p; (void)size; (void)type;
    g_va_freed_cnt++;
    return 1; /* FastMM arena 解放は省略 (boot 終了後まとめて drop) */
}

int VirtualProtect(void* p, unsigned size, unsigned prot_new, unsigned* prot_old) {
    (void)p; (void)size; (void)prot_new;
    if (prot_old) *prot_old = 0;
    return 1;
}

unsigned VirtualQuery(void* p, void* buf, unsigned len) {
    (void)buf; (void)len;
    (void)p;
    return len; /* 0 以外を返す (QUERY 失敗扱いを避ける) */
}

/* ---- m11 boot counter / 状態 ---- */
static int32_t g_m11_init_cnt = 0;
static int32_t g_m11_boot_stage = 0;
static int32_t g_m11_last_stage_line = 0;

/* [M5] init prologue counter の生ポインタ (IR pass 側で ptr 指定で使われる) */
EMSCRIPTEN_KEEPALIVE int32_t* m11_counter_ptr(void) {
    return (int32_t*)&g_m11_init_cnt;
}

EMSCRIPTEN_KEEPALIVE
int32_t m11_init_count(void) { return g_m11_init_cnt; }

EMSCRIPTEN_KEEPALIVE
int32_t m11_boot_stage(void) { return g_m11_boot_stage; }

EMSCRIPTEN_KEEPALIVE
void m11_mark_stage(int32_t v) { g_m11_boot_stage = v; }

/* boot anchor: lifted entry_point に接続 */
extern int64_t entry_point(int64_t a1, int64_t a2, int64_t a3);
extern void m11_data_install(void);   /* 自動生成 (m11_data_gen.py): PE 画像 .data/.rdata 敷設 */

EMSCRIPTEN_KEEPALIVE
int64_t m11_boot_enter(int64_t hinst, int64_t reason) {
    static int data_installed = 0;
    if (!data_installed) {
        m11_data_install();
        data_installed = 1;
        fprintf(stderr, "[m11] PE image .data/.rdata installed (LVA base 0)\n");
    }
    g_m11_boot_stage = 1;
    fflush(stdout);
    fprintf(stderr, "[m11][args] entry_point(0x%llx, 0x%llx, 0x%llx)\n",
            (unsigned long long)hinst, (unsigned long long)reason,
            (unsigned long long)(hinst ^ reason)); /* 第3引数は m11 側未定義 */
    int64_t rc = entry_point(hinst, reason, 0);
    g_m11_boot_stage = 2;
    return rc;
}

/* 未定義 function_* 参照の fail-fast stdout (auto-gen stubs ファイルで呼ばれる) */
void m11_unresolved_function(const char* name) {
    fprintf(stderr, "[m11][fail-fast] unresolved function call: %s\n", name);
    fflush(stderr);
    abort();  /* exit code 101 相当 (wasm EXITRUNTIME が abort を伝える; exit_runtime=1) */
}

/* state 値: VirtualAlloc arena 実測値 */
EMSCRIPTEN_KEEPALIVE
int64_t m11_va_used(void) { return (int64_t)g_va_used; }
EMSCRIPTEN_KEEPALIVE
int64_t m11_va_calls(void) { return (int64_t)g_va_calls; }

/* __asm_fnclex0 等の SIMD/FPU helper は m11_simd2.py が IR 署名から生成 (work/m11_simd.c) */

/* ---- 未実装 Win32/CRT API stub の呼出し記録 (genstubs の winstubs から呼ばれる; 0 を返して継続) ---- */
#define STUB_MAX 512
static const char* g_stub_names[STUB_MAX];
static unsigned g_stub_cnt[STUB_MAX];
static int g_stub_n = 0;
static unsigned long long g_stub_total = 0;

void m11_stub_hit(const char* n) {
    g_stub_total++;
    for (int i = 0; i < g_stub_n; i++)
        if (g_stub_names[i] == n || strcmp(g_stub_names[i], n) == 0) { g_stub_cnt[i]++; return; }
    if (g_stub_n < STUB_MAX) { g_stub_names[g_stub_n] = n; g_stub_cnt[g_stub_n] = 1; g_stub_n++; }
    fprintf(stderr, "[m11][stub-notimpl] %s called (0 を返して継続)\n", n);
}
EMSCRIPTEN_KEEPALIVE int m11_stub_total(void) { return (int)g_stub_total; }
EMSCRIPTEN_KEEPALIVE int m11_stub_uniq(void) { return g_stub_n; }
EMSCRIPTEN_KEEPALIVE const char* m11_stub_name(int i) { return (i >= 0 && i < g_stub_n) ? g_stub_names[i] : ""; }
EMSCRIPTEN_KEEPALIVE int m11_stub_count(int i) { return (i >= 0 && i < g_stub_n) ? (int)g_stub_cnt[i] : 0; }

/* ---- 関数入口 probe (m11_post.py が FastMM4 入口等に被せる) ---- */
#define PROBE_MAX 32
static unsigned long long g_probe[PROBE_MAX];
void m11_probe(int i) { if (i >= 0 && i < PROBE_MAX) g_probe[i]++; }
EMSCRIPTEN_KEEPALIVE double m11_probe_count(int i) { return (i >= 0 && i < PROBE_MAX) ? (double)g_probe[i] : -1.0; }
