# flengine REPORT 付録

`REPORT.md` の行数上限 (250 行・`docs/DOC_MAP.md` §1) を超えないよう、本付録へ分割移動した節。内容は削除していない。

## 6i. S1 (soft) の unit 304/555 調査 (#1442 / GUI-21)

測定 commit: `549e6817` (`build.sh` の改名のみ。main `721f5acb` の上)。実行: `ANALYSIS_DIR=$RUNNER_TEMP FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 PATH=/opt/retdec/bin:$PATH bash tools/gui/flengine/e2e.sh` (runner 4 vCPU・直列。e2e 375 s、load 0.86 → 1.19)。

- **build 修正**: #1096 の `m11_win.c` の `EnumDisplayMonitors` / `GetMonitorInfoW` が `gui_adapt_w32.c` と重複し、ff / soft の wasm-ld が落ちていた (§6 の前提節と同じ件)。`build.sh` の user32 改名リストに 2 件を足した (`m11_win_*`)。これで L1 link[ff/soft] が PASS。
- **判定 13/14**: S1 のみ FAIL。`ok/noproc/miss/trap/clobber = 870/1/47/24/0` (base `867/1/47/27/0`)。他 13 gate は PASS (selftest 506/0、pe_image 4b、ネガコン N1〜N9 が全て FAIL を確認)。
- **unit 別の突き合わせ** (base は `run.mjs --survey --wasm m11_base.cjs` に `GF_SURVEY_UNITS` を付けて取り直し、soft の `survey_soft_units.json` と比較):
  - 差は **3 unit のみ**: 101 (base `trap halt0->longjmp` / soft `ok`)、291 と 296 (base `trap oob` / soft `ok`)。方向は全て base→soft の trap 解消。
  - **304 と 555 は base も soft も `memory access out of bounds`** (`baseline_base` 側で ok ではない)。issue 本文の「base は ok」は現 main の測定と合わない。soft 側の OOB 2 件は base の OOB と同じ kind で、GUI 結合による新規 trap ではない。923 も両方 OOB。
- **304/555 の真因 (受入条件 1)**: 未達。真因は `[M11-N91]` (#1426・OPEN: OOB 直前の tbl/cnt/obj の実値採取と obj の生成元特定) と #714 (`function_535c2e` 系) の既存調査にある。本 run では wasm の local を読む計測を入れておらず、特定に至っていない。
- **#1275 系統の判定 (受入条件 2)**: 同系統ではない。#1275 (`tools/m11/trap_triage/REPORT_1275.md`) の 304/555 は **ClassCreate ON 時の abort** (`function_535c2e` の未定義 closure 外)。本 e2e は ClassCreate OFF (既定) で、304/555 は OFF でも OOB のまま。OFF の OOB は `function_535bf2` が先頭フレーム (REPORT_1275 §3 の OFF 行)。したがって OFF の OOB の原因は #1275 の abort とは別経路で、#1426 側。
- **S1 の残り (101/291/296)**: base 側だけ trap する 3 unit。survey の順序依存 (§5-6 の既知) か GUI 実装の差かは未切り分け。子 issue #1635 `[GUI-22]` で扱う。

未解決 (起票先付き): 受入条件 1 は #1426 (304/555/923 の OOB 実値採取)。S1 の 3 unit は #1635 `[GUI-22]`。gate の判定式 (`judge.py`) は変更していない。


> 注: 上記の判定 (13/14・S1 の値) は測定 commit `549e6817` の `judge.py` によるもの。その後 `1844b4f7` で S2 gate の判定式が変わっており、現 HEAD では未再測定。
