/* hostshim.h — TFruityHost shim (CAB-195) の公開インタフェース.
 *
 * FL ホスト側 TFruityHost (FLEngine_x64.dll VMT 0x1314108, vtable = VMT+0x70 から 46 slot,
 * slot0 = Dispatcher 0x13173a0 — ABI.md §2.3 / delphi_vmt.py 再生成値) を wasm 内で模する。
 * Host オブジェクトの vptr は合成 VA (HS_VA_BASE + 8*slot) を指し、lift 側の間接呼出
 * (icall dispatch 表, fw_table.py が登録) 経由で hs_slotNN C 実装に届く。
 * 例外/未対応は fail-soft + 呼出記録 (tools/shimx の SHIMX_TRACE 方式を踏襲)。
 */
#ifndef HOSTSHIM_H
#define HOSTSHIM_H
#include <stdint.h>

#define HS_VA_BASE 0xE100000u   /* import 合成 VA (0xE000000..0xE000FC0) の直上, fw_imports.json 実測 */
#define HS_SLOTS   46           /* TFruityHost vtable slot 数 (plugin から見た offset 0x00..0x168) */

/* Host オブジェクト (wasm address) を返す。未初期化時は fw_hs_install 済みの
 * g_hs_obj (296B = TFruityHost InstanceSize 実測 + 余裕) を返す。 */
void *fw_hs_host(void);
long long fw_hs_host_va(void);

/* Host vtable 敷設 + RetDec 定数畳み込み分岐接続 cell の設定。
 * RetDec は「Host 引数」を "$" 文字列定数 (内容 0x24) に定数畳み込みしたため、
 * `call [[Host]]` / `call [[resp]+0x30]` がそれぞれ wasm address 0x24 / 0x54 の
 * load に確定する (fw_flat4_canon3.ll function_6bd210/6bd150 実測)。
 * 本関数は [0x24]=slot0 VA, [0x54]=slot6 VA を書き、両経路を shim に接続する。 */
void fw_hs_install(void);

/* 任意の畳み込み cell に slot VA を書く (実行時に追加の分岐接続が必要になった場合) */
void fw_hs_fold_cell(uint32_t addr, uint32_t slot);

/* plugin 連鎖の誤 decode mosaic 領域 (NewAnsiString 0x40e5e0 等) からの安全確保用
 * bump allocator (静的 1MB pool, 枯渇で先頭に wrap)。返した領域は書込み安全で、
 * 呼出側が garbage 長で write しても linear memory 内に収まる。 */
void *fw_hs_scratch(unsigned n);

/* 呼出記録 (SHIMX_TRACE 方式): ring buffer + stderr trace。
 * 記録は常時, stderr 出力は g_hs_trace (既定 ON, HOSTSHIM_TRACE=0 / fw_hs_trace(0) で消す)。 */
typedef struct {
    uint32_t slot;      /* vtable slot (0=Dispatcher) */
    uint32_t id;        /* slot0: Dispatcher ID. 他 slot: 未使用 0 */
    uint64_t a0, a1, a2;/* BLK+8 / +0x10 / +0x20 (rcx, rdx, r9 相当) */
    uint64_t ret;       /* 応答値 */
} hs_rec;
void fw_hs_trace(int on);
void fw_hs_reset(void);
int fw_hs_count(void);          /* 累積記録数 (飽和: HS_REC_N=512 超は上書き) */
void *fw_hs_records(void);      /* hs_rec 配列先頭 (mjs から DataView で読む) */

#endif
