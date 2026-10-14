# REPORT N1479 — xmm 引数を読む callee の署名復元: 現 HEAD での unit 別 A/B (#1479, 親 #1430)

既知類型との関係: D5 (`docs/DEFECTS.md`、既知 (F2): xmm 引数の落ち) の対処「引数追加 (f2)」を m11 の IR に適用したもの。方式は #954 (`REPORT_N54.md`) と #2762 (`REPORT_N154.md`) で実装済み。新規類型は無し。

## 1. 結論

- 方式は既存の opt-in `M11_XMM_ARGS=1` (`tools/plugins/lift/passes/fix_xmm_args.py`, #547) を採用する。既定 OFF は変えない。既定を ON にするかは §7 の判断待ち。
- 測定 commit `e244259e` で、同一 IR・同一 PE の既定 (0) と opt-in (1) を unit 別 942 本で比較した。**unit 別差 0 件・ok 喪失 0 件・unit 838/882/885 は両 arm とも ok**。
- **未完**: 両 arm の IR (`boot_final3.ll`) と survey JSON の sha256 は未記録。fix commit `2bbad8ff` で `m11_xmm_ab.sh` にその出力を足したが、この変更は未測定 (素材 `work-m11`・`toolchain-emsdk` が本 run に無く再測定できなかった)。§3・§7。
- 基準 `7e149974` の全再生成との直接比較は未実施 (§5)。0 詰め 7 カテゴリの和の実測は #1532 (`392d8ba5`) で済み、1,172→1,185 の原因 commit は未特定 (§6)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 測定 commit | `e244259e` (A/B スクリプトの最後のコード変更 commit。前 commit `35b0ad0a` の前提コメントを修正)。コミット済み HEAD で再実行し同じ結果 |
| IR | `$ARTIFACTS_DIR/work-m11` の `tools/m11/work/boot_final.ll` (生成 commit 不明)。展開直後の sha256 `69c774de…` (N54 の指紋と一致)。build の qstore・alloca 適用後の `ir_sha256` は `666ce8fb…` |
| 条件記録 | `work/ir_conditions.json` は同梱されていない。N54・N154 と同じく手で記録した (正規の生成経路ではない)。手順 1 行: `cd tools/m11 && python3 m11_cond.py pe="$FL_WIN64_DIR/extracted/block00031_PE.bin" ldfix=applied ld108=applied && python3 m11_cond.py --bind work/boot_final.ll`。この行は `m11_cond.py` の CLI と `m11_build.sh` の検査項目から導いたもので、測定時の実コマンドの記録は無い。次の再測定で本行を実行して確認する |
| PE | fl-win64 `extracted/block00031_PE.bin` (sha256 `b2c64da4…` 一致) |
| 実行環境 | 4 vCPU、load 0.16 (開始時 `uptime`)、node・capstone・pefile 入り venv |

## 3. 測定値 (測定 commit `e244259e`, `bash tools/m11/m11_xmm_ab.sh`)

| 測定 | 既定 (`M11_XMM_ARGS=0`) | opt-in (`=1`) |
|---|---|---|
| build (単発) | 17 s (rc 0) | 36 s (rc 0) |
| survey (unit 別 JSON, 単発) | 8 s (rc 0) | 8 s (rc 0) |
| ok / trap / miss / noproc / oom (unit 別ラベル) | 869 / 24 / 47 / 1 / 1 | 869 / 24 / 47 / 1 / 1 |
| survey 集計 (trap は oom を含む 25) | ok 869 / noproc 1 / miss 47 / trap 25 | 同左 |
| 復元 (`xmm_args_report.json`) | — | fixed 39 / skipped 713 / callsite_zero_args 86 |
| unit 別差 (942 本) | — | **0 件** |
| ok 喪失 (ok→非 ok) / ok 獲得 | — | **0 件 / 0 件** |
| unit 838 / 882 / 885 | ok / ok / ok | ok / ok / ok |

- 判定の機械化: `tools/m11/m11_xmm_ab.sh` が ok 喪失または watch unit (838/882/885) の非 ok で終了 1 にする。判定器は、unit 838 を ok→trap に改変した写しで FAIL を検出することを毎回確認する (`[negctl]` 行)。
- **IR の差の証拠は未記録**: 旧版の「unit 別 JSON の sha256 が両 arm で一致」は値が無くスクリプトも計算していなかったため撤回する。`2bbad8ff` の `m11_xmm_ab.sh` は各 arm の `work/boot_final3.ll` と survey JSON の sha256 を `work/xmm_ab/ir_sha256_{0,1}.txt`・`survey_sha256_{0,1}.txt` へ出力し、両 arm の IR が同一なら終了 2 で止める。この版の実測値は無い。ダミー入力での動作確認 (IR 差ありで通常判定に進む・IR 同一で終了 2) のみ済み。
- 所要時間は判定に使わない。n=1 で、min–max 規則 (`docs/WORKFLOW.md` §5) を満たさない。表の build・survey の秒数と「スクリプト全体 1 分 7 秒」(67 s、rc 0) は、出典 run が本 REPORT に記録されていない。内訳の和 69 s は合計 67 s を超える。
- 同一 IR の絶対値は commit によって動く。絶対値の比較は §5 にまとめる。**有効な比較は同一 commit 内の A/B だけ**。

## 4. 差分と再現

- 測定 commit `e244259e` から HEAD までの tools/m11 のコード差分 (本 REPORT を除く)。`git diff --stat e244259e HEAD -- tools/m11 ':!tools/m11/REPORT_N1479.md'` の出力:

  ```
  tools/m11/m11_xmm_ab.sh | 8 ++++++++
  1 file changed, 8 insertions(+)
  ```

  差分は `2bbad8ff` の sha256 出力と IR 不変の判定 (8 行追加) で、測定は未実施。差分 0 ではないため、この版の A/B は再測定まで有効と言えない (§7)。
- 再現: `export FL_WIN64_DIR=<fl-win64 展開先> PATH="<capstone・pefile 入り venv の bin>:$PATH"; cd tools/m11 && bash m11_xmm_ab.sh`。前提: `work/boot_final.ll`・`work/ir_conditions.json` (§2 の手順)・emsdk (`[EMSDK]`)。素材は PR 本文の `oc_artifacts: fl-win64 toolchain-emsdk work-m11`。出力は `work/xmm_ab/`。

## 5. 比較の数値 (本 REPORT で再掲するのはここだけ)

| 値 | 内容 | 出典 |
|---|---|---|
| ok 869 / 871 / 869 | 同一 IR の既定 (0) の ok 数。commit 98c2183 / 0ea7df21 / e244259e の順 | `REPORT_N54.md` 表 1 / `REPORT_N154.md` 表 1 / 本 §3 |
| ok 872 / trap 23 / miss 46 / noproc 1 | 基準 `7e149974` の全再生成 IR の survey | `REPORT_APPENDIX_1430.md` |
| 0 詰め site 1,049 / 引数 2,064 | 本 A/B の IR (`7e149974` の work-m11 由来) | `REPORT_N1702.md` |
| 0 詰め site 1,061 / 引数 2,084 | 全再生成 `392d8ba5` | `REPORT_N1532.md` |
| 0 詰め 7 カテゴリの和 1,963 → 1,983 (+20) | 1,963 は `7e149974` の work-m11 由来、1,983 は `392d8ba5` の全再生成 | `REPORT_N1532.md` §4 |
| inherit 1,172 → 1,185 (+13) | 7 カテゴリの内訳の 1 つ | `REPORT_N1532.md` §4 |

- 基準との直接比較は未実施。本 A/B の IR は基準 IR (`7e149974` 全再生成) と別物のため、参考差 (ok −3 / trap+oom +2 / miss +1) は**退行の判定には使わない**。
- 全再生成の所要 (`REPORT_APPENDIX_1430.md`): `m11_e2e.sh --full` 626.99 秒 (10 分 27 秒、`7e149974`、rc 0、load 0.68)。Ghidra 12.1.4 による `functions_dll.csv` の再生成 577 秒 (9 分 37 秒)。`REPORT_N1997.md` が引く 649 秒は `REPORT_N1702.md` の別 run の値で、本 REPORT の値ではない。
- 全再生成は本 PR では行わない。`work-m11` は `functions_dll.csv`・`lift_pe.sha256`・`ir_conditions.json` を含まず、Ghidra・JDK・emsdk の用意が要る。本 run の素材にはそれが無い (§7)。

## 6. 1,172→1,185 / 48→49 の原因と 3 カテゴリ

- 7 カテゴリの実測は `REPORT_N1532.md` §4 (`392d8ba5`)。和と内訳の値は §5。`7e149974` の全再生成値は未測定。
- 原因 commit は未特定。`REPORT_N1904.md` で `m11_post.py` (sigfix 段) は犯人でないと切り分け済み。残りは関数の発見・リフト範囲 (lift 段より上流) で、特定には commit ごとの全再生成 (§5 の 626.99 秒) を複数回回す必要がある。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| **B3 の再測定**: 両 arm の `boot_final3.ll`・survey JSON の sha256 の値 (`2bbad8ff` の出力)、および測定 commit の更新 | IR が arm 間で変わったことと、unit 別差 0 が空振りでないことの証拠が無い。§4 の差分は未測定 | 本 PR の次の実行で再測定 (素材 `oc_artifacts: fl-win64 toolchain-emsdk work-m11` が要る)。再測定だけの子は起票しない |
| `7e149974` 全再生成 IR による基準 JSON (unit 別) と本 A/B の対応付け | 基準 (§5) との unit 別対応が未確認。本 A/B は同一 IR 内の判定 | #1479 の全再生成と同時 (PM 判断) |
| 1,172→1,185 / 48→49 の原因 commit (0 詰め 7 カテゴリ和の増分、§5) | 旧 1,963 と新 1,983 の差の説明が無い | 既存 issue `#1904` [M11-N125] と `#1702` [M11-N117] (両方 CLOSED・残件は `REPORT_N1904.md` §6。その子 `#1997` [M11-N131] も CLOSED)。再測定だけの子は起票しない |
| `work/ir_conditions.json` の `pe`・`ldfix`・`ld108` を手で記録 / work-m11 の生成 commit 不明 | 絶対値の IR 条件が未確認 (同一 IR 内の A/B の判定には影響しない) | #1479 の全再生成と同時 (PM 判断) |
| 既定を ON にするか | 既定 OFF のまま。ON の survey は unit 別差 0 だが、起動 KPI は未測定 | PM agent の判断待ち: 既定を ON にするか・既定案: OFF 維持 |

KPI (`docs/WORKFLOW.md`・AGENTS 路線 2): 本 PR は m11 の survey 判定のみで、起動経路 (`tools/flelift`・`tools/m11` の既定) は変えない。起動 KPI (dispatch 数・通過 unit 数・最初のウィンドウ) は**動かしていない**。
