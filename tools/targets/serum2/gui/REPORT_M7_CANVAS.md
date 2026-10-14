# REPORT — [SR-7 #68] canvas platform の CanvasFrame を M7 HUD (tools/gui) へ接続できるか (静的照合)

- 日付: 2026-10-14 / 親: #68 (SR-7) / 前段: `gui/REPORT.md` (§4 の残件に M7 接続が無い)、`tools/gui/PROTOCOL.md` §1〜§3、`tools/gui/INTEGRATION.md` §2、`tools/targets/kilohearts/ui_eval/REPORT.md` (KH-7 の同種判定)
- 範囲: repo 内ファイルの静的照合のみ。素材 (plugins-serum2 等) は未使用。実描画・実 host 接続は未実施 (PoC は #2065 SR-36)。
- **製品 KPI: 動かしていない。** FLEngine 起動・GUI 描画は実行していない (`tools/flelift/boot/REPORT.md` の値は変更なし)。
- 既知類型 (`docs/DEFECTS.md`): 該当なし (lift 前の静的照合)。
- 測定 commit: `5a2214d1` (照合スクリプト `gui/m7_canvas_connect.py` の追加。以後このスクリプトは変更していない)。

## 0. 結論 (先出し)

| 観点 | 判定 |
|---|---|
| M7 HUD (surface 表 + out ring + in ring) へ `CanvasFrame` を**設計上**接続できるか | **接続可 (設計上)**。`CanvasFrame` の 21 定義のうち 10 件はプロトコルの記号に対応先がある |
| 実装状態 | 21 定義のうち**実装は 3 件** (geometry の getGlobalPosition / setSize / getSize)。残り 18 件は stub (`return false` など)。M7 への送出 (invalidRect → GUI_CMD_PRESENT) は**未実装** |
| 接続で詰まる点 | (1) 画素形式が不一致 (canvas bitmap = RGBA、M7 surface = BGRA32)。(2) 対応記号の無い未対応 3 件 (ポップアップメニュー・ドラッグ元)。(3) 要設計 6 件 |
| 次の一手 | 送出部 (invalidRect → SURF_CREATE/CHANGE・PRESENT) の実装と 1 view の実描画を、PoC #2065 (SR-36) で動的に確認する |

「接続可」は**プロトコル上の対応先がある**という意味で、動作確認ではない。

## 1. 照合の対象と方法

- M7 側: `tools/gui/include/gui_proto.h` (出力 `GUI_CMD_*`・入力 `GUI_IN_*`・`GuiSurface` 表・共有領域の `cursor_x` / `buttons`)。仕様は `tools/gui/PROTOCOL.md` §1〜§3。
- canvas 側: `tools/targets/serum2/gui/canvas/canvas_frame.cpp` の `CanvasFrame::*` 定義 (コンストラクタ除く 21 件) と `canvas_bitmap.cpp` の画素形式。
- 照合器: `python3 tools/targets/serum2/gui/m7_canvas_connect.py` (本 PR)。本体が stub か (`(void)` 以外の文が無く、`return false` / `nullptr` / `{}` / 定数 enum だけか) を機械判定し、対応記号が `gui_proto.h` に存在するかを検査する (欠落なら exit 1)。
- 判定 (接続可 / 代替可 / 要設計 / 未対応 / 対象外) は対応表の人手判断。スクリプトが検査するのは記号の存在と本体の stub 判定だけ。

## 2. 実測 (スクリプト出力)

```
| method | 本体 | M7 記号 (gui_proto.h) | 判定 |
|---|---|---|---|
| getGlobalPosition | 実装 | GuiSurface / GUI_CMD_SURF_CHANGE | 接続可 |
| setSize | 実装 | GUI_CMD_SURF_CREATE / GUI_CMD_SURF_CHANGE | 接続可 |
| getSize | 実装 | GuiSurface | 接続可 |
| getCurrentMousePosition | stub | cursor_x | 接続可 |
| getCurrentMouseButtons | stub | buttons | 接続可 |
| getCurrentModifiers | stub | GUI_MOD_SHIFT | 接続可 |
| setMouseCursor | stub | GUI_CMD_SET_CURSOR | 接続可 |
| invalidRect | stub | GUI_CMD_PRESENT / GUI_CMD_FRAME_END | 接続可 |
| scrollRect | stub | GUI_CMD_PRESENT | 代替可 |
| showTooltip | stub | GUI_CMD_SURF_CREATE | 要設計 |
| hideTooltip | stub | GUI_CMD_SURF_DESTROY | 要設計 |
| getPlatformRepresentation | stub | pixels | 要設計 |
| createPlatformTextEdit | stub | GUI_IN_IME / GUI_CMD_IME_POS | 要設計 |
| createPlatformOptionMenu | stub | — | 未対応 |
| createPlatformViewLayer | stub | — | 要設計 |
| doDrag | stub | — | 未対応 |
| doDrag | stub | — | 未対応 |
| getPlatformType | stub | — | 対象外 |
| onFrameClosed | stub | GUI_IN_CLOSE | 接続可 |
| convertCurrentKeyEventToText | stub | GUI_IN_CHAR | 接続可 |
| setupGenericOptionMenu | stub | — | 要設計 |

定義数 21 / stub 18 / 実装 3
接続可: 10 / 代替可: 1 / 要設計: 6 / 未対応: 3 / 対象外: 1
画素形式: canvas bitmap = RGBA / M7 surface = BGRA32 / 不一致 = True
```

- `doDrag` は 2 定義 (`#if VSTGUI_ENABLE_DEPRECATED_METHODS` の版と新版)。判定は両方同じ。
- 再現: `python3 tools/targets/serum2/gui/m7_canvas_connect.py` を 2 回実行し出力が一致 (`cmp` 0 差分)。exit 0。

## 3. 判定の根拠

- **接続可 (10)**
  - geometry (getGlobalPosition / setSize / getSize): surface 表の x・y・w・h と、変化時の `GUI_CMD_SURF_CHANGE` (再確保は `GUI_CMD_SURF_CREATE`)。
  - 入力状態 (getCurrentMousePosition / Buttons / Modifiers): host が共有領域の `cursor_x` / `buttons` / `mods` に書く値を読むだけ (`PROTOCOL.md` §2)。
  - setMouseCursor → `GUI_CMD_SET_CURSOR` (w2 = IDC_* の数値)。CCursorType から IDC_* への対応表は未作成。
  - invalidRect → `GUI_CMD_PRESENT` (l,t,r,b) と `GUI_CMD_FRAME_END`。M7 の描画経路の中心。
  - onFrameClosed → `GUI_IN_CLOSE`。convertCurrentKeyEventToText → `GUI_IN_CHAR` (UTF-16)。
- **代替可 (1)**: scrollRect は画素の移動を canvas 側で行い、移動先の矩形を PRESENT する。プロトコルの追加は不要。
- **要設計 (6)**
  - showTooltip / hideTooltip: 別 surface を z 順の上位で作る方式が候補 (`tools/gui/REPORT.md` §14 の popup/tooltip z 順)。
  - getPlatformRepresentation: M7 にネイティブハンドルは無い。`pixels` (wasm アドレス) を返す必要があるかは利用側次第。
  - createPlatformTextEdit: `GUI_IN_IME` / `GUI_CMD_IME_POS` は届くが、編集ボックスを描く経路が無い。
  - setupGenericOptionMenu / createPlatformViewLayer: 必要性を Serum の uidesc と実行経路で確認してから決める。
- **未対応 (3)**: createPlatformOptionMenu と doDrag (2 定義)。ポップアップメニューとドラッグ元を host に通知するコマンドが protocol に無い。`installDropTarget` はドロップ先のみ (`tools/gui/INTEGRATION.md` §2)。
- **対象外 (1)**: getPlatformType (定数の返却)。

## 4. 画素形式の不一致

- canvas: `canvas_bitmap.cpp` の `lockPixels` が `IPlatformBitmapPixelAccess::kRGBA` を返す (R,G,B,A の順)。
- M7: `GuiSurface.pixels` は **BGRA32 top-down** (`gui_proto.h`、`PROTOCOL.md` §2)。
- 解消案 (未決): (i) 描画バッファを BGRA で持つ (VSTGUI 版の PixelFormat に BGRA 相当があるかは未確認)、(ii) PRESENT 前に surface へ変換コピーする (画素コピーが 1 回増える)。コストは `tools/gui/REPORT.md` §9 の転送・変換の実測を正とする (本 REPORT には数値を複写しない)。

## 5. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| CanvasFrame の送出部 (invalidRect → SURF_CREATE/CHANGE・PRESENT) の実装 | 接続可 10 件のうち実装は geometry の 3 件のみ | #2065 (SR-36, PoC の前提) |
| 1 view の実描画と PRESENT の動的確認・画素形式の解消 | 静的照合のみ。変換コストは未測定 | #2065 (SR-36) |
| 未対応 3 件 (ポップアップメニュー・ドラッグ元) の protocol 追加の要否 | uidesc 上で使われるかで決まる | #68 残作業 |
| 要設計 6 件 | 利用側の要否の確認が先 | #68 残作業 |
| Splice 実体化分岐 | 本 REPORT の範囲外 | #1917 (SR-28) |

## 6. 検証

- 照合: `python3 tools/targets/serum2/gui/m7_canvas_connect.py` を HEAD `5a2214d1` 相当の tree で実行。exit 0、2 回の出力が一致。
- 所要: real 0.02 s (`/usr/bin/time`)。load average は 0.12 (実行前後で同値)。
- 差分: `git diff 5a2214d1 HEAD -- tools/targets/serum2/gui/*.py` = 0 行 (本 REPORT の追加以降にコード変更は無い)。
- 範囲外: 実 VSTGUI の描画、実 host 接続、mac 版、工数 (人日)、FLEngine 起動 (製品 KPI は未測定)。
