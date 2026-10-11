/* scen_em.h — KH-10 (CAB-247) EditorModel 層部分 lift の ctx-fuzz scenario。
 *
 * 対象: EditorModel ctor 0x180051af0 / poll1 0x180052830 / poll2 0x180052a00 / +0x1088 writer 0x18002e850。
 * stub seam (wasm と native image パッチの両系で同一動作):
 *   getStatus 0x180054bd0  → mov eax,[0x04000008]; ret     (wasm: lic_stub retderef。アリーナ status セル = 状態注入点)
 *   key_init  0x180021490  → cave stub (lic_stub key_init と同一の 6 フィールド書込み, rax=rcx)
 *   apply_key 0x1800219b0  → cave stub ([rcx]=0x1a を i32 store, rax=1)
 *   getManager 0x180107430 → cave stub ([rcx]=0x0400F000, [rcx+8]=0)  (fake mgr: subscribe を no-op にするため参照されない)
 *   subscribe 0x1800526f0  → ret (登録先は manager ヒープでアリーナ外 + functor 経路に stage-0 で落ちる vtable call があるため統合 seam)
 *   operator new 0x180f878e0 → em_new (ms_abi, アリーナ bump。wasm shim と同一式)
 *   operator delete 0x180f8791c → ret
 * 実 IR のまま両系で比較: ctor / poll1 / poll2 / writer / 分類 thunk 5 種 / 状態マージ / property・EventSlot 機構 / std::string copy。
 *
 * アリーナ配置 (used 内に収めて比較対象にする):
 *   +0x0000 sys (0x100): [0]=new bump cursor (trial 冒頭で +0x100 に設定), [8]=getStatus status セル (i32)
 *   +0x0100 newheap (0x1000): ctor 中の operator new 確保域
 *   以降: EM(0xC00) / SUB(0x1400) / PM(0x1000) / desc(0x100) / p7(0x40) / sp2,sp4,sp5(各0x10) / X(0x108)
 */
#ifndef SCEN_EM_H
#define SCEN_EM_H
#include "ctxfuzz.h"
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>

#define EM_CTOR    0x180051af0UL
#define EM_POLL1   0x180052830UL
#define EM_POLL2   0x180052a00UL
#define EM_WRITER  0x18002e850UL
#define EM_SUBSCRIBE 0x1800526f0UL
#define EM_REGISTER  0x18002e710UL      /* editor document ctor 0x18002dc30 と同行為 (observer → SUB+0x1b0) */
#define EM_FIRE      0x18010b180UL      /* LicenseManager notify (0x18010a740) の EventSlot 起火部分 */

#define A_CURSOR   0x04000000UL   /* new bump cursor (u64) */
#define A_STATUS   0x04000008UL   /* getStatus が返す status セル (i32) */
#define A_FAKEMGR  0x0400F000UL   /* getManager が out に書く fake manager (書込なし・used 外) */
#define MGR_SLOT   (A_FAKEMGR + 0x20UL)   /* LicenseManager EventSlot (subscribe の登録先・起火対象) */
#define NEW_BASE   0x04000100UL   /* trial 冒頭で cursor に設定する初期値 */

/* ms_abi bump allocator — 0x180f878e0 の entry から jmp で呼ばれる (呼出し規約は Windows 側)。
 * 呼出し側 (LTCG 最適化済み MSVC コード) は new 越しに rdi/rsi 等を生存させているため、
 * volatile GPR 全部を保存 / 復元してから本体を実行する (戻り rax のみ更新)。 */
static __attribute__((naked, used)) void em_new_entry(void) {
    __asm__ volatile(
        "push %rdi \n\t push %rsi \n\t push %rdx \n\t push %rcx \n\t"
        "push %r8 \n\t push %r9 \n\t push %r10 \n\t push %r11 \n\t"
        "mov %rcx, %r10 \n\t"                       /* size */
        "movabs $0x04000000, %r11 \n\t"             /* cursor cell */
        "mov (%r11), %rax \n\t"
        "test %rax, %rax \n\t"
        "jnz 1f \n\t"
        "movabs $0x04001000, %rax \n\t"
        "1: \n\t"
        "add $15, %rax \n\t andq $-16, %rax \n\t"
        "mov %rax, %r9 \n\t"                        /* p */
        "add %r10, %rax \n\t add $15, %rax \n\t andq $-16, %rax \n\t"
        "mov %rax, (%r11) \n\t"
        "mov %r9, %rax \n\t"
        "pop %r11 \n\t pop %r10 \n\t pop %r9 \n\t pop %r8 \n\t"
        "pop %rcx \n\t pop %rdx \n\t pop %rsi \n\t pop %rdi \n\t"
        "ret \n\t"
    );
}

static int em_patched = 0;

static void patch_jmp(u8* entry, u64 target) {
    /* movabs r11, imm64 (49 BB); jmp r11 (41 FF E3) (計 14B) */
    u8 code[14] = {0x49, 0xBB, 0, 0, 0, 0, 0, 0, 0, 0, 0x41, 0xFF, 0xE3, 0x90};
    memcpy(code + 2, &target, 8);
    memcpy(entry, code, 14);
}

static void patch_em(void) {
    void* cave = mmap((void*)0x05000000UL, 0x1000, PROT_READ | PROT_WRITE | PROT_EXEC,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (cave != (void*)0x05000000UL) { fprintf(stderr, "em: cave mmap failed\n"); exit(9); }
    u8* c = (u8*)0x05000000UL;
    /* key_init stub: lic_stub key_init と同一 (state=0x17, found=1, SSO リセット) */
    u8 key_init_stub[] = {
        0xC7, 0x01, 0x17, 0x00, 0x00, 0x00,             /* mov dword [rcx], 0x17 */
        0xC6, 0x41, 0x04, 0x01,                          /* mov byte [rcx+4], 1 */
        0x48, 0xC7, 0x41, 0x08, 0x00, 0x00, 0x00, 0x00,  /* mov qword [rcx+8], 0 */
        0x48, 0xC7, 0x41, 0x10, 0x00, 0x00, 0x00, 0x00,  /* mov qword [rcx+0x10], 0 */
        0x48, 0xC7, 0x41, 0x18, 0x00, 0x00, 0x00, 0x00,  /* mov qword [rcx+0x18], 0 */
        0x48, 0xC7, 0x41, 0x20, 0x0F, 0x00, 0x00, 0x00,  /* mov qword [rcx+0x20], 0xF */
        0x48, 0x89, 0xC8, 0xC3,                          /* mov rax, rcx; ret */
    };
    memcpy(c, key_init_stub, sizeof(key_init_stub));
    u8* apply_stub = c + 64;
    u8 apply_code[] = {
        0xC7, 0x01, 0x1A, 0x00, 0x00, 0x00,              /* mov dword [rcx], 0x1a */
        0xB8, 0x01, 0x00, 0x00, 0x00, 0xC3,              /* mov eax, 1; ret */
    };
    memcpy(apply_stub, apply_code, sizeof(apply_code));
    u8* gm_stub = c + 128;
    u8 gm_code[] = {
        0x48, 0xB8, 0x00, 0xF0, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, /* mov rax, 0x0400F000 */
        0x48, 0x89, 0x01,                                            /* mov [rcx], rax */
        0x48, 0xC7, 0x41, 0x08, 0x00, 0x00, 0x00, 0x00,             /* mov qword [rcx+8], 0 */
        0xC3,
    };
    memcpy(gm_stub, gm_code, sizeof(gm_code));
    /* functor の offset 字段 (+0x18, invoke thunk 0x18003f7f0 が movsxd で読む) は FL コードが
     * dword 部分的に初期化し (subscribe 0x18005275c / register 0x18002e779 の `mov dword [rbp-0x48], r15d`。
     * 本 closure の全 functor は r15d=0)、clone (0x18005b430) が +0x18 を qword コピーするため
     * native 実スタックの call リターンアドレス残骸が下位 4B に写り invoke 時の rcx がワイルド化する
     * (0x180022be0 の `incl 0x30(%rcx)` で SIGSEGV を実測)。本 closure では offset は常に 0 なので
     * clone の `mov rcx,[rcx+0x18]` (48 8B 48 18) を `xor ecx,ecx; nop; nop` (同 4B) に置換し
     * 0 確定にする。wasm 側は kh_stack のフレーム窓を 0 化 (compare.mjs --zero-stack) して対にする。 */
    {
        u8* img0 = (u8*)0x180000000UL;
        /* (1) functor 構築の dword store を qword store に (44 89 7D B8 → 4D 89 7D B8, 同 4B):
         *     +0x1C パディングを 0 確定にする (r15d ロードは 0 拡張なので値は不変) */
        u64 PAD_STORES[2] = {0x18005275cUL, 0x18002e779UL};   /* subscribe / register */
        for (int k = 0; k < 2; k++) {
            u8* q = img0 + (PAD_STORES[k] - 0x180000000UL);
            if (!(q[0] == 0x44 && q[1] == 0x89 && q[2] == 0x7D && q[3] == 0xB8)) {
                fprintf(stderr, "em: functor pad patch mismatch @%lx\n", PAD_STORES[k]);
                exit(9);
            }
            q[0] = 0x4D;   /* mov dword [rbp-0x48], r15d → mov qword [rbp-0x48], r15 */
        }
        /* (2) functor clone の offset qword コピーを 0 確定に (48 8B 49 18 → 31 C9 90 90, 同 4B) */
        u64 CLONE_LOADS[2] = {0x18005b445UL, 0x18003f7e5UL};   /* subscribe/register の functor clone */
        for (int k = 0; k < 2; k++) {
            u8* q = img0 + (CLONE_LOADS[k] - 0x180000000UL);
            if (!(q[0] == 0x48 && q[1] == 0x8B && q[2] == 0x49 && q[3] == 0x18)) {   /* mov rcx, [rcx+0x18] */
                fprintf(stderr, "em: clone offset patch mismatch @%lx\n", CLONE_LOADS[k]);
                exit(9);
            }
            q[0] = 0x31; q[1] = 0xC9; q[2] = 0x90; q[3] = 0x90;   /* xor ecx,ecx; nop; nop */
        }
    }
    /* image パッチ */
    u8* img = (u8*)0x180000000UL;
    patch_jmp(img + (0x180021490UL - 0x180000000UL), (u64)c);            /* key_init */
    patch_jmp(img + (0x1800219b0UL - 0x180000000UL), (u64)apply_stub);   /* apply_key */
    patch_jmp(img + (0x180107430UL - 0x180000000UL), (u64)gm_stub);      /* getManager */
    patch_jmp(img + (0x180f878e0UL - 0x180000000UL), (u64)em_new_entry);  /* operator new */
    { u8 r = 0xC3; memcpy(img + (0x180f8791cUL - 0x180000000UL), &r, 1); } /* operator delete: no-op */
    /* getStatus: mov eax, dword [0x04000008]; ret (8B, 関数は 285B) */
    u8 gs[8] = {0x8B, 0x04, 0x25, 0x08, 0x00, 0x00, 0x04, 0xC3};
    memcpy(img + (0x180054bd0UL - 0x180000000UL), gs, 8);
    em_patched = 1;
}

/* std::string (char/wchar 共通, 0x18000caf0 / 0x1800524e0 のソース) を SSO/heap 両系で作る */
static void em_mkstr(u8* s, int wide) {
    u32 len = R32() % 13;
    u8* buf = A(64);                       /* 常に確保して layout を固定 */
    for (int i = 0; i < 64; i++) buf[i] = (u8)R32();
    for (int i = 0; i < 16; i++) s[i] = (u8)R32();   /* inline 領域も乱数 (SSO 時のコピー元) */
    *(u64*)(s + 0x10) = len;
    if (len < (wide ? 8u : 8u)) {
        *(u64*)(s + 0x18) = wide ? 0xF : 7;
    } else {
        *(u64*)(s + 0x18) = len | 7;
        *(u64*)(s + 0x00) = (u64)buf;
    }
}

typedef struct {
    u8 *sys, *heap, *EM, *SUB, *PM, *desc, *p7, *sp2, *sp4, *sp5, *X;
} EmObj;

/* trial 冒頭の共通セットアップ。status セルは呼び出し直前に設定する */
static void em_setup(int t, EmObj* o) {
    o->sys = A(0x100);
    o->heap = A(0x1000);
    o->EM = A(0xC00);
    o->SUB = A(0x1400);
    o->PM = A(0x1000);
    o->desc = A(0x100);
    o->p7 = A(0x40);
    o->sp2 = A(0x10);
    o->sp4 = A(0x10);
    o->sp5 = A(0x10);
    o->X = A(0x108);
    REGION("sys", o->sys, 0x100);
    REGION("newheap", o->heap, 0x1000);
    REGION("EM", o->EM, 0xC00);
    REGION("SUB", o->SUB, 0x1400);
    REGION("PM", o->PM, 0x1000);
    REGION("desc", o->desc, 0x100);
    REGION("p7", o->p7, 0x40);
    REGION("sp2", o->sp2, 0x10);
    REGION("sp4", o->sp4, 0x10);
    REGION("sp5", o->sp5, 0x10);
    REGION("X", o->X, 0x108);
    if (!em_patched) patch_em();
    *(u64*)o->sys = NEW_BASE;                     /* bump cursor */
    for (int k = 0; k < 16; k++) *(u32*)(o->desc + 4 * k) = R32() & 0x7fffffff;
    u8* d = o->desc + 0x40;                       /* FUN_1800524e0 のコピー元 (decomp の param_6+0x10 は undefined4* 級 = +0x40B) */
    em_mkstr(d, 0); em_mkstr(d + 0x20, 0); em_mkstr(d + 0x40, 0);
    em_mkstr(d + 0x60, 1); em_mkstr(d + 0x80, 0);
    *(u16*)(d + 0xa4) = (u16)R32();
    *(u32*)(o->p7 + 0x00) = RI(0, 40);            /* kind → EM+0x998 */
    *(u64*)(o->p7 + 0x08) = (u64)o->PM;           /* property manager → EM+0xa90 (decomp param_7+2 は undefined4* 級 = +0x08B) */
    *(u64*)(o->p7 + 0x18) = (t % 3 == 0) ? 1 : 0; /* apply_key gate */
    *(u64*)(o->p7 + 0x20) = 0;
    /* SUB 注入: +0x548 cache / +0x5c8 dirty / +0x1088 flag / +0xdb8 */
    *(u32*)(o->SUB + 0x548) = R32() & 1;
    *(u8*)(o->SUB + 0x5c8) = (u8)(R32() & 1);
    *(u32*)(o->SUB + 0x1088) = (R32() % 4 == 0) ? 1 : 0;
    *(u32*)(o->SUB + 0xdb8) = R32() & 1;
}

/* status セルの注入値: ライセンス関連値を重点的に */
static u32 em_pick_status(int t) {
    switch (R32() % 8) {
    case 0: return 9;
    case 1: return 5;
    case 2: return 26;
    case 3: return 25;
    case 4: return 13;
    case 5: return 8;
    case 6: return RI(0, 40);
    default: return 7;
    }
    (void)t;
}

/* em: ctor → poll1 → poll2 → (half) writer。状態注入込み */
static void trial_em(int t) {
    EmObj o;
    em_setup(t, &o);
    *(u32*)A_STATUS = 9;
    C7(EM_CTOR, RET_I64, o.EM, o.sp2, o.SUB, o.sp4, o.sp5, o.desc, o.p7);
    *(u32*)A_STATUS = 9;
    C1(EM_POLL1, RET_NONE, o.EM);
    *(u32*)A_STATUS = (t % 2) ? 9 : em_pick_status(t);
    C1(EM_POLL2, RET_NONE, o.EM);
    if (t & 1) {
        *(u64*)(o.X + 0x100) = (u64)o.EM;
        *(u32*)A_STATUS = em_pick_status(t);
        C1(EM_WRITER, RET_NONE, o.X);
    }
}

/* empoll: ctor のあと poll2 を状態注入しながら 8 回 (thunkA×flag の真理値表を sweep) */
static void trial_empoll(int t) {
    EmObj o;
    em_setup(t, &o);
    *(u32*)A_STATUS = 9;
    C7(EM_CTOR, RET_I64, o.EM, o.sp2, o.SUB, o.sp4, o.sp5, o.desc, o.p7);
    for (int k = 0; k < 8; k++) {
        u32 s = em_pick_status(t);
        *(u32*)A_STATUS = s;
        *(u32*)(o.SUB + 0x1088) = (R32() % 3 == 0) ? 1 : 0;
        *(u32*)(o.SUB + 0x548) = R32() & 1;
        if (k == 4) C1(EM_POLL1, RET_NONE, o.EM);
        C1(EM_POLL2, RET_NONE, o.EM);
    }
}

/* emfire (KH-11 / CAB-247 残スコープ): subscribe 経路を通した「状態変化 → poll1 起火 → +0x548 更新」E2E。
 *   ctor       … subscribe (0x1800526f0) が EM→poll1 functor を mgr+0x20 EventSlot へ実登録 (実 IR)
 *   register   … editor document ctor 0x18002dc30 と同行為で writer functor を SUB+0x1b0 へ登録 (0x18002e710)
 *   fire       … notify (0x18010a740) が呼ぶ EventSlot 起火 (0x18010b180) → functor invoke → poll1
 *                → poll1 の 0x180022be0(SUB+0x1b0) → writer 0x18002e850 → [+0x1088]
 *   poll2      … editable = thunkA(status) && [+0x1088]==0 → [+0x548]/[+0x5c8]
 * 状態注入 (10 状態) を fire/poll の前に書くので [+0x548] が status に追従することを両系で照合する。
 * 起火的 payload string は SSO (cap=7, len≤7) で 0x18010c010 の inline リセット経路を通す。 */
static u32 emfire_pick_status(int t, int k) {
    static const u32 st[10] = {0, 5, 7, 8, 9, 13, 22, 25, 26, 40};
    return st[(t * 3 + k * 7) % 10];
}

static void trial_emfire(int t) {
    EmObj o;
    em_setup(t, &o);
    REGION("mgrslot", (void*)MGR_SLOT, 0x40);
    *(u64*)(o.X + 0x100) = (u64)o.EM;             /* X = writer の ctx ([X+0x100]=EM) */
    u8* fn = A(0x10);                             /* functor {callback VA, i32 0} (ctor と同じ形) */
    *(u64*)fn = EM_WRITER;
    *(u32*)(fn + 8) = 0;
    u8* str = A(0x20);                            /* 通知 payload: SSO std::string {u8[16], len, cap=7} */
    for (int i = 0; i < 16; i++) str[i] = 0;
    *(u64*)(str + 0x10) = 4;
    *(u64*)(str + 0x18) = 7;
    *(u32*)A_STATUS = 9;
    C7(EM_CTOR, RET_I64, o.EM, o.sp2, o.SUB, o.sp4, o.sp5, o.desc, o.p7);   /* subscribe 実登録 */
    C3(EM_REGISTER, RET_NONE, (u64)o.EM + 0x1b0, o.X, fn);   /* writer observer 登録 (editor doc ctor 0x18002dc30 と同: [doc+0x100]+0x1b0 = EM+0x1b0) */
    for (int k = 0; k < 4; k++) {
        u32 s = emfire_pick_status(t, k);
        *(u32*)A_STATUS = s;                       /* LicenseManager 状態変化 (seam: getStatus) */
        *(u32*)(o.SUB + 0x1088) = (R32() % 3 == 0) ? 1 : 0;
        *(u32*)(o.SUB + 0x548) = R32() & 1;
        C2(EM_FIRE, RET_NONE, MGR_SLOT, str);      /* EventSlot 起火 → poll1 → writer */
        C1(EM_POLL1, RET_NONE, o.EM);
        C1(EM_POLL2, RET_NONE, o.EM);
    }
}

#endif
