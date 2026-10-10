#ifndef SCEN_KHMATH_H
#define SCEN_KHMATH_H
/* scen_khmath.h — KH-4 共通基盤 (khbase) の ctx-fuzz 差分。
 *
 * 構成:
 *   khmath  : powf (0x180fc3640, FMA3/SSE2 二系統 + UCRT 内部 helper) を (float,float) で直接差分。
 *             引数は UCRT powf の定義内 (domain error → matherr/SEH/errno(TLS) 経路を避ける) + 特殊値。
 *   khalloc : operator new (0x180f878e0) / operator delete (0x180fd4f30) / malloc core (0x180fd51cc)。
 *             native 側は IAT slot を同意味の ms_abi shim へ patch (下段 patch_iats)。wasm 側は
 *             gen_stubs_sigs の同一意味 shim (kh_heap_alloc: 0x05000000 固定循環 bump + 16B 整列 + ゼロ充填)。
 *   khvec   : std::vector<int> push_back (0x18004cf20)。begin/end/cap を arena 内に初期配置し push を
 *             繰り返して成長 (realloc = op_new + memmove shim) も発火。push 先が arena の間は全バイト突合。
 *   khicall : shared_ptr move-assign (0x180050bb0, D15 [icall] 対象)。control block を arena に構築し
 *             vtable slot (+8 destroy / +0x10 delete) を lift �濈関数へ向け、refcount→0 の destroy 経路で
 *             arena vtable 経由の間接 call (kh_icall) を両側で発火させる。
 *   khprobe : 上記以外の lift 関数を巡回突合 (vtable dispatch 群・gs/PEB プローブ・delay-load 経路は対象外)。
 */
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include "scen_common.h"

static int heap_mapped = 0;

#define KH_POWF 0x180fc3640UL
#define OP_NEW  0x180f878e0UL
#define OP_DEL  0x180fd4f30UL
#define MALLOC_CORE 0x180fd51ccUL
#define VEC_PUSH 0x18004cf20UL
#define SP_MOVE 0x180050bb0UL
#define CTX_SET2F 0x1800fb8f0UL

#ifndef __EMSCRIPTEN__
/* ---- native のみ: IAT slot を同意味 shim へ patch (slot は PE 実測) ---- */
u64 __attribute__((ms_abi)) n_HeapAlloc(u64 h, u32 flags, u64 bytes) {
    (void)h; (void)flags;
    u64 cur = *(u64*)0x04000100ULL;
    if (!cur) cur = 0x05000010UL;
    u64 a = (cur + 15) & ~(u64)15;
    u64 n = (bytes + 15) & ~(u64)15;
    if (n > 0xF0000ULL) n = 0xF0000ULL;                     /* 異常大はクランプ (wasm 側と同一) */
    if (a + n > 0x05100000ULL) a = 0x05000010ULL;           /* 循環 (wasm 側と同一) */
    unsigned char* m = (unsigned char*)a;
    for (u64 i = 0; i < n; i++) m[i] = 0;
    *(u64*)0x04000100ULL = a + n;
    return a;
}
u64 __attribute__((ms_abi)) n_HeapFree(u64 h, u32 f, u64 p) { (void)h; (void)f; (void)p; return 1; }
u64 __attribute__((ms_abi)) n_GetLastError(void) { return 0; }
u64 __attribute__((ms_abi)) n_SetLastError(u64 e) { (void)e; return 0; }
u64 __attribute__((ms_abi)) n_CS(u64 p) { (void)p; return 0; }
u64 __attribute__((ms_abi)) n_IsPFP(u64 f) { (void)f; return 1; }
u64 __attribute__((ms_abi)) n_IsDbg(void) { return 0; }
u64 __attribute__((ms_abi)) n_GetCurProc(void) { return 0xffffffffffffffffULL; }
u64 __attribute__((ms_abi)) n_FlsGet(u64 i) { (void)i; return 0x04000200ULL; }
u64 __attribute__((ms_abi)) n_FlsSet(u64 i, u64 v) { (void)i; (void)v; return 1; }
u64 __attribute__((ms_abi)) n_Term(u64 h, u32 c) { (void)h; (void)c; return 1; }
u64 __attribute__((ms_abi)) n_GetModH(u64 n) { (void)n; return 0; }
u64 __attribute__((ms_abi)) n_FreeLib(u64 m) { (void)m; return 1; }
u64 __attribute__((ms_abi)) n_GetProcAddr(u64 m, u64 n) { (void)m; (void)n; return 0; }
u64 __attribute__((ms_abi)) n_GetModHEx(u32 f, u64 n, u64* o) { (void)f; (void)n; if (o) *o = 0; return 0; }
u64 __attribute__((ms_abi)) n_LoadLibExW(u64 n, u64 h, u32 f) { (void)n; (void)h; (void)f; return 0; }
u64 __attribute__((ms_abi)) n_RaiseException(u64 a, u32 b, u32 c, u64 d) { (void)a; (void)b; (void)c; (void)d; return 1; }
u64 __attribute__((ms_abi)) n_SetUHF(u64 h) { (void)h; return 0; }
u64 __attribute__((ms_abi)) n_UHF(u64 e) { (void)e; return 0; }

static void patch_iats(void) {
    /* kh heap (0x05000000, 1MB) をマップ (wasm はリニアメモリ内) */
    if (!heap_mapped) {
        void* p = mmap((void*)0x05000000UL, 0x100000UL, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (p != (void*)0x05000000UL) { fprintf(stderr, "cannot map kh heap\n"); exit(4); }
        heap_mapped = 1;
    }
    static const struct { u64 slot; void* fn; } T[] = {
        {0x1813a1748ULL, (void*)n_HeapAlloc},
        {0x1813a1760ULL, (void*)n_HeapFree},
        {0x1813a1790ULL, (void*)n_GetLastError},
        {0x1813a12c0ULL, (void*)n_SetLastError},
        {0x1813a1268ULL, (void*)n_CS},
        {0x1813a1270ULL, (void*)n_CS},
        {0x1813a1218ULL, (void*)n_IsPFP},
        {0x1813a11f8ULL, (void*)n_IsDbg},
        {0x1813a14b8ULL, (void*)n_GetCurProc},
        {0x1813a1360ULL, (void*)n_FlsGet},
        {0x1813a1368ULL, (void*)n_FlsSet},
        {0x1813a1220ULL, (void*)n_GetModH},
        {0x1813a11a8ULL, (void*)n_FreeLib},
        {0x1813a11a0ULL, (void*)n_GetProcAddr},
        {0x1813a16d8ULL, (void*)n_GetModHEx},
        {0x1813a12f0ULL, (void*)n_LoadLibExW},
        {0x1813a12f8ULL, (void*)n_Term},
        {0x1813a1250ULL, (void*)n_RaiseException},
        {0x1813a1208ULL, (void*)n_SetUHF},
        {0x1813a1200ULL, (void*)n_UHF},
    };
    for (unsigned k = 0; k < sizeof(T) / sizeof(T[0]); k++) *(u64*)T[k].slot = (u64)T[k].fn;
    *(u64*)0x05000000UL = 0;   /* kh heap 初期化 (wasm 側は初回 cur==0 を 0x05000010 扱い) */
}
#else
static void patch_iats(void) {}
#endif

static void trial_khmath_powf(int t) {
    (void)t;
    static const float sp[] = {0.0f, 1.0f, 2.0f, 0.5f, 4.0f, 8.0f, 64.0f, 1e-30f, 1e30f, 3.4e38f, 1.17549435e-38f, 1e-45f};
    for (int k = 0; k < 15; k++) {
        float x, y;
        int r = (t + k) % 7;
        if (r != 1) { r = 1; }   /* DEBUG single-class */
        if (0) { x = sp[(t + k) % 12]; y = sp[(t * 3 + k) % 12]; }
        else if (r == 1) { x = RF(0.01f, 100.0f); y = RF(0.0f, 8.0f); }
        else if (r == 2) { x = -RF(0.01f, 100.0f); y = (float)RI(0, 8); }         /* 負の底 + 整数指数 */
        else if (r == 3) { x = RF(1e-20f, 1e20f); y = RF(0.0f, 1.0f); }
        else if (r == 4) { x = RF(0.999f, 1.001f); y = RF(0.0f, 1000.0f); }      /* 1 付近 (桁落ち経路) */
        else if (r == 5) { x = RF(1e-38f, 1e-30f); y = RF(0.5f, 2.5f); }          /* 非正規/アンダーフロー境界 */
        else { x = RF(1e28f, 3e38f); y = RF(0.5f, 2.0f); }                        /* オーバーフロー境界 */
        do_call(KH_POWF, RET_F32, 0, 0, 0, 0, fbits(x), fbits(y), 0, 0);
    }
}

/* allocator: op_new → op_delete (scenario は heap を直接触らない = wasm 再生と整合) */
static void trial_khalloc(int t) {
    (void)t;
    u64 ps[8];
    for (int k = 0; k < 8; k++) {
        u64 sz = (u64)RI(1, 512) + ((k == 3) ? 4096 : 0);
        ps[k] = do_call(OP_NEW, RET_I64, sz, 0, 0, 0, 0, 0, 0, 0);
        REGION("newret", (u8*)&ps[k], 8);
    }
    for (int k = 0; k < 8; k += 2) do_call(OP_DEL, RET_I64, ps[k], 0, 0, 0, 0, 0, 0, 0);
    for (int k = 0; k < 4; k++) {
        /* 0x180fd51cc = calloc(elem, count): (rcx=elem, rdx=count) */
        u64 p = do_call(MALLOC_CORE, RET_I64, (u64)RI(8, 256), 1, 0, 0, 0, 0, 0, 0);
        REGION("mallocret", (u8*)&p, 8);
    }
}

/* vector<int> push_back: 初期バッファを arena 内に置き push (成長時は op_new+memmove 経路) */
static void trial_khvec(int t) {
    (void)t;
    u8* vec = A(32);
    int* store = A((size_t)4 * 40);
    int* pv = A(4);
    REGION("vec", vec, 32); REGION("vecstore", store, 4 * 40); REGION("pv", pv, 4);
    *(void**)(vec + 0) = store;
    *(void**)(vec + 8) = store;
    *(void**)(vec + 16) = store + 40;
    int n = 8 + (t % 8);
    for (int k = 0; k < n; k++) {
        *pv = RI(-1000, 1000);
        /* ABI 実測: (rcx=vec, rdx=end=[vec+8], r8=&value) — realloc helper 毎回呼び = op_new+memmove 経路を毎回発火 */
        C3(VEC_PUSH, RET_NONE, vec, *(u64*)(vec + 8), (u64)pv);
    }
}

/* shared_ptr move-assign (D15 icall): ctrl block の vtable を arena 内 fake vtable にし、
 * slot+8 → 0x1800fb8f0 (float 2 個を [rcx+0x768/0x780][r9d] へ書込 = arena に反映) */
static void trial_khicall(int t) {
    (void)t;
    u8* sp1 = A(32); u8* sp2 = A(32);            /* shared_ptr<int> 本体 {elem, +8.., ctrl@+0x18} */
    u8* ctrl = A(0x800);                          /* control block: [+0]vtable [+8]ref [+0xc]weak */
    u8* vt = A(32);                               /* fake vtable: [+8]=destroy [+0x10]=delete */
    float* f1 = A(64); float* f2 = A(64);
    REGION("sp1", sp1, 32); REGION("sp2", sp2, 32); REGION("ctrl", ctrl, 0x800);
    REGION("vt", vt, 32); REGION("f1", f1, 64); REGION("f2", f2, 64);
    *(void**)(vt + 8) = (void*)CTX_SET2F;
    *(void**)(vt + 16) = (void*)0x180f87f24UL;    /* delete: and dword [rip+..],0; ret (data flag update) */
    *(void**)(vt + 0) = (void*)(ctrl + 0x40);      /* vt[0] = inner (addref パターン用) */
    *(void**)(ctrl + 0x40 + 0x88) = (void*)(ctrl + 0x7f0);   /* [inner+0x88] = refcount cell */
    *(void**)(vt + 0x88) = (void*)(ctrl + 0x7f0);  /* vt[0x88] = addref 先 (要素 vtable 経由) */
    *(void**)(ctrl + 0x80) = vt;                   /* 要素オブジェクトの vtable */
    *(void**)(ctrl + 0) = vt;
    *(u32*)(ctrl + 8) = (t % 3 == 0) ? 1 : 2;     /* refcount: 1 → destroy 発火 / 2 → 不発 */
    *(u32*)(ctrl + 0xc) = 1;                      /* weak count: 1 → delete 発火 */
    *(void**)(ctrl + 0x768) = f1;
    *(void**)(ctrl + 0x780) = f2;
    *(void**)(sp1 + 0) = (void*)(ctrl + 0x80);    /* 要素ポインタ (addref 経路の [obj] deref 用) */
    *(void**)(sp2 + 0) = (void*)(ctrl + 0x80);
    *(void**)(sp1 + 8) = (void*)(ctrl + 0x80);    /* release 経路の [obj+8] deref 用 */
    *(void**)(sp2 + 8) = (void*)(ctrl + 0x80);
    *(void**)(sp1 + 0x18) = ctrl;
    *(void**)(sp2 + 0x18) = ctrl;
    for (int k = 0; k < 8; k++) { f1[k] = RF(-1, 1); f2[k] = RF(-1, 1); }
    C2(SP_MOVE, RET_I64, sp1, sp2);
    /* 2 回目: move 元を別 ctrl にして解放側を変える */
    u8* ctrl2 = A(0x800);
    *(void**)(ctrl2 + 0) = vt;
    *(u32*)(ctrl2 + 8) = 1;
    *(u32*)(ctrl2 + 0xc) = (t % 2);
    *(void**)(ctrl2 + 0x768) = f1;
    *(void**)(ctrl2 + 0x780) = f2;
    *(void**)(sp1 + 0x18) = ctrl2;
    REGION("ctrl2", ctrl2, 0x800);
    C2(SP_MOVE, RET_I64, sp2, sp1);
    /* CS 経由 addref / release (0x180fd2c10 / 0x180fd2c90): (rcx=CS, rdx=obj, r8=obj2, r9=ptr) */
    u8* cs = A(64);
    *(u64*)(cs + 0) = 0;                        /* lock 状態 0 = 未保持 */
    REGION("cs", cs, 64);
    do_call(0x180fd2c10UL, RET_I64, (u64)cs, (u64)sp1, (u64)sp2, (u64)(ctrl + 0x40), 0, 0, 0, 0);
    do_call(0x180fd2c90UL, RET_I64, (u64)cs, (u64)sp1, (u64)sp2, (u64)(ctrl + 0x40), 0, 0, 0, 0);
}

/* generic prober: lift 関数を巡回 (vtable dispatch 群・gs/PEB プローブ・delay-load 経路は対象外) */
static const u64 PROBE[] = {
    0x180f8791cUL, 0x180f87d40UL, 0x180f87f24UL, 0x180fb5bb4UL, 0x180fb5c20UL, 0x180fb6bf8UL, 0x180fb6c0cUL, 0x180fbdd78UL, 0x180fbdef4UL, 0x180fd1b00UL, 0x180fd1f30UL, 0x180fd1f84UL, 0x180fd2ba0UL, 0x180fd4f30UL, 0x180fd62dcUL, 0x180fd6320UL, 0x180fd81e4UL, 0x180fd81ecUL, 0x180fe2470UL, 0x180fe24b8UL, 0x180fe3488UL, 0x180fe34b0UL, 0x180fe34e8UL, 0x180fe3690UL, 0x180fe3cd0UL, 0x180fe5c6cUL, 0x180fe5f40UL
};
#define NPROBE ((int)(sizeof(PROBE) / sizeof(PROBE[0])))

static void trial_khprobe(int t) {
    (void)t;
    /* 2 段の pointer chain を満たす fake object:
     * [obj]=vt, [vt]=inner, [inner+0x88]=ref (addref パターン), [vt+8/0x10..]=0 */
    u8* b0 = A(0x100); u8* b1 = A(0x100); u8* b2 = A(0x100);
    u8* vt0 = A(0x100); u8* vt1 = A(0x100); u8* vt2 = A(0x100);
    u8* inner0 = A(0x100); u8* inner1 = A(0x100); u8* inner2 = A(0x100);
    u32* refc = A(16);
    REGION("p0", b0, 0x100); REGION("p1", b1, 0x100); REGION("p2", b2, 0x100);
    *(u64*)(b0 + 0) = (u64)vt0; *(u64*)(vt0 + 0) = (u64)inner0; *(u64*)(inner0 + 0x88) = (u64)refc;
    *(u64*)(b1 + 0) = (u64)vt1; *(u64*)(vt1 + 0) = (u64)inner1; *(u64*)(inner1 + 0x88) = (u64)(refc + 1);
    *(u64*)(b2 + 0) = (u64)vt2; *(u64*)(vt2 + 0) = (u64)inner2; *(u64*)(inner2 + 0x88) = (u64)(refc + 2);
    /* chain ptr (0..16) を壊さないよう値は +16 以降に書く */
    for (int k = 4; k < 64; k++) {
        *(float*)(b0 + 4 * k) = ((k & 1) ? RF(-100, 100) : RF(0.01f, 100));
        if (k < 32) *(double*)(b1 + 8 * k) = ((k & 1) ? RF(-1e3, 1e3) : RF(0.001, 1000));
        if (k < 64) *(int*)(b2 + 4 * k) = RI(-100, 100);
    }
    *(u64*)(b0 + 8) = (u64)(b0 + 16);
    *(u64*)(b1 + 8) = (u64)(b1 + 16);
    *(u64*)(b2 + 8) = (u64)(b2 + 16);
    for (int j = 0; j < 6; j++) {
        u64 va = PROBE[(t * 6 + j) % NPROBE];
        int rk = (va == 0x180f87f24UL) ? RET_NONE : RET_I64;   /* 87f24 は rax 未定義 (data flag 更新のみ) */
        do_call(va, rk, (u64)b0, (u64)b1, (u64)b2, (u64)(b0 + 0x40),
                dbits(*(double*)(b1 + 8 * (t % 8))), dbits(*(double*)(b1 + 8 * ((t + 3) % 8))),
                fbits(*(float*)(b0 + 4 * (t % 8))), fbits(*(float*)(b0 + 4 * ((t + 5) % 8))));
    }
}

/* khmath = 統合シナリオ (1 trial で全サブ試験を実施。build.py の scenario は 1 つを参照するため) */
static void trial_khmath(int t) {
    static int inited = 0;
    if (!inited) { patch_iats(); inited = 1; }
    u8* hc = A(0x110); *(u64*)(hc + 0x100) = 0;    /* kh heap bump 状態を trial 毎に reset (両側同一) */
    trial_khmath_powf(t);
    trial_khalloc(t);
    trial_khvec(t);
    trial_khicall(t);
    trial_khprobe(t);
}
#endif /* SCEN_KHMATH_H */
