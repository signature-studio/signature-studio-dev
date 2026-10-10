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

/* ---------------- 計数 ---------------- */
static u32 g_units_run, g_units_total, g_units_empty, g_boot_stage;
static u32 g_n_getmem, g_n_freemem, g_n_longjmp, g_n_exit, g_n_getproc, g_n_soft, g_n_cb, g_n_loadstr;
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

/* fle_cpu.c の fail-fast を JS 例外化 (survey を 1 インスタンスで継続できるように)。
 * unlifted(0) は m11 の icall-miss (ret 0) 揃えで容忍: retaddr を pop して RAX=0 で dispatch に戻る。 */
static void fle_ff(const char* kind, u64 a) {
    char buf[160];
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

/* ---------------- curated imports ---------------- */
void imp_ExitProcess(void) {
    g_n_exit++;
    fprintf(stderr, "[fleboot][exit] code=%u call_site=0x%llx\n", (unsigned)(R[1] & 0xffffffff), (unsigned long long)LD64(R[4]));
    fle_throw_kind((long)(intptr_t)"exit", (long)(R[1] & 0xffffffff));
}
void imp_TerminateProcess(void) { g_n_exit++; fle_throw_kind((long)(intptr_t)"exit", 3); }
void imp_GetProcAddress(void) { g_n_getproc++; R[4] += 8; R[0] = 0; }  /* m11 旧 stub 揃え (REPORT §4) */
void imp_LoadStringW(void) {   /* gui_compat.c と同一: buf[0]=0 を書かないと LoadResString が暴走 */
    u64 buf = R[9];
    g_n_loadstr++;
    if (buf) ST16(buf, 0);
    R[4] += 8; R[0] = 0;
}
void imp_memset(void) {        /* CRT 実体 (soft 0 返却だと意味破壊) */
    u64 dst = R[1]; u32 c = R[2] & 0xff; u64 n = R[3];
    if (n) memset((void*)(uintptr_t)dst, (int)c, n);
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
    void* p = VirtualAlloc(PX(addr), size, type, prot);
    g_va_calls++; g_va_bytes += size;
    R[4] += 8; R[0] = (u64)(uintptr_t)p;
}

/* ---------------- --override C 実装 ---------------- */

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

/* f_409410 = System._GetMem(size) — mm table 経由の呼出を計数 (逆アセンブル照合済の転記) */
void fle_ov_getmem(void) {
    g_n_getmem++;
    u64 save_rbx = R[3];
    if ((int64_t)R[1] > 0) {
        u64 t_ = LD64(MM_TABLE);
        R[4] -= 8; ST64(R[4], 0x409424ull);
        ott_dispatch(t_);
        u64 p = R[0];
        if (!p) { R[1] = (R[1] & ~0xffull) | 1; R[4] -= 8; ST64(R[4], 0x409433ull); f_409730(); }
        R[3] = save_rbx; R[0] = p;
        return;
    }
    R[3] = save_rbx; R[0] = 0;
}

/* f_409440 = System._FreeMem(p) */
void fle_ov_freemem(void) {
    g_n_freemem++;
    u64 save_rbx = R[3];
    if (R[1]) {
        u64 t_ = LD64(MM_TABLE + 8);
        R[4] -= 8; ST64(R[4], 0x409454ull);
        ott_dispatch(t_);
        u32 ok = R[0] & 0xffffffff;
        if (!ok) { R[1] = (R[1] & ~0xffull) | 2; R[4] -= 8; ST64(R[4], 0x409461ull); f_409730(); }
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
        R[4] -= 8; ST64(R[4], 0x412129ull);   /* 実機の call [rbp+0x38] (0x412126, 3B) の復帰点 */
        R[1] = 0; R[2] = 0; R[8] = 0; R[9] = 0;
        ott_dispatch(proc);
    }
}

/* ---------------- boot / survey 入口 ---------------- */
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
        shimx_cbtrans_set_invoke((shimx_cb_invoke_fn)fle_icall9);
        shimx_cbtrans_install();
        shimx_set_proc_resolver(shimx_lifttab_proc_resolver);
        shimx_set_intptr_limit(0x10000);
        fle_ff_hook = fle_ff;
        fle_dispatch_probe = fle_probe_dispatch;
        g_installed = 1;
        fprintf(stderr, "[fleboot] image + textwin installed, shimx cbtrans/resolver wired\n");
    }
    g_survey = (u32)survey;
    g_units_run = g_units_total = g_units_empty = 0;
    g_n_getmem = g_n_freemem = g_n_longjmp = g_n_exit = 0;
    g_boot_stage = 1;
    /* DllMain(hinst=0, DLL_PROCESS_ATTACH=1, reserved=0) — m11_boot_enter(0,1) と同一条件 */
    fle_run(ENTRY_VA, 0, 1, 0, 0, 0, 0, 0, 0);
    g_boot_stage = 2;
}
