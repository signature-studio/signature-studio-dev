# M11 REPORT (#3140 / [M11-N172] / 親 #3134・#1154): set_other 非 imm reg 引数 merge 34 件の CFG 到達定義

結論: 初版 (`9b205ba79`) の判定器は、定義を含む循環の寄与を捨てていた。そのため実値化 1 件 (`function_f6bb50` → `function_cd1c20` の pos 1 = rdx) は誤りで、rdx は 1 周目 0・2 周目 1 になる (§3)。判定器を直した (循環の経路に定義があれば `loop` 未決、宛先 32bit 未満の ext は未決)。修正版の実測: merge 系 34 件は 実値化 0 / 復元不能 0 / 未決 34 (§2-2)。非 imm 349 件の再測定も同じ 0 / 0 / 349。cross-check (reg 宛先 46 件) は decided 0 / undecided 46 (§2-3)。機械語照合は §3。宛先幅の判定 (movzx/movsx/movsxd の宛先 32bit 未満) は #3961 (M11-N205) で `m11_setother_nonimm_class.py` に入れ、349 件・34 件・46 件を修正版で再測定した (§2-2・§2-3・§5)。IR は変えていない (分類のみ)。

## 1. 方式

- 対象: `nonimm_class_rows.json` の reason が `merge`・`merge_at_call`・`chain>merge` の reg 行 (pos 0〜3)。34 件すべて reg。
- 状態 `S(i, fam)` = 命令 i の直前で族 fam が持つ到達定義の葉の集合。分岐先 (直接 jump の飛び先) は全 predecessor の「直後の状態」の和集合。直線部分は後ろ向きに 1 本だけ追い、分岐先に着いた時点で join する。
- 葉の定義の読み方は `m11_setother_nonimm_class.py` と同じ (全幅 mov imm・xor・全幅 copy・即値の加減論理演算の連鎖)。
  - 例外 (修正): 宛先 32bit 未満の movzx/movsx/movsxd (reg 源) は、上位ビットが旧値に依存する部分書込なので未決 (`partial_ext`)。初版は源の値をそのまま宛先に写していた。
- call: rax は戻り値 (葉 `call_ret`・未決)。その他の揮発族は壊れる (葉 `call_clobber`・復元不能)。
- 区分: 全葉が同じ定数 → 実値化 (`cfg_agree`)。葉に `call_clobber` がある → 復元不能。他 → 未決 (`merge>` + 葉の理由)。
- 循環 (修正): 戻り辺で同じ (分岐先, 族) に戻ったとき、DFS の現在の経路 (`path`: その (分岐先, 族) の判定開始から現在位置まで) に族の定義があれば葉 `loop` (未決)。定義が無ければ寄与を空にする (その循環は族の値を変えないため)。循環を通った途中結果はメモしない。
  - 初版は busy 分岐を常に空にしていた。定義を含む循環の寄与 (`add ebx,1`) が捨てられ、§3 の誤りになった。
- 間接 jmp: 関数内の間接 jmp は分岐先を `merge_indirect` で未決にする。34 件はいずれも関数に間接 jmp が無かった (`indirect` 0 件)。

## 2. 測定

### 2-1. 修正の確認 (HEAD・再実行)

- 測定 commit: `a7b7b0045` (判定器 cfg 2 本の測定。判定器 2 本は `5bd2af3fe` から不変。#3961 の修正後の再測定は §2-4)。
- 入力: fl-win64 の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`・REPORT と一致)。
- 1 行再現 (レビューの確認と同じ入力): 初版 `実値化 0x0` (葉 `zero_idiom@0xf6bd0d`) → 修正後 `未決 merge>chain>loop` (葉 `実値化:zero_idiom@0xf6bd0d`・`未決:chain>loop@0xf6bd37`)。
- 合成検査 `python3 m11_setother_nonimm_cfg_check.py <PE>` (命令列を capstone で組み、同じ `Cfg` で判定。実機 PE は使わない):

| ケース | 内容 | 初版 (`173820710`) | 修正後 |
|---|---|---|---|
| A1 | `movzx dx,bl` (16bit 宛先) | 実値化 0x0 (誤り) | 未決 merge>partial_ext |
| A2 | `movsx dx,bl` (16bit 宛先) | 実値化 0x0 (誤り) | 未決 merge>partial_ext |
| A3 | `movzx edx,bl` (32bit 宛先) | 実値化 0x0 | 実値化 0x0 (変化なし) |
| A4 | `movzx rdx,bl` (64bit 宛先) | 実値化 0x0 | 実値化 0x0 (変化なし) |
| B | 循環・定義を含む (`add ebx,1` が戻り辺) | 未決 cfg_conflict | 未決 merge>chain>loop |
| C | 循環・定義を含まない (`mov ebx,5` が出口まで残る) | 実値化 0x5 | 実値化 0x5 (変化なし) |
| D | 循環の後で参照 (出口の ebx は常に 2) | 実値化 0x1 (誤り) | 未決 merge>chain>loop |

### 2-2. 34 件の 3 値内訳 (実測・HEAD)

- 測定 commit: `a7b7b0045` (main 取り込み merge。コードの最後の変更。以後の commit は md のみ)。PR head `059fe1423` に `origin/main` `bbff6d4c2` を merge し、DOC_MAP.md の索引の競合だけを解消した。
- 素材: `work-m11.tar.zst` を `tools/m11/work/` に展開 (`boot_final.ll` sha256 `69c774de…`)。`fl-win64` の `extracted/block00031_PE.bin` (sha256 `b2c64da4…`)。この run で取得できた (以前の「無い」は誤り)。
- 実行順 (すべて rc 0): `m11_post.py` (sha `ecab191b…`・REPORT_N86 と一致) → `m11_argrecover.py` → `m11_setother_ledger_verify.py` (`match 410`) → `m11_setother_nonimm_class.py` (349 件) → `m11_setother_nonimm_cfg.py` (34 件)。cross-check 用に `m11_setother_imm_class.py` (61 件) → `m11_setother_cfg_value.py` (55 件) も実行。

| 集計 | 件数 |
|---|---:|
| 実値化 / 復元不能 / 未決 / 未分類 | 0 / 0 / **34** / 0 |

| 元の理由 | 区分理由 (`nonimm_cfg_rows.json`) | 件数 |
|---|---|---:|
| merge | merge>load_ptr | 10 |
| merge | merge>call_ret | 9 |
| merge_at_call | merge>load_ptr | 5 |
| merge | merge>entry | 4 |
| merge_at_call | merge>entry | 3 |
| merge | merge>load_stack | 1 |
| merge | merge>chain>loop (`function_f6bb50` → `function_cd1c20` pos 1 を含む) | 1 |
| chain>merge | merge>chain>call_ret | 1 |

- 修正は実値化を未決へ落としただけで、実値化の件数は 0 (初版の 1 件は §2-1 のとおり未決)。

- 非 imm 349 件の 3 値 (`nonimm_class_rows.json`): **実値化 0 / 復元不能 0 / 未決 349 / 未分類 0**。元の kind 別は、reg 123 (うち stack_set_other 17)・mem_ptr 89・lea_stack 59・mem_stack 50・lea_ptr 17・mem_global 11 (計 349)。理由の根は load_ptr 117・lea_stack 59・load_stack 50・merge 25・chain 18・lea_ptr 17・call_ret 15・load_global 11・merge_at_call 8・stack_match 8・arith 7・stack_narrow 9・call_ret_indirect 4・entry 1 (計 349)。

- 旧版 (`9b205ba79`・誤りを含む) の実測値は次のとおり。無効で、参考のみ。

| 元の理由 | 旧版の区分理由 | 旧版の区分 | 件数 |
|---|---|---|---:|
| merge | cfg_agree (全葉が定数 0) | 実値化 | 1 |
| merge | merge>call_ret | 未決 | 9 |
| merge | merge>entry | 未決 | 4 |
| merge | merge>load_ptr | 未決 | 10 |
| merge | merge>load_stack | 未決 | 1 |
| merge_at_call | merge>entry | 未決 | 3 |
| merge_at_call | merge>load_ptr | 未決 | 5 |
| chain>merge | merge>chain>call_ret | 未決 | 1 |
| **合計 (旧版・無効)** | | **実値化 1 / 復元不能 0 / 未決 33 / 未分類 0** | **34** |

### 2-4. #3961 の修正版の再測定 (測定 commit `5817ee7e5`)

- 修正: `m11_setother_nonimm_class.py` の `def_reg` の movzx/movsx/movsxd (reg 源) 分岐に `w < 32` → 未決 `partial_ext` を入れた (cfg 側 `m11_setother_nonimm_cfg.py:176-178` と同じ規則)。
- 入力: `work-m11` の `boot_final.ll` (sha256 `69c774de…`)・`fl-win64` の `block00031_PE.bin`。`m11_sigfix_stats.sh` で `pads.json`・`fixes.json` を再生成 (`[verify] fixes 33: match 33 / mismatch 0`・`const recovered 24`)。
- 測定 (すべて rc 0・`ws-3961` 作業ツリーの HEAD `5817ee7e5`):

| 測定 | 件数 | 修正前 (`a7b7b0045`) | 修正後 (`5817ee7e5`) |
|---|---|---|---|
| 非 imm 349 件 (`m11_setother_nonimm_class.py`) | 実値化 / 復元不能 / 未決 | 0 / 0 / 349 | **0 / 0 / 349** |
| 同 349 件の理由・区分 (行単位) | 変化した行 | — | **0 件** (`partial_ext` 0 件) |
| merge 系 34 件 (`m11_setother_nonimm_cfg.py`) | 実値化 / 復元不能 / 未決 | 0 / 0 / 34 | **0 / 0 / 34** (理由別件数は §2-2 と一致) |
| 合成検査 (`m11_setother_nonimm_cfg_check.py`) | A1・A2 (16bit 宛先 movzx/movsx) | 実値化 0x0 (誤り) | **未決 merge>partial_ext** |
| 同 | A3・A4 (32/64bit 宛先)・C | 実値化 | 実値化 (変化なし) |
| 同 | B・D (循環) | 未決 / 実値化 0x1 (誤り) | 未決 merge>chain>loop |
| cross-check imm 非定数 55 件 (`m11_setother_cfg_value.py`・reg 宛先 46) | decided / undecided | 0 / 55 | **0 / 55** |

- 合成検査 `m11_setother_nonimm_cfg_check.py` の結果は §2-1 の表 (A1・A2 を「未決 merge>partial_ext」にした修正後) と一致する。
- 修正前の判定器 (`git show a7b7b0045:...` を一時ファイルで実行) と修正後の 349 行を比べ、差は 0 行。

### 2-3. cross-check (imm 非定数の reg 行 46 件)

- 実測 (HEAD `a7b7b0045`・`m11_setother_cfg_value.py`): 対象 imm 非定数 55 件、**decided 0 / undecided 55**。うち reg 宛先 (挿入命令の宛先がレジスタ) は 46 件で、decided 0 / undecided 46 (旧版と一致)。mem 宛先 9 件は reg 行に含めない。
- 件数は cross-check の reg 行で、判定の出力は変わらない。理由ラベルは `m11_setother_cfg_value.py` の出力どおり (`partial_old_*`・`mem_old_*`・`arith_old_*`)。

## 3. 初版の誤り: 実値化 1 件の機械語照合

- 対象: `function_f6bb50` → `function_cd1c20` の k=0・pos 1 (rdx)。初版の判定 `0x0` は誤り。
- 機械語 (`objdump -d block00031_PE.bin --start-address=0xf6bd0d --stop-address=0xf6bd80`。範囲は戻り辺の後まで広げた):

```
f6bd0d  xor    %ebx,%ebx
f6bd0f  test   %ebx,%ebx                 ← ループ頭 (戻り辺 f6bd71 の到達先)
   ...  (分岐・call 0x4622f0 → f6bd33)
f6bd47  mov    %ebx,%edx                 ← rdx = rbx
f6bd66  call   0xcd1c20
f6bd6b  add    $0x1,%ebx
f6bd6e  cmp    $0x2,%ebx
f6bd71  jne    0xf6bd0f                  ← 戻り辺
```

- rdx は call 時点の rbx。1 周目は rbx = 0 で rdx = 0、2 周目は rbx = 1 で rdx = 1。循環で値が変わるので、未決が正しい。
- 初版が誤った理由: busy 分岐が空を返し、戻り辺の `add ebx,1` の寄与を捨てた (§1)。
- 実値化 1 件の照合 (#3916 の前提) は消えた。修正版では、この行は未決 (§2-1)。
- `m11_argrecover_verify.py` (HEAD `a7b7b0045`・`fixes.json`) は `fixes 33: match 33 / mismatch 0` (rc 0)。今回の行 (`function_f6bb50` → `function_cd1c20` pos 1) は fixes の対象外で、照合の対象ではない。

## 4. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 34 件を 実値化 / 復元不能 / 未決 の 3 値で件数実測、未分類 0 | **達成** (0 / 0 / 34 / 0) | §2-2 (実測・HEAD `a7b7b0045`) |
| 2. 実値化値を照合 | **該当なし** (修正版の実値化 0 件・実測) | §2-2・§3 (初版の 1 件は誤りで、未決になった) |
| 3. survey ok ≥ 870 | **除外** (#1154 へ移した) | 素材 `functions_dll.csv` の欠落で測れない (`REPORT_N171.md` §6)。IR を変えていない |

## 5. 同型の欠落: `m11_setother_nonimm_class.py` の `def_reg` (#3146)

- 旧版: `def_reg` の movzx/movsx/movsxd (reg 源) の分岐は宛先幅 `w` を見なかった (#3146 で merge 済みの欠落)。
- 対応: #3961 で `w < 32` → 未決 `partial_ext` を入れた (測定 commit `5817ee7e5`・§2-4)。349 件の 3 値は修正前と同じ 0 / 0 / 349 / 0 で、理由ラベルも 1 件も変わらなかった (`REPORT_N171.md` §2)。

## 6. 旧版 §5 の接続先 (無効・参考)

旧版の未決 33 件の接続先 (#3141 戻り値 10・#3142 メモリ読込 16・#1154 呼出元 def 7) は、修正版の未決 34 件 (§2-2) に対して付け直す。付け直した結果は §2-2 の表の理由別件数 (load_ptr 15・call_ret 9・entry 7・load_stack 1・loop 1・chain>call_ret 1) を接続先に対応させる: #3142 (メモリ読込 16 件) ・#3141 (戻り値 10 件)・#1154 (呼出元 def 7 件)・#3140 (循環 1 件・§3)。

## 7. 測定 commit と差分

- 測定 commit: `a7b7b0045` (main 取り込み merge。コードを変えた最後の commit)。以後の commit は REPORT (md) のみ。
- 判定器 2 本の差分: `git diff 5bd2af3fe a7b7b0045 -- tools/m11/m11_setother_nonimm_cfg.py tools/m11/m11_setother_nonimm_cfg_check.py` は 0 行。
- `tools/m11` の差分 (main 取り込み分・`m11_setother_nonimm_class.py` は #3141 の変更を含む): `git diff 5bd2af3fe a7b7b0045 -- tools/m11 ':(exclude)*.md'` は 1517 行。本 PR の判定規則には入らない。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 実値化 1 件の自動照合 (分岐先・mov 連鎖) | 手動 (§3) のみ。前提の 1 件は未決になった | #3916 ([M11-N198])。前提が消えたことを #3916 に書いた |
| 8/16bit 部分書込の旧値を見ない (cfg_value と理由が異なる) | 部分書込を含む経路は未決に寄る (保守側) | #1154 |
| survey ok ≥ 870 (素材欠落) | 退行判定が未実施 | #1154 |
