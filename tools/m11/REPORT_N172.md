# M11 REPORT (#3140 / [M11-N172] / 親 #3134・#1154): set_other 非 imm reg 引数 merge 34 件の CFG 到達定義

結論: `REPORT_N171.md` §3 で「分岐先越え (merge)」として #3140 に残した reg 引数 34 件を、基本ブロックの predecessor を辿って判定した。測定 commit `9b205ba79` の実測は **実値化 1 / 復元不能 0 / 未決 33 / 未分類 0** (§2)。実値化は 1 件 (`function_f6bb50` → `function_cd1c20` の pos 1 = rdx = 0・§3 で機械語照合)。未決 33 件は接続先 #3141 (10)・#3142 (16)・#1154 (7) に分けた (§5)。IR は変えていない (分類のみ)。

## 1. 方式

- 対象: `nonimm_class_rows.json` の reason が `merge`・`merge_at_call`・`chain>merge` の reg 行 (pos 0〜3)。34 件すべて reg。
- 状態 `S(i, fam)` = 命令 i の直前で族 fam が持つ到達定義の葉の集合。分岐先 (直接 jump の飛び先) は全 predecessor の「直後の状態」の和集合。直線部分は後ろ向きに 1 本だけ追い、分岐先に着いた時点で join する。
- 葉の定義の読み方は `m11_setother_nonimm_class.py` と同じ (全幅 mov imm・xor・全幅 copy・movzx/movsx と即値 add/sub/and/or の連鎖)。
- call: rax は戻り値 (葉 `call_ret`・未決)。その他の揮発族は壊れる (葉 `call_clobber`・復元不能)。
- 区分: 全葉が同じ定数 → 実値化 (`cfg_agree`)。葉に `call_clobber` がある → 復元不能 (ABI 上その経路の値が保証されない)。他 → 未決 (`merge>` + 葉の理由)。
- 循環: 戻り辺で同じ (分岐先, 族) に戻る経路は寄与を空にする (葉の最小不動点)。循環を通った途中結果はメモしない。
- 間接 jmp: 関数内の間接 jmp は分岐先を `merge_indirect` で未決にする。今回の 34 件はいずれも関数に間接 jmp が無かった (`indirect` 0 件)。
- 初版は循環の戻り辺を `loop` 葉にしたため、定義が循環で変わらない経路まで未決になった。最小不動点に直して 1 件が実値化した (§6 の cross-check は修正後の版で実施)。

## 2. 測定 (HEAD の実測)

- 測定 commit: `9b205ba79` (コードを変えた最後の commit。`git diff 9b205ba79 HEAD -- tools/m11 ':(exclude)*.md'` は 0 行)。
- 入力: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 `69c774de…`)・PE は `fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。
- 再現手順 (`tools/m11/` で実行。`work/sigfix_stats/` は gitignore):
  1. `python3 m11_post.py work/boot_final.ll work/sigfix_stats/final3_base.ll --pads work/sigfix_stats/pads.json` → sha `ecab191b…` (REPORT_N86 §4 と一致)。
  2. `python3 m11_argrecover.py work/sigfix_stats/pads.json --pe <PE> --out work/sigfix_stats/fixes.json` → 非 imm 349 (reg 123・mem 150・lea 76)。
  3. `python3 m11_setother_ledger_verify.py work/sigfix_stats/fixes.json --pe <PE>` → `match 410`・exit 0。
  4. `python3 m11_setother_nonimm_class.py work/sigfix_stats/fixes.json --pe <PE>` → 実値化 0 / 復元不能 0 / 未決 349 (REPORT_N171 §2 と一致)。
  5. **`python3 m11_setother_nonimm_cfg.py work/sigfix_stats/fixes.json --pe <PE>` (本 PR の判定器)**。所要 1.9 秒 (4 vCPU・load 0.12〜0.19)。

| 元の理由 | 区分理由 | 区分 | 件数 |
|---|---|---|---:|
| merge | cfg_agree (全葉が定数 0) | 実値化 | 1 |
| merge | merge>call_ret | 未決 | 9 |
| merge | merge>entry | 未決 | 4 |
| merge | merge>load_ptr | 未決 | 10 |
| merge | merge>load_stack | 未決 | 1 |
| merge_at_call | merge>entry | 未決 | 3 |
| merge_at_call | merge>load_ptr | 未決 | 5 |
| chain>merge | merge>chain>call_ret | 未決 | 1 |
| **合計** | | **実値化 1 / 復元不能 0 / 未決 33 / 未分類 0** | **34** |

## 3. 実値化 1 件の機械語照合

- 対象: `function_f6bb50` → `function_cd1c20` の k=0・pos 1 (rdx)。判定値 `0x0`。
- 機械語 (`objdump -d block00031_PE.bin --start-address=0xf6bd0d --stop-address=0xf6bd6b`): `f6bd0d xor %ebx,%ebx` → (`f6bd33` の分岐先。経路は `f6bd20` の jmp と `f6bd2e` の fall-through の 2 本で、どちらも `call` の後に入る。Win64 では rbx は呼出し越えで保存される) → `f6bd47 mov %ebx,%edx` → `f6bd66 call cd1c20`。`f6bd47`〜`f6bd66` で rdx を書く命令は無い。よって rdx = 0。
- 葉は `xor` 1 つ (`0xf6bd0d`) のみ。`f6bd0d` は分岐先だが `xor` 自身が書くので、その後の状態は全経路で 0。
- `m11_argrecover_verify.py` は未実行。直線区間の 1 命令の定数代入だけを照合する検算で、分岐先と `mov` 連鎖を扱えないため対象外 (不一致ではない)。上の機械語照合を代替とした。

## 4. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 34 件を 実値化 / 復元不能 / 未決 の 3 値で件数実測、未分類 0 | **達成** | §2 (1 / 0 / 33 / 未分類 0) |
| 2. 実値化値を `m11_argrecover_verify.py` で照合 | **代替** (verify.py は対象外・未実行) | 1 件を §3 の機械語で手動照合 (一致)。自動照合の拡張は §6 |
| 3. survey ok ≥ 870 | **除外** (#1154 へ移した) | 素材 `functions_dll.csv` の欠落で測れない (`REPORT_N171.md` §6)。IR を変えていないため本 PR の影響も無い |

## 5. 未決 33 件の接続先 (IR 側で何を接続すれば決まるか)

| 区分理由 | 件数 | 接続先 |
|---|---:|---|
| merge>call_ret・merge>chain>call_ret (戻り値の定義) | 10 | #3141 (M11-N173) |
| merge>load_ptr・merge>load_stack・merge_at_call>load_ptr (メモリ読込) | 16 | #3142 (M11-N174) |
| merge>entry・merge_at_call>entry (呼出元の def) | 7 | #1154 |

10 + 16 + 7 = 33。実値化 1 を足して 34。

## 6. cross-check と限界

- 同じ判定器を、`m11_setother_cfg_value.py` (#1867) の入力 (imm 非定数の reg 行 46 件) に当てた: 実値化 0 / 未決 46。既存の `cfg_value` の reg 行 (decided 0 / undecided 46) と一致。理由の分類は異なる: `cfg_value` は 8/16bit 部分書込の旧値を辿って `call_clobber` を返すが、本判定器は部分書込を `partial_imm` の未決で止める (保守的)。今回の 34 件の葉には部分書込が現れなかった。
- 循環の扱い: 最小不動点 (§1) は、循環を含む 2 行のうち 1 行を実値化に、1 行を `load_ptr` のみの未決にした。
- 限界: 呼出し先の戻り値 (`call_ret`) とメモリ読込 (`load_*`) は IR 側の情報が無いと決まらない。実値化 1 件の自動照合 (verify.py の対象を分岐先・mov 連鎖へ広げること) は未実装。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 未決 33 件 (§5) | 0 詰め reg 引数の値が未保証 | #3141・#3142・#1154 |
| 実値化 1 件の自動照合 (verify.py の対象拡張) | 手動 (§3) のみで照合 | #1154 |
| 8/16bit 部分書込の旧値を見ない (cfg_value と理由が異なる) | 部分書込を含む経路は未決に寄る (保守側) | #1154 |
| survey ok ≥ 870 (素材欠落) | 退行判定が未実施 | #1154 |
