/* hb_rt_entry.c — HB-H2 (CAB-91): lowbase x64c 入口拡張 module 用の override body。
 *
 * tools/ott/entry/rt_entry.c (CAB-137 の direct ott_run ハーネス用) と同じ役割を、
 * hostbridge 結線版として置き換えたもの:
 *   ovr_editor_null  (0x180120ff0): OTTEditor ctor を editor=NULL 返しに置換 (GUI 対象外 surrogate。
 *                                    native 側は同一箇所 3 byte 機械語 patch = 同一意味。CAB-137 REPORT §2.4)
 *   ovr_am_shim_hb   (0x1802f8000): audioMaster 仮想入口。lift 済み VSTPluginMain の `call rbx` を
 *                                    ott_dispatch(0x308000) でここに落とし、MS x64 ABI の引数置き場から
 *                                    読み替えて import hb_host_call (bridge upcall) へ転送する。
 *
 * override body 規約: lifted ABI (CPU 状態 R/X) で動作し、末尾で ret 相当 R[RSP] += 8 を実行
 * (tools/ott/rt/ott_ovr.c の規約)。audioMaster の第 5/6 引数 (ptr, opt) はスタック渡し
 * ([RSP+0x28], [RSP+0x30] — 呼出直後の frame で caller の [rsp+0x20]/[rsp+0x28])。
 */
#include "ott_cpu.h"
#include <string.h>

#define RET() (R[RSP] += 8)

void ovr_editor_null(void) {
    R[RAX] = 0;
    RET();
}

/* plugin → host upcall (emscripten import)。poc/plugin_ott_entry.c と同一署名 */
extern int32_t hb_host_call(uint32_t eff, int32_t op, int32_t idx, uint32_t vlo, uint32_t vhi,
                            uint32_t ptr, float opt);

void ovr_am_shim_hb(void) {
    uint32_t eff = (uint32_t)R[RCX];                 /* lift 側が渡す eff (entry 中は NULL, 以後は guest AEffect*) */
    int32_t op = (int32_t)R[RDX];
    int32_t idx = (int32_t)R[R8];
    int64_t val = (int64_t)R[R9];
    uint32_t ptr = (uint32_t)LD64(R[RSP] + 0x28);    /* 第 5 位置引数 */
    uint32_t ob = LD32(R[RSP] + 0x30);               /* 第 6 位置引数 (float, bit渡し) */
    float opt; memcpy(&opt, &ob, 4);
    R[RAX] = (uint64_t)(int64_t)hb_host_call(eff, op, idx, (uint32_t)val, (uint32_t)((uint64_t)val >> 32), ptr, opt);
    RET();
}
