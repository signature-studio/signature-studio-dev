# REPORT N2045 — sigfix 0 詰め site の 1,049→1,061 の原因 commit の二分探索: 1 段の駆動と段 1〜4 の実測 (#2045, 親 #1997・#1904)

既知類型との関係: 該当なし (測定とスクリプトの追加。コード変更は `tools/m11/m11_bisect_step.sh` の追加のみ)。
親: #1997 → #1904 (`REPORT_N1904.md`)。前提: `REPORT_N1997.md` (PR #2046, merge 済み)。

## 1. 結論

- 依存を含む範囲 `7e149974..392d8ba5` の no-merges commit は **129** (前回の lift pathspec の 16 は依存を含まず不完全だった)。⌈log2 129⌉ = 8 段。
- 段 1〜4 (順序位置 65・33・17・9) を実測した。いずれも **1,061 / 2,084** で、`REPORT_N1532.md` の full 再生成の値 (`392d8ba5`) と同じ。
- **原因 commit は未特定。** 旧値 1,049 は既製素材 (`work-m11` の `boot_final.ll`) から出た値で、`7e149974` を同じ手順 (full 再生成) で測った値ではない (§2)。基線が同手順で測れていないため、1,049 → 1,061 の変化が commit によるものか、素材と再生成の手順差かは区別できない。順序 9 以前に 1,061 が現れていることは段 4 で確認したが、変化の位置は決まらない。
- 基線 `7e149974` の同手順測定と、残りの二分探索は子 `[M11-N166]` (#3011) に移す。`toolchain-retdec` 素材 (RetDec・Ghidra を含む) が要るため、本 run では実施していない (§5)。
- 1 段は約 6 分 15 秒〜6 分 35 秒。Ghidra の `functions_dll.csv` 生成 (6 分 06 秒) は 1 回だけ要る (PE だけで決まる)。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 範囲 | `7e149974` (旧) .. `392d8ba5` (新, 1,061 site・`REPORT_N1532.md`)。`merge-base --is-ancestor` OK |
| 基線の出典 | `REPORT_N1702.md` §2・§3 の 1,049 は、既製 `work-m11` の `boot_final.ll` (10 Oct 生成) から出た値。`7e149974` を full 再生成した値ではない。同じ素材から新値 1,061 は再現しなかった (`REPORT_N1702.md` §4)。本 PR の手順で `7e149974` を測った記録は無い |
| 範囲の commit 数 | `git rev-list --count` = 665 (merge 含む)・no-merges 455 |
| 依存込み pathspec | `tools/m11` (`REPORT*`・`results` を除く)・`tools/m2/ir_normalize.py`・`tools/m5/ir5_patch.py`・`tools/shared`・`tools/m1/flags.sh`・`tools/m2/ghidra_scripts` → no-merges **129** |
| 順序 | `git rev-list --reverse --no-merges <範囲> -- <pathspec>` の位置 (1 始まり) |
| 素材 | `fl-win64` の `block00031_PE.bin` のみ (22,227,016 B)。Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致) を `$RUNNER_TEMP` に導入し、JDK 21 で `DumpFunctions.java` を実行 (6 分 06 秒・59,010 行) |
| 駆動 | `tools/m11/m11_bisect_step.sh <commit>` (`git archive` で展開し、scan→bounds→lift_all→tail/boot4/boot5 lift→gen_ir2→sigfix_stats。build と node 実行は省く) |

## 3. 実測値

| 段 | 順序位置 | commit | 所要 | 0 詰め site / 引数 | const recovered |
|---|---|---|---|---|---|
| 1 | 65 / 129 | `0b46b944` | 6 分 15 秒 | 1,061 / 2,084 | 18 |
| 2 | 33 / 129 | `a702c909` | 6 分 35 秒 | 1,061 / 2,084 | 18 |
| 3 | 17 / 129 | `a5e9c1ed` | 6 分 22 秒 | 1,061 / 2,084 | 18 |
| 4 | 9 / 129 | `b8b640ee` | 6 分 19 秒 | 1,061 / 2,084 | 18 |

- 段 1〜4 の 1,061 / 2,084 は `REPORT_N1532.md` が `392d8ba5` で記録した full 再生成の値と一致した。
- 段 1〜3 は本 PR に入っていない作業用の手順 (`$RUNNER_TEMP/m11b/step.sh`、PR 外) で測った。段 4 だけは PR のスクリプト `tools/m11/m11_bisect_step.sh` そのもの。
- 判定: 段 1〜4 はいずれも 1,061。基線 `7e149974` を同手順で測っていないため、1,049 → 1,061 の変化が起きた位置・原因 commit は未確定。次段の対象は基線の結果が出てから決める。

## 4. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 基線 `7e149974` の同手順測定 (full 再生成。`toolchain-retdec` 素材が要る。本 run では素材・RetDec・Ghidra が無く未実施) | 1,049 → 1,061 の差が commit によるか、手順差かが未確定 | 子 `[M11-N166]` (#3011) の最初の項目 |
| 原因 commit の二分探索 (基線が 1,049 と確認された場合のみ。順序 1〜9 の残り) | 増加の原因 commit が未特定 | 子 #3011 |
| 範囲の両端の前提 (pathspec 外の commit が 0 詰め数に効かない) | pathspec 外が原因なら二分探索の結論が外れる | 子 #3011 |

## 5. 検証

- `bash -n tools/m11/m11_bisect_step.sh` = OK。
- 素材の欠落時の fail-closed: `M11_BISECT_GHIDRA_CSV` 未指定で rc 1 とメッセージを出すことを確認。
- 終端行の fail-closed (本 commit): 終端行 `[stats] zeropad` を含む入力で rc 0 と終端行を出し、含まない入力で rc 1 とメッセージを出すことを確認。
- 段 4 (`b8b640ee`) を PR のスクリプトで実行: rc 0・終端行 `[stats] zeropad sites 1061 / args 2084; const recovered 18 (base 0)`。
- 差分 (測定 commit `b8b640ee` から HEAD まで): `git diff --shortstat b8b640ee HEAD -- tools/m11 tools/m2 tools/m5 tools/shared tools/m1` の実出力は `494 files changed, 51633 insertions(+), 339 deletions(-)`。`b8b640ee` は HEAD の祖先。差分の大半は、測定 commit より後に main へ入った他 PR の変更で、本 PR の変更ではない。
- 差分が測定に入らない理由: 各段の測定対象は `git archive <commit>` で取り出した木 (`m11_bisect_step.sh` の `git archive "$SHA"`) で、HEAD の差分は測定の入力に入らない。駆動スクリプトの PR 初版 (`8530cfc2`) から HEAD までの差分は、`git diff 8530cfc2 HEAD -- tools/m11/m11_bisect_step.sh` で注釈 1 行 (`c94f98fd`) と終端行の判定 (本 commit) のみ。測定の計算に入るコマンドは変わらない。よって HEAD での再測定は求めない。

## 6. 再現

```sh
export RUNNER_TEMP=... FL_WIN64_DIR=<fl-win64 の展開先> M11_BISECT_GHIDRA_CSV=<functions_dll.csv の場所>
git rev-list --reverse --no-merges 7e149974..392d8ba5 -- tools/m11 ':(exclude)tools/m11/REPORT*' ':(exclude)tools/m11/results' tools/m2/ir_normalize.py tools/m5/ir5_patch.py tools/shared tools/m1/flags.sh tools/m2/ghidra_scripts > range.txt   # 129 行
bash tools/m11/m11_bisect_step.sh "$(sed -n 9p range.txt)"   # 段 4 (b8b640ee)。終端行 1061 / 2084
```

段 1〜3 (順序 65・33・17) は PR 外の手順で測った (§3)。本 PR の再現は段 4 のみ。基線 (未実施・子 #3011): `bash tools/m11/m11_bisect_step.sh 7e149974` (`toolchain-retdec` 素材が要る)。
