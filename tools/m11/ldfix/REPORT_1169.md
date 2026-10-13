# #1169 (LD-37) D17 spill 宛 CELL_COLLAPSED の消費者追跡: 現状測定と分割 (部分達成)

**判定: 部分達成**。spill 宛 CELL_COLLAPSED 37 site / 22 関数の修復は未着手 (修復 pass を追加していない)。
本 run では、現 HEAD での基準値の実測と、既存の目視判定の分類を残すことまでを行った。
受入条件 1 (消費者の脱落判定) の残りと 2 (修復 pass)・3 (修復後の残数) は子 issue に分割する。

## 1. 基準値 (実測・修復前後)

測定 commit: `711b58ca` (origin/main)。`bash tools/m11/ldfix/fix_d17_e2e.sh` (`M11_WORK` = main の `tools/m11/work`、PE 無し)。

| 項目 | 修復前 | 修復後 (fix_d17.py) |
|---|--:|--:|
| CELL_COLLAPSED spill 宛 site | 37 | 37 |
| CELL_COLLAPSED spill 宛 関数 | 22 | 22 |
| CELL_COLLAPSED store 宛 site | 86 | 53 |
| CELL_COLLAPSED store 宛 関数 | 49 | 28 |
| alg3 flagged 関数 | 77 | 58 |

- `fixed_fns=24 fixed_cells=29` (`fix_d17.py`)。emcc 構文検証 `-O0 -g1 -c`: rc=0。
- e2e の所要時間: 約 32 秒 (`real 0m31.8s`、load 0.36 開始時)。
- 修復前後の数値は `REPORT_968.md` §2 の値と一致する (store 宛 86 → 53、spill 宛 37 → 37)。
- `fix_d17.py` は store 宛 (`frame=False`) だけを対象とするため、spill 宛 37 site は修復前後で変化しない。これは想定どおり。

## 2. spill 宛の内訳 (既存判定の集計)

`results/drops_510.tsv` の `dest=frame` 37 行 (REPORT_510 §4.3 と同じ集合):

- `source=manual` 6 行: TRUE_DROP 6 (4 関数: cf3790・f40840・ff8b60・100b890)。
- `source=candidate` 31 行: 未確認 (18 関数相当の oracle 候補)。

`results/manual_verdicts_510.jsonl` の spill 宛判定 (関数別):

| 関数 | 判定 (site) |
|---|---|
| cf3790 | TRUE_DROP 3 (cf387f・cf38be・cf390f)、OK_LOAD 2 (cf395f・cf3af5)、NO_CONSUMER 1 (cf398c) |
| f40840 | TRUE_DROP 1 (f43266)、OK_LOAD 5 (f4286f・f431c1・f43545・f442cd・f4434c)、NO_CONSUMER 2 (f44154・f4435b) |
| ff8b60 | TRUE_DROP 1 (ff8c63)、OK_LOAD 1 (ff8c15)、NO_CONSUMER 1 (ff8b77 dead spill) |
| 100b890 | TRUE_DROP 1 (100b8d0) |

- 目視 27 site の消費者判定: TRUE_DROP 6、OK_LOAD 16、NO_CONSUMER 5 (REPORT_510 §4.3 と一致)。
- 上記の表は `manual_verdicts_510.jsonl` の上記 4 関数の spill 宛 18 行 (`evidence` 欄) をそのまま分類したもので、再判定はしていない。REPORT_510 §4.3 の「目視 27 site」は、この 18 行に加えて他関数の行を含む数である (本 run では他関数の行は未集計)。

## 3. 未了と既存の子 issue

- **候補 31 site / 18 関数 (`source=candidate`) の消費者追跡・分類・ネガコン**: #1161 (LD-35、親 #969) が受入条件として持つ。本 run では重複起票しない。
- **複数 load の CELL_COLLAPSED 28 関数 / 53 site (store 宛)**: #1168 (LD-36)。本 issue の対象外。
- **spill 宛の脱落に対応する修復 pass**: spill 宛は IR から値が消えるため、`fix_d17.py` (store 宛の 2 段 load 修復) の方式は流用できない。消費者 (call 引数・cmp・算術) 側の修復方式は #1161 の分類結果を待って決める。本 issue の残件。
- **修復後の残数の実測**: 修復 pass の実装後に `fix_d17_e2e.sh` の step 3 で測り直す。本 issue の残件。

本 PR は `Refs #1169` (部分達成)。

## 4. 再現

```
M11_WORK=<work-m11>/tools/m11/work bash tools/m11/ldfix/fix_d17_e2e.sh
```

ステップ 1 の `ssa_base.json` で spill 宛 CELL_COLLAPSED を数える (`cell.verdict == CELL_COLLAPSED` かつ `frame == true`)。
