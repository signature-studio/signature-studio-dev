> **付録**: `REPORT_EFFORT_APPENDIX_4428.md` (SR-69) → 本付録 (SR-78)。SR-78 (#4551) の `fillRectWithBitmap`・`drawBitmapNinePartTiled` の拡大縮小と bilinear の実装と実測。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4551 / SR-78): canvas の拡大縮小と bilinear の実測

### 1-1. 実装範囲
- 実装 (`canvas_graphicsdevice.cpp`・`.h`): `fillRectWithBitmap` は srcRect を dstRect へ拡大縮小して描く。quality が `kMedium`・`kHigh` なら bilinear (4 近傍の α 加重平均)、それ以外は最近傍。`drawBitmapNinePartTiled` は `calcRects` で得た 9 部分を各々 `fillRectWithBitmap` へ渡す。
- `drawBitmap` は変更しない (1:1 のまま)。理由は 1-5 の未解決を参照。vstgui 14.3 の cairo・D2D 実装も `drawBitmap` は bitmap を自身の大きさで描き、拡大縮小は `CDrawContext::fillRectWithBitmap` (src→dst) だけが担う。
- 判定 harness (`draw_ops_main.cpp`) に 8x8→32x32 の拡大、白黒 2x2 の bilinear / 最近傍、9 分割 (dest 20x20) を追加。判定 (`check_draw_ops.sh`) は画素数の一致で行う (期待: 拡大 1024、9 分割 400)。bilinear は中間階調が 1 以上、最近傍は 0 を要求する。

### 1-2. 測定 commit と検証
- 測定 commit: `201b10a2f` (`feat(serum2): scale and bilinear fillRectWithBitmap, nine-part stretch (#4551)`)。この付録を含む commit は REPORT のみ。
- 前提の素材と取得経路:
  - `work/emsdk` は `$ARTIFACTS_DIR` の `toolchain-emsdk.tar.zst` を `tar --zstd -xf` で展開 (2.4 s)。
  - `work/vstgui4` (vstgui4_14_3・commit `b1e82355`): `https://github.com/steinbergmedia/vstgui.git` を `git clone --filter=blob:none --no-checkout` し、`git checkout vstgui4_14_3`。clone の時間は所要の比較対象にしない。
  - `fl-win64` は本 run の検証では使わない (canvas の検証は vstgui の lib と canvas 層のみ)。

| 検証 (HEAD `201b10a2f`) | 結果 | 所要 (real) | load (uptime 1 分平均・開始→終了) |
|---|---|---|---|
| `check_draw_ops.sh` (rc) | **0** | 15.838 s (user 53.098 s・sys 7.221 s) | 0.76 → 1.94 |
| `check_canvas_syntax.sh` (rc) | **0** (8/8 errors=0) | 3.626 s | 未計測 |

`check_draw_ops.sh` の判定 (HEAD `201b10a2f`):

| op | nonzero | 判定 |
|---|---|---|
| drawLine | 49 | pass |
| drawLines | 26 | pass |
| drawPolygon | 607 | pass |
| drawEllipse | 2472 | pass |
| drawBitmap | 64 | pass (1:1 のまま) |
| fillRectWithBitmap_scale | 1024 (want 1024) | pass |
| fillRectWithBitmap_bilinear (mid-tone) | 512 | pass (bilinear_mid=512) |
| fillRectWithBitmap_nearest (mid-tone) | 0 | pass (nearest_mid=0) |
| drawBitmapNinePartTiled | 400 (want 400) | pass |

- 同じ入力での対比: 最近傍は中間階調 0、bilinear は 512。判定は この差で bilinear の効きを見ている (負の対照の実行はしていない)。
- 実行回数: working tree で 2 回 (commit 前の 15.109 s・14.852 s)、HEAD で 1 回 (15.838 s)。いずれも rc=0。

### 1-3. コード差分 (測定 commit 以降)
- `git diff 201b10a2f HEAD -- tools/targets/serum2/gui/canvas` は 0 行 (コード差分なし)。

### 1-4. 製品 KPI
- 起動・GUI の製品 KPI (FLEngine 起動 dispatch・通過 unit・最初のウィンドウ) は動かしていない。本 PR は canvas の描画 harness の範囲。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| `drawBitmap` の拡大縮小 (受入条件 1) | issue 本文の条件は vstgui 14.3 の参照実装 (cairo・D2D) と食い違う。参照実装は `drawBitmap` を 1:1 で描き、拡大縮小は `fillRectWithBitmap` が担う。1:1 のまま。issue 本文の条件の見直しが要る | PM 判断 (#4551 の受入条件の修正)。子は起票しない |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
