# REPORT_APPENDIX_1521 — #1521 の付録 (REPORT §9 の分割移動)

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md`。本付録は REPORT §9 を移動したもの (内容は削除していない)。

## 9. #1521: int/pointer・frontend helper の修復と emcc 通過数 (測定 commit: bb076c69)

環境: `[RETDEC]` v5.0 (`toolchain-retdec`)・`[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64`。分割 lift は `retdec_batch.py` (batch 500) で再実行し、§8 と同じ 19,812 / 19,822 関数の lift 成功を再現した。emcc は `emcc_per_function.py` (修正後 DEF_RE) で測定。

**修復内容** (`retdec_repair.py`): (1) `CALL_RE` に `__frontend_*` を追加 (`__frontend_reg_load_fpr` / `__frontend_reg_store_fpr` の宣言漏れ)。(2) `--int-ptr`: emcc の `-Wint-conversion` 診断行だけ、その行の `&x` を `(int64_t)&x` に包む。型は推測せず、コンパイラの判定に従う。`break -> 0x...` と goto/label は触らない (DEFECTS D19 型の制御構造変更になり得るため)。

| 項目 | block19091 修復なし (§8 と同条件) | block19091 修復後 | block23676 修復なし | block23676 修復後 |
|---|---|---|---|---|
| 関数数 (pdata 併合後) | 19,816 | 19,816 | 19,826 | 19,826 |
| RetDec 定義あり | 19,812 | 19,812 | 19,822 | 19,822 |
| 補った宣言 | — | 921 | — | 924 |
| 包んだ `&` (int/pointer) | — | 1,993 | — | 1,986 |
| emcc `-c` 通過 (関数単位) | 16,815 | 18,932 | 16,821 | 18,939 |
| error 行 | 11,432 | 1,377 | 11,475 | 1,383 |
| emcc exit 0 (ファイル数 / 40) | 0 | 1 | 0 | 1 |
| emcc 所要 (合計) | 7.24 s | 5.99 s | 7.00 s | 6.05 s |

**残り error の内訳** (block19091 修復後, 全 40 ファイル) — **未再計測 (要再計数)**:

この表の件数は前回 run の概数で、合計が修復後の総 error 行 1,377 と一致しない (1,245 + 78 + 16 + 63 + 約 35 = 約 1,437)。同じ emcc 出力からの再計数はこの runner では行えない (RetDec・`[EMSDK]` 未配置、生成 C なし)。よって件数は正本ではなく、正確な内訳は未確定。

| 類型 | 件数 (未再計測) | 修復可否 |
|---|---|---|
| `incompatible pointer types passing` (RetDec の引数型推定 `int16_t*` 等と実引数の不一致) | 約 1,245 (未再計測) | 不可。同じ宣言を補うと型が固定されるだけで、正しい型の推測は silent miscompile になり得る |
| `'break' statement not in loop` | 78 (未再計測) | 不可。`break -> 0x...` は RetDec の goto 相当の復元。機械的に `goto` 等へ変えると制御構造が変わる (DEFECTS D19 型) |
| `use of undeclared label` | 16 (未再計測) | 不可。上記 goto と同根 |
| `call to undeclared function` | 63 (未再計測) | 未修復。`__asm_*` 以外の未宣言 helper (本 run では `CALL_RE` の対象外の名前) |
| その他 (`incompatible pointer types assigning` 等) | 約 35 (未再計測) | 未分類 |

再計数の手順 (要 RetDec v5.0 と `[EMSDK]` 6.0.12 のある環境で実施): `retdec_repair.py --int-ptr` 適用後の出力に対し `emcc -c` を実行し、`emcc 2>&1 | grep -oE 'error: .*'` を分類ごとに `grep -c` で数える。全類型の合計が 1,377 と一致することを確認してから本表を差し替える。

**受入条件の判定**:
- 受入条件 1 (int/pointer 混在の修復): 達成。`-Wint-conversion` 行は block19091_0.c 単体で 46 → 0 件、全 40 ファイルでも修復後 0 件 (実測)。全 40 ファイルの error 行は 11,432 → 1,377。
- 受入条件 2 (goto/break の扱い): 判断を記録。`break`・`undeclared label` (計 94 件) は機械的修復を行わない。根拠は上表 (C の制御構造を変える修復は silent miscompile になり得る)。
- 受入条件 3 (emcc exit 0 件数): 未達。exit 0 は block19091 / block23676 とも 40 件中 1 件。残るのは goto/break (94 件、未再計測) と引数型の不一致 (約 1,245 件、未再計測) で、これは上表の「不可」類型のため、機械的修復では 40 件全てを exit 0 にできない。

**未解決 (起票先)**: goto/break・undeclared label の制御構造復元 → #1679 (HB-H35)。引数型不一致 (約 1,245 件) の型推定修復 → #1680 (HB-H36)。

**未検証 (本 run の範囲外)**:
- `(int64_t)&x` の値が RetDec の意図と一致するかは、wasm 実行系が無いため未検証。wasm32 では `void*` 4B・`int64_t` 8B で、キャストは番地を拡張するだけという実測のみ (`(int64_t)&g94` = `0x10bb0`)。
- 修復後の関数が機械語どおりに動くかは未検証 (link・実行は未実施)。
- `no_definition` 4 件の原因は未特定 (§8 と同じ)。
