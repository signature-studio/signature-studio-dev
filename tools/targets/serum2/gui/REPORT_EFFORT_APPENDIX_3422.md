> **付録**: `REPORT_EFFORT.md` §16 (#2065 / SR-36) → `REPORT_EFFORT_APPENDIX_3260.md` (SR-50) の続き。SR-55 (#3422) の描画命令の実装と測定。測定値の正本はこの付録。

## 1. 2026-10-15 run (#3422 / SR-55): canvas の線・多角形・楕円・bitmap 描画

### 1-1. 実装範囲
- 前提の #3370 (SR-50) は 2026-10-15 01:24Z に merge 済み (main `da6ff541b`)。描画基盤 (bitmap 結線・clip・矩形・5x7 字形) は main にある。
- 実装 (`canvas_graphicsdevice.cpp`): `drawLine`・`drawLines` (1px Bresenham)・`drawPolygon` (偶奇則の走査線塗り + 輪郭)・`drawEllipse` (外接矩形の内接多角形で近似)・`drawBitmap` (1:1 転写。拡大縮小と `quality` は未対応で無視、alpha は globalAlpha と掛ける)。
- 未実装 (本 issue の残り・子 issue へ): `drawArc`・`drawPoint`・`drawGraphicsPath`・`fillLinearGradient`・`fillRadialGradient`・`drawBitmapNinePartTiled`・`fillRectWithBitmap`。

### 1-2. 測定 commit と検証
- 測定 commit: `137544ec2` (コードを変えた最後の commit)。
- 判定 harness: `canvas/draw_ops_main.cpp` (新規・検証専用)、判定スクリプト `canvas/check_draw_ops.sh` (新規)。各命令を bitmap へ直接呼び、rc と非ゼロ画素数を出す。

| 検証 | 結果 | 所要 | load (開始時) |
|---|---|---|---|
| `check_draw_ops.sh` (rc) | **0** | 14.76 s (real) | 0.27 |
| drawLine | pass (nonzero=49) | | |
| drawLines | pass (nonzero=26) | | |
| drawPolygon | pass (nonzero=607) | | |
| drawEllipse | pass (nonzero=2472) | | |
| drawBitmap | pass (nonzero=64) | | |

（各命令の rc は `run.log` の `draw_op ... rc=1` で確認。判定は rc=1 かつ nonzero>0。）
| `check_render_poc.sh` (rc, 既存の判定) | **0** (render pass: nonzero_after=12000 text_px=112) | 15.1 s (real) | 0.27 |
| `check_canvas_syntax.sh` (rc) | **0** (8 ファイル全て rc=0) | 3.8 s (real・ベースライン時) | — |

- 測定条件: vstgui4_14_3 (work/)、toolchain-emsdk (work/emsdk)。`work/` は gitignore。
- 初回の run は素材の展開と vstgui4 の clone を含むため所要の比較対象にしない。

### 1-3. コード差分 (測定 commit 以降)
`git diff 137544ec2 HEAD -- tools/targets/serum2/gui/canvas` の出力は、この付録 commit までで 0 行 (コード差分なし)。

### 1-4. no-op の計数について
`count_canvas_noop.py` は本体に入れ子の波括弧 (for 文) があると関数を読み飛ばすため、`drawBitmap`・`fillPolygon`・`ellipsePoints` 等を数えられない。main 基点の静的計数 (draw: functions=15 noop=12 impl=3) と本 PR の計数 (draw: functions=14 noop=7 impl=7) は、読み飛ばし方が違うため直接比べられない。描画が通ったことの根拠は 1-2 の判定 harness。計数スクリプトの修正は別件。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| drawArc・drawGraphicsPath (path 描画・円弧の画素化) | 円弧・path 描画が no-op のまま | 子 issue (本 PR 本文の表) |
| fillLinearGradient・fillRadialGradient | gradient 付き背景が描かれない | 子 issue |
| drawBitmapNinePartTiled・fillRectWithBitmap | 9 分割・タイル描画が no-op のまま | 子 issue |
| drawPoint | 点が描かれない (受入条件の範囲外だが no-op) | 子 issue へ同梱 |
| 拡大縮小・quality の bilinear | drawBitmap は 1:1 のみ | 子 issue へ同梱 |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
