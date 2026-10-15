# M11 REPORT (#3933 / [M11-N202] / 親 #3906): set_other スタック slot 未決 85 件の再測定と C 規則の突合

結論: 現 HEAD (`m11_post.py`・`m11_setother_nonimm_class.py` は `fe41cc75` から変更あり) で `work-m11` を入力に再測定した。対象は **112 件** (N196 の 110 件より 2 件多い)。件数は **実値化 25・復元不能 0・未決 87・未分類 0**。C 規則 (`stack_var_(d−C)`) の IR 突合は、既存 call に引数が無いため引数単位では **0 件** しか確認できず、名前単位では 22 件 (一意な (呼出し元, alloca)) が同じ関数内で参照されていた。未決 87 件の接続先 (slot_merge・slot_call) は未決定で、子 issue に移す。

## 1. 入力と手順

- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774ded8aaf717…`・REPORT_N171 と一致)。PE は `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da40921cf26…`・一致)。
- 手順 (すべて HEAD の script):
  1. `python3 m11_post.py boot_final.ll sigfix_stats/final3_base.ll --pads sigfix_stats/pads.json` → 1049 site・0 詰め引数 2064。出力 sha256 `c029ada4…` (REPORT_N86 §4 の `ecab191b…` とは不一致。site 数は一致)。
  2. `python3 m11_argrecover.py sigfix_stats/pads.json --pe <PE> --out sigfix_stats/fixes.json` (27 秒)。
  3. `python3 m11_setother_nonimm_class.py sigfix_stats/fixes.json --pe <PE> --ir boot_final.ll` → 非 imm 349 件・未決 349 (N171 と一致)。`nonimm_class_rows.json` 112 件の内訳は lea_stack 59・mem_stack/load_stack 50・reg 3。
  4. `python3 m11_setother_slot_class.py nonimm_class_rows.json --pe <PE> --ir boot_final.ll --out mem_class_rows.json` (0.4 秒)。
  5. `python3 m11_setother_slot_check.py mem_class_rows.json --ir boot_final.ll` (本 PR の検算スクリプト)。

- 測定 commit: 本 PR の HEAD。測定経路の差分は `git diff fe41cc75 HEAD -- tools/m11/m11_post.py tools/m11/m11_argrecover.py tools/m11/m11_setother_nonimm_class.py tools/m11/ldfix/ldmach.py` の 3 ファイル 146 追加・10 削除 (§4)。N196 の「差分 0」は現 HEAD では成り立たない。

## 2. 測定結果 (受入 1)

| 区分 | 件数 |
|---|---|
| 実値化 | 25 (lea_alloca) |
| 復元不能 | 0 |
| 未決 | 87 |
| 未分類 | 0 |
| 合計 | 112 |

未決の理由別 (`m11_setother_slot_check.py` の出力):

| 理由 | 件数 |
|---|---|
| lea_alloca_absent | 34 |
| slot_merge | 22 |
| slot_call | 17 |
| no_frame | 6 |
| slot_unknown_write | 3 |
| slot_ptr_write | 2 |
| slot_alias_base | 1 |
| slot_reg | 1 |
| no_mem_operand | 1 |

N196 (110 件) との差 2 件: 現 HEAD の `m11_setother_nonimm_class.py` は台帳 reg 行に `call_ret>ret>load_stack` を 2 件出す (N196 の台帳の内訳 lea 59・load_stack 50・chain>load_stack 1 には無い)。この 2 件の分類結果は no_frame 1・no_mem_operand 1 (未決)。未決の合計は 85 → 87。理由別の差は次のとおりで、2 件の増加だけでは説明できない: slot_unknown_write 0 → 3 (`8391cf741` の set*・kind=other の打ち切りによる理由の移動)、slot_merge 23 → 22、slot_call 19 → 17 (reg 1 件を含む)、no_frame 5 → 6 (reg 1 件を含む)。N196 の測定 commit `fe41cc75` と HEAD で分類器が違うため、理由の移動は分類器の変更による。実値化 25 は両方で一致する。

## 3. C 規則の IR 突合 (受入 2)

検算 (`m11_setother_slot_check.py`) の 2 段階:

| 段階 | 結果 | 読み |
|---|---|---|
| 引数単位: 実値化 25 件の対応する既存 call の引数に `%stack_var_X` が現れるか | only_argless_call 25 (一致 0・不一致 0) | 呼出し元 IR の対象 callee への call は、いずれも `call @f()` (引数 0 個)。0 詰め引数は IR に出ない (`m11_post.py` の 0 詰め call site 1049 と整合) |
| 名前単位: 一意な (呼出し元, alloca) 22 件の alloca 名が同じ関数内で他の命令に参照されるか | ref_elsewhere 22 (alloca_only 0) | 名前の存在は確認できた。ただし参照先が C 規則で正しいかは判定できない |

- 引数単位の突合は**原理的に不可能**だった。0 詰めの引数が IR から落ちているため、既存 call の引数と照合する対象がない。
- 名前単位の 22 件は、alloca 名が偶然一致した場合も含む。「C 規則がずれている」か「alloca が無い」かは切り分けていない。

## 4. 検証と限界

- **負例・検算の独立性**: 名前単位の突合は N196 の検算 (`stack_var` 名の存在) と同じ入力の上の判定で、独立な算法ではない。引数単位は既存 call の構造に依存する。
- **範囲外**: 未決 87 件の接続先 (slot_merge 22・slot_call 17・no_frame 6 ほか) の決定は本 PR では行っていない。CFG 到達定義・call を越える格納探索は未実装。
- **分類器の変更**: `m11_setother_slot_class.py` の `load_def` は N196 から変更していない。変わったのは台帳 (`nonimm_class_rows.json` の reg 行) のみ。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未決 87 件の接続先 (slot_merge 22・slot_call 17) の決定 (CFG 到達定義・call 越えの格納探索) | 85 件の受入 1 の残り | 子 issue (本 PR で起票) |
| lea_alloca_absent 34 件 (alloca 不在の理由の切り分け) | 接続先が無い | 子 issue (本 PR で起票) |
| C 規則の正しさ (名前単位の 22 件が正しい alloca か) | 接続 25 件の正しさが名前の存在だけで確認されている | #3932 (M11-N201) の IR 注入と survey で確認 |
| `m11_post.py` 出力 sha が N86 の `ecab191b…` と不一致 | 測定の再現性 (site 数は一致) | #3933 (本 PR の REPORT。原因の切り分けは未実施) |
