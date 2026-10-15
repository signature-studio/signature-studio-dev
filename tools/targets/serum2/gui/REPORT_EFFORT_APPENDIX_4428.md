> **付録**: `REPORT_EFFORT_APPENDIX_3260.md` (SR-50) → `REPORT_EFFORT_APPENDIX_3422.md` (SR-55) の続き。SR-69 (#4428) の `setTransformMatrix` の実装と実測。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4428 / SR-69): canvas の setTransformMatrix と原点以外の view の実測

### 1-1. 実装範囲
- 実装 (`canvas_graphicsdevice.cpp`・`.h`): `setTransformMatrix` は絶対行列を保持する。点・線・多角形・楕円・矩形・`clearRect`・bitmap の dest 位置・文字の基準点 (`canvas_font.cpp`) に適用する。
- clipRect は変換しない。VSTGUI の `CDrawContext::setClipRect` が device へ渡す前に `getCurrentTransform` で変換済みのため。
- 制限: 回転・傾斜は矩形を外接矩形で近似する。拡大縮小は bitmap の転写・文字に掛けない (`drawBitmap` は 1:1 のまま)。
- 線の太さ・アンチエイリアス (SR-68 / #4427, closed) は main の `9d4a6d5c0` の実装が、`2001e0920` の main 取り込み merge で本 PR に入っている。本 issue の受入は transform のみで、線の実測は SR-68 側 (`check_line_width.sh`) の範囲。

### 1-2. 測定 commit と検証
- 測定 commit: `2001e0920` (main 取り込み merge。コードを含む最後の commit)。この付録を含む commit は REPORT のみ。
- 判定 harness: `canvas/transform_check_main.cpp` (新規・検証専用)、判定スクリプト `canvas/check_transform.sh` (新規)。同じ親に原点のコンテナ `(0,0)` と `(40,20)` のコンテナを置き、それぞれの中の `(0,0)-(30,10)` の子 view に固定色 (赤) の矩形を描いて、領域ごとの赤画素を数える。期待は両方 300。
- 前提の素材と取得経路:
  - `work/vstgui4` (vstgui4_14_3・commit `b1e82355`): `https://github.com/steinbergmedia/vstgui.git` を `git clone --filter=blob:none --no-checkout` し、`git checkout vstgui4_14_3`。
  - `work/emsdk/upstream/emscripten` (Emscripten 6.0.12): `https://github.com/emscripten-core/emsdk.git` を clone し、`./emsdk install 6.0.12` → `./emsdk activate 6.0.12` → `source ./emsdk_env.sh` (`$ARTIFACTS_DIR` の `toolchain-emsdk` は本 run に無かったため、上流から取得)。
  - `work/render_poc/upstream_cpp.txt`: `check_render_poc.sh` を先に 1 回実行して作る。
  - `work/` は gitignore。clone と install の時間は所要の比較対象にしない。

| 検証 (HEAD `2001e0920`) | 結果 | 所要 (real) | load (uptime 1 分平均・開始→終了) |
|---|---|---|---|
| `check_render_poc.sh` (rc・既存の判定) | **0** (render pass: `nonzero_after=12000 text_px=112 text_width=54`) | 14.710 s | 未計測 |
| `check_transform.sh` (rc) | **0** (`origin_px=300 shifted_px=300 expected=300 result=pass`) | 14.661 s | 0.95 → 1.69 |
| `check_canvas_syntax.sh` (rc) | **0** (8/8 errors=0) | 3.180 s | 未計測 |
| `check_wasm_syntax.sh` (rc) | **0** (seed 6 errors=0) | 0.431 s | 未計測 |

- 所要の内訳 (`check_transform.sh` の summary): compile 14121 ms (`xargs -P 4`・nproc 4)・link 385 ms・run 38 ms。
- 負の対照 (HEAD `2001e0920` の作業ツリーで `setTransformMatrix` の本体を `(void)tm;` (no-op) にして `check_transform.sh` を実行 → 戻して clean を確認): `origin_px=300 shifted_px=0 expected=300 result=fail` (rc=1)。元の本体に戻すと `shifted_px=300 result=pass` (rc=0)。変換が効いていることの根拠。

### 1-3. コード差分 (測定 commit 以降)
- `git diff 2001e0920 HEAD -- tools/targets/serum2/gui/canvas` は、この付録を含む commit までで 0 行 (コード差分なし)。
- 参考: 旧測定 commit `5e667deeb` から `2001e0920` までの canvas 差分は 4 ファイル・183 行追加 (main の SR-68 `9d4a6d5c0`・`e94ac2f53` 由来: `canvas_graphicsdevice.{h,cpp}` の `plotLine` 分岐・`plotThickLine`・`drawMode`、新規 `check_line_width.sh`・`line_width_main.cpp`)。これは実行される検証コードの差分のため、上の表は `2001e0920` で取り直した値。

### 1-4. no-op の計数について
`count_canvas_noop.py` の HEAD の結果は `draw: functions=14 noop=7 impl=7`・`state: functions=14 noop=6 impl=8`。#3422 の 1-4 で書いたとおり、本体に入れ子の波括弧があると関数を読み飛ばすため、REPORT_EFFORT_APPENDIX_3260 §17-5 の値 (draw 15/12・state 14/7) とは直接比べられない。描画が通ったことの根拠は 1-2 の判定 harness。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 回転・傾斜の描画 (矩形を外接矩形で近似) | 回転した view の枠・塗りが実際より大きく出る | 未解決の追跡のみ (子は起票しない・受入の範囲外) |
| 拡大縮小 (`drawBitmap` の dest 幅・高さ・bitmap の scale) | 拡大縮小された view の画像は 1:1 のまま | `[SR-55]` #3422 系の残り (bilinear・拡大縮小) |
| 線の太さ・アンチエイリアス | 解消済み (main `9d4a6d5c0` を取り込み済み・#4427 は closed) | なし |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
