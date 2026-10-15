# REPORT_APPENDIX_3352 (WIN-21 #3352)

#3352 (WIN-21) の S1 unit 差の再測定と、現 HEAD の e2e 実測の正本。REPORT.md には §6k を置かない (REPORT.md は DOC_MAP §1 の上限 250 行を `c3ee6daa7` の時点で超えており、編集すると pr-lint の report-lines に当たる)。参照は REPORT_APPENDIX.md §6i から張る。

## 6k. 現 HEAD の実測と S1 の unit 差 (#3352 / WIN-21)

測定 commit `c3ee6daa7` (origin/main)。本 PR はコードを変えていない (`git diff c3ee6daa7 HEAD -- tools/gui tools/m11 ':(exclude)tools/gui/flengine/REPORT*.md'` は空)。`bash tools/gui/flengine/e2e.sh` を foreground で 1 回実行 (`FL_WIN64_DIR` = fl-win64 展開先、`EMSDK_ENV=[EMSDK] の emsdk_env.sh`、`RETDEC=[RETDEC] の retdec-decompiler`、`TMPDIR=$RUNNER_TEMP`。素材は fl-win64・work-m11・toolchain-emsdk・toolchain-retdec、`gcc-mingw-w64-x86-64` は apt で導入)。

修正 commit では e2e を再実行していない (work-m11・toolchain-emsdk・toolchain-retdec の素材が、修正時の runner に無い)。下表と以下の値は実行時の記録で、e2e の生成物 (`results/` の再生成分と unit 別出力) は commit していないため、残っていない。

| 項目 | 結果 |
|---|---|
| e2e | rc 1 / 322 s / load 1.15 → 1.03 |
| judge | **12/14** (FAIL は **B1** と **S1**) |
| B1 boot parity | FAIL。詳細は下の B1 節 |
| S1 survey parity (soft) | FAIL。soft `873/1/47/21/0` vs base `871/1/47/23/0` |
| 他 gate | L1 (ff・soft) PASS・A1 declare=193 adapter=193 impl=173 stub=20・R1 `LoadStringW`・R2 reach 33 ≥ 19・S2 PASS (soft fail-fast 無し)・P1 (RegisterClassW=3 CreateWindowExW=3)・P2・P3・P4 hwnd `0x1100010`・P5 hwnd `0x110000f`・W1 WNDCLASS 11 / fn WNDPROC 8 |
| ネガコン | N1〜N9 期待どおり FAIL (9/9) |
| native selftest | 506 passed / 0 failed |
| `__pe_image` parity (4b) | PASS |

### B1 (本 run で FAIL)

judge の B1 (`judge.py` 39〜41 行) は boot と baseline の `units_run`・`dllmain_done`・`init_count`・`GetMem`・`FreeMem`・`icall_miss`・`boot_failfast`・`boot_threw` を全て等しさで比べる。判定式は変えていない。

| 判定項目 | 本 run の boot | 本 run の base | 既存記録 (boot / baseline。committed `results/boot.json` と `results/baseline_boot.json`、測定 commit `c3ee6daa7` の内容) |
|---|---|---|---|
| `units_run` | 109 | 109 | 52 / 52 |
| `init_count` | 未記録 | 未記録 | 54 / 54 |
| `dllmain_done` | False | 未記録 | False / False |
| `icall_miss` | **6** | **7** | 5 / 5 |
| `GetMem` | 707 | 未記録 | 560 / 560 |
| `FreeMem` | 20 | 未記録 | 20 / 20 |
| `boot_threw` / `threw` | 未記録 | 未記録 | unreachable / unreachable |

- **数字から確認できる不一致は `icall_miss` (6 ≠ 7) の 1 項目**。他の項目は base 値を記録していないため、一致・不一致は判定できない。B1 の FAIL 要因の全体は未確定。
- 初版の「`dllmain_done` が baseline は `True`」は根拠が無く、既存記録とも合わないため取り下げる。既存の baseline も `dllmain_done False` である (`baseline_boot.json`)。REPORT §6c-2 (HEAD `b3819e2`) も `dllmain_done false` を記録している。
- **既存記録からの変化**: 本 run は boot と base の両方で `units_run` が 52 から 109 に変わった (REPORT §6h は 52、§6c 冒頭は HEAD `19ebb43` の 22)。boot と base が同時に動いているため、shim 結合ではなく m11 baseline 側 (素材・生成手順) の変化と読む (推定)。109 の由来は未確認。
- **同じ FAIL の既存記録**: REPORT §6c-2 (HEAD `b3819e2`) は B1 を `units_run 52 (base 52) / dllmain_done False / GetMem 560 FreeMem 20 / icall_miss 5` で FAIL と記録し、素材 `work-m11` の世代差と推定している (未確認)。本 run の値 (units 109・icall 6/7・GetMem 707) は、これとも一致しない。

### S1 (unit 差の特定。#1442 で扱った unit 集合の再測定)

本 run の S1: soft `873/1/47/21/0` vs base `871/1/47/23/0`。soft 2 回・base 2 回の unit 別突き合わせ (手順は末尾) で、差は **unit 304 と 555 の 2 件のみ** (base は `memory access out of bounds` の trap、soft は ok)。ok/trap 以外の差は無い。S1 の `+2 / -2` はこの 2 件で説明される。

- **受入条件 1 の「特定」は新規の特定ではない**。既存の REPORT_APPENDIX.md §6i (#1442 で扱った unit 集合) は、差を **101 / 291 / 296 の 3 unit** (base のみ trap、soft ok。unit 別突き合わせの測定 commit `549e6817` の時点) と記録し、304・555 は base・soft とも OOB と記録している。本 run の 304・555 は、この既存の unit 集合の再測定に当たる。
- **既存記録と違う理由は未確認**。候補は (a) 測定 commit (`719f1c43` から `c3ee6daa7` の間で `tools/gui`・`tools/m11` の非文書 203 ファイルが変わっている)、(b) 素材 (work-m11 の世代)、(c) baseline の再生成 (committed `results/baseline_survey.json` は `870/1/47/24/0`、本 run の base は `871/1/47/23/0`)。どれが効いたかは切り分けていない。
- **向きの反転**: 304・555 の base/soft のどちらが OOB かは測定ごとに入れ替わった記録がある。REPORT_APPENDIX.md §7-7 (測定 commit `5f9d7cbd`、boot7 の有無の 2 run) が該当し、§6i には反転の記録は無い。順序依存と読むのは推定 (§7-7 と同じ)。
- 真因 (304・555 の OOB の実アドレスと命令) は未採取 (#1426)。判定式は変えていない。S1 の gate は FAIL のまま。

### 再測の手順と出力 (unit 別。soft・base 各 2 回)

`$GF_W` は `tools/gui/work/flengine` (`env.sh` の既定。gitignore)。`bash tools/gui/flengine/build.sh --soft` と `bash tools/gui/flengine/build.sh --base` で `$GF_W/m11_gui_soft.cjs`・`$GF_W/m11_base.cjs` を作ってから、各 2 回次を実行する: `GF_SURVEY_UNITS=$GF_W/res/<名前>_units.json node tools/gui/flengine/run.mjs --survey --wasm $GF_W/<m11_gui_soft または m11_base>.cjs --out $GF_W/res/<名前>.json`。`run.mjs` は `GF_SURVEY_UNITS` が指定されると unit 別の `[i, ok|trap, kind]` を書く (soft の形は e2e.sh の 53 行と同じ。base の 39 行には環境変数が無いので、単独再測では付ける)。942 unit の unit 別出力 (`*_units.json`) は gitignore の `tools/gui/work/` にあり、コミットしていない。

### 製品 KPI (起動・GUI)

コード変更なし。前後は同値。`units_run` は PR 作成時の run で 109 (base 109)。前回記録 (52 / 22) との違いは上の B1 節のとおり未確認。最初の GUI API は `LoadStringW` (自然到達)。自然起動の `RegisterClassW`/`CreateWindowExW` 到達は INFO 行のとおり (直接 probe で `TApplication` と `TLightweightLayeredControl` の窓 (P4/P5) が生成される)。

### 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| S1 の unit 304・555 の OOB の真因 (実アドレス・命令) | judge S1 FAIL。JUDGE 14/14 の未達 | #1426 (OPEN) |
| 既存の 101/291/296 (§6i) と本 run の 304/555 の食い違いの原因 (測定 commit・素材・baseline 再生成のどれか) | S1 の unit 集合が測定ごとに変わる | #1635 (OPEN、Refs #1442) |
| B1 の base 値の未記録 (`init_count`・`dllmain_done`・`GetMem`・`FreeMem`・`threw`)、`units_run 109` の由来、`icall_miss 6 ≠ 7` | judge B1 FAIL。JUDGE 14/14 の未達 | #3352 (本 issue に残す。次の再測で全項目を記録) |
| `tools/gui/flengine/REPORT.md` 479 行 (上限 250 行。`c3ee6daa7` の時点で超過済み) | DOC_MAP §1 の行数上限。本 PR は REPORT.md を変更しない | PM 起票依頼 (超過分の分割移動) |
