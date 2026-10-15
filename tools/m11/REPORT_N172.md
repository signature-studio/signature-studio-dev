# M11 REPORT (#3140 / [M11-N172] / 親 #3134・#1154): set_other 非 imm reg 引数 merge 34 件の CFG 到達定義

結論: 初版 (`9b205ba79`) の判定器は、定義を含む循環の寄与を捨てていた。そのため実値化 1 件 (`function_f6bb50` → `function_cd1c20` の pos 1 = rdx) は誤りで、rdx は 1 周目 0・2 周目 1 になる (§3)。判定器を直した (循環の経路に定義があれば `loop` 未決、宛先 32bit 未満の ext は未決)。その 1 件は未決になった (§2-1)。修正版の 34 件・46 件の内訳は、この run に素材 `work-m11` が無く再測定できなかった。導出値は 実値化 0 / 復元不能 0 / 未決 34 (§2-2)。再測定は子 #3961 (M11-N205)。IR は変えていない (分類のみ)。

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

### 2-1. 修正の確認 (この run・HEAD)

- 測定 commit: `5bd2af3fe` (コードを変えた最後の commit。`git diff 5bd2af3fe HEAD -- tools/m11 ':(exclude)*.md'` は 0 行)。
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

### 2-2. 34 件の 3 値内訳 (未測定・導出値)

- 修正版の 34 件の 3 値件数と理由別件数は、この run では測れない。`work-m11` (`tools/m11/work/boot_final.ll`) が `ARTIFACTS_DIR` に無く、`m11_argrecover.py` の `fixes.json` を作れないため。
- 導出: 修正は (a) 実値化の葉を未決へ落とす (ext の分岐)、(b) 定義を含む循環の空の寄与に `loop` 未決の葉を足す、の 2 つだけ。未決の葉を実値化にする変更は無い。よって修正後の実値化は初版の実値化 (1 件) の部分集合で、その 1 件は §2-1 で未決になった。
- 導出値: **実値化 0 / 復元不能 0 / 未決 34** (未測定)。内訳 (理由別) は再測定 (子 #3961)。
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

### 2-3. cross-check (imm 非定数の reg 行 46 件)

- 旧版の実測: 実値化 0 / 未決 46 (`m11_setother_cfg_value.py` の reg 行 decided 0 / undecided 46 と一致)。
- 修正版は未測定。導出は 実値化 0 / 未決 46 (修正は実値化を減らす・未決を足すだけのため)。理由ラベルは変わり得る。再測定は子 #3961。

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
- `m11_argrecover_verify.py` は未実行。入力 `fixes.json` に今回の行が無いため照合していない (不一致の有無は不明)。verify.py は jcc・jmp・call で打ち切り、mov 連鎖を不一致として数えるため、「不一致ではない」の根拠にはならない。

## 4. 受入条件の判定

| 受入 | 判定 | 根拠 |
|---|---|---|
| 1. 34 件を 実値化 / 復元不能 / 未決 の 3 値で件数実測、未分類 0 | **未達 (再測定は子 #3961)** | §2-2 (導出値 0 / 0 / 34 のみ。素材 `work-m11` が無い) |
| 2. 実値化値を照合 | **該当なし** (修正版の実値化 0 件・導出) | §2-2・§3 (初版の 1 件は誤りで、未決になった) |
| 3. survey ok ≥ 870 | **除外** (#1154 へ移した) | 素材 `functions_dll.csv` の欠落で測れない (`REPORT_N171.md` §6)。IR を変えていない |

## 5. 同型の欠落: `m11_setother_nonimm_class.py` の `def_reg` (#3146)

- `def_reg` の movzx/movsx/movsxd (reg 源) の分岐は宛先幅 `w` を見ない。修正版の判定器と同じ欠落。
- 影響 (導出): 修正は実値化・復元不能を未決へ落とすだけなので、旧版の 3 値件数 (実値化 0 / 復元不能 0 / 未決 349) は変わらない (既に 0 件のため)。理由ラベル (未決の内訳) は変わり得る。
- 対応: 修正と再測定を子 #3961 に移した (`REPORT_N171.md` の内訳を更新する)。

## 6. 旧版 §5 の接続先 (無効・参考)

旧版の未決 33 件の接続先 (#3141 戻り値 10・#3142 メモリ読込 16・#1154 呼出元 def 7) は、修正版で付け直す (子 #3961)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 修正版の 34 件の 3 値内訳と理由別件数 (§2-2)・46 件の cross-check (§2-3) | 0 詰め reg 引数の内訳が未確定 (導出値のみ) | 子 #3961 (M11-N205) |
| `m11_setother_nonimm_class.py` の宛先幅の欠落 (§5) | 理由ラベルのみ (3 値件数は不変・導出) | 子 #3961 (M11-N205) |
| 実値化 1 件の自動照合 (分岐先・mov 連鎖) | 手動 (§3) のみ。前提の 1 件は未決になった | #3916 ([M11-N198])。前提が消えたことを #3916 に書いた |
| 8/16bit 部分書込の旧値を見ない (cfg_value と理由が異なる) | 部分書込を含む経路は未決に寄る (保守側) | #1154 |
| survey ok ≥ 870 (素材欠落) | 退行判定が未実施 | #1154 |
