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

static m11_tr_t disp_find(u32 va) {
    int lo = 0, hi = (int)m11_disp_n - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        u32 v = m11_disp_tab[mid].va;
        if (v == va) return (m11_tr_t)m11_disp_tab[mid].fn;
        if (v < va) lo = mid + 1; else hi = mid - 1;
    }
    return 0;
}

/* 間接 call: target は .data ポインタ表由来 (LVA; reloc 補正済) か lea [rip] 由来の VA. */
u64 m11_icall(u64 target, u64 a0, u64 a1, u64 a2, u64 a3, u64 a4, u64 a5, u64 a6, u64 a7) {
    m11_tr_t f = disp_find((u32)(target + (0x400000ull - M11_LB_BASE)));
    if (!f) {
        f = disp_find((u32)target);
        if (f) g_icall_viaVA++;
    }
    if (!f) {
        g_icall_miss++;
        int seen = 0;
        for (u32 i = 0; i < g_nmiss_uniq; i++) if (g_miss[i] == (u32)target) { seen = 1; break; }
        if (!seen && g_nmiss_uniq < MISS_MAX) g_miss[g_nmiss_uniq++] = (u32)target;
        if (g_trace) fprintf(stderr, "[m11][icall-miss] target=0x%llx (closure 外; skip, ret 0)\n", target);
        return 0;
    }
    g_icall_ok++;
    if (g_trace) fprintf(stderr, "[m11][icall] 0x%llx\n", target);
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
    m11_icall(proc, 0, 0, 0, 0, 0, 0, 0, 0);
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
    if (g_trace) fprintf(stderr, "[m11][InitUnits] InitTable=0x%llx\n", tbl);
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
        if (g_trace) fprintf(stderr, "[m11][unit %d/%d] init=0x%llx\n", i, count, proc);
        m11_icall(proc, 0, 0, 0, 0, 0, 0, 0, 0);
        if ((u32)g_icall_miss != miss0) g_units_skipped++;
        else g_units_run++;
    }
    return (u64)i;
}

/* System._InitLib  VA 0x412160
 *   args: rcx=Context rdx=a1 r8=a2 r9=InitTable(hook 表: [reason] を call) [stk5]=DllProc [stk6]=hInst [stk7]=Reason [stk8]=Reserved */
u64 m11_InitLib(u64 ctx, u64 a1, u64 a2, u64 tbl, u64 dllproc, u64 hinst, u64 reason64, u64 reserved) {
    u32 reason = (u32)reason64;
    if (g_trace) fprintf(stderr, "[m11][InitLib] ctx=0x%llx a1=0x%llx a2=0x%llx tbl=0x%llx dllproc=0x%llx hinst=0x%llx reason=%u reserved=0x%llx\n", ctx, a1, a2, tbl, dllproc, hinst, reason, reserved);
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
    if (reason == 1 || reason == 2) m11_icall(Q(tbl + (u64)reason * 8), reason, 0, 0, 0, 0, 0, 0, 0);
    if (dllproc) m11_icall(dllproc, reason, reserved, 0, 0, 0, 0, 0, 0);
    if (reason == 3) m11_icall(Q(tbl + (u64)reason * 8), reason, 0, 0, 0, 0, 0, 0, 0);
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
    if (g_trace) fprintf(stderr, "[m11][UStrAsg] dest=0x%llx src=0x%llx\n", dest, src);
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

/* function_416db0  VA 0x416db0  (System._CopyArray 系: rcx=dst, rdx=src, r8=型情報(kind byte 先頭), r9=要素数; kind で要素 copy を分岐)
 * RetDec は `movzx rcx, byte ptr [rax]` (rax=r8=型情報) の kind 読出しを落とし, kind が常に 0 → 未知 kind の Error (Halt0) に直行した
 * (unit #18: TFormatSettings の string フィールド (kind=18) が 416750 → 416db0 で Halt0). 逆アセンブル 0x416db0-0x416f65 と突合:
 *   10→413540 / 11→4134e0 / 15→41a7b0 (8B 刻み) / 17→418210(…, ti) / 18→_UStrAsg(4133f0) / 12→416720 (0x18 刻み)
 *   13→自己再帰 (ti+B(ti+1) の {+6:count, +2:stride, +0xa:elemti**}) / 14,22→416750(dst,src,ti) (stride=D(r14+2)) / 他→Error(2) */
unsigned long long function_416db0(unsigned long long dst, unsigned long long src, unsigned long long ti, unsigned int cnt) {
    u64 rbx = dst, rsi = src, r13 = (u64)cnt;
    if (r13 == 0) return 0;
    u64 rax = 0;
    u32 kind = B(ti);
    u64 r14 = ti + (u64)B(ti + 1);
    switch (kind) {
    case 10: do { rax = function_413540(rbx, Q(rsi)); rbx += 8; rsi += 8; } while (--r13); break;
    case 11: do { rax = function_4134e0(rbx, Q(rsi)); rbx += 8; rsi += 8; } while (--r13); break;
    case 12: do { rax = function_416720(rbx); (void)rsi; rbx += 0x18; rsi += 0x18; } while (--r13); break;
    case 13: do { u64 et = Q(Q(r14 + 0xa)); rax = function_416db0(rbx, rsi, et, D(r14 + 6)); u64 st = D(r14 + 2); rbx += st; rsi += st; } while (--r13); break;
    case 14: case 22: do { rax = function_416750(rbx, rsi, ti); u64 st = D(r14 + 2); rbx += st; rsi += st; } while (--r13); break;
    case 15: do { rax = function_41a7b0(rbx, Q(rsi)); rbx += 8; rsi += 8; } while (--r13); break;
    case 17: do { rax = function_418210(rbx, Q(rsi), ti); rbx += 8; rsi += 8; } while (--r13); break;
    case 18: do { rax = function_4133f0(rbx, Q(rsi)); rbx += 8; rsi += 8; } while (--r13); break;
    default: function_409730(2); break;
    }
    return rax;
}

/* function_412770  VA 0x412770  (System: InitContext 復元 + longjmp(setjmp 点=entry_point 内) )
 * 実機では戻らない (DllMain の setjmp が eax=1 で再返却 → DllMain は TRUE を返す).
 * lift 版は longjmp を表現できず, 通常 return して Halt0 が ExitProcess まで進んでしまう (実測).
 * wasm では JS 例外で呼出しスタックを巻き戻し, ハーネスが「DllMain attach 完走」と判定する. */
EM_JS(void, m11_throw_dllmain_done, (int code), { throw { m11_dllmain_done: code }; });
static int g_longjmp_hit = 0;
EMSCRIPTEN_KEEPALIVE int m11_longjmp_hit(void) { return g_longjmp_hit; }
unsigned long long function_412770(void* ctx) {
    g_longjmp_hit++;
    if (g_trace) fprintf(stderr, "[m11][longjmp] Halt0 -> RestoreContext(ctx=%p): DllMain attach 完走として JS 例外で巻き戻す\n", ctx);
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
        u64 r = m11_icall(Q(Q(R(0x11e3af0))), 0, 0x400, 0, (u64)(uintptr_t)&s78, 0, 0, 0, 0);
        function_45a640((u32)r, 0xb, 8);
        function_4149b0((void*)(uintptr_t)R(0x11f1118), s78);
        function_4149b0(&a[7], s78);                   /* rbp+0x60 */
        function_439930(&a[8], a[7]);                  /* rbp+0x68 */
        function_4133f0(R(0x11f1120), a[8]);
        function_4149b0(&a[5], s78);                   /* rbp+0x50 */
        function_4398f0(&a[6], a[5]);                  /* rbp+0x58 */
        function_4133f0(R(0x11f1128), a[6]);
        function_412e00(&s78);
        r = m11_icall(Q(Q(R(0x11e3af0))), 0xffffffffull, 0x400, 0, (u64)(uintptr_t)&s78, 0, 0, 0, 0);
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

/* function_417b70  VA 0x417b70  (System._DynArraySetLength(pa: PPointer, typeinfo, dimCnt: NativeInt, pdims: PNativeInt))
 * RetDec は `mov rax,[rbp+0xc8]; mov rax,[rax]` (pdims の 1 段 deref) と `mov rax,[rcx]` (*pa の旧値) を落とし (D7 型),
 * pdims のポインタ自体を新 Length として扱い overflow 検査 (idiv) で Error(4) → Halt0 に進んだ (unit #23: BoolToStr の DynArray SetLength(1)).
 * 機械語 0x417b70〜0x417fa2 と突合 (配列 header = [ -0x10 .. ): +4 refcnt(i32), +8 length(i64)). 例外 landing pad (0x417f30〜) は転記しない. */
unsigned long long function_417b70(unsigned long long pa, unsigned long long ti, unsigned long long dimCnt, unsigned long long pdims) {
    u64 p = Q(pa);
    long long newLen = (long long)Q(pdims);
    if (newLen <= 0) {
        if (newLen < 0) function_409730(4);
        function_418190(pa, ti, 0);
        return 0;
    }
    long long oldLen = 0;
    if (p) { p -= 0x10; oldLen = (long long)Q(p + 8); }
    u64 td = ti + B(ti + 1);
    long long elSize = (long long)(int)D(td + 2);
    u64 elPP = Q(td + 6);
    u64 elTi = elPP ? Q(elPP) : 0;
    long long total;
    if (__builtin_mul_overflow(newLen, elSize, &total)) function_409730(4);
    if (__builtin_add_overflow(total, 0x10, &total) || total < 0) function_409730(4);
    if (p == 0 || (int)D(p + 4) == 1) {
        u64 np = p;
        if (elTi) {
            if (function_417b10(elTi) & 0xff) {
                long long n = newLen < oldLen ? newLen : oldLen;
                np = function_409410((unsigned)total);
                function_40d210((void*)(uintptr_t)(np + 0x10), (unsigned long long)(n * elSize), 0, 0);
                if (p) {
                    function_416f80(np + 0x10, p + 0x10, elTi, (unsigned)n);
                    if (newLen < oldLen) function_417130(p + 0x10 + (u64)(newLen * elSize), elTi, (unsigned long long)(oldLen - newLen));
                    function_409440(p);
                }
            } else {
                if (newLen < oldLen) function_417130(p + 0x10 + (u64)(newLen * elSize), elTi, (unsigned long long)(oldLen - newLen));
                function_409470(&np, (unsigned long long)total);
            }
        } else {
            function_409470(&np, (unsigned long long)total);
        }
        p = np;
    } else {
        p = function_409410((unsigned)total);
        long long n = oldLen < newLen ? oldLen : newLen;
        if (elTi) {
            function_40d210((void*)(uintptr_t)(p + 0x10), (unsigned long long)(n * elSize), 0, 0);
            function_416db0(p + 0x10, Q(pa), elTi, (unsigned)n);
        } else {
            function_409c80(Q(pa), p + 0x10, (unsigned long long)(n * elSize));
        }
        function_418190(pa, ti, 0);
    }
    D(p + 4) = 1;
    Q(p + 8) = (u64)newLen;
    p += 0x10;
    if (newLen > oldLen) {
        function_40d210((void*)(uintptr_t)(p + (u64)(elSize * oldLen)), (unsigned long long)(elSize * (newLen - oldLen)), 0, 0);
        if (elTi && (function_415b30(elTi) & 0xff))
            function_417310(p + (u64)(oldLen * elSize), elTi, (unsigned long long)(newLen - oldLen));
    }
    if ((long long)dimCnt > 1) {
        u64 nd = pdims + 8;
        for (long long i = 0; i < newLen; i++) function_417b70(p + (u64)i * 8, elTi, dimCnt - 1, nd);
    }
    Q(pa) = p;
    return 0;
}

/* function_409470  VA 0x409470  (System._ReallocMem(var P: Pointer; NewSize: NativeInt): Pointer)
 * RetDec は 0x4094c5〜0x4094da (P=nil, NewSize>0 の GetMem 経路) の `mov [rbx],rsi` を落とし, 続く llvm.trap に化けさせた
 * (unit #23: DynArraySetLength が p==nil の _ReallocMem で trap). 機械語 0x409470〜0x4094dd と突合.
 *   P!=nil: NewSize>0 → ReallocMem(P) (0 なら Error(1)) / NewSize<=0 → FreeMem(P) (非0 なら Error(2)), 結果を *P へ
 *   P==nil: NewSize>0 → GetMem(NewSize) (0 なら Error(1)), 結果を *P へ / NewSize<=0 → 0 */
unsigned long long function_409470(void* pp, unsigned long long newsize) {
    u64 p = (u64)(uintptr_t)pp;
    u64 r;
    if (Q(p) != 0) {
        if ((long long)newsize > 0) {
            r = function_408040(Q(p), newsize);
            if (r == 0) function_409730(1);
        } else {
            if ((u32)function_407e20(Q(p)) != 0) function_409730(2);
            r = 0;
        }
        Q(p) = r;
        return r;
    }
    if ((long long)newsize <= 0) return 0;
    r = function_407a50(newsize);
    if (r == 0) function_409730(1);
    Q(p) = r;
    return r;
}
