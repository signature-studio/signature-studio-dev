> **付録**: `REPORT_EFFORT.md` §16 (#2065 / SR-36) → `REPORT_EFFORT_APPENDIX_3422.md` (SR-55) の続き。SR-61 (#4231) の path・円弧・点の描画と測定。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4231 / SR-61): canvas の円弧・点・path 描画

### 1-1. 実装範囲
- 前提の #3422 (SR-55) は main 取り込み済み。`drawLine`・`drawLines`・`drawPolygon`・`drawEllipse`・`drawBitmap` は main にある。
- 実装 (`canvas/canvas_graphicsdevice.cpp`):
  - `drawArc`: 角度はラジアン (Cairo の `cairo_arc` と同じ単位)。弧を多角形に近似し、塗りは弧と弦で囲んだ領域、線は弧だけ。
  - `drawPoint`: 1 画素を、四捨五入した位置に `blendPixel` で置く。`true` を返すので、`CDrawContext::drawPoint` の drawRect フォールバック (2×2 px) は通らなくなる。
  - `drawGraphicsPath`: path の全 subpath を使う。`Filled` は非零巻き数則、`FilledEvenOdd` は偶奇則で塗る。`Stroked` は各 subpath を閉じずに線で描く。`transformation` を頂点に掛けた後、`transformMatrix` (setTransformMatrix の状態) も頂点に掛ける。
  - `drawArc`・`drawPoint` も `transformMatrix` を掛ける (SR-69 #4428 の契約。`3f76a2119` で追加。それ以前は掛けていなかった)。
- 補助: `fillPolygon` を `fillRings` (複数輪郭・非零/偶奇の切替) に広げた。`drawPolygon`・`drawEllipse` の塗りは偶奇則のまま (画素数は 3422 の値と一致)。
- `canvas_graphicspath.{h,cpp}`: `subpaths ()` を追加 (subpath ごとの頂点列を返す)。曲線は既存の近似 (制御点を含む) のまま。

### 1-2. 測定 commit と検証
- 測定 commit: `3f76a2119` (transformMatrix を drawArc・drawPoint・drawGraphicsPath に掛ける修正。コードを変えた最後の commit)。main (`0835de52e`) を merge 済み。
- 判定 harness: `canvas/draw_ops_main.cpp` に `drawArc`・`drawPoint`・`drawGraphicsPath` を追加 (`check_draw_ops.sh`、rc=1 かつ nonzero>0 で fail)。`canvas/transform_check_main.cpp` に device 直叩きの変換判定を追加 (`check_transform.sh`)。
- 変換判定 (`transform_ops`): 回転 90 度と平行移動 (40,20) を `setTransformMatrix` で掛け、`drawPoint` (5,5)・`drawArc` (0,0)-(20,20) の半円・`drawGraphicsPath` (0,0)-(10,10) を描く。変換前の位置 (0,0)-(20,20) に出た画素数 (`untransformed_px`) が 0、変換後の位置に点・弧・path の画素が出ることを判定する。
- 判定の効き: 修正前 (`f291f0b09` の canvas_graphicsdevice.cpp に戻して実行) は `untransformed_px=258 point=0 arc_px=0 path_px=0 result=fail` で rc=1。修正後は `untransformed_px=0 point=1 arc_px=168 path_px=100 result=pass`。
- 測定日時: 2026-10-15。素材は `toolchain-emsdk` (`$ARTIFACTS_DIR` にあったものを `work/emsdk` に展開) と `vstgui4_14_3` (depth 1 clone、commit `b1e8235`) を `work/` に置いて測った。`work/` は gitignore。
- 所要・load は同一の run の 2 回目 (依存の取得・初回コンパイルの後) の値。load は `/proc/loadavg` の 1 分値 (開始→終了)。op 単位の所要は計っていない (`check_draw_ops.sh` は 8 op を 1 回の実行で判定するため)。

| 検証 | 結果 | 所要 | load (開始→終了) |
|---|---|---|---|
| `check_draw_ops.sh` | rc=0 (8 op 全 pass) | 31 s | 1.91→2.65 |
| 　drawLine | pass (nonzero=49) | 同上 | 同上 |
| 　drawLines | pass (nonzero=26) | 同上 | 同上 |
| 　drawPolygon | pass (nonzero=607) | 同上 | 同上 |
| 　drawEllipse | pass (nonzero=2472) | 同上 | 同上 |
| 　**drawArc** | **pass (nonzero=1307)** | 同上 | 同上 |
| 　**drawPoint** | **pass (nonzero=1)** | 同上 | 同上 |
| 　**drawGraphicsPath** | **pass (nonzero=876)** | 同上 | 同上 |
| 　drawBitmap | pass (nonzero=64) | 同上 | 同上 |
| `check_render_poc.sh` (既存の判定) | rc=0 (render pass: nonzero_after=12000 text_px=112) | 31 s | 2.65→3.18 |
| `check_canvas_syntax.sh` | rc=0 (8 ファイル errors=0) | 7 s | 3.18→3.01 |
| `check_line_width.sh` | rc=0 (4 判定 pass) | 31 s | 3.01→3.40 |
| `check_transform.sh` (SR-69 判定 + 3 命令の変換判定) | rc=0 (origin_px=300 shifted_px=300 result=pass、transform_ops untransformed_px=0 point=1 arc_px=168 path_px=100 result=pass) | 31 s | 3.40→3.59 |

- 測定条件: vstgui4_14_3 (`work/vstgui4`)、toolchain-emsdk (`work/emsdk`、emcc 6.0.12)。
- 初回の run は vstgui4 の clone・emsdk の展開・初回コンパイルを含むため、所要の比較対象にしない。

### 1-3. コード差分 (測定 commit 以降)
`git diff 3f76a2119 HEAD -- tools/targets/serum2/gui/canvas` は 0 行 (コード差分なし)。
参考: main 取り込み前の測定 commit `c95e740d1` からの canvas 差分は 347 行 (SR-68 #4427 の線の太さ・AA と SR-69 #4428 の transformMatrix)。旧測定値はこの差分を含まないので使わない。

### 1-4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| fillLinearGradient・fillRadialGradient | gradient 付き背景が描かれない | #4233 (SR-62) |
| drawBitmapNinePartTiled・fillRectWithBitmap | 9 分割・タイル描画が no-op のまま | #4233 (SR-62) |
| 曲線 (addBezierCurve・addArc・addEllipse) の正確な形 | path の曲線は制御点を含む近似 | 別件 (本 issue の範囲外・「曲線は既存の近似のまま」) |
| 線の太さ・アンチエイリアス | 線は 1px・非 AA | 別件 (本 issue の範囲外) |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
