# REPORT_1157 — ClassCreate ON の unit 85/719 退行の二分探索: 前提の実測 (#1157, 親 #595)

結論: 基点 `5ff73ff` の ON で unit 85 / 719 は**退行しなかった**。issue 本文の前提 (「#446 基点で 85/719 が ok 退行していた」) は実測と合わない。判定基準が定まらないため、2381 commit の二分探索は本 run では実行していない。基点 `5ff73ff` の ON 退行は 15 42 45 138 415 の 5 件で、REPORT_595 §1 の旧ベース表と一致する。**PM の判断が必要**: (a) 退行対象を 15 42 45 138 415 に差し替えて探索するか、(b) 85/719 を対象から外して #595 の受入条件 1 を閉じるか。

測定 commit: 現 main `711b58ca` (`origin/main`、本 branch の基点) と基点 `5ff73ff`。本 PR はコードを変えない (本ファイルの追加のみ)。

## 1. 測定 (単発・並列数 1・逐次実行)

手順: `bash tools/m11/m11_gen_ir2.sh` → `bash tools/m11/m11_build.sh` (`M11_OV_CLASSCREATE=0/1`) → `node tools/m11/trap_triage/survey_units.mjs out.json` → `python3 tools/m11/trap_triage/survey_diff.py a.json b.json`。素材: fl-win64 / toolchain-retdec / toolchain-emsdk / work-m11。

| 構成 | コード | ok | oob | halt0 | miss | noproc | other/abort | ok 退行 |
|---|---|--:|--:|--:|--:|--:|--:|---|
| 既定 OFF | `5ff73ff` | 818 | 21 | 56 | 46 | 1 | — | — |
| ON | `5ff73ff` | 813 | 23 | 55 | 50 | 1 | — | 5: 15 42 45 138 415 |
| 既定 OFF | `711b58ca` | 870 | 16 | 7 | 47 | 1 | other 1 | — |
| ON | `711b58ca` | 869 | 15 | 7 | 47 | 1 | other 1, abort 2 | 1: 190 |

基点 `5ff73ff` の OFF / ON は REPORT_595 §1 旧ベース表 (OFF 818/21/56/46/1、ON 813/23/55/50/1、退行 15 42 45 138 415) と完全に一致した。現 main の値は REPORT_595 §5 (OFF 869/16/8/47/1/1) と ok/halt0 が 1 ずつ異なる。IR 再生成の差 (sha は `ir_conditions.json` の `ir_sha256` で確認) の可能性があるが、本 run では切り分けていない。

### 1.1 unit 85 / 719 / 114 の kind (unit 単位)

| 構成 | 85 | 719 | 114 |
|---|---|---|---|
| 基点 `5ff73ff` OFF | ok | halt0 | halt0 |
| 基点 `5ff73ff` ON | ok | halt0 | halt0 |
| 現 main `711b58ca` OFF | ok | ok | halt0 |
| 現 main `711b58ca` ON | ok | ok | halt0 |

- 基点で 85 は OFF/ON とも ok、719 は OFF/ON とも halt0。ON で ok→非 ok になる変化は無い。
- 現 main で 719 は OFF/ON とも ok。REPORT_595 §3 は「OFF halt0」と書いていたが、本 run の OFF は ok。ここも IR 再生成の差と思われるが切り分けていない。
- unit 114 は基点・現 main とも OFF/ON で halt0 (ハングではない)。

## 2. 前提が崩れた経緯 (判断材料)

- issue #1157 は「#446 基点 (`5ff73ff` 系) で unit 85/719 の ok 退行があった」を前提とする。REPORT_419 §遷移 は「ok→oob 2 (85 719)」と記録しており、この記録が前提の出所と思われる。ただし REPORT_419 の時点は `8cbda0/8cbce0` を ON にした別構成の値。
- `5ff73ff` の ON では 85/719 の kind が変わらない。`5ff73ff` の ON は REPORT_595 §1 の旧ベースと同じ構成で、退行 5 件は 15 42 45 138 415。
- REPORT_595 §3 も「85/719 は #446 の古い tree (#474/#503 前) での値」と記録している。二分探索の始点 (`5ff73ff`) が前提の退行を再現しないため、どの commit で「解消」したかを判定する基準が無い。

## 3. 再現の注意 (本 run で判明した環境上の点)

- `m11_gen_ir2.sh` の 34 行目 `PE=/home/ubuntu/work/analysis/win64/extracted/block00031_PE.bin` は `FL_WIN64_DIR` を見ない。CI の runner では `/home/ubuntu` が無いため ldfix が skip され、`ir_conditions.json` が `ldfix=applied` と書かれたまま未適用の IR になる (`WARNING: ldfix skip` が出る)。本 run では `5ff73ff` の IR 生成で実際にこの状態になり、PE パスを差し替えた一時コピー (`m11_gen_ir2_ci.sh`、commit していない) で再生成した。`ir_sha256` は `16d1bae6…` で ldfix 適用済みの値。**gen スクリプトの PE 解決を `M11_PE`/`FL_WIN64_DIR` 優先にする修正は別 issue で扱うべき** (本 PR では変更していない)。
- `/opt/emsdk` `/opt/retdec` は展開先の symlink で用意した。emsdk は `emsdk_env.sh` 経由だと `emcc` が PATH に乗らず、`upstream/emscripten` と `upstream/bin` と `node/24.19.0_64bit/bin` を直接 PATH に通して解決した。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 二分探索の判定基準 (対象 unit と始点) が未確定。現在の前提は基点で再現しない | #1157 の受入条件 1・2 が達成できない | PM 判断 (#1157 にコメント) |
| 現 main の 719 OFF が REPORT_595 §3 (halt0) と食い違う (本 run は ok) | IR 再生成の差の切り分け未了 | #595 (Refs) |
| `m11_gen_ir2.sh` の PE 固定パス (`/home/ubuntu`) で ldfix が skip する | CI で IR 条件が静かに変わる | PM 判断 (新規 issue を要望) |
