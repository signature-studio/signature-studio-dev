/* M11 lift-fix overrides: RetDec が落とした意味 (間接 call / stack 引数) を逆アセンブルから手修正.
 *
 * RetDec は IR から間接 call を全て落とす (boot closure 7416 fn 中 0 件) ため Delphi RTL 起動部が壊れる:
 *   function_4120c0 (System.InitUnits): unit 初期化ループ全体が脱落 (Count 読出しのみ残る)
 *   function_412160 (System._InitLib):  Reason(第7引数/stack) を取りこぼし 0 固定 → Halt0 に直行,
 *                                       InitTable 表呼出し [rbx+rsi*8] / DllProc 呼出し脱落
 *   function_41d8f0 (System._StartLib): 第5引数 (stack) 欠落 + 上記を呼ぶ
 * ここでは該当関数のみを C に転記 (命令単位で disasm 照合済; weak define を強シンボルで上書き).
 * 他の lifted 関数・データ配置は一切変更しない.
 *
 * アドレス表記: VA_* = 実 VA, LVA = VA - 0x400000 + M11_LB_BASE (wasm linear memory 上の実座標).
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <emscripten.h>
#include <emscripten/stack.h>

typedef unsigned long long u64;
typedef unsigned int u32;
typedef unsigned char u8;

/* LVA = RVA + M11_LB_BASE (-DM11_LB_BASE; 既定 0 = LVA=RVA, #222). R(rva) = RVA 定数 → LVA */
#ifndef M11_LB_BASE
#define M11_LB_BASE 0
#endif
#define R(rva) ((u64)(rva) + (u64)M11_LB_BASE)
#define Q(lva) (*(volatile u64*)(uintptr_t)(lva))
#define D(lva) (*(volatile u32*)(uintptr_t)(lva))
#define B(lva) (*(volatile u8*)(uintptr_t)(lva))

typedef struct { u32 va; void* fn; } m11_disp_ent;
extern const m11_disp_ent m11_disp_tab[];
extern const u32 m11_disp_n;
typedef u64 (*m11_tr_t)(u64, u64, u64, u64, u64, u64, u64, u64);

/* trace 出力 (fprintf) は wasm shadow stack の SP より下を汚す. その残骸は後続 unit の frame で「未初期化 alloca の読み」として読まれ,
 * survey の結果が trace の有無で変わる (#495: unit 134 の function_413870 は rcx/rdx/r8 を未初期化 alloca から読む).
 * 出力の前後で SP 直下 M11_TRACE_SPAN バイトを JS 側 (shadow stack を使わない) で退避/復元し, trace を透過にする.
 * M11_TRACE_ISOLATE=0 で従来 (素の fprintf) に戻る (ネガコン用: trap_triage/negctl_495.sh). */
#ifndef M11_TRACE_ISOLATE
#define M11_TRACE_ISOLATE 1
#endif
#define M11_TRACE_SPAN 8192   /* 下の EM_JS の 8192 と同じ値 */
const int m11_trace_isolate = M11_TRACE_ISOLATE;
EM_JS(void, m11_stk_save, (unsigned sp), {
    Module.m11_stk_saved = HEAPU8.slice(Math.max(0, sp - 8192), sp);
});
EM_JS(void, m11_stk_restore, (unsigned sp), {
    const s = Module.m11_stk_saved, base = sp - s.length;
    if (Module.m11_trace_probe) {   /* 汚れた最深バイトの SP からの距離 (最大値) を記録: M11_TRACE_SPAN が足りているかの実測 */
        let d = 0; for (let i = 0; i < s.length; i++) if (HEAPU8[base + i] !== s[i]) { d = s.length - i; break; }
        if (d > (Module.m11_maxdirty | 0)) Module.m11_maxdirty = d;
    }
    HEAPU8.set(s, base);
});
#if M11_TRACE_ISOLATE
#define M11_TRACE(...) do { unsigned sp_ = (unsigned)emscripten_stack_get_current(); m11_stk_save(sp_); fprintf(stderr, __VA_ARGS__); m11_stk_restore(sp_); } while (0)
#else
#define M11_TRACE(...) fprintf(stderr, __VA_ARGS__)
#endif
#ifndef M11_INSTR_K12
#define M11_INSTR_K12 0   /* 1 = _CopyArray kind 12 (416720) の到達を stderr に出す計測専用 probe. 既定 0 は build 出力に影響しない */
#endif

static int g_trace = 0;
static u64 g_icall_ok = 0, g_icall_miss = 0, g_icall_viaVA = 0;
#define MISS_MAX 256
static u32 g_miss[MISS_MAX];
static u32 g_nmiss_uniq = 0;

extern int m11_trace_flag;
EMSCRIPTEN_KEEPALIVE void m11_set_trace(int v) { g_trace = v; m11_trace_flag = v; }
EMSCRIPTEN_KEEPALIVE int m11_icall_ok(void) { return (int)g_icall_ok; }
EMSCRIPTEN_KEEPALIVE int m11_icall_miss(void) { return (int)g_icall_miss; }
EMSCRIPTEN_KEEPALIVE int m11_icall_miss_uniq(void) { return (int)g_nmiss_uniq; }
EMSCRIPTEN_KEEPALIVE int m11_icall_miss_at(int i) { return (i >= 0 && i < (int)g_nmiss_uniq) ? (int)g_miss[i] : 0; }
EMSCRIPTEN_KEEPALIVE int m11_disp_count(void) { return (int)m11_disp_n; }

/* boot closure 外で C 転記した関数 (m11_disp_tab に無い) を icall から呼べるようにする (#474). 転記本体は下方 */
extern unsigned long long function_40f960(unsigned long long);
extern unsigned long long function_41c160(unsigned long long);
extern unsigned long long function_5c0e70(unsigned long long);
/* 481790 (逆アセンブル #704): rcx = ptr, dl = flag(1 byte) → rax = ptr 幅の戻り値 (u64 で切り捨てなし) */
extern unsigned long long function_481790(void* rcx, unsigned long long dl);
static u64 tr_40f960(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return function_40f960(a0); }
static u64 tr_41c160(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return function_41c160(a0); }
static u64 tr_5c0e70(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return function_5c0e70(a0); }
static u64 tr_ret0(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return 0; }
/* closure 外の既定 IEqualityComparer<pointer-size ordinal> のメソッド (#483): 479b00 Equals = `cmp rdx,r8; sete al`,
 * 479b10 GetHashCode = FNV-1a(&Value, 8, 0x811c9dc5) (475ba0 も closure 外のため直接展開) */
static u64 tr_479b00(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return a1 == a2; }
static u64 ov_getter_478420(u64 info);
static u64 ov_getter_478540(u64 info);
static u64 ov_getter_478c70(u64 info, u64 size);
static u64 tr_478420(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return ov_getter_478420(a0); }
static u64 tr_478540(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return ov_getter_478540(a0); }
static u64 tr_478c70(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return ov_getter_478c70(a0, a1); }
static u64 tr_479b10(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) {
    u32 h = 0x811c9dc5u;
    for (int i = 0; i < 8; i++) h = (h ^ (u32)((a1 >> (8 * i)) & 0xff)) * 0x1000193u;
    return h;
}

#ifndef M11_OV_CLASSCREATE
#define M11_OV_CLASSCREATE 0
#endif
#if M11_OV_CLASSCREATE
/* 41c130  `or eax,-1; lock xadd [rcx+8],eax; ret` = TInterfacedObject.AfterConstruction (FRefCount を 1→0 に戻す。NewInstance 41c160 が 1 にしている)。
 * 410360 ON で [vmt-0x50] 経由の呼出しが現れるが closure 外のため miss (skip) になり FRefCount が 1 のまま残っていた (#595)。戻り値は xadd の旧値 */
static u64 tr_41c130(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) {
    u32 old = *(volatile u32*)(uintptr_t)(a0 + 8); *(volatile u32*)(uintptr_t)(a0 + 8) = old - 1; return old;
}
static u64 tr_9b4b00(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7);
#endif

static m11_tr_t disp_find(u32 va) {
    int lo = 0, hi = (int)m11_disp_n - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        u32 v = m11_disp_tab[mid].va;
        if (v == va) return (m11_tr_t)m11_disp_tab[mid].fn;
        if (v < va) lo = mid + 1; else hi = mid - 1;
    }
    switch (va) {
    case 0x40f960: return tr_40f960;
    case 0x41c160: return tr_41c160;
    case 0x5c0e70: return tr_5c0e70;   /* 5c03d0 の node 差替え通知の実体 (#482) */
    case 0x5c04a0: return tr_ret0;   /* `ret` 1 命令 (キャッシュ node 解放フックの既定実体) */
    case 0x478420: return tr_478420;
    case 0x478540: return tr_478540;
    case 0x478c70: return tr_478c70;
    case 0x479b00: return tr_479b00;
    case 0x479b10: return tr_479b10;
#if M11_OV_CLASSCREATE
    case 0x41c130: return tr_41c130;   /* TInterfacedObject.AfterConstruction (#595) */
    case 0x9b4b00: return tr_9b4b00;   /* ユーザクラス AfterConstruction (closure 外; #704) */
#endif
    }
    return 0;
}

/* ---- 間接 call の入口計測 (常設, #494) ----
 * m11_icall の全呼出しを site (元バイナリの `call` 命令 VA) 別と target (解決先 VA) 別に ok / miss で数える.
 * site は C 転記側が ICALL_AT(va, m11_icall の引数...) で渡す (m11_icall の署名・呼出し経路は不変: shimx_link が --wrap=m11_icall する).
 * ICALL_AT を使わない呼出し (外部 TU) は site = M11_SITE_EXT, survey ドライバは M11_SITE_NONE (数えない).
 * 読出しは m11_icall_cnt_* (survey_units.mjs が unit 前後の差分を JSON の icall 欄に出す). */
#define M11_SITE_NONE 0xffffffffu
#define M11_SITE_EXT 1u
typedef struct { u32 key, ok, miss; } icall_cnt_t;
typedef struct { icall_cnt_t* e; short* h; u32 cap, n; } icall_tab_t;
#define ICALL_SITE_CAP 256
#define ICALL_TGT_CAP 2048
static icall_cnt_t g_isite_e[ICALL_SITE_CAP], g_itgt_e[ICALL_TGT_CAP];
static short g_isite_h[ICALL_SITE_CAP * 2], g_itgt_h[ICALL_TGT_CAP * 2];
static icall_tab_t g_isite = { g_isite_e, g_isite_h, ICALL_SITE_CAP, 0 }, g_itgt = { g_itgt_e, g_itgt_h, ICALL_TGT_CAP, 0 };
static u32 g_icall_drop = 0, g_icall_site = 0;
#define ICALL_AT(site, ...) (g_icall_site = (u32)(site), m11_icall(__VA_ARGS__))
static void icall_bump(icall_tab_t* t, u32 key, int miss) {
    u32 m = t->cap * 2, h = (key * 2654435761u) % m;
    for (short s; (s = t->h[h]) != 0; h = (h + 1) % m)
        if (t->e[s - 1].key == key) { if (miss) t->e[s - 1].miss++; else t->e[s - 1].ok++; return; }
    if (t->n >= t->cap) { g_icall_drop++; return; }
    icall_cnt_t* c = &t->e[t->n];
    c->key = key; c->ok = !miss; c->miss = !!miss;
    t->h[h] = (short)++t->n;
}
static icall_tab_t* icall_tab(int t) { return t ? &g_itgt : &g_isite; }
EMSCRIPTEN_KEEPALIVE int m11_icall_cnt_n(int t) { return (int)icall_tab(t)->n; }
EMSCRIPTEN_KEEPALIVE unsigned m11_icall_cnt_key(int t, int i) { return icall_tab(t)->e[i].key; }
EMSCRIPTEN_KEEPALIVE unsigned m11_icall_cnt_ok(int t, int i) { return icall_tab(t)->e[i].ok; }
EMSCRIPTEN_KEEPALIVE unsigned m11_icall_cnt_miss(int t, int i) { return icall_tab(t)->e[i].miss; }
EMSCRIPTEN_KEEPALIVE int m11_icall_cnt_drop(void) { return (int)g_icall_drop; }

/* 間接 call: target は .data ポインタ表由来 (LVA; reloc 補正済) か lea [rip] 由来の VA. */
u64 m11_icall(u64 target, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) {
    u32 site = g_icall_site ? g_icall_site : M11_SITE_EXT;
    g_icall_site = 0;
    u32 tkey = (u32)(target + (0x400000ull - M11_LB_BASE));
    m11_tr_t f = disp_find(tkey);
    if (!f) {
        f = disp_find((u32)target);
        if (f) { g_icall_viaVA++; tkey = (u32)target; }
    }
    if (site != M11_SITE_NONE) { icall_bump(&g_isite, site, !f); icall_bump(&g_itgt, tkey, !f); }
    if (!f) {
        g_icall_miss++;
        int seen = 0;
        for (u32 i = 0; i < g_nmiss_uniq; i++) if (g_miss[i] == (u32)target) { seen = 1; break; }
        if (!seen && g_nmiss_uniq < MISS_MAX) g_miss[g_nmiss_uniq++] = (u32)target;
        if (g_trace) M11_TRACE("[m11][icall-miss] target=0x%llx (closure 外; skip, ret 0)\n", target);
        return 0;
    }
    g_icall_ok++;
    if (g_trace) M11_TRACE("[m11][icall] 0x%llx\n", target);
    return f(a0, a1, a2, a3, a4, a5, a6, a7);
}

#include "work/boot_final3_sigs.h"   /* IR 署名そのままの extern 宣言 (署名ずれ防止) */

static u32 g_units_run = 0, g_units_total = 0, g_units_skipped = 0;
EMSCRIPTEN_KEEPALIVE int m11_units_run(void) { return (int)g_units_run; }
EMSCRIPTEN_KEEPALIVE int m11_units_total(void) { return (int)g_units_total; }
EMSCRIPTEN_KEEPALIVE int m11_units_skipped(void) { return (int)g_units_skipped; }

/* System.InitUnits  VA 0x4120c0
 *   rax=[InitContext.InitTable @VA 0x15eac90]; Count=*(i32*)rax; Units=*(rax+8) (16B stride; +0=Init, +8=FInit)
 *   for i<Count: InitCount(@VA 0x15eac98)=i+1; proc=Units[i].Init; if (proc && *proc) call proc
 *   (元は *proc の先頭 8B が非0 かを .text 上で読む; wasm には .text が無いので proc!=0 に置換) */
static int g_survey = 0;
EMSCRIPTEN_KEEPALIVE void m11_set_survey(int v) { g_survey = v; }

/* survey 用: unit i の Init を 1 本だけ呼ぶ (JS が try/catch で trap を隔離). 戻り 0=proc 無し 1=実行 2=closure 外(miss) */
EMSCRIPTEN_KEEPALIVE int m11_call_unit(int i) {
    u64 tbl = Q(R(0x11eac90));
    if (!tbl || i < 0 || i >= (int)D(tbl)) return -1;
    u64 proc = Q(Q(tbl + 8) + (u64)i * 16);
    if (!proc) return 0;
    u32 m0 = (u32)g_icall_miss;
    D(R(0x11eac98)) = (u32)(i + 1);
    ICALL_AT(M11_SITE_NONE, proc, 0, 0, 0, 0, 0, 0, 0, 0);
    return (u32)g_icall_miss != m0 ? 2 : 1;
}
EMSCRIPTEN_KEEPALIVE unsigned m11_unit_va(int i) {
    u64 tbl = Q(R(0x11eac90));
    if (!tbl || i < 0 || i >= (int)D(tbl)) return 0;
    return (unsigned)Q(Q(tbl + 8) + (u64)i * 16);
}

u64 function_4120c0(void) {
    u64 tbl = Q(R(0x11eac90));
    if (g_survey) { g_units_total = tbl ? D(tbl) : 0; return 0; }
    if (g_trace) M11_TRACE("[m11][InitUnits] InitTable=0x%llx\n", tbl);
    if (!tbl) return 0;
    int count = (int)D(tbl);
    u64 units = Q(tbl + 8);
    g_units_total = (u32)count;
    int i = 0;
    while (i < count) {
        u64 proc = Q(units + (u64)i * 16);
        i++;
        D(R(0x11eac98)) = (u32)i;
        if (!proc) continue;
        u32 miss0 = (u32)g_icall_miss;
        if (g_trace) M11_TRACE("[m11][unit %d/%d] init=0x%llx\n", i, count, proc);
        ICALL_AT(0x412126, proc, 0, 0, 0, 0, 0, 0, 0, 0);
        if ((u32)g_icall_miss != miss0) g_units_skipped++;
        else g_units_run++;
    }
    return (u64)i;
}

/* System._InitLib  VA 0x412160
 *   args: rcx=Context rdx=a1 r8=a2 r9=InitTable(hook 表: [reason] を call) [stk5]=DllProc [stk6]=hInst [stk7]=Reason [stk8]=Reserved */
u64 m11_InitLib(u64 ctx, u64 a1, u64 a2, u64 tbl, u64 dllproc, u64 hinst, u64 reason64, u64 reserved) {
    u32 reason = (u32)reason64;
    if (g_trace) M11_TRACE("[m11][InitLib] ctx=0x%llx a1=0x%llx a2=0x%llx tbl=0x%llx dllproc=0x%llx hinst=0x%llx reason=%u reserved=0x%llx\n", ctx, a1, a2, tbl, dllproc, hinst, reason, reserved);
    u64 r13 = R(reason < 2 ? 0x11eac80 : 0x11eada8);
    u64 tmp[30];
    memcpy(tmp, (void*)(uintptr_t)(ctx + 0x38), 240);
    memcpy((void*)(uintptr_t)ctx, (void*)(uintptr_t)r13, 296);
    memcpy((void*)(uintptr_t)(r13 + 0x38), tmp, 240);
    Q(r13 + 0x10) = a1;
    Q(r13 + 0x20) = a2;
    Q(r13) = ctx;
    D(r13 + 0x34) = (u32)function_406f90();
    if (reason == 0) D(r13 + 0x18) = D(Q(r13 + 0x10)); else D(r13 + 0x18) = 0;
    Q(R(0x11e6030)) = 0x406fd0;
    Q(R(0x11e6038)) = 0x406fe0;
    Q(r13 + 8) = 1;
    B(r13 + 0x30) = (u8)(reason + 1);
    Q(r13 + 0x28) = Q(tbl);
    if (reason == 1 || reason == 2) ICALL_AT(0x41223e, Q(tbl + (u64)reason * 8), reason, 0, 0, 0, 0, 0, 0, 0);
    if (dllproc) ICALL_AT(0x412258, dllproc, reason, reserved, 0, 0, 0, 0, 0, 0);
    if (reason == 3) ICALL_AT(0x41226d, Q(tbl + (u64)reason * 8), reason, 0, 0, 0, 0, 0, 0, 0);
    if (Q(R(0x11e6078)) == 0) {
        B(R(0x11e6084)) = 1;
        D(R(0xfa5054)) = (u32)function_40a3b0();
    }
    if (reason == 1) return function_4120c0();
    return function_4128b0();
}

/* RetDec 版 5 引数署名を保つ (IR 側の呼び出しは触らない): 実引数は function_41d8f0 から直接 m11_InitLib へ */
unsigned long long function_412160(unsigned long long a, unsigned long long b, void* c, void* d, unsigned long long e) {
    fprintf(stderr, "[m11][ov] function_412160 (lifted 5-arg 版) は未使用のはず\n");
    abort();
}

/* System._StartLib  VA 0x41d8f0   (rcx=Context rdx=PackageInfo r8=hInst r9d=Reason [stk]=Reserved) */
u64 function_41d8f0(u64 rcx, u64 rdx, u64 r8, u64 r9, u64 reserved) {
    u32 reason = (u32)r9;
    if (reason == 1) {
        B(R(0x11ec290)) = 1;
        B(R(0x11ec2d8)) = 1;
        Q(R(0x11ec298)) = r8;
        Q(R(0xfa93b8)) = r8;
        Q(R(0xfa93c0)) = 0;
        Q(R(0xfa93c8)) = 0;
        Q(R(0xfa93d8)) = rdx + 0x10;
        function_41d170();
    }
    return m11_InitLib(rcx, rdx, R(0xfa93b0), R(0xfa9410), Q(R(0x11ec2a8)), r8, reason, reserved);
}

/* function_412510  VA 0x412510  (Delphi RTL: 再配置表の適用)
 * RetDec は `mov r8d,[rcx]` (Count 読出し) を `mov r8d,ecx` 相当に誤 lift した (Count=ポインタ下位32bit → 巨大ループ/OOB).
 *   table: { i32 Count; ...; entries[i] @ table + 24*i - 16 (i=1..Count): { u64* dest; u64* srcptr; u64 off } }
 *   for each: *dest = *srcptr + off */
unsigned long long function_412510(void* tbl) {
    u64 t = (u64)(uintptr_t)tbl;
    int count = (int)D(t);
    for (int i = 1; i <= count; i++) {
        u64 e = t + 24ull * (u64)i - 16ull;
        u64 dest = Q(e), srcp = Q(e + 8), off = Q(e + 16);
        Q(dest) = Q(srcp) + off;
    }
    return 0;
}

/* function_4133f0  VA 0x4133f0  (System._UStrAsg(dest: PPointer, src: Pointer))
 * RetDec は `mov rax,[rbx]; mov [rbx],rsi` の旧値読出しを落とし (store→load 転送を逆順に誤適用), 旧文字列の解放判定が壊れた.
 *   src != nil: refcnt(src-8) < 0 (literal) → NewUStr(len) + Move(src,dst,len*2) / else refcnt++
 *   old=*dest; *dest=src; old!=nil && refcnt(old-8)>0 → --refcnt==0 なら 0x409440(old-0x10) (FreeMem) */
unsigned long long function_4133f0(unsigned long long dest, unsigned long long src) {
    u64 s = src;
    if (g_trace) M11_TRACE("[m11][UStrAsg] dest=0x%llx src=0x%llx old=0x%llx\n", dest, src, Q(dest));
    if (s) {
        if ((int)D(s - 8) < 0) {
            u32 len = D(s - 4);
            s = function_412c20(len);
            function_409c80(src, s, (unsigned long long)(long long)(int)(len * 2u));
        } else {
            D(s - 8) = D(s - 8) + 1;
        }
    }
    u64 old = Q(dest);
    Q(dest) = s;
    if (old) {
        u64 hdr = old - 0x10;
        int rc = (int)D(hdr + 8);
        if (rc > 0) {
            D(hdr + 8) = (u32)(rc - 1);
            if (rc - 1 == 0) function_409440(hdr);
        }
    }
    return 0;
}

/* function_412d60  VA 0x412d60  (System._UStrClr(dest: PPointer))
 * RetDec は `mov rax,[rbx]` (旧値の読出し) を落とし, dest のアドレス自体を文字列ポインタとして refcnt を触った (4133f0 と同型).
 *   old=*dest; old!=nil → *dest=0; refcnt(old-8)>0 → --refcnt==0 なら 0x409440(old-0x10) (FreeMem). 戻り値 = dest */
unsigned long long function_412d60(unsigned long long dest, unsigned long long unused) {
    (void)unused;
    u64 old = Q(dest);
    if (old) {
        u64 hdr = old - 0x10;
        Q(dest) = 0;
        int rc = (int)D(hdr + 8);
        if (rc > 0) {
            D(hdr + 8) = (u32)(rc - 1);
            if (rc - 1 == 0) function_409440(hdr);
        }
    }
    return dest;
}

/* function_418190  VA 0x418190  (System._LStrArrayClr/_DynArrayClear 系: dest=PPointer, rdx=type info)
 * 同上: `mov rsi,[rbx]` の旧値読出しが落ちている. refcnt は old-0xc (int32), length は old-8.
 *   old=*dest; old!=nil → *dest=0; refcnt(old-0xc)>0 → --refcnt==0 なら
 *   elem=Q(ti+6+B(ti+1)) があり len=Q(old-8)!=0 なら 0x416230(old, Q(elem), len) (要素 finalize) → 0x409440(old-0x10). 戻り値 = dest */
unsigned long long function_418190(unsigned long long dest, unsigned long long ti, unsigned long long unused) {
    (void)unused;
    u64 old = Q(dest);
    if (old) {
        Q(dest) = 0;
        int rc = (int)D(old - 0xc);
        if (rc > 0) {
            D(old - 0xc) = (u32)(rc - 1);
            if (rc - 1 == 0) {
                u64 elem = Q(ti + 6 + (u64)B(ti + 1));
                if (elem) {
                    u64 len = Q(old - 8);
                    if (len) function_416230(old, Q(elem), (unsigned int)len);
                }
                function_409440(old - 0x10);
            }
        }
    }
    return dest;
}

/* function_412770  VA 0x412770  (System: InitContext 復元 + longjmp(setjmp 点=entry_point 内) )
 * 実機では戻らない (DllMain の setjmp が eax=1 で再返却 → DllMain は TRUE を返す).
 * lift 版は longjmp を表現できず, 通常 return して Halt0 が ExitProcess まで進んでしまう (実測).
 * wasm では JS 例外で呼出しスタックを巻き戻し, ハーネスが「DllMain attach 完走」と判定する. */
EM_JS(void, m11_throw_dllmain_done, (int code), { throw { m11_dllmain_done: code, stack: new Error().stack }; });
static int g_longjmp_hit = 0;
EMSCRIPTEN_KEEPALIVE int m11_longjmp_hit(void) { return g_longjmp_hit; }
unsigned long long function_412770(void* ctx) {
    g_longjmp_hit++;
    if (g_trace) M11_TRACE("[m11][longjmp] Halt0 -> RestoreContext(ctx=%p): DllMain attach 完走として JS 例外で巻き戻す\n", ctx);
    m11_throw_dllmain_done(1);
    return 0;
}

/* function_450560  VA 0x450560  (SysUtils: 文字列の LCMapStringW 変換; dest := src; dest を一意化し src→dest へ LCMapString)
 * RetDec は `mov [rsp+0x60],rcx ... mov rax,[rsp+0x60]; mov rdx,[rax]` (スピルしたポインタ経由の 2 段 deref) の
 * 1 段を落とし, UStrAsg(dest, dest) / 引数に dest を渡す形に誤 lift した (stack アドレスが文字列値として流れ OOB の根因). */
extern int LCMapStringW(unsigned, unsigned, const void*, int, void*, int);
unsigned long long function_450560(unsigned long long src, unsigned long long dest, unsigned loc) {
    function_4133f0(dest, Q(src));
    if (Q(dest) != 0) {
        function_413780(dest);
        int ns = Q(src) ? (int)D(Q(src) - 4) : 0;
        int nd = Q(dest) ? (int)D(Q(dest) - 4) : 0;
        unsigned long long ps = function_414850(Q(src));
        unsigned long long pd = function_414850(Q(dest));
        int r = LCMapStringW(loc, 0x1000100u, (const void*)(uintptr_t)ps, ns, (void*)(uintptr_t)pd, nd);
        if (r == 0) function_44cb40(0, 0);
    }
    return dest;
}

/* function_40fac0  VA 0x40fac0  (TObject.InitInstance の入れ子手続き: 親チェーンの tkMRecord InitTable を再帰処理)
 * 逆アセンブル転記. 引数 rcx = 親フレーム (未使用), rdx = クラス, r8 = インスタンス.
 * クラス → 親クラスへ [vmt-0xb0] (InitTable) を辿り, 種別 0x16 (tkMRecord) の RecOps[0] が奇数なら 417150(inst, typeinfo) を呼ぶ.
 * 40fb40 と同じく boot closure 外 (IR に関数が無い). */
static void ov_initinst_nested(u64 cls, u64 inst) {
    u64 ti, p;
    for (;;) {
        ti = Q(cls - 0xb0);
        p = Q(cls - 0x78);
        if (p) p = Q(p);
        if (!p) break;
        if (!ti || B(ti) != 0x16) { cls = p; continue; }
        ov_initinst_nested(p, inst);
        break;
    }
    if (ti && B(ti) == 0x16) {
        u64 n = ti + B(ti + 1);
        u64 ops = n + 0xa + ((u64)D(n + 6) << 4);
        if (B(ops) > 0) {
            u64 op0 = Q(ops + 1);
            if (op0 & 1) function_417150(inst, ti);
        }
    }
}

/* function_40fb40  VA 0x40fb40  (System.TObject.InitInstance(Self: TClass; Instance: Pointer): TObject)
 * 410320 (_ClassCreate) が vmtNewInstance 既定実体 40f960 経由で呼ぶ. boot closure 外 (IR に関数が無い) ため C で補う (#474).
 *   FillChar(Instance^, InstanceSize [self-0x80], 0); PPointer(Instance)^ := Self;
 *   クラス → 親クラス ([vmt-0x78] を 1 段 deref) を辿り, 各クラスの IntfTable [vmt-0xc0] (EntryCount dword + 40B entry,
 *   +0x10 VTable / +0x18 IOffset) の VTable != nil を Instance[IOffset] に書く. 途中で InitTable [vmt-0xb0] が tkMRecord (0x16) なら
 *   最後に入れ子手続き (40fac0) を呼ぶ. 戻りは Instance. */
u64 function_40fb40(u64 self, u64 inst) {
    int flag = 0;
    u64 cls = self;
    memset((void*)(uintptr_t)inst, 0, (size_t)(long long)(int)D(self - 0x80));
    Q(inst) = self;
    do {
        u64 it = Q(cls - 0xc0);
        if (it) {
            int cnt = (int)D(it);
            for (int i = 0; i < cnt; i++) {
                u64 ent = it + (u64)(long long)i * 40 + 8;
                u64 vt = Q(ent + 0x10);
                if (vt) Q(inst + (u64)(long long)(int)D(ent + 0x18)) = vt;
            }
        }
        u64 ti = Q(cls - 0xb0);
        if (ti && B(ti) == 0x16) flag = 1;
        cls = Q(cls - 0x78);
        if (cls) cls = Q(cls);
    } while (cls);
    if (flag) ov_initinst_nested(self, inst);
    return inst;
}

/* function_40f960  VA 0x40f960  (System.TObject.NewInstance = vmtNewInstance 既定実体): GetMem(InstanceSize) → InitInstance */
u64 function_40f960(u64 self) {
    u64 obj = function_409410((unsigned)(int)D(self - 0x80));
    return function_40fb40(self, obj);
}

/* function_41c160  VA 0x41c160  (System.TInterfacedObject.NewInstance): `call 40f960; mov dword [rax+8],1; ret` (FRefCount := 1) */
u64 function_41c160(u64 self) {
    u64 obj = function_40f960(self);
    D(obj + 8) = 1;
    return obj;
}

/* function_410320  VA 0x410320  (System._ClassCreate(self: TClass; alloc: ShortInt): TObject)
 * 逆アセンブル: `test dl,dl; jl skip; mov rcx,rax; call [rax-0x30]` (= VMT vmtNewInstance). RetDec は間接 call を落とし
 * `ret arg1` にしたため, 494 call site 全てで「生成したオブジェクト」が TClass (VMT, .text 上) 自身になっていた (#418).
 * vmtNewInstance の実体は m11_icall (disp 表 + C 転記の追加表) 経由で呼ぶ: 既定 40f960 / TInterfacedObject 41c160 は下記 C 転記.
 * alloc < 0 (継承 ctor 経由) は従来どおり self をそのまま返す. */
unsigned long long function_410320(unsigned long long self, unsigned int alloc) {
    if ((signed char)(alloc & 0xff) < 0) return self;
    return ICALL_AT(0x41032e, Q(self - 0x30), self, 0, 0, 0, 0, 0, 0, 0);
}

/* function_47b260  VA 0x47b260  (TList 系 Add: rcx = リスト (rbx), rdx = 追加する値の番地 (rsi); 戻り = 旧 Count)
 * 逆アセンブル: rdi = [rbx+8] (Count); rax = [rbx] (FItems); cap = [rax-8] (rax≠0); Count = cap なら 47a3e0(rbx, Count+1);
 *   [rax+rdi*8] = [rsi]; [rbx+8] += 1; [rbx+0x20] ≠ 0 なら call [rbx+0x20](rcx=[rbx+0x18], rdx=rsi, r8b=1).
 * RetDec は `mov rax,[rbx]` と `mov rcx,[rsi]` の disp=0 deref を 2 点とも落とし, 項目番地を rbx+8*Count (= FItems 欄そのもの)
 * にして値として rsi (番地) を書いた (DEFECTS D4, #682). 4f9f10 (25 call site の Add 呼出し) から FItems に stack 番地が入る.
 * notify (`call [rbx+0x20]`, D15) は既定で省略 (M11_NOTIFY_682=1 で有効化。呼出し先 0x535cf0/0x536570 等が closure 外 → miss 化するため。REPORT_682 §7). */
#ifndef M11_FIX_682
#define M11_FIX_682 1
#endif
#ifndef M11_NOTIFY_682
#define M11_NOTIFY_682 0
#endif
#if M11_FIX_682
u64 function_47b260(u64 self, void* src, u64 unused) {
    u64 s = (u64)(uintptr_t)src;
    u64 cnt = Q(self + 8);
    u64 items = Q(self);
    u64 cap = items ? Q(items - 8) : 0;
    if (cnt == cap) function_47a3e0(self, cnt + 1);
    items = Q(self);
    Q(items + cnt * 8) = Q(s);
    Q(self + 8) = cnt + 1;
#if M11_NOTIFY_682
    if (Q(self + 0x20)) ICALL_AT(0x47b2ae, Q(self + 0x20), Q(self + 0x18), s, 1, 0, 0, 0, 0, 0);
#endif
    return cnt;
}
#endif

/* function_535bf2 / function_535c11  VA 0x535bf2 / 0x535c11  (rcx = self; 24B 要素の配列を走査し dword = -1 で空と判定)
 * 逆アセンブル: 535bf0 = jmp 535c11.
 *   535c11: items = [[self+8]+8]; bound = (items ? [items-8] : 0) - 1; [self+0x10] < bound (signed) なら 535bf2, 否なら 0 を返す.
 *   535bf2: [self+0x10] += 1; dword items[idx*24] ≠ -1 なら (items & ~0xff) | 1 を返す (al=1), = -1 なら 535c11 へ.
 * RetDec は 535bf2 末尾の `ret` (VA 0x535c2e) を未定義の function_535c2e への call にし, 535c11 の jl 先 535bf2 を rcx=0 の call にした (#714).
 * 同じ分岐を C で書き、closure 外参照を転記で消す (seed 追加では解けないため). */
#ifndef M11_FIX_535BF2
#define M11_FIX_535BF2 0
#endif
#if M11_FIX_535BF2
u64 function_535c11(u64 self) {
    for (;;) {
        u64 items = Q(Q(self + 8) + 8);
        long long bound = (long long)(items ? Q(items - 8) : 0) - 1;
        if (!((long long)Q(self + 0x10) < bound)) return 0;
        Q(self + 0x10) += 1;
        items = Q(Q(self + 8) + 8);
        if (*(volatile u32*)(uintptr_t)(items + Q(self + 0x10) * 24) != 0xffffffffu) return (items & ~0xffULL) | 1;
    }
}
u64 function_535bf2(u64 self) {
    u64 items;
    Q(self + 0x10) += 1;
    items = Q(Q(self + 8) + 8);
    if (*(volatile u32*)(uintptr_t)(items + Q(self + 0x10) * 24) != 0xffffffffu) return (items & ~0xffULL) | 1;
    return function_535c11(self);
}
#endif

/* function_5c0270  VA 0x5c0270  (参照カウント付きキャッシュ node の Release: self = キャッシュ, node = function_5c00e0 の戻り)
 * 逆アセンブル転記 (5c0270..5c0392). node = {+0 next, +8 refcount(dword), +0xc 第 1 qword キー, +0x14 hash(word), +0x18 tid(dword), +0x1c payload}.
 * RetDec は 3 点を落とした (#474):
 *   head 一致時  `mov rcx,[node]; mov [self+8],rcx` の [node] (D4: disp=0 の deref 脱落) → head := node 自身
 *   前任走査後   同じく `mov rcx,[node]; mov [prev],rcx` → prev.next := node 自身 (解放後の node を指したまま = 後で同じ番地が再配分されると循環)
 *   末尾         `call [ [self] ]` (vmt slot 0, D15: 間接 call 脱落) */
u64 function_5c0270(u64 self, u64 node) {
    if (!node) return 0;
    function_4232e0((void*)(uintptr_t)(self + 0x10));
    D(node + 8) = D(node + 8) - 1;
    int zero = D(node + 8) == 0;
    if (zero) {
        u64 head = Q(self + 8);
        if (node == head) {
            Q(self + 8) = Q(node);
        } else {
            u64 prev = head, nx = head ? Q(head) : 0;
            while (nx && nx != node) { prev = nx; nx = Q(prev); }
            if (nx) Q(prev) = Q(node);
        }
    }
    function_423980((void*)(uintptr_t)(self + 0x10));
    if (zero) {
        u64 key = Q(node + 0xc);
        if (key) function_424090((void*)(uintptr_t)key);
        ICALL_AT(0x5c037e, Q(Q(self)), self, node, 0, 0, 0, 0, 0, 0);
        function_409440(node);
    }
    return 0;
}

/* function_5c03d0  VA 0x5c03d0  (参照カウント付きキャッシュ node の差替え: self = キャッシュ, obj = node を +0x18 に持つ所有オブジェクト, key = 検索キー)
 * 逆アセンブル転記 (5c03d0..5c0463; 5c0470.. は finally 用ハンドラ). 5c0270 / 5c00e0 の呼出し元.
 *   Lock(self+0x10); old := obj[+0x18]; node := 5c00e0(self, key); obj[+0x18] := node;
 *   if node <> old then obj.vmt[+0x18](obj)   -- 5c0437 `call [rbx+0x18]` (rcx = obj, rbx = [obj]); node 差替え通知
 *   5c0270(self, old); Unlock(self+0x10)
 * RetDec は `cmp rax,[old]; je` ごと `call [rbx+0x18]` を落とした (D15, #482): IR は 5c00e0 → 格納 → 5c0270 を無条件に直列化するだけ.
 * 通知先は obj の VMT スロット (+0x18) をそのまま m11_icall で解決する (closure 外なら miss = skip, ret 0). */
u64 function_5c03d0(u64 self, u64 obj, u64 key) {
    function_4232e0((void*)(uintptr_t)(self + 0x10));
    u64 old = Q(obj + 0x18);
    u64 node = function_5c00e0(self, key);
    Q(obj + 0x18) = node;
    if (node != old) ICALL_AT(0x5c0437, Q(Q(obj) + 0x18), obj, 0, 0, 0, 0, 0, 0, 0);
    function_5c0270(self, old);
    function_423980((void*)(uintptr_t)(self + 0x10));
    return 0;
}

/* function_5c0810  VA 0x5c0810  (DoChange: `if FOnChange.Code <> nil then FOnChange(Self)`; self = +8 Code / +0x10 Data の通知イベントを持つオブジェクト)
 * 逆アセンブル転記 (5c0810..5c082e): `cmp [rbx+8],0; je; mov rcx,[rbx+0x10]; mov rdx,rbx; call [rbx+8]`. boot closure 外 (IR に関数が無い). */
u64 function_5c0810(u64 self) {
    u64 code = Q(self + 8);
    if (code) ICALL_AT(0x5c0826, code, Q(self + 0x10), self, 0, 0, 0, 0, 0, 0);
    return 0;
}

/* function_5c0e70  VA 0x5c0e70  (5c03d0 の通知先 = obj の VMT スロット +0x18 の実体 (Changed): DoChange → 所有者があればその Changed)
 * 逆アセンブル転記 (5c0e70..5c0e99): `call 5c0810; cmp [rbx+0x30],0; je; mov rax,[rbx+0x30]; mov rcx,rax; mov rbx,[rax]; call [rbx+0x18]`.
 * boot closure 外 (vtable 経由でしか到達しない). 所有者の Changed は m11_icall で解決する (closure 外なら miss = skip, #482). */
u64 function_5c0e70(u64 self) {
    function_5c0810(self);
    u64 owner = Q(self + 0x30);
    if (owner) ICALL_AT(0x5c0e91, Q(Q(owner) + 0x18), owner, 0, 0, 0, 0, 0, 0, 0);
    return 0;
}

/* function_409470  VA 0x409470  (System.ReallocMem(var P: Pointer; NewSize: NativeInt): Pointer)
 * 逆アセンブル (boot0.drc.dsm 409470..4094e6) から転記. RetDec は `cmp [rbx],0` / `mov rcx,[rbx]` の 1 段 deref (*P) を落とし,
 * P 自体 (変数のアドレス) を旧ブロックとして扱った (#418). */
unsigned long long function_409470(void* pv, unsigned long long newsize) {
    u64 pp = (u64)(uintptr_t)pv;
    u64 rsi;
    if (Q(pp) != 0) {
        if ((long long)newsize > 0) {
            rsi = function_408040(Q(pp), newsize);
            if (rsi == 0) function_409730(1);
        } else {
            if ((unsigned)function_407e20(Q(pp)) != 0) function_409730(2);
            rsi = 0;
        }
        Q(pp) = rsi;
    } else {
        if ((long long)newsize <= 0) return 0;
        rsi = function_407a50(newsize);
        if (rsi == 0) function_409730(1);
        Q(pp) = rsi;
    }
    return rsi;
}

#ifndef M11_OV_414AD0
#define M11_OV_414AD0 0
#endif
#if M11_OV_414AD0
/* function_414ad0  VA 0x414ad0  (System._UStrSetLength(var s: UnicodeString; newLen: Integer)) (#683)
 * RetDec は var 引数 s の 1 段 deref `mov rax,[rbx]` (rbx = rcx = &s) を 4 箇所 (414af3/414b49/414b64/414b78) とも落とし,
 * &s (arg1) を文字列本体として扱った. 結果 `[arg2-4]` を読んで OOB (unit 149/158/280/659; #307 §9 と同一欠陥).
 * 逆アセンブル (414ad0..414ba9) から転記. 文字列ヘッダ: data-8=refcnt, data-4=length, data-16=確保ブロック先頭.
 * 414850(p) は p!=0 なら p をそのまま返す. 戻り値は機械語の rax. */
u64 function_414ad0(u64 arg1, u64 arg2) {
    u32 esi = (u32)arg2;
    if ((int)esi <= 0) return function_412d60(arg1, arg2);
    u64 p = Q(arg1);
    if (p && D(p - 8) == 1) {
        if (D(p - 4) == esi) return p;
        u64 slot = p - 0x10;
        long long r13 = (long long)(int)esi;
        function_409470((void*)(uintptr_t)&slot, (u64)(r13 * 2 + 18));
        D(slot + 0xc) = esi;
        Q(arg1) = slot + 0x10;
        u64 r = function_414850(Q(arg1));
        *(volatile unsigned short*)(uintptr_t)(r + (u64)(r13 * 2)) = 0;
        return r;
    }
    u64 rdi = function_412c20(esi);
    if (p == 0) { Q(arg1) = rdi; return 0; }
    u32 r13 = D(p - 4);
    if ((int)r13 > (int)esi) r13 = esi;
    u64 src = function_414850(p);
    function_409c80(src, rdi, (u64)(long long)(int)(r13 * 2u));
    u64 ret = function_412d60(arg1, rdi);
    Q(arg1) = rdi;
    return ret;
}
#else
/* function_414ad0  VA 0x414ad0  (System._LStrSetLength(var s: AnsiString; newLen: Integer))
 * 逆アセンブル (block00031_PE.bin 0x414ad0..0x414ba9) から転記. rcx = &s (var 引数). 先頭で mov rax,[rbx] の 1 段 deref を要する.
 * RetDec IR は rcx を文字列ポインタとして扱い, その deref を落とした (DEFECTS.md D4 型). 結果 realloc・長さ書込み・NUL 終端が
 * スタックアドレスに対して働き, unit #23 (0x467f00) の IntToStr 表構築 (467c40 → 43a7e0 → 43a3f0) で OOB になった. */
unsigned long long function_414ad0(unsigned long long s, unsigned long long newlen) {
    int n = (int)(u32)newlen;
    u64 p, tmp, rdi;
    if (n <= 0) {
        function_412d60(s, 0);
        return 0;
    }
    p = Q(s);
    if (p != 0 && D(p - 8) == 1) {
        if (D(p - 4) == (u32)n) return 0;
        tmp = p - 16;
        u64 sz = (u64)(long long)(n + 1) * 2 + 16;
        if ((long long)sz <= 0) function_40f560(s, 0);
        function_409470((void*)(uintptr_t)&tmp, sz);
        D(tmp + 0xc) = (u32)n;
        Q(s) = tmp + 0x10;
        u64 pc = function_414850(Q(s));
        *(unsigned short*)(uintptr_t)(pc + (u64)(long long)n * 2) = 0;
        return 0;
    }
    rdi = function_412c20((u64)(u32)n);
    p = Q(s);
    if (p != 0) {
        int m = (int)D(p - 4);
        if (m > n) m = n;
        u64 pc = function_414850(Q(s));
        function_409c80(pc, rdi, (u64)(long long)(m * 2));
        function_412d60(s, 0);
    }
    Q(s) = rdi;
    return 0;
}
#endif /* M11_OV_414AD0 */

#ifndef M11_FIX_652500
#define M11_FIX_652500 0
#endif
#if M11_FIX_652500
/* function_652500  VA 0x652500  (rcx = arg1 = &s; 文字列ポインタ *arg1 を読んで 414ec0/414e70/414bb0 に渡す; #748)
 * 逆アセンブル (64bit, block00031_PE.bin 0x652500..0x65257c) から転記. 定数 0x6525a4 (rip 相対) = R(0x2525a4).
 * 機械語: if (*arg1 == 0) goto ret; p = *arg1; len = p ? [p-4] : 0; 414ec0(&slot, p, len, 1);
 *         if (414e70(slot, C) != 0) 414bb0(arg1, C); ret: 412d60(&slot, unused).
 * RetDec IR は *arg1 の 1 段 deref を落とし ([arg1-4] を読み, &slot を p として渡した). 欠陥類型は D4 と同一. */
u64 function_652500(void* arg1_p) {
    u64 arg1 = (u64)(uintptr_t)arg1_p;
    u64 slot = 0;
    u64 c = R(0x2525a4);
    if (Q(arg1) != 0) {
        u64 p = Q(arg1);
        u32 len = D(p - 4);
        function_414ec0((void*)(uintptr_t)&slot, p, len, 1);
        if ((u32)function_414e70(slot, c) != 0) function_414bb0(arg1, c);
    }
    return function_412d60((u64)(uintptr_t)&slot, 0);
}
#endif /* M11_FIX_652500 */

/* function_43a3f0  VA 0x43a3f0  (System: 整数 → 10 進文字列の書込み; 符号 '-' 任意)
 * 逆アセンブル (0x43a3f0..0x43a4ea) から転記. rcx = &s (var string), edx = 絶対値 (u32), r8b = 負符号フラグ.
 * 414ad0 で桁数+符号ぶん確保した後, `mov r8,[rbx]` (= *s) の 1 段 deref を RetDec IR が落とし, r8 = &s として '-' と桁を書いた (DEFECTS.md D4 型).
 * その結果 a[0] 自身 (= 文字列変数) が文字列の中身で上書きされ, 467c40 の IntToStr 表構築で次の反復に OOB となった. */
unsigned long long function_43a3f0(unsigned long long s, unsigned long long value, unsigned long long sign) {
    u32 v = (u32)value;
    u8 sb = (u8)sign;
    int nd;
    if (v < 10000u) nd = v < 100u ? 1 + (v >= 10u) : 3 + (v >= 1000u);
    else if (v < 1000000u) nd = 5 + (v >= 100000u);
    else if (v < 100000000u) nd = 7 + (v >= 10000000u);
    else nd = 9 + (v >= 1000000000u);
    function_414ad0(s, (u64)(u32)(nd + sb));
    u64 r8 = Q(s);
    *(unsigned short*)(uintptr_t)r8 = 0x2d;
    r8 += (u64)(long long)(signed char)sb * 2;
    while (nd > 1) {
        u32 q = v / 100u;
        u32 rem = v - q * 100u;
        nd -= 2;
        u32 pair = (u32)('0' + rem / 10u) | ((u32)('0' + rem % 10u) << 16);
        *(u32*)(uintptr_t)(r8 + (u64)(long long)nd * 2) = pair;
        v = q;
    }
    if (nd != 0) *(unsigned short*)(uintptr_t)r8 = (unsigned short)(v | 0x30u);
    return s;
}

/* function_417b70  VA 0x417b70  (System.DynArraySetLength(var a: Pointer; ti: PDynArrayTypeInfo; dimCnt: NativeInt; lengths: PNativeInt))
 * RetDec は `mov rax,[rbp+0xb0]; mov rax,[rax]` (= *a) と `mov rax,[rbp+0xc8]; mov rax,[rax]` (= *lengths) の
 * 1 段 deref を 2 箇所とも落とし, lengths (スタックアドレス) を配列長, a を配列本体として扱った.
 * → GetMem に巨大サイズが渡り 0 を返して Error(reOutOfMemory) → Halt0 (survey halt0 の 17 unit 直接原因, #130).
 * 逆アセンブル (417b70..417fa2) から転記. 動的配列ヘッダ: hdr = data-16, [hdr+4]=refcnt, [hdr+8]=length. */
#if M11_ENTRY_PROBE
extern volatile int m11_fe_417b70;
#endif
unsigned long long function_417b70(unsigned long long a, unsigned long long ti, unsigned long long dimcnt, unsigned long long lengths) {
#if M11_ENTRY_PROBE
    m11_fe_417b70 = 1;
#endif
    u64 p = Q(a);
    u64 len = Q(lengths);
    if ((long long)len <= 0) {
        if ((long long)len < 0) function_409730(4);
        function_418190(a, ti, 0);
        return 0;
    }
    u64 oldlen = 0, hdr = p;
    if (p) { hdr = p - 0x10; oldlen = Q(hdr + 8); }
    u64 nm = ti + B(ti + 1);
    long long elsz = (long long)(int)D(nm + 2);
    u64 elp = Q(nm + 6);
    u64 elt = elp ? Q(elp) : 0;
    long long sz = (long long)len * elsz;
    if (sz / (long long)len != elsz) function_409730(4);
    sz += 0x10;
    if (sz < 0) function_409730(4);
    u64 nkeep = oldlen < len ? oldlen : len;   /* min(oldlen, len) */
    u64 nh;
    if (hdr == 0 || D(hdr + 4) == 1) {
        nh = hdr;
        if (elt) {
            if (function_417b10(elt) & 0xff) {
                nh = function_409410((unsigned)sz);
                function_40d210((void*)(uintptr_t)(nh + 0x10), nkeep * (u64)elsz, 0, 0);
                if (hdr) {
                    function_416f80(nh + 0x10, hdr + 0x10, elt, (unsigned)nkeep);
                    if ((long long)len < (long long)oldlen) function_417130(hdr + 0x10 + len * (u64)elsz, elt, oldlen - len);
                    function_409440(hdr);
                }
            } else {
                if ((long long)len < (long long)oldlen) function_417130(hdr + 0x10 + len * (u64)elsz, elt, oldlen - len);
                function_409470((void*)(uintptr_t)&nh, (unsigned long long)sz);
            }
        } else {
            function_409470((void*)(uintptr_t)&nh, (unsigned long long)sz);
        }
    } else {
        nh = function_409410((unsigned)sz);
        if (elt) {
            function_40d210((void*)(uintptr_t)(nh + 0x10), nkeep * (u64)elsz, 0, 0);
            function_416db0(nh + 0x10, p, elt, (unsigned)nkeep);
        } else {
            function_409c80(p, nh + 0x10, nkeep * (u64)elsz);
        }
        function_418190(a, ti, 0);
    }
    D(nh + 4) = 1;
    Q(nh + 8) = len;
    u64 data = nh + 0x10;
    if ((long long)len > (long long)oldlen) {
        function_40d210((void*)(uintptr_t)(data + oldlen * (u64)elsz), (len - oldlen) * (u64)elsz, 0, 0);
        if (elt && (function_415b30(elt) & 0xff)) function_417310(data + oldlen * (u64)elsz, elt, len - oldlen);
    }
    if ((long long)dimcnt > 1) {
        u64 lv = lengths + 8, dc = dimcnt - 1;
        for (u64 i = 0; (long long)i < (long long)len; i++) function_417b70(data + i * 8, elt, dc, lv);
    }
    Q(a) = data;
    return 0;
}

#ifndef M11_OV_CLASSCREATE
#define M11_OV_CLASSCREATE 0
#endif
#ifndef M11_NOVCALL
#define M11_NOVCALL 0
#endif
#if M11_OV_CLASSCREATE
/* function_410360  VA 0x410360  (System.TObject: AfterConstruction 呼出し stub) (#419) — 実験: 既定 OFF (-DM11_OV_CLASSCREATE=1 で有効)。
 * 410320 (ClassCreate) / 40f960 (NewInstance) / 40fb40 (InitInstance) / 40fac0 は main (#474) が既定で転記済みのため本ブロックには持たない。
 * RetDec は `call [rbx-0x50]` (= AfterConstruction) を落とし `ret arg1` に誤 lift した (DEFECTS D15 型, call site 492)。
 * VMT slot 呼出し: closure 外の AfterConstruction 既定実装 410070 (= ret) は呼ばず (miss 計上を避ける), #494 の site/target 計測には ok で計上する。
 * site は元バイナリの `call [rbx-0x50]` の VA 0x41037d (逆アセンブルで確認) */
static u64 m11_vcall(u32 site, u64 target, u64 self) {
    if (target == R(0x10070)) {
        icall_bump(&g_isite, site, 0);
        icall_bump(&g_itgt, 0x410070u, 0);
        return self;
    }
#if M11_NOVCALL
    return self;
#endif
    return ICALL_AT(site, target, self, 0, 0, 0, 0, 0, 0, 0);
}
unsigned long long function_410360(unsigned long long inst) {
    m11_vcall(0x41037d, Q(Q(inst) - 0x50), inst);
    return inst;
}

/* function_9b5450  VA 0x9b5450  (ユーザクラス初期化: フィールドを 0 クリアし 412d60 で解放) (#704)
 * 逆アセンブル: mov qword/dword [rcx+off],0 (0x5c,0x20,0x88,0x78,0x08,0x64,0x6c,0x10,0x50,0x74) → lea rcx,[rcx+0x28]; call 412d60; ret */
static void function_9b5450(u64 rcx) {
    Q(rcx + 0x5c) = 0;
    Q(rcx + 0x20) = 0;
    Q(rcx + 0x88) = 0;
    Q(rcx + 0x78) = 0;
    Q(rcx + 8) = 0;
    Q(rcx + 0x64) = 0;
    Q(rcx + 0x6c) = 0;
    Q(rcx + 0x10) = 0;
    D(rcx + 0x50) = 0;
    D(rcx + 0x74) = 0;
    function_412d60(rcx + 0x28, 0);
}

/* function_9b4b00  VA 0x9b4b00  (ユーザクラス AfterConstruction 相当。410360 ON 時に [vmt-0x50] 経由で呼ばれる; #704)
 * 逆アセンブル (103 byte): push rbx; mov rbx,rcx; call 410070 (ret); rcx=[0x9b4b00+...]; dl=1; call 481790 → [rbx+0x54]=rax;
 *   byte [rbx+0x34]=0; call 9b5450(rbx); call 4133f0(rbx+0x48, rip+0x3b); call 412d60(rbx+0x80); dword [rbx+0x3c]=0;
 *   call 412d60(rbx+0x28); dword [rbx+0x30]=0xffffff9d; ret
 * closure 外 (boot_fns.json に無い) のため m11_icall が miss していた (REPORT_595 §2.3)。 */
static u64 function_9b4b00(u64 rcx) {
    u64 rbx = rcx;
    u64 rax = function_481790((void*)(uintptr_t)Q(R(0x805a8)), 1);
    Q(rbx + 0x54) = rax;
    *(volatile u8*)(uintptr_t)(rbx + 0x34) = 0;
    function_9b5450(rbx);
    function_4133f0(rbx + 0x48, R(0x5b4b74));
    function_412d60(rbx + 0x80, 0);
    D(rbx + 0x3c) = 0;
    function_412d60(rbx + 0x28, 0);
    D(rbx + 0x30) = 0xffffff9d;
    return rbx;
}
static u64 tr_9b4b00(u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) { return function_9b4b00(a0); }

#endif /* M11_OV_CLASSCREATE */

#ifndef M11_OV_413060
#define M11_OV_413060 0
#endif
#ifndef M11_NEG_413060
#define M11_NEG_413060 0
#endif
#if M11_OV_CLASSCREATE || M11_OV_413060
/* function_413060  VA 0x413060  (System._UStrFromPWCharLen 系: dest: PPointer, src: PWideChar, len: Integer) (#595)
 * 逆アセンブル: `old := [rbx]` を stack に退避 → len>0 なら [rbx] := 412c20(len), src があれば 409c80(src, new, len*2) / len<=0 なら [rbx] := 0 → 最後に 412d60(&old) で旧文字列を解放。
 * RetDec は `mov rax,[rbx]` の deref を落とし (D4), stack に dest のアドレス自体を入れた。412d60 がそれを文字列ポインタと見て dest-0x10+8 = dest-8 を refcount として減算するため,
 * dest = オブジェクト +8 の文字列フィールド (448ee0 → 41c820 → 413060 の経路) では オブジェクト先頭 dword (VMT ポインタの下位) が 1 減り, 410360 が壊れた VMT から [vmt-0x50] を引いた。
 * 戻り値: 元実装は 412d60 の戻り値 = stack 上の old のアドレス (関数終了後は無効) を返す。C でそれを返すと無効な番地になるため dest を返す。
 * 呼出し側が戻り値を読むかは未検証 (REPORT_595 §2.2)。 */
#ifndef M11_INSTR_413060
#define M11_INSTR_413060 0
#endif
#if M11_INSTR_413060
void m11_probe(int i);
void m11_dest_obs(unsigned long long dest);
#endif
unsigned long long function_413060(unsigned long long dest, void* src, unsigned long long len) {
#if M11_INSTR_413060
    m11_probe(8);
#endif
    u64 old = Q(dest);
    int n = (int)len;
    if (n > 0) {
        u64 p = function_412c20(len & 0xffffffffull);
        Q(dest) = p;
        if (src) function_409c80((u64)(uintptr_t)src, p, (u64)(long long)(int)((unsigned)n * 2u));
    } else {
        Q(dest) = 0;
    }
    function_412d60((u64)(uintptr_t)&old, 0);
#if M11_INSTR_413060
    m11_dest_obs(dest);
#endif
    return dest;
}
#endif /* M11_OV_CLASSCREATE || M11_OV_413060 */

/* #882 計測専用 (M11_INSTR_40FF70=1 のときだけ有効): function_40ff70 の入口で p-144 (= arg1-0x90) の値と
 * 先頭ノードの word [p] を stderr に出す。線形メモリ外は読まない。既定 0 では何も入らない。 */
#ifndef M11_INSTR_40FF70
#define M11_INSTR_40FF70 0
#endif
#if M11_INSTR_40FF70
static int g_p144_n;
void m11_p144_obs(unsigned long long p) {
    unsigned long long heap = (unsigned long long)__builtin_wasm_memory_size(0) * 65536ULL;
    unsigned long long head = 0, w0 = 0;
    if (p >= 0x90 && p - 0x90 + 8 <= heap) head = *(volatile unsigned long long*)(uintptr_t)(p - 0x90);
    if (head >= 8 && head + 2 <= heap) w0 = *(volatile unsigned short*)(uintptr_t)head;
    if (g_p144_n++ < 16)
        fprintf(stderr, "[m11][p144] #%d arg1=0x%llx p-144=0x%llx word[head]=%llu\n", g_p144_n, p, head, w0);
}
#endif

/* #882 計測専用 (M11_INSTR_40FFE0=1 のときだけ有効): function_40ffe0 の入口で arg1 と、40ff70 へ渡る値 v = [arg1]、
 * v-0x90 (p-144) の値を stderr に出す。線形メモリ外は読まない (address 0 は線形メモリ内なので読む)。既定 0 では何も入らない。 */
#ifndef M11_INSTR_40FFE0
#define M11_INSTR_40FFE0 0
#endif
#if M11_INSTR_40FFE0
static int g_ffe0_n;
void m11_ffe0_obs(unsigned long long a) {
    unsigned long long heap = (unsigned long long)__builtin_wasm_memory_size(0) * 65536ULL;
    unsigned long long v = 0, p144 = 0;
    if (a + 8 <= heap) v = *(volatile unsigned long long*)(uintptr_t)a;
    if (v >= 0x90 && v - 0x90 + 8 <= heap) p144 = *(volatile unsigned long long*)(uintptr_t)(v - 0x90);
    if (g_ffe0_n++ < 16)
        fprintf(stderr, "[m11][ffe0] #%d arg1=0x%llx v=[arg1]=0x%llx p-144=0x%llx\n", g_ffe0_n, a, v, p144);
}
#endif

/* #2373 計測専用 (M11_INSTR_60A270=1 のときだけ有効): function_60a270 の入口で this (arg1) と arg2 を stderr に出す。
 * 60a270 は 40ffe0 の唯一の観測 caller (#882 §13.3)。this が 0 かどうかを見る。既定 0 では何も入らない。 */
#ifndef M11_INSTR_60A270
#define M11_INSTR_60A270 0
#endif
#if M11_INSTR_60A270
static int g_60a270_n;
void m11_60a270_obs(unsigned long long a, unsigned int b) {
    if (g_60a270_n++ < 16)
        fprintf(stderr, "[m11][60a270] #%d this=0x%llx arg2=0x%x\n", g_60a270_n, a, b);
}
#endif

/* ---- #483: TDictionary<K,V> (Generics.Collections) の Add/GetItem が全て「重複キー」と誤判定される原因 3 点の C 転記 ----
 * 8cc190 (Add) は FComparer = TEqualityComparer<K>.Default (53df80 → 479b40 _LookupVtableInfo) の GetHashCode/Equals を使う.
 *   479b40  `movzx rcx,byte [rbx]` (TypeInfo.Kind) の deref 脱落 (D4) で Kind=0 固定, `test cl,2; call rax` (getter 呼出し) 脱落 (D15)
 *           → FComparer が実体でなく getter 関数 478b10 自身 (0x78b10) になる
 *   8cbda0  GetHashCode: `call [vt+0x20]` 脱落 (D15) + 引数 rdx (key) が唯一の使用者を失って IR 署名から消える → hash = [FComparer]+1 の定数
 *   8cbce0  Find:        `call [vt+0x18]` (Equals) 脱落 (D15) → `test al,al` が [FComparer] の下位 byte を読み 常に真 → 2 個目のキーが必ず「重複」
 * → 8cc190 が EListError を生成して 411e80 (RaiseExcept) を呼び Halt0 (survey halt0 11 unit, REPORT_483).
 * 逆アセンブル (479b40..479bd6 / 8cbda0..8cbdc2 / 8cbce0..8cbd90 / 8cc190..8cc214 / 8cbde0..8cbe3a) から転記.
 * 8cbda0 は引数 key を取れないので helper (ov_dict_hash) に置き, IR 署名を変えずに済むよう呼出元の 8cc190 / 8cbde0 も転記する. */

/* function_479b40  VA 0x479b40  (_LookupVtableInfo(intf: u8; info: PTypeInfo; size: Integer): Pointer)
 *   表 @LVA 0xfb2c28: [intf * 0x170 + info.Kind * 16] = { u8 flags; u64 data @+8 }
 *   flags&2: data := data(info, size) (getter) / flags&1: data := MakeInstance(data, info, size) (4781a0).
 *   info = nil: intf 0 → 478a90(nil,size) / 1 → 478b10(nil,size) / 他 → Error(reInvalidPtr). */
u64 function_479b40(u64 intf, void* infop, u64 size) {
    u64 info = (u64)(uintptr_t)infop;
    if (info) {
        u64 e = R(0xfb2c28) + (intf & 0xff) * 0x170 + (u64)B(info) * 16;
        u64 data = Q(e + 8);
        if (B(e) & 2) data = m11_icall(data, info, size, 0, 0, 0, 0, 0, 0);
        if (B(e) & 1) data = function_4781a0(data, info, size);
        return data;
    }
    if ((intf & 0xff) == 0) return function_478a90(0, size);
    if ((intf & 0xff) == 1) return function_478b10(0, size);
    function_409730(4);
    return 0;
}

/* function_8cbda0 の転記 (key を引数に取る): GetHashCode(FComparer, key) を m11_icall で呼び (vt+0x20), (h & 0x7fffffff) + 1 を再マスク */
static u32 ov_dict_hash(u64 self, u64 key) {
    u64 cmp = Q(self + 0x18);
    u32 h = (u32)m11_icall(Q(Q(cmp) + 0x20), cmp, key, 0, 0, 0, 0, 0, 0);
    return ((h & 0x7fffffffu) + 1u) & 0x7fffffffu;
}

/* function_8cbce0  VA 0x8cbce0  (TDictionary.GetBucketIndex(key, hash): 戻り >= 0 = 発見 index, < 0 = ~(挿入位置), 空表は 0x8000000000000000)
 *   バケット = 24B { u32 hash (0xffffffff = 空); u64 key @+8; u64 value @+0x10 }, 線形探査, 配列長は [arr-8]. Equals は [FComparer.vt + 0x18]. */
u64 function_8cbce0(u64 self, u64 key, u64 hash) {
    u32 h = (u32)hash;
    u64 arr = Q(self + 8);
    long long n = arr ? (long long)Q(arr - 8) : 0;
    if (n == 0) return 0x8000000000000000ull;
    long long i = (long long)(int)h & (n - 1);
    u64 p = arr + (u64)i * 24;
    for (;;) {
        u32 eh = D(p);
        if (eh == 0xffffffffu) return ~(u64)i;
        if (eh == h) {
            u64 cmp = Q(self + 0x18);
            if ((u8)m11_icall(Q(Q(cmp) + 0x18), cmp, Q(p + 8), key, 0, 0, 0, 0, 0)) return (u64)i;
        }
        i++; p += 24;
        if (i >= n) { i = 0; p = Q(self + 8); }
    }
}

/* function_8cc190  VA 0x8cc190  (TDictionary.Add(key, value)): 満杯なら Grow(8cbcb0) → hash → Find → 発見なら EListError を生成して RaiseExcept (411e80) /
 * 未発見なら 8cbe40 (AddItem(self, hash, ~idx, key, value)). EListError クラス = [LVA 0x2f078], メッセージ resourcestring = [LVA 0x11e00e0]. */
u64 function_8cc190(u64 self, u64 key, u64 val) {
    if ((long long)Q(self + 0x10) >= (long long)Q(self + 0x20)) function_8cbcb0(self);
    u32 h = ov_dict_hash(self, key);
    long long idx = (long long)function_8cbce0(self, key, h);
    if (idx >= 0) function_411e80(function_448ee0(Q(R(0x2f078)), 1, Q(R(0x11e00e0))));
    return function_8cbe40(self, h, ~(u64)idx, key, val);
}

/* function_8cbde0  VA 0x8cbde0  (TDictionary.GetItem(key): value; 未発見は EListError [msg = LVA 0x11e0080]) */
u64 function_8cbde0(u64 self, u64 key) {
    u32 h = ov_dict_hash(self, key);
    long long idx = (long long)function_8cbce0(self, key, h);
    if (idx < 0) {
        function_411e80(function_448ee0(Q(R(0x2f078)), 1, Q(R(0x11e0080))));
        return 0;
    }
    return Q(Q(self + 8) + (u64)idx * 24 + 0x10);
}

/* function_8c7710  VA 0x8c7710  (GetItem の呼出し口: 辞書 = [self+0x410], key = [obj] (obj の VMT = TClass))
 *   機械語 `mov rax,[rbp+0x30]; mov rax,[rax]; ... call 8cbde0` の 1 段 deref (key = [arg2]) が IR で脱落し arg2 がそのまま渡っていた (D4 型, #662) */
u64 function_8c7710(u64 self, u64 obj) {
    return function_8cbde0(Q(self + 0x410), Q(obj));
}

/* function_478420  VA 0x478420  (IEqualityComparer getter: tkInteger / tkEnumeration; OrdType (byte [info+1+nameLen+1]) で static 実体を選ぶ)
 *   OrdType 0,1 (byte) → LVA 0xfb21e0 / 2,3 (word) → 0xfb21e8 / 4,5 (long) → 0xfb21f0 / 他 → Error(reInvalidPtr) */
static u64 ov_getter_478420(u64 info) {
    u8 ot = B(info + B(info + 1) + 2);
    if (ot < 2) return R(0xfb21e0);
    ot -= 2;
    if (ot < 2) return R(0xfb21e8);
    ot -= 2;
    if (ot < 2) return R(0xfb21f0);
    function_409730(4);
    return 0;
}

/* function_478540  VA 0x478540  (IComparer getter: tkInt64; MaxInt64Value > MinInt64Value (符号付き比較) なら符号付き用 / 他は符号なし用の static 実体) */
static u64 ov_getter_478540(u64 info) {
    u64 n = B(info + 1);
    return (long long)Q(info + n + 0xa) > (long long)Q(info + n + 2) ? R(0xfb2218) : R(0xfb2240);
}

/* function_471310  VA 0x471310  (record 型の比較方式分類: 0 = 非 record / 1 = 4B 以下で最初の RecOp が奇数 / 2 = 4B 以下で単純 / 3 = 4B 超か複数 RecOp).
 *   Kind は tkRecord (14) / tkMRecord (22) だけ対象 (word 表 @LVA 0x71400 = 0x4040 の bit (Kind-8)). RecSize (dword) > 4 → 3, tkRecord → 2,
 *   tkMRecord は ManagedFld (16B x Count) を飛ばした先の RecOps を最大 4 個見る. */
static u8 ov_rec_kind(u64 info) {
    if (!info) return 0;
    u8 k = (u8)(B(info) - 8);
    if (k > 0xf || !((1u << k) & 0x4040u)) return 0;
    u64 n = info + 1;
    if ((int)D(n + B(n) + 1) > 4) return 3;
    if (B(info) == 0xe) return 2;
    u64 a = n + B(n) + 5;
    u32 cnt = D(a);
    a += 4 + (u64)(long long)((int)(cnt << 4));
    u8 c = B(a);
    a += 1;
    if (c != 0 && (Q(a) & 1)) return 1;
    if (c > 1 && Q(a + 8) != 0) return 3;
    if (c > 2 && Q(a + 0x10) != 0) return 3;
    if (c > 3 && Q(a + 0x18) != 0) return 3;
    return 2;
}

/* function_478c70  VA 0x478c70  (IComparer getter: tkRecord / tkMRecord; ov_rec_kind で static vtable を選び 4781a0 でインスタンス化) */
static u64 ov_getter_478c70(u64 info, u64 size) {
    switch (ov_rec_kind(info)) {
    case 1: return function_4781a0(R(0xfb2670), info, size);
    case 2: return function_478a90(info, size);
    case 3: return function_4781a0(R(0xfb2488), info, size);
    }
    return 0;
}

/* function_410b10  VA 0x410b10  (System.TMonitor の GetMonitor 相当: obj の monitor スロット = obj + InstanceSize - 8 を返し, 無ければ 410650 で作って cmpxchg で差す)
 * RetDec は `mov rax,[rcx]` (obj → VMT) を落とし, `[obj-0x80]` (InstanceSize = [VMT-0x80]) を読んだ (D4: disp=0 の deref 脱落).
 * _ClassCreate が TClass 自身を「オブジェクト」として返していた間は [obj-0x80] が偶然 InstanceSize になっていたが, 40fb40 以降の実オブジェクトでは
 * ヒープ上の任意値になり, 不正アドレスに TMonitor の LockCount/Recursion/Owner を書いて FastMM のプールヘッダを壊した (unit #18 OOB の再発).
 *   rsi = obj + sext([[obj]-0x80]) - 8; cur = *rsi; (cur & ~1) があればそれを返す.
 *   無ければ new = 410650() (TMonitor 作成); lock cmpxchg(*rsi, cur → new | (cur & 1)); 再読込して (*rsi & ~1) == 0 なら再試行;
 *   勝った値が new と異なれば new を 407e20 (FreeMem) で解放. 戻り = *rsi & ~1. */
extern unsigned long long function_410650(void);
extern unsigned long long function_407e20(unsigned long long);
unsigned long long function_410b10(unsigned long long obj) {
    u64 slot = obj + (u64)(long long)(int)D(Q(obj) - 0x80) - 8;
    u64 cur = Q(slot);
    u64 mon = cur & ~1ull;
    if (mon) return mon;
    u64 nw = function_410650();
    for (;;) {
        if (Q(slot) == cur) Q(slot) = nw | (cur & 1);
        cur = Q(slot);
        mon = cur & ~1ull;
        if (mon) break;
    }
    if (mon != nw) function_407e20(nw);
    return mon;
}

/* function_40a3b0 (System.Math.GetMXCSR: stmxcsr [rsp]; pop rax; ret): RetDec は pop rax を落とし常に 0 を返す
 * (__asm_stmxcsr(0); ret 0)。MXCSR マスクビット (0x1f80) が 0 = 全 FP 例外アンマスク扱いとなり,
 * 40a1c0 (FP 例外送出) → 409730 Error → Halt0 に至る (#417)。wasm に MXCSR は無いので既定値 0x1f80 を返す。 */
unsigned long long function_40a3b0(void) {
    return 0x1f80;
}

/* function_4159e0  VA 0x4159e0  (System.InitializeArray(p, ti, count))  /  function_416db0 (System.CopyArray(dest, src, ti, count))
 * RetDec は型情報の種別バイト `mov rax,ti; movzx rcx,byte [rax]` の load を落とし kind=0 固定 → default 分岐の Error(reInvalidPtr)
 * → Halt0 (#417: survey halt0 の 6 unit 直接原因)。逆アセンブル (4159e0..415b05 / 416db0..416f70) から転記。
 * kind: 10/11/15/17/18 = 単純管理型 (8B), 12 = 24B, 13 = 静的配列 (再帰), 14/22 = record */
#define TI_REC(ti) ((ti) + B((ti) + 1))
unsigned long long function_4159e0(unsigned long long p, unsigned long long ti, unsigned int count32) {
    u64 count = count32;
    if (!count) return 0;
    u32 kind = B(ti);
    switch (kind) {
    case 10: case 11: case 15: case 17: case 18:
        if (count == 1) Q(p) = 0; else function_40d210((void*)(uintptr_t)p, count << 3, 0, 0);
        return 0;
    case 12:
        if (count == 1) { Q(p) = 0; Q(p + 8) = 0; Q(p + 16) = 0; }
        else function_40d210((void*)(uintptr_t)p, count * 24, 0, 0);
        return 0;
    case 13: {
        u64 r = TI_REC(ti);
        return function_4159e0(p, Q(Q(r + 0xa)), (unsigned)((u64)D(r + 6) * count));
    }
    case 14: {
        u64 r = TI_REC(ti), sz = D(r + 2);
        do { function_415610(p, ti); p += sz; } while (--count);
        return 0;
    }
    case 22: {
        u64 dummy[16];
        return function_4158e0(dummy, p, ti, count);
    }
    default:
        function_409730(2);
        return 0;
    }
}

#if M11_INSTR_K12
volatile unsigned int m11_site_cur = 0;
#endif

unsigned long long function_416db0(unsigned long long dest, unsigned long long src, unsigned long long ti, unsigned int count32) {
    u64 count = count32;
#if M11_INSTR_K12
    M11_TRACE("[CA_KIND] site=%u kind=%u count=%llu dest=0x%llx src=0x%llx ti=0x%llx\n", m11_site_cur, B(ti), count, dest, src, ti);
#endif
    if (!count) return 0;
    u32 kind = B(ti);
    u64 r = (kind == 13 || kind == 14 || kind == 22) ? TI_REC(ti) : 0;
    do {
        u64 step = 8;
        switch (kind) {
        case 10: function_413540(dest, Q(src)); break;
        case 11: function_4134e0(dest, Q(src)); break;
        case 12: /* 416720: Q(RVA 0xfa5028) が 0 なら Error(0x10), 非 0 なら間接 call (RetDec は落とす, D15 型) */
#if M11_INSTR_K12
            M11_TRACE("[K12HIT] fn=0x%llx slot=0x%llx dest=0x%llx src=0x%llx count=%llu\n", (u64)0x416720, Q(R(0xfa5028)), dest, src, count);
#endif
            if (Q(R(0xfa5028)) == 0) function_409730(0x10);
            else m11_icall(Q(R(0xfa5028)), dest, src, 0, 0, 0, 0, 0, 0);
            step = 0x18; break;
        case 13: function_416db0(dest, src, Q(Q(r + 0xa)), D(r + 6)); step = D(r + 2); break;
        case 14: case 22: function_416750(dest, src, ti); step = D(r + 2); break;
        case 15: function_41a7b0(dest, Q(src)); break;
        case 17: function_418210(dest, Q(src), ti); break;
        case 18: function_4133f0(dest, Q(src)); break;
        default: function_409730(2); return 0;
        }
        dest += step; src += step;
    } while (--count);
    return 0;
}

/* function_467c40  VA 0x467c40  (System.SysUtils 系 unit 0x467f00 の初期化: VarBstrFromBool 経由の TrueBoolStrs/FalseBoolStrs 初期化)
 * RetDec は `mov rax,[rip+0x15e3af0]; call [rax]` (.data の関数ポインタ変数 → .bss 0x15f10e0 の VarBstrFromBool 実体) を 2 箇所とも落とし
 * (D15 型: 0x467cc9 / 0x467d5d), 戻り値 (HRESULT) の代わりに slot ポインタの下位 32bit を 45a640 に渡して例外 0xEEDFADE → Halt0 に進んでいた.
 * 0x15f10e0 は 457c70 が GetProcAddress(oleaut32,"VarBstrFromBool") で埋める (wasm では 0 → fallback 0x457860, closure の boot5).
 * 機械語 0x467c40〜0x467e28 と 1 命令ずつ突合 (stack slot: a[i] = rbp+0x28+8*i (i=0..8, 467e10 で _LStrArrayClr 相当に 9 本まとめて解放), s78 = rbp+0x78). */
unsigned long long function_467c40(void) {
    u64 a[9] = {0, 0, 0, 0, 0, 0, 0, 0, 0};
    u64 s78 = 0;
    u64 slot = Q(R(0x11e3af0));
    if (Q(slot) != 0) {
        function_412e00(&s78);
        u64 r = ICALL_AT(0x467cc9, Q(Q(R(0x11e3af0))), 0, 0x400, 0, (u64)(uintptr_t)&s78, 0, 0, 0, 0);
        function_45a640((u32)r, 0xb, 8);
        function_4149b0((void*)(uintptr_t)R(0x11f1118), s78);
        function_4149b0(&a[7], s78);                   /* rbp+0x60 */
        function_439930(&a[8], a[7]);                  /* rbp+0x68 */
        function_4133f0(R(0x11f1120), a[8]);
        function_4149b0(&a[5], s78);                   /* rbp+0x50 */
        function_4398f0(&a[6], a[5]);                  /* rbp+0x58 */
        function_4133f0(R(0x11f1128), a[6]);
        function_412e00(&s78);
        r = ICALL_AT(0x467d5d, Q(Q(R(0x11e3af0))), 0xffffffffull, 0x400, 0, (u64)(uintptr_t)&s78, 0, 0, 0, 0);
        function_45a640((u32)r, 0xb, 8);
        function_4149b0((void*)(uintptr_t)R(0x11f1130), s78);
        function_4149b0(&a[3], s78);                   /* rbp+0x40 */
        function_439930(&a[4], a[3]);                  /* rbp+0x48 */
        function_4133f0(R(0x11f1138), a[4]);
        function_4149b0(&a[1], s78);                   /* rbp+0x30 */
        function_4398f0(&a[2], a[1]);                  /* rbp+0x38 */
        function_4133f0(R(0x11f1140), a[2]);
        u32 ebx = 0xffffff80u;
        u64 rsi = R(0x11f1148);
        do {
            function_43a7e0(&a[0], ebx, 0, 0);
            function_4133f0(rsi, a[0]);
            ebx++;
            rsi += 8;
        } while (ebx != 0x100u);
    }
    function_412e40((u64)(uintptr_t)&a[0], 9);
    function_412e00(&s78);
    return 0;
}
