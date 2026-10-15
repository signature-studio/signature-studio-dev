> **付録**: `REPORT_EFFORT_APPENDIX_3260.md` (SR-50) → `REPORT_EFFORT_APPENDIX_3422.md` (SR-55) の続き。SR-69 (#4428) の `setTransformMatrix` の実装と実測。測定値の正本はこの付録。

## 1. 2026-10-15 run (#4428 / SR-69): canvas の setTransformMatrix と原点以外の view の実測

### 1-1. 実装範囲
- 実装 (`canvas_graphicsdevice.cpp`・`.h`): `setTransformMatrix` は絶対行列を保持する。点・線・多角形・楕円・矩形・`clearRect`・bitmap の dest 位置・文字の基準点 (`canvas_font.cpp`) に適用する。
- clipRect は変換しない。VSTGUI の `CDrawContext::setClipRect` が device へ渡す前に `getCurrentTransform` で変換済みのため。
- 制限: 回転・傾斜は矩形を外接矩形で近似する。拡大縮小は bitmap の転写・文字に掛けない (`drawBitmap` は 1:1 のまま)。
- 未実装 (範囲外): 線の太さ・アンチエイリアス (子 #4427 `[SR-68]`)。描画命令の no-op 解消 (`[SR-55]`・#3422 の子)。

### 1-2. 測定 commit と検証
- 測定 commit: `5e667deeb` (コードを変えた最後の commit)。
- 判定 harness: `canvas/transform_check_main.cpp` (新規・検証専用)、判定スクリプト `canvas/check_transform.sh` (新規)。同じ親に原点のコンテナ `(0,0)` と `(40,20)` のコンテナを置き、それぞれの中の `(0,0)-(30,10)` の子 view に固定色 (赤) の矩形を描いて、領域ごとの赤画素を数える。期待は両方 300。

| 検証 (HEAD `5e667deeb`) | 結果 | 所要 (real) | load (開始→終了) |
|---|---|---|---|
| `check_transform.sh` (rc) | **0** (`origin_px=300 shifted_px=300 expected=300 result=pass`) | 14.788 s | 0.64 → 1.45 |
| `check_render_poc.sh` (rc・既存の判定) | **0** (render pass: `nonzero_after=12000 text_px=112 text_width=54`) | 13.342 s | 0.33 → 0.90 |
| `check_canvas_syntax.sh` (rc) | **0** (8/8 errors=0) | — | — |
| `check_wasm_syntax.sh` (rc) | **0** (seed 6 errors=0) | — | — |

- 所要の内訳 (`check_transform.sh` の summary): compile 14407 ms (`xargs -P 4`・nproc 4)・link 214 ms・run 35 ms。
- 負の対照 (作業中の commit で取得。HEAD では再実行していない): `setTransformMatrix` を no-op (`(void)tm;`) にすると `origin_px=300 shifted_px=0 result=fail` (rc=1)。戻すと `shifted_px=300 result=pass`。変換が効いていることの根拠。
- 前提: `work/vstgui4` (vstgui4_14_3・`b1e8235`)、`work/emsdk/upstream/emscripten` (toolchain-emsdk)。`work/` は gitignore。初回の展開と clone は所要の比較対象にしない。

### 1-3. コード差分 (測定 commit 以降)
`git diff 5e667deeb HEAD -- tools/targets/serum2/gui/canvas` の出力は、この付録 commit までで 0 行 (コード差分なし)。

### 1-4. no-op の計数について
`count_canvas_noop.py` の HEAD の結果は `draw: functions=14 noop=7 impl=7`・`state: functions=14 noop=6 impl=8`。#3422 の 1-4 で書いたとおり、本体に入れ子の波括弧があると関数を読み飛ばすため、REPORT_EFFORT_APPENDIX_3260 §17-5 の値 (draw 15/12・state 14/7) とは直接比べられない。描画が通ったことの根拠は 1-2 の判定 harness。

### 1-5. 未解決
| 未解決 | 影響 | 起票先 |
|---|---|---|
| 回転・傾斜の描画 (矩形を外接矩形で近似) | 回転した view の枠・塗りが実際より大きく出る | 未解決の追跡のみ (子は起票しない・受入の範囲外) |
| 拡大縮小 (`drawBitmap` の dest 幅・高さ・bitmap の scale) | 拡大縮小された view の画像は 1:1 のまま | `[SR-55]` #3422 系の残り (bilinear・拡大縮小) |
| 線の太さ・アンチエイリアス | 太い線・角の見え方が実機と異なる | 子 #4427 `[SR-68]` |
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 別件 (本 issue の範囲外) |
