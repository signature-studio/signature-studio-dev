> **付録**: `REPORT_EFFORT_APPENDIX_3422.md` (SR-55 / #3422) の続き。SR-62 (#4233) の gradient・9 分割・fillRectWithBitmap の実装と測定。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4233 / SR-62): canvas の gradient・9 分割・fillRectWithBitmap

### 1-1. 実装範囲
- `fillLinearGradient`: path の内側の画素ごとに、始点→終点への射影 t (0〜1) から色停止点を線形補間して置く。
- `fillRadialGradient`: 焦点 (center + originOffset) からの距離 / radius で色停止点を補間する。楕円形の放射は未対応。
- `drawBitmapNinePartTiled`: `CNinePartTiledDescription::calcRects` で 9 部分の元 rect と先 rect を求め、各部分を 1:1 タイルで置く。拡大縮小と quality は未対応で無視する。
- `fillRectWithBitmap`: srcRect を左上から繰り返して dstRect を塗る (1:1 タイル)。
- `CanvasGradient` (`canvas_gradient.h`、新規) を追加し、`CanvasPlatformFactory::createGradient` が `nullptr` でなく実体を返すようにした。これが無いと gradient を作れない。

### 1-2. 測定 commit と検証
- 測定 commit: `c7c3a7ffc` (コードを変えた最後の commit)。検証は同 commit の HEAD で再現してから報告。
- 判定 harness: `canvas/draw_ops_main.cpp` (SR-62 の 4 命令を追加)。判定スクリプト `canvas/check_draw_ops.sh` に次を追加した。
  - 期待する `draw_op` 行数 (9 件) が揃わなければ fail。
  - コンパイル失敗が 1 件でもあれば fail (従来は失敗 src を外して link し、op 行が 0 件でも rc=0 で通っていた)。
  - gradient は異なる色が 2 以上であること (一色の塗りを通さない)。

| 検証 | 結果 | 所要 | load (開始→終了) |
|---|---|---|---|
| `check_draw_ops.sh` (rc) | **0** | 33 s (real) | 0.35 → 3.44 |
| drawLine | pass (nonzero=49) | | |
| drawLines | pass (nonzero=26) | | |
| drawPolygon | pass (nonzero=607) | | |
| drawEllipse | pass (nonzero=2472) | | |
| drawBitmap | pass (nonzero=64) | | |
| fillLinearGradient | pass (nonzero=3136, distinct=57) | | |
| fillRadialGradient | pass (nonzero=3136, distinct=173) | | |
| drawBitmapNinePartTiled | pass (nonzero=3136) | | |
| fillRectWithBitmap | pass (nonzero=900) | | |
| `check_render_poc.sh` (rc) | **0** (render pass: nonzero_after=12000 text_px=112) | 32 s (real) | 同上 |
| `check_canvas_syntax.sh` (rc) | **0** (8 ファイル全て rc=0) | 4 s (real) | — |

- 測定条件: vstgui4_14_3 (`work/vstgui4`)、toolchain-emsdk (`work/emsdk`)。`work/` は gitignore。
- 初回の draw run は素材展開と vstgui4 clone を含むため、所要の比較対象にしない。

### 1-3. 画素数の意味
- 非ゼロ画素数は描いたかの判定にだけ使う。描いた範囲の大きさではない。
- 9 分割とタイル塗りは、ソースが一様色 (青) のため distinct を見ていない。gradient だけ色の変化を見る。

### 1-4. コード差分 (測定 commit 以降)
`git diff c7c3a7ffc HEAD -- tools/targets/serum2/gui/canvas` の出力は、この付録 commit までで 0 行 (コード差分なし)。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| drawArc・drawPoint・drawGraphicsPath (path 描画・円弧・点) | 円弧・点・path が no-op のまま | [SR-61] (本 issue の範囲外) |
| gradient の楕円形の放射・アルファ付き停止点の厳密な合成 | 円形以外の radial と色の細部が近似 | 後続 issue (未起票) |
| 拡大縮小・quality の bilinear (drawBitmap / 9 分割 / fillRectWithBitmap) | 1:1 のみ | 後続 issue (未起票) |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
| 起動 (FLEngine) の KPI 前後 | 本 PR では動かしていない | 本 PR 本文に明記 |
