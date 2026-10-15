/* gui_hostcall.h — shim → ブラウザ main thread の同期呼出路 (host call; #172 SHX-T5)。
 * ShellExecute→window.open / GetOpen・SaveFileName→File System Access のような「main thread でしか実行できず結果を同期で返す」操作用。
 * GuiShared (gui_proto.h) とは独立した静的 1 領域 (gui_hostcall_ptr())。JS ミラーは src/runtime/gui_hostcall.ts。
 *
 * 手順: wasm 側が lock 取得 → in/op/flags を書く → req_seq++ + wake → resp_seq == req_seq まで futex wait。
 *       host は Atomics.waitAsync(req_seq) で起床 → 処理 → out/result を書く → resp_seq = req_seq + notify。
 * host_ready == 0 (host 未接続) なら gui_hostcall() は待たずに -1 を返す。 */
#ifndef GUI_HOSTCALL_H
#define GUI_HOSTCALL_H
#include <stdint.h>

#define GUI_HC_MAGIC   0x43484749u   /* "IGHC" */
#define GUI_HC_VERSION 1u
#define GUI_HC_IN      2048
#define GUI_HC_OUT     4096

enum { GUI_HC_OPEN_URL = 1, GUI_HC_OPEN_FILE = 2, GUI_HC_SAVE_FILE = 3, GUI_HC_OPEN_HELP = 4 /* in = FL の Help パス (UTF-8, NUL 終端) → host の flHelp.shellExecute (#554) */,
       GUI_HC_FETCH_FONT = 5 /* in = face 名 (UTF-8, NUL 終端) → host が取得・sha256 検証して wasm heap へ置き、out = ptr(u32 LE), size(u32 LE) (GUI-13 #615; gui_ft_wasm.c)。result 1 = ok / 0 = 無し・検証失敗 */,
       GUI_HC_FILE_CLOSED = 6 /* in = 書込み用に閉じた file の POSIX path (UTF-8, NUL 終端; stage 配下のみ送る)。host は保存待ちの先なら実体へ反映 (#958)。result 1 = 反映 / 0 = 対象外 */ };

/* result: >0 成功 / 0 キャンセル・拒否 / <=-16 host 側エラー (gui_hostcall.ts HC_ERR)。ライブラリ側の失敗は gui_hostcall() の戻りで -1 (未接続) / -2 (timeout) / -3 (溢れ) */
typedef struct {
  uint32_t magic, version;            /* 0x00 : wasm が書く */
  volatile uint32_t host_ready;       /* 0x08 : host が 1 */
  volatile uint32_t lock;             /* 0x0C : wasm 内部の futex mutex (host は触らない) */
  volatile uint32_t req_seq;          /* 0x10 : wasm が ++ */
  volatile uint32_t resp_seq;         /* 0x14 : host が req_seq の値を書く */
  uint32_t op, flags;                 /* 0x18, 0x1C */
  int32_t  result;                    /* 0x20 : host → wasm */
  uint32_t in_len, out_len;           /* 0x24, 0x28 */
  uint32_t _rsv[5];                   /* 0x2C..0x3F */
  char in[GUI_HC_IN];                 /* 0x40 : wasm → host (UTF-8, フィールドは NUL 区切り) */
  char out[GUI_HC_OUT];               /* 0x840 : host → wasm */
} GuiHostCall;                        /* 0x1840 = 6208 B */
_Static_assert(sizeof(GuiHostCall) == 0x1840, "GuiHostCall size");
_Static_assert(__builtin_offsetof(GuiHostCall, req_seq) == 0x10 && __builtin_offsetof(GuiHostCall, in) == 0x40 &&
               __builtin_offsetof(GuiHostCall, out) == 0x840, "GuiHostCall layout");

/* ---- C API (gui_platform.c) ---- */
GuiHostCall *gui_hostcall_native(void);   /* テスト/native host 用 */
/* op を同期発行。戻り: host result (>=0 / <0) | -1 = host 未接続 | -2 = timeout | -3 = in/out 溢れ。timeout_ms < 0 は無期限 */
int gui_hostcall(uint32_t op, uint32_t flags, const void *in, uint32_t in_len, void *out, uint32_t out_cap, uint32_t *out_len, int timeout_ms);

#endif
