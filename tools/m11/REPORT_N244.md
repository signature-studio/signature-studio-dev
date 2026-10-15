# M11 REPORT (#5449 / [M11-N244] / 親 #4906 / 親 #4891): set_other 非 imm の書込可能グローバル 3 件 (VA 0x15e3a70) の計算ポインタ経由の格納探索

結論: checker を GEP の定数 offset を加算した実効アドレス判定に直した (区間重なり判定)。制御 IR 10 行で全ケースが期待どおり (§4)。**実 IR の再測定は本 run で未実施** (素材 `work-m11` が `$ARTIFACTS_DIR` に無い)。旧 checker (`a31318bf9`) の結果 (`va_hit` 0) は offset を無視していたため**無効**で、新 checker の件数は次の再測定まで確定しない。格納値の到達定義は未実装のため、3 件の区分は **未決 3** のまま。

## 1. 入力と手順

- 素材: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 先頭 `69c774ded8aaf717`・REPORT_N227 と一致)。PE は `fl-win64` の `extracted/block00031_PE.bin` (sha256 先頭 `b2c64da40921cf26`・一致)。
- 中間物 `sigfix_stats/` は素材に無いため、REPORT_N227 §1 の手順 1〜4 で再生成 (`m11_post.py`・`m11_argrecover.py`・`m11_setother_nonimm_class.py`・`m11_setother_mem_class.py`)。件数は REPORT_N227 と一致 (0 詰め call site 1049・引数 2064・fixes 33・非 imm 349・対象 257・実値化 8・gep 17・global_store 3)。
- 本 run の新規コード: `tools/m11/m11_global_store_alias.py` (commit `a31318bf9`)。IR は変更しない。
- 再現: `cd tools/m11/work && python3 ../m11_global_store_alias.py boot_final.ll --out sigfix_stats/alias.json`
- 本 run の再測定: 未実施。`work-m11` 素材が `$ARTIFACTS_DIR` に無く、`tools/m11/work/` を作れなかった (PR 本文の `oc_artifacts: work-m11` で次の run に素材を要求)。

## 2. 接続方式 (受入 2)

- 対象 store: IR 全関数の全 store 行 (`boot_final.ll`・store 行 54,041)。呼出し元 CFG に限定しない。IR 全体を探索範囲にした (呼出し元の外も含む)。
- 辿る連鎖: `inttoptr` (定数) / `getelementptr` (inbounds 含む・定数式を含む) / `bitcast` / `add`・`sub` (先頭被演算子) / `phi` (全入力が同じ根)。`alloca` と `load` は止める。
- 上限: 連鎖の深さ 12。循環は `cycle` として数える。

## 3. 探索結果 (受入 1)

**注記: 以下は旧 checker (`a31318bf9`・GEP の offset を無視) の出力で、無効。新 checker での再測定は未実施。** 件数は再測定の比較用にだけ残す。

```
[global-store-alias] target VA 0x15e3a70  IR store 行 54041
  alloca         39085
  unknown        8627
  const_other    4130
  load_ptr       2199
[unknown の定義元の内訳 (上位 8)]
  call           3482
  inttoptr       1434
  add            962
  icmp           658
  and            622
  zext           438
  or             356
  trunc          232
```

- (旧 checker の値) `va_hit` 0 件。IR で `inttoptr i64 22952560` の使用は `function_6520b0` の load 1 箇所のみ (store 0 件)。この記述は offset 付き GEP を見ていない旧判定に基づくため、確定しない。
- 旧 checker で `const_other` 4,130 件とした定数 inttoptr 群の内訳は、offset 付き GEP を含むため、新 checker の再測定の出力でのみ書く (手作業の判定は書かない)。
- `alloca` 39,085 件は reg2mem スロットへの store (GEP 定数式を含む 11 件もスロット宛て)。
- `load_ptr` 2,199 件はポインタを load で得たもの。別名解析が無いため追えない。
- `unknown` 8,627 件は計算ポインタ (call 戻り値 3,482・非定数 inttoptr 1,434・算術)。これが issue の『計算で作ったアドレス』に当たる部分で、本 run では解けなかった。

## 4. 検証 (checker の健全性)

- 制御 IR (リポジトリ外の一時ファイル `/tmp/opencode/alias_probe.ll`・store 10 行) の出力: `va_hit 7`・`const_other 1`・`const_var_offset 1`・`alloca 1`。
  - 行ごとの判定 (プローブの行番号順): 1 直接 `va_hit`・2 定数式 GEP (offset 0) `va_hit`・3 名前付き GEP (基底 0x15e3a60 + 16) `va_hit`・4 定数式 GEP (基底 0x15e3a60 + 16) `va_hit`・5 `[4 x i8]` 定数 GEP `va_hit`・6 8 バイト store at 0x15e3a68 (`[0x15e3a68, +8)` は対象と重ならない) `const_other`・7 1 バイト store at 0x15e3a77 (対象 `[0x15e3a70, +8)` 内) `va_hit`・8 `gep i64, +2` (+16) `va_hit`・9 非定数 index `const_var_offset`・10 alloca `alloca`。
  - 旧 checker は 3 と 4 (offset 付き) を `const_other` に落としていた (レビュー指摘どおり)。新 checker はこれを `va_hit` にする。

## 5. 3 件の区分 (受入 3)

- `m11_setother_gep_global.py --pe` (測定 commit `a31318bf9`・コードは origin/main と同一): 対象 20 件・実値化 0・復元不能 0・未決 20・未分類 0 (REPORT_N229 と一致)。
- global_store 3 件は全件 `no_store_in_ir` (VA `0x15e3a70` を読む関数: `function_1014ff0`・`function_11ff040`・`function_12b4e30`)。
- 格納値の到達定義は未実装なので、区分は未決のまま。実値化 0 は分類規則から決まる値で、実測ではない。

## 6. 照合 (受入 4)

- `m11_argrecover_verify.py` は set_const 専用。実値化 0 件のため照合対象は無い (**該当なし**)。

## 7. 差分

- 旧測定 commit `a31318bf9` (checker は offset 無視・無効)。checker 修正 commit の後で、実 IR の再測定を `work-m11` 付きの次回レビューで行う。`git diff a31318bf9 HEAD -- tools/m11/m11_global_store_alias.py` は checker 修正で 0 行でない。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計算ポインタ (`unknown` 8,627 件: call 戻り値・非定数 inttoptr・算術) の別名解析 | global_store 3 件の格納元 (VA 0x15e3a70 への store) を確定できない | #4906 (本文の作業 1 に残す) |
| 格納値の到達定義 (ptr_mem・load_ptr 2,199 件を含む) | 格納値を決めない限り 3 件は実値化できない | #4906 |
| alloca スロット宛て store 39,085 件のメモリ SSA | スロット経由で対象 VA に届く格納を除外できない | #4906 |
| gep 17 件の基底 SSA 対応付け | 同上 (gep) | #4905 (M11-N228) |
