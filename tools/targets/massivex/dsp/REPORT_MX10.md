# MX-10 (#1488) .pdata 解決不能 19,420 件の読み方 (受入 1 の候補検証)

- 親: #1321 (MX-8) / 起票: #1488 (MX-10)。本ファイルは #1488 の実測。
- 素材: `plugins-massivex` → `work/extracted/VST3/Massive X.vst3` (95,356,824 B / md5 `622993e76565f49c094063a2b717d6ca`、REPORT_MX5 §5 と一致)。
- 計測スクリプト: `dsp/scripts/mx_unres_probe.py` (新規・本 run)。

## 1. 今 run で達成した範囲

- 受入 1 (解決不能 19,420 件の読み方): **未確定**。候補 section の整合条件で 11,922 件は一意に読めたが、残り 7,498 件は候補が 0 件または 2 件以上で決まらない。
- 受入 2 (code/data 区別の再帰降下): **未着手** (子 issue)。
- 受入 3 (leaf 境界の実 unwind 化): **未着手** (子 issue)。
- 受入 4 (e2e PASS・negctl 3 件 FAIL<期待>): **達成** (§4)。

## 2. 候補検証の結果

解決不能 entry (section hit 0 件 or 2 件以上・REPORT_MX5 §2 注 4) について、UNWIND_INFO の RVA を VirtualSize 範囲に持つ section ごとに file offset を求め、次の整合条件で判定した。

- Version ∈ {1, 2}・SizeOfProlog ≤ 関数長・CountOfCodes ≤ 255
- CountOfCodes = 0 は CHAININFO (Flags & 4) のときだけ許す
- CHAININFO なら親 RUNTIME_FUNCTION が valid .pdata に完全一致で在るか

| 指標 | 値 |
|---|--:|
| 解決不能 entry | 19,420 |
| hit 3 件 / 2 件 / 0 件 | 16,706 / 2,554 / 160 |
| 整合候補 0 件 | 160 |
| 整合候補 1 件 (すべて plain) | 11,922 |
| 整合候補 2 件 | 7,274 |
| 整合候補 3 件 | 64 |

注: 整合条件は候補の否定 (明らかに不正な読みを落とす) にしか効かない。1 件の plain 候補が残った 11,922 件も、正しい読みだと確定したわけではない。CHAININFO の親一致による絞り込みは、解決不能分では一意にならなかった (`unique_sane_chain_*` は 0 件)。

## 3. 未解決 (子 issue へ)

| 残件 | 受入 | 起票先 |
|---|---|---|
| 解決不能 19,420 件のうち、整合候補が 0/2/3 件の 7,498 件の読み方 | 1 | 子 issue (MX-12) |
| code/data 区別 (jump table・文字列窓) を入れた再帰降下と round 推移 | 2 | 子 issue (MX-13) |
| leaf 境界を実 unwind / 境界に置換し、closure バイト数と target 判定の変化を定量化 | 3 | 子 issue (MX-14) |

## 4. 検証

- **測定 commit (コードを変えた最後の commit)**: `cff67fbf` (`feat(massivex): probe candidate sections for unresolved UNWIND_INFO (Refs #1488)`)。e2e が使うコードは base (`3cdf8329`) と同一。
- **e2e (`bash dsp/e2e.sh`・測定 commit・n=1)**: rc 0 / `OK elapsed=43s` / load 0.22 0.37 0.21 → 0.76 0.49 0.26。base 3cdf8329 でも rc 0 / `OK elapsed=43s` (load 0.50 0.42 0.19 → 0.96 0.54 0.24)。
- **negctl (`bash dsp/negctl.sh`・base 3cdf8329)**: NC1 unsup 67 / NC2 unsup 746 / NC3 insns 31 unsup 0 → 3 件とも FAIL<期待>。
- **probe (測定 commit)**: `mx_unres_probe.py` → valid 186,961 / 解決不能 19,420 (REPORT_MX5 §2 と一致)。
- **鮮度 (WORKFLOW §6)**: 測定 commit `cff67fbf` 以降、本 REPORT の commit だけが増える (コード差分は dsp 外の REPORT のみ)。
