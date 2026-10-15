# REPORT_APPENDIX_3161 — #3161 の boot5 × ld108 × LB 切り分けの補足 (REPORT_N403.md §10 の分割移動)

分割移動 (REPORT_N403.md が 250 行を超えるため)。§10-1 の表・§10-2・§10-3 の本体は REPORT_N403.md §10 に残す。
ここには分割前の §10 にあった以下の記述を、文面を変えずに移す (内容は削除していない。Git 履歴にも残る)。

## 10-1 の補足 (移動分)

- 1 通りの所要: IR 生成 46–47 s・build 22–24 s・run 1–2 s・survey 15–16 s。
- LB=0x10000 は boot5 有無で ok 870 の変化なし (boot5=0 の 2 通りは未測定)。

## 10-3 の補足 (移動分)

- 寛容起動の「ハング」(#2779 の子) とは別件か未確認。

## 10-5 LB=0x10000 × boot5=0 の 2 通り (#4386 の再測定)

測定主体: #4386 の run (2026-10-15, runner 1 台, load 1.0〜1.1)。素材: fl-win64・work-m11 (展開済み snapshot)。`--full` の lift 成果物は使わず、snapshot の `boot0〜4.lift.ll` から driver (`m11_lb_matrix.sh`) を実行 (`boot5.lift.ll` は snapshot に無く、boot5=0 の経路のみ)。測定 commit: ced43062c (survey の進捗ログ追加のみ。既定 off で挙動は変わらない)。

| boot5 | ld108 | LB | IR sha (先頭12) | gen / build / run 秒 | rc_run | rc_survey | 通常起動 | survey |
|---|---|---|---|---|---|---|---|---|
| 0 | 1 | 0x10000 | 31bcfaa2b145 | 41 / 23 / 1 | 0 | 124 (600 s 打ち切り) | units_run 36・Halt0 1・longjmp 1 | 出力 0 行 (`M11_SURVEY` 無し) |
| 0 | 0 | 0x10000 | 57811d278766 | 41 / 22 / 1 | 0 | 124 (600 s 打ち切り) | 同上 | 出力 0 行 |

- 進捗ログ (`M11_SURVEY_PROGRESS=1`・stderr の unit 番号) で止まり位置を特定: unit 0〜295 は 0.44 s で完了し、unit 296 (`0x456130`) に入ったまま戻らない (150 s の単独再現でも同じ位置)。`LBM_RESULT` が出なかった前回 (§10-3) とは違い、今回は段の失敗ではなく survey の打ち切りである。
- 比較: boot5=1 の LB=0x10000 は §10-1 のとおり完走 (ok 870 / trap 25)。boot5=0 の LB=0x10000 でだけ unit 296 が戻らない。unit 296 が無限ループか極端な遅さかは未確認 (呼出元の trap スタックは取れていない)。
- 未解決: unit 296 の停止原因 (boot5=0 × LB=0x10000 固有)。受入 2 の寄与差 (4 通りの ok/trap) は、この unit を抜けなければ測れない。起票先: 子 issue (本 PR の未解決表を参照)。

## 10-4 結論 (この run の範囲)

- 受入 1: 8 通り中 6 通りを `--full` の IR で実測。未測定 2 通りは REPORT_N403 §10-3。
- 受入 2: 答えは「同じ unit ではない」(REPORT_N403 §10-2)。
- 受入 3: 未達。`--full` の IR での値 (LB=0 873/21・LB=0x10000 870/25) は #403 の引用値と異なる。

## 10-6 unit 296 の挙動 (#4639・2026-10-15 実測)

- 測定: `M11_SURVEY_PROGRESS=1 bash tools/m11/m11_lb_matrix.sh 0 1 <LB>` (boot5=0・ld108=1・fl-win64 展開済み・load 1.00〜1.05・runner 4 core)。
- LB=0x10000: `LBM_RESULT rc_survey=124 survey_s=600`。進捗ログで unit 0〜295 は完了し、`unit 296 0x456130 begin` の後 `end` が出ない (2 回再現)。
- LB=0: `LBM_RESULT rc_survey=0 survey_s=16`・`LBM_SURVEY units=942 ok=873 noproc=1 miss=47 trap=21`。同じ unit 296 は `0x446130 begin/end` で戻る。
- IR sha: LB=0x10000 = `31bcfaa2b145`・LB=0 = `a58ac284416b`。
- 観測した事実: unit 296 は LB=0x10000 の LVA `0x456130` で、LB=0 の `0x446130` と同じ PE 位置 (+0x10000 ずれ)。
- 未特定: 無限ループか極端な遅さかの区別、LB 依存で挙動が変わる機構。`m11_survey.mjs` に `M11_SURVEY_PROGRESS=1` (unit ごとの begin/end を stderr へ同期出力) を追加して測定に使った。
