> **付録**: `REPORT_EFFORT_APPENDIX_3422.md` (SR-55 / #3422) の続き。SR-62 (#4233) の gradient・9 分割・fillRectWithBitmap の実装と測定。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4233 / SR-62): canvas の gradient・9 分割・fillRectWithBitmap

### 1-1. 実装範囲
- `fillLinearGradient`: path の内側の画素ごとに、始点→終点への射影 t (0〜1) から色停止点を線形補間して置く。
- `fillRadialGradient`: 焦点 (center + originOffset) からの距離 / radius で色停止点を補間する。楕円形の放射は未対応。
- `drawBitmapNinePartTiled`: `CNinePartTiledDescription::calcRects` で 9 部分の元 rect と先 rect を求め、各部分を 1:1 タイルで置く。拡大縮小と quality は未対応で無視する。
- `fillRectWithBitmap`: srcRect を左上から繰り返して dstRect を塗る (1:1 タイル)。
- `CanvasGradient` (`canvas_gradient.h`、新規) を追加し、`CanvasPlatformFactory::createGradient` が `nullptr` でなく実体を返すようにした。これが無いと gradient を作れない。

### 1-2. 測定 commit と検証
- 測定 commit: `42b81b0d7` (main 取り込みの merge。canvas のコードを変えた最後の commit。SR-68 #4427 の線幅・drawMode を含む)。検証は同 commit で実施し、結果はすべて実測値。
- 判定 harness: `canvas/draw_ops_main.cpp` (SR-62 の 4 命令を追加)。判定スクリプト `canvas/check_draw_ops.sh` に次を追加した。
  - 期待する `draw_op` 行数 (9 件) が揃わなければ fail。
  - コンパイル失敗が 1 件でもあれば fail (従来は失敗 src を外して link し、op 行が 0 件でも rc=0 で通っていた)。
  - gradient は異なる色が 2 以上であること (一色の塗りを通さない)。

| 検証 | 結果 (rc) | 所要 (real) | load (開始時 1 分平均) |
|---|---|---|---|
| `check_canvas_syntax.sh` | **0** (8 ファイル全て rc=0) | 4 s | 0.50 |
| `check_draw_ops.sh` | **0** (link rc=0・compile fail=0・run rc=0) | 17 s | 0.42 (終了時 1.29) |
| `check_render_poc.sh` | **0** (nonzero_after=12000 text_px=112・compile 71/71 ok) | 17 s | 未記録 (run 中の計測なし) |
| `check_line_width.sh` | **0** (4 check pass・w4_aa partial=136 full=199) | 16 s | 未記録 |

`check_draw_ops.sh` の op 別結果 (`work/draw_ops/summary.txt`・op 別の所要は計っていない):

| op | 結果 |
|---|---|
| drawLine | pass (nonzero=49) |
| drawLines | pass (nonzero=26) |
| drawPolygon | pass (nonzero=607) |
| drawEllipse | pass (nonzero=2472) |
| drawBitmap | pass (nonzero=64) |
| fillLinearGradient | pass (nonzero=3136, distinct=57) |
| fillRadialGradient | pass (nonzero=3136, distinct=173) |
| drawBitmapNinePartTiled | pass (nonzero=3136) |
| fillRectWithBitmap | pass (nonzero=900) |

- drawLine / drawLines の既存判定は、SR-68 の線幅変更 (`plotThickLine` 分岐) の後も nonzero=49 / 26 で、前測定 (`c7c3a7ffc` 時点) と同値。判定は変わらない。
- 測定条件: vstgui4_14_3 (commit `b1e823550e23067c5adee67f05ac3ddaba7a25c9`、`git clone --filter=blob:none --no-checkout https://github.com/steinbergmedia/vstgui.git` → `git checkout vstgui4_14_3`)。toolchain-emsdk: 上流 emsdk を `git clone --depth 1 --branch 6.0.12 https://github.com/emscripten-core/emsdk.git` し `./emsdk install 6.0.12` → `./emsdk activate 6.0.12` で `work/emsdk` に展開 (`tools/m1/flags.sh` の pin と一致)。素材 `toolchain-emsdk` は本 run の `$ARTIFACTS_DIR` に無く、上流から取得した。`work/` は gitignore。
- 初回の draw run は素材展開と vstgui4 clone を含むため、所要の比較対象にしない。実測は素材を取得した後の 2 回目以降の run。

### 1-3. 画素数の意味
- 非ゼロ画素数は描いたかの判定にだけ使う。描いた範囲の大きさではない。
- 9 分割とタイル塗りは、ソースが一様色 (青) のため distinct を見ていない。gradient だけ色の変化を見る。

### 1-4. コード差分
- 測定 commit `42b81b0d7` から HEAD までの canvas のコード差分は 0 行 (この付録の commit は REPORT のみで canvas に触れない)。
- 参考: 旧測定 commit `c7c3a7ffc` から `42b81b0d7` までは SR-68 (#4427) の取り込みで差分がある (`git diff --stat c7c3a7ffc 42b81b0d7 -- tools/targets/serum2/gui/canvas` = 4 files, 183 insertions(+), 3 deletions(−)。内訳は `canvas_graphicsdevice.cpp` 42 行変更、`canvas_graphicsdevice.h` 5 行変更、`check_line_width.sh` 70 行追加、`line_width_main.cpp` 69 行追加)。このため上記の再測定を 42b81b0d7 で行った。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| drawArc・drawPoint・drawGraphicsPath (path 描画・円弧・点) | 円弧・点・path が no-op のまま | [SR-61] #4231 |
| gradient の楕円形の放射・アルファ付き停止点の厳密な合成 | 円形以外の radial と色の細部が近似 | #4550 [SR-77] |
| 拡大縮小・quality の bilinear (drawBitmap / 9 分割 / fillRectWithBitmap) | 1:1 のみ | #4551 [SR-78] |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
| 起動 (FLEngine) の KPI 前後 | 本 PR では動かしていない | 本 PR 本文に明記 |
