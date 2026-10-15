# REPORT_APPENDIX_3161 — #3161 の boot5 × ld108 × LB 切り分けの補足 (REPORT_N403.md §10 の分割移動)

分割移動 (REPORT_N403.md が 250 行を超えるため)。§10-1 の表・§10-2・§10-3 の本体は REPORT_N403.md §10 に残す。
ここには分割前の §10 にあった以下の記述を、文面を変えずに移す (内容は削除していない。Git 履歴にも残る)。

## 10-1 の補足 (移動分)

- 1 通りの所要: IR 生成 46–47 s・build 22–24 s・run 1–2 s・survey 15–16 s。
- LB=0x10000 は boot5 有無で ok 870 の変化なし (boot5=0 の 2 通りは未測定)。

## 10-3 の補足 (移動分)

- 寛容起動の「ハング」(#2779 の子) とは別件か未確認。

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
