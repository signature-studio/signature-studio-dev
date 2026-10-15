> **付録**: `REPORT_EFFORT.md` §16 (#2065 / SR-36) の続き。SR-50 (#3260) の実装と再測定の本文。測定値の正本はこの付録。

## 17. 2026-10-15 run (#3260 / SR-50): canvas の文字列・矩形描画・drawString と bitmap 結線

### 17-1. 結論

- 受入条件 5 件を満たす (17-2)。`check_render_poc.sh` の render 判定は pass (`nonzero_after=12000`・`text_width=54`・`text_px=112`)。
- 文字は同梱の手書き 5x7 placeholder フォントで描く。フォントサイズは無視する (17-7)。
- 測定 commit: `560357317` (コードを変えた最後の commit。本節を含む REPORT の commit は後続で、コードは変えない)。

### 17-2. 受入条件の達成

| # | 受入条件 | 結果 | 根拠 |
|---|---|---|---|
| 1 | `IPlatformString` を wasm 向けに実装し、`createString` が nullptr を返さない | 達成 | `canvas/canvas_string.{h,cpp}`。`createString` は常に `CanvasString` を返す (nullptr なら text_width=-1 になる) |
| 2 | CTextLabel の描画に要る描画命令 (`drawString` を含む) を実装し、bitmap へ画素を書く | 達成 | `drawRect`・`clearRect`・`drawString` を実装。文字色の画素 `text_px=112` |
| 3 | `createBitmapContext(bitmap)` が渡された bitmap に結線される | 達成 | harness は `device->createBitmapContext(bitmap)` 経由で描画する (直接 new しない) |
| 4 | `check_render_poc.sh` で `nonzero_after>0` かつ `text_width>=0` | 達成 (+ `text_px>0` を追加判定) | `render: pass`。追加条件の理由は 17-8 |
| 5 | 測定 commit・rc・所要秒・load・画素数を実測で残す | 達成 | 17-3 |

### 17-3. 測定 (測定 commit `560357317`、HEAD で再実行)

| 項目 | 値 |
|---|---|
| `bash canvas/check_render_poc.sh` の rc | 0 |
| 所要 (`time` の real) | 20.674 s (summary の compile secs=20164ms・link secs=289ms・run secs=48ms) |
| load (`uptime` の 1 分平均) | 開始 1.09 → 終了 2.22 |
| compile | 70/70 ok (upstream 62/62・canvas と harness 8)、`error:` 行 0 |
| link | rc=0・未解決シンボル 0・`render_poc.wasm` 10,673,200 B・`render_poc.js` 62,001 B |
| run (node) | rc=0 |
| 画素数 `bytes` | 48000 (200×60×4) |
| `nonzero_before` | 0 |
| `control` (陽性対照) | 1 |
| `nonzero_after` | 12000 (内訳: 黒背景 `000000ff` 11888 px + 文字色 `ffffffff` 112 px) |
| `text_px` (文字色の画素) | 112 |
| `text_width` | 54 (= 6 px × 9 字) |
| `bash canvas/check_canvas_syntax.sh` | rc=0 (7/7 で errors=0)・所要 4.186 s (load 2.05 → 1.96) |
| `bash check_wasm_syntax.sh` | rc=0 (seed 6 errors=0)・所要 0.634 s |
| `canvas/check_concrete.cpp` (`em++ -fsyntax-only`) | rc=0 |

- 注記: load は同時に走る他の処理の影響を受ける。commit 前の検証 (render・syntax) も同じ結果 (`nonzero_after=12000`・`text_px=112`・rc=0)。

### 17-4. 字形の確認 (ASCII art)

`drawString("Signature", CPoint(2, 11))` を 100×12 の bitmap に描き、`#` = alpha>0、`.` = 透明で出力した。列 0〜59 のみ表示 (文字は x=2 から 6 px 刻み)。文字の上端は p.y−7 = 行 4、下端は行 10。

```
...####...#......................#..........................
..#............####..............#..........................
..#......##...#...#.#.##...###..###...#...#.#.##...###......
...###....#...#...#.##..#.....#..#....#...#.##..#.#...#.....
......#...#....####.#...#..####..#....#...#.#.....#####.....
......#...#.......#.#...#.#...#..#..#.#..##.#.....#.........
..####...###...###..#...#..####...##...##.#.#......###......
```

（表示は行 4〜10 の 7 行で、各行の先頭 60 列。S・i・g・n・a・t・u・r・e と読める。）

- 確認用の main は `work/ascii_check/` (gitignore、repo に残さない)。canvas の object を同じ build から link し、`CTextLabel` 経路の色ヒストグラムも同時に出した。

### 17-5. no-op 計数の変化 (`canvas/count_canvas_noop.py`)

| 区分 | ベースライン cf2966030 | 本 PR (`560357317`) |
|---|---|---|
| 描画命令 (`draw*`・`clearRect`・`fill*`・`drawString`) | 15 (no-op 15・実装 0) | 15 (no-op **12**・実装 **3**: `drawRect`・`clearRect`・`drawString`) |
| 状態設定 (`set*`・`save*`・`restore*`) | 13 (no-op 7・実装 6) | 14 (no-op 7・実装 7: `setUTF8String` 追加) |

- 変化の内訳: 描画 3 件を実装 (15→12)。状態は `canvas_string.cpp` を計数対象 `FILES` に加えたため `setUTF8String` が 1 件増えた (実装)。
- ベースラインは cf2966030 の canvas を一時展開し、現行の計数スクリプトで再計数した (draw 15/15・state 13 (7/6))。値は 16-5 と一致する。
- no-op 12 件 (draw): `drawLine`・`drawLines`・`drawPolygon`・`drawArc`・`drawEllipse`・`drawPoint`・`drawBitmap`・`drawGraphicsPath`・`fillLinearGradient`・`fillRadialGradient`・`drawBitmapNinePartTiled`・`fillRectWithBitmap`。
- `drawPoint` は device が false を返すため `CDrawContext::drawPoint` が `drawRect` へフォールバックする。よって点は `drawRect` 経由で描かれる (丸めにより 2×2 px)。

### 17-6. 実装の要点

- `IPlatformString`: UTF-8 を `std::string` に保持する。純粋仮想は `setUTF8String` の 1 件だけ (`platform/iplatformstring.h`)。ワイド文字列は扱わない。`canvasDecodeUTF8` で UTF-8 をコードポイントへ分解する。
- bitmap 結線: `createBitmapContext(bitmap)` が `CanvasGraphicsDeviceContext(device, bitmap)` を作る。bitmap は `PlatformBitmapPtr` で保持し、`CanvasBitmap` でなければ描画しない。clip の既定は bitmap 全体 `(0,0,w,h)`。`setClipRect` は bitmap 境界との交差を保持する。
- `drawRect`: `Filled` は `fillColor` で塗り、`Stroked` は `frameColor` の 1 px 枠を矩形の内側に描く。`FilledAndStroked` は両方。
- `clearRect`: clip 内の画素を `(0,0,0,0)` で書く。
- 合成: 非 premultiplied RGBA の source-over。`globalAlpha` を乗じる。clip と bitmap 境界の外は書かない。
- 字形: `canvas/canvas_glyph5x7.h` (ASCII 0x20〜0x7E の 95 字、5 列×7 行、bit 4 が左端)。出所は本リポジトリで手書きした placeholder で、外部フォントからの流用はしない。非 ASCII と制御文字は `?` の字形にする。
- 文字の配置: 1 字 6 px (字形 5 px + 間隔 1 px)。`p.x` が左端、上端は `p.y − 7`。中央寄せなどの配置は `CDrawContext::drawString` (upstream) の計算に従う。

### 17-7. 未解決・限界

| 未解決 | 影響 | 起票先 |
|---|---|---|
| フォントサイズを無視する (`size` は保持のみ)。比例幅・ディセンダの余白なし | 文字の大きさ・字間は実フォントと一致しない | 未起票 (実フォント資源の扱いを決める issue が要る) |
| `drawLine`・`drawLines`・`drawPolygon`・`drawArc`・`drawEllipse`・`drawBitmap`・`drawGraphicsPath`・gradient 2 件・9 分割・`fillRectWithBitmap` は no-op | CTextLabel の枠は `drawGraphicsPath` 経路なので描かれない。黒背景は `drawRect` で描かれる | 未起票 (canvas 描画の後続 issue) |
| 線は lineWidth に依らず 1 px。アンチエイリアスなし | 太い線・角の見え方が実機と異なる | 未起票 |
| `setTransformMatrix` は no-op (平行移動・拡大縮小は未適用) | 原点 (0,0) 以外の view では描画位置がずれる。harness は原点のみで検証 | 未起票 |
| placeholder の 5x7 フォント | 確認用の見た目のみ。製品の字形としては使わない | 未起票 |
| wasm の初期化経路 (`getPlatformFactory` の代替と `CFontDesc::init()` の直呼び) | harness の回避が残る | #3261 (SR-51) |
| XferOnOffButton の canvas 実装 | 範囲外 | #3262 (SR-52) |

### 17-8. render 判定の条件 (追加判定 `text_px>0`)

- 受入の 2 条件 (`nonzero_after>0`・`text_width>=0`) だけでは、文字が無くても pass する。`CTextLabel` の既定は黒背景で、実装済みの描画命令のうち不透明な黒を書けるのは `drawRect` だけなので、`nonzero_after=12000` の 11888 px は背景である。
- そのため `check_render_poc.sh` は `text_px>0` (文字色の画素) を追加で要求する。文字が描かれた証拠を別に残すため。
- `control` と `before` の計数は変えていない。`text_px` は harness の出力行の末尾に足した。

### 17-9. 測定 commit と差分

- 測定 commit: `995f9fb32` (main 取り込みの merge commit。コードを変えた最後の commit)。main 取り込み前の測定 commit は `560357317` (§17-3 の値)。
- 差分 (コード・ベースラインからの規模): `git diff --stat cf2966030 560357317 -- tools/targets/serum2/gui/canvas` → 14 files・460 insertions・42 deletions (PR 本体の規模。main 取り込みの差分は含まない)。
- 差分 (測定 commit から HEAD まで): `git diff 995f9fb32 HEAD -- tools/targets/serum2/gui/canvas tools/targets/serum2/gui/*.py` の出力は **0 行** (本節の commit は REPORT とドキュメントだけ)。
- 再現: `cd tools/targets/serum2/gui && bash canvas/check_render_poc.sh && bash canvas/check_canvas_syntax.sh && bash check_wasm_syntax.sh && python3 canvas/count_canvas_noop.py`。前提は `work/vstgui4` (vstgui4_14_3 の clone) と `work/emsdk/upstream/emscripten` (`toolchain-emsdk` を `work/` に展開)。

### 17-10. main 取り込み後の再測定 (`995f9fb32`)

- 経緯: main (`e7cff966b`) が #3261 (SR-51) を取り込み、本 PR と競合した。解消は 3 件 (`docs/DOC_MAP.md`・`REPORT_EFFORT.md` は両側の行を残し、`check_canvas_syntax.sh` は `canvas_string.cpp` と vstgui4 の `platformfactory.cpp` を両方検査する)。main 側の `platformfactory.cpp` の WASM 分岐で harness の初期化経路が変わったため、HEAD で再測定した。
- 測定は `995f9fb32` (作業ツリー clean・`work/` のみ) で行った。load (1 分平均) は render 実行の直前 0.32・全検証の後 0.70。

| 項目 | 値 (`995f9fb32`) |
|---|---|
| `check_render_poc.sh` rc / real | 0 / 14.644 s |
| compile | 71/71 ok (upstream 63/63・canvas・harness の失敗 0・error 行 0)・13928 ms |
| link | rc=0・未解決 0・479 ms |
| run | rc=0・95 ms |
| `bytes` / `nonzero_before` / `control` / `nonzero_after` | 48000 / 0 / 1 / 12000 |
| `text_px` / `text_width` | 112 / 54 |
| render 判定 | pass |
| `check_canvas_syntax.sh` | rc=0 (8/8 errors=0・real 3.325 s) |
| `check_wasm_syntax.sh` | rc=0 (seed 6 errors=0・real 0.465 s) |
| `count_canvas_noop.py` | draw 15 (no-op 12・実装 3)・state 14 (no-op 7・実装 7)。§17-5 と同じ |

- §17-3 からの変化は件数だけ: compile 70→71・canvas 構文検査 7→8 (main 側が upstream の `platformfactory.cpp` を検査対象に加えたため)。画素・文字の値は変わらない。
