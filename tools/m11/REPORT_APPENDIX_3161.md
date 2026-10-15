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

## 10-7 unit 296 の機構 (#5274・2026-10-15 実測・部分)

測定: `FL_WIN64_DIR=<展開先> M11_SURVEY_PROGRESS=1 bash tools/m11/m11_lb_matrix.sh 0 1 <LB>` (fl-win64・work-m11 を展開した snapshot・runner 4 core・load 0.8〜1.7)。

| 条件 | 結果 | IR sha (先頭12) | gen / build / run / survey 秒 |
|---|---|---|---|
| boot5=0 ld108=1 LB=0x10000 | rc_survey=124 (600 s 打ち切り)・`unit 296 0x456130 begin` の後 `end` 無し | 400a8b7b2780 | 47 / 24 / 1 / 600 |
| boot5=0 ld108=1 LB=0 | rc_survey=0・942 unit 完走 (unit 296 は `0x446130` で begin/end) | af3e9e05e8e1 | 46 / 24 / 1 / 12 |

- IR sha は §10-6 の値 (31bcfaa2b145・a58ac284416b) と違う。`ir_conditions.json` が生成時の PE パスを記録するため、展開先が違うと sha も変わる (推定。未確認)。
- 単独再現: `M11_SURVEY_END=297 M11_TRACE=1` で unit 0〜296 だけを流すと、unit 296 が begin の後 120 s 戻らない (unit 0〜295 は 0.4 s)。前の unit の副作用ではない。
- アドレス対応: unit の proc は LVA `0x456130`。LVA = RVA + LB (LB=0x10000) なので RVA `0x446130`、VA `0x846130`。LB=0 の unit 296 (LVA `0x446130`) も同じ VA。IR に `function_846130` が存在する (67 行の one-shot 初期化、ガードは `[0x1200...]`)。
- unit 296 の呼出し先のうち、ループを持つのは 2 つ: `function_4123c0` (カウンタ `rdi` で必ず終わる) と `function_4fb780` (連結リストの走査。終了は番兵 `icmp eq i64 %…, 5028360` (VA `0x4cba08`) との一致か、`function_4fb000` の戻り値)。
- 番兵の仮説を 1 行だけ試した: `icmp eq ... 5028360` を LVA `5093896` (+0x10000) に置いて build・survey → **unit 296 は依然として戻らない** (survey rc=124・300 s 打ち切り)。番兵だけが原因ではない。
- 観測した事実: `pass_m2`・`pass_m2p`・`pass_m2b` (m11_passes.py) は `inttoptr`・`store`・`add`/`sub` の即値 VA だけを LVA に remap し、`icmp` の即値は remap しない。LB=0x10000 の IR で、image 範囲の `icmp eq/ne i64 … , <即値>` は 49 件 (うち `0x4cba08` は 1 件)。残り 48 件が非ポインタの比較か (未確認)。
- 未解決: 止まっている関数 (`function_4fb780` か `function_4123c0` か、それ以外か) と停止の機構。次に要るもの: 停止中の呼出しスタック (`M11_SURVEY_STACK` 相当を unit 296 だけに効かせた trap 取得、または `4fb780` の反復回数の計測)。この run では時間が足りず打ち切った。
- 測定の副産物: `tools/m11/m11_survey.mjs` に `M11_SURVEY_FROM`・`M11_SURVEY_END` (既定 0・942。既定の挙動は不変) を追加した。単独再現に使った。
