> **付録**: `REPORT_EFFORT.md` §16 (#2065 / SR-36) → `REPORT_EFFORT_APPENDIX_3422.md` (SR-55) の続き。SR-61 (#4231) の path・円弧・点の描画と測定。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4231 / SR-61): canvas の円弧・点・path 描画

### 1-1. 実装範囲
- 前提の #3422 (SR-55) は main 取り込み済み。`drawLine`・`drawLines`・`drawPolygon`・`drawEllipse`・`drawBitmap` は main にある。
- 実装 (`canvas/canvas_graphicsdevice.cpp`):
  - `drawArc`: 角度はラジアン (Cairo の `cairo_arc` と同じ単位)。弧を多角形に近似し、塗りは弧と弦で囲んだ領域、線は弧だけ。
  - `drawPoint`: 1 画素を、四捨五入した位置に `blendPixel` で置く。`true` を返すので、`CDrawContext::drawPoint` の drawRect フォールバック (2×2 px) は通らなくなる。
  - `drawGraphicsPath`: path の全 subpath を使う。`Filled` は非零巻き数則、`FilledEvenOdd` は偶奇則で塗る。`Stroked` は各 subpath を閉じずに線で描く。`transformation` は頂点に掛ける。
- 補助: `fillPolygon` を `fillRings` (複数輪郭・非零/偶奇の切替) に広げた。`drawPolygon`・`drawEllipse` の塗りは偶奇則のまま (画素数は 3422 の値と一致)。
- `canvas_graphicspath.{h,cpp}`: `subpaths ()` を追加 (subpath ごとの頂点列を返す)。曲線は既存の近似 (制御点を含む) のまま。

### 1-2. 測定 commit と検証
- 測定 commit: `c95e740d1` (コードを変えた最後の commit。main 取り込み後の SR-68 (#4427) の `plotLine`・`plotThickLine` を含む)。
- 判定 harness: `canvas/draw_ops_main.cpp` に `drawArc`・`drawPoint`・`drawGraphicsPath` を追加。判定は `check_draw_ops.sh` (rc=1 かつ nonzero>0)。
- 測定日時: 2026-10-15。素材は `toolchain-emsdk` (emsdk 上流から取得、pin 6.0.12) と `vstgui4_14_3` を `work/` に用意して測った。`work/` は gitignore。
- 所要・load は 2 回目の測定 (依存の取得を含まない) の値。load は `/proc/loadavg` の 1 分値 (開始→終了)。

| 検証 | 結果 | 所要 | load (開始→終了) |
|---|---|---|---|
| `check_draw_ops.sh` | rc=0 (8 op 全 pass) | 21 s | 1.66→2.32 |
| 　drawLine | pass (nonzero=49) | | |
| 　drawLines | pass (nonzero=26) | | |
| 　drawPolygon | pass (nonzero=607) | | |
| 　drawEllipse | pass (nonzero=2472) | | |
| 　**drawArc** | **pass (nonzero=1307)** | | |
| 　**drawPoint** | **pass (nonzero=1)** | | |
| 　**drawGraphicsPath** | **pass (nonzero=876)** | | |
| 　drawBitmap | pass (nonzero=64) | | |
| `check_render_poc.sh` (既存の判定) | rc=0 (render pass: nonzero_after=12000 text_px=112) | 22 s | 2.32→2.80 |
| `check_canvas_syntax.sh` | rc=0 (8 ファイル errors=0) | 5 s | 2.80→2.66 |
| `check_line_width.sh` | rc=0 (4 判定 pass) | 22 s | 2.66→3.03 |

- 測定条件: vstgui4_14_3 (`work/vstgui4`)、toolchain-emsdk (`work/emsdk`、emcc 6.0.12)。
- 初回の run は vstgui4 の clone と emsdk の取得を含むため、所要の比較対象にしない。

### 1-3. コード差分 (測定 commit 以降)
`git diff c95e740d1 HEAD -- tools/targets/serum2/gui/canvas` は 0 行 (コード差分なし)。
参考: 前の測定 commit `1d2a5c9ab` からの差分は main 取り込みで 183 行 (`canvas_graphicsdevice.cpp`・`.h`・`check_line_width.sh`・`line_width_main.cpp`)。この差分の中身は SR-68 (#4427)。

### 1-4. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| fillLinearGradient・fillRadialGradient | gradient 付き背景が描かれない | #4233 (SR-62) |
| drawBitmapNinePartTiled・fillRectWithBitmap | 9 分割・タイル描画が no-op のまま | #4233 (SR-62) |
| 曲線 (addBezierCurve・addArc・addEllipse) の正確な形 | path の曲線は制御点を含む近似 | 別件 (本 issue の範囲外・「曲線は既存の近似のまま」) |
| 線の太さ・アンチエイリアス | 線は 1px・非 AA | 別件 (本 issue の範囲外) |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
