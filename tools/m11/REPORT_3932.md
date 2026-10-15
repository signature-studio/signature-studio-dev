# M11 REPORT (#3932 / [M11-N201] / 親 #3906): set_other 実値化 25 件の 0 詰め call 引数への注入

結論: `m11_post.py` に `--slots` (実値化 `lea_alloca` 行の注入) を足した。既定 (`M11_SLOT_ROWS` 未指定) は注入経路に入らず、出力は main と一致する。注入の前後の survey 実測は未達 (入力 IR の一部が本 run に無い)。

## 1. 注入の規則

- 対象: `m11_setother_slot_class.py` の出力のうち `class=実値化`・`reason=lea_alloca` の行。`(caller, callee, k, pos)` で 0 詰め引数の位置を引く。
- 注入する値は呼出し元の `%stack_var_X = alloca`。次の 2 条件をすべて満たす alloca だけを使う (IR の支配関係を保つため):
  1. 同じ関数の entry block 内にある。
  2. 呼出しより前の行で定義されている。
  条件を外れた alloca は注入せず、`sigfix_slot_nonentry` で数える。
- 型: callee 引数が `ptr` なら `ptr nonnull %stack_var_X`。整数型なら `ptrtoint ptr %stack_var_X to i64` を前置し、必要なら `_conv` で幅を合わせる。一時名は `%m11sl<N>`。
- `M11_SIGFIX_RECOVER=1` (#131) との併用: RECOVER 分岐の最終 post にも `--slots` を渡す (以前は黙って無効だった)。

## 2. 検証 (実測)

### 2.1 入力 IR を使った測定 (commit `eba68fdbe`)

測定 commit: `eba68fdbe` (注入の entry block 判定を入れる前の最後のコード変更)。

| 項目 | 結果 |
|---|---|
| 入力 IR | `work-m11` の `boot_final.ll` (sha256 `69c774de…`・REPORT_N202 と一致) |
| PE | `block00031_PE.bin` sha256 `b2c64da4…` (素材と一致) |
| 分類の再現 | 対象 112 件・実値化 25 / 復元不能 0 / 未決 87 (REPORT_N202 と一致) |
| 0 詰め位置との突合 | 実値化 25 件すべてが `pads.json` の 0 詰め位置 (`have ≤ pos < want`) に一致 (25/25) |
| 注入の反映 | `sigfix_slot_injected` 25。注入した `%stack_var_X` は全件、同じ関数内の alloca で定義済み (undefined 0) |
| 既定動作 | `--slots` 未指定の出力は `origin/main` の `m11_post.py` と `cmp` 一致 (fixes あり・なしの 2 通り) |
| 注入前後の差分 | 注入なし (`final3_cur.ll`) と注入あり (`final3_slot.ll`) の diff は、0 詰め call の引数 25 件の差し替えと `ptrtoint` の追加だけ (`<` 25 行・`>` 48 行) |

### 2.2 本 run の追加確認 (commit は下記の HEAD)

- 入力 IR (`work-m11`) が `$ARTIFACTS_DIR` に無く、2.1 の数値は本 run で再実行できなかった。2.1 は eba68fdbe での値であり、HEAD の判定 (entry block 制限) を通した後の件数は未測定。
- 合成 IR での確認 (`m11_post.py` を CLI で実行):
  - entry block 内・呼出し前の alloca (`%stack_var_-8`・`%stack_var_-24`) → 注入される (`ptr nonnull`)。
  - 後続ブロックの alloca (`%stack_var_-16`) → 注入されず、`sigfix_slot_nonentry` = 1。
- 単体テスト: `test_setother_slot_class.py` 8 件 OK。`py_compile` と `bash -n` は OK。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| survey (`m11_e2e.sh`) の前後実測 | 注入が退行を起こさないかは未確認。既定は不変 | 未解決表のまま (再測定のため子を起票しない) |
| HEAD の判定 (entry block 制限) を通した後の 25 件の件数 | 2.1 の 25/25 は eba68fdbe の値 | 上と同じ (入力 IR が揃った run で再測定) |
| `work-m11` の IR に `ir_conditions.json` (ldfix=applied) の記録が無い | `m11_build.sh` が fail-closed で止まる | #4724 (M11-N220) |
| REPORT_N196 §6 の 25 件の行の更新 | 未更新 | 未解決表のまま (文言修正のため子を起票しない) |
