> **付録**: `REPORT_EFFORT.md` §12 (#2109 / SR-40) の本文。行数上限 250 行のため分割移動 (内容は削除していない)。

## 12. 2026-10-14 run (#2109 / SR-40): canvas の frame 実装 (factory は子 #2139 へ)

- 範囲: §11 の残り 4 files のうち、frame (IPlatformFrame) を実装。font 7・graphicsdevice 31 は #2107 (SR-39)、factory 20 は #2139 (SR-42) へ移した。
- 実装: `canvas/canvas_frame.{h,cpp}`。ネイティブのウィンドウを持たないため、サイズだけ保持し、マウス・修飾キー・カーソル・tooltip・drag・text edit・option menu・view layer は `false` / `nullptr` を返す。
- 検証 (`canvas/check_canvas_syntax.sh`、`-D__linux__` 補正なし):
  - `canvas_bitmap.cpp`: rc=0 errors=0
  - `canvas_graphicspath.cpp`: rc=0 errors=0
  - `canvas_frame.cpp`: rc=0 errors=0
  - `check_wasm_syntax.sh` (seed 6): rc=0 errors=0
- 初回 (include 不足) の失敗: `canvas_frame.cpp` は `IPlatformTextEdit` / `IPlatformOptionMenu` / `IPlatformViewLayer` が不完全型のまま `SharedPointer` を返すため error 3 件。対策は 3 つの `iplatformXXX.h` の include 追加。これで abstract 化の error も消えた。
- factory 未実装の原因: `platformfactory.h` → `platformfwd.h:36` が `static_assert (false, "unknown platform")` で止まる。`vstguibase_emscripten.patch` は `WASM 1` のみで `LINUX` を立てないため。factory の 20 関数はこの分岐が決まるまで実装・検証できない (#2139)。
- 未検証: リンク・実行・描画 (#2065 の範囲)。
- 測定 commit: `c9a7329a` (コードを変えた最後の commit。本節の REPORT 修正は含まない)。
