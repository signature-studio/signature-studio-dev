# flengine 付録 (#3832 分割移動): REPORT.md §6e〜§6h・§6f の全文

本文書は `REPORT.md` の 250 行上限のため、§6e〜§6h・§6f を行を削らず移したもの (Git 履歴に残す)。

## 6e. 再測定と main 切り分け (PR #577 の PM 指示 1・2。測定 commit `a88aabfa`)

測定対象のコード差分は `22062917` 以降 0 (`git diff 22062917 a88aabfa -- tools/gui tools/m11` は `results/` のみ)。`a88aabfa` は `results/baseline_boot.json` と `results/ir_sha256.txt` の再生成のみ commit。

| 実行 (foreground・1 回・rc は実測) | rc | 所要 | 結果 |
|---|---|---|---|
| `flengine/e2e.sh` (HEAD `22062917`、`pnpm install` 前は gui/e2e.sh のみ tsc 欠落) | **1** | 304 s (load 1.00→1.00) | judge **13/14**。S1 FAIL `870/1/47/24/0` (base `872/1/47/22/0`)。他 13 PASS。P1 `RegisterClassW=3`、P4 `hwnd=0x110000f`、P5 `hwnd=0x110000e`。ネガコン N1〜N9 期待どおり FAIL |
| `flengine/e2e.sh` (**origin/main `c6f70c98`**、検証用 worktree `work/main_wt`) | **1** | — | **main 単体は build 段で停止**: `wasm-ld: duplicate symbol: GetMonitorInfoW` (#1096 `6f979463` の `tools/m11/m11_win.c` と `tools/gui/build/gui_adapt_w32.c` の重複)。S1 まで到達せず |
| 同 (main、重複 2 関数 `GetMonitorInfoW`・`EnumDisplayMonitors` を scratch で削除。**コミットしない**) | **1** | 301 s (load 1.00→1.00) | judge **13/14**。**S1 FAIL `870/1/47/24/0` (base `872/1/47/22/0`)**。S1 の値は HEAD と同一 |
| `gui/e2e.sh` (HEAD `a88aabfa`、`pnpm install --frozen-lockfile` 後) | **0** | 139 s (load 2.60→1.60) | ALL PASS (selftest 506/0、stress negctl 2/2 exit 1、text/pe_image/present/input ALL PASS) |
| `m11/ldfix/f4_e2e.sh` (HEAD `a88aabfa`) | **0** | 249 s (load 1.04→1.27) | 6 gate PASS (F1/F2/D1/D2/P1/A1)。ネガコン 4/4 期待行付き FAIL。RegisterClassW pre 2 / noand 2 / post 3。survey `870/1/47/24` |

**切り分けの結論 (PM 指示 1)**: S1 FAIL は main でも同じ値で再現する。したがって **この PR の変更が原因ではない**。S1 の判定は緩和していない (FAIL のまま)。原因特定は子 issue **#1442** (`[GUI-21]`、親 #564) に起票。#1275 ([M11-N78]) とは対象 unit が一致するが、同系統かは未確認。main でも同値 (S1 FAIL) であることは、この PR の原因ではないことの根拠。S1 の gate PASS の根拠ではない。追跡 #1442。

注記: main の build 段の重複は scratch の削除で回避しただけで、main 側の修正は行っていない。起票先は本 PR の範囲外 (`#1096` の作者 / m11 系の PM 判断)。

**ret 値の IR 併記 (PM 指示・受入条件 3)**: `function_52a7f0` の ret は IR ごとに異なる値。どの IR の値か:
- `f4_e2e.sh` の post IR (`m11_gen_ir2.sh` → `m11_build.sh`、wndseed 無し): **`0x110000f`**
- `flengine/e2e.sh` の最終 IR (wndseed 込み。`m11_wndseed.sh` を実行): **`0x1100010`** (§6d-2)

## 6g. 現 head の再測定 (review `bde0c341` 差し戻しの必須 2。main 取り込み後)

main `f3ffd7ba` 取り込み後の head `bde0c341` で、§6e の測定 commit `a88aabfa` 以降のコード差分を再測定した。`git diff a88aabfa bde0c341 -- tools/gui tools/m11` のうち `.sh`・`.py`・`.c`・`.h`・`.inc` 等の実行コードは `m11_win.c` (#1096 由来) と `gui/build/*` の main 側差分のみ (main が重複定義を持ち込んだ)。

| 実行 (foreground・1 回・rc は実測) | rc | 所要 | 結果 |
|---|---|---|---|
| `bash tools/m11/ldfix/f4_e2e.sh` (head `bde0c341`) | **2** | 86 s (load 0.59→1.03) | **build 段で停止** (gui build 失敗 (pre))。`wasm-ld: duplicate symbol: GetMonitorInfoW` と `EnumDisplayMonitors` (`obj/win.o` と `gui/gui_adapt_w32.o`)。F4 の gate には到達せず |
| `bash tools/gui/flengine/e2e.sh` (head `bde0c341`) | **1** | 325 s (load 1.12→1.33) | build 段で停止。`wasm-ld: error: duplicate symbol: GetMonitorInfoW` (同上 2 件)。judge は実行されず |
| `bash tools/gui/e2e.sh` (head `bde0c341`) | **0** | 301 s (load 3.47→0.89) | ALL PASS (simd / 6c/6 fail-fast / present / input / stress (negctl 2/2 exit 1) / selftest 506 passed 0 failed)。ASan の `heap-use-after-free` 等の出力 0 件 |

**判定 (bde0c341 時点の記録)**: `gui/e2e.sh` は PASS。`flengine/e2e.sh` と `f4_e2e.sh` は main 由来の重複定義 (#1096 `6f979463` の `tools/m11/m11_win.c` と `tools/gui/build/gui_adapt_w32.c`) で build 段が止まった。この時点の S1 と F4 の gate は未測定。`a88aabfa` の測定値は main 取り込み前のものなので、現 head の値としては使わない。**重複は `97db5a58` の weak 化で解消済み。現 head の値は §6h。**

**GetMonitorInfoW 重複の扱い**: 重複の解消 (どちらの定義を正とするか) は build 仕様の判断を要するため、本 run では commit しない。起票先は子 issue **#1559** (`[M11-N102]`)。

**回避版の実測 (参考・commit していない)**: `tools/gui/flengine/build.sh` のリンク行に `-Wl,--allow-multiple-definition` を一時的に足して測定し、測定後に元へ戻した (`git status` は測定後クリーン)。

| 実行 (回避版・foreground・1 回) | rc | 所要 | 結果 |
|---|---|---|---|
| `bash tools/gui/flengine/e2e.sh` (head `bde0c341` + 回避) | **1** | 467 s (load 1.13→1.07) | judge **12/14**。**R2 FAIL** `reached 31 (expected floor 19); missing=['EnumDisplayMonitors', 'GetMonitorInfoW']`。**S1 FAIL** `870/1/47/24/0` (base `872/1/47/22/0`、main と同値)。他 PASS: L1×2・A1 (193/193/173/20)・B1 52・R1・S2・P1 (RegisterClassW=3)・P2〜P5・W1。ネガコン N1〜N9 期待どおり FAIL |
| `bash tools/m11/ldfix/f4_e2e.sh` (head `bde0c341` + 回避) | **0** | 387 s (load 1.06) | 6 gate PASS (F1/F2/D1/D2/P1/A1)。ネガコン 4/4 期待どおり FAIL。`RegisterClassW` pre 2 / noand 2 / post 3。`function_52a7f0` ret pre `0x0` → noand `0x0` → post **`0x110000f`** (本 IR (wndseed 無し) の値)。survey pre/noand/post = `870/1/47/24` |

結論: 回避版では S1 の値は main と同じ (`870/1/47/24/0`)。R2 は重複の片方が消えたことで 2 件欠落する (§6f の回避の副作用と同じ形)。したがって flengine の判定 (12/14) は、重複の解消方法を決めるまで確定しない。S1 の判定式は変えていない。baseline の値は §6h 冒頭の注記のとおり再生成で変わっている (判定式ではない)。

## 6h. weak 化後の現 head の実測 (PM 指示 #577。測定 commit `97db5a58`)

`m11_win.c` の `EnumDisplayMonitors` / `GetMonitorInfoW` に `__attribute__((weak))` を付けた 1 変更 (`97db5a58`、差分 2 関数のみ) の head で、3 本を foreground・各 1 回。素材は `ws-577/work/` (gitignore) に展開。`retdec-decompiler` と `EMSDK_ENV` は `ws-577/work/toolchain/` を指定。

| 実行 | rc | 所要 | load (開始→終了) | 結果 |
|---|---|---|---|---|
| `bash tools/m11/ldfix/f4_e2e.sh` | **0** | 411 s | 0.89 → 1.30 | build 段は通過 (重複定義の解消を確認)。gate F1/F2/D1/D2/P1/A1 全 PASS。ネガコン N1〜N4 期待どおり FAIL。RegisterClassW pre 2 / noand 2 / post 3、ret pre `0x0` → noand `0x0` → post `0x110000f`。survey pre/noand/post = `870/1/47/24` |
| `bash tools/gui/flengine/e2e.sh` | **1** | 460 s | 1.18 → 1.23 | build 段通過。**judge 13/14**。FAIL は **S1 のみ**: `870/1/47/24/0` (base `872/1/47/22/0`)。R1・R2 (floor 19、reached 33)・B1 52・S2・P1〜P5・W1 は PASS。ネガコン N1〜N9 期待どおり FAIL。selftest 506 passed / 0 failed |
| `bash tools/gui/e2e.sh` | **0** | 211 s | 1.58 → 3.37 | **ALL PASS** (simd / 6c/6 fail-fast / text / stress (50000 frames ×2、negctl 2/2 exit 1) / selftest)。`heap-use-after-free` 0 件 |

前提 (回避版との違い): 回避版 (`--allow-multiple-definition`) は `m11_win.c` と GUI 側の両方を連結して片方を捨てる。weak 版は GUI 側の強い定義が勝つ。両者で `EnumDisplayMonitors` / `GetMonitorInfoW` の使われる定義が同じかは、R2 の `missing` の変化で見る。今回の R2 は `missing=[]` で PASS。

S1 の値 `870/1/47/24/0` は §6f の main と同値で、**S1 の判定式は変えていない**。#1442 で扱う。

**baseline の値の変化 (再生成によるもの。判定式は変えていない)**: `results/baseline_survey.json` の現値は `ok 872 / trap 22` (kinds: unreachable 1 / halt0->longjmp 7 / OOB 14)、`results/baseline_boot.json` の `threw` は `unreachable` (`units_run 52` は不変)。旧値は `baseline_survey` が `871 / 23`、`threw` が `memory access out of bounds`。両ファイルは `tools/gui/flengine/e2e.sh` が毎回 m11 baseline を測り直して `results/` にコピーする生成物 (e2e.sh の 36〜41 行・64 行)で、判定基準を手で書き換えた値ではない。main 取り込み後の再生成で値が変わった。
- `baseline_survey.json` の現値は commit `bf9cf547` で初めて現れた (それ以前は `52e6bd57`〜`d96a0fa8` の `871 / 23`)。
- `baseline_boot.json` の `threw` が `unreachable` になったのは `d96a0fa8` から (それ以前は `memory access out of bounds`)。
- 現 `results/` を作った run は**特定できなかった** (run ID は確認していない)。main の値 (871 / 23) に戻すと、現 IR の実測と食い違う古い値を残すことになるため戻していない。

**S2 gate の変更 (`judge.py`、commit `8a6dcf4b`。S1 の判定式とは別)**:
- 旧式: `ffu <= stub_soft and not (kinds.gui_failfast and not ffu)`。ff で fail-fast になった API は、soft で必ず STUB でなければならなかった (`ffu` = ff survey の fail-fast API 集合、`stub_soft` = soft の STUB API 集合)。
- 新式: `sfu <= ffu and ffu <= (stub_soft | sfu)` (`sfu` = soft survey の fail-fast API 集合)。soft が ff に無い fail-fast を増やさないこと、ff の fail-fast API は soft で STUB か fail-fast のままであること、の 2 条件。
- 変えた理由: fail-fast は API 単位ではなく **action 単位** で起きる (例: §5-5 の `SystemParametersInfoW` の未対応 action)。旧式は、同じ API が soft で別の action として fail-fast すると FAIL になり、action の違いを表せなかった。新式は「soft で fail-fast が増えない」を直接検査する。
- 注意: 新式は旧式より**緩い** (ff の fail-fast API が soft で fail-fast のままでも PASS する)。
- 現 head の値で旧式を手計算した (既存の `results/survey_ff.json` と `survey_soft.json` から。再実行はしていない): ff の fail-fast 集合 = `{LoadImageW}`、soft の STUB 集合 = `{LoadImageW}`、soft の fail-fast 集合 = `{}`。**旧式 = PASS、新式 = PASS**。S2 の判定結果は変わらない。

`tools/gui/flengine/results/*.json` と `baseline_boot.json` は本実測で再生成された出力 (`GetMem` 等の probe 値・`gui_shared_ptr` の 1 件・`ir_sha256` が現 head で変わる)。本 commit に含める。

## 6f. origin/main の S1 実測 (PR #577 の PM 指示 1。main commit `b4a8422c`)

PM 指示: 「main でも同じ 870 vs 872 なら既存の欠陥、違えば本 PR が原因」。S1 の判定式は変えていない。

| 項目 | 値 |
|---|---|
| 測定対象 | `origin/main` = `b4a8422c` (Merge #1443)。検証用 worktree (detached・本 PR の branch ではない)。素材 `work-m11` / `work-liftdiff` / `fl-win64` は同じ展開物 |
| 手順 | `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> RETDEC=<[RETDEC] の retdec-decompiler> FL_WIN64_DIR=<[WIN64]> ANALYSIS_DIR=… bash tools/gui/flengine/e2e.sh` (foreground・1 回) |
| rc / 所要 / load | **1** / 445 s / 0.62→1.65 (nproc 4) |
| S1 survey parity (soft) | **FAIL `870/1/47/24/0` (base `872/1/47/22/0`)** |
| 判定 | 12/14 (S1 FAIL、**R2 FAIL**)。他 L1×2・A1・B1・R1・S2・P1〜P5・W1 は PASS |

**main 側の build 段の回避 (本実測だけの前提。main に修正は入れていない)**: main `b4a8422c` は `wasm-ld: duplicate symbol: GetMonitorInfoW / EnumDisplayMonitors` で build 段で止まる (`tools/m11/m11_win.c` (#1096) と `tools/gui/build/gui_adapt_w32.c` (`gen_api.py` 生成) の重複)。scratch の `tools/gui/flengine/build.sh` のリンク行に `-Wl,--allow-multiple-definition` を足して通した (`obj/*.o` を先に並べるので `m11_win.c` 側の定義が使われる)。この変更は commit していない。

**R2 の FAIL は回避の副作用の可能性が高い (未確定)**: 回避後の main では `EnumDisplayMonitors` / `GetMonitorInfoW` が reach に出ず (`missing=['EnumDisplayMonitors', 'GetMonitorInfoW']`、reached 30 ≥ floor 19 だが欠落 2 件で FAIL)。直前の main 測定 (§6e、ソース側で重複を削除した版) では R2 PASS の 13/14 だった。回避方法で R2 が変わるため、本節の R2 は main の欠陥の根拠にしない。S1 の値は両方法で `870/1/47/24/0` と一致する。

**結論**: S1 の `870/1/47/24/0` (base `872/1/47/22/0`) は `origin/main` (`b4a8422c`) でも同一。**PR #577 の変更が原因ではない**。S1 は FAIL のまま (判定を緩和していない)。原因の追跡は子 issue **#1442** (`[GUI-21]`、親 #564)。#1275 (`[M11-N78]`) とは対象 unit が一致するが、同一原因か・同系統かは未確認 (機械語・IR の突合は未実施)。
