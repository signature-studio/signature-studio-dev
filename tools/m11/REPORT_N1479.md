# REPORT N1479 — xmm 引数を読む callee の署名復元: 現 HEAD での unit 別 A/B (#1479, 親 #1430)

既知類型との関係: D5 (`docs/DEFECTS.md`、既知 (F2): xmm 引数の落ち) の対処「引数追加 (f2)」を m11 の IR に適用したもの。方式は #954 (`REPORT_N54.md`) と #2762 (`REPORT_N154.md`) で実装済み。新規類型は無し。

## 1. 結論

- 方式は既存の opt-in `M11_XMM_ARGS=1` (`tools/plugins/lift/passes/fix_xmm_args.py`, #547) を採用する。既定 OFF は変えない (既定を ON にするかは PM 判断。§7)。
- 測定 commit `e244259e` (測定時の HEAD) で、同一 IR・同一 PE の既定 (0) と opt-in (1) を unit 別 942 本で比較した。**unit 別差 0 件・ok 喪失 0 件・unit 838/882/885 は両 arm とも ok**。
- 基準 `7e149974` の全再生成 (ok 872 / trap 23 / miss 46 / noproc 1) との直接比較は**未実施**。素材の IR が別物で、全再生成には Ghidra 込みの再生成が要る (§5)。
- 0 詰め 7 カテゴリの和 1,983 は #1532 (`392d8ba5`) で実測済み。1,172→1,185 の原因 commit は未特定 (§6)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `e244259e` (A/B スクリプトの最後のコード変更 commit。前 commit `35b0ad0a` の前提コメントを修正)。コミット済み HEAD で再実行し同じ結果 |
| IR | `$ARTIFACTS_DIR/work-m11` の `tools/m11/work/boot_final.ll` (生成 commit 不明)。展開直後の sha256 `69c774de…` (N54 の指紋と一致)。build の qstore・alloca 適用後の `ir_sha256` は `666ce8fb…` |
| 条件記録 | `work/ir_conditions.json` は同梱されていないため、`pe`・`ldfix=applied`・`ld108=applied` を手で記録して `--bind` した (N54・N154 と同じ扱い。正規の生成経路ではない) |
| PE | fl-win64 `extracted/block00031_PE.bin` (sha256 `b2c64da4…` 一致) |
| 実行環境 | 4 vCPU、load 0.16 (開始時 `uptime`)、node・capstone・pefile 入り venv |

## 3. 測定値 (HEAD `e244259e`, `bash tools/m11/m11_xmm_ab.sh`)

| 測定 | 既定 (`M11_XMM_ARGS=0`) | opt-in (`=1`) |
|---|---|---|
| build (単発) | 17 s (rc 0) | 36 s (rc 0) |
| survey (unit 別 JSON, 単発) | 8 s (rc 0) | 8 s (rc 0) |
| ok / trap / miss / noproc / oom (unit 別ラベル) | 869 / 24 / 47 / 1 / 1 | 869 / 24 / 47 / 1 / 1 |
| survey 集計 (trap は oom を含む 25) | ok 869 / noproc 1 / miss 47 / trap 25 | 同左 |
| 復元 (`xmm_args_report.json`) | — | fixed 39 / skipped 713 / callsite_zero_args 86 |
| unit 別差 (942 本) | — | **0 件** (unit 別 JSON の sha256 が両 arm で一致) |
| ok 喪失 (ok→非 ok) / ok 獲得 | — | **0 件 / 0 件** |
| unit 838 / 882 / 885 | ok / ok / ok | ok / ok / ok |

- 判定の機械化: `tools/m11/m11_xmm_ab.sh` が ok 喪失または watch unit (838/882/885) の非 ok で終了 1 にする。判定器は、unit 838 を ok→trap に改変した写しで FAIL を検出することを毎回確認する (`[negctl]` 行)。
- 所要時間: スクリプト全体 1 分 7 秒 (rc 0、n=1)。HEAD での再実行も同じ結果 (survey の unit 別 JSON が byte 一致)。
- 同一 IR の絶対値は commit によって動く。本 IR では 869 (N54 表 1、98c2183) / 871 (N154 表 1、0ea7df21) / 869 (本 REPORT、e244259e) で、絶対値の比較は意味が無い。**有効な比較は同一 commit 内の A/B だけ**。

## 4. 差分と再現

- 測定 commit `e244259e` から HEAD までの tools/m11 のコード差分 (本 REPORT を除く): `git diff --stat e244259e HEAD -- tools/m11 ':!tools/m11/REPORT_N1479.md'` は出力 0 件。
- 再現: `export FL_WIN64_DIR=<fl-win64 展開先> PATH="$HOME/.local/agent-py/bin:$PATH"; cd tools/m11 && bash m11_xmm_ab.sh` (前提: `work/boot_final.ll`・`work/ir_conditions.json`・emsdk (`[EMSDK]`))。出力は `work/xmm_ab/`。

## 5. 基準 (`7e149974` 全再生成) との関係 (未実施)

- 基準値 ok 872 / trap 23 / miss 46 / noproc 1 (`REPORT_APPENDIX_1430.md`) は全再生成 IR の値。本 A/B の IR は別物 (0 詰め site 1,049。全再生成の `392d8ba5` は 1,061・`REPORT_N1532.md`)。参考として差を書くと ok −3 / trap+oom +2 / miss +1 だが、IR が違うため**退行の判定には使わない**。
- 全再生成 (`m11_e2e.sh --full` 約 650 s + `functions_dll.csv` の Ghidra 12.1.4 再生成 約 620 s) は 1 run の上限内に両方を収められないため本 PR では行わない。

## 6. 1,172→1,185 / 48→49 の原因と 3 カテゴリ

- 7 カテゴリの実測は `REPORT_N1532.md` §4 (`392d8ba5`): set_other 384・stack_set_other 32・callee_nopdata 2 を含む 7 カテゴリの和 1,983 (1,963 から +20)。`7e149974` の全再生成値は未測定。
- 原因 commit は未特定。`REPORT_N1904.md` で `m11_post.py` (sigfix 段) は犯人でないと切り分け済み。残りは関数の発見・リフト範囲 (lift 段より上流) で、特定には commit ごとの全再生成 (約 650 s) を複数回回す必要がある。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `7e149974` 全再生成 IR による基準 JSON (unit 別) と本 A/B の対応付け | 基準 872 との unit 別対応が未確認。本 A/B は同一 IR 内の判定 | 未起票 (再測定のみ・Ghidra 込みで 1 run 外。PM 判断) |
| 1,172→1,185 / 48→49 の原因 commit (`392d8ba5` 系の段の特定) | 0 詰め 1,983 の増分の説明が無い | 未起票 (commit ごとの全再生成の二分探索。`REPORT_N1904.md` §6 の残り。PM 判断) |
| 既定を ON にするか | 既定 OFF のまま。ON の survey は unit 別差 0 だが、起動 KPI は未測定 | PM 判断 (既定案: OFF 維持) |
| `work/ir_conditions.json` の `pe`・`ldfix`・`ld108` を手で記録 / work-m11 の生成 commit 不明 | 絶対値の IR 条件が未確認 (同一 IR 内の A/B の判定には影響しない) | 全再生成 (上の基準と同時) で解消 |

KPI (`docs/WORKFLOW.md`・AGENTS 路線 2): 本 PR は m11 の survey 判定のみで、起動経路 (`tools/flelift`・`tools/m11` の既定) は変えない。起動 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) は**動かしていない**。
