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

