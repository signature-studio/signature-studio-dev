# liftdiff REPORT 付録: #5406 (LD-268) fvm 42 件の this 埋め blob での再実行 (受入 2)

正本は `REPORT_APPENDIX_LD177.md` §12.1.4 (分類) と本付録 (遷移の実測)。親 #4173・LD-177 (#3782)。

## 1. 実測 (vmtf)

- **測定 commit**: `6884c0829` (コードを変えた最後の commit。`tools/liftdiff/ld5406_fvm_fill.py` を新規追加)。
- **方法**: `ld5406_fvm_fill.py` が batch jsonl の fvm 42 件 (関数 VA・fvm_arg) を読み、this (arena+0x1000) の先頭 0x100 byte の各 qword を内部オブジェクト (arena+0x3000) へのポインタにし、その先頭に VMT (arena+0x2000・仮 proc slot) を置く blob `vmtf` で 1 件ずつ native / wasm に実行する。既存 blob `vmt` は変えない。
- **実測 (HEAD `6884c0829` で 2 回・同じ結果)**: 旧 → 新 の遷移

| 旧 outcome | 新 outcome | 件数 |
|---|---|---|
| both_fault | both_fault | 23 |
| both_fault | native_fault | 1 (`0xa96620` fvm0・wasm ok) |
| native_fault | native_fault | 8 |
| native_fault | diff | 5 |
| native_fault | both_fault | 1 (`0x47d460`) |
| native_fault | equal | 1 (`0x681380` fvm0) |
| diff | diff | 3 |

- 合計: 旧 both_fault 24 / native_fault 15 / diff 3 → 新 both_fault 24 / native_fault 9 / diff 8 / equal 1。**wasm_trap 0 件、equal 1 件**。
- 旧 both_fault の 24 件は、vmtf でも native は 24 件すべて fault のまま。wasm は trap のままが 23 件 (`0xa96620` fvm0 は wasm ok に変化)。`wasm_trap` (native ok・wasm trap) への遷移は 0 件。
- 結論: 受入 2 の**根拠付きの件数は 1 件 (equal)**。上限の推定 (wasm_trap 24・equal 18) は this の埋め方を変えた実測で大きく下がった。残り 41 件の阻害要因は未切り分け (native の segv 箇所と、wasm の trap・stub の原因は本測定では確認していない)。
- **未切り分け**: 残り 8 件の native_fault→native_fault (addr の変化の原因)、wasm_trap 0 件の理由 (wasm の trap は this の内容ではなく stub・境界の欠陥と見られる)。
- 再現: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 tools/liftdiff/ld5406_fvm_fill.py` (約 6 秒・出力 `work/m11/ld5406_fill.jsonl`)。

## 2. 残り 41 件の阻害要因 (run 3)

- **測定 commit**: `4289a20fe` (origin/main。本 run はコードを変えていない)。前回の測定 commit `6884c0829` からの `tools/liftdiff` 差分は RESET の変更 (wasm 側の戻しを JS 側 `ld_runner.mjs` へ移した LD-240 系の変更) を含むが、fill の結果は `6884c0829` と一致した (下の 2.1)。
- **再現手順**: `bash tools/liftdiff/liftdiff_e2e.sh --m11-only` で batch を再生成 (`LIFTDIFF_E2E PASS`・208〜218 s 相当の実測・load 0.93→4.90) し、`ld5406_fvm_classify.py` と `ld5406_fvm_fill.py` を実行。
- **分類の再現差**: 前 run の `wasm_stub_unreach 15` は、今回の batch では `wasm_stub_unreach 13` と `other:hang 2` (`0x47d670`・`0x5c5500`) に分かれた。batch 再生成による差で、outcome の変化ではない。
- **fill の実測 (2 回目も同じ)**: 旧 both_fault 24 / native_fault 15 / diff 3 / hang 2 → 新 both_fault 24 / native_fault 9 / diff 8 / equal 1。**wasm_trap 0 件**。

### 2.1 fill 後 outcome 別の阻害要因 (`ld5406_fill.jsonl` の行から集計)

| 新 outcome | 件数 | 阻害要因 (実測) |
|---|---|---|
| both_fault (native segv + wasm trap) | 24 | wasm 側は unreachable (`function_4128b0` の stub 系) 14 件・memory OOB 10 件。**native が先に segv する**ため、wasm の trap が native と同じ位置かを比べる段に進まない。native の segv アドレスは `0x810470ff8` が 7 件で同一 (共通の不正読み込み経路と見られる)。 |
| native_fault (wasm ok) | 9 | native segv。アドレスは `0x0`〜`0x78` が 5 件・アドレス無しが 3 件・`0x22474000` が 1 件。this を埋めても native 側の読み込みは解消しない。 |
| diff (native ok・wasm ok) | 8 | 両方 ok で差分あり。wasm 側の欠陥 (既知類型) の候補だが、差分の内訳は未確認。 |
| equal (native ok・wasm ok) | 1 | `0x681380` fvm0。遷移の実測 1 件。 |

### 2.2 遷移しうる件数 (受入 2 の数)

- **根拠付きの件数 = 1 件 (equal・実測)**。`0x681380` fvm0 のみ。
- **wasm_trap への遷移 = 0 件**。wasm_trap は「native ok・wasm trap」だが、現在 native ok の 9 件 (equal 1 + diff 8) はすべて wasm ok。native が fault の 33 件 (both_fault 24 + native_fault 9) は、native 側が ok にならない限り wasm 側の trap を比べられない。
- **範囲の限定**: 上の数は `vmtf` (this の先頭 0x100 byte を内部オブジェクトへのポインタにした blob) 1 種類の投入形による実測。他の投入形 (引数の埋め方・this の大きさ) は試していない。未確認。
- **未切り分け**: native segv の原因 (`0x810470ff8`・`0x0`〜`0x78`) の特定、diff 8 件の wasm 側の欠陥の内訳、stub `function_4128b0` の欠落の要否 (lift 側 icall 系か否か)。いずれも遷移の数には影響しないため、本付録の未解決として残す。

