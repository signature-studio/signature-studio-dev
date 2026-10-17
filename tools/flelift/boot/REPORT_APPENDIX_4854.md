# tools/flelift/boot — #4854 付録: mode 3 の survey が InitTable 0 で測定不能 (補修と jsonl の残し方)

> 正本: `REPORT.md` §12 の全文の分割移動 (#6219 の round 1 指摘 1 による・内容は変えていない)。

## 12. #4854: mode 3 の survey が InitTable 0 で測定不能 (補修と jsonl の残し方)

- **結論**: 既定 (mode 3) の survey は補修 (`InitTable` を PKG へ戻す) ありで 942 件を判定 (ok 895 / empty 46 / noproc 1)。補修なしは `InitTable == 0` で不成立。補修が判定を変えるかは未切り分け (#4901)。受入 2 (旧 mode 0 との差) は #4901。
- 測定 commit: `a64aa3aab` (コードを変えた最後の commit。main 取り込み `db771b431` 後の HEAD)。差分 0 の証跡: `git diff a64aa3aab HEAD -- tools/flelift/boot ':!tools/flelift/boot/REPORT.md'` の出力 0 行 (本節の追記のみが REPORT の差分)。
- 素材: `fl-win64` (`FL_WIN64_DIR` に展開)・emsdk 6.0.12 (`[EMSDK]` を上流から取得して `SS_EMSDK_ENV` で指定)。

| 項目 | 結果 (HEAD `a64aa3aab`) |
|---|---|
| lift (closure 2・既定 root) | 50 s・29,910 関数 |
| clang plain (8 shard) | 50 s・mismatch 0 / undefined 0 / dup 0 |
| boot 既定 (mode 3・`--boot-only`) | units 895・stopped 895・`exit`・IPP check ok (ptr=0x7f10001c) |
| survey 既定 (mode 3・補修あり) | 1 セグメント・5〜6 s・ok 895 / empty 46 / noproc 1 (942 件)。jsonl 942 行 |
| survey 補修なし (`FLE_SURVEY_NOREPAIR=1`) | `InitTable == 0` で不成立 (`survey.error`) |
| survey mode 0 (`FLE_IPP=0`) | `InitTable == 0` で不成立。`survey_seg_0.json` の boot は units 209・exit code 0 |

- 未解決: 補修の判定への影響 → #4901 [FLE-33]。unit 280 / 659 / 895 の補修なし unlifted → #4855 [FLE-32]。注記 (load・mode 0 の未実施) は付録 §5。
