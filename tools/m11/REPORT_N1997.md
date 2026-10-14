# REPORT N1997 — 新規 12 site (引数 20) を生んだ段の二分探索: 実行可能性の判定と範囲の絞り込み (#1997, 親 #1904)

既知類型との関係: 該当なし (測定条件の判定と範囲の絞り込みのみ。コード変更なし)。
親: #1904 → #1702 → #1532 (`REPORT_N1904.md` §6)。二分探索の本体は子 issue に分離 (§5)。

## 1. 結論

- commit 単位の二分探索 (`7e149974..392d8ba5`, 665 commit) は **本 run (上限 58 分) では実行できない**。
  1 段の `m11_e2e.sh --full` は 649 s (`REPORT_N1702.md` の実測値) で、二分探索は 10 段 (⌈log2 665⌉ = 10)。10 段分の計算値は 649 s × 10 = 6,490 s (108 分) で、上限を超える。
- 探索対象を、lift 段 (boot0〜6・tail 反復・wndclass 閉包) の入力に触れた commit に絞ると 16 commit になった (計算値 ⌈log2 16⌉ = 4 段 × 649 s = 2,596 s)。ただし pathspec は不完全で、§3 の依存を含めると範囲は広がる。
- 原因 commit は **未特定**。本 PR では二分探索を実行していない。

## 2. 測定条件

| 項目 | 値 |
|---|---|
| 基準 commit | `origin/main` = `c171b9dc` (worktree `ws-1997`, branch `1997-m11-zeropad-bisect`) |
| 対象範囲 | `7e149974` (旧, 1,049 site) .. `392d8ba5` (新, 1,061 site)。`git merge-base --is-ancestor` で祖先関係を確認 (OK) |
| 範囲内 commit 数 | 665 (`git rev-list --count`) |
| 1 段の所要 | 649 秒 (`REPORT_N1702.md`・`m11_e2e.sh --full` の実測値を引用。本 run では測っていない) |
| 本 run の素材 | `ARTIFACTS_DIR` を `ls` で確認した結果、実在は `fl-win64` (`fl-win64.tar.zst`) のみ。`[WORK-M11]`・`toolchain-retdec`・`toolchain-emsdk` は不在。e2e は未実行 |

## 3. 範囲の絞り込み

`git log --oneline 7e149974..392d8ba5 -- <lift 段の入力>` の結果 (pathspec: `m11_extra_ranges5.txt`・`m11_wndclass_scan.py`・`m11_tail.py`・`m11_gen_ir2.sh`・`m11_lift.sh`・`m11_lift_all.sh`・`m11_bounds.py`・`m11_scan.py`・`work/boot_ranges_extra.txt`・`m11_cond.py`・`m11_build.sh`・`m11_e2e.sh`・`e2e_expect.env`・`tools/shared/env.sh`) は **16 commit**。

ただし `m11_gen_ir2.sh` は次も呼ぶため、pathspec に入れていない依存が残る:

- `ldfix/ldfix.py` (`tools/m11/ldfix/` 配下)
- `m11_asmfix.py`・`m11_genstubs.py`・`m11_merge.py`・`m11_passes.py`
- `../m2/ir_normalize.py`・`../m5/ir5_patch.py` (`m11_lift.sh` から参照)

`tools/m11/ldfix` 系と `tools/shared` を含めた対象範囲の commit 数は本 run では数えていない (子 issue で数える)。

## 4. 素材の状態

- 本 run の確認 (`ls`): `ARTIFACTS_DIR` の実在は `fl-win64` のみ。`[WORK-M11]` (`work-m11`) の素材は不在のため、`tools/m11/work/` の中身 (`scan_index.json`・`boot_ranges_extra.txt` 等) は**未確認**。
- `[RETDEC]`・`[EMSDK]` のツールも本 run には不在 (`docs/REFERENCES.md` §1 の `[OPT-TOOLS]` 配下。`toolchain-retdec`・`toolchain-emsdk` の取得指定が要る)。
- `functions_dll.csv`・`lift_pe.sha256`・`ir_conditions.json` の有無は**未確認**。`REPORT_APPENDIX_1430.md` によれば `functions_dll.csv` は Ghidra で作られる (9 分 37 秒)。したがって `--full` の 1 段の 649 s に Ghidra 時間が含まれるかは、子 issue で確認する必要がある。

## 5. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 新規 12 site を生んだ commit (または段) の二分探索。16 commit の pathspec と §3 の依存を合わせた範囲で、commit ごとに `m11_e2e.sh --full` を回す | 旧 1,963 と新 1,983 の差の説明が無い | #2045 `[M11-N134]` (本 PR で起票) |

## 6. 検証

- 祖先関係: `git merge-base --is-ancestor 7e149974 392d8ba5` = OK。
- 範囲 commit 数: `git rev-list --count 7e149974..392d8ba5` = 665。
- pathspec 絞り込み: `git log --oneline 7e149974..392d8ba5 -- <§3 の pathspec>` = 16 commit。
- 祖先関係・件数は上記コマンドで本 run に再実測した値 (`merge-base` OK / 665 / 16)。
- コード変更なし。e2e 未実行 (§2)。素材は `fl-win64` のみ実在し、他は不在 (§2・§4)。

## 7. 差分

- 測定 commit: `c171b9dc` (本 run は測定していない。コード変更なし)。
- PR の差分 (main 取り込み後): `git diff $(git merge-base origin/main HEAD) HEAD -- tools/m11/REPORT_N1997.md` = 追加 59 行・削除 0 行のみ。
- 注: 同じ HEAD で `git diff c171b9dc HEAD -- tools/m11` には、取り込んだ main 側の他 PR の変更 (9 file) が含まれる。本 PR の変更ではない。
