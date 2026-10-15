# tools/flelift/boot — REPORT §13 付録 (#4931): 既定経路 (mode 3) の survey で 942 unit を分類

> 正本: 本ファイル。REPORT.md §13 の全文を分割移動した (内容は削除していない。行数上限 250 行・`docs/DOC_MAP.md` §1)。

## 1. 結論

- 既定経路 (`FLE_IPP` 未指定・補修あり) の survey で 0〜941 の 942 unit を分類した (ok 895 / empty 46 / noproc 1)。`merge_survey.py` の covered は 942。#4931 の前提「mode 3 の survey は測定不能」は、REPORT §12 の補修 (#4854) で解消済み。
- 測定 commit: `ceb5a0ba6` (main 取り込み後・flelift 差分 0 の HEAD)。main の `1ff7c6880` でも同じ結果 (ok 895 / empty 46 / noproc 1) を先に得ている。
- 素材: `fl-win64` (`FL_WIN64_DIR` = `$RUNNER_TEMP/fl-win64`)・`[EMSDK]` (既存)。
- 再現: `FL_WIN64_DIR=... FLE_EXTRA_ROOTS= FLE_BOOT_RUNS=default FLE_BOOT_TAG=s4931 bash tools/flelift/boot/fle6_measure.sh` → `bash tools/flelift/boot/survey_drive.sh 150 20` → `python3 tools/flelift/boot/merge_survey.py`。

## 2. 実測表 (HEAD `ceb5a0ba6`)

| 項目 | 結果 |
|---|---|
| lift (closure 2) | 63 s・29,909 関数・traps 0 |
| clang plain (8 shard) | 74 s・mismatch 0 / undefined 0 / dup 0・RSS 最大 2.6 GB |
| boot 既定 (mode 3) | units 895・`exit`・IPP check ok (ptr=0x7f10001c)・最初のウィンドウ無し |
| survey 既定 (1 セグメント) | 7.6 s・ok 895 / empty 46 / noproc 1 (942 件・jsonl 942 行・重複 0) |
| `merge_survey.py` | `covered=942` |

- 負荷: 測定時の loadavg 1.8 前後 (4 コア)。
- 集計の規則テスト: `tools/flelift/tests/merge_survey_test.py` (合成 jsonl)。正しい規則で `covered=942`。empty/noproc を落とす変異を入れると `covered=917` になり失敗する (規則を壊すと落ちることを確認)。

## 3. 測定後の差分確認 (WORKFLOW §6)

- 測定 commit `ceb5a0ba6` から本 PR の HEAD までの、測定対象のコード差分:
  `git diff ceb5a0ba6 HEAD -- tools/flelift/boot tools/shimx tools/shared` の出力 **0 行**。
- `tools/flelift/tests/merge_survey_test.py` は本 PR で新規に追加したテストで、測定対象 (`tools/flelift/boot`・`tools/shimx`・`tools/shared`) の外にある。測定の値そのものは変えていない。
- `tools/flelift/boot/results/` の survey 結果 (`survey.json`・`survey_seg_0.*`) は測定の出力であり、コードではない。

## 4. 件数の違い (issue #4931 タイトルとの対応)

- 起票済み issue #4931 のタイトルは「empty / noproc 37 件」だが、実測は **47 件** (empty 46 + noproc 1)。タイトルの 37 は実測と合わないため、実測の 47 を正とする。判定の内訳は ok 895 / empty 46 / noproc 1 (942 件)。

## 5. 未解決

- 補修 (`InitTable` を PKG へ戻す) が判定を変えるか → #4901 [FLE-33]。
- unit 280 / 659 / 895 の補修なし unlifted → #4855 [FLE-32]。
- mode 0 との差分 (受入の旧比較) は本付録の対象外 (#4901)。

## 6. 補足: 測定 commit と起動指標

- `tools/startup/boot_metric.json` の `x64c-isolated-survey` は、`survey.json` (`byCls` = ok 895 / empty 46 / noproc 1) から再算出した。変更前の記録は ok 892 / failed 3 (`unlifted` 3)、変更後は ok 895 / failed 0。
- `unlifted` キーは本 survey では 0 件のため、欠損は 0 として扱うよう `tools/startup/boot_metric.py` の `_x64c_survey` を直した (合計の検査 `byCls 合計 = units_covered` は残す)。main の同関数も同じ検査で止まっていた。
- 起動の記録への当たり方: survey の `unlifted 3 → ok` は、既定経路 (mode 3・補修あり・`0x976da0` root 化) の測定結果が survey に入ったことによる。この既定経路の変更は main に既に入っており (REPORT §0 の PM 判断 2026-10-15)、本 PR のコード変更によるものではない。boot の既定 units 895 は本 PR の前後で変わらない。
- したがって `boot_metric: unchanged` ではなく、`boot_metric.json` を再生成して同じ PR に含める。
