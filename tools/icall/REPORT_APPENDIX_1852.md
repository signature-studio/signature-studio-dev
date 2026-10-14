# 付録: icall #1852 (ICALL-44) — Fresh Air SlateCore の wasm abort / out of bounds 8 関数の原因切り分け

> 親: #1633 (ICALL-37) の付録 `REPORT_APPENDIX_1633.md` §4.1。本付録は子 issue #1852 の結論を記録する。

## 1. 結論

- 対象 8 関数のうち 6 件 (abort) は、**wasm route 側** (`ir_flatten.py` の dispatch table 生成) が原因。引数付き (`%arg1` 等) の lifted 関数は `icall_tbl_va` に登録されず、`ott_run` の `lookup` が NULL を返して `[icall] ott_run: unknown entry` → `abort()` になる。closure 外 callee 起因ではない。
- 残り 2 件 (out of bounds) は原因を**未確定**。shift 後 memory 外参照であることまでは確認したが、trap 位置の特定は未実施。route 側 (memory shift・data 敷設) の疑いが強いが、断定しない。
- 修正は本 PR の範囲外 (下記 §4)。route の生成規則を変える修正は比較基準そのものを動かすため、子 issue に分けた。

## 2. 8 関数の内訳

測定: `tools/icall/diff/fa_sweep.sh 8 60` (`sweep.jsonl`、141 関数) の該当行と、`node` で `ott_run` を直接呼んだ結果 (入力 xmm0 = 1.0)。

| VA | sweep (wasm_err / 8) | wasm の最初のエラー | 分類 | 原因 (1 行) |
|---|---|---|---|---|
| 180c8b310 | 8 | abort: `unknown entry 0x30c8b310` | wasm route 側 | 引数付き関数で table 未登録 (`%arg1`)。 |
| 180c9d880 | 8 | abort: `unknown entry` (直接確認) | wasm route 側 | 引数付き関数で table 未登録 (`%arg1`)。 |
| 180ca1480 | 8 | abort: `unknown entry` (直接確認) | wasm route 側 | 引数付き関数 (`%arg1,%arg2`) で table 未登録。 |
| 180da3f80 | 8 | abort: `unknown entry` (直接確認) | wasm route 側 | 引数付き関数 (`%arg1`) で table 未登録。 |
| 18103fd60 | 8 | abort: `unknown entry 0x3103fd60` | wasm route 側 | 引数付き関数 (`%arg1`) で table 未登録。 |
| 18106a3ba | 8 | abort: `unknown entry` (直接確認) | wasm route 側 | 引数付き関数 (`%arg1`) で table 未登録。 |
| 180c8b280 | 2 | memory access out of bounds (入力 #3) | trap 位置確定 (#1899)・分類は未確定 (#1998) | 引数無し・table 登録済み。trap は引数付きの 180c8b310 (wasm 0x14475) で起きる。詳細は `REPORT_APPENDIX_1899.md`。 |
| 181057b38 | 8 | memory access out of bounds | trap 位置確定 (#1899)・分類は未確定 (#1998) | 引数無し・table 登録済み。trap は `18106632c` (wasm 0x2700e) で、BLK (`0x36319008`) が `"emsc"` に書き換えられた後に読む。書き込み元は未特定 (#1998)。 |

### 2.1 根拠

- `oi.table.c` の `icall_tbl_va` は 125 件。`oi.flat.ll` の `define` 163 件のうち引数無し 125 件と一致し、引数付き 38 件は登録されていない。
- 対象 8 関数の `define` 行を確認: 180c8b280 と 181057b38 のみ引数無し (登録済み)、残り 6 件は引数付き (未登録)。
- `ir_flatten.py` の table 生成は `define i64 @function_<va>()` (引数無し) だけを対象にしている。
- `icall_rt.c` の `ott_run` は `lookup(va)` が 0 のとき `unknown entry` を出して `abort()` する (line 83)。

## 3. 測定

| 項目 | 値 |
|---|---|
| 測定 commit | `8ea5d402` (origin/main 取り込み後・コード変更なし) |
| `roundtrip.sh` (freshair-core, `fa_ranges_1633.txt` 151 範囲) | 38.9 s、func_map 141 |
| `fa_route_build.sh` | exit 0、9.5 s (route `fa_route.cjs` 生成) |
| `fa_sweep.sh 8 60` | 141 関数、74.3 s、load 0.86 |
| 区分 | bit 一致 53 / native crash・timeout 73 / wasm のみ err 9 / 値の不一致 6 (合計 141) |

付録 `REPORT_APPENDIX_1633.md` §4 の値 (53 / 73 / 9 / 6) と一致した。

補足: 作業開始直後の sweep は全 131 関数が `crash_or_timeout` になった。原因は `libottnative.so` 未ビルド (`tools/ott/native/build.sh` で解消)。この状態の値は本付録の測定には使っていない。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 引数付き lifted 関数を dispatch table に載せる規則 (BLK 経由の引数受け渡しを表で扱う wrapper) | abort 6 件 (本付録 §2) | #1897 (ICALL-49) |
| out of bounds 2 件 (180c8b280・181057b38) の trap 位置と原因の確定 | wasm のみ err 2 件 | #1899 (ICALL-50) |

注: `GetCurrentThreadId` (180f9e540) は main で解消済み (#1853 / #1898、shim は `tools/icall/rt/icall_rt.c`)。本測定 commit `8ea5d402` は shim 導入前のため、§2 の wasm のみ err 9 件に含まれる。

## 5. 再現

```
bash tools/ott/native/build.sh
bash tools/icall/roundtrip.sh "tools/targets/freshair/work/win/Fresh Air/C__ProgramData_Slate Digital/Fresh Air/SlateCore.core_64" tools/icall/fa_ranges_1633.txt freshair-core
bash tools/icall/fa_route_build.sh
bash tools/icall/diff/fa_sweep.sh 8 60
```

前提: `work-icall`・`plugins-freshair` (`FA_DL=... bash tools/targets/freshair/fetch.sh`)・`toolchain-retdec`・`toolchain-emsdk`。`libottnative.so` は gitignore 対象の `tools/ott/work/` に生成する (素材には含まれない)。
