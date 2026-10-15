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

## 2. 2026-10-15 run (#4427 / SR-68): canvas の線の太さ・アンチエイリアス

### 2-1. 実装
- `setLineWidth` の値と `setDrawMode` の値を保持し、`plotLine` が参照する。
- 太さ 1 かつ aliasing は従来の Bresenham (既存の `draw_ops` の測定値は不変)。それ以外は `plotThickLine`: 画素中心から線分までの距離で被覆を求め、半幅以内を塗る。`kAntiAliasing` は境界の 1 px を線形に薄めて alpha に掛ける。
- 判定 harness: `canvas/line_width_main.cpp` (検証専用)、判定 `canvas/check_line_width.sh` (新規)。線 (4.5, 8.5)→(58.5, 40.5) を 64x64 に描く。

### 2-2. 実測 (変更前 = `origin/main` 基準 / 変更後 = 測定 commit `9d4a6d5c0`)

| ケース | 変更前 nonzero / partial / full | 変更後 nonzero / partial / full |
|---|---|---|
| w1 aliasing | 55 / 0 / 55 | 55 / 0 / 55 |
| w4 aliasing | 55 / 0 / 55 (太さ無視) | **263** / 0 / 263 |
| w1 AA | 55 / 0 / 55 (AA 無視) | **127** / 124 / 3 |
| w4 AA | 55 / 0 / 55 (太さ・AA 無視) | **335** / 136 / 199 |

- partial = 0 < alpha < 255 の画素数 (AA の証拠)。
- 判定 (`check_line_width.sh`): 変更後 rc=0 (4 項目 pass: 太い線の画素が多い / aliasing に部分被覆なし / AA に部分被覆あり / AA の画素が aliasing より多い)。変更前は rc=1 (太さ・AA が効かない)。
- 既存判定 `check_draw_ops.sh` 変更後も rc=0 (drawLine 49・drawLines 26・drawPolygon 607・drawEllipse 2472・drawBitmap 64、従来どおり)。
- 描画基盤の回帰: `check_render_poc.sh` rc=0 (render pass: nonzero_after=12000 text_px=112)、`check_canvas_syntax.sh` rc=0。

### 2-3. 測定条件と所要
- 測定 commit: `9d4a6d5c0` (コードを変えた最後の commit)。
- `check_line_width.sh` real 26.19 s (変更後)、変更前 25.58 s。load (開始時) 2.16。
- `check_draw_ops.sh` real 27.60 s (変更後・初回の canvas 再コンパイル込み)。
- review 対応後の HEAD: `git diff 9d4a6d5c0 HEAD -- tools/targets/serum2/gui/canvas` は file mode の変更 (`check_line_width.sh` 100644 → 100755) のみ。コードの内容差分は 0。実行権限の付与だけなので、再測定は行っていない。

### 2-4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 線端の形状 (cap・join)・破線 (`setLineStyle`) | 太い線の角が丸まる。破線は no-op | 子 #4469 (SR-71) |
| AA の被覆は線形近似 → SR-72 (§3) で面積被覆へ改めた | 解消 (§3) | — |
| 閉じた polyline の角の二重合成 → SR-72 (§3) で解消 | 解消 (§3) | — |

## 3. 2026-10-15 run (#4470 / SR-72): AA の面積被覆と閉じた polyline の角の二重合成

### 3-1. 原因 (変更前)
- `strokePolyline` が辺ごとに `plotLine` を呼び、`plotThickLine` が辺ごとに画素へ alpha 合成していた。角では 2 辺の境界 1 px が重なり、二重に合成される。
- AA の被覆は `clamp (half + 0.5 - distance)` の線形近似で、厳密な面積被覆ではない。

### 3-2. 方式 (変更後)
- `plotLines (points, closed, color)` に一本化 (`drawLine`・`drawLines`・`drawPolygon`・`drawEllipse` の輪郭が通る)。
- 画素ごとに「線分の和集合」の被覆を 1 回だけ求め、`blendRGBA` を 1 回だけ呼ぶ。角で辺が重なっても二重合成しない。
- 被覆: aliasing (太さ 1 を含む) は画素中心 1 点の内外 (0/1)。`kAntiAliasing` は画素を 4x4 に分けた標本点の割合 (面積被覆の近似・16 段階)。
- 太さ 1 かつ aliasing は従来どおり Bresenham (`forEachBresenhamPixel`)。判定の旧値と一致する。

### 3-3. 判定
- `check_line_width.sh` に角のケースを追加 (`corner_tri_w4_aa`: 頂点 (8.5,50.5)・(32.5,10.5)・(56.5,50.5)、w4 AA の閉じた三角形)。参照値は同じ標本法で「線分の和集合の被覆」を直接求めた値。判定 `corner_no_double_blend` は `over` (参照値より alpha が 1 を超えて濃い画素数) = 0 を要求。
- 変更前 (本体 = `origin/main` `d355f2a71`・判定は本 commit の新版): `corner_join over=105 maxdiff=64` → `corner_no_double_blend: fail`。
- 変更後 (測定 commit `66f9d8acd`): `corner_join over=0 maxdiff=0` → pass。rc=0。

| ケース | 変更前 nonzero / partial / full | 変更後 nonzero / partial / full |
|---|---|---|
| w1 aliasing | 55 / 0 / 55 | 55 / 0 / 55 |
| w4 aliasing | 263 / 0 / 263 | 263 / 0 / 263 |
| w1 AA | 127 / 124 / 3 (§2 旧方式) | 127 / 127 / 0 |
| w4 AA | 335 / 136 / 199 (§2 旧方式) | 335 / 140 / 195 |
| 閉じた三角形 w4 AA (角) | 692 / 278 / 414 (`over=105`) | 692 / 276 / 416 (`over=0`) |

- AA 行は被覆方式を 4x4 標本に変えたため、§2 の partial/full の値は置換される (nonzero は変わらない)。
- 既存判定: `check_draw_ops.sh` rc=0 (drawLine 49・drawLines 26・drawPolygon 607・drawEllipse 2472・drawBitmap 64、従来と同一)。`check_render_poc.sh` rc=0 (nonzero_after=12000 text_px=112)。`check_canvas_syntax.sh` rc=0。

### 3-4. 測定条件と所要
- 測定 commit: `66f9d8acd` (コードを変えた最後の commit)。
- `check_line_width.sh` real 24.28 s (測定 commit で再実行)。load (開始時) 1.46。
- `check_draw_ops.sh` real 24.42 s、`check_render_poc.sh` real 24.40 s、`check_canvas_syntax.sh` real 5.66 s (いずれも変更後・同一作業ツリー)。
- 測定環境: vstgui4_14_3 (`work/vstgui4`)、toolchain-emsdk (`work/emsdk`)。`work/` は gitignore。

### 3-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 線端の形状 (cap・join)・破線 (`setLineStyle`) | 太い線の角が丸まる。破線は no-op | 子 #4469 (SR-71) |
