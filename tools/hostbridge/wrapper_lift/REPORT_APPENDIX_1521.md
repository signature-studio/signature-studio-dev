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

**残り error の内訳 (修復後)**: 類型別の件数は**未計測**。この run では `[RETDEC]`・`[EMSDK]` が無く、生成 C も残っていないため、修復後の出力を emcc で再計数できなかった。したがって本付録には類型別件数を書かない (推定値は捨てた)。正本は実測済みの総数のみ: block19091 修復後 error 行 1,377、block23676 修復後 1,383 (emcc exit 0 は各 40 件中 1 件)。

修復なしの類型別集計 (block19091) は `REPORT.md` の「修復なし RetDec 出力の誤り内訳」の行を参照 (修復後とは別の状態の実測)。

再計数の手順 (要 RetDec v5.0 と `[EMSDK]` 6.0.12 のある環境で実施): `retdec_repair.py --int-ptr` 適用後の出力に対し `emcc -c` を実行し、`emcc 2>&1 | grep -oE 'error: .*' | sort | uniq -c | sort -rn` で類型別件数を出す。総数が error 行 1,377 と一致することを確かめてから、その表を本付録に載せる。

**受入条件の判定**:
- 受入条件 1 (int/pointer 混在の修復): 達成。`-Wint-conversion` 行は block19091_0.c 単体で 46 → 0 件、全 40 ファイルでも修復後 0 件 (実測)。全 40 ファイルの error 行は 11,432 → 1,377。
- 受入条件 2 (goto/break の扱い): 判断を記録。`break`・`undeclared label` (計 94 件) は機械的修復を行わない。根拠は上表 (C の制御構造を変える修復は silent miscompile になり得る)。
- 受入条件 3 (emcc exit 0 件数): 未達。exit 0 は block19091 / block23676 とも 40 件中 1 件。残る error には、制御構造の復元が要る goto/break・undeclared label と、引数型の推定が要る不一致が含まれる。修復後の類型別件数は未計測のため、これらが 40 件全ての exit 0 を阻む量かどうかは未確定。

**未解決 (起票先)**: goto/break・undeclared label の制御構造復元 → #1679 (HB-H35)。引数型不一致の型推定修復 → #1680 (HB-H36)。

**未検証 (本 run の範囲外)**:
- `(int64_t)&x` の値が RetDec の意図と一致するかは、wasm 実行系が無いため未検証。wasm32 では `void*` 4B・`int64_t` 8B で、キャストは番地を拡張するだけという実測のみ (`(int64_t)&g94` = `0x10bb0`)。
- 修復後の関数が機械語どおりに動くかは未検証 (link・実行は未実施)。
- `no_definition` 4 件の原因は未特定 (§8 と同じ)。
