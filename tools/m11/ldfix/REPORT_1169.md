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
- e2e の所要時間: `real 0m31.8s` (開始時 load 0.36)。元の測定 run の値。再現に必要な素材 (`work-m11`・`toolchain-emsdk`) は本 fix run では無く、再測定していない。
- 修復前後の数値は `REPORT_968.md` §2 の値と一致する (store 宛 86 → 53、spill 宛 37 → 37)。
- `fix_d17.py` は store 宛 (`frame=False`) だけを対象とするため、spill 宛 37 site は修復前後で変化しない。これは想定どおり。

## 2. spill 宛の内訳 (既存判定の集計)

`results/drops_510.tsv` の `dest=frame` は 37 行 (22 関数): `source=candidate` 31 行 (判定なし、本 run では未集計) と `source=manual` 6 行。

`results/manual_verdicts_510.jsonl` で spill 宛の判定が付いているのは 18 行 (4 関数)。このうち TSV の `dest=frame` と突き合わせられるのは次の 6 行だけで、6 行とも TRUE_DROP。

| 関数 | TSV `dest=frame` (manual) の site | 判定 |
|---|---|---|
| cf3790 | cf387f・cf38be・cf390f | TRUE_DROP 3 |
| f40840 | f43266 | TRUE_DROP 1 |
| ff8b60 | ff8c63 | TRUE_DROP 1 |
| 100b890 | 100b8d0 | TRUE_DROP 1 |

残りの 12 行は TSV に無く、spill 宛 37 site の集合には入らない (由来は REPORT_510 §4.3 の目視判定)。

| 関数 | TSV に無い site と判定 |
|---|---|
| cf3790 | cf395f OK_LOAD・cf3af5 OK_LOAD・cf398c NO_CONSUMER |
| f40840 | f4286f・f431c1・f43545・f442cd・f4434c OK_LOAD、f44154・f4435b NO_CONSUMER |
| ff8b60 | ff8c15 OK_LOAD、ff8b77 NO_CONSUMER (dead spill) |

- 上の 12 行の内訳: OK_LOAD 8、NO_CONSUMER 4。
- REPORT_510 §4.3 の「目視 27 site の消費者判定: TRUE_DROP 6、OK_LOAD 16、NO_CONSUMER 5」は、この 18 行より広い集合の引用である。本 run では再集計していない。

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
