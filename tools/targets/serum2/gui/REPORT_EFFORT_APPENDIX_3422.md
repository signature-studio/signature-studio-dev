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
- 太さ 1 かつ aliasing は従来どおり Bresenham (`forEachBresenhamPixel`)。判定の旧値と一致する。ただし画素は bit mask に立てるだけで、閉じた polyline の頂点の画素も辺ごとに二重合成せず、1 回だけ合成する (半透明色でも二重に濃くならない)。
- 計算量: 画素ごとの bit mask は線分の bbox を半幅 +1 で広げた範囲だけを走査する (線分ごとに全画素を見ない)。全標本が立った画素は以降の標本計算を省く。

### 3-3. 判定
- `check_line_width.sh` に角のケースを追加 (`corner_tri_w4_aa`: 頂点 (8.5,50.5)・(32.5,10.5)・(56.5,50.5)、w4 AA の閉じた三角形)。参照値は同じ標本法で「線分の和集合の被覆」を直接求めた値。判定 `corner_no_double_blend` は `over` (参照値より alpha が 1 を超えて濃い画素数) = 0 を要求。
- 変更前 (本体 = `origin/main` `d355f2a71`・判定は本 commit の新版): `corner_join over=105 maxdiff=64` → `corner_no_double_blend: fail`。
- 変更後 (測定 commit `66f9d8acd`): `corner_join over=0 maxdiff=0` → pass。rc=0。
- 注意: 参照値は実装と同じ 4x4 標本法・同じ距離関数で作っている。判定の意味は「和集合を 1 回だけ合成したか」のみ。実機 VSTGUI の画素との一致は測っていない。
- review 対応 (本 commit 後): 同じ判定 (`corner_join over=0 maxdiff=0`) を native (`g++`・vstgui4_14_3・emsdk 無し) で再確認した。

### 3-5. 計算量の実測 (review 対応・native)
- 測定: `g++` で `canvas_graphicsdevice.cpp` を旧 (`66f9d8acd^`) と新 (HEAD) で各々ビルドし、同じ bench (`drawEllipse`・`Stroked`・AA・太さ 4 (d200 は 1 px 太さも)) を 1 回あたり平均で計った。`check_line_width.sh` の emsdk は無いので wasm の値ではない。
- 結果 (1 回あたり ms):

| ケース | 旧 -O0 | 新 -O0 | 旧 -O2 | 新 -O2 |
|---|---|---|---|---|
| 楕円 d200 w4 AA | 1.47 | 7.83 | 0.59 | 2.68 |
| 楕円 d400 w4 AA | 2.99 | 16.22 | 1.16 | 4.89 |
| 楕円 d200 w1 AA | 0.51 | 4.03 | 0.19 | 1.34 |

- 頂点の二重合成 (太さ 1 aliasing・`globalAlpha` 0.5・赤線): 旧 `max_alpha=192` (2 回合成) → 新 `max_alpha=128` (1 回)。native・同じ三角形。
- 判断: 新方式は旧方式の約 4.5 倍 (-O2)。reviewer の「全辺を画素ごとに見る」最悪 (約 2.6 億回) にはならない (辺 bbox 走査で抑えている)。ただし楕円の描画は旧より重くなるため、wasm の実機での時間は未測定。画面に多数の楕円を描く場面では再測定が要る。未解決として残す。

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

## 4. 2026-10-15 run (#4469 / SR-71): 線端 (cap)・接合 (join)・破線 (dash) を plotLines の被覆に載せる

### 4-1. 方式 (統合後)
- 統合は main の `plotLines` (線分の被覆の和集合を画素ごとに 1 回だけ合成) を土台にする。PR 側の `strokeThick` (符号付き距離) は削除した。
- cap・join の形状は `plotLines` の被覆に入れる (cap: butt は何もしない・round は端の円・square は半幅ぶん延ばした矩形。join: bevel は三角形・miter は先端まで延ばす (先端が幅の 4 倍を超えると bevel)・round は円)。形状どうしが重なっても標本は 1 回だけ立つので二重合成しない。
- 破線は `dashRuns` で on 区間に分け、区間ごとに `plotLines` を呼ぶ。
- 太さ 1 かつ aliasing は `plotThinPolyline` (Bresenham の画素を集めて sort・unique し、1 回ずつ合成)。辺どうしが共有する頂点の画素を二重に合成しない。
- 閉じた線の点が 2 つのとき閉じない (従来どおり)。

### 4-2. 測定 commit と検証
- 測定 commit: `14753d025` (AA 判定の追加と harness のケース追加。コードを変えた最後の commit)。HEAD 側の追加は REPORT のみ。
- 判定: `check_line_width.sh` (12 項目) / `check_draw_ops.sh` / `check_render_poc.sh` / `check_canvas_syntax.sh`。

| 検証 | 結果 | 所要 (real) | load (全検証の後に読んだ 1 分平均) |
|---|---|---|---|
| `check_line_width.sh` | rc=0 (12 項目 pass) | 16.96 s | 2.07〜2.90 (各検証の直後) |
| `check_draw_ops.sh` | rc=0 (5 op の nonzero は main と一致) | 16.73 s | 同上 |
| `check_render_poc.sh` | rc=0 (nonzero_after=12000 text_px=112) | 16.63 s | 同上 |
| `check_canvas_syntax.sh` | rc=0 (platformfactory.cpp errors=0) | 3.90 s | 同上 |

- 素材: `toolchain-emsdk` を `work/emsdk` へ展開 (`em++` 利用)、vstgui は `steinbergmedia/vstgui` の tag `vstgui4_14_3` を `work/vstgui4` へ clone。`work/` は gitignore。

### 4-3. 実測 (統合後・64x64)
| ケース | nonzero / partial / full |
|---|---|
| w1 aliasing | 55 / 0 / 55 |
| w4 aliasing | 250 / 0 / 250 |
| w1 AA | 127 / 127 / 0 |
| w4 AA | 321 / 140 / 181 |
| 閉じた三角形 w4 AA (丸い接合の角) | 692 / 276 / 416 (`corner_join over=0 maxdiff=0`) |
| w8 cap butt | 503 / 0 / 503 |
| w8 cap round | 551 / 0 / 551 |
| w8 cap square | 566 / 0 / 566 |
| w8 join bevel | 1117 / 0 / 1117 |
| w8 join round | 1141 / 0 / 1141 |
| w8 join miter | 1184 / 0 / 1184 |
| w4 dash 6/4 | 154 / 0 / 154 |
| w8 cap butt (AA) | 575 / 144 / 431 |
| w8 cap round (AA) | 635 / 160 / 475 |
| w8 cap square (AA) | 644 / 157 / 487 |
| w8 join bevel (AA) | 1204 / 264 / 940 |
| w8 join round (AA) | 1242 / 276 / 966 |
| w8 join miter (AA) | 1279 / 286 / 993 |
| w4 dash 6/4 (AA) | 227 / 134 / 93 |

- AA の部分被覆は cap・join・dash の全形状で正 (aliasing は 0)。AA の非ゼロ数の順序は aliasing と同じ (cap butt < round < square、join bevel < round < miter)。破線 AA (227) は solid AA の w4 (321) より少ない。
- `check_draw_ops.sh` の既存値は main と一致: drawLine 49・drawLines 26・drawPolygon 607・drawEllipse 2472・drawBitmap 64。
- 判定: `corner_no_double_blend` (over=0) pass・`cap_shapes_differ` pass・`join_shapes_differ` pass・`dash_less_than_solid` pass。AA 側は `aa_shapes_partial`・`aa_cap_shapes_differ`・`aa_join_shapes_differ`・`aa_dash_less_than_solid` が pass。既存 4 項目も pass。
- 見込みの差: AA の cap・join・dash は solid との差が出ている (部分被覆 0 ではない)。ただし部分被覆の値は 4x4 標本法の近似で、実機 VSTGUI との一致は未測定 (§4-4)。
- 注意: 角の参照値は線分の和集合の被覆 (§3 と同じ 4x4 標本法)。実機 VSTGUI の画素との一致は測っていない。

### 4-4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| miter の先端が幅の 4 倍を超えるときは bevel に落とす (VSTGUI の miterlimit 既定値との一致は未測定) | 鋭い角の形が実機と異なる可能性 | 未起票 (PR 本文の表に残す) |
| 破線の on/off の端 (cap の扱い) は実機と未照合 | 破線の端の画素が実機と 1 px ずれる可能性 | 未起票 (PR 本文の表に残す) |
| `setLineStyle` の cap・join・破線は save/restore の対象外で、一度設定すると後続の描画に残る (lineWidth と同じ扱い) | 設定後の別の線が意図せず破線・太い cap になる可能性 | 未起票 (PR 本文の表に残す) |
| 楕円・多数の線の wasm 実行時間は未測定 (§3-5 の native 計測は旧方式) | 描画の重さ | §3 の未解決を継続 |
