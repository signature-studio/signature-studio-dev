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
| `count_canvas_noop.py` の入れ子の波括弧 | 計数が不正確 | 未起票 (`count_canvas_noop` を含む issue は 0 件。起票要否は PM 判断) |

### 1-6. 再測定 (HEAD `021b79922`・SR-62 の merge 後)
- 測定 commit: `021b79922` (SR-62 #4233 を main 取り込みで含む merge。canvas のコードを変えた最後の commit)。`git diff 021b79922 HEAD -- tools/targets/serum2/gui/canvas` の出力は 0 行。
- 結果: `check_transform.sh` rc=0 (compile 71/71 fail=0・link rc=0・run rc=0・`origin_px=300 shifted_px=300 expected=300 result=pass`)。所要 31.7 s、load 3.43 → 3.78 (直列実行・開始前に load 1 分平均 1.15 まで待ってから他の 4 本と順に実行)。
- 素材: toolchain-emsdk は `$ARTIFACTS_DIR/toolchain-emsdk.tar.zst` を展開 (上流 emsdk の取得はしていない)。

## 2. 2026-10-17 run (#3424 / SR-56 受入 4): HEAD で再測定した実測値
- 測定 commit: `ff41e8aae` (origin/main・Merge #6051)。3 本の判定 harness の対象は canvas/ を含むこの HEAD のコード。
- コード差分 (測定 commit から HEAD まで): `git diff ff41e8aae HEAD -- tools/targets/serum2/gui/canvas` は 0 行 (この付録 §2 を含む commit は REPORT のみ)。
- 比較用の旧測定: §1-6 (測定 commit `021b79922`)。`021b79922` から `ff41e8aae` までの canvas 差分は 10 files・994 行追加・122 行削除 (#3424 の受入 4 が指す差分。今回は HEAD で取り直した値を正とする)。
- 素材: `toolchain-emsdk.tar.zst` を `tools/targets/serum2/gui/work/emsdk` に展開 (3.6 s)。vstgui4 は `steinbergmedia/vstgui` を `vstgui4_14_3` (`b1e82355`) に checkout。`work/` は gitignore。
- 実行環境: runner (nproc 4)。3 本は直列実行。load は `/proc/loadavg` の 1 分平均 (開始時 → 終了時)。所要は `date` の差 (real)。

| スクリプト (HEAD `ff41e8aae`) | rc | 所要 (real) | load (1 分平均・開始→終了) | 判定の内訳 |
|---|---|---|---|---|
| `check_render_poc.sh` | **0** | 33.229 s | 1.34 → 2.44 | compile 71/71 ok (32195 ms)・link rc=0 (691 ms)・run rc=0 (157 ms)。render pass: `nonzero_after=12000 text_px=112 text_width=54` |
| `check_transform.sh` | **0** | 31.172 s | 2.25 → 2.99 | compile 71/71 fail=0 (30462 ms)・link rc=0 (501 ms)・run rc=0 (62 ms)。`origin_px=300 shifted_px=300 expected=300 result=pass`。`transform_ops untransformed_px=0 point=1 arc_px=168 path_px=100 result=pass` |
| `check_line_width.sh` | **0** | 31.612 s | 2.99 → 3.20 | link rc=0・run rc=0。全 19 ケース rc=1 かつ nonzero>0。12 check すべて pass (例: `w1_alias nonzero=55`・`w4_alias nonzero=250`・`w4_aa nonzero=321 partial=140`・`w8_join_miter nonzero=1184`・`w4_dash nonzero=154`) |

- 3 本とも rc=0。受入 4 の「測定 commit・rc・所要秒・load average・画素数」を満たす。
- 旧測定 (§1-6・`021b79922`) の `check_transform.sh` は `origin_px=300 shifted_px=300` で、HEAD でも同じ値。
