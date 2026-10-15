# GUI #4822 (WIN-58): e2e.sh への step 6i (W 版ゲストの wasm 読み戻し sha256 と native の一致) 組込み — 検証記録

正本は `tools/gui/REPORT.md` の索引から辿る。本付録は #4822 (PR #4856) の実測を置く。

## 1. 変更範囲
- `tools/gui/e2e.sh` に step `6i/6` (`bash tools/gui/test/wasm_w_e2e.sh`) を 2 行追加。既存 step のコードは変えていない。
- `tools/gui/e2e.sh` は `flengine/e2e.sh` を呼ばない (`grep -c flengine tools/gui/e2e.sh` = 0)。よって `tools/gui/flengine/e2e.sh` は本 e2e の入力を変えず、個別実行の対象外とする。
- `tools/gui/flengine/e2e.sh` は本 run で個別に実行を試みたが、前提素材 `tools/m11/work/boot_final.ll` (work-m11) が無く `前提欠如` で rc 2 (実測 0.0 秒)。回帰の実測は無い。

## 2. 検証 (取り込み後 HEAD で実測)
- 測定 commit: `0c8989a87` (main を merge した、コードを変えた最後の commit)。
- 前回の測定 commit `fb99928ca` からの `tools/gui` の差分は main 由来の 118 行 (`REPORT.md` 1 行、`REPORT_APPENDIX_4804.md`、`e2e.sh` の step 2d、`golden/gen_golden_w.py` の統計照合、`test/native_w_e2e.sh`)。
- 全体: `TMPDIR=$RUNNER_TEMP bash tools/gui/e2e.sh` → `[gui-e2e] ALL PASS`、rc 0、実測 259 秒 (4 分 19 秒)、開始時 load 1.33。
- step 6i の出力:
  - OffscreenCanvas 読み戻し vs 独立オラクル: EXACT MATCH (0 differing px of 64000)
  - 読み戻し sha256 `6f809bdf…596bc6` vs native 同 sha256: MATCH
  - スクリーンショット vs オラクル: EXACT MATCH (0 differing px)
  - 到達ログ順序検査: PASS (32 件の到達行)
  - ネガコン (1 px 改竄): MISMATCH・rc 1 → PASS
- 単体: `bash tools/gui/test/wasm_w_e2e.sh` → `[wasm_w_e2e] PASS` (本 run の全体 run 内で確認)。
- 他 step の実測 (同 run): `selftest` `512 passed, 0 failed`、`stats_test` `21 passed, 0 failed`、統計照合 `STATS MATCH` とネガコン `STATS MISMATCH`。
- 差分 0 証跡: `git diff 0c8989a87 HEAD -- tools/gui ':!*.md'` は 0 行 (本 appendix と `REPORT.md` の文書差分のみ)。

## 3. 製品 KPI
- 起動・GUI の挙動は変えていない (e2e gate の追加のみ)。FLEngine 起動 dispatch 数・通過 unit 数・最初のウィンドウの有無は**動かしていない**。
