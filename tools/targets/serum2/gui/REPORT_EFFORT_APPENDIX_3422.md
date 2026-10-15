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
| 線端の形状 (cap・join)・破線 (`setLineStyle`) | §3 で解消 (SR-71 #4469) | 解消済み |
| AA の被覆は線形近似 (厳密な面積被覆ではない) | 画素値は実機と一致しない可能性 | 子 #4470 (SR-72) |
| 閉じた polyline の角で AA の境界 1 px が二重に alpha 合成される (未測定) | 角が濃くなる。harness に角のケースは未追加 | 子 #4470 (SR-72) |

## 3. 2026-10-15 run (#4469 / SR-71): 線端 (cap)・接合 (join)・破線 (dash)

### 3-1. 実装
- `setLineStyle` の値を保持する (従来は no-op)。既定は vstgui の既定 (butt cap・miter join・破線なし)。
- 太い線 (`lineWidth > 1` または kAntiAliasing) は線分ごとの帯と、端 (cap)・折れ目 (join) の形状の和で被覆を求める。同じ線の中は画素ごとに被覆の最大値を取るので、接合部が二重に濃くならない。
- cap: butt は端で切る、round は端の円、square は半幅ぶん延ばした矩形。join: bevel は三角形、miter は先端まで延ばす (先端が幅の 4 倍を超えると bevel に落とす)、round は円。
- 破線: 折れ線を on 区間へ分けてから、区間ごとに描く。要素数が奇数のときは 2 周で 1 サイクル (SVG と同じ)。
- 太さ 1 かつ aliasing の Bresenham 経路は変えない (`check_draw_ops.sh` の drawLine 49 等は不変)。

### 3-2. 実測 (変更前 = `1483d6fd1` 基準 / 変更後 = 測定 commit `147f2392f`)
harness の 64x64 の線を 2 系統で数えた。変更前は cap・join・dash の 7 ケースを追加した状態で、形状の違いが出ないことを確認した。

| ケース | 変更前 nonzero / partial / full | 変更後 nonzero / partial / full |
|---|---|---|
| w1 aliasing | 55 / 0 / 55 | 55 / 0 / 55 |
| w4 aliasing | 263 / 0 / 263 | 250 / 0 / 250 (既定 cap が butt に変わった) |
| w1 AA | 127 / 124 / 3 | 127 / 126 / 1 |
| w4 AA | 335 / 136 / 199 | 319 / 132 / 187 |
| w8 cap butt | 551 / 0 / 551 (cap 無視) | 503 / 0 / 503 |
| w8 cap round | 551 / 0 / 551 | 551 / 0 / 551 |
| w8 cap square | 551 / 0 / 551 | 566 / 0 / 566 |
| w8 join bevel | 1216 / 0 / 1216 (join 無視) | 1186 / 0 / 1186 |
| w8 join round | 1216 / 0 / 1216 | 1216 / 0 / 1216 |
| w8 join miter | 1216 / 0 / 1216 | 1236 / 0 / 1236 |
| w4 dash 6/4 | 263 / 0 / 263 (破線 no-op) | 154 / 0 / 154 |

- 変更前の cap・join・dash は solid と同じ数字になり、no-op であることを示す。
- 変更後は cap が butt < round < square、join が bevel < round < miter の順に画素が増える。破線は solid より少ない。
- `check_line_width.sh` の判定は 7 項目 (既存 4 + 新規 3: `cap_shapes_differ`・`join_shapes_differ`・`dash_less_than_solid`)。
- ASCII で形を確認: butt は平ら、square は半幅ぶん延び、round は丸い。破線 6/4 は 6 画素の on と 4 画素の off を繰り返す。
- 既存の回帰: `check_draw_ops.sh` rc=0 (drawLine 49・drawLines 26・drawPolygon 607・drawEllipse 2472・drawBitmap 64、従来どおり)。`check_render_poc.sh` rc=0 (nonzero_after=12000 text_px=112)。`check_canvas_syntax.sh` rc=0。

### 3-3. 測定条件と所要
- 測定 commit: `147f2392f` (コードを変えた最後の commit)。
- `check_line_width.sh` real 21.03 s、load (開始時) 1.46。
- 素材: `toolchain-emsdk` を `work/emsdk` へ展開 (emcc 6.0.12)、vstgui は `vstgui4_14_3` (`b1e82355`) を clone。`work/` は gitignore。

### 3-4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 閉じた polyline の角で AA の境界 1 px が二重に alpha 合成される | §3 の接合は被覆の最大値で二重を防ぐが、AA 経路の角は未測定 | 子 #4470 (SR-72) |
| AA の被覆は線形近似 (厳密な面積被覆ではない) | 画素値は実機と一致しない可能性 | 子 #4470 (SR-72) |
