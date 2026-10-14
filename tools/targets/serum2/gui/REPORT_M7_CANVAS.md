# REPORT — [SR-7 #68] canvas platform の CanvasFrame を M7 HUD (tools/gui) へ接続できるか (静的照合)

- 日付: 2026-10-14 / 親: #68 (SR-7) / 前段: `gui/REPORT.md` (§4 の残件に M7 接続が無い)、`tools/gui/PROTOCOL.md` §1〜§3、`tools/gui/INTEGRATION.md` §2、`tools/targets/kilohearts/ui_eval/REPORT.md` (KH-7 の同種判定)
- 範囲: repo 内ファイルの静的照合のみ。素材 (plugins-serum2 等) は未使用。実描画・実 host 接続は未実施 (PoC は #2065 SR-36)。
- **製品 KPI: 動かしていない。** FLEngine 起動・GUI 描画は実行していない (`tools/flelift/boot/REPORT.md` の値は変更なし)。
- 既知類型 (`docs/DEFECTS.md`): 該当なし (lift 前の静的照合)。
- 測定 commit: `b60e2e42` (照合スクリプト `gui/m7_canvas_connect.py` の修正 commit。修正前は `aded3194`)。以後、測定対象のコードは変えていない (§6 の差分 0 行)。

## 0. 結論 (先出し)

| 観点 | 判定 |
|---|---|
| M7 HUD (surface 表 + out ring + in ring) へ `CanvasFrame` を**設計上**接続できるか | **接続可 (設計上)**。`CanvasFrame` の定義のうち 10 定義はプロトコルの記号に対応先がある |
| 実装状態 | 定義のうち**実装は 3 定義** (geometry の getGlobalPosition / setSize / getSize)。残りは stub (`return false` など)。M7 への送出 (invalidRect → GUI_CMD_PRESENT) は**未実装** |
| 接続で詰まる点 | (1) 画素形式が不一致 (canvas bitmap = RGBA、M7 surface = BGRA32)。(2) 対応記号の無い未対応 3 定義 (ポップアップメニュー・ドラッグ元)。(3) 要設計 6 定義 |
| 次の一手 | 送出部 (invalidRect → SURF_CREATE/CHANGE・PRESENT) の実装と 1 view の実描画を、PoC #2065 (SR-36) で動的に確認する。HUD 本体の操作性は #10 (GUI-10) |

「接続可」は**プロトコル上の対応先がある**という意味で、動作確認ではない。

## 1. 照合の対象と方法

- **単位・除外**: 「定義」= `canvas_frame.cpp` 中の `CanvasFrame::NAME (` の関数定義。`#if VSTGUI_ENABLE_DEPRECATED_METHODS` の分岐は評価せず両方を数える (doDrag は 2 定義)。コンストラクタ 1 件は除外。
- M7 側: `tools/gui/include/gui_proto.h` (出力 `GUI_CMD_*`・入力 `GUI_IN_*`・`GuiSurface` 表・共有領域の `cursor_x` / `buttons` / `mods`)。仕様は `tools/gui/PROTOCOL.md` §1〜§3。
- canvas 側: `tools/targets/serum2/gui/canvas/canvas_frame.cpp` の `CanvasFrame::*` 定義 (コンストラクタ除く 21 定義) と `canvas_bitmap.cpp` の画素形式。
- 照合器: `python3 tools/targets/serum2/gui/m7_canvas_connect.py`。本体が stub か (`(void)` 以外の文が無く、`return false` / `nullptr` / `{}` / 定数 enum だけか) を機械判定する。対応記号は `gui_proto.h` の**コメントを除いたコード部**に単語境界で存在するかを検査し、欠落なら exit 1。画素形式は `pixels` 宣言行のコメント (`BGRA32 top-down`) で確認する。
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
| getCurrentModifiers | stub | GUI_MOD_SHIFT / GUI_MOD_CTRL / GUI_MOD_ALT / GUI_MOD_META | 接続可 |
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

- `doDrag` は 2 定義 (`#if VSTGUI_ENABLE_DEPRECATED_METHODS` の版と新版)。判定は両方同じ。未対応 3 定義 = createPlatformOptionMenu 1 + doDrag 2。
- 独立検算 (grep, 別アルゴリズム): `grep -E 'CanvasFrame::[A-Za-z_]+ *\('` で 22 行 = コンストラクタ 1 + 定義 21。スクリプトの 21 定義と一致。
- 再現: HEAD `b60e2e42` で `python3 tools/targets/serum2/gui/m7_canvas_connect.py` を 3 回実行。exit 0、出力は `cmp` で一致 (§6)。

## 3. 判定の根拠

- **接続可 (10 定義)**
  - geometry (getGlobalPosition / setSize / getSize): surface 表の x・y・w・h と、変化時の `GUI_CMD_SURF_CHANGE` (再確保は `GUI_CMD_SURF_CREATE`)。
  - 入力状態 (getCurrentMousePosition / Buttons / Modifiers): host が共有領域の `cursor_x` / `buttons` / `mods` に書く値を読むだけ (`PROTOCOL.md` §2)。Modifiers は `mods` の 4 フラグ (`GUI_MOD_SHIFT` / `CTRL` / `ALT` / `META`、`gui_proto.h` L43) に対応する。
  - setMouseCursor → `GUI_CMD_SET_CURSOR` (w2 = IDC_* の数値)。CCursorType から IDC_* への対応表は未作成。
  - invalidRect → `GUI_CMD_PRESENT` (l,t,r,b) と `GUI_CMD_FRAME_END`。M7 の描画経路の中心。
  - onFrameClosed → `GUI_IN_CLOSE`。convertCurrentKeyEventToText → `GUI_IN_CHAR` (UTF-16)。
- **代替可 (1 定義)**: scrollRect は画素の移動を canvas 側で行い、移動先の矩形を PRESENT する。プロトコルの追加は不要。
- **要設計 (6 定義)**
  - showTooltip / hideTooltip: 別 surface を z 順の上位で作る方式が候補 (`tools/gui/REPORT.md` §14 の popup/tooltip z 順)。
  - getPlatformRepresentation: M7 にネイティブハンドルは無い。`pixels` (wasm アドレス) を返す必要があるかは利用側次第。
  - createPlatformTextEdit: `GUI_IN_IME` / `GUI_CMD_IME_POS` は届くが、編集ボックスを描く経路が無い。
  - setupGenericOptionMenu / createPlatformViewLayer: 必要性を Serum の uidesc と実行経路で確認してから決める。
- **未対応 (3 定義)**: createPlatformOptionMenu (1) と doDrag (2)。ポップアップメニューとドラッグ元を host に通知するコマンドが protocol に無い。`installDropTarget` はドロップ先のみ (`tools/gui/INTEGRATION.md` §2)。
- **対象外 (1 定義)**: getPlatformType (定数の返却)。

## 4. 画素形式の不一致

- canvas: `canvas_bitmap.cpp` の `lockPixels` が `IPlatformBitmapPixelAccess::kRGBA` を返す (R,G,B,A の順)。
- M7: `GuiSurface.pixels` は **BGRA32 top-down** (`gui_proto.h` L69 の宣言行のコメント、`PROTOCOL.md` §2)。
- 既存の実測は `tools/gui/REPORT.md` §3 (性能) の「描画ワーカ (BGRA→RGBA + putImageData)」行が正本 (本 REPORT には数値を複写しない)。これは **M7 → ブラウザ** の向きの変換。本 PR が必要とする **RGBA→BGRA (canvas → M7)** の変換コストは未測定 (§5)。
- 解消案 (未決): (i) 描画バッファを BGRA で持つ (VSTGUI 版の PixelFormat に BGRA 相当があるかは未確認)、(ii) PRESENT 前に surface へ変換コピーする (画素コピーが 1 回増える)。

## 5. 残る作業 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| CanvasFrame の送出部 (invalidRect → SURF_CREATE/CHANGE・PRESENT) の実装 | 接続可 10 定義のうち実装は geometry の 3 定義のみ | #2065 (SR-36, PoC の前提) |
| 1 view の実描画と PRESENT の動的確認・画素形式の解消 (RGBA→BGRA の変換コストを含む) | 静的照合のみ。変換コストは未測定 | #2065 (SR-36) |
| 未対応 3 定義 (ポップアップメニュー・ドラッグ元) の protocol 追加の要否 | uidesc 上で使われるかで決まる | #68 (要否の調査)。要と確定したら protocol 追加と HUD 側の対応は #10 (GUI-10「GDI/フレーム転送 → 操作可能 HUD (M7 相当)」) の範囲 |
| 要設計 6 定義 | 利用側の要否の確認が先 | #68 (要否の調査)。要と確定したら #10 (GUI-10) |
| Splice 実体化分岐 | 本 REPORT の範囲外 | #1917 (SR-28) |

protocol 追加の要否は、canvas の利用側 (uidesc と実行経路) の調査であり、#68 の残件 (M7 接続の調査) に当たる。HUD の実装と操作性は #10 が持つ。

## 6. 検証

- 測定 commit: `b60e2e42` (照合スクリプトの修正 commit)。以後、`tools/gui/include/gui_proto.h`・`tools/targets/serum2/gui/canvas/`・`m7_canvas_connect.py` の変更は無い。
- 差分: `git diff b60e2e42 HEAD -- tools/gui/include/gui_proto.h tools/targets/serum2/gui/canvas/ tools/targets/serum2/gui/m7_canvas_connect.py` = **0 行**。
- 再現: HEAD `b60e2e42` で 3 回実行し、exit 0 (3/3)、出力は `cmp` で一致。
- 所要 (逐次・並列数 1・`nproc` 4): 3 回の実測 25〜26 ms (26 / 25 / 25 ms、min–max 25–26 ms)。load average (1/5/15 分) は実行前後で 0.16 0.39 0.20 (同値)。
- WORKFLOW §6 の確認: `git status --porcelain=v1 -- tools/targets/serum2/gui tools/gui` は空 (取りこぼし・他担当 WIP の混入なし)。`find tools/targets/serum2/gui tools/gui -type f -size +20M -not -path '*/work/*'` は 0 件。
- ネガティブコントロール (WORKFLOW §5): 修正前 `aded3194` の照合器と修正後 `b60e2e42` の照合器を、HEAD の `gui_proto.h`・`canvas/`・照合器をそのまま同じ相対位置に複製したミラーで比較した (repo は変更していない)。ミラーの `gui_proto.h` を sed で 1 件壊して実行し、復元する。

| 壊し方 (ミラーの gui_proto.h) | 修正前 (aded3194) | 修正後 (b60e2e42) |
|---|---|---|
| N0 無加工 | exit 0 | exit 0 |
| N1 `uint32_t buttons, mods;` 行を削除 | exit 0・MISSING なし (偽陰性。L26 のコメント `a=buttons mask` に一致) | exit 1・`MISSING: buttons` |
| N2 `uint32_t pixels;` 行を削除 | exit 0・MISSING なし (偽陰性。L50・L71 のコメントに一致) | exit 1・`MISSING: pixels`・画素形式 M7 = 不明 |
| N3 `GUI_CMD_SET_CURSOR` → `GUI_CMD_SET_CURSORX` (全箇所) | exit 0 (偽陰性。改名後の名前が元の記号を部分一致で含む) | exit 1・`MISSING: GUI_CMD_SET_CURSOR` |
| N3b `GUI_CMD_SET_CURSOR` → `GUI_CMD_SETCURSOR` (全箇所) | exit 1・`MISSING: GUI_CMD_SET_CURSOR` | exit 1・`MISSING: GUI_CMD_SET_CURSOR` |
| N4 `GUI_MOD_META = 8` → `GUI_MOD_METX = 8` | (修正前は META を検査しない) | exit 1・`MISSING: GUI_MOD_META` |
| N5 `pixels` 行の `BGRA32 top-down` → `RGBA top-down` | (未実行) | exit 0 (形式は終了コードの対象外)・画素形式 M7 = 不明・不一致 = True |
| N6 復元 (無加工) | exit 0 | exit 0 |

- N1・N2 は、記号がコードから消えても同じ語がコメントに残っていたため修正前は見逃した。N3 は改名後の名前が元の記号を部分一致で含んだため見逃した。修正後はすべて exit 1 で検出する。
- N5 は画素形式の表示行の変化であり、exit code の対象ではない (形式は表示行で確認する)。
- 範囲外: 実 VSTGUI の描画、実 host 接続、mac 版、工数 (人日)、FLEngine 起動 (製品 KPI は未測定)。
