# GUI #4804 (WIN-56): e2e.sh への step 2d (統計 API 単体) 組込み — 検証記録

正本は `tools/gui/REPORT.md` の索引から辿る。本付録は #4804 (PR #4816) の実測を置く。

## 1. 変更範囲
- `tools/gui/e2e.sh` に step `2d/6` (`bash tools/gui/test/stats_test.sh`、grep `passed|FAIL`) を 2 行追加。
- 2d は W 版ゲスト (`gui_app_w.c`) を実行しない。統計 API `gui_hl_stats` と SHA-256 の単体テスト (`stats_test.c`) と、そのネガコンだけを回す (#3460 受入 2)。
- W 版ゲストの native 通し・EXACT MATCH・到達順序検査は既存の step 2c (`native_w_e2e.sh`) にあり、本変更では触っていない。2c の出力には統計が含まれない。
- 未達 (子 issue): W 版ゲストの統計を 2c の出力に入れる → #4821 (WIN-57)。wasm W 版の sha256 一致を e2e に組込む → #4822 (WIN-58)。

## 2. 検証 (この run で実測)
- 測定 commit: `c06575782` (コードを変えた最後の commit。`git diff c06575782 HEAD -- tools/gui` は 0 行 = 差分 0)。
- 検証 HEAD: 本 REPORT 更新の commit (本付録の追記 commit)。コード差分は 0 のまま。
- `bash tools/gui/test/stats_test.sh`: `[stats_test] 21 passed, 0 failed`、0.27 秒、rc 0。

## 3. 再現できなかった項目 (この run の環境)
- 全体 `bash tools/gui/e2e.sh` は本 run では再実行していない。ランナーに `/opt/retdec`・`/opt/emsdk`・`x86_64-w64-mingw32-gcc` が無く、`selftest.sh` が mingw 不足で落ちることを確認した (実測: `FileNotFoundError: x86_64-w64-mingw32-gcc`、0.06 秒で rc 1)。
- したがって `[selftest] 512 passed` と全体 `[gui-e2e] ALL PASS` (3m09s) は、作者の run (PR 本文が挙げる `/tmp/opencode/gui_e2e_full2.log`) の値で、本 run では確認していない。このログはこの環境に無い。
- `tools/gui/flengine/e2e.sh` (既存 gate の回帰) は本 run で実行していない。`tools/gui/e2e.sh` の変更は追加 2 行のみで、`flengine/e2e.sh` は `tools/gui/e2e.sh` を呼ばない (review で確認済み)。
- 製品 KPI (FLEngine 起動 dispatch 数・通過 unit 数・最初のウィンドウ) は動かしていない。
