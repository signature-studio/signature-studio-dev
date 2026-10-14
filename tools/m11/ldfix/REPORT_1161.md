# REPORT #1161 — spill 宛 178 site の分類表・独立再計算・ネガコンの HEAD 再測定 (LD-35)

親: #969 (LD-22)。本 issue は規約 (AGENTS.md 行動規範 11) に従い範囲を縮小した。完了分は独立再計算・ネガコン・分類表 (再測定)。未達の全数分類と脱落関数一覧の最終化は子 issue へ移した (§3)。

## 1. 測定条件

- 測定 commit: `cc6d6610` (origin/main。コードは変更していない)。作業 worktree `ws-1161` (branch `1161-spill-coverage`)
- 素材: `work-m11` / `work-liftdiff` を `tar --zstd -xf` で展開 (gitignore 対象の `tools/m11/work/`・`tools/liftdiff/work/`)
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (foreground)
- 結果: rc=0、real 137 s、load average (uptime) 0.40 → 1.08
- 7/7 完了時に `spill178_1161.tsv` と `drops_510.tsv` が results/ と一致。実行後の `git status` は clean

## 2. 独立再計算・ネガコン (受入 4・5)

- 3/7 `window_recount.py`: window pairs 420 (210 関数)。データフロー側に無い対は 0 (`window_not_in_dataflow=0`)
- 6/7 `negctl_510.sh`: NC0 (無改変) と NC1〜NC7 の 8 本すべてが REPORT_510 §6 の期待どおり

## 3. 全数分類の現状と担当 (受入 1〜3 の残件)

spill 宛 unk site 178 (71 関数) の判定状態 (`results/spill178_1161.tsv`・7/7 出力)。確定 97 / 判定不能 16 / 未判定 65。

| 状態 | 範囲 | site | 担当 |
|---|---|---|---|
| 未判定 | 関数群 B (10c7cd0・1046a30・ddf630・6bb3f0・466af0・12cb680) | 32 | #2245 (LD-93) |
| 未判定 | c589b0・128f9e0 | 24 | #2288 (LD-104) |
| 未判定 | 旧 TRUE_DROP 保留 (775340 ほか 8 関数) | 9 | #2583 (LD-118) |
| 判定不能 | 候補 31 site 由来 (128c320・1280530・dcdde0・c343f0・128f9e0) | 7 | #2253 (LD-95) |
| 判定不能 | 上記以外 (41ba50・41bfa0・41e490・45b170・45c290・45d0a0・45d610・45f560) | 9 | LD-119 (新規起票) |

- 未判定 65 + 判定不能 16 は上表の 5 群で過不足なく覆われる (site 単位で突合済み)。
- 候補 31 site (`drops_510.tsv` の `source=candidate`) は 確定 24 / 判定不能 7 (#2253)。
- 脱落関数の和集合 (5/7・8/7 出力): 69 関数 (store 宛 DROP 51 ∪ spill 宛 22)。spill 宛の確定 TRUE_DROP は 21 関数で、drops_510 に無いのは 4120c0・41a5d0・6c3700 の 3 関数。未判定の決着で和集合は変わりうるため、最終化は LD-119 で行う。

## 4. 棚卸し

- #2312 (LD-105) の対象 cf3790 の 15 site は、`spill178_1161.tsv` で既に確定している (#2388 で完了・closed)。#2312 は open のまま残るため、PM が close を判断する。
- 判定不能 9 site と #1169 (LD-37) の対象が重なるかは未確認 (LD-119 の注意に記載)。

## 5. 再現

```
tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst
tar --zstd -xf $ARTIFACTS_DIR/work-liftdiff.tar.zst
bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh
```
