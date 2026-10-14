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
#ifndef M11_LB_BASE
#define M11_LB_BASE 0   /* #222: LVA = RVA + M11_LB_BASE (m11_build.sh が -D で渡す) */
#endif
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten.h>
#include <emscripten/stack.h>

#define PAGE daunting_nop = 0  /* (未使用のプレース保留は書かない) */

extern void* HeapAlloc(void* heap, unsigned flags, unsigned long long bytes);
extern int   HeapFree(void* heap, unsigned flags, void* p);
extern void* malloc(size_t n);
extern void  free(void* p);

/* ---- Virtual memory shim ----
 * VirtualAlloc: 要求ごとに calloc(size + 64KB) で確保し 64KB 境界へ揃える (wasm には ページ予約/保護が無い).
 *   addr 指定 (commit 追加) は既に確保済領域内とみなし addr をそのまま返す.
 *   確保ごとに (返した基底, calloc の生ポインタ, 長さ) を表に記録する (#513).
 * VirtualFree: MEM_RELEASE (0x8000) で基底ポインタが表にあれば free して表から消す (実解放).
 *   MEM_DECOMMIT (0x4000) は no-op (回数だけ数える). 表に無い解放要求は 1 を返し g_va_free_unknown に数える.
 *   M11 の survey は 942 unit を 1 プロセスで通算実行する. 旧版 (VirtualFree no-op) は累計が wasm 上限に達すると
 *   OOM → NULL → GetMem 失敗 → Halt0 となり, 意味の trap と区別できなかった (#513).
 *   m11_set_vfree_noop(1) で旧挙動 (解放しない) に戻せる = ネガティブコントロール.
 * 旧版の「64MB arena + 超過時は arena 末尾を返す」は大きな要求 (339MB) で arena 外を返し OOB を起こしていた (修正済).
 */
int m11_trace_flag = 0;   /* m11_ov.c の m11_set_trace が設定 */
#define M11_VA_BIG (64ULL << 20)   /* この大きさ以上の要求は stderr に記録し, m11_set_va_bigtrace(1) なら呼出元スタックも出す */
static int g_va_bigtrace = 0;
static unsigned long long g_va_unit_budget = 0;  /* >0: unit 1 本が VirtualAlloc で確保できる累計バイト上限 (survey 用; 超過は NULL = OOM 扱い) */
static unsigned long long g_va_unit_base = 0;    /* m11_va_unit_begin 時点の g_va_used */
static unsigned long long g_va_denied = 0;       /* 上限超過で NULL を返した回数 (g_va_oom にも含む) */
static unsigned long long g_va_stack_at = 0;   /* >=1: 0 起算でその番号の VirtualAlloc 呼出しで呼出元スタックを出す (0 = 無効なので最初の呼出し #0 は指定不可) */
typedef struct { unsigned char* base; unsigned char* raw; unsigned long long need; } va_ent;
static va_ent* g_va_tab = 0;
static unsigned g_va_tab_n = 0, g_va_tab_cap = 0;
static int g_vfree_noop = 0;
static unsigned long long g_va_used = 0;       /* 累計確保バイト (従来値と同義) */
static unsigned long long g_va_live = 0;       /* 現在確保中バイト */
static unsigned long long g_va_peak = 0;       /* g_va_live の最大 */
extern const int m11_trace_isolate;   /* trace が shadow stack を汚さないよう SP 直下を退避/復元する (m11_ov.c M11_TRACE, #495) */
extern void m11_stk_save(unsigned sp);
extern void m11_stk_restore(unsigned sp);
static unsigned long long g_va_calls = 0;
static unsigned long long g_va_oom = 0;        /* calloc 失敗 (NULL を返した) 回数 */
static unsigned long long g_va_freed_cnt = 0;  /* MEM_RELEASE で実解放した回数 */
static unsigned long long g_va_freed_bytes = 0;
static unsigned long long g_va_free_unknown = 0;
static unsigned long long g_va_free_skipped = 0;  /* NC (m11_set_vfree_noop) で解放を見送った回数 */
static unsigned long long g_va_decommit = 0;
static unsigned long long g_va_big_cnt = 0;

EM_JS(void, m11_va_big_stack, (unsigned size), {
    var l = Error.stackTraceLimit; Error.stackTraceLimit = 48;
    var st = new Error().stack; Error.stackTraceLimit = l;
    console.error('[m11][VA-big] size=' + size + ' (' + (size / 1048576).toFixed(1) + ' MB)\n' + st.split('\n').slice(2, 48).join('\n'));
});

EMSCRIPTEN_KEEPALIVE
void *VirtualAlloc(void* addr, unsigned size, unsigned type, unsigned protect) {
    if (g_va_calls < 8) fprintf(stderr, "[m11][VA] #%llu addr=%p size=%u (0x%x) type=0x%x prot=0x%x\n", g_va_calls, addr, size, size, type, protect);
    if (m11_trace_flag && g_va_calls < 3) {
        unsigned sp_ = (unsigned)emscripten_stack_get_current();
        if (m11_trace_isolate) m11_stk_save(sp_);
        EM_ASM({ console.error('[m11][VA-stack]\n' + new Error().stack.split('\n').slice(2, 12).join('\n')); });
        if (m11_trace_isolate) m11_stk_restore(sp_);
    }
    if (g_va_stack_at && g_va_calls == g_va_stack_at) m11_va_big_stack(size);
    g_va_calls++;
    if (addr) return addr;
    if (size >= M11_VA_BIG) {
        g_va_big_cnt++;
        fprintf(stderr, "[m11][VA-big] #%llu size=%u (%.1f MB) live=%.1fMB\n", g_va_calls - 1, size, size / 1048576.0, g_va_live / 1e6);
        if (g_va_bigtrace && g_va_big_cnt <= 8) m11_va_big_stack(size);
    }
    unsigned long long need = ((unsigned long long)size + 0xffffULL) & ~0xffffULL;
    if (g_va_unit_budget && g_va_used - g_va_unit_base + need > g_va_unit_budget) {
        g_va_oom++; g_va_denied++;
        if (g_va_denied <= 8) fprintf(stderr, "[m11][VA] unit budget 超過 want=%.1fMB unit_used=%.1fMB budget=%.1fMB (NULL を返す)\n", need / 1e6, (g_va_used - g_va_unit_base) / 1e6, g_va_unit_budget / 1e6);
        return 0;
    }
    unsigned char* raw = (unsigned char*)calloc(1, (size_t)(need + 0x10000ULL));
    if (!raw) {
        g_va_oom++;
        fprintf(stderr, "[m11][VA] OOM want=%.1fMB used=%.1fMB live=%.1fMB (NULL を返す)\n", need / 1e6, g_va_used / 1e6, g_va_live / 1e6);
        return 0;
    }
    unsigned long long p = (unsigned long long)raw;
    unsigned long long off = (0x10000ULL - (p & 0xffffULL)) & 0xffffULL;
    if (g_va_tab_n == g_va_tab_cap) {
        unsigned nc = g_va_tab_cap ? g_va_tab_cap * 2 : 256;
        va_ent* nt = (va_ent*)realloc(g_va_tab, nc * sizeof(va_ent));
        if (!nt) { free(raw); g_va_oom++; fprintf(stderr, "[m11][VA] OOM (管理表)\n"); return 0; }
        g_va_tab = nt; g_va_tab_cap = nc;
    }
    g_va_tab[g_va_tab_n].base = raw + off; g_va_tab[g_va_tab_n].raw = raw; g_va_tab[g_va_tab_n].need = need; g_va_tab_n++;
    g_va_used += need;
    g_va_live += need;
    if (g_va_live > g_va_peak) g_va_peak = g_va_live;
    return raw + off;
}

EMSCRIPTEN_KEEPALIVE
int VirtualFree(void* p, unsigned size, unsigned type) {
    (void)size;
    if (type & 0x4000) { g_va_decommit++; return 1; }          /* MEM_DECOMMIT: 領域は保持 */
    if (!(type & 0x8000)) return 1;                              /* MEM_RELEASE 以外は従来どおり成功扱い */
    for (unsigned i = g_va_tab_n; i-- > 0; ) {                   /* 直近の確保から探す */
        if (g_va_tab[i].base == (unsigned char*)p) {
            if (g_vfree_noop) { g_va_free_skipped++; return 1; }  /* NC: 旧挙動 (解放しない, 表にも残す) */
            g_va_live -= g_va_tab[i].need;
            g_va_freed_bytes += g_va_tab[i].need;
            g_va_freed_cnt++;
            free(g_va_tab[i].raw);
            g_va_tab[i] = g_va_tab[--g_va_tab_n];
            return 1;
        }
    }
    g_va_free_unknown++;
    return 1;
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
        fprintf(stderr, "[m11] PE image .data/.rdata installed (LVA = RVA + 0x%x)\n", (unsigned)M11_LB_BASE);
    }
    hinst += (int64_t)M11_LB_BASE;   /* hinst = LVA 上の image 先頭 (ホストは従来どおり 0 を渡す; LVA=RVA では 0) */
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

/* state 値: VirtualAlloc 実測値 (m11_va_used = 累計確保バイト; live/peak/oom/freed は #513) */
EMSCRIPTEN_KEEPALIVE
int64_t m11_va_used(void) { return (int64_t)g_va_used; }
EMSCRIPTEN_KEEPALIVE
int64_t m11_va_calls(void) { return (int64_t)g_va_calls; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_live(void) { return (int64_t)g_va_live; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_peak(void) { return (int64_t)g_va_peak; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_oom(void) { return (int64_t)g_va_oom; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_freed(void) { return (int64_t)g_va_freed_cnt; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_freed_bytes(void) { return (int64_t)g_va_freed_bytes; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_free_unknown(void) { return (int64_t)g_va_free_unknown; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_free_skipped(void) { return (int64_t)g_va_free_skipped; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_decommit(void) { return (int64_t)g_va_decommit; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_big(void) { return (int64_t)g_va_big_cnt; }
EMSCRIPTEN_KEEPALIVE void m11_set_vfree_noop(int v) { g_vfree_noop = v; }
EMSCRIPTEN_KEEPALIVE void m11_set_va_bigtrace(int v) { g_va_bigtrace = v; }
EMSCRIPTEN_KEEPALIVE void m11_set_va_unit_budget(int mb) { g_va_unit_budget = (unsigned long long)(mb > 0 ? mb : 0) << 20; }
EMSCRIPTEN_KEEPALIVE void m11_va_unit_begin(void) { g_va_unit_base = g_va_used; }
EMSCRIPTEN_KEEPALIVE int64_t m11_va_denied(void) { return (int64_t)g_va_denied; }
EMSCRIPTEN_KEEPALIVE void m11_set_va_stack_at(int v) { g_va_stack_at = (unsigned long long)v; }

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
/* #944 (計測専用; M11_INSTR_413060=1 のときだけ有効): function_413060 呼出し後の dest の値を畳んだ指紋 (OFF/ON/ネガコンの比較用)。
 * M11_NEG_413060=1 のときだけ dest に +0x40 を書く既知変更 (b) を入れる。既定 build には含めない */
#ifndef M11_INSTR_413060
#define M11_INSTR_413060 0
#endif
#if M11_INSTR_413060
/* #1952 対照用 (既定 0 = 無効): PADPRE は g_dest_h より前の静的領域 (配置と量が変わる)・PADPOST は後ろ (量だけ変わる)。
 * EMPTY=1 は m11_dest_obs の本体だけ空にする (関数と静的データは残す)。 */
#ifndef M11_RT_PADPRE
#define M11_RT_PADPRE 0
#endif
#ifndef M11_RT_PADPOST
#define M11_RT_PADPOST 0
#endif
#ifndef M11_RT_EMPTY
#define M11_RT_EMPTY 0
#endif
#ifndef M11_RT_NODATA
#define M11_RT_NODATA 0
#endif
#if M11_RT_NODATA
void m11_dest_obs(unsigned long long dest) { (void)*(volatile unsigned long long*)(uintptr_t)dest; }
EMSCRIPTEN_KEEPALIVE double m11_dest_rec(int k, int field) { (void)k; (void)field; return -1.0; }
EMSCRIPTEN_KEEPALIVE double m11_dest_obs_n(void) { return 0.0; }
EMSCRIPTEN_KEEPALIVE double m11_dest_obs_hhi(void) { return 0.0; }
EMSCRIPTEN_KEEPALIVE double m11_dest_obs_hlo(void) { return 0.0; }
#else
#if M11_RT_PADPRE
static unsigned char g_pad_pre[M11_RT_PADPRE] __attribute__((used));
#endif
static unsigned long long g_dest_h = 1469598103934665603ULL, g_dest_n;
#define M11_DEST_REC_MAX 512
static unsigned long long g_rec_st[M11_DEST_REC_MAX], g_rec_len[M11_DEST_REC_MAX], g_rec_rc[M11_DEST_REC_MAX], g_rec_h[M11_DEST_REC_MAX];
#if M11_RT_PADPOST
static unsigned char g_pad_post[M11_RT_PADPOST] __attribute__((used));
#endif
#ifndef M11_NEG_413060
#define M11_NEG_413060 0
#endif
#ifndef M11_DEST_READ
#define M11_DEST_READ 1
#endif
#ifndef M11_DEST_GUARD
#define M11_DEST_GUARD 0
#endif
void m11_dest_obs(unsigned long long dest) {
#if M11_RT_EMPTY
    (void)dest; return;
#endif
#if M11_NEG_413060
    *(volatile unsigned long long*)(uintptr_t)dest += 0x40;
#endif
#if !M11_DEST_READ
    return;
#endif
    unsigned long long k = g_dest_n;
#if M11_DEST_GUARD
    /* #1547 (M11_DEST_GUARD=1 のときだけ): dest 自体が線形メモリ外なら読まない (st=3)。読出し値は変えない */
    unsigned long long heap0 = (unsigned long long)__builtin_wasm_memory_size(0) * 65536ULL;
    if (dest < 8 || dest + 8 > heap0) {
        g_dest_h = (g_dest_h ^ 0xdeadULL) * 1099511628211ULL; g_dest_n++;
        if (k < M11_DEST_REC_MAX) { g_rec_st[k] = 3; g_rec_len[k] = 0; g_rec_rc[k] = 0; g_rec_h[k] = 0; }
        return;
    }
#endif
    unsigned long long v = *(volatile unsigned long long*)(uintptr_t)dest;
    g_dest_h = (g_dest_h ^ v) * 1099511628211ULL; g_dest_n++;
    if (k < M11_DEST_REC_MAX) {
        /* #1389: 呼出し k の dest の値 (文字列の内容) を記録する。ポインタ値はヒープ配置で変わるため指紋に使わない。
         * 読むのは線形メモリの範囲内だけ (範囲外・長さ異常は st=2)。refcount は dest の文字列ヘッダ (p-8)。 */
        unsigned long long heap = (unsigned long long)__builtin_wasm_memory_size(0) * 65536ULL;
        unsigned long long h = 1469598103934665603ULL, len = 0, rc = 0, st = 0;
        if (v == 0) st = 0;
        else if (v < 8 || v + 4 > heap) st = 2;
        else {
            len = *(volatile unsigned int*)(uintptr_t)(v - 4);
            rc = *(volatile unsigned int*)(uintptr_t)(v - 8);
            if (len > (1ull << 24) || v + len * 2 > heap) st = 2;
            else {
                for (unsigned long long j = 0; j < len * 2; j++)
                    h = (h ^ *(volatile unsigned char*)(uintptr_t)(v + j)) * 1099511628211ULL;
                st = 1;
            }
        }
        g_rec_st[k] = st; g_rec_len[k] = len; g_rec_rc[k] = rc; g_rec_h[k] = h;
    }
}
EMSCRIPTEN_KEEPALIVE double m11_dest_rec(int k, int field) {
    if (k < 0 || k >= (int)M11_DEST_REC_MAX) return -1.0;
    switch (field) {
    case 0: return (double)g_rec_st[k];
    case 1: return (double)g_rec_len[k];
    case 2: return (double)g_rec_rc[k];
    case 3: return (double)(unsigned)(g_rec_h[k] >> 32);
    default: return (double)(unsigned)(g_rec_h[k] & 0xffffffffu);
    }
}
EMSCRIPTEN_KEEPALIVE double m11_dest_obs_n(void) { return (double)g_dest_n; }
EMSCRIPTEN_KEEPALIVE double m11_dest_obs_hhi(void) { return (double)(unsigned)(g_dest_h >> 32); }
EMSCRIPTEN_KEEPALIVE double m11_dest_obs_hlo(void) { return (double)(unsigned)(g_dest_h & 0xffffffffu); }
#endif
#endif
