/* hs_plug.c — CAB-195 (P0b) TTestPlug26 対向ドライバ + CreatePlugInstance→ctor E2E。
 *
 * 役割: framework (CAB-194 lift = Fruity Balance) を plugin 側から駆動する host 側の対向実装。
 *   1) fw_hs_install()           — host オブジェクト (vtable 46 slot, hostshim.c) 準備
 *   2) CreatePlugInstance(Host, Tag) — VA 0x6bdde0 (Balance export, ABI.md §1.1)
 *      → 6bd210 (Dispatcher ID=0x47) → TTestPlug.Create 0x6be800 (ID=0x21)
 *      → TDelphiFruityPlug.Create 0x6b8e80 (ID=0x0d/0x2e/0x47/0x1d) …
 *   3) 生成された TFruityPlug (TTestPlug, vtable 26 slot) を host として駆動:
 *      TFruityPlug vtable20 の内、BLK-ABI 4 引数で呼べる slot (0/2/5/6/7) を実呼出。
 *      slot4 GetName は 5 引数 (stack buf) — BLK+0x48 拡張で対応。
 *   4) 戻り値/呼出記録は hs_rec (hostshim.c) と本 file の plug_log に記録。
 *
 * 呼出手順は fw_boot.c の fw_call_cur 契約 (BLK 設定 → fw_call_cur(va)) を踏襲する。
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <emscripten.h>

#ifndef FW_BLK
#define FW_BLK 0x8A1000u
#endif
#define BLKQ(off) (*(volatile uint64_t *)(uintptr_t)(FW_BLK + (off)))

extern long long fw_call_cur(uint32_t va);
extern void fw_hs_install(void);
extern void fw_ff(const char *what);

/* ---- Balance (framework) 内 VA — tools/plugins/ABI.md §1.1/§3.1 実測値 ---- */
#define VA_CreatePlugInstance 0x6bdde0u
#define VA_Plug_DestroyObject 0x6b92f0u /* slot0 */
#define VA_Plug_Dispatcher    0x6bde30u /* slot1 (未使用) */
#define VA_Plug_Idle          0x6ba140u /* slot2 (ret) */
#define VA_Plug_SaveRestore   0x6be740u /* slot3 (IStream 要 — 本 smoke では未呼出) */
#define VA_Plug_GetName       0x6bee90u /* slot4 (5 引数: buf は BLK+0x48) */
#define VA_Plug_ProcessEvent  0x6b97d0u /* slot5 */
#define VA_Plug_ProcessParam  0x6beaa0u /* slot6 */
#define VA_Plug_Eff_Render    0x6befc0u /* slot7 */

/* TTestPlug instance layout (ABI.md §2.1, TTestPlug instance size 0x1b8) */
#define PLUG_VPTR    0x00
#define PLUG_HostTag 0x08
#define PLUG_Info    0x10
#define PLUG_EditorH 0x18
#define PLUG_Host    0xbc
#define PLUG_MaxPoly 0xe0
#define PLUG_Param0  0x198

/* TFruityPlugInfo (0x70e3cc, ABI.md §2.2) — ctor が [plug+0x10] に設定する実測値 */
#define VA_PlugInfo 0x70e3ccu

/* ---- status bits (e2e 判定用) ---- */
#define HS_ST_OK              0u
#define HS_ST_HOSTCALL_FAIL   1u << 0   /* fw_call_cur 失敗 (fw_ff で exit するので基本到達しない) */
#define HS_ST_PLUG_NULL       1u << 1
#define HS_ST_FIELD_VPTR      1u << 2
#define HS_ST_FIELD_TAG       1u << 3
#define HS_ST_FIELD_INFO      1u << 4
#define HS_ST_FIELD_HOST      1u << 5
#define HS_ST_VTABLE_RANGE    1u << 6
#define HS_ST_IDLE_RET        1u << 7   /* slot2 Idle の戻りが 0 以外 */
#define HS_ST_DESTROY_TRAP    1u << 8   /* 到達しない (trap は JS 側検知) */

static uint32_t hs_status;
static uint64_t hs_plug;
static uint64_t hs_tag_used = 0x54534154; /* 'TAST' — HostTag (64bit 幅, ABI.md §4) */
static uint32_t hs_slots_called;          /* bit per plug-slot (0..25) */
static uint32_t hs_plug_vtab[26];         /* 生成された TTestPlug vtable の実効 VA 記録 */

/* plugin 側呼出の記録 (seq, slot, rax) — host shim 側 hs_rec とは別枠 */
#define PLUG_LOG_N 64
static uint32_t plug_log[PLUG_LOG_N * 3];
static uint32_t plug_log_n;

EMSCRIPTEN_KEEPALIVE uint32_t hs_status_get(void) { return hs_status; }
EMSCRIPTEN_KEEPALIVE uint64_t hs_plug_get(void) { return hs_plug; }
EMSCRIPTEN_KEEPALIVE uint32_t *hs_pluglog_buf(void) { return plug_log; }
EMSCRIPTEN_KEEPALIVE uint32_t hs_pluglog_count(void) { return plug_log_n; }
EMSCRIPTEN_KEEPALIVE uint32_t hs_slots_called_get(void) { return hs_slots_called; }
EMSCRIPTEN_KEEPALIVE uint64_t hs_tag_get(void) { return hs_tag_used; }
EMSCRIPTEN_KEEPALIVE uint32_t *hs_plugvtab_buf(void) { return hs_plug_vtab; }

static void plog(uint32_t slot, uint64_t rax, uint64_t aux) {
    if (plug_log_n >= PLUG_LOG_N) return;
    uint32_t *e = &plug_log[plug_log_n * 3];
    e[0] = slot; e[1] = (uint32_t)rax; e[2] = (uint32_t)aux;
    plug_log_n++;
    hs_slots_called |= 1u << (slot & 31);
}

/* stack 引数域 (BLK+0x48..0x78) を 0 で掃除してから BLK-ABI で lifted 関数を呼ぶ。
 * 戻り: 0-arg direct 表 entry = wasm 戻り rax (そのまま), wrapper entry = BLK+0x80。 */
static uint64_t plug_call(uint32_t va, uint64_t a1, uint64_t a2, uint64_t a3, uint64_t a4, uint64_t stk5, int via_wrapper) {
    for (uint32_t o = 0x48; o < 0x80; o += 8) BLKQ(o) = 0;
    BLKQ(8) = a1; BLKQ(0x10) = a2; BLKQ(0x18) = a3; BLKQ(0x20) = a4;
    BLKQ(0x48) = stk5;
    long long r = fw_call_cur(va);
    uint64_t rax = via_wrapper ? (uint64_t)BLKQ(0x80) : (uint64_t)r;
    for (uint32_t o = 0x48; o < 0x80; o += 8) BLKQ(o) = 0;
    return rax;
}

static int in_image(uint64_t va) { return va >= 0x400000u && va < 0xd02000u; }

EMSCRIPTEN_KEEPALIVE uint32_t hs_e2e_run(void) {
    hs_status = 0; hs_plug = 0; plug_log_n = 0; hs_slots_called = 0;
    fw_hs_install();

    /* ---- 1. CreatePlugInstance(Host, Tag) — HostTag は 64bit 幅で受領 (ABI.md §1.1) ---- */
    uint64_t host = 0;
    {   /* host ptr は hostshim.c の静的オブジェクト (fw_hs_install 済み) */
        extern long long fw_hs_host_va(void);
        host = (uint64_t)fw_hs_host_va();
    }
    fprintf(stderr, "[hs] CreatePlugInstance(Host=0x%llx, Tag=0x%llx)\n",
            (unsigned long long)host, (unsigned long long)hs_tag_used);
    fflush(stderr);
    hs_plug = plug_call(VA_CreatePlugInstance, host, hs_tag_used, 0, 0, 0, 1);
    fprintf(stderr, "[hs] -> TFruityPlug* = 0x%llx\n", (unsigned long long)hs_plug);
    fflush(stderr);
    if (!hs_plug) { hs_status |= HS_ST_PLUG_NULL; return hs_status; }

    /* ---- 2. instance field 検証 (ABI.md §2.1 の ctor 実測契約) ---- */
    uint64_t vptr = *(volatile uint64_t *)(uintptr_t)(hs_plug + PLUG_VPTR);
    uint64_t f_tag = *(volatile uint64_t *)(uintptr_t)(hs_plug + PLUG_HostTag);
    uint64_t f_info = *(volatile uint64_t *)(uintptr_t)(hs_plug + PLUG_Info);
    uint64_t f_host = *(volatile uint64_t *)(uintptr_t)(hs_plug + PLUG_Host);
    fprintf(stderr, "[hs] plug fields: vptr=0x%llx Tag=0x%llx Info=0x%llx Host=0x%llx\n",
            (unsigned long long)vptr, (unsigned long long)f_tag,
            (unsigned long long)f_info, (unsigned long long)f_host);
    fflush(stderr);
    if (!in_image(vptr)) hs_status |= HS_ST_FIELD_VPTR;
    if (f_tag != hs_tag_used) hs_status |= HS_ST_FIELD_TAG;
    if (f_info != VA_PlugInfo) hs_status |= HS_ST_FIELD_INFO;
    if (f_host != host) hs_status |= HS_ST_FIELD_HOST;

    /* vtable dump (TTestPlug 26 slot — A検収: TFruityPlug vtable20 + Delphi 6) */
    for (int i = 0; i < 26; i++) {
        uint64_t va = *(volatile uint64_t *)(uintptr_t)(vptr + 8u * (uint32_t)i);
        hs_plug_vtab[i] = (uint32_t)va;
        if (i < 20 && !in_image(va)) { hs_status |= HS_ST_VTABLE_RANGE; }
        fprintf(stderr, "[hs] plug vtable[%02d] = 0x%llx\n", i, (unsigned long long)va);
    }
    fflush(stderr);

    /* ---- 3. TFruityPlug vtable20 呼出 (host → plugin 方向; 期待戻りは REPORT.md §4) ---- */
    uint8_t namebuf[64];
    uint32_t frames = 8;
    static float audio[16]; /* 8 frame x stereo — Eff_Render の DestBuffer */
    for (int i = 0; i < 16; i++) audio[i] = (float)(i % 8) * 0.25f;

    /* slot2 Idle_Public(this) — Balance 実装は ret (rax=0) */
    uint64_t r2 = plug_call(VA_Plug_Idle, hs_plug, 0, 0, 0, 0, 0);
    plog(2, r2, 0);
    if (r2 != 0) hs_status |= HS_ST_IDLE_RET;

    /* slot5 ProcessEvent(this, EventID=1 MaxPoly, EventValue=8, Flags=0) */
    uint64_t r5 = plug_call(VA_Plug_ProcessEvent, hs_plug, 1, 8, 0, 0, 0);
    plog(5, r5, 0);
    uint64_t maxpoly = *(volatile uint64_t *)(uintptr_t)(hs_plug + PLUG_MaxPoly);
    fprintf(stderr, "[hs] ProcessEvent(1,8) -> rax=0x%llx, [plug+0xe0]=0x%llx (MaxPoly 保存)\n",
            (unsigned long long)r5, (unsigned long long)maxpoly);
    fflush(stderr);

    /* slot6 ProcessParam(this, Index=0, Value=0x4000, REC=UpdateValue) → 戻り記録 */
    uint64_t r6a = plug_call(VA_Plug_ProcessParam, hs_plug, 0, 0x4000, 1, 0, 0);
    plog(6, r6a, 1);
    uint64_t r6b = plug_call(VA_Plug_ProcessParam, hs_plug, 0, 0, 2, 0, 0);
    plog(6, r6b, 2);
    fprintf(stderr, "[hs] ProcessParam(0,0x4000,REC=1) -> 0x%llx / (0,0,REC=2) -> 0x%llx\n",
            (unsigned long long)r6a, (unsigned long long)r6b);
    fflush(stderr);

    /* slot7 Eff_Render(this, Src, Dst, Length=8 frames) — in-place 可 (ABI.md §4)。
     * 差分検証 (native 突合) は次段 (P0c/検収) — 本 e2e は通過と出力の記録のみ。 */
    uint64_t r7 = plug_call(VA_Plug_Eff_Render, hs_plug, (uint64_t)(uintptr_t)audio,
                            (uint64_t)(uintptr_t)audio, frames, 0, 0);
    plog(7, r7, frames);
    fprintf(stderr, "[hs] Eff_Render(8 frames) -> rax=0x%llx, dst[0..3]=%g %g %g %g\n",
            (unsigned long long)r7, (double)audio[0], (double)audio[1], (double)audio[2], (double)audio[3]);
    fflush(stderr);

    /* slot4 GetName(this, Section, Index, Value, buf) — 5 引数目 (buf) は BLK+0x48 拡張。
     * RetDec が Section/Index を定数化しているため戻り内容の妥当性は記録のみ (REPORT §4)。 */
    memset(namebuf, 0, sizeof namebuf);
    uint64_t r4 = plug_call(VA_Plug_GetName, hs_plug, 0, 0, 0, (uint64_t)(uintptr_t)namebuf, 1);
    plog(4, r4, (uint64_t)(uintptr_t)namebuf);
    fprintf(stderr, "[hs] GetName -> rax=0x%llx buf='%s'\n", (unsigned long long)r4, (const char *)namebuf);
    fflush(stderr);

    /* ---- 4. slot0 DestroyObject(this) — 最後 (以後 plug は無効) ---- */
    uint64_t r0 = plug_call(VA_Plug_DestroyObject, hs_plug, 0, 0, 0, 0, 0);
    plog(0, r0, 0);
    fprintf(stderr, "[hs] DestroyObject -> rax=0x%llx\n", (unsigned long long)r0);
    fflush(stderr);

    return hs_status;
}
