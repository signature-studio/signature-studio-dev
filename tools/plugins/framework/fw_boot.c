/* fw_boot.c — P0a (CAB-194) Delphi RTL 起動シーケンスの C override (m11_ov.c 方式の Balance 版).
 *
 * 対象: _StartLib (0x4189c0) / _InitLib (0x40db20) — 両者は 5〜8 引数を **stack 渡し** するため,
 * icall 経路 (BLK = rcx/rdx/r8/r9/xmm0-3 のみ) では stack 引数が構造的に落ちる
 * (integration/README §4 の既知制約; 実測: _InitLib の [rbp+0x170]=Reason が垃圾値になり
 *  DllProc call が未解決 target で fail-fast)。m11 と同様に逆アセンブルからの C 転記で置き換える。
 * InitUnits (0x40da80) は icall 復元済みの lifted 実装をそのまま使う (fw_call_cur 経由)。
 *
 * Balance VA 対応表 (m11 FLE → Balance, fw_stats.json の landmark 一致で実証):
 *   InitUnits  0x4120c0 → 0x40da80 / _InitLib 0x412160 → 0x40db20 / _StartLib 0x41d8f0 → 0x4189c0
 * InitContext (Balance): reason<2 → 0x714C80 / else 0x714DA8 (native 0x40db36/0x40db46 の lea 実測)
 *   InitTable ptr = 0x714C90 (fw_prep.py が抽出) / unit counter = 0x714C98
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <emscripten.h>

#define BLK 0x8A1000u
#define Q(va) (*(volatile uint64_t *)(uintptr_t)(va))
#define D(va) (*(volatile uint32_t *)(uintptr_t)(va))
#define B(va) (*(volatile uint8_t *)(uintptr_t)(va))

extern long long fw_call_cur(uint32_t va);
extern void fw_ff(const char *what);

/* _StartLib (0x4189c0): rcx=Context rdx=PackageInfo r8=hInst r9d=Reason [stk]=Reserved
 * native 実測 (capstone):
 *   reason==1: B(0x716290)=1 B(0x7162D8)=1 Q(0x716298)=hinst Q(0x6D6EA0)=hinst
 *              Q(0x6D6EA8)=0 Q(0x6D6EB0)=0 Q(0x6D6EC0)=pkg+0x10; call 0x418240
 *   → _InitLib(ctx, pkg, r8=&0x6D6E98, r9=&0x6D6EF8, [stk] Q(0x7162A8)=DllProc, hinst, reason, reserved) */
static uint64_t fw_ov_InitLib(uint64_t ctx, uint64_t pkg, uint64_t tblctx, uint64_t hooks,
                               uint64_t dllproc, uint64_t hinst, uint32_t reason, uint64_t reserved);

__attribute__((used)) long long fw_ov_startlib(void) {
    uint64_t ctx = Q(BLK + 8), pkg = Q(BLK + 0x10), hinst = Q(BLK + 0x18);
    uint32_t reason = (uint32_t)Q(BLK + 0x20);
    uint64_t reserved = 0;                    /* stack 引数は BLK 未経由 (未使用を確認済み) */
    fprintf(stderr, "[fw][ov] _StartLib ctx=0x%llx pkg=0x%llx hinst=0x%llx reason=%u\n",
            (unsigned long long)ctx, (unsigned long long)pkg, (unsigned long long)hinst, reason);
    if (reason == 1) {
        B(0x716290) = 1;
        B(0x7162D8) = 1;
        Q(0x716298) = hinst;
        Q(0x6D6EA0) = hinst;
        Q(0x6D6EA8) = 0;
        Q(0x6D6EB0) = 0;
        Q(0x6D6EC0) = pkg + 0x10;
        fw_call_cur(0x418240);
    }
    uint64_t dllproc = Q(0x7162A8);
    return (long long)fw_ov_InitLib(ctx, pkg, 0x6D6E98, 0x6D6EF8, dllproc, hinst, reason, reserved);
}

/* _InitLib (0x40db20): rcx=Context rdx=a1 r8=a2 r9=hooks [stk5]=DllProc [stk6]=hInst [stk7]=Reason [stk8]=Reserved
 * native 実測:
 *   r13 = reason<2 ? 0x714C80 : 0x714DA8
 *   save ctx+0x38 (240B) → ctx ← r13 (296B) → r13+0x38 ← save
 *   Q(r13+0x10)=rdx  Q(r13+0x20)=r8  Q(r13)=rcx
 *   D(r13+0x34) = call 0x404bc0
 *   reason==0 → D(r13+0x18)=D(Q(r13+0x10)) : 0
 *   Q(0x710030)=0x404C00  Q(0x710038)=0x404C10  Q(r13+8)=1  B(r13+0x30)=reason+1
 *   Q(r13+0x28)=Q(hooks)
 *   reason∈{1,2} → call Q(hooks+reason*8) (BLK 現状のまま)
 *   Q([rbp+0x160])=dllproc ≠ 0 → ecx=reason rdx=reserved で call dllproc
 *   reason==3 → call Q(hooks+3*8)
 *   Q(0x716078)==0 → B(0x716084)=1; D(0x70A054)=call 0x407d50
 *   reason==1 → call 0x40da80 (InitUnits) : call 0x40e270 */
static uint64_t fw_ov_InitLib(uint64_t ctx, uint64_t pkg, uint64_t tblctx, uint64_t hooks,
                               uint64_t dllproc, uint64_t hinst, uint32_t reason, uint64_t reserved) {
    (void)hinst;
    uint64_t r13 = (reason < 2) ? 0x714C80 : 0x714DA8;
    uint64_t tmp[30];
    memcpy((void *)(uintptr_t)tmp, (void *)(uintptr_t)(ctx + 0x38), 240);
    memcpy((void *)(uintptr_t)ctx, (void *)(uintptr_t)r13, 296);
    memcpy((void *)(uintptr_t)(r13 + 0x38), (void *)(uintptr_t)tmp, 240);
    Q(r13 + 0x10) = pkg;
    Q(r13 + 0x20) = tblctx;
    Q(r13) = ctx;
    D(r13 + 0x34) = (uint32_t)fw_call_cur(0x404bc0);
    if (reason == 0) D(r13 + 0x18) = (uint32_t)Q(Q(r13 + 0x10)); else D(r13 + 0x18) = 0;
    Q(0x710030) = 0x404C00;
    Q(0x710038) = 0x404C10;
    Q(r13 + 8) = 1;
    B(r13 + 0x30) = (uint8_t)(reason + 1);
    Q(r13 + 0x28) = Q(hooks);
    fprintf(stderr, "[fw][ov] _InitLib reason=%u r13=0x%llx hooks=0x%llx dllproc=0x%llx\n",
            reason, (unsigned long long)r13, (unsigned long long)hooks, (unsigned long long)dllproc);
    if (reason == 1 || reason == 2) {
        uint64_t proc = Q(hooks + (uint64_t)reason * 8);
        fprintf(stderr, "[fw][ov] hooks[%u]=0x%llx\n", reason, (unsigned long long)proc);
        if (proc) fw_call_cur((uint32_t)proc);
        fprintf(stderr, "[fw][ov] hooks[%u] done: tls_idx=%d tls_7162d0=0x%llx\n", reason,
                (int)D(0x6d6e70), (unsigned long long)Q(0x7162d0));
    }
    if (dllproc) {
        Q(BLK + 8) = reason;             /* ecx = reason */
        Q(BLK + 0x10) = reserved;        /* edx = reserved */
        fw_call_cur((uint32_t)dllproc);
    }
    if (reason == 3) {
        uint64_t proc = Q(hooks + (uint64_t)reason * 8);
        if (proc) fw_call_cur((uint32_t)proc);
    }
    if (Q(0x716078) == 0) {
        B(0x716084) = 1;
        D(0x70A054) = (uint32_t)fw_call_cur(0x407d50);
    }
    if (reason == 1) return (uint64_t)fw_call_cur(0x40da80);   /* System.InitUnits (lifted) */
    return (uint64_t)fw_call_cur(0x40e270);
}

/* RestoreContext/longjmp (0x40e130, FLE 0x412770 相当): unit 初期化中の Halt0 → longjmp。
 * m11 と同じく「初期化シーケンスの終端マーカー」として扱う (context[0]=0 の失敗ではなく正常系) */
__attribute__((used)) long long fw_ov_restorectx(void) {
    fprintf(stderr, "[fw][longjmp/Halt0] RestoreContext 到達 — 初期化シーケンス終了 (m11 方式)\n");
    fflush(stderr);
    emscripten_force_exit(0);
}

/* RestoreContext 実行本体 (0x40e0b0): context[0]==0 で失敗する経路。
 * unit 初期化中の SEH unwind 到達 = Halt0 系。 m11 方式で「初期化終了マーカー」として扱う。 */
__attribute__((used)) long long fw_ov_restorectx_run(void) {
    fprintf(stderr, "[fw][RestoreContext] SEH unwind 到達 — 初期化シーケンス終了扱い (m11 方式)\n");
    fflush(stderr);
    emscripten_force_exit(0);
}

/* dispatch 経由の呼出し用 0-arg wrapper (_InitLib への直接 dispatch は無いが保険) */
__attribute__((used)) long long fw_ov_initlib(void) {
    return fw_ov_InitLib(Q(BLK + 8), Q(BLK + 0x10), Q(BLK + 0x18), Q(BLK + 0x20),
                         Q(0x7162A8), Q(BLK + 0x18), (uint32_t)Q(BLK + 0x20), 0);
}
