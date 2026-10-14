/* fle_boot.c — FLE-2: x64c lift (tools/flelift) による FLEngine boot 連鎖ドライバ。
 *
 * 連鎖: fle_data_install (image 敷設) → fle_textwin_install (.text 内データ窓:
 *        InitTable 0x13768b0 / units 配列 942*16B / unit proc 先頭 8B) → fle_init (TEB)
 *        → fle_run(0x1376820 = DllMain, hinst=0, reason=DLL_PROCESS_ATTACH)
 *        → lifted entry_point が setjmp → _StartLib(0x41d8f0) → _InitLib(0x412160, 8引数)
 *        → InitUnits(0x4120c0, override で計数) → unit init 連鎖。
 *        Halt0 は lifted 0x4126f0 (longjmp, override で計数) 経由で entry_point 断片
 *        0x1376840 (entries に追加済み) へ復帰し DllMain が返る = RetDec route の
 *        JS 例外ハック (m11_ov.c function_412770) が x64c では不要なことの実証になる。
 *
 * Win32 import は fle_imp_bridge.c (gen_boot.py 生成) が imp_<Name> を strong 定義し
 * shimx へ橋絡みする。fle_cpu.c 側の同名 imp_ は -Dimp_X=impc_X で改名 (重複排除)。
 * 本ファイルは curated import (ExitProcess/GetProcAddress/LoadStringW/memset ほか) と
 * --override 用 C 関数 (fle_ov_*) を持つ。
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <emscripten.h>
#include "../../shimx/src/shimx.h"
#include "../rt/fle_cpu.h"

typedef unsigned long long u64;
typedef unsigned int u32;
typedef unsigned char u8;

#define Q(a) (*(volatile u64*)(uintptr_t)(a))
#define D(a) (*(volatile u32*)(uintptr_t)(a))
#define PX(v) ((void*)(uintptr_t)(v))

#define ENTRY_VA        0x1376820u   /* PE AddressOfEntryPoint (DllMain, Delphi SysInit) */
#define INITCTX_TABLE   0x15eac90u   /* InitContext.InitTable (値 = 0x13768b0, _InitLib が設定) */
#define INITCTX_COUNT   0x15eac98u
#define MM_TABLE        0x13a5c90u   /* TMemoryManager (GetMem/FreeMem/ReallocMem/...) */
#define CB_RET_SENTINEL 0x1E00000u   /* callback 呼出の retaddr (通常は callee の ret で消費) */

/* ---------------- JS 例外化 (fail-fast / halt / soft strict) ---------------- */
EM_JS(void, fle_throw_kind, (long kind, long a), {
    throw { fle_kind: UTF8ToString(kind), fle_a: Number(a) };
});
EM_JS(void, fle_throw_soft, (const char* nm), {
    throw { fle_kind: 'soft', name: UTF8ToString(nm) };
});

extern uint64_t fle_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                        uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3);
extern void fle_data_install(void);       /* fle_data_gen.py 生成 (fle_lift.sh と同一物) */
extern void fle_textwin_install(void);    /* gen_boot.py 生成 (.text 内データ窓) */
extern void fle_init(void);               /* fle_glue.c: TEB 敷設 */
extern void fle_reset(void);              /* fle_glue.c: CPU 状態リセット */
extern void f_409730(void);               /* System: GetMem/FreeMem エラー処理 (lifted) */
void fle_blk_getmem_pre(u32 size, u32 ret);
void fle_blk_getmem_post(u32 p, u32 size);
void fle_blk_free_pre(u32 p, u32 ret);
void fle_blk_free_post(u32 p, u32 ok, u32 ret);

/* ---------------- 計数 ---------------- */
static u32 g_units_run, g_units_total, g_units_empty, g_boot_stage;
static u32 g_n_getmem, g_n_freemem, g_n_longjmp, g_n_exit, g_n_getproc, g_n_soft, g_n_cb, g_n_loadstr, g_n_cb_enum;
static int g_nullpage_off = 0;   /* FLE-4: 1 = NULL ページ guard を無効化 (既定 0 = 有効) */
static u32 g_va_calls; static u64 g_va_bytes;
static u32 g_survey;
/* dispatch probe: 直近 128 target のリング + 計数 (FastMM 0x407a50 系 / VMT 由来の観測) */
#define PROBE_RING 128
static u32 g_ring[PROBE_RING]; static u32 g_ring_n;
static u32 g_n_dispatch, g_n_disp_getmem, g_n_disp_freemem, g_n_disp_realloc, g_n_disp0;
static void fle_probe_dispatch(u64 t) {
    g_n_dispatch++;
    if (t == 0x407a50u) g_n_disp_getmem++;
    else if (t == 0x407e20u) g_n_disp_freemem++;
    else if (t == 0x408040u) g_n_disp_realloc++;
    else if (t == 0) { g_n_disp0++; return; }
    g_ring[g_ring_n % PROBE_RING] = (u32)t; g_ring_n++;
}
/* PY-123 (#3028): undo 系 global の 0 化を unit 単位で追う (計測のみ・挙動は変えない)。
 * 監視 slot の値が変わったときだけ記録する。unit = g_units_run (1-based・0 は InitUnits 前)。
 * site: 0 = fle_run 直前 (snap) / 1 = unit dispatch 直前 / 2 = unit dispatch 直後 / 3 = memset 直後 /
 *       4 = ExitProcess / 5 = MessageBoxW / 6 = GetMem 直後 / 7 = FreeMem 直後。
 * proc: site 1・2 は unit の proc VA、3 は memset の長さ、4 は呼出し元、6 は要求サイズ、7 は解放ポインタ。
 * aux: site 3 は memset の dst、6 は GetMem の戻り値 (0 = 失敗)、7 は FastMM の応答 (0 = 成功)。 */
#define PY_WATCH_N 3
#define PY_EV_MAX 64
typedef struct { u32 unit, site, slot, proc; u64 old, nw, aux; } py_ev;   /* 40 B (JS 側の読出しと一致) */
static const u32 g_py_watch[PY_WATCH_N] = { 0x15e1c78u, 0x15e4790u, 0x16b82e0u };
static u64 g_py_last[PY_WATCH_N];
static py_ev g_py_ev[PY_EV_MAX];
static u32 g_py_ev_n, g_py_ev_over;
static void py_watch_snap(void) {
    for (u32 k = 0; k < PY_WATCH_N; k++) {
        g_py_last[k] = LD64(g_py_watch[k]);
        if (g_py_ev_n < PY_EV_MAX) {
            py_ev* e = &g_py_ev[g_py_ev_n++];
            e->unit = 0; e->site = 0; e->slot = g_py_watch[k]; e->proc = 0; e->old = 0; e->nw = g_py_last[k]; e->aux = 0;
        }
    }
}
static void py_watch(u32 site, u32 proc, u64 aux) {
    for (u32 k = 0; k < PY_WATCH_N; k++) {
        u64 v = LD64(g_py_watch[k]);
        if (v == g_py_last[k]) continue;
        if (g_py_ev_n < PY_EV_MAX) {
            py_ev* e = &g_py_ev[g_py_ev_n++];
            e->unit = g_units_run; e->site = site; e->slot = g_py_watch[k]; e->proc = proc;
            e->old = g_py_last[k]; e->nw = v; e->aux = aux;
        } else g_py_ev_over++;
        g_py_last[k] = v;
    }
}
EMSCRIPTEN_KEEPALIVE unsigned fle_py_ev_ptr(void) { return (unsigned)(uintptr_t)g_py_ev; }
EMSCRIPTEN_KEEPALIVE int fle_py_ev_n(void) { return (int)g_py_ev_n; }
EMSCRIPTEN_KEEPALIVE int fle_py_ev_over(void) { return (int)g_py_ev_over; }
/* strict variant は link 構成として fail-fast 化 (-DFLEBOOT_STRICT=1)。実行時切替も可。 */
#if FLEBOOT_STRICT
unsigned char fle_g_strict = 1;
#else
unsigned char fle_g_strict = 0;
#endif

/* soft stub 呼出計数 (fle_imp_bridge.c から)。strict 時は例外で抜ける (戻らない)。 */
#define SOFT_MAX 512
static const char* g_soft_nm[SOFT_MAX]; static u32 g_soft_ct[SOFT_MAX]; static u32 g_soft_n;
long fle_soft_hit(const char* nm) {
    g_n_soft++;
    long idx = -1;
    for (u32 i = 0; i < g_soft_n; i++) if (!strcmp(g_soft_nm[i], nm)) { g_soft_ct[i]++; idx = (long)i; break; }
    if (idx < 0 && g_soft_n < SOFT_MAX) { g_soft_nm[g_soft_n] = nm; g_soft_ct[g_soft_n] = 1; idx = (long)g_soft_n++; }
    if (fle_g_strict) fle_throw_soft(nm);
    return idx;
}

/* fle_cpu.c の fail-fast を JS 例外化 (survey を 1 インスタンスで継続できるように) */
EM_JS(void, fle_js_err, (const char* s), { console.error(UTF8ToString(s)); });

/* ---------------- FLE-6: dsp_ippv2_x64.dll ローダ (f_653f40 の fill コールバック登録) ----------------
 * f_6539e0 は LoadLibraryW("dsp_ippv2_x64.dll") の戻りを 0x15F40E8 に保存し、f_653f40 は 0 だと
 * 早期 return する。さらに f_653dd0 が GetProcAddress(h, 423 名) の戻りを .bss に格納する
 * (0x15F34A0 = ippsZero_8u)。LoadLibraryW 失敗 + GetProcAddress 常に 0 が「0x15F34A0 未登録」の原因。
 * ここでは dsp_ippv2_x64.dll を擬似モジュール登録し、GetProcAddress に名前ごとのトークン
 * (guest 側では dispatch → ott_unlifted → fle_ff で処理) を返す。実装は ippsZero_8u のみ
 * (guest メモリを 0 埋め)、他は ippStsNoErr(0) を返す fail-soft + 呼出計数。 */
#define IPP_TOK_BASE 0x7F100000u
#define IPP_MAX 512
static const char* g_ipp_nm[IPP_MAX]; static u32 g_ipp_n, g_ipp_calls[IPP_MAX], g_ipp_total;
static u64 g_ipp_h; static int g_ipp_on = 0;   /* 既定は無効 (通常 boot の挙動を変えない)。fle_boot_set_ipp(1) で有効 */
static int g_ipp_stop = 0;                       /* mode 2 (#2702): ippsZero_8u 以外の IPP 呼出で停止 */
static const char* g_ipp_stop_nm; static u64 g_ipp_stop_site;
static u64 g_ipp_site[IPP_MAX];                  /* 各 IPP 名の初回呼出元 (ret) */
static u32 ipp_token(const char* nm) {
    for (u32 i = 0; i < g_ipp_n; i++) if (!strcmp(g_ipp_nm[i], nm)) return IPP_TOK_BASE + i;
    if (g_ipp_n >= IPP_MAX) return 0;
    char* d = (char*)malloc(strlen(nm) + 1); strcpy(d, nm);
    g_ipp_nm[g_ipp_n] = d;
    return IPP_TOK_BASE + g_ipp_n++;
}
static int ipp_call(u64 t) {   /* fle_ff から。処理したら 1 */
    if (t < IPP_TOK_BASE || t >= IPP_TOK_BASE + g_ipp_n) return 0;
    u32 i = (u32)(t - IPP_TOK_BASE);
    if (!g_ipp_calls[i]) g_ipp_site[i] = LD64(R[4]);
    g_ipp_calls[i]++; g_ipp_total++;
    if (!strcmp(g_ipp_nm[i], "ippsZero_8u")) {   /* IppStatus ippsZero_8u(Ipp8u* pDst, int len) */
        u64 dst = R[1]; int len = (int)(R[2] & 0xffffffffu);
        if (dst && len > 0) memset((void*)(uintptr_t)dst, 0, (size_t)len);
    } else if (g_ipp_stop) {                     /* mode 2: 停止して名前と呼出元を残す */
        g_ipp_stop_nm = g_ipp_nm[i]; g_ipp_stop_site = LD64(R[4]);
        fle_throw_kind((long)(intptr_t)"ipp_stop", (long)i);
    }
    R[4] += 8; R[0] = 0;
    return 1;
}
#define IPP_HMOD 0x7F0F0000u   /* wasm メモリ外の擬似 HMODULE */
static HMODULE fle_ipp_load_hook(const char* name, DWORD flags) {
    (void)flags;
    if (g_ipp_on && name && strstr(name, "dsp_ippv2")) { g_ipp_h = IPP_HMOD; return (HMODULE)(uintptr_t)IPP_HMOD; }
    return 0;
}
/* mode: 0 = 無効 (既定) / 1 = shim 有 (ippsZero_8u 以外は fail-soft) / 2 = shim 有 + ippsZero_8u 以外で停止 (#2702) */
EMSCRIPTEN_KEEPALIVE void fle_boot_set_ipp(int mode) { g_ipp_on = (int)(mode != 0); g_ipp_stop = (mode == 2); }
EMSCRIPTEN_KEEPALIVE u32 fle_ipp_total(void) { return g_ipp_total; }
EMSCRIPTEN_KEEPALIVE u32 fle_ipp_names(void) { return g_ipp_n; }
EMSCRIPTEN_KEEPALIVE const char* fle_ipp_name(int i) { return (u32)i < g_ipp_n ? g_ipp_nm[i] : ""; }
EMSCRIPTEN_KEEPALIVE u32 fle_ipp_count(int i) { return (u32)i < g_ipp_n ? g_ipp_calls[i] : 0; }
EMSCRIPTEN_KEEPALIVE u32 fle_ipp_site(int i) { return (u32)i < g_ipp_n ? (u32)g_ipp_site[i] : 0; }
EMSCRIPTEN_KEEPALIVE const char* fle_ipp_stop_name(void) { return g_ipp_stop_nm ? g_ipp_stop_nm : ""; }
EMSCRIPTEN_KEEPALIVE u32 fle_ipp_stop_site(void) { return (u32)g_ipp_stop_site; }

/* fle_cpu.c の fail-fast を JS 例外化 (survey を 1 インスタンスで継続できるように)。
 * unlifted(0) は m11 の icall-miss (ret 0) 揃えで容忍: retaddr を pop して RAX=0 で dispatch に戻る。 */
static void fle_ff(const char* kind, u64 a) {
    char buf[160];
    if (!strcmp(kind, "unlifted") && ipp_call(a)) return;
    if (!strcmp(kind, "unlifted") && a == 0) {
        snprintf(buf, sizeof buf, "[fleboot][ff] dispatch(0) -> ret 0 (m11 icall-miss 揃え, call site ret=0x%llx)",
                 (unsigned long long)LD64(R[4]));
        fle_js_err(buf);
        R[4] += 8; R[0] = 0;
        return;
    }
    snprintf(buf, sizeof buf, "[fleboot][ff] %s 0x%llx (call site ret=0x%llx)",
             kind, (unsigned long long)a, (unsigned long long)LD64(R[4]));
    fle_js_err(buf);
    fle_throw_kind((long)(intptr_t)kind, (long)a);
}

/* ---------------- shimx callback 橋絡み (R2/CAB-177 踏襲) ---------------- */
/* cbtrans invoke 契約: u64 fn(va, a0..a7) — a0..a3 = rcx/rdx/r8/r9, a4..a7 = stack */
static u64 fle_icall9(u64 va, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) {
    g_n_cb++;
    u64 saved = R[4];
    R[4] -= 8 + 0x20 + 8 * 4;                       /* ret + shadow + stack args */
    u64 base = R[4];
    ST64(base, CB_RET_SENTINEL);
    ST64(base + 0x28, a4); ST64(base + 0x30, a5); ST64(base + 0x38, a6); ST64(base + 0x40, a7);
    R[1] = a0; R[2] = a1; R[8] = a2; R[9] = a3;
    ott_dispatch(va);
    R[4] = saved;
    return R[0];
}

/* ---------------- curated imports: コールバック列挙 API (FLE-2) ----------------
 * shimx の cbtrans トランポリンは「C 関数ポインタ = wasm 関数 index」として
 * call_indirect する設計で、トランポリン未登録のAPI/index だと
 * "table index is out of bounds" で trap する (m11 REPORT #3 と同一事象)。
 * lift 側が dispatch の正本なので、ここでコールバック VA を直接 fle_icall9 に落とす。
 * Windows の意味に合わせた最小エミュレーション (shimx locale.c の k_* 表を借用しない —
 * 読み取りのみで per-calendar の列挙順が必要なため、列挙そのものを 1 件も呼ばず
 * 「0 件」で正常終了させる = m11 の「icall-miss 1 で列挙は打切り」と等価な穏当縮退)。 */
void imp_EnumCalendarInfoW(void) {
    /* BOOL EnumCalendarInfoW(LCID, CALID, CALTYPE, CALINFO_ENUMPROCW cb) */
    u64 cb = LD64(R[4] + 0x20 + 8 * 3);   /* 4th stack arg */
    if (cb >= 0x100000ull) g_n_cb_enum++;  /* guest VA っぽい値 -> 呼ばれるはずだった */
    R[4] += 8; R[0] = 1;                   /* TRUE = 正常終了 (0 件) */
}
void imp_EnumSystemLocalesW(void) {
    /* BOOL EnumSystemLocalesW(LOCALE_ENUMPROCW cb, DWORD flags) */
    u64 cb = R[1];
    if (cb >= 0x100000ull) g_n_cb_enum++;
    R[4] += 8; R[0] = 1;
}
void imp_ExitProcess(void) {
    g_n_exit++;
    fprintf(stderr, "[fleboot][exit] code=%u call_site=0x%llx\n", (unsigned)(R[1] & 0xffffffff), (unsigned long long)LD64(R[4]));
    py_watch(4, (u32)LD64(R[4]), R[1] & 0xffffffffu);
    for (int i = 0; i < 40; i++) { u64 v = LD64(R[4] + 8ull * i); if (v >= 0x401000ull && v < 0x13a44b0ull) fprintf(stderr, "[py123][exit-stack] +%d 0x%llx\n", i, (unsigned long long)v); }
    fle_throw_kind((long)(intptr_t)"exit", (long)(R[1] & 0xffffffff));
}
void imp_TerminateProcess(void) { g_n_exit++; fle_throw_kind((long)(intptr_t)"exit", 3); }
void imp_GetProcAddress(void) {  /* m11 旧 stub 揃え (REPORT §4)。FLE-6: dsp_ippv2 のみトークンを返す */
    u64 h = R[1] & 0xffffffffu, nm = R[2];
    g_n_getproc++; R[4] += 8; R[0] = 0;
    if (g_ipp_on && g_ipp_h && h == g_ipp_h && nm >= 0x10000ull) R[0] = ipp_token((const char*)(uintptr_t)nm);
}
void imp_LoadStringW(void) {   /* gui_compat.c と同一: buf[0]=0 を書かないと LoadResString が暴走 */
    u64 buf = R[9];
    g_n_loadstr++;
    if (buf) ST16(buf, 0);
    R[4] += 8; R[0] = 0;
}
void imp_memset(void) {        /* CRT 実体 (soft 0 返却だと意味破壊) */
    u64 dst = R[1]; u32 c = R[2] & 0xff; u64 n = R[3];
    if (n) memset((void*)(uintptr_t)dst, (int)c, n);
    py_watch(3, (u32)n, dst);
    R[4] += 8; R[0] = dst;
}
void imp_MessageBoxA(void) {
    fprintf(stderr, "[fleboot][MessageBoxA] text='%s' (自動 IDOK)\n", (char*)(uintptr_t)R[2]);
    R[4] += 8; R[0] = 1;
}
void imp_MessageBoxW(void) {
    unsigned short* w = (unsigned short*)(uintptr_t)R[2];
    char t[256]; int i;
    for (i = 0; w && w[i] && i < 255; i++) t[i] = w[i] < 128 ? (char)w[i] : '?'; t[i] = 0;
    fprintf(stderr, "[fleboot][MessageBoxW] text='%s' (自動 IDOK)\n", t);
    py_watch(5, (u32)LD64(R[4]), 0);
    R[4] += 8; R[0] = 1;
}
void imp_RaiseException(void) {  /* Delphi SEH raise → JS 例外化 (boot/survey を継続させる) */
    u64 code = R[1], p0 = R[8];
    fprintf(stderr, "[fleboot][raise] code=0x%llx p0=0x%llx call_site=0x%llx (SEH 未対応 → 例外化)\n",
            (unsigned long long)code, (unsigned long long)p0, (unsigned long long)LD64(R[4]));
    fle_throw_kind((long)(intptr_t)"raise", (long)code);
}
void imp_VirtualAlloc(void) {  /* shimx VirtualAlloc (weak) へ委譲 + 計数 */
    u64 addr = R[1], size = R[2]; u32 type = R[8] & 0xffffffff, prot = R[9] & 0xffffffff;
#if FLEBOOT_NOSX
    /* nosx: shimx 未 link なので fle_cpu.c の bump allocator を使う */
    static uint64_t cur = 0x2100000ull;
    uint64_t sz = (size + 0xffff) & ~0xffffull;
    void* p = memset((void*)A_(cur), 0, (size_t)sz); cur += sz;
#else
    void* p = VirtualAlloc(PX(addr), size, type, prot);
#endif
    g_va_calls++; g_va_bytes += size;
    R[4] += 8; R[0] = (u64)(uintptr_t)p;
}

/* ---------------- --override C 実装 ---------------- */

/* ============ FLE-2 diag: FastMM block 追跡 (unit#17 FreeMem invalid pointer の特定) ============
 * System._GetMem / _FreeMem は全 RTL 経路が通る関所 (0x412c20 dynarray alloc / 0x412d60
 * @DynArrayClear / 0x409470 _ReallocMem のいずれも mm table 経由) ため、ここで
 *   (1) alloc/free の時系列 (seq, size, ptr, 呼出元 retaddr 連鎖)
 *   (2) live block の 16B snapshot canary 再検証 → 書換えが起きた alloc 区間の特定
 *   (3) free 対象の追跡情報 (初回 alloc seq / size / 二重解放 / 未追跡 / header 内容)
 * を記録する。読出は wasm linear memory 全域 ([0,0x36000000)) で安全。
 */
#define BLKDIAG_MAX   768
#define BLKDIAG_MEMSZ 0x36000000ull
#define TEXT_LO       0x401000u
#define TEXT_HI       0x13a44b0u
#define DYN_HDR       16u        /* dynarray header: base+8=refcnt, base+0xC=len, data=base+0x10 */

typedef struct {
    u32 ptr, size, seq, site2, site3;
    u32 snap[4];
    u32 state;            /* 1 = live, 0 = freed */
    u32 fseq, fsite;
    u32 ref_at_alloc, len_at_alloc;
} blkdiag_t;
static blkdiag_t g_bd[BLKDIAG_MAX];
static u32 g_bd_n, g_bd_seq, g_bd_verbose = 1;
static u32 g_bd_alloc_n, g_bd_free_n, g_bd_free_ok, g_bd_free_fail, g_bd_dblfree, g_bd_notrack;
static u32 g_bd_canary_hit;                     /* 最初に canary 不一致を検出した seq */
static u32 g_bd_lo = 0xffffffffu, g_bd_hi;
EMSCRIPTEN_KEEPALIVE void fle_boot_set_blkdiag(int v) { g_bd_verbose = (u32)(v != 0); }
/* NULL ページ guard の ON/OFF (既定 ON)。0 にすると元の wasm 内容に戻す。 */
EMSCRIPTEN_KEEPALIVE void fle_boot_set_nullpage(int off) { g_nullpage_off = (int)(off != 0); }

static u32 bd_site(int k) {                    /* guest stack 上の直近 .text retaddr (k 段上) */
    u64 sp = R[4];
    for (int i = 0; i < 4 + k; i++) {
        u64 a = sp + 8ull * i;
        if (a + 8 > BLKDIAG_MEMSZ) break;
        u64 v = LD64(a);
        if (v >= TEXT_LO && v < TEXT_HI) { if (k == 0) return (u32)v; k--; }
    }
    return 0;
}
static int bd_ok(u64 a, u64 n) { return a < BLKDIAG_MEMSZ && a + n <= BLKDIAG_MEMSZ; }

static void bd_dump(u32 p, const char* tag) {
    fprintf(stderr, "[blkdiag]   %s p=0x%x align=%u\n", tag, p, p & 0xf);
    if (!bd_ok(p - 32, 48)) { fprintf(stderr, "[blkdiag]     (dump 範囲外)\n"); return; }
    fprintf(stderr, "[blkdiag]     -32:0x%08x 0x%08x 0x%08x 0x%08x\n", LD32(p-32), LD32(p-28), LD32(p-24), LD32(p-20));
    fprintf(stderr, "[blkdiag]     -16:0x%08x 0x%08x 0x%08x 0x%08x\n", LD32(p-16), LD32(p-12), LD32(p-8), LD32(p-4));
    fprintf(stderr, "[blkdiag]     +00:0x%08x 0x%08x 0x%08x 0x%08x   <p\n", LD32(p), LD32(p+4), LD32(p+8), LD32(p+12));
    if (p + DYN_HDR + 8 < BLKDIAG_MEMSZ)
        fprintf(stderr, "[blkdiag]     dyn: refcnt=%d len=%d elem@0=%d elem@4=%d\n",
                (int)LD32(p + 8), (int)LD32(p + 12), (int)LD32(p + 16), (int)LD32(p + 20));
}
static blkdiag_t* bd_find(u32 p) {
    blkdiag_t* last = 0;
    for (u32 i = 0; i < g_bd_n; i++) if (g_bd[i].ptr == p) last = &g_bd[i];
    return last;
}
/* live block の canary (alloc 時 snapshot) 再検証 — guest store による破壊を検出 */
static void bd_canary(const char* when) {
    for (u32 i = 0; i < g_bd_n; i++) {
        blkdiag_t* b = &g_bd[i];
        if (b->state != 1 || !b->ptr || !bd_ok(b->ptr, DYN_HDR)) continue;
        if (LD32(b->ptr) != b->snap[0] || LD32(b->ptr + 4) != b->snap[1] ||
            LD32(b->ptr + 8) != b->snap[2] || LD32(b->ptr + 12) != b->snap[3]) {
            if (!g_bd_canary_hit) {
                g_bd_canary_hit = g_bd_seq;
                fprintf(stderr, "[blkdiag] CANARY HIT at seq=%u (%s) blk#%u p=0x%x size=%u\n",
                        g_bd_seq, when, i, b->ptr, b->size);
                fprintf(stderr, "[blkdiag]   alloc seq=%u site=0x%x<-0x%x  snapshot=%08x %08x %08x %08x\n",
                        b->seq, b->site2, b->site3, b->snap[0], b->snap[1], b->snap[2], b->snap[3]);
                fprintf(stderr, "[blkdiag]   now      =%08x %08x %08x %08x\n",
                        LD32(b->ptr), LD32(b->ptr + 4), LD32(b->ptr + 8), LD32(b->ptr + 12));
                bd_dump(b->ptr, "canary block");
            }
            b->snap[0] = LD32(b->ptr); b->snap[1] = LD32(b->ptr + 4);
            b->snap[2] = LD32(b->ptr + 8); b->snap[3] = LD32(b->ptr + 12);
        }
    }
}
void fle_blk_getmem_pre(u32 size, u32 ret) {
    g_bd_seq++;                        /* seq は alloc 単位で 1 つだけ進める */
    if (g_bd_seq == 1) fprintf(stderr, "[blkdiag] 有効 (System._GetMem/_FreeMem トラッキング開始)\n");
    bd_canary("GetMem");
    if (g_bd_verbose)
        fprintf(stderr, "[blkdiag] GETMEM  seq=%u size=%u site=0x%x<-0x%x live=%u\n",
                g_bd_seq, size, bd_site(0), bd_site(1), g_bd_n);
    (void)ret;
}
void fle_blk_getmem_post(u32 p, u32 size) {
    g_bd_alloc_n++;
    if (!p) return;
    if (g_bd_lo > p) g_bd_lo = p;
    if (g_bd_hi < p) g_bd_hi = p;
    if (g_bd_n < BLKDIAG_MAX) {
        blkdiag_t* b = &g_bd[g_bd_n++];
        b->ptr = p; b->size = size; b->seq = g_bd_seq; b->state = 1;
        b->site2 = bd_site(0); b->site3 = bd_site(1);
        b->fseq = b->fsite = 0;
        if (bd_ok(p, DYN_HDR)) {
            b->snap[0] = LD32(p); b->snap[1] = LD32(p + 4);
            b->snap[2] = LD32(p + 8); b->snap[3] = LD32(p + 12);
            b->ref_at_alloc = LD32(p + 8); b->len_at_alloc = LD32(p + 12);
        } else { b->snap[0] = b->snap[1] = b->snap[2] = b->snap[3] = 0; b->ref_at_alloc = b->len_at_alloc = 0; }
    }
    if (g_bd_verbose) {
        blkdiag_t* d = bd_find(p);
        u32 prev = 0; for (u32 i = 0; i < g_bd_n; i++) if (g_bd[i].ptr == p) prev++;
        if (prev > 1) fprintf(stderr, "[blkdiag]   !! 同一 ptr 0x%x が %u 回目に返却 (alloc seq=%u)\n", p, prev, g_bd_seq);
        (void)d;
    }
}
void fle_blk_free_pre(u32 p, u32 ret) {
    bd_canary("FreeMem");
    blkdiag_t* b = bd_find(p);
    if (g_bd_verbose) {
        fprintf(stderr, "[blkdiag] FREEMEM seq=%u p=0x%x site=0x%x<-0x%x  liveblk=%u\n",
                g_bd_seq, p, bd_site(0), bd_site(1), g_bd_n);
        if (b) fprintf(stderr, "[blkdiag]   tracked: alloc seq=%u size=%u state=%s site=0x%x<-0x%x\n",
                       b->seq, b->size, b->state ? "live" : "ALREADY-FREED", b->site2, b->site3);
        else   { fprintf(stderr, "[blkdiag]   NOT TRACKED (本 _GetMem 経路で確保されていない)\n"); g_bd_notrack++; }
        if (b && !b->state) g_bd_dblfree++;
        bd_dump(p, "free 対象");
    }
    (void)ret;
}
void fle_blk_free_post(u32 p, u32 ok, u32 ret) {
    blkdiag_t* b = bd_find(p);
    g_bd_free_n++;
    if (!ok) {                    /* FastMM: 0 = 成功 / 非 0 = エラー (0x40801f は -1) */
        g_bd_free_ok++;
        if (b) { b->state = 0; b->fseq = g_bd_seq; b->fsite = bd_site(0); }
        return;
    }
    g_bd_free_fail++;
    fprintf(stderr, "[blkdiag] *** FastMM FreeMem REJECTED (ret=%d) p=0x%x (seq=%u, site=0x%x<-0x%x)\n",
            (int)ok, p, g_bd_seq, bd_site(0), bd_site(1));
        if (b) {
            fprintf(stderr, "[blkdiag]   alloc: seq=%u size=%u refcnt@alloc=%d len@alloc=%d site=0x%x<-0x%x\n",
                    b->seq, b->size, (int)b->ref_at_alloc, (int)b->len_at_alloc, b->site2, b->site3);
            fprintf(stderr, "[blkdiag]   now:   refcnt=%d len=%d\n",
                    (int)LD32(p + 8), (int)LD32(p + 12));
        } else fprintf(stderr, "[blkdiag]   alloc: NOT TRACKED\n");
        bd_dump(p, "REJECTED block");
        fprintf(stderr, "[blkdiag]   統計: alloc=%u free=%u(ok=%u fail=%u) dblfree=%u notrack=%u canary_seq=%u\n",
                g_bd_alloc_n, g_bd_free_n, g_bd_free_ok, g_bd_free_fail, g_bd_dblfree, g_bd_notrack, g_bd_canary_hit);
        fprintf(stderr, "[blkdiag]   FastMM dispatch: getmem=%u freemem=%u realloc=%u  heap=[0x%x..0x%x]\n",
                g_n_disp_getmem, g_n_disp_freemem, g_n_disp_realloc, g_bd_lo, g_bd_hi);
        /* live block の一覧 (refcnt を含む) — 二重参照の材料 */
        for (u32 i = 0; i < g_bd_n; i++) {
            blkdiag_t* l = &g_bd[i];
            if (l->state != 1) continue;
            fprintf(stderr, "[blkdiag]   live[%u] p=0x%x size=%u seq=%u refcnt=%d len=%d site=0x%x<-0x%x\n",
                    i, l->ptr, l->size, l->seq, (int)LD32(l->ptr + 8), (int)LD32(l->ptr + 12), l->site2, l->site3);
        }
}
EMSCRIPTEN_KEEPALIVE int fle_blkdiag_stat(int k) {
    switch (k) {
    case 0: return (int)g_bd_alloc_n;
    case 1: return (int)g_bd_free_n;
    case 2: return (int)g_bd_free_ok;
    case 3: return (int)g_bd_free_fail;
    case 4: return (int)g_bd_dblfree;
    case 5: return (int)g_bd_notrack;
    case 6: return (int)g_bd_canary_hit;
    case 7: return (int)g_bd_n;
    default: return 0;
    }
}

/* f_4126f0 = System longjmp (rcx=jmp_buf, edx=retval)。実機: xchg edx,eax → レジスタ復元
 * (rbx,rbp,rsi,rdi,r12-15,xmm6-15) → rsp=[buf+8] → jmp [buf] (0x1376840 断片へ)。計数を追加。 */
void fle_ov_longjmp(void) {
    g_n_longjmp++;
    u64 buf = R[1];
    u32 retval = R[2] & 0xffffffff;
    R[0] = retval;                       /* xchg edx,eax (32bit 書込) */
    R[3] = LD64(buf + 0x10);             /* rbx */
    R[5] = LD64(buf + 0x18);             /* rbp */
    R[6] = LD64(buf + 0x20);             /* rsi */
    R[7] = LD64(buf + 0x28);             /* rdi */
    R[12] = LD64(buf + 0x30); R[13] = LD64(buf + 0x38); R[14] = LD64(buf + 0x40); R[15] = LD64(buf + 0x48);
    for (int k = 0; k < 10; k++) X[6 + k] = LDX(buf + 0x50 + 16 * k);   /* xmm6..15 */
    R[4] = LD64(buf + 8);                /* rsp */
    ott_dispatch(LD64(buf));             /* jmp qword ptr [rcx] */
}

/* f_409410 = System._GetMem(size) — mm table 経由の呼出を計数 (逆アセンブル照合済の転記)
 * スタック約束: x64c の call_stmt は「R[RSP] -= 8; ST64(R[RSP], retaddr); f_T();」を発行し、
 * callee 側は ret で R[RSP] += 8 する。本 override は C 関数なので、mm table の実装
 * (0x407a50 等) を ott_dispatch で呼ぶ前に **独自の** 偽 retaddr を 1 段 push している。
 * その push は callee の ret で消費されるが、guest の `call` が push した本来の retaddr は
 * 消費されないため、ここで R[4] += 8 して釣合させないと 1 呼出につき guest stack が 8B
 * ずつ沈む — 呼出元の `pop rbx` が 8B 低い slot を読み、野生指针になって OOB する
 * (FLE-2 実測: f_412c20 → f_413060 の rbx = 0x43000000000000 → OOB)。
 */
void fle_ov_getmem(void) {
    g_n_getmem++;
    u64 save_rbx = R[3];
    if ((int64_t)R[1] > 0) {
        u32 gsz = (u32)R[1], gret = (u32)LD64(R[4]);
        fle_blk_getmem_pre(gsz, gret);              /* diag: canary 検証 + 記録 */
        u64 t_ = LD64(MM_TABLE);
        R[4] -= 8; ST64(R[4], 0x409424ull);
        ott_dispatch(t_);
        R[4] += 8;                                  /* 拙い push/pop 釣合 (下記注記) */
        u64 p = R[0];
        py_watch(6, gsz, p);
        fle_blk_getmem_post((u32)p, gsz);
        if (!p) { R[1] = (R[1] & ~0xffull) | 1; R[4] -= 8; ST64(R[4], 0x409433ull); f_409730(); }
        R[3] = save_rbx; R[0] = p;
        return;
    }
    R[3] = save_rbx; R[0] = 0;
}

/* f_409440 = System._FreeMem(p)
 * 実機意味 (逆アセンブル照合済):
 *   0x409454 mov ebx, eax / test ebx, ebx / je 0x409461 / mov cl,2 / call @Error
 *   → FastMM 側の戻りは **0 = 成功 / 非 0 = エラー** (0x40801f は mov eax,-1)。
 * したがって _Error を呼ぶ条件は `ok != 0` (旧実装は !ok で判定しており、正常 free を
 * エラー扱いしていた — FLE-2 unit#17 停止の直接原因)。
 * スタック約束は fle_ov_getmem の注記参照 (R[4] += 8 の釣合が必須)。 */
void fle_ov_freemem(void) {
    g_n_freemem++;
    u64 save_rbx = R[3];
    if (R[1]) {
        u32 fp = (u32)R[1], fret = (u32)LD64(R[4]);
        fle_blk_free_pre(fp, fret);              /* diag: 破壊 / 二重解放 / 未追跡の記録 */
        u64 t_ = LD64(MM_TABLE + 8);
        R[4] -= 8; ST64(R[4], 0x409454ull);
        ott_dispatch(t_);
        R[4] += 8;                                  /* 拙い push/pop 釣合 (下記注記) */
        u32 ok = R[0] & 0xffffffff;
        py_watch(7, fp, ok);
        fle_blk_free_post(fp, ok, fret);         /* diag: FastMM 応答 (0=成功) */
        if (ok) { R[1] = (R[1] & ~0xffull) | 2; R[4] -= 8; ST64(R[4], 0x409461ull); f_409730(); }
        R[3] = save_rbx; R[0] = ok;
        return;
    }
    R[3] = save_rbx; R[0] = 0;
}

/* f_4120c0 = System.InitUnits — boot: 計数つき unit 連鎖 / survey: total のみ設定して戻る */
void fle_ov_initunits(void) {
    u64 tbl = LD64(INITCTX_TABLE);
    if (!tbl) return;
    u32 count = LD32(tbl);
    u64 units = LD64(tbl + 8);
    g_units_total = count;
    if (g_survey) return;
    for (u32 i = 0; i < count; i++) {
        u64 proc = LD64(units + 16ull * i);
        ST32(INITCTX_COUNT, i + 1);
        if (!proc) continue;
        if (LD64(proc) == 0) { g_units_empty++; continue; }   /* 実機と同じ [proc]!=0 check (.text 窓) */
        g_units_run++;
        py_watch(1, (u32)proc, 0);
        R[4] -= 8; ST64(R[4], 0x412129ull);   /* 実機の call [rbp+0x38] (0x412126, 3B) の復帰点 */
        R[1] = 0; R[2] = 0; R[8] = 0; R[9] = 0;
        ott_dispatch(proc);
        py_watch(2, (u32)proc, 0);
    }
}

/* FLE-5 診断フック (既定 0 = 無効)。gentrace/dbg lift の fprintf を有効にする。
 * 設定は fle_boot_set_dbg(int)。diagnostic lift (work/boot/dbgout/) のみ参照。 */
int g_dbg_6c = 0;
EMSCRIPTEN_KEEPALIVE void fle_boot_set_dbg(int v) { g_dbg_6c = (int)(v != 0); }
static int g_installed;
EMSCRIPTEN_KEEPALIVE void fle_boot_set_strict(int v) { fle_g_strict = (unsigned char)(v != 0); }
EMSCRIPTEN_KEEPALIVE void fle_test_throw(void) { fle_throw_kind((long)(intptr_t)"test", 5); }
EMSCRIPTEN_KEEPALIVE int fle_units_run(void) { return (int)g_units_run; }
EMSCRIPTEN_KEEPALIVE int fle_units_total(void) { return (int)g_units_total; }
EMSCRIPTEN_KEEPALIVE int fle_units_empty(void) { return (int)g_units_empty; }
EMSCRIPTEN_KEEPALIVE int fle_boot_stage(void) { return (int)g_boot_stage; }
EMSCRIPTEN_KEEPALIVE int fle_n_getmem(void) { return (int)g_n_getmem; }
EMSCRIPTEN_KEEPALIVE int fle_n_freemem(void) { return (int)g_n_freemem; }
EMSCRIPTEN_KEEPALIVE int fle_n_longjmp(void) { return (int)g_n_longjmp; }
EMSCRIPTEN_KEEPALIVE int fle_n_exit(void) { return (int)g_n_exit; }
EMSCRIPTEN_KEEPALIVE int fle_n_getproc(void) { return (int)g_n_getproc; }
EMSCRIPTEN_KEEPALIVE int fle_n_soft(void) { return (int)g_n_soft; }
EMSCRIPTEN_KEEPALIVE int fle_n_soft_uniq(void) { return (int)g_soft_n; }
EMSCRIPTEN_KEEPALIVE const char* fle_soft_name(int i) { return (i >= 0 && i < (int)g_soft_n) ? g_soft_nm[i] : ""; }
EMSCRIPTEN_KEEPALIVE int fle_soft_count(int i) { return (i >= 0 && i < (int)g_soft_n) ? (int)g_soft_ct[i] : 0; }
EMSCRIPTEN_KEEPALIVE int fle_va_calls(void) { return (int)g_va_calls; }
EMSCRIPTEN_KEEPALIVE long long fle_va_bytes(void) { return (long long)g_va_bytes; }
EMSCRIPTEN_KEEPALIVE int fle_n_cb(void) { return (int)g_n_cb; }
EMSCRIPTEN_KEEPALIVE int fle_n_loadstr(void) { return (int)g_n_loadstr; }
EMSCRIPTEN_KEEPALIVE int fle_n_cb_enum(void) { return (int)g_n_cb_enum; }
EMSCRIPTEN_KEEPALIVE int fle_n_dispatch(void) { return (int)g_n_dispatch; }
EMSCRIPTEN_KEEPALIVE int fle_n_disp_getmem(void) { return (int)g_n_disp_getmem; }
EMSCRIPTEN_KEEPALIVE int fle_n_disp_freemem(void) { return (int)g_n_disp_freemem; }
EMSCRIPTEN_KEEPALIVE int fle_n_disp_realloc(void) { return (int)g_n_disp_realloc; }
EMSCRIPTEN_KEEPALIVE int fle_n_disp0(void) { return (int)g_n_disp0; }
EMSCRIPTEN_KEEPALIVE unsigned fle_ring_at(int i) { return g_ring[(g_ring_n + i) % PROBE_RING]; }
EMSCRIPTEN_KEEPALIVE unsigned fle_unit_proc(int i) {
    u64 tbl = LD64(INITCTX_TABLE);
    if (!tbl) return 0;
    u32 count = LD32(tbl);
    if (i < 0 || (u32)i >= count) return 0;
    return (unsigned)LD64(LD64(tbl + 8) + 16ull * (u64)i);
}

EMSCRIPTEN_KEEPALIVE void fle_boot_enter(int survey) {
    if (!g_installed) {
        fle_data_install();
        fle_textwin_install();
        fle_init();
        /* FLE-4: NULL ページ guard。guest が field_8 == NULL のオブジェクトに対して
         * `mov rax,[rax+8]; mov rcx,rax; mov rbx,[rax]; call [rbx+0x18]` (仮想呼出) を
         * 実行すると、wasm では linear address 0 に emscripten の magic ("emsc" =
         * 0x63736d65) があるため `call [0x63736d7d]` で OOB trap する
         * (unit#209 で実測: chk variant が __LINE__=1015940 → lift C の
         *  `0x8157c1: call qword ptr [rbx + 0x18]` を指した)。
         * ネイティブ Windows では AV になるところを、m11 の icall-miss 規約と同じ
         * 「NULL 参照は 0 扱い」にして boot 連鎖を続行する。
         * guest イメージは 0x400000 始まりなので [0, 0x1000) は未使用領域。 */
        if (!g_nullpage_off) memset((void*)A_(0), 0, 0x1000);
#if !FLEBOOT_NOSX
        /* nosx variant は shimx を link しない (fle_cpu.c の imp_ のみ) ので、shimx 依存の
         * wiring は丸ごと落とす。旧実装はここが無条件で nosx が link できなかった
         * (FLE-2 実測: wasm-ld undefined symbol shimx_cbtrans_* 等 8 件)。 */
        shimx_cbtrans_set_invoke((shimx_cb_invoke_fn)fle_icall9);
        shimx_cbtrans_install();
        shimx_set_proc_resolver(shimx_lifttab_proc_resolver);
        shimx_set_intptr_limit(0x10000);
        /* FLE-3: R7 互換モード。unit 111 で `InitializeCriticalSectionEx(NULL/misaligned)` が
         * shimx の fail-fast に掛かり abort していた (実測: work/boot/run_plain.log)。
         * CRITICAL_SECTION は単一スレッド前提では意味を持たないので no-op で通し、
         * boot 連鎖の先を伸ばす。副作用: Enter/Leave/TryEnter の意味が失われる
         * (survey の lock 依存 unit は誤判定する可能性 — REPORT §5 に記録)。 */
        shimx_set_cs_null_ok(1);
        /* FLE-6: dsp_ippv2_x64.dll の LoadLibraryW を成功させる (f_6539e0 → 0x15F40E8) */
        shimx_set_load_hook(fle_ipp_load_hook);
#endif
        fle_ff_hook = fle_ff;
        fle_dispatch_probe = fle_probe_dispatch;
        g_installed = 1;
#if FLEBOOT_NOSX
        fprintf(stderr, "[fleboot] image + textwin installed (nosx: shimx 未 link)\n");
#else
        fprintf(stderr, "[fleboot] image + textwin installed, shimx cbtrans/resolver wired\n");
#endif
    }
    g_survey = (u32)survey;
    g_units_run = g_units_total = g_units_empty = 0;
    g_n_getmem = g_n_freemem = g_n_longjmp = g_n_exit = 0;
    g_py_ev_n = g_py_ev_over = 0;
    py_watch_snap();
    g_boot_stage = 1;
    /* DllMain(hinst=0, DLL_PROCESS_ATTACH=1, reserved=0) — m11_boot_enter(0,1) と同一条件 */
    fle_run(ENTRY_VA, 0, 1, 0, 0, 0, 0, 0, 0);
    g_boot_stage = 2;
}
