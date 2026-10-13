/*
 * gui_proto.h — GUI shim <-> ブラウザ host の共有メモリプロトコル (正本)。
 *
 * 配置: wasm linear memory (pthread build では SharedArrayBuffer) 内の静的 1 領域 `GuiShared`。
 * JS 側は gui_shared_ptr() が返すアドレスを基点に同一オフセットで読み書きする
 * (JS ミラー: src/runtime/gui_proto.ts — オフセット値は _Static_assert で固定)。
 * 詳細・スレッドモデルは tools/gui/PROTOCOL.md。
 */
#ifndef GUI_PROTO_H
#define GUI_PROTO_H

#include <stddef.h>
#include <stdint.h>

#define GUI_MAGIC        0x31495547u /* "GUI1" (LE) */
#define GUI_VERSION      1u
#define GUI_MAX_SURF     16u
#define GUI_IN_RECS      1024u  /* 2^n */
#define GUI_OUT_RECS     2048u  /* 2^n */
#define GUI_REC_BYTES    32u

/* ---- 入力イベント (host -> shim) : 8 x u32 --------------------------------
 * w0 type | w1 surf | w2 x(i32) | w3 y(i32) | w4 a | w5 b | w6 time_ms | w7 seq
 * x,y は desktop(=canvas CSS px) 座標。 */
enum {
  GUI_IN_MOUSE_MOVE = 1, /* a=buttons mask (bit0 L, bit1 R, bit2 M) */
  GUI_IN_MOUSE_DOWN = 2, /* a=button index (0 L, 1 M, 2 R : DOM 準拠), b=mods */
  GUI_IN_MOUSE_UP   = 3, /* 同上 */
  GUI_IN_WHEEL      = 4, /* a=delta(i32, 120=1 notch, 上スクロール正), b=mods */
  GUI_IN_KEY_DOWN   = 5, /* a=VK, b=flags: bit0 repeat, bit1 extended, bits8..15 scancode, bits16..19 mods */
  GUI_IN_KEY_UP     = 6,
  GUI_IN_CHAR       = 7, /* a=UTF-16 code unit */
  GUI_IN_FOCUS      = 8, /* a=1 gained / 0 lost */
  GUI_IN_SCREEN     = 9, /* x=w, y=h : desktop リサイズ */
  GUI_IN_CLOSE      = 10, /* w1=surf : ユーザがウィンドウを閉じた (WM_CLOSE) */
  /* ---- GUI-6 (#182) 入力品質 ---- */
  GUI_IN_LAYOUT     = 11, /* a=KLID (下位 16bit = LANGID; 例 0x0409 US / 0x0407 DE / 0x040C FR)。以後 MapVirtualKey/ToUnicode/GetKeyboardLayout がこの配列で答える */
  GUI_IN_IME        = 12, /* a = phase(bit0-3) | nunits(bit8-10, 0..4) | first(bit12) | last(bit13); x = u0|u1<<16, y = u2|u3<<16 (UTF-16); b = カーソル位置 (last のみ有効)。
                           * phase: 1 START / 2 COMPOSITION 更新 / 3 COMMIT (結果文字列) / 4 CANCEL。文字列は first..last の連続レコードで運ぶ */
  GUI_IN_TOUCH      = 13, /* x,y = 座標(i32); a = pointerId | phase<<8 (0 down / 1 move / 2 up / 3 cancel) | primary<<12; b = 接触径 (w|h<<16, px) */
  GUI_IN_POINTER_LOCK = 14 /* a=1 ロック成立 / 0 解除 (host 通知: shim は GetCursorPos の意味を「仮想カーソル」へ切替えない = host が相対量を積算して cursor_x/y へ書く) */
};
enum { GUI_MOD_SHIFT = 1, GUI_MOD_CTRL = 2, GUI_MOD_ALT = 4, GUI_MOD_META = 8 };

/* ---- 出力コマンド (shim -> host) : 8 x u32 ---------------------------------
 * w0 cmd | w1 surf | w2..w7 params */
enum {
  GUI_CMD_SURF_CREATE  = 1, /* surf 表 [surf] が有効になった */
  GUI_CMD_SURF_DESTROY = 2,
  GUI_CMD_SURF_CHANGE  = 3, /* geometry/visible/z/pixels/gen が変化 -> host は表を再読込し全面再描画 */
  GUI_CMD_PRESENT      = 4, /* w2..w5 = l,t,r,b (surface client 座標, 半開区間), w6 = frame seq */
  GUI_CMD_FRAME_END    = 5, /* w1 = frame seq : ここまでを 1 フレームとして描画/ack してよい */
  GUI_CMD_SET_TITLE    = 6, /* title は surf 表の title[64] (UTF-8) */
  GUI_CMD_SET_CURSOR   = 7, /* w2 = cursor shape (IDC_* の数値) */
  GUI_CMD_LOG          = 8, /* w1 = byte len(0..24), w2..w7 = payload, w1 の bit8 = 行末 */
  GUI_CMD_EXIT         = 9, /* w1 = exit code */
  GUI_CMD_POINTER_LOCK = 10, /* w2 = 1 要求 / 0 解除。host は requestPointerLock / exitPointerLock (成立は GUI_IN_POINTER_LOCK で返す) */
  GUI_CMD_IME_POS      = 11, /* w1 = surf, w2 = x, w3 = y (surface client 座標; ImmSetCompositionWindow/CandidateWindow)。host は IME ポップアップ位置の textarea を移動 */
  GUI_CMD_CLIP_RECT    = 12  /* w2..w5 = l,t,r,b (ClipCursor; 全 0 = 解除)。host はロック中の仮想カーソルをこの矩形へ clamp */
};

/* ---- surface 表エントリ (128 B) -------------------------------------------- */
typedef struct GuiSurface {
  uint32_t state;   /* 0 free / 1 live */
  uint32_t visible;
  int32_t  x, y;    /* desktop 上の原点 (client 左上) */
  uint32_t w, h;
  uint32_t stride;  /* bytes */
  uint32_t pixels;  /* wasm アドレス : BGRA32 top-down */
  uint32_t z;       /* 大きいほど前面 */
  uint32_t gen;     /* pixels/サイズ再確保ごとに +1 */
  uint32_t wseq;    /* seqlock (GUI-4): 奇数 = shim が画素を書き換え中/未 flush、偶数 = flush 済みで静止。host は読出し前後で同値かつ偶数を確認 */
  uint32_t _rsv[5];
  char     title[64];
} GuiSurface;

typedef struct GuiRing {
  uint32_t head;    /* consumer が進める */
  uint32_t tail;    /* producer が進める */
  uint32_t _pad[14];
} GuiRing;

typedef struct GuiShared {
  /* 0x000 header */
  uint32_t magic, version, total_size, host_ready;
  uint32_t screen_w, screen_h, dpr_x100, flags;
  uint32_t doorbell;     /* futex word : あらゆる producer が ++ して wake */
  uint32_t exited, exit_code, _h0;
  uint32_t _h1[4];
  /* 0x040 pointer / keyboard state (host が書き、shim が読む) */
  int32_t  cursor_x, cursor_y;
  uint32_t buttons, mods;
  uint32_t focused, page_visible;
  uint32_t _p0[2];
  uint32_t key_down[8];  /* VK ビットマップ */
  /* 0x080 stats */
  uint32_t in_pushed, in_dropped, in_consumed, out_pushed;
  uint32_t out_full_waits, present_seq, present_done_seq, msgs_dispatched;
  uint32_t timer_fires, paints, frames_flushed, _s0[5];
  /* 0x0C0 / 0x100 ring control */
  GuiRing  in_ring;
  GuiRing  out_ring;
  /* 0x140 */
  GuiSurface surf[GUI_MAX_SURF];
  /* data */
  uint32_t in_recs[GUI_IN_RECS][8];
  uint32_t out_recs[GUI_OUT_RECS][8];
} GuiShared;

#define GUI_OFF_HEADER   0x000
#define GUI_OFF_PTR      0x040
#define GUI_OFF_STATS    0x080
#define GUI_OFF_IN_RING  0x0C0
#define GUI_OFF_OUT_RING 0x100
#define GUI_OFF_SURF     0x140
#define GUI_OFF_IN_RECS  0x940
#define GUI_OFF_OUT_RECS (0x940 + GUI_IN_RECS * GUI_REC_BYTES)
#define GUI_TOTAL_SIZE   (GUI_OFF_OUT_RECS + GUI_OUT_RECS * GUI_REC_BYTES)

_Static_assert(offsetof(GuiShared, magic) == GUI_OFF_HEADER, "hdr");
_Static_assert(offsetof(GuiShared, doorbell) == 0x20, "doorbell");
_Static_assert(offsetof(GuiShared, cursor_x) == GUI_OFF_PTR, "ptr");
_Static_assert(offsetof(GuiShared, key_down) == 0x60, "keys");
_Static_assert(offsetof(GuiShared, in_pushed) == GUI_OFF_STATS, "stats");
_Static_assert(offsetof(GuiShared, in_ring) == GUI_OFF_IN_RING, "inring");
_Static_assert(offsetof(GuiShared, out_ring) == GUI_OFF_OUT_RING, "outring");
_Static_assert(offsetof(GuiShared, surf) == GUI_OFF_SURF, "surf");
_Static_assert(sizeof(GuiSurface) == 128, "surf size");
_Static_assert(offsetof(GuiShared, in_recs) == GUI_OFF_IN_RECS, "inrecs");
_Static_assert(offsetof(GuiShared, out_recs) == GUI_OFF_OUT_RECS, "outrecs");
_Static_assert(sizeof(GuiShared) == GUI_TOTAL_SIZE, "total");

#endif
