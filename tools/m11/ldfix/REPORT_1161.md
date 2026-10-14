# REPORT #1161 — spill 宛 178 site の分類表・独立再計算・ネガコンの HEAD 再測定 (LD-35)

既知類型との関係: 該当 ID なし (`docs/DEFECTS.md` の D3 (fe: メモリ宛 store の消失) と D20 (wrong-value reuse) に近いが、本 REPORT は機構を確定せず分類するため同一類型とは断定しない)。

親: #969 (LD-22)。本 issue は規約 (`.github/prompts/implementer.md` 行動規範 11・`docs/WORKFLOW.md` §3 の Closes 縮小規定) に従い範囲を縮小した。完了分は独立再計算・ネガコン・分類表 (再測定)。未達の全数分類と脱落関数一覧の最終化は子 issue へ移した (§3)。

## 1. 測定条件

- 測定 commit: `cc6d6610` (origin/main)。§2 と §3 の 1〜6/7 の数値はこの commit の e2e 実行の結果。作業 worktree `ws-1161` (branch `1161-spill-coverage`)
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で展開 (gitignore 対象の `tools/m11/work/`・`tools/liftdiff/work/`)
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground)
- 結果: rc=0、real 137 s、load average (uptime) 0.40 → 1.08
- 7/7 完了時に `spill178_1161.tsv` と `drops_510.tsv` が results/ と一致。実行後の `git status` は clean
- 測定後の変更: `spill_classify_1161.py` の docstring のみ (commit `9a1045ee`。出力は不変)。`git diff cc6d6610 HEAD -- tools/m11/ldfix` の残りは本 REPORT のみ
- 7/7 の HEAD 再実行 (`9a1045ee` 以降): 入力は commit 済みの `results/audit_510_ssa.json` (2/7 の出力)。`spill178_1161.tsv` と cmp 一致。§3 の [1]〜[6] の出力も同一
- **未実施: 1〜6/7 の HEAD 再測定**。本 run の `$ARTIFACTS_DIR` に `work-m11`・`work-liftdiff` が無く、手元の検証スナップショットも無い。PR 本文に `oc_artifacts: work-m11 work-liftdiff` を指定した (本スクリプトは PE (fl-win64) を使わない)

## 2. 独立再計算・ネガコン (受入 4・5)

- 3/7 `window_recount.py`: window pairs 420 (210 関数)。データフロー側に無い対は 0 (`window_not_in_dataflow=0`)。測定 commit `cc6d6610`
- 6/7 `negctl_510.sh`: NC0 (無改変) と NC1〜NC7 の 8 本すべてが REPORT_510 §6 の期待どおり。測定 commit `cc6d6610`

## 3. 全数分類の現状と担当 (受入 1〜3 の残件)

spill 宛 unk site 178 (71 関数) の判定状態 (`results/spill178_1161.tsv`・7/7 出力)。確定 97 (TRUE_DROP 33・OK_LOAD 57・NO_CONSUMER 7) / 判定不能 16 / 未判定 65。

| 状態 | 範囲 | site | 担当 |
|---|---|---|---|
| 未判定 | 関数群 B (10c7cd0・1046a30・ddf630・6bb3f0・466af0・12cb680) | 32 | #2245 (LD-93) |
| 未判定 | c589b0・128f9e0 (128f9e0 の 13 site のうち 12 が未判定。残る 12900c4 は下の判定不能) | 24 | #2288 (LD-104) |
| 未判定 | 旧 TRUE_DROP 保留 (775340 ほか 7 関数: 1042d20・12f9730・6c3700・6c3d20・6c5930・815050・f3e050) | 9 | #2583 (LD-118) |
| 判定不能 | 候補 31 site 由来 (128c320・1280530・dcdde0・c343f0・128f9e0 の 12900c4) | 7 | #2253 (LD-95) |
| 判定不能 | 上記以外 (41ba50・41bfa0・41e490・45b170・45c290・45d0a0・45d610・45f560) | 9 | #2660 (LD-119) |

- 未判定 65 + 判定不能 16 は上表の 5 群で過不足なく覆われる (site 単位で突合済み)。
- 「候補 31 site」= `results/drops_510.tsv` の `source=candidate` の 31 行 (全て dest=frame)。確定 24 / 判定不能 7 (上表)。判定不能 9 site (#2660) は `candidate_verdicts_1161.jsonl` で UNDETERMINED だが、この 31 には含まれない。
- 脱落関数の集合 (`spill_classify_1161.py` の出力 [5]・[6] と突合):
  - A = `drops_510.tsv` の dest=store の関数 = 51
  - B = `drops_510.tsv` の dest=frame の関数 = 22 (候補 31 site と目視 6 site。C とは別集合: 128f9e0・c343f0・dcdde0・f5d510 は B にあるが確定 TRUE_DROP ではない)
  - C = spill 178 のうち確定 TRUE_DROP の関数 = 21
  - A ∪ B = 69 (A ∩ B = 4: 1046a30・1280530・128c320・128f9e0)。出力 [5]
  - C のうち A ∪ B に無い関数 = 3 (4120c0・41a5d0・6c3700)。出力 [6]
  - **A ∪ B ∪ C = 72** (= 69 + 3)。未判定の決着で変わりうる。最終化は #2660 (LD-119)

## 4. 棚卸し

- #2312 (LD-105) は closed 済みで残件なし。対象の cf3790 の spill 宛 unk site 24 はすべて確定 (`spill178_1161.tsv`)。
- 判定不能 9 site (#2660) と #1169 (LD-37・spill 宛 CELL_COLLAPSED 37 site) の対象が重なる可能性がある。未照合 (#2660 の本文に記載)。

## 5. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```

7/7 のみ (素材不要・commit 済み入力): `python3 tools/m11/ldfix/spill_classify_1161.py tools/m11/ldfix/results/audit_510_ssa.json "$RUNNER_TEMP/spill178.tsv"` の後、`cmp` で `tools/m11/ldfix/results/spill178_1161.tsv` と比較する。
