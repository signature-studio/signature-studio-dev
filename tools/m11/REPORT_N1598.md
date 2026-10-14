# REPORT_N1598 — #1598 (M11-N104): m11_e2e.sh 既定経路の再通し (Ghidra 再生成 functions_dll.csv)

既知類型との関係: DEFECTS.md の類型は新規確定しない。該当なし。

## 1. 結論
- 受入 (1) Ghidra 12.1.4 取得と sha256 確認 → `functions_dll.csv` 作成: **達成**。59,010 行・sha256 `90d1bbac…`。
- 受入 (2) HEAD で `m11_e2e.sh` 既定経路を rc 0 まで通す: **達成**。rc 0・623 秒。judge rc 0 (reached_stage 4 ≥ 4・survey_ok 872 ≥ 800)。
- 受入 (3) 測定 commit と `git diff` を添付: **達成** (§2・§6)。
- 受入 (4) 作れない場合の理由: 該当なし (作成できた)。

## 2. 測定の条件
- 測定 commit: `4c3f7458` (origin/main、Merge PR #1781)。コード変更なし。本 PR は本 REPORT の追加のみ。
- ブランチ・worktree: `1598-m11-n104-e2e-ghidra` / `ws-1598`。
- 素材: `work-m11`・`work-liftdiff` を worktree の `tools/m11/work/`・`tools/liftdiff/work/` に展開 (gitignore)。`fl-win64` は `extracted/block00031_PE.bin` (sha256 `b2c64da4…`・REPORT_N1415 と一致) を `$RUNNER_TEMP/fl-win64` に展開して `FL_WIN64_DIR` に指定。`toolchain-retdec`・`toolchain-emsdk` は `[RETDEC]`・`[EMSDK]` が既に存在したためそのまま使用。
- Ghidra: 公式 release `ghidra_12.1.4_PUBLIC_20260921.zip` を取得し sha256 `ddac49f9…` 一致を確認。JDK は Temurin 21 (JDK 21)。`MAXMEM=8G`。
- 環境: 4 vCPU, 15 GiB。実行開始時 load average 0.20 (1 分平均)・終了後 0.01。
- Python: capstone / pefile 導入済み (ldfix が有効)。

## 3. Ghidra 再生成 (`functions_dll.csv`)
| 項目 | 値 |
|---|---|
| コマンド | `analyzeHeadless <proj> dll_proj -import block00031_PE.bin -scriptPath tools/m2/ghidra_scripts -postScript DumpFunctions.java <out.csv>` |
| rc | 0 |
| 所要 | 611 秒 |
| 出力 | `tools/m2/work/ghidra_dll/functions_dll.csv` 59,010 行 (REPORT_N1532 の 59,010 と一致) |
| sha256 | `90d1bbac…` (REPORT_N27・N1042 と一致) |

## 4. `m11_e2e.sh` 既定経路 (HEAD = 4c3f7458)
実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_e2e.sh` (既定・`--full` 無し)

| 段 | 結果 |
|---|---|
| 全再生成モード (`lift_pe.sha256` 無し → 全再生成) | 入り、以降すべて ok |
| m11_bounds | ok (`functions_dll.csv` を読めた) |
| lift 4 chunks (RetDec) / m11_tail 固定点 #1〜#3 / lift boot4 / gen_ir2 | 全 ok |
| lift boot5 (RetDec) / gen_ir2 (boot5 追加) | ok |
| m11_data_gen / m11_image_gen / lb_check / build (emcc) | ok |
| 実行 A (通常起動) / 実行 B (unit survey) | 実行 |
| judge (`--require-stage 4 --min-survey-ok 850` 相当) | rc 0 |

- 所要: **623 秒** (全体 `timeout 1500` 内)。rc: **0**。PASS/FAIL: **PASS** (judge の期待値 `e2e_expect.env`: stage 4・survey_ok 800 以上を満たす)。
- M11_SUMMARY (抜粋): `reached_stage` 4 / `stop_reason` `trap "unreachable" @ function_8c5eb0 <- ...` / `ir_conditions`: `ldfix` applied・`qstore` applied・`ir_sha256` `951e5b5d…` / `units_run_full` 53 / `survey_ok` 872 / `survey_trap` 23 / `survey_miss` 46 / `wasm_bytes` 6,043,394。
- 注: trap (stage 4 で停止) は REPORT_N27 §12・N1415 と同じ既知の停止で、本 run で解消していない。判定の PASS は回帰ゲート (stage ≥ 4・survey_ok ≥ 800) の通過であり、lift 成果物の正しさの判定ではない。
- 注: `ir_sha256` `951e5b5d…` は過去記録との比較を本 run では行っていない。REPORT_N27 §12 で IR sha が実行ごとに変わる件は未切り分けのまま。本 run の値は参照用に残すのみ。

## 5. 検証範囲 / 範囲外
- 範囲: 本 runner の 1 ホスト・PE 1 member・n=1 (再現性の反復は未実施)。
- 範囲外: trap の解消 (stage 4 → 5 以上)・IR sha の実行間変動の切り分け・survey 値の基準比較。

## 6. コード差分 (測定 commit → HEAD)
- 測定 commit `4c3f7458` から HEAD までのコード変更はない。本 PR で追加するのは本 REPORT と `docs/DOC_MAP.md` の索引 1 行のみ。
- 本節の実出力は測定対象の HEAD `f97600d3` (参照名修正 commit・本節追加前) で取得した。本節を追加した後の HEAD では `tools/m11` の差分が本節分だけ増えるため、再取得すると本節の出力と一致しない。
- `git diff --stat 4c3f7458 f97600d3 -- tools/m11`:

```
 tools/m11/REPORT_N1598.md | 58 +++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 58 insertions(+)
```

- `git diff 4c3f7458 f97600d3 -- tools/m11`:

```diff
diff --git a/tools/m11/REPORT_N1598.md b/tools/m11/REPORT_N1598.md
new file mode 100644
index 00000000..36e266eb
--- /dev/null
+++ b/tools/m11/REPORT_N1598.md
@@ -0,0 +1,58 @@
+# REPORT_N1598 — #1598 (M11-N104): m11_e2e.sh 既定経路の再通し (Ghidra 再生成 functions_dll.csv)
+
+既知類型との関係: DEFECTS.md の類型は新規確定しない。該当なし。
+
+## 1. 結論
+- 受入 (1) Ghidra 12.1.4 取得と sha256 確認 → `functions_dll.csv` 作成: **達成**。59,010 行・sha256 `90d1bbac…`。
+- 受入 (2) HEAD で `m11_e2e.sh` 既定経路を rc 0 まで通す: **達成**。rc 0・623 秒。judge rc 0 (reached_stage 4 ≥ 4・survey_ok 872 ≥ 800)。
+- 受入 (3) 測定 commit と `git diff` を添付: **達成** (§2・§6)。
+- 受入 (4) 作れない場合の理由: 該当なし (作成できた)。
+
+## 2. 測定の条件
+- 測定 commit: `4c3f7458` (origin/main、Merge PR #1781)。コード変更なし。本 PR は本 REPORT の追加のみ。
+- ブランチ・worktree: `1598-m11-n104-e2e-ghidra` / `ws-1598`。
+- 素材: `work-m11`・`work-liftdiff` を worktree の `tools/m11/work/`・`tools/liftdiff/work/` に展開 (gitignore)。`fl-win64` は `extracted/block00031_PE.bin` (sha256 `b2c64da4…`・REPORT_N1415 と一致) を `$RUNNER_TEMP/fl-win64` に展開して `FL_WIN64_DIR` に指定。`toolchain-retdec`・`toolchain-emsdk` は `[RETDEC]`・`[EMSDK]` が既に存在したためそのまま使用。
+- Ghidra: 公式 release `ghidra_12.1.4_PUBLIC_20260921.zip` を取得し sha256 `ddac49f9…` 一致を確認。JDK は Temurin 21 (JDK 21)。`MAXMEM=8G`。
+- 環境: 4 vCPU, 15 GiB。実行開始時 load average 0.20 (1 分平均)・終了後 0.01。
+- Python: capstone / pefile 導入済み (ldfix が有効)。
+
+## 3. Ghidra 再生成 (`functions_dll.csv`)
+| 項目 | 値 |
+|---|---|
+| コマンド | `analyzeHeadless <proj> dll_proj -import block00031_PE.bin -scriptPath tools/m2/ghidra_scripts -postScript DumpFunctions.java <out.csv>` |
+| rc | 0 |
+| 所要 | 611 秒 |
+| 出力 | `tools/m2/work/ghidra_dll/functions_dll.csv` 59,010 行 (REPORT_N1532 の 59,010 と一致) |
+| sha256 | `90d1bbac…` (REPORT_N27・N1042 と一致) |
+
+## 4. `m11_e2e.sh` 既定経路 (HEAD = 4c3f7458)
+実行: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/m11/m11_e2e.sh` (既定・`--full` 無し)
+
+| 段 | 結果 |
+|---|---|
+| 全再生成モード (`lift_pe.sha256` 無し → 全再生成) | 入り、以降すべて ok |
+| m11_bounds | ok (`functions_dll.csv` を読めた) |
+| lift 4 chunks (RetDec) / m11_tail 固定点 #1〜#3 / lift boot4 / gen_ir2 | 全 ok |
+| lift boot5 (RetDec) / gen_ir2 (boot5 追加) | ok |
+| m11_data_gen / m11_image_gen / lb_check / build (emcc) | ok |
+| 実行 A (通常起動) / 実行 B (unit survey) | 実行 |
+| judge (`--require-stage 4 --min-survey-ok 850` 相当) | rc 0 |
+
+- 所要: **623 秒** (全体 `timeout 1500` 内)。rc: **0**。PASS/FAIL: **PASS** (judge の期待値 `e2e_expect.env`: stage 4・survey_ok 800 以上を満たす)。
+- M11_SUMMARY (抜粋): `reached_stage` 4 / `stop_reason` `trap "unreachable" @ function_8c5eb0 <- ...` / `ir_conditions`: `ldfix` applied・`qstore` applied・`ir_sha256` `951e5b5d…` / `units_run_full` 53 / `survey_ok` 872 / `survey_trap` 23 / `survey_miss` 46 / `wasm_bytes` 6,043,394。
+- 注: trap (stage 4 で停止) は REPORT_N27 §12・N1415 と同じ既知の停止で、本 run で解消していない。判定の PASS は回帰ゲート (stage ≥ 4・survey_ok ≥ 800) の通過であり、lift 成果物の正しさの判定ではない。
+- 注: `ir_sha256` `951e5b5d…` は過去記録との比較を本 run では行っていない。REPORT_N27 §12 で IR sha が実行ごとに変わる件は未切り分けのまま。本 run の値は参照用に残すのみ。
+
+## 5. 検証範囲 / 範囲外
+- 範囲: 本 runner の 1 ホスト・PE 1 member・n=1 (再現性の反復は未実施)。
+- 範囲外: trap の解消 (stage 4 → 5 以上)・IR sha の実行間変動の切り分け・survey 値の基準比較。
+
+## 6. コード差分 (測定 commit → HEAD)
+- 測定 commit `4c3f7458` から HEAD までのコード変更はない。本 PR で追加するのは本 REPORT と `docs/DOC_MAP.md` の索引 1 行のみ。
+- `git diff 4c3f7458 HEAD -- tools/m11` の実出力は PR 本文に添付する。
+
+## 7. 未解決 (起票先)
+| 未解決 | 影響 | 起票先 |
+|---|---|---|
+| stage 4 の trap (`function_8c5eb0`) が残る | e2e の到達 stage が 4 止まり | 既存の起票先なし (REPORT_N27 §12・N1415 §6 参照)。PM 判断 |
+| IR sha256 が実行ごとに変わる (未切り分け) | IR 再現性の判定 | 既存の起票先なし (REPORT_N27 §12 参照)。PM 判断 |
```

## 7. 未解決 (起票先)
| 未解決 | 影響 | 起票先 |
|---|---|---|
| stage 4 の trap (`function_8c5eb0`) が残る | e2e の到達 stage が 4 止まり | 既存の起票先なし (REPORT_N27 §12・N1415 §6 参照)。PM 判断 |
| IR sha256 が実行ごとに変わる (未切り分け) | IR 再現性の判定 | 既存の起票先なし (REPORT_N27 §12 参照)。PM 判断 |
