# M11 REPORT (#5449 / [M11-N244] / 親 #4906 / 親 #4891): set_other 非 imm の書込可能グローバル 3 件 (VA 0x15e3a70) の計算ポインタ経由の格納探索

結論: checker を、関数ごとの SSA 定義で引き、GEP の定数 offset を加算した実効アドレスと store サイズの区間重なりで判定するように直した。制御 IR (`fixtures/alias_probe.ll`) で期待どおりに判定され、実 IR (`boot_final.ll`・store 54,041 行) では **`va_hit` 0 件** (対象 VA への直接・GEP 経由の store は見つからない)。計算ポインタ 10,774 件・格納値の到達定義は未決のまま #4906 に移送した。

## 1. 入力と手順

- 素材: `work-m11` の `tools/m11/work/boot_final.ll` (sha256 先頭 `69c774ded8aaf717`・store 行 54,041・`define` 7,422)。
- 測定 commit: `97587cc25` (checker 修正。コードを変えた最後の commit)。
- 再現: `cd tools/m11/work && python3 ../m11_global_store_alias.py boot_final.ll --out alias.json`
- 制御 IR の回帰テスト: `cd tools/m11 && python3 test_global_store_alias.py`

## 2. 接続方式 (受入 2)

- 対象 store: IR の各 `define` 内の全 store 行。関数ごとに SSA 定義表 (`defs`) を分け、その関数の store だけをその表で判定する (別関数の同名 SSA で上書きしない)。
- 辿る連鎖: `inttoptr` (定数) / `getelementptr` (inbounds 含む・定数式を含む・定数 index のみ) / `bitcast` / `phi` (全入力が同じ結果)。`alloca` と `load` は止める。
- 判定: 実効アドレスが定まったら、store のサイズと対象 VA から `--span` (既定 8) バイトの区間との重なりで判定する。
- 上限: 連鎖の深さ 12。循環は `cycle` として数える。

## 3. 探索結果 (受入 1)

測定 commit `97587cc25`・`boot_final.ll` (sha256 先頭 `69c774ded8aaf717`):

```
[global-store-alias] target VA 0x15e3a70 span 8  IR store 行 54041
  alloca           39017
  unknown          10774
  const_other      3952
  load_ptr         298
[unknown の定義元の内訳 (上位 8)]
  inttoptr       8581
  call           1794
  bitcast        211
  <param/undefined> 181
  select         6
```

- `va_hit` 0 件。対象 VA へ届く直接・定数 GEP 経由の store は実 IR に無い。
- `const_other` 3,952 件: 定数アドレス (定数 inttoptr・定数 GEP) だが対象 VA と重ならない。
- `alloca` 39,017 件: reg2mem スロットへの store。メモリ SSA が無いので辿らない (未決)。
- `load_ptr` 298 件: ポインタを load で得たもの。別名解析が無いため追えない。
- `unknown` 10,774 件: 計算ポインタ。定義元の内訳は上の表のとおり (`inttoptr` 8,581・`call` 1,794 ほか)。
- `const_var_offset` 0 件 (実 IR では定数 inttoptr 基底の非定数 index GEP は現れない)。

## 4. 検証 (checker の健全性)

- 制御 IR: `tools/m11/fixtures/alias_probe.ll` (store 9 行・リポジトリ内)。出力: `va_hit 6`・`const_other 1`・`const_var_offset 1`・`alloca 1`。
  - 行ごと: 直接 `va_hit`・定数式 GEP (offset 0) `va_hit`・`inttoptr 22952544` + `gep i64 2` (+16) `va_hit`・定数式 GEP +16 `va_hit`・`[4 x i8]` 定数 GEP `va_hit`・`inttoptr 22952552` (+8, 重ならない) `const_other`・1 バイト store at +7 `va_hit`・非定数 index `const_var_offset`・alloca `alloca` (9 行目の `store i64 9, ptr %a` は alloca 直接)。
  - 注: fixture の 8 行目の `load` 由来の index は `const_var_offset` に入る。
- テスト: `tools/m11/test_global_store_alias.py` が上の 4 件を固定する (`OK`)。

## 5. 3 件の区分 (受入 3)

- `m11_setother_gep_global.py --pe` の判定 (REPORT_N229 と一致): global_store 3 件は全件 `no_store_in_ir`。
- 本 checker の実 IR 結果では `va_hit` 0 のため、直接・GEP 経由の格納は見つからなかった。格納値の到達定義は未実装なので、区分は未決 3 のまま。
- 実値化 0 件は分類規則から決まる値で、実測ではない。

## 6. 照合 (受入 4)

- `m11_argrecover_verify.py` は set_const 専用。実値化 0 件のため照合対象は無い (**該当なし**)。

## 7. 差分

- `git diff 97587cc25 HEAD -- tools/m11/m11_global_store_alias.py tools/m11/m11_setother_gep_global.py` の出力は 0 行 (測定後のコード変更は無し)。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 計算ポインタ (`unknown` 10,774 件: inttoptr 非定数 8,581・call 1,794 ほか) の別名解析 | global_store 3 件の格納元を確定できない | #4906 (チェックリスト) |
| 格納値の到達定義 (`load_ptr` 298 件・alloca スロット宛て 39,017 件を含む) | 格納値を決めない限り 3 件は実値化できない | #4906 (チェックリスト) |
| gep 17 件の基底 SSA 対応付け | 同上 (gep) | #4905 (M11-N228) |
