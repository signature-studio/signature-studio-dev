# REPORT #2266 — spill 宛 未判定 関数群 A (42 site) の IR 側突合 (分割)

親: #2244 (LD-92) / #2227 / #1161 (LD-35)。本 run は関数群 A の判定を 1 件も入れず、突合の入口と分割を残した。

## 1. 測定

- 測定 commit: 25d2cdc0 (run 開始時の main。本 PR の差分は `tools/m11/ldfix/REPORT_2266.md` のみ)
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (rc=0・所要 113s・7/7 完了・load average 0.90)
- 結果: `spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (cmp OK)。基準実測 (着手直後) と再測定で数値は同一
- 集計 (step 7/7): spill 宛 unk site 178 / 71 関数。status 未判定 120 / 確定 51 / 判定不能 7。脱落関数の和集合 69 (store 宛 51 ∪ spill 宛 22)
- コード差分: `git diff 25d2cdc0 HEAD -- tools/m11/ldfix` は本 PR で REPORT のみ追加 (分類スクリプト・results/ は変更なし)

## 2. 関数群 A の状況

| 関数 | 未判定 site | 既判定 site | IR 本体 | 機械語の型 |
|---|---|---|---|---|
| cf3790 | 18 | 6 (TRUE_DROP 3・OK_LOAD 2・NO_CONSUMER 1) | `function_cf3790` (401631〜402269) | `[rip+X]` slot 値 → 1 段 deref → `[rbp+disp]` store |
| c589b0 | 12 | 2 (候補 TRUE_DROP) | `function_c589b0` (390809〜) | slot `0x11e0ab0` の 1 段 deref |
| 128f9e0 | 12 | 1 (候補 UNDETERMINED) | `function_128f9e0` (76541〜) | slot `0x11e0ab0` の 1 段 deref |

- 機械語側の後続読み出しは #2244 の TSV で 42 site 全てに READ がある (NO_CONSUMER の根拠にならない)
- cf3790 の IR では、slot 値 `18745080` (0x11e06f8) と `18743568` (0x11e0110) の inttoptr load が 8 件あり、既判定 cf387f / cf38be / cf390f と同じく「slot 値を配列ポインタとして使い deref が落ちている」型と読める。ただし site ごとに機械語の frame store と IR の store 先を結んでいないため、本 run では判定を入れない
- c589b0 / 128f9e0 は IR の本体が `function_X` 側にあり、frame の store/load の形が cf3790 と異なる。同型の判定は行えなかった

## 3. 判定の結果

- 本 run で確定させた判定: **0 site** (`candidate_verdicts_1161.jsonl` は変更なし)
- 理由: 42 site の IR 対応 (機械語の `[rbp+disp]` store と IR の `stack_var` / reg2mem の対応) を 1 run の残り時間で site 単位に終えられなかった。根拠無しの判定は脱落集合を誤って確定させるため入れていない
- 注記: 作業中に「cf3790 の 3 site が確定」と書いた着手コメントは誤りで、既判定は 6 site (issue コメントで訂正済み)

## 4. 分割

| 子 | 関数 | site | 起票 |
|---|---|---|---|
| cf3790 の IR 突合 | cf3790 | 18 | #2287 (LD-103) |
| c589b0 ・ 128f9e0 の IR 突合 | c589b0 ・ 128f9e0 | 24 | #2288 (LD-104) |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| cf3790 の未判定 18 site | spill 宛の脱落関数の和集合 69 が未確定 | #2287 |
| c589b0 ・ 128f9e0 の未判定 24 site | 同上 | #2288 |
| 関数群 A の判定 (親) | #2244 の子として、判定 0 件のまま | #2266 (本 PR で部分達成) |
