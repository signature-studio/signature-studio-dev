> **付録**: `REPORT_EFFORT_APPENDIX_4428.md` (SR-69) → 本付録 (SR-78)。SR-78 (#4551) の `fillRectWithBitmap`・`drawBitmapNinePartTiled` の拡大縮小と bilinear の実装と実測。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4551 / SR-78): canvas の拡大縮小と bilinear の実測

### 1-1. 実装範囲
- 実装 (`canvas_graphicsdevice.cpp`・`.h`): `fillRectWithBitmap` は srcRect を dstRect へ拡大縮小して描く。quality が `kMedium`・`kHigh` なら bilinear (4 近傍の α 加重平均)、それ以外は最近傍。`drawBitmapNinePartTiled` は `calcRects` で得た 9 部分を各々 `fillRectWithBitmap` へ渡す。
- `drawBitmap` は変更しない (1:1 のまま)。理由は 1-5 の未解決を参照。vstgui 14.3 の cairo・D2D 実装も `drawBitmap` は bitmap を自身の大きさで描き、拡大縮小は `CDrawContext::fillRectWithBitmap` (src→dst) だけが担う。
- 判定 harness (`draw_ops_main.cpp`) に 8x8→32x32 の拡大、白黒 2x2 の bilinear / 最近傍、9 分割 (dest 20x20) を追加。判定 (`check_draw_ops.sh`) は画素数の一致で行う (期待: 拡大 1024、9 分割 400)。bilinear は中間階調が 1 以上、最近傍は 0 を要求する。

### 1-2. 測定 commit と検証
- 測定 commit: `a91be2092` (`merge: origin/main into 4551-canvas-bitmap-scale (resolve canvas conflicts with #4231 and #4233) (#4551)`)。main (`70f4ffaa7`) の取り込みで `canvas_graphicsdevice.h` と `check_draw_ops.sh` の競合を解消した commit。判定の期待件数を 12 → 15 に直したのもこの commit。前回の `52d2a6d29` は main 取り込み前の測定のため、現 head の根拠にしない (round 2 blocking 1)。この付録を含む commit は REPORT のみ。
- 前提の素材と取得経路:
  - `toolchain-emsdk` 素材は `$ARTIFACTS_DIR` に無かった (`fl-win64` のみ)。runner 上の既存の emsdk も無い。そこで上流 emsdk を `git clone --depth 1` → `./emsdk install 6.0.12` → `./emsdk activate 6.0.12` で `work/emsdk` に導入した (emcc 6.0.12)。install 所要は clone 込みで計測対象外。
  - 導入後、`work/emsdk/upstream/emscripten/.emscripten` が無く em++ が `BINARYEN_ROOT` 不明で失敗したため、`EM_CONFIG` を emsdk ルートの `.emscripten` に、`PATH` に `upstream/bin` を与えて実行した (`check_draw_ops.sh` の PATH 設定だけでは足りない)。
  - `work/vstgui4` (vstgui4_14_3・commit `b1e82355`): `https://github.com/steinbergmedia/vstgui.git` を `git clone --filter=blob:none --no-checkout` し、`git checkout vstgui4_14_3`。
  - `fl-win64` は本 run の検証では使わない (canvas の検証は vstgui の lib と canvas 層のみ)。

| 検証 (HEAD `a91be2092`) | 結果 | 所要 (real) | load (uptime 1 分平均・開始→終了) |
|---|---|---|---|
| `check_draw_ops.sh` (rc) | **0** (link rc=0・compile fail=0・run rc=0・draw_op 15 件) | 28 s | 1.41 → 2.19 |
| `check_canvas_syntax.sh` (rc) | **0** (全 8 ファイル errors=0) | 6 s | 2.19 → 2.10 |

- 前提の emsdk は上流 6.0.12 を `work/emsdk` (`tools/targets/serum2/gui/work/`、gitignore) に導入し、`EM_CONFIG=work/emsdk/.emscripten`・`PATH` に `upstream/bin` を与えて実行した (`emsdk install 6.0.12` → `emsdk activate 6.0.12`。install は計測対象外)。`fl-win64` は使わない。
- `work/vstgui4` は `b1e82355` (vstgui4_14_3)。

`check_draw_ops.sh` の判定 (HEAD `a91be2092`):

| op | nonzero | 判定 |
|---|---|---|
| drawLine | 49 | pass |
| drawLines | 26 | pass |
| drawPolygon | 607 | pass |
| drawEllipse | 2472 | pass |
| drawArc | 1307 | pass (#4231) |
| drawPoint | 1 | pass (#4231) |
| drawGraphicsPath | 876 | pass (#4231) |
| drawBitmap | 64 | pass (1:1 のまま) |
| fillLinearGradient | 3136 (distinct 57) | pass (#4233) |
| fillRadialGradient | 3136 (distinct 173) | pass (#4233) |
| drawBitmapNinePartTiled | 3136 | pass (1:1 タイル, #4233) |
| fillRectWithBitmap | 900 | pass (1:1 タイル, #4233) |
| fillRectWithBitmap_scale | 1024 (want 1024) | pass (#4551) |
| fillRectWithBitmap_bilinear (mid-tone) | 512 | pass (bilinear_mid=512) |
| fillRectWithBitmap_nearest (mid-tone) | 0 | pass (nearest_mid=0) |
| drawBitmapNinePartTiled_scale | 400 (want 400) | pass (#4551) |

注: `fillRectWithBitmap` (1:1 タイル, #4233 の harness) と `fillRectWithBitmap_scale` (#4551) は同じ `fillRectWithBitmap` 経路を別入力で測っている。#4233 の 1:1 方針は #4551 で拡大縮小へ置き換わった (PM 判断待ち、§1-6)。

- `run.log` の `rc=` は実測値になった (`fillRectWithBitmap_bilinear rc=1`・`fillRectWithBitmap_scale rc=1` 等。前回の固定 `rc=1` を外した)。
- 同じ入力での対比: 最近傍は中間階調 0、bilinear は 512。判定はこの差で bilinear の効きを見ている (負の対照の実行はしていない)。
- 参考 (前回 `201b10a2f` の数値 15.838 s は、解放済みポインタの上で出た値のため採らない)。

### 1-3. コード差分 (測定 commit 以降)
- 測定 commit `a91be2092` 以降のコード差分 (`git diff a91be2092 HEAD -- tools/targets/serum2/gui/canvas`) は 0 行 (この付録の commit は REPORT のみ)。
- main の取り込み: `1bf34deea` (main `325cf6a4d`・SR-62 競合の解消) の後、main が `70f4ffaa7` まで進んだため、`a91be2092` で再度取り込んだ。競合は `canvas_graphicsdevice.h` の注釈と `check_draw_ops.sh` の期待件数 (drawArc・drawPoint・drawGraphicsPath の #4231 を含めて 15 件)。`canvas_graphicsdevice.cpp`・`draw_ops_main.cpp` は自動マージ。
- 前回測定 (`52d2a6d29`) からの差分: `1bf34deea` 以前の main 取り込みで canvas 層の差分が増えたため、現 head の根拠は `a91be2092` の測定のみ。

### 1-6. #4233 の 1:1 タイル方針との関係 (PM 判断待ち)
- `fillRectWithBitmap`・`drawBitmapNinePartTiled` は #4233 (SR-62) で 1:1 タイルだった。#4551 (SR-78) は srcRect → dstRect の拡大縮小 (quality に応じて bilinear・最近傍) へ置き換えた。#4551 の受入条件に沿う変更で、#4233 の受入 (1:1 タイル) の挙動は変わる。
- PM agent の判断待ち: #4233 の 1:1 タイル方針を #4551 の拡大縮小で置き換えてよいか。既定案: 拡大縮小 (#4551 の受入)。

### 1-4. 製品 KPI
- 起動・GUI の製品 KPI (FLEngine 起動 dispatch・通過 unit・最初のウィンドウ) は動かしていない。本 PR は canvas の描画 harness の範囲。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `drawBitmap` の拡大縮小 (受入条件 1) | issue 本文の条件は vstgui 14.3 の参照実装と食い違う。参照実装は `drawBitmap` を 1:1 で描き、拡大縮小は `fillRectWithBitmap` が担う。1:1 のまま。issue 本文の条件の見直しが要る | 子 issue #4657 (`[SR-80]`・`親: #4551`・「drawBitmap の参照実装と受入条件の食い違いの確認」) と PM 判断 |

- 参照実装の該当箇所 (vstgui4_14_3・commit `b1e82355`、`work/vstgui4/vstgui/lib/` 配下):
  - `platform/linux/cairographicscontext.cpp:497-520` (`CairoGraphicsDeviceContext::drawBitmap`): パターンの行列は `cairo_matrix_init_scale` に `getScaleFactor()` だけを使い、`dest` の大きさは clip 矩形にしか使わない。拡大率は 1:1 (dest のサイズを拡大率に使わない)。
  - `platform/win32/direct2d/d2dgraphicscontext.cpp:650-674` (`D2DGraphicsDeviceContext::drawBitmap`): 変換は `bitmapTransform.scale (1. / bitmapScaleFactor, ...)` だけで、dest の大きさは描画先の clip 範囲にしか使わない。
  - `cdrawcontext.cpp:408-414` (`CDrawContext::fillRectWithBitmap`): src→dst の拡大縮小は `fillRectWithBitmap` 側の経路で扱う。
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
