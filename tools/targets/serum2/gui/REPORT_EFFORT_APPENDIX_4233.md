> **付録**: `REPORT_EFFORT_APPENDIX_3422.md` (SR-55 / #3422) の続き。SR-62 (#4233) の gradient・9 分割・fillRectWithBitmap の実装と測定。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4233 / SR-62): canvas の gradient・9 分割・fillRectWithBitmap

### 1-1. 実装範囲
- `fillLinearGradient`: path の内側の画素ごとに、始点→終点への射影 t (0〜1) から色停止点を線形補間して置く。
- `fillRadialGradient`: 焦点 (center + originOffset) からの距離 / radius で色停止点を補間する。楕円形の放射は未対応。
- `drawBitmapNinePartTiled`: `CNinePartTiledDescription::calcRects` で 9 部分の元 rect と先 rect を求め、各部分を 1:1 タイルで置く。拡大縮小と quality は未対応で無視する。
- `fillRectWithBitmap`: srcRect を左上から繰り返して dstRect を塗る (1:1 タイル)。 (注: #4551 (SR-78) で srcRect → dstRect の拡大縮小へ置き換えた。PM 判断待ち。REPORT_EFFORT_APPENDIX_4551.md §1-6)
- `CanvasGradient` (`canvas_gradient.h`、新規) を追加し、`CanvasPlatformFactory::createGradient` が `nullptr` でなく実体を返すようにした。これが無いと gradient を作れない。

### 1-2. 測定 commit と検証
- 測定 commit: `021b79922` (main 取り込みの merge。canvas のコードを変えた最後の commit。SR-62 の実装と main の SR-69 (#4428) を含む)。検証 HEAD も `021b79922`。
- 前版 (round 3 まで) の測定 commit `42b81b0d7` と「差分 0 行」の記述は誤りだった。`42b81b0d7` から `021b79922` までに canvas の差分があったため、全検証を `021b79922` で取り直した。
- 判定 harness: `canvas/draw_ops_main.cpp` (SR-62 の 4 命令を追加)。判定スクリプト `canvas/check_draw_ops.sh` に次を追加した。
  - 期待する `draw_op` 行数 (9 件) が揃わなければ fail。
  - コンパイル失敗が 1 件でもあれば fail (従来は失敗 src を外して link し、op 行が 0 件でも rc=0 で通っていた)。
  - gradient は異なる色が 2 以上であること (一色の塗りを通さない)。
- 測定方法: 5 本を直列に 1 本ずつ実行 (各 run は前の run の終了後に開始)。開始前に load が 1 分平均で 1.15 まで下がるのを待った。各 run は `xargs -P 4` で 4 core を使うため、load は run 自身で上がる。2 本を同時に走らせた試行 (load 6.05・所要 65.9 s) は比較対象から外した。

| 検証 | 結果 (rc) | 所要 (real) | load (開始 → 終了・1 分平均) |
|---|---|---|---|
| `check_canvas_syntax.sh` | **0** (8 ファイル全て rc=0・errors=0) | 7.1 s | 1.15 → 1.21 |
| `check_draw_ops.sh` | **0** (link rc=0・compile fail=0・run rc=0・9 op pass) | 31.9 s | 1.21 → 2.31 |
| `check_render_poc.sh` | **0** (compile 71/71 ok・nonzero_after=12000・text_px=112) | 31.8 s | 2.31 → 2.98 |
| `check_line_width.sh` | **0** (4 check pass・w4_aa partial=136 full=199) | 32.0 s | 2.98 → 3.43 |

`check_transform.sh` (main 由来の SR-69 の判定) の実測は `REPORT_EFFORT_APPENDIX_4428.md` §1-6 に置いた。

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
- 測定条件・素材: toolchain-emsdk は `$ARTIFACTS_DIR/toolchain-emsdk.tar.zst` (実在を `ls` で確認) を `tar --zstd -xf` で `work/` に展開した (`work/emsdk/upstream/emscripten`・展開 3.7 s)。上流 emsdk の clone と install は行っていない。vstgui4_14_3 は上流を `git clone --filter=blob:none --no-checkout` して `git checkout vstgui4_14_3` (commit `b1e82355`)。`work/` は gitignore。

### 1-3. 画素数の意味
- 非ゼロ画素数は描いたかの判定にだけ使う。描いた範囲の大きさではない。
- 9 分割とタイル塗りは、ソースが一様色 (青) のため distinct を見ていない。gradient だけ色の変化を見る。

### 1-4. コード差分
- `git diff 021b79922 HEAD -- tools/targets/serum2/gui/canvas` の出力は 0 行 (測定 commit = 検証 HEAD)。この付録を含む commit は REPORT のみで canvas に触れない。
- 参考: 旧測定 commit `42b81b0d7` から `021b79922` までの canvas 差分は main 側の SR-69 (#4428) の取り込み分。`git diff --stat 42b81b0d7 021b79922 -- tools/targets/serum2/gui/canvas` = 5 files, 200 insertions(+), 12 deletions(−) (`canvas_font.cpp`・`canvas_graphicsdevice.{cpp,h}`・`check_transform.sh`・`transform_check_main.cpp`)。判定結果に効き得るため、上の表は全て `021b79922` で取り直した値。
- 参考: 旧々測定 commit `c7c3a7ffc` から `42b81b0d7` までは SR-68 (#4427) の取り込みで差分がある (4 files, 183 insertions(+), 3 deletions(−))。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| drawArc・drawPoint・drawGraphicsPath (path 描画・円弧・点) | 円弧・点・path が no-op のまま | [SR-61] #4231 |
| gradient の楕円形の放射・アルファ付き停止点の厳密な合成 | 円形以外の radial と色の細部が近似 | #4550 [SR-77] |
| 拡大縮小・quality の bilinear (drawBitmap / 9 分割 / fillRectWithBitmap) | 1:1 のみ | #4551 [SR-78] |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 未起票 (`count_canvas_noop` を含む issue は 0 件。起票要否は PM 判断) |
| 起動 (FLEngine) の KPI 前後 | 本 PR では動かしていない | 本 PR 本文に明記 |
