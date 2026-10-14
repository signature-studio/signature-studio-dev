> **付録**: `REPORT_EFFORT.md` §13 (#2107 / SR-39) の本文。行数上限 250 行のため分割移動 (内容は削除していない)。

## 13. 2026-10-14 run (#2107 / SR-39): canvas platform の font・graphicsdevice (wasm)

- 範囲: §6 の純粋仮想のうち、font 7 関数 (`iplatformfont.h`) と graphicsdevice 31 関数 (`iplatformgraphicsdevice.h`) の wasm 実装。計 38 関数。人日は出さない (§7)。
- 実装: `gui/canvas/canvas_font.{h,cpp}` (`IPlatformFont` 1 + `IFontPainter` 1)、`gui/canvas/canvas_graphicsdevice.{h,cpp}` (factory 1・device 1・context 1 が `IPlatformGraphicsDeviceContextBitmapExt` を兼ねる)。
- 関数数の照合: `grep -cE '=\s*0\s*;'` は font 7 (`iplatformfont.h`)・graphicsdevice 31 (`iplatformgraphicsdevice.h`)。新規 2 ファイルの `override` は font 7・graphicsdevice 31 で、純粋仮想と 1 対 1 に対応する。
- 意味論は PoC の最小: 描画命令 (`draw*` `fill*` `clearRect`) はラスタライザが無いため `false` を返して描画しない。状態設定は `setLineWidth` `setClipRect` `setFillColor` `setFrameColor` `setGlobalAlpha` だけ値を保持し、`setLineStyle` `setDrawMode` `setTransformMatrix` `saveGlobalState` `restoreGlobalState` は何もしない (実装は `canvas_graphicsdevice.cpp` の該当関数)。文字の描画と幅は空 (幅 0)。メトリクス (ascent 等) は upstream の「未対応」値 `-1`。描画の確認は #2065 (SR-36) の範囲。
- 検証: 実測値は下記 13-1 節が正本 (測定 commit `89495465`)。
  - 具象性の確認: 追跡ファイル `gui/canvas/check_concrete.cpp`。新規 5 クラス (`CanvasFontPainter` `CanvasFont` `CanvasGraphicsDeviceFactory` `CanvasGraphicsDevice` `CanvasGraphicsDeviceContext`) の `static_assert(!std::is_abstract_v<...>)` と、`CanvasFont` 生成・`getPainter()`・`CanvasGraphicsDeviceContext` 生成の検査。実行コマンド (`gui/work/vstgui4` と `gui/work/emsdk/upstream/emscripten` が展開済みの環境で、`gui` を cwd として実行する):
    ```
    cd work/vstgui4 && em++ -std=c++17 -fsyntax-only -I. -I../../canvas ../../canvas/check_concrete.cpp; echo rc=$?
    ```
    測定 (`89495465`): rc=0。初回は `canvas_font.h` が `UTF8String` の定義 (`cstring.h`) を include しておらず rc=1 だった。`check_concrete.cpp` は `canvas_font.h` を単独で読むため、ヘッダの自己完結性の欠陥として `#include "vstgui/lib/cstring.h"` を足して修正した (`89495465`)。
- 修正した既存スクリプト: `check_canvas_syntax.sh` と `check_wasm_syntax.sh` の PATH が `work/emsdk/emsdk/upstream` を指していた。`toolchain-emsdk` の実配置は `work/emsdk/upstream/emscripten` (`em++` 6.0.12 で確認)。旧パスでは `em++` が見つからず rc=127 になり、0 error に見えていた。修正後に実行して rc=0 を確認した。
- 未検証: リンク・実行・描画 (閉包が実際に要求する関数はリンク時に確定させる、§6 の注記どおり。リンクは本 run で行っていない)。

### 13-1. 測定 commit と差分

- 測定 commit: `89495465` (コードを変えた最後の commit。`canvas_font.h` に `cstring.h` の include を追加)。
- 実測 (HEAD = `89495465`、em++ 6.0.12、vstgui4_14_3):
  - `gui/canvas/check_canvas_syntax.sh` (`-D__linux__` 補正なし): `canvas_bitmap.cpp` rc=0 errors=0、`canvas_graphicspath.cpp` rc=0 errors=0、`canvas_frame.cpp` rc=0 errors=0、`canvas_font.cpp` rc=0 errors=0、`canvas_graphicsdevice.cpp` rc=0 errors=0。script rc=0、所要 2.04 s real。load 1.21 (測定直前)。
  - `gui/canvas/check_concrete.cpp` (§13 のコマンド): rc=0。
  - `gui/check_wasm_syntax.sh` (seed 6): rc=0 errors=0。
- 測定 commit `89495465` から HEAD (`cdb3f89f`) までのコード差分: 空 (`git diff 89495465 HEAD -- tools/targets/serum2/gui/canvas tools/targets/serum2/gui/check_wasm_syntax.sh` は 0 行)。
- HEAD `cdb3f89f` での再実測 (2026-10-14 run、em++ 6.0.12、vstgui4_14_3 は `$RUNNER_TEMP` に clone し `gui/work` を使わず symlink で指定): `check_canvas_syntax.sh` の 5 ファイル rc=0 errors=0、script rc=0、elapsed 4.31 s、load 0.68 (開始時)。`check_concrete.cpp` rc=0。`check_wasm_syntax.sh` seed 6 rc=0 errors=0。
- 差分の扱い (本 fix run の訂正): 前版の `22e33688` 測定は HEAD の `canvas_frame.*`・`check_concrete.cpp` を含まなかった。今回 HEAD 版を全て実測し直した (上記)。
