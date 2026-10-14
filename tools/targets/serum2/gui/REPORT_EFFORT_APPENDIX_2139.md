> **付録**: `REPORT_EFFORT.md` §14 (#2139 / SR-42) の本文。行数上限 250 行のため分割移動。

## 14. 2026-10-14 run (#2139 / SR-42): canvas platformfactory の wasm 実装

- 範囲: §6 の純粋仮想のうち factory 20 関数 (`platformfactory.h` の `IPlatformFactory`)。人日は出さない (§7)。
- 前提 (解決): `platformfwd.h:36` の `static_assert (false, "unknown platform")` を止めるため、upstream ヘッダへの 2 つ目の patch `patches/platformfwd_emscripten.patch` を追加し、`LINUX` を立てる案 (副作用が大きい) は採らなかった。`vstguibase_emscripten.patch` は `WASM 1` に加えて `VSTGUI_OPENGL_SUPPORT 0` を定義する (未定義だと既定値 1 になり、`IPlatformFrame::createPlatformOpenGLView` が純粋仮想として残って `CanvasFrame` が具象化できない)。
- 実装: `canvas/canvas_platformfactory.{h,cpp}` (`CanvasPlatformFactory`)。`createFrame` `createFont` `createBitmap(size)` `createGradient` 等は既存の canvas 実装を返す。`getTicks` は `steady_clock` のミリ秒。資源読込 (`createBitmap(desc)` `createBitmapFromPath` `createBitmapFromMemory` `createResourceInputStream`)・文字列・タイマー・クリップボード・file selector・gradient は `nullptr` / `false` / 空値 (未対応)。`asLinuxFactory` `asMacFactory` `asWin32Factory` は `nullptr`。
- 検証 (測定 commit `e5ba8809`、クリーン clone の `vstgui4_14_3` = `b1e82355` に両 patch を当てた状態。`-D__linux__` 補正なし):
  - `canvas/check_canvas_syntax.sh`: bitmap・graphicspath・frame・font・graphicsdevice・platformfactory の 6 files すべて rc=0 errors=0 (実行 5.3 s real、load average 0.23)。
  - `check_wasm_syntax.sh` (seed 6): rc=0 errors=0。
  - `canvas/check_concrete.cpp` (`CanvasPlatformFactory` の具象性を追加): rc=0 errors=0。
- 途中で出た 2 件 (修正済み): (1) `CanvasFrame` の `createPlatformOpenGLView` 欠落。#2109 時点では factory 未インスタンス化のため露見していなかった。patch 側で `VSTGUI_OPENGL_SUPPORT 0` にして解消。(2) `IPlatformTimer` の include 不足 (`SharedPointer` が不完全型を参照)。
- 未検証: リンク・実行・描画 (#2065 の範囲)。閉包が実際に要求する関数はリンク時に確定させる (§6 の注記どおり)。
- `git diff e5ba8809 HEAD -- tools/targets/serum2/gui` の出力: 測定 commit が本節の commit 時点の HEAD のため、差分 0 (本節の REPORT 文書は除く)。
