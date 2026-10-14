# REPORT N2045 — sigfix 0 詰め site の増加 (1,049→1,061) を生んだ commit の二分探索: 1 段の駆動と段 1〜4 の実測 (#2045, 親 #1997・#1904)

既知類型との関係: 該当なし (測定とスクリプトの追加。コード変更は `tools/m11/m11_bisect_step.sh` の追加のみ)。
親: #1997 → #1904 (`REPORT_N1904.md`)。前提: `REPORT_N1997.md` (PR #2046, merge 済み)。

## 1. 結論

- 依存を含む範囲 `7e149974..392d8ba5` の no-merges commit は **129** (前回の lift pathspec の 16 は依存を含まず不完全だった)。⌈log2 129⌉ = 8 段。
- 段 1〜4 を実測した。いずれも **1,061 / 2,084 (新値)**。原因 commit は順序位置 **1〜9 番目** (`b8b640ee` を含む以前) にある。残り 4 段 (⌈log2 9⌉) は子 issue `[M11-N166]` に移す。
- 1 段は約 6 分 15 秒〜6 分 35 秒。Ghidra の `functions_dll.csv` 生成 (6 分 06 秒) は 1 回だけ要る (PE だけで決まる)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 範囲 | `7e149974` (旧, 1,049 site・`REPORT_N1702.md`) .. `392d8ba5` (新, 1,061 site・`REPORT_N1532.md`)。`merge-base --is-ancestor` OK |
| 範囲の commit 数 | `git rev-list --count` = 665 (merge 含む)・no-merges 455 |
| 依存込み pathspec | `tools/m11` (`REPORT*`・`results` を除く)・`tools/m2/ir_normalize.py`・`tools/m5/ir5_patch.py`・`tools/shared`・`tools/m1/flags.sh`・`tools/m2/ghidra_scripts` → no-merges **129** |
| 順序 | `git rev-list --reverse --no-merges <範囲> -- <pathspec>` の位置 (1 始まり) |
| 素材 | `fl-win64` の `block00031_PE.bin` のみ (22,227,016 B)。Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致) を `$RUNNER_TEMP` に導入し、JDK 21 で `DumpFunctions.java` を実行 (6 分 06 秒・59,010 行) |
| 駆動 | `tools/m11/m11_bisect_step.sh <commit>` (`git archive` で展開し、scan→bounds→lift_all→tail/boot4/boot5 lift→gen_ir2→sigfix_stats。build と node 実行は省く) |

## 3. 実測値

| 段 | 順序位置 | commit | 所要 | 0 詰め site / 引数 | const recovered | 判定 |
|---|---|---|---|---|---|---|
| 1 | 65 / 129 | `0b46b944` | 6 分 15 秒 | 1,061 / 2,084 | 18 | 新 |
| 2 | 33 / 129 | `a702c909` | 6 分 35 秒 | 1,061 / 2,084 | 18 | 新 |
| 3 | 17 / 129 | `a5e9c1ed` | 6 分 22 秒 | 1,061 / 2,084 | 18 | 新 |
| 4 | 9 / 129 | `b8b640ee` | 6 分 19 秒 | 1,061 / 2,084 | 18 | 新 |

- 段 1 の 1,061 / 2,084 は `REPORT_N1532.md` が `392d8ba5` で記録した値と一致した (駆動の妥当性)。
- 段 1〜4 は作業用の同じ手順 (`$RUNNER_TEMP/m11b/step.sh`) で測った。段 4 は PR に入れた `tools/m11/m11_bisect_step.sh` そのもので測った。
- 判定: 新値の初出は順序位置 1〜9 のどこか。次段は 1〜9 の中点 5 番目。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 原因 commit の特定 (順序位置 1〜9 の二分探索。残り ⌈log2 9⌉ = 4 段) | 旧 1,049 と新 1,061 の差の説明が無い | 子 `[M11-N166]` (本 PR で起票) |
| 範囲の両端 (`7e149974` = 1,049 の再測定) は未実施。pathspec 外の commit が 0 詰め数に効かないという前提は未検証 | pathspec 外が原因なら二分探索の結論は外れる | 子 `[M11-N166]` の受入条件に含める |

## 5. 検証

- `bash -n tools/m11/m11_bisect_step.sh` = OK。
- 素材の欠落時の fail-closed: `M11_BISECT_GHIDRA_CSV` 未指定で rc 1 とメッセージを出すことを確認。
- 段 4 (`b8b640ee`) を PR のスクリプトで実行: rc 0・終端行 `[stats] zeropad sites 1061 / args 2084; const recovered 18 (base 0)`。
- 差分 (測定 commit `b8b640ee` から HEAD までのパイプライン入力): `git diff --stat b8b640ee HEAD -- tools/m11 tools/m2 tools/m5 tools/shared tools/m1` の出力は PR 本文に添付した。本 PR のコード変更は `tools/m11/m11_bisect_step.sh` の追加のみ。

## 6. 再現

```sh
export RUNNER_TEMP=... FL_WIN64_DIR=<fl-win64 の展開先> M11_BISECT_GHIDRA_CSV=<functions_dll.csv の場所>
git rev-list --reverse --no-merges 7e149974..392d8ba5 -- tools/m11 ':(exclude)tools/m11/REPORT*' ':(exclude)tools/m11/results' tools/m2/ir_normalize.py tools/m5/ir5_patch.py tools/shared tools/m1/flags.sh tools/m2/ghidra_scripts > range.txt   # 129 行
bash tools/m11/m11_bisect_step.sh "$(sed -n 9p range.txt)"   # 終端行 1061 / 2084
```
