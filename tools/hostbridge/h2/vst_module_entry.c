/* vst_module_entry.c — HB-H2 (CAB-91): lift 済み OTT closure を hostbridge の plugin module 契約に載せる glue。
 *
 * 旧 surrogate (poc/plugin_ott_entry.c) の plugin ロジック再現 (shadow params / opcode switch) をすべて撤去し、
 * **lift 済み実機械語への薄い ABI 変換**だけにする。これが「ott_run → hb_icall 接続」の確定版 (REPORT §2):
 *
 *   host (FL/Fruity Wrapper lift, PoC では host_vst2.wasm)
 *     --LoadLibraryW/GetProcAddress--> bridge が module の VSTPluginMain を呼ぶ (audioMaster token 付き)
 *     --AEffect fn ptr (thunk slot)--> bridge が module の hb_icall(fn, a0..a5) を呼ぶ
 *                                        → 本 glue が ott_run(fn, ...) に変換して lift 済みコードを実行
 *     <--plugin → host upcall-------- lift 渡しの audioMaster は override (ovr_am_shim_hb) 経由で
 *                                      import hb_host_call に落ちる (hb_lib.js → bridge.upcall)
 *
 * AEffect の関数ポインタ欄には lift 済み AudioEffect ctor が書いた **実 guest VA (LB_BASE+RVA)** が入る
 * (= surrogate の合成 id 0x1000 系とここが置き換わる)。hb_icall は fn 下位 32bit を RVA とみなして
 * VST2 AEffect の 6 関数の署名に従い ott_run の (整数 4 + xmm 4 + stack 2) 引数置き場へ振り分ける。
 */
#include <stdint.h>
#include <string.h>
#include <emscripten.h>
#include "ott_cpu.h"

#ifndef LB_BASE
#define LB_BASE 0x10000u
#endif

/* lift 済み AEffect 静的 thunk の RVA (lift 済み ctor が AEffect に書く実ポインタ; CAB-137 実測) */
#define RVA_DISPATCHER  0x126c00u  /* AEffect+0x08 dispatchEffectClass (6 引数: ptr/opt は stack) */
#define RVA_PROCESS     0x127430u  /* AEffect+0x10 process (4 引数) */
#define RVA_SETPARAM    0x127520u  /* AEffect+0x18 setParameter (第3引数 float → xmm2) */
#define RVA_GETPARAM    0x1271a0u  /* AEffect+0x20 getParameter (OTT は float を xmm0 で返す) */
#define RVA_PROCD       0x127440u  /* AEffect+0x80 processDoubleReplacing */
#define RVA_PROCR       0x127450u  /* AEffect+0x78 processReplacing */

#define AM_TRAMP_VA (LB_BASE + 0x2f8000u)   /* ovr_am_shim_hb override の shifted VA */
#define VSTMAIN_VA  (LB_BASE + 0x128ba0u)   /* VSTPluginMain */

extern uint64_t ott_run(uint32_t va, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3,
                        uint64_t x0, uint64_t x1, uint64_t x2, uint64_t x3);
extern uint64_t ott_xmm0(void);
extern void ott_set_stackarg(int i, uint64_t v);
extern void ott_data_install(void);

#ifndef LB_ARENA_ADDR
#define LB_ARENA_ADDR 0x320000u
#endif
#define HB_SCRATCH_SIZE 0x00100000u

static int32_t g_initialised;

EMSCRIPTEN_KEEPALIVE int32_t hb_plugin_init(void) {
    if (g_initialised) return 0;
    ott_data_install();
    memset((void *)(uintptr_t)LB_ARENA_ADDR, 0, HB_SCRATCH_SIZE);
    g_initialised = 1;
    return 0;
}

EMSCRIPTEN_KEEPALIVE uint32_t hb_scratch(void) { return LB_ARENA_ADDR; }

/* PE export と同名・同意味。audioMaster token (bridge 発行 slot) は lift 側では使わない
 * (upcall は override → hb_host_call 経由で bridge に戻るため)。 */
EMSCRIPTEN_KEEPALIVE uint64_t VSTPluginMain(uint64_t audioMasterSlot) {
    (void)audioMasterSlot;
    hb_plugin_init();
    return ott_run((uint32_t)VSTMAIN_VA, AM_TRAMP_VA, 0, 0, 0, 0, 0, 0, 0);
}

/* host → plugin の全間接呼出 (= 旧 surrogate の switch を置き換える汎用転送路) */
EMSCRIPTEN_KEEPALIVE uint64_t hb_icall(uint64_t fn, uint64_t a0, uint64_t a1, uint64_t a2,
                                       uint64_t a3, uint64_t a4, uint64_t a5) {
    uint32_t rva = (uint32_t)(fn - LB_BASE);
    switch (rva) {
    case RVA_DISPATCHER:                     /* (eff, op, idx, value, ptr, opt): 5/6 引数は stack */
        ott_set_stackarg(0, a4);
        ott_set_stackarg(1, a5);
        return ott_run((uint32_t)fn, a0, a1, a2, a3, 0, 0, 0, 0);
    case RVA_SETPARAM:                       /* (eff, index, float value): value → xmm2 (f32 bit) */
        return ott_run((uint32_t)fn, a0, a1, 0, 0, 0, 0, a2 & 0xffffffffull, 0);
    case RVA_GETPARAM:                       /* (eff, index, float* value): OTT は xmm0 返値 (CAB-137 実測) */
        ott_run((uint32_t)fn, a0, a1, a2, 0, 0, 0, 0, 0);
        return ott_xmm0();
    case RVA_PROCR:
    case RVA_PROCESS:
    case RVA_PROCD:                          /* (eff, in**, out**, n) */
        return ott_run((uint32_t)fn, a0, a1, a2, a3, 0, 0, 0, 0);
    default:                                 /* その他の guest fn ポインタ: dispatcher と同形で汎用転送 */
        ott_set_stackarg(0, a4);
        ott_set_stackarg(1, a5);
        return ott_run((uint32_t)fn, a0, a1, a2, a3, 0, 0, 0, 0);
    }
}
