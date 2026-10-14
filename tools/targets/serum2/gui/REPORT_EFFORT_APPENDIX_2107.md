> **付録**: `REPORT_EFFORT.md` §13 (#2107 / SR-39) の本文。行数上限 250 行のため分割移動 (内容は削除していない)。

## 13. 2026-10-14 run (#2107 / SR-39): canvas platform の font・graphicsdevice (wasm)

- 範囲: §6 の純粋仮想のうち、font 7 関数 (`iplatformfont.h`) と graphicsdevice 31 関数 (`iplatformgraphicsdevice.h`) の wasm 実装。計 38 関数。人日は出さない (§7)。
- 実装: `gui/canvas/canvas_font.{h,cpp}` (`IPlatformFont` 1 + `IFontPainter` 1)、`gui/canvas/canvas_graphicsdevice.{h,cpp}` (factory 1・device 1・context 1 が `IPlatformGraphicsDeviceContextBitmapExt` を兼ねる)。
- 関数数の照合: `grep -cE '=\s*0\s*;'` は font 7 (`iplatformfont.h`)・graphicsdevice 31 (`iplatformgraphicsdevice.h`)。新規 2 ファイルの `override` は font 7・graphicsdevice 31 で、純粋仮想と 1 対 1 に対応する。
- 意味論は PoC の最小: 描画命令 (`draw*` `fill*` `clearRect`) はラスタライザが無いため `false` を返して描画しない。状態設定は `setLineWidth` `setClipRect` `setFillColor` `setFrameColor` `setGlobalAlpha` だけ値を保持し、`setLineStyle` `setDrawMode` `setTransformMatrix` `saveGlobalState` `restoreGlobalState` は何もしない (実装は `canvas_graphicsdevice.cpp` の該当関数)。文字の描画と幅は空 (幅 0)。メトリクス (ascent 等) は upstream の「未対応」値 `-1`。描画の確認は #2065 (SR-36) の範囲。
- 検証 (実測、load は各 run 前後で 0.47 → 0.47):
  - `gui/canvas/check_canvas_syntax.sh` (em++ `-fsyntax-only`、`-D__linux__` 補正なし): `canvas_bitmap.cpp` rc=0 errors=0、`canvas_graphicspath.cpp` rc=0 errors=0、`canvas_font.cpp` rc=0 errors=0、`canvas_graphicsdevice.cpp` rc=0 errors=0。所要 2.14 s real。
  - `gui/check_wasm_syntax.sh` (seed 6): rc=0 errors=0。
  - 具象性の確認: 追跡ファイル `gui/canvas/check_concrete.cpp`。新規 5 クラス (`CanvasFontPainter` `CanvasFont` `CanvasGraphicsDeviceFactory` `CanvasGraphicsDevice` `CanvasGraphicsDeviceContext`) の `static_assert(!std::is_abstract_v<...>)` と、`CanvasFont` 生成・`getPainter()`・`CanvasGraphicsDeviceContext` 生成の検査。実行コマンド (`gui/work/vstgui4` と `gui/work/emsdk/upstream/emscripten` が展開済みの環境で、`gui` を cwd として実行する):
    ```
    cd work/vstgui4 && em++ -std=c++17 -fsyntax-only -I. -I../../canvas ../../canvas/check_concrete.cpp; echo rc=$?
    ```
    **本 run では実行していない** (`em++` と `vstgui4` が runner に無く、`toolchain-emsdk` 素材も未取得)。rc=0 は未確認で、再現には上記コマンドを em++ 環境で実行する必要がある。
- 修正した既存スクリプト: `check_canvas_syntax.sh` と `check_wasm_syntax.sh` の PATH が `work/emsdk/emsdk/upstream` を指していた。`toolchain-emsdk` の実配置は `work/emsdk/upstream/emscripten` (`em++` 6.0.12 で確認)。旧パスでは `em++` が見つからず rc=127 になり、0 error に見えていた。修正後に実行して rc=0 を確認した。
- 未検証: リンク・実行・描画 (閉包が実際に要求する関数はリンク時に確定させる、§6 の注記どおり。リンクは本 run で行っていない)。

### 13-1. 測定 commit と差分

- 測定 commit: `22e33688` (コードを変えた最後の commit。canvas 4 ファイル・2 スクリプト)。
- 測定 commit `22e33688` から HEAD までのコード差分 (`git diff 22e33688 HEAD -- tools/targets/serum2/gui/canvas tools/targets/serum2/gui/check_wasm_syntax.sh`) は空ではない。内訳: `canvas_graphicsdevice.h` (コメントのみ)、`check_canvas_syntax.sh` (main 由来の `canvas_frame.cpp` の対象追加)、`check_concrete.cpp` (新規)、main 由来の `canvas_frame.{h,cpp}` (#2109)。`canvas_font.{h,cpp}`・`canvas_graphicsdevice.cpp`・`check_wasm_syntax.sh` は差分 0。
- 差分の扱い: main 由来の `canvas_frame.*` と `check_canvas_syntax.sh` の対象追加は、本節の実測対象 (4 ファイル) に含まれない。HEAD の `check_canvas_syntax.sh` (5 ファイル) と `check_concrete.cpp` は本 fix run では未実測で、em++ 環境での再測定が必要。
