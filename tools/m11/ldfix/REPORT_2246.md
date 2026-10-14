# REPORT #2246 — spill 宛 未判定 関数群 C (38 関数・46 site) の消費者分類 (分割)

親: #2227 / #1161 (LD-35)。本 run は関数群 C の判定を確定させず、実測と分割を残した。

## 1. 測定

- 測定 commit: 92856da8 (run 開始時の main)。以後 `tools/m11/ldfix` の差分は 0 (`git diff 92856da8 HEAD -- tools/m11/ldfix` が空)
- 実行: `bash tools/m11/ldfix/audit_lsf_ssa_e2e.sh` (rc=0・所要 2m29s・7/7 完了・load average 1.10)
- 結果: `spill178_1161.tsv` と `drops_510.tsv` は results/ と一致 (cmp OK)
- 集計 (step 7/7): spill 宛 unk site 178 / 71 関数。status 未判定 120 / 確定 51 / 判定不能 7。脱落関数の和集合 69 (store 宛 51 ∪ spill 宛 22)

## 2. 群 C の確認

- 群 C = `spill178_1161.tsv` の status=未判定 のうち、群 A (#2244) と群 B (#2245) 以外の 38 関数・46 site
- 46 site の内訳: oracle `CELL_DEEP` 7 site / oracle 無し 39 site
- 機械語の後続読み出し (`audit_lsf.descend` で関数内を降下し、同じ frame slot の後続 `mov`/`cmp`/`lea` を列挙) は 46 site のうち 38 site で 1 件以上あり、NO_CONSUMER の根拠にはならない。後続読み出しが無い 8 site (`41ba50`・`41e490`・`44f440`・`6c3700` ×2・`6c3d20`・`6c5930`・`1042d20`) は、同一関数内の別経路で読まれる可能性が残るため判定しない
- 関数の IR 本体は `function_X__lifted` が正。`function_X` のみの wrapper が多い

## 3. 判定の結果

- 本 run で確定させた判定: **0 site**
- 理由: IR 側の store→load 対応 (値の出自の追跡) を site 単位で終えるには、46 site で 1 run の残り時間 (約 45 分) では不足した。根拠無しの判定は脱落集合を誤って確定させるため、jsonl には書いていない
- 試行の実測: 410770 4107c7 は IR の `stack_var_-16.0.reg2mem` 経由で store と reload が残る (機械語の後続 `mov rax,[rbp+0x38]` 4107ec に対応する消費者は IR に残存) ことを確認。ただし、これは確定判定の根拠として `candidate_verdicts_*.jsonl` に書くには、IR 側の値の出自 (load 由来か) の段数確認が残っている

## 4. 分割

| 子 | 関数 | site | 起票 |
|---|---|---|---|
| 前半 | 410770 〜 45f560 (19 関数) | 23 | #2264 (LD-97) |
| 後半 | 4fa3d0 〜 12f9730 (19 関数) | 23 | #2265 (LD-98) |

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 群 C 46 site の機械語・IR 両面の分類 | spill 宛の脱落関数の和集合 69 が未確定 | #2264 (前半) / #2265 (後半) |
| UNDETERMINED 7 site の IR 側再検証 | 同上 | #2253 (LD-95・既存) |
| 群 A / 群 B の分類 | 同上 | #2244 / #2245 (既存) |
