# REPORT #2287 — cf3790 の未判定 18 site のうち 3 site の判定 (部分達成)

親: #2266 (LD-99) / #2244 (LD-92) / #1161 (LD-35)。本 run は cf3790 の未判定 18 site のうち **3 site (cf3c7a・cf3cbb・cf3d20) だけ** に判定を入れた。残り 15 site は子 issue に分割した。

既知類型との関係: DEFECTS.md の D17 系 (spill 宛の脱落。#1161 の分類と同じ枠)。新規類型なし。

## 1. 測定

- 測定 commit (コードを変えた最後の commit): `d96d4a97` (判定 3 件とスペル TSV の更新)。後続の `0b5edbd9` は REPORT の表の 1 行だけで、`git diff d96d4a97 HEAD -- tools/m11/ldfix` は REPORT_2287.md の表記のみ (コード・判定・TSV は差分 0)。
- 基準 (origin/main e53d845b・判定変更前): `audit_lsf_ssa_e2e.sh` の step 7 で status 未判定 120 / 確定 51 / 判定不能 7 (`results/spill178_1161.tsv` 元の集計)。
- 測定 (d96d4a97): `M11_WORK=<main の tools/m11/work> LD_WORK=<main の tools/liftdiff/work> bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` rc=0・所要 112 s (11:38:28〜11:40:20 実測)・7/7 完了・load average 0.91・`results/` と cmp 一致。status 未判定 **117** / 確定 **54** / 判定不能 7。増分は判定 3 件 (cf3c7a・cf3cbb・cf3d20) のみ。
- step 6 ネガティブコントロール (negctl_510.sh) は両回とも完了し、rc=0 (NC1〜NC7)。
- step 7 の `results/spill178_1161.tsv` は再生成して cmp 一致 (差分は 3 行の status 変化だけ)。

## 2. cf3790 の未判定 18 site の状況

| 状態 | site | 根拠 |
|---|---|---|
| 判定済み (TRUE_DROP・類推) | cf3c7a・cf3cbb・cf3d20 | 機械語の slot (0x15E0110 / 0x15E06F8) の 1 段 deref → IR の同じ slot 定数の load が `icmp`/`add -8` に使われる。既判定 cf387f / cf38be / cf390f と同型。`candidate_verdicts_1161.jsonl` に根拠行を追加 |
| 未判定 (残 15 site) | cf3b03・cf3b54・cf3b62・cf3baf・cf3bbd・cf3c0e・cf3c1c・cf3dfa・cf3e08・cf3e7a・cf3e88・cf3f47・cf3f55・cf3fd3・cf3fe1 | 機械語は `[rbp+0x178]` 系の要素アドレス経由 (cf3b03〜cf3c1c・cf3baf〜)・rip slot 経由 (cf3dfa・cf3e7a・cf3f47 等) のどれも後続 READ がある (`ld92_machine_evidence.tsv`)。IR 側は reg2mem の store→load 結線を site ごとに取る必要があり、本 run では未完 |

- 判定の根拠は「同じ slot・同じ型」の類推である。reg2mem の store→load の結線 (`stack_var_-N` の対応) は 3 site とも未確認。REPORT_510 の目視判定と同じ粒度に揃えるには、子 issue で結線を取る。
- 残り 15 site の NO_CONSUMER 判定は、機械語の後続 READ があるため現時点では根拠が無い (根拠無しの判定は入れない)。

## 3. 作業上の注意

- 最初の 3 行を共有 main ワークツリーの `candidate_verdicts_1161.jsonl` に追記した (規約違反)。直ちに main 側を `origin/main` の内容へ戻し (`cmp` 一致を確認)、3 行は worktree 側で書き直した。main の既存の未コミット変更 (`package.json`・`pnpm-lock.yaml`) には触れていない。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| cf3790 の残り 15 site の IR 側突合と判定 (reg2mem の結線) | spill 宛の脱落関数の和集合 69 が未確定 (cf3790 は判定が揃うまで未確定) | #2312 (LD-105) |
| 判定 3 件 (cf3c7a・cf3cbb・cf3d20) の reg2mem 結線 | 類推のままの判定。結線が取れなければ覆る | #2312 (LD-105 の受入条件に含む) |
| c589b0・128f9e0 の未判定 24 site | 同上 | #2288 (LD-104) |
