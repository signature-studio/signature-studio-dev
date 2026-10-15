# M11 REPORT (#4891 / [M11-N227] / 親 #3907): set_other 非 imm の lea GEP 17 件と書込可能グローバル 3 件の接続判定

結論: 台帳の gep 17 件と global_store 3 件を 3 値で判定した。実測は **実値化 0 / 復元不能 0 / 未決 20 / 未分類 0**。IR には接続していない。gep は基底 reg の SSA 値の対応付け、global_store は格納値の到達定義が未実装で、どちらも未決のまま残し、子 #4905 ([M11-N228]・gep)・#4906 ([M11-N229]・global_store) に移した。

## 1. 入力と手順

- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774ded8aaf717…`・REPORT_N171 と一致)。PE は `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da40921cf26…`・一致)。
- 手順 (HEAD の script のみ・`tools/m11/work/` 内):
  1. `python3 ../m11_post.py boot_final.ll sigfix_stats/final3_base.ll --pads sigfix_stats/pads.json` → 0 詰め call site 1049・引数 2064 (REPORT_N202 と一致)。
  2. `python3 ../m11_argrecover.py sigfix_stats/pads.json --pe $PE --out sigfix_stats/fixes.json` → const 復元可能 fixes 33 (REPORT_N98 と一致)。
  3. `python3 ../m11_setother_nonimm_class.py sigfix_stats/fixes.json --pe $PE --ir boot_final.ll` → 非 imm 349 件・未決 349 (REPORT_N171 と一致)。
  4. `python3 ../m11_setother_mem_class.py sigfix_stats/nonimm_class_rows.json --pe $PE` → 対象 257 件・実値化 8・未決 249・未分類 0。接続方式 gep 17・global_store 3 (REPORT_N174 と一致)。
  5. `python3 ../m11_setother_gep_global.py sigfix_stats/mem_class_rows.json --ir sigfix_stats/final3_base.ll --out sigfix_stats/gep_global_rows.json` → 対象 20 件・実値化 0・復元不能 0・未決 20・未分類 0 (本 PR の分類器)。

## 2. 測定結果 (受入 1)

| 接続方式 | 件数 | 区分 | 理由 |
|---|---|---|---|
| gep (`lea [reg+d]`) | 17 | 未決 17 | `base_ssa_unmapped`: 基底 reg の SSA 値の対応付けが未実装 |
| global_store (`mov r, qword ptr [rip+d]` の `.data`) | 3 | 未決 3 | `no_store_in_ir`: 3 件とも同じ VA `0x15e3a70` を読むが、IR 全体でこのアドレスへの store は 0 件 |
| 合計 | 20 | 実値化 0・復元不能 0・未決 20・未分類 0 | |

- **実測と呼べるのは、対象 20 件 (gep 17・global_store 3) と各行の理由 (`base_ssa_unmapped` 17・`no_store_in_ir` 3) だけ。**
- 実値化 0・復元不能 0・未分類 0 は実測ではなく、分類規則から決まる値。`m11_setother_gep_global.py` は全分岐で `class` を `'未決'` に固定しており、実値化の経路が無い。未分類は `len - 実値化 - 復元不能 - 未決` なので、必ず 0 になる。復元不能も判定規則が無いため 0 になる。
- 実値化 0 件のため、`m11_argrecover_verify.py` で照合する値は無い (該当なし)。

## 3. 接続方式 (受入 2)

- gep 17 件: 接続先は「基底 reg の SSA 値に対する GEP」。基底 reg の直前定義を辿る到達定義は未実装のため、対応付けは未決 (`base_ssa_unmapped`)。
- 参考 (手作業の数字・再現不可): 17 件の caller 内の `getelementptr` 行を手で数えたところ、0〜2 件 (`function_a981f0` 2・`function_ff0600`・`function_ff0d70` 各 1、他は 0)。**この数字は `m11_setother_gep_global.py` の出力に含まれず、本 PR の手順でも再現できない。** 数え方の手順も残していない。本 run では `tools/m11/work/` が無く IR を再確認できないため、この数字は根拠として使わない。
- 参考 (手作業の数字・再現不可): global_store 3 件が読む VA `0x15e3a70` について、`function_6520b0` の `inttoptr` を経由した load が IR 内に 1 箇所あるとの確認も、手作業の数字。スクリプトは出力しない。
- global_store 3 件: 分類器の出力では `store_count` が 0 (`no_store_in_ir`)。3 件とも同じ VA `0x15e3a70` を読む。`store_count` が 0 のとき `store_fns` は空になる。計算で作ったアドレスによる store は、この照合では見えない。格納の探索を IR 全体・呼出し元の外へ広げる必要がある (子 #4906)。

## 4. 検証と限界

- 分類器 `m11_setother_gep_global.py` は IR を変えない。判定は store の有無と理由の割当だけで、値は決めない。
- 件数の再現: 手順 1〜4 の実測は REPORT_N171・N174 と一致 (349・257・実値化 8・gep 17・global_store 3)。
- 範囲外: gep 17 件の基底 SSA 対応付け (子 #4905)、global_store 3 件の格納値の到達定義と呼出し元外の格納探索 (子 #4906)。
- 未検証の前提: `target_va` は `def + 7 + disp` で、命令長を 7 バイトと固定している (`mov r64, [rip+d32]` を想定)。`m11_setother_mem_class.py` のように命令長を逆アセンブルで取ってはいない。今の 3 件 (qword) では影響しない想定だが、本 run では入力が無く確認していない。
- 測定経路の差分: 本 PR は `tools/m11/m11_setother_gep_global.py` と本 REPORT の追加のみ。前段 (`m11_post.py`・`m11_argrecover.py`・`m11_setother_nonimm_class.py`・`m11_setother_mem_class.py`) は変更していない。e2e 経路には入らないため e2e は実行していない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| gep 17 件の基底 reg の SSA 値への対応付けと GEP の接続 | 受入の『接続』の残り 17 件 | #4905 (M11-N228) |
| global_store 3 件の格納値の到達定義と、呼出し元外の格納探索 | 受入の『接続』の残り 3 件 | #4906 (M11-N229) |
