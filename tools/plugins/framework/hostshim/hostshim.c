/* hostshim.c — TFruityHost shim 実装 (CAB-195, P0b Host shim).
 *
 * 方針 (チケット CAB-195 + tools/shimx 方針の踏襲):
 *   * slot0 = Dispatcher(Host, HostTag, ID, Index, Value) — ID で分岐する唯一の窓口。
 *     Balance 初期化連鎖が発行する ID (0x47/0x56/0x0d) は機械実測 (ABI.md §6, pedis.py) に基づき応答。
 *     A検収上位 35 ID (hostshim/hs_ids.json: 894 site, cover 89.8%) は
 *     「戻り値使用クラス」実測 (store/reg = Host オブジェクト, ignore/test = 0) に基づき応答。
 *   * その他の slot は fail-soft + 呼出記録 (応答 0)。trap/abort しない。
 *   * 引数は icall memory-ABI (BLK+8=rcx, +0x10=rdx, +0x18=r8, +0x20=r9) から復元。
 *     第5引数 (Dispatcher の Value = [rsp+0x20]) は BLK-ABI が 4 整数引数までしか運ばないため未経由
 *     (fw_table.py ARG_SLOTS 4 個 — integration/README §4 既知制約)。連鎖内の全発行 site は
 *     Value=0 を store している (pedis.py 実測) ので動作影響は無い (REPORT §制限)。
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <emscripten.h>
#include "hostshim.h"

#ifndef FW_BLK
#define FW_BLK 0x8A1000u
#endif
#define BLKQ(off) (*(volatile uint64_t *)(uintptr_t)(FW_BLK + (off)))

#define HS_REC_N 512
#define HSVA(s) ((uint64_t)(HS_VA_BASE + 8u * (s)))

/* ---- TFruityHost vtable (plugin から見た 46 slot) ----
 * FLE 実装 VA は inventory/delphi_vmt.py block00031 0x1314108 の再生成値 (2026-10-10 実測):
 *   plugin offset 0x00..0x168 = VMT+0x70..VMT+0x1D8, slot0 = 0x13173a0 (Dispatcher) */
static const uint32_t g_fle_impl[HS_SLOTS] = {
    0x13173a0, 0x132a7b0, 0x132a860, 0x132ac90, 0x132aea0, 0x132aec0, /* 0..5  */
    0x132aee0, 0x132b0e0, 0x132b100, 0x132a910, 0x132ab40, 0x132acc0, /* 6..11 */
    0x132ad20, 0x132b230, 0x132b5b0, 0x132b940, 0x132b960, 0x132b970, /* 12..17*/
    0x132b980, 0x132b990, 0x132b9e0, 0x132ac50, 0x132ac60, 0x132b610, /* 18..23*/
    0x132ad80, 0x132ba50, 0x132b9f0, 0x132bc30, 0x132b160, 0x132b1c0, /* 24..29*/
    0x132b7c0, 0x132ac70, 0x132b1f0, 0x132b210, 0x132b120, 0x132b130, /* 30..35*/
    0x132ba60, 0x132bb10, 0x132b190, 0x132a850, 0x132a830, 0x132a840, /* 36..41*/
    0x132be10, 0x132b140, 0x132b1a0, 0x132c0f0                        /* 42..45*/
};

static uint64_t g_hs_vtable[HS_SLOTS];
static uint64_t g_hs_obj[40];            /* 296B (InstanceSize 296 実測) + 余裕 */
static volatile int g_hs_installed;

/* ---- 呼出記録 ---- */
static hs_rec g_hs_rec[HS_REC_N];
static unsigned long long g_hs_cnt;      /* 累積 (飽和しない) */
static int g_hs_trace = 1;

EMSCRIPTEN_KEEPALIVE void fw_hs_trace(int on) { g_hs_trace = on; }
EMSCRIPTEN_KEEPALIVE void fw_hs_reset(void) { g_hs_cnt = 0; memset(g_hs_rec, 0, sizeof g_hs_rec); }
EMSCRIPTEN_KEEPALIVE int fw_hs_count(void) { return (int)(g_hs_cnt > 0xFFFFFFFFull ? 0xFFFFFFFFull : g_hs_cnt); }
EMSCRIPTEN_KEEPALIVE void *fw_hs_records(void) { return g_hs_rec; }

static void hs_rec_put(uint32_t slot, uint32_t id, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t ret) {
    unsigned long long k = g_hs_cnt++;
    hs_rec *r = &g_hs_rec[k % HS_REC_N];
    r->slot = slot; r->id = id; r->a0 = a0; r->a1 = a1; r->a2 = a2; r->ret = ret;
    if (g_hs_trace) {
        fprintf(stderr, "[hostshim] slot=%u id=0x%x a0=0x%llx a1=0x%llx a2=0x%llx -> 0x%llx\n",
                slot, id, (unsigned long long)a0, (unsigned long long)a1,
                (unsigned long long)a2, (unsigned long long)ret);
        fflush(stderr);
    }
}

/* ---- Host オブジェクト / 敷設 ---- */
EMSCRIPTEN_KEEPALIVE void *fw_hs_host(void) { return g_hs_obj; }
EMSCRIPTEN_KEEPALIVE long long fw_hs_host_va(void) { return (long long)(uintptr_t)g_hs_obj; }

EMSCRIPTEN_KEEPALIVE void fw_hs_fold_cell(uint32_t addr, uint32_t slot) {
    if (slot >= HS_SLOTS) slot = 0;
    *(volatile uint64_t *)(uintptr_t)addr = HSVA(slot);
    if (g_hs_trace) {
        fprintf(stderr, "[hostshim] fold cell [0x%x] = slot%u (0x%llx)\n",
                addr, slot, (unsigned long long)HSVA(slot));
        fflush(stderr);
    }
}

/* ---- scratch pool (誤 decode mosaic 領域の override 先) ---- */
static unsigned char g_hs_pool[1u << 20];
static unsigned g_hs_pool_off;
EMSCRIPTEN_KEEPALIVE void *fw_hs_scratch(unsigned n) {
    if (n == 0 || n > sizeof g_hs_pool) n = 4096;
    if (g_hs_pool_off + n > sizeof g_hs_pool) g_hs_pool_off = 0;   /* wrap */
    void *p = &g_hs_pool[g_hs_pool_off];
    g_hs_pool_off += n;
    memset(p, 0, n);
    return p;
}

EMSCRIPTEN_KEEPALIVE void fw_hs_install(void) {
    for (int i = 0; i < HS_SLOTS; i++) g_hs_vtable[i] = HSVA(i);
    g_hs_obj[0] = (uint64_t)(uintptr_t)g_hs_vtable;   /* vptr → vtable */
    memset(&g_hs_obj[1], 0, sizeof(g_hs_obj) - 8);    /* instance 内容は shim 管理領域 */
    g_hs_installed = 1;
    /* RetDec 定数畳み込み接続 (fw_flat4_canon3.ll 実測):
     *   function_6bd210 site 0x6bd253/0x6bd2a4: target = *(u64*)0x24 (= "$" の内容 = [Host] の畳み込み)
     *   function_6bd150 site 0x6bd197:          target = *(u64*)0x54 (= 0x24 + 0x30, [resp]+0x30 の畳み込み) */
    fw_hs_fold_cell(0x24, 0);
    fw_hs_fold_cell(0x54, 6);
    if (g_hs_trace) {
        fprintf(stderr, "[hostshim] installed: host=0x%llx vtable=0x%llx (46 slots @0x%x)\n",
                (unsigned long long)(uintptr_t)g_hs_obj, (unsigned long long)(uintptr_t)g_hs_vtable,
                HS_VA_BASE);
        fflush(stderr);
    }
}

/* ---- slot0: Dispatcher 応答表 ----
 * 根拠:
 *  * 0x47 (71) — Balance 0x6bd253 (init 0x6bd210 内): 応答を 0x6bd150 へ渡し、そこで
 *    `[resp]` の vtable+0x30 を BOOL として呼ぶ (test eax,eax; je fail — 0x6bd197 実測)。
 *    → 応答は非 NULL オブジェクトであること。FLE 側 0x47 case の返す実体解析は未 (CAB-195 作業5)。
 *  * 0x56 (86) — Balance 0x6bd2a4: 応答を 0x5c1930() の結果オブジェクト [X+0x14] に store のみ。
 *    FLE case 0x131bb5c は global オブジェクトポインタを返す → shim も非 NULL を返す。
 *    **検収で独立照合済 (hs_disp_tree.py, 2026-10-11)**: Dispatcher 0x13173a0 の
 *    cmp/sub 二分木を ID 具体駆動すると ID=0x56 だけが `je 0x131bb5c` を取り、
 *    周辺 ID (0x54/0x55/0x57/0x58) はすべて別パス (= 判別力あり)。0x131bb5c の本体は
 *    `mov rax,[rip+0x2c9005]; mov rax,[rax]` で global オブジェクトポインタを返す。
 *  * 0x0d (13) — TDelphiFruityPlug ctor 0x6b8f4b: 応答は未使用 (実測) → 0。
 *  * 上位 35 ID — hostshim/hs_ids.json (894 site の戻り値使用クラス実測):
 *    store/reg クラスは非 NULL (deref に備える), ignore/test クラスは 0。
 *    FLE 0x13173a0 の case 別応答値解析は未のため、数値の意味論は次段 (T0 frontier) で要確認。 */
static long long hs_dispatcher(uint64_t host, uint64_t tag, uint32_t id, uint64_t index) {
    switch (id) {
    case 0x47: return (long long)(uintptr_t)g_hs_obj;   /* 71: init — オブジェクト返答 (実測) */
    case 0x56: return (long long)(uintptr_t)g_hs_obj;   /* 86: init — handle store のみ (実測) */
    case 0x0d: return 0;                                /* 13: ctor — 戻り未使用 (実測) */
    /* ---- A検収上位 35 ID (hostshim/hs_ids.json: 894 site / cover 89.8%) ----
     * ret_use 実測による分類 (REPORT §2.2 根拠表):
     *   store / reg クラス → 戻り値を保存/保持するので **非 NULL** 応答を返す
     *   ignore / test クラス → 0 を返す (fail-soft + 記録)
     * 各 ID の ret_use 実測内訳は REPORT §2.2。FLE 側 case 別応答値の意味論は
     * 次段 (T0 frontier CreatePlugInstance 完了後) で要確認。 */
    case 0x1d: case 0x32: case 0x2e: case 0x0e: case 0x0a:
    case 0x3d: case 0x25: case 0x12:
        return (long long)(uintptr_t)g_hs_obj;          /* 29,50,46,14,10,61,37,18 */
    /* 格納元が 0x41d110 の戻り値 + 0x2a8 (非 NULL ポインタ) と機械語で確定した ID (#2886 REPORT_DISPATCHER_APPENDIX §2) */
    case 0x07: case 0x1c: case 0x4e:                    /* 7,28,78 */
        return (long long)(uintptr_t)g_hs_obj;
    /* ignore/test クラス + 未知 ID: 0 (fail-soft, 記録済み)
     * 2,33(0x3b),3,36(0x24),91(0x5b),23(0x17),48(0x30),30(0x1e),40(0x28),38(0x26),
     * 97(0x61),59(0x67),103(0x67?)、17(0x11),27(0x1b),8,13(0x0d),20(0x14),34(0x22),
     * 67(0x43),90(0x5a),0,5,9,13(0x13?)、15(0x15) 他 */
    default: return 0;
    }
}

/* ---- slot 実装 ---- */
static long long hs_slot_impl(uint32_t slot) {
    uint64_t a0 = BLKQ(8), a1 = BLKQ(0x10), a2 = BLKQ(0x18), a3 = BLKQ(0x20);
    long long ret;
    if (slot == 0) {
        uint32_t id = (uint32_t)a2;                     /* r8d = ID */
        ret = hs_dispatcher(a0, a1, id, a3);
        hs_rec_put(0, id, a0, a1, a3, (uint64_t)ret);
        return ret;
    }
    if (slot == 6) {
        /* 0x47 応答オブジェクト経由の BOOL 仮想呼出 (Balance 0x6bd197: (resp, 0x40f, ptr, 0,0,&out)
         * → test eax,eax; je fail)。shim は真 (1) 固定で成功経路を通す。 */
        ret = 1;
        hs_rec_put(6, 0, a0, a1, a3, (uint64_t)ret);
        return ret;
    }
    /* fail-soft: 記録して 0 を返す (SHIMX_TRACE 方式 — abort しない) */
    ret = 0;
    hs_rec_put(slot, 0, a0, a1, a3, (uint64_t)ret);
    return ret;
}

/* 46 slot を 0-arg 一様 ABI (icall 表) で export (名前は fw_table.py の hs_slot<N> と一致) */
#define HS_SLOT(N) \
    __attribute__((used)) long long hs_slot##N(void) { return hs_slot_impl(N); }

HS_SLOT(0)  HS_SLOT(1)  HS_SLOT(2)  HS_SLOT(3)  HS_SLOT(4)  HS_SLOT(5)
HS_SLOT(6)  HS_SLOT(7)  HS_SLOT(8)  HS_SLOT(9)  HS_SLOT(10) HS_SLOT(11)
HS_SLOT(12) HS_SLOT(13) HS_SLOT(14) HS_SLOT(15) HS_SLOT(16) HS_SLOT(17)
HS_SLOT(18) HS_SLOT(19) HS_SLOT(20) HS_SLOT(21) HS_SLOT(22) HS_SLOT(23)
HS_SLOT(24) HS_SLOT(25) HS_SLOT(26) HS_SLOT(27) HS_SLOT(28) HS_SLOT(29)
HS_SLOT(30) HS_SLOT(31) HS_SLOT(32) HS_SLOT(33) HS_SLOT(34) HS_SLOT(35)
HS_SLOT(36) HS_SLOT(37) HS_SLOT(38) HS_SLOT(39) HS_SLOT(40) HS_SLOT(41)
HS_SLOT(42) HS_SLOT(43) HS_SLOT(44) HS_SLOT(45)

/* 未使用警告の抑止 + installed フラグの観測用 */
EMSCRIPTEN_KEEPALIVE int fw_hs_installed(void) { return g_hs_installed; }
static const uint32_t *volatile g_fle_impl_ref = g_fle_impl;   /* REPORT 用 (FLE 実装 VA 表の生存) */
EMSCRIPTEN_KEEPALIVE const void *fw_hs_fle_impl(void) { return g_fle_impl_ref; }
