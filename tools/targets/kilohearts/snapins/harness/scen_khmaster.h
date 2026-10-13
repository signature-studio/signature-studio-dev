/* scen_khmaster.h — CAB-56: SnapinMasterDsp ホストハーネス (vtable dispatch 4種の unit-diff)。
 *
 * 対象 (KH-4 で lift+[icall] 済・unit-diff 未実施だった 4 関数):
 *   sp_release        0x18004f350  dirty record ヒープからの pop + shared_ptr release (小路線 / 大路線=再帰+0bb0+f860)
 *   sp_destroy_walker 0x180050860  ヒープ replace + displaced shared_ptr release
 *   dirty_notify      0x18004df70  [master+0xa8]==1 で 201 個の dirty record を走査 (vtable +8/+0x10/+0x18 dispatch,
 *                                  ctx_set2f 直接呼び, ctrl release (destroy/delete dispatch), 接続 append, pending push)
 *   param_map_notify  0x18004d980  dirty record 群の modulation 合算 (route map [vt+0x18], ctx_getidx, ring 補間)
 *
 * 実オブジェクト契約 (機械語から確定したレイアウト, アリーナ上に構築):
 *   master+0x00 vtable (+0x10 = sp_get_shared 0x1800fb920, +0x18 = route_map_get 0x1800065e0)
 *   master+0x08 container T (T[0] = VT: VT[0x10+i*0x20] = param obj, VT[0x18+i*0x20] = i32 idx)
 *   master+0x10/0x18 int 配列 begin/end (n = 0x100), master+0x28 状態配列 (0x20/entry)
 *   master+0x78/80/88 pending vec<int> (cap満杯で vec_push 経路), master+0x90/98 接続 vec<int>
 *   master+0xa8 flag (1 で有効), master+0xac counter, master+0xb0.. dirty record ×201 (0x20 stride)
 *   record = { i32 id@0 (hi16=ring id), u16 kind@4, u16 param@6, i32 slot@8, u32 y@C,
 *              ptr elem@0x10 (obj2 契約: +0x2c8 chain / +0x768,+0x780), ptr ctrl@0x18 }
 *   ctrl block = { vtable@0, ref@8, weak@C, ...0x800B } — vtable+8 = destroy, +0x10 = delete (op_delete 実物)
 *   route table (master+0x1b30, 0x38×100): [rt+8+0x38k] = block_k ({i32 a, u32 b} と modrec の二重ビュー),
 *     [rt+0x38p] = i32 idx, [rt+0x38p+0x18] = float block ([+0x44] を読む)
 *
 * dispatch 先はすべて khbase lift 済の実関数 VA (アリーナ vtable → kh_icall が実値を読んで dispatch)。
 * destroy: class A = ctx_set2f (r9 が scenario 制御値の経路, アリーナ可視) / class B = 0x180f87f24
 *          (r9 がワイルドになる経路 = f860/0bb0/f350 大路線・df70 後半。引数無視で安全)。
 * delete  = op_delete 0x180fd4f30 (HeapFree IAT shim 経路の実物)。
 */
#ifndef SCEN_KHMASTER_H
#define SCEN_KHMASTER_H
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include "scen_common.h"

typedef uint64_t u64; typedef uint32_t u32; typedef uint16_t u16; typedef uint8_t u8; typedef int32_t i32;

#define F_SP_RELEASE 0x18004f350ULL
#define F_SP_WALKER  0x180050860ULL
#define F_DIRTY      0x18004df70ULL
#define F_INTERP     0x180006500ULL
#define F_RINGDRV    0x1804faa80ULL
#define F_GETSHARED  0x1800fb920ULL
#define F_ROUTEGET   0x1800065e0ULL
#define F_GETIDX     0x1800fb8c0ULL
#define F_SET2F      0x1800fb8f0ULL
#define F_DESTR_B    0x180f87f24ULL
#define F_OP_DELETE  0x180fd4f30ULL

#define NREC   201                     /* master+0xb0 の record 数 */
#define NROUTE 100                     /* route table エントリ数 (0x38 stride) */
#define NPARAM_MAX 0x100               /* param / cid / idx 上限 (buffer index = n = 0x100) */

#ifndef __EMSCRIPTEN__
/* ---- native のみ: IAT slot を同意味 shim へ patch (scen_khmath.h と同一実装・別名) ---- */
static int khb_heap_mapped = 0;
u64 __attribute__((ms_abi)) khb_HeapAlloc(u64 h, u32 flags, u64 bytes) {
    (void)h; (void)flags;
    u64 cur = *(u64*)0x04000100ULL;
    if (!cur) cur = 0x05000010ULL;
    u64 a = (cur + 15) & ~(u64)15;
    if (bytes > 0x100000ULL) return 0;
    u64 n = (bytes + 15) & ~(u64)15;
    if (a + n > 0x05100000ULL) return 0;
    unsigned char* m = (unsigned char*)a;
    for (u64 i = 0; i < n; i++) m[i] = 0;
    *(u64*)0x04000100ULL = a + n;
    return a;
}
u64 __attribute__((ms_abi)) khb_HeapFree(u64 h, u32 f, u64 p) { (void)h; (void)f; (void)p; return 1; }
u64 __attribute__((ms_abi)) khb_GetLastError(void) { return 0; }
u64 __attribute__((ms_abi)) khb_SetLastError(u64 e) { (void)e; return 0; }
u64 __attribute__((ms_abi)) khb_CS(u64 p) { (void)p; return 0; }
u64 __attribute__((ms_abi)) khb_IsPFP(u64 f) { (void)f; return 1; }
u64 __attribute__((ms_abi)) khb_IsDbg(void) { return 0; }
u64 __attribute__((ms_abi)) khb_GetCurProc(void) { return 0xffffffffffffffffULL; }
u64 __attribute__((ms_abi)) khb_FlsGet(u64 i) { (void)i; return 0x04000200ULL; }
u64 __attribute__((ms_abi)) khb_FlsSet(u64 i, u64 v) { (void)i; (void)v; return 1; }
u64 __attribute__((ms_abi)) khb_Term(u64 h, u32 c) { (void)h; (void)c; return 1; }
u64 __attribute__((ms_abi)) khb_GetModH(u64 n) { (void)n; return 0; }
u64 __attribute__((ms_abi)) khb_FreeLib(u64 m) { (void)m; return 1; }
u64 __attribute__((ms_abi)) khb_GetProcAddr(u64 m, u64 n) { (void)m; (void)n; return 0; }
u64 __attribute__((ms_abi)) khb_GetModHEx(u32 f, u64 n, u64* o) { (void)f; (void)n; if (o) *o = 0; return 0; }
u64 __attribute__((ms_abi)) khb_LoadLibExW(u64 n, u64 h, u32 f) { (void)n; (void)h; (void)f; return 0; }
u64 __attribute__((ms_abi)) khb_RaiseException(u64 a, u32 b, u32 c, u64 d) { (void)a; (void)b; (void)c; (void)d; return 1; }
u64 __attribute__((ms_abi)) khb_SetUHF(u64 h) { (void)h; return 0; }
u64 __attribute__((ms_abi)) khb_UHF(u64 e) { (void)e; return 0; }

static void khb_patch_iats(void) {
    if (!khb_heap_mapped) {
        void* p = mmap((void*)0x05000000UL, 0x100000UL, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
        if (p != (void*)0x05000000UL && errno != EEXIST) { fprintf(stderr, "cannot map kh heap\n"); exit(4); }
        khb_heap_mapped = 1;
    }
    static const struct { u64 slot; void* fn; } T[] = {
        {0x1813a1748ULL, (void*)khb_HeapAlloc},
        {0x1813a1760ULL, (void*)khb_HeapFree},
        {0x1813a1790ULL, (void*)khb_GetLastError},
        {0x1813a12c0ULL, (void*)khb_SetLastError},
        {0x1813a1268ULL, (void*)khb_CS},
        {0x1813a1270ULL, (void*)khb_CS},
        {0x1813a1218ULL, (void*)khb_IsPFP},
        {0x1813a11f8ULL, (void*)khb_IsDbg},
        {0x1813a14b8ULL, (void*)khb_GetCurProc},
        {0x1813a1360ULL, (void*)khb_FlsGet},
        {0x1813a1368ULL, (void*)khb_FlsSet},
        {0x1813a1220ULL, (void*)khb_GetModH},
        {0x1813a11a8ULL, (void*)khb_FreeLib},
        {0x1813a11a0ULL, (void*)khb_GetProcAddr},
        {0x1813a16d8ULL, (void*)khb_GetModHEx},
        {0x1813a12f0ULL, (void*)khb_LoadLibExW},
        {0x1813a12f8ULL, (void*)khb_Term},
        {0x1813a1250ULL, (void*)khb_RaiseException},
        {0x1813a1208ULL, (void*)khb_SetUHF},
        {0x1813a1200ULL, (void*)khb_UHF},
    };
    for (unsigned k = 0; k < sizeof(T) / sizeof(T[0]); k++) *(u64*)T[k].slot = (u64)T[k].fn;
    *(u64*)0x05000000UL = 0;
}
#else
static void khb_patch_iats(void) {}
#endif

/* ---- 共有オブジェクト群 (trial 毎に再構築) ---- */
typedef struct {
    u8* vtM;      /* master vtable (arena): +0x10 getshared, +0x18 routemap */
    u8* vtA;      /* ctrl vtable class A: +8 = ctx_set2f, +0x10 = op_delete */
    u8* vtB;      /* ctrl vtable class B: +8 = 0x180f87f24, +0x10 = op_delete */
    u8* vtP;      /* param obj vtable: +8 = ctx_getidx */
    u8* obj2;     /* ctx_getidx / ctx_set2f の両契約を満たすオブジェクト */
    u8 *p1c, *p2c, *q, *iarr;         /* getidx chain: [obj2+0x2c8]=p1c, [p1c+8]=p2c, [p2c]=q, [p1c+0x10]=iarr */
    u8 *f1, *f2;                      /* obj2+0x768 / +0x780 の float 配列 */
    u8 *T, *VT;                       /* container: T[0]=VT */
    u8 *state, *begin;                /* master+0x28 / +0x10 の実体 */
    u8 *blocks, *fbs;                 /* route block ×100 (0x20), float block 群 */
    u8 *ctrls;                        /* ctrl block 群 (0x800 each) */
    u8 *master;                       /* 0x2e00 (khmaster) / 0x2b600 (khmring) */
    int nctrl;
} Ms;

#define MS_SZ      0x3100               /* +0x1b30 route table (0x15b8B) を含む */
#define MS_RING_SZ 0x2b600             /* +0x28d08 ring bank (0x810×5) を含む */
#define RT_OFF     0x1b30               /* route_map_get (= this+0x1b30) */

static int khb_inited = 0;
#ifndef __EMSCRIPTEN__
static u8 khb_teb[0x1000] __attribute__((aligned(4096)));
#endif
static void khb_init(void) {
    if (!khb_inited) {
        khb_patch_iats();
#ifndef __EMSCRIPTEN__
        /* native: PE 側の gs:[0x10] (= stack limit) / gs:[0x60] (= PEB) 参照のため ARCH_SET_GS で
         * ゼロ TEB を設定 (wasm [gs] pass のゼロ初期化エミュレート = StackLimit 0 → probe 不発 と同一) */
        syscall(SYS_arch_prctl, 0x1001 /* ARCH_SET_GS */, (unsigned long)khb_teb);
#endif
        khb_inited = 1;
    }
}

/* ctrl block: vt=vtA/vtB, ref/weak を設定 */static u8* khb_ctrl(Ms* m, int idx, u8* vt, u32 ref, u32 weak) {
    u8* c = m->ctrls + (size_t)idx * 0x800;
    *(u64*)(c + 0) = (u64)vt;
    *(u32*)(c + 8) = ref;
    *(u32*)(c + 0xc) = weak;
    for (int k = 0; k < 8; k++) *(float*)(c + 0x100 + 4 * k) = RF(-1, 1);
    /* ctx_set2f (destroy class A) の書込み先: block 内 +0x500 / +0x600 (r9d ≤ 0x3f)。
     * +0x2c8: getshared が返す elem が ctrl block になる経路 (R block append → d980 が ctx_getidx) の契約 */
    *(u64*)(c + 0x768) = (u64)(c + 0x500);
    *(u64*)(c + 0x780) = (u64)(c + 0x600);
    *(u64*)(c + 0x2c8) = (u64)m->p1c;
    for (int k = 0; k < 0x40; k++) { *(float*)(c + 0x500 + 4 * k) = RF(-1, 1); *(float*)(c + 0x600 + 4 * k) = RF(-1, 1); }
    return c;
}

static void khb_build(Ms* m, int nctrl, int ms_sz) {
    m->nctrl = nctrl;
    m->vtM = A(0x20);
    *(u64*)(m->vtM + 0x00) = F_DESTR_B;
    *(u64*)(m->vtM + 0x08) = F_GETIDX;
    *(u64*)(m->vtM + 0x10) = F_GETSHARED;
    *(u64*)(m->vtM + 0x18) = F_ROUTEGET;
    m->vtA = A(0x20);
    *(u64*)(m->vtA + 0x00) = F_DESTR_B;
    *(u64*)(m->vtA + 0x08) = F_SET2F;
    *(u64*)(m->vtA + 0x10) = F_OP_DELETE;
    m->vtB = A(0x20);
    *(u64*)(m->vtB + 0x00) = F_DESTR_B;
    *(u64*)(m->vtB + 0x08) = F_DESTR_B;
    *(u64*)(m->vtB + 0x10) = F_OP_DELETE;
    m->vtP = A(0x20);
    *(u64*)(m->vtP + 0x00) = F_DESTR_B;
    /* get_value ([vt+8]): routemap_get (lea rax,[rcx+0x1b30]; ret) — メモリ読書き 0・全レジスタ非依存。
     * ctx_set2f は [this+0x768+4*r9d] 書込みで r9d が実機ループ内では残留ポインタ値になり OOB (実測 SEGV)
     * のため不採用。df70 ループは [rsp+0x2c] を call 前に 0 初期化するため out 値は両系 0 で決定的。 */
    *(u64*)(m->vtP + 0x08) = F_ROUTEGET;
    /* getidx provider (obj2): ctx_getidx の +0x2c8 chain と ctx_set2f の +0x768/+0x780 を両方持つ
     * (+0x00 = vtable: df70 の get_value dispatch [vt+8] が obj2[0] を読む) */
    m->obj2 = A(0x800);
    m->p1c = A(0x40);
    m->p2c = A(0x40);
    m->q = A(0x1a00);                    /* q[0x18 + param*0x20]: param < 0xd0 */
    m->iarr = A(0x100);
    m->f1 = A(0x400);
    m->f2 = A(0x400);
    *(u64*)(m->obj2 + 0x000) = (u64)m->vtP;
    *(u64*)(m->obj2 + 0x2c8) = (u64)m->p1c;
    *(u64*)(m->p1c + 8) = (u64)m->p2c;
    *(u64*)(m->p2c + 0) = (u64)m->q;
    *(u64*)(m->p1c + 0x10) = (u64)m->iarr;
    *(u64*)(m->obj2 + 0x768) = (u64)m->f1;
    *(u64*)(m->obj2 + 0x780) = (u64)m->f2;
    for (int k = 0; k < 0x100; k++) *(float*)(m->f1 + 4 * k) = RF(-1, 1);
    for (int k = 0; k < 0x100; k++) *(float*)(m->f2 + 4 * k) = RF(-1, 1);
    /* container: T[0] = VT, VT[0x10+i*0x20] = param obj (= obj2), VT[0x18+i*0x20] = i32 idx */
    m->T = A(0x40);
    m->VT = A(0x1a00);
    *(u64*)(m->T + 0) = (u64)m->VT;
    for (int i = 0; i < NPARAM_MAX; i++) {
        *(u64*)(m->VT + 0x10 + i * 0x20) = (u64)m->obj2;
        *(i32*)(m->VT + 0x18 + i * 0x20) = RI(0, 0x30);
        *(i32*)(m->q + 0x18 + i * 0x20) = RI(0, 0x30);
    }
    for (int i = 0; i < 0x40; i++) *(i32*)(m->iarr + 4 * i) = RI(-100, 100);
    m->state = A(0x1a00);
    m->begin = A(0x400);
    for (int i = 0; i < 0x100; i++) *(float*)(m->state + i * 0x20 + 4) = RF(-1, 1);
    /* route block ×100: {i32 a@0, u32 b@4, f32@8, f32@C, f32 0@0x10, u8 en@0x14} */
    m->blocks = A(0x20 * NROUTE);
    m->fbs = A(0x48 * 8);
    m->ctrls = A((size_t)nctrl * 0x800);
    m->master = A((size_t)ms_sz);
    REGION("master", m->master, ms_sz);
    REGION("state", m->state, 0x1a00);
    REGION("begin", m->begin, 0x400);
    REGION("VT", m->VT, 0x1a00);
    REGION("obj2", m->obj2, 0x800);
    REGION("q", m->q, 0x1a00);
    REGION("f1", m->f1, 0x400);
    REGION("f2", m->f2, 0x400);
    REGION("blocks", m->blocks, 0x20 * NROUTE);
    REGION("fbs", m->fbs, 0x48 * 8);
    REGION("ctrls", m->ctrls, (size_t)nctrl * 0x800);
}

/* dirty record を書く (kind: 0xffff / 0xfffd / other / 0) */
static void khb_rec(u8* base, int i, u32 id, u16 kind, u16 param, i32 slot, u8* elem, u8* ctrl) {
    u8* r = base + (size_t)i * 0x20;
    *(u32*)(r + 0) = id;
    *(u16*)(r + 4) = kind;
    *(u16*)(r + 6) = param;
    *(i32*)(r + 8) = slot;
    *(u32*)(r + 0xc) = 0;
    *(u64*)(r + 0x10) = (u64)elem;
    *(u64*)(r + 0x18) = (u64)ctrl;
}

/* route table 設置 (khmaster/khmring 共通。block の a/b と modrec ビューは二重) */
static void khb_route(Ms* m, int ring_en, u32 seed) {
    u8* rt = m->master + RT_OFF;
    for (int k = 0; k < NROUTE; k++) {
        u8* b = m->blocks + (size_t)k * 0x20;
        *(i32*)(b + 0) = 0;
        *(u32*)(b + 4) = 0;
        *(float*)(b + 8) = RF(-1, 1);
        *(float*)(b + 0xc) = RF(-1, 1);
        *(float*)(b + 0x10) = 0.0f;
        *(u8*)(b + 0x14) = (u8)(ring_en ? 1 : 0);
        *(u64*)(rt + 8 + (size_t)k * 0x38) = (u64)b;
    }
    /* df70 / d980 が fire する 3 block (P: pending push, Q: 0xfffd idx push, R: append+getshared) */
    *(i32*)(m->blocks + 0x00) = 0x0000ffff; *(u32*)(m->blocks + 0x04) = (20u << 16) | 0xffffu;
    *(i32*)(m->blocks + 0x20) = 0x0000ffff; *(u32*)(m->blocks + 0x24) = (21u << 16) | 0xfffdu;
    *(i32*)(m->blocks + 0x40) = 0x0000ffff; *(u32*)(m->blocks + 0x44) = (22u << 16) | 1u;
    /* [rt + p*0x38] = i32 idx (0xfffd 経路の書込み先 index), [rt+0x38p+0x18] = float block ([+0x44]) */
    int ps[4] = {5, 6, 7, 21};
    for (int j = 0; j < 4; j++) {
        int p = ps[j];
        *(i32*)(rt + (size_t)p * 0x38) = 0x10 + 4 * j + (int)(seed & 3);
        *(u64*)(rt + (size_t)p * 0x38 + 0x18) = (u64)(m->fbs + (size_t)j * 0x48);
        *(float*)(m->fbs + (size_t)j * 0x48 + 0x44) = RF(0.01f, 2.0f);
    }
    /* slot = -1 (append 済 record) の fallback modrec: [rt-0x30] = master+0x1b00 */
    *(u64*)(m->master + RT_OFF - 0x30) = (u64)(m->blocks + 3 * 0x20);
}

/* master 本体の field 設置 + record 群 */
static void khb_master(Ms* m, int flag, u32 idbase) {
    u8* M = m->master;
    *(u64*)(M + 0x00) = (u64)m->vtM;
    *(u64*)(M + 0x08) = (u64)m->T;
    *(u64*)(M + 0x10) = (u64)m->begin;
    *(u64*)(M + 0x18) = (u64)(m->begin + 0x400);      /* n = 0x100 */
    *(u64*)(M + 0x28) = (u64)m->state;
    u8* pend = A(0x40);                                /* pending vec: 満杯 (vec_push 経路) */
    *(u64*)(M + 0x78) = (u64)pend;
    *(u64*)(M + 0x80) = (u64)(pend + 0x40);
    *(u64*)(M + 0x88) = (u64)(pend + 0x40);
    u8* conn = A(0x20);                                /* 接続 vec: 2 id */
    *(i32*)(conn + 0) = 200;
    *(i32*)(conn + 4) = 20;
    *(u64*)(M + 0x90) = (u64)conn;
    *(u64*)(M + 0x98) = (u64)(conn + 8);
    *(u8*)(M + 0xa8) = (u8)flag;
    *(u32*)(M + 0xac) = 0;
    REGION("pend", pend, 0x40);
    REGION("conn", conn, 0x20);
    /* record 群: B_0..B_4 は 0xffff (df70 先頭ループ + append で上書きされる枠),
     * B_5..B_7 = 0xfffd (d980 の obj2 → ctx_getidx 経路), B_8/B_9 = other (ctrl release),
     * B_10 = 0 (終端), B_15.ctrl = getshared の供給元 C15 */
    khb_rec(M + 0xb0, 0, idbase + 1, 0xffff, 3, 0, m->obj2, 0);
    khb_rec(M + 0xb0, 1, idbase + 2, 0xffff, 4, 0, m->obj2, 0);
    khb_rec(M + 0xb0, 2, idbase + 3, 0xffff, 3, 0, m->obj2, 0);
    khb_rec(M + 0xb0, 3, idbase + 4, 0xffff, 11, 0, m->obj2, 0);
    khb_rec(M + 0xb0, 4, idbase + 5, 0xffff, 12, 0, m->obj2, 0);
    khb_rec(M + 0xb0, 5, idbase + 6, 0xfffd, 5, 0, m->obj2, 0);
    khb_rec(M + 0xb0, 6, idbase + 7, 0xfffd, 6, 1, m->obj2, 0);
    khb_rec(M + 0xb0, 7, idbase + 8, 0xfffd, 7, 2, m->obj2, 0);
    khb_rec(M + 0xb0, 8, idbase + 9, 2, 8, 0, m->obj2, khb_ctrl(m, 0, m->vtA, 1, 1));
    khb_rec(M + 0xb0, 9, idbase + 10, 2, 9, 0, 0, khb_ctrl(m, 1, m->vtA, 2, 3));
    khb_rec(M + 0xb0, 10, 0, 0, 0, 0, 0, 0);
    khb_rec(M + 0xb0, 15, 0, 0, 0, 0, 0, khb_ctrl(m, 2, m->vtA, 7, 7));   /* B_15.ctrl = C15 */
}

/* ---- khmrel: sp_release (小路線/大路線) + sp_destroy_walker の直接差分 ---- */
static u8* khb_recs(int n, Ms* m, int clsA, u32 hkey) {
    u8* recs = A((size_t)n * 0x20);
    REGION("recs", recs, (size_t)n * 0x20);
    *(u32*)(recs + 4) = hkey & 0xffff;
    *(u32*)(recs + 6) = (hkey >> 16) & 0xffff;
    for (int i = 1; i < n; i++) {
        u16 k1 = RI(0, 0xfff), k2 = RI(0, 0xfff);
        if (i == 3) { k1 = hkey & 0xffff; k2 = (hkey >> 16) & 0xffff; }   /* header key と一致 → remove 経路 */
        *(u32*)(recs + (size_t)i * 0x20 + 0) = RI(0, 0xffffff);
        *(u16*)(recs + (size_t)i * 0x20 + 4) = k1;
        *(u16*)(recs + (size_t)i * 0x20 + 6) = k2;
        *(i32*)(recs + (size_t)i * 0x20 + 8) = RI(-100, 100);
        *(u64*)(recs + (size_t)i * 0x20 + 0x10) = (u64)m->obj2;
        *(u64*)(recs + (size_t)i * 0x20 + 0x18) =
            (u64)khb_ctrl(m, 3 + (i % (m->nctrl - 3)), clsA ? m->vtA : m->vtB, (u32)RI(0, 3), (u32)RI(0, 3));
    }
    return recs;
}

static void trial_khmrel(int t) {
    (void)t;
    khb_init();
    u8* hc = A(0x110); *(u64*)(hc + 0x100) = 0;
    Ms m;
    khb_build(&m, 3 + 16, 0x100);
    /* 小路線: span < 0x401 (≤32 record)。r9 = scenario a3 (=k%4, 界隈内) → class A (ctx_set2f destroy がアリーナ可視) */
    u32 hk = (u32)RI(1, 0xffff) | ((u32)RI(1, 0xffff) << 16);
    u8* rs = khb_recs(20, &m, 1, hk);
    do_call(F_SP_RELEASE, RET_NONE, (u64)rs, (u64)(rs + 20 * 0x20), (u64)(t % 20), (u64)(t % 4),
            0, fbits(RF(-1, 1)), fbits(RF(-1, 1)), 0);
    /* 大路線: span ≥ 0x401 → 再帰 + sp move-assign (0bb0) + walker (f860)。r9 がワイルド → class B */
    u32 hk2 = (u32)RI(1, 0xffff) | ((u32)RI(1, 0xffff) << 16);
    u8* rb = khb_recs(40, &m, 0, hk2);
    do_call(F_SP_RELEASE, RET_NONE, (u64)rb, (u64)(rb + 40 * 0x20), (u64)(t % 39), 0, 0, 0, 0, 0);
    /* walker 直接: (recs, start, count, &newrec) — newrec の ctrl は fresh (ref1/weak1 で置換先 release を発火) */
    u8* rw = khb_recs(32, &m, 0, (u32)RI(1, 0xffff));
    u8* nr = A(0x20);
    *(u32*)(nr + 0) = RI(0, 0xffffff);
    *(u16*)(nr + 4) = (u16)RI(0, 0xfff);
    *(u16*)(nr + 6) = (u16)RI(0, 0xfff);
    *(i32*)(nr + 8) = RI(-100, 100);
    *(u64*)(nr + 0x10) = (u64)m.obj2;
    *(u64*)(nr + 0x18) = (u64)khb_ctrl(&m, 3 + (t % (m.nctrl - 3)), m.vtB, 1, 1);
    REGION("newrec", nr, 0x20);
    do_call(F_SP_WALKER, RET_NONE, (u64)rw, (u64)(1 + t % 16), (u64)(32), (u64)nr, 0, 0, 0, 0);
}

/* ---- khmaster: dirty_notify + (interp driver による) param_map_notify, 簡易 path (r8=0) ---- */
static void trial_khmaster(int t) {
    khb_init();
    u8* hc = A(0x110); *(u64*)(hc + 0x100) = 0;
    Ms m;
    khb_build(&m, 3 + 8, MS_SZ);
    khb_route(&m, 0, (u32)t);
    khb_master(&m, (t % 4 != 2) ? 1 : 0, (u32)t * 0x100);
    /* ctx2: d980 が [+0x30]/[+0x38] の float 配列を読む */
    u8* ctx2 = A(0x40);
    *(u64*)(ctx2 + 0x30) = (u64)m.f1;
    *(u64*)(ctx2 + 0x38) = (u64)m.f2;
    REGION("ctx2", ctx2, 0x40);
    C1(F_DIRTY, RET_NONE, (u64)m.master);
    C2(F_INTERP, RET_NONE, (u64)m.master, (u64)ctx2);   /* df70 (flag 0 なら epilogue のみ) + d980 ループ */
}

/* ---- khmring: ring driver (0x1804faa80) による modulation 経路 (r8 = ring bank) ---- */
static void trial_khmring(int t) {
    khb_init();
    u8* hc = A(0x110); *(u64*)(hc + 0x100) = 0;
    Ms m;
    khb_build(&m, 3 + 8, MS_RING_SZ);
    khb_route(&m, 1, (u32)t);
    khb_master(&m, (t % 5 != 4) ? 1 : 0, (u32)t * 0x100);
    u8* ctx2 = A(0x40);
    *(u64*)(ctx2 + 0x30) = (u64)m.f1;
    *(u64*)(ctx2 + 0x38) = (u64)m.f2;
    REGION("ctx2", ctx2, 0x40);
    /* ring bank at master+0x28d08: ring j = bank + j*0x810, 128 slot ×16B (+0x10 f32 値, +0x18 qword ts) */
    u8* bank = m.master + 0x28d08;
    REGION("ringbank", bank, 0x810 * 5);
    for (int j = 0; j < 5; j++) {
        u8* ring = bank + (size_t)j * 0x810;
        int mode = (t + j) % 4;
        *(u32*)(ring + 0) = (u32)(j % 8);                      /* head */
        *(u64*)(ring + 8) = (u64)((mode == 2) ? 0x8 : 0x2000 + (t & 7) * 0x10);   /* 現在時刻 */
        for (int k = 0; k < 128; k++) {
            *(float*)(ring + 0x10 + k * 0x10) = RF(-1, 1);
            *(u64*)(ring + 0x18 + k * 0x10) = (u64)((mode == 3) ? 0x40 : (u64)(k + 1) * 0x40);
        }
    }
    /* record の ring id (id hi16) を 0..4 に散らす */
    for (int i = 0; i < 10; i++) {
        u8* r = m.master + 0xb0 + (size_t)i * 0x20;
        *(u32*)(r + 0) = ((u32)(i % 5) << 16) | (*(u32*)(r + 0) & 0xffff);
    }
    C3(F_RINGDRV, RET_NONE, (u64)m.master, (u64)ctx2, 0);
}

#endif /* SCEN_KHMASTER_H */
