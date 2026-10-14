# REPORT 付録 — #1339: RetDec 分割 lift 出力 C の修復 (§8 の全文)

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md`。本付録は REPORT §8 の全文の分割移動 (内容は無変更)。


測定 commit: a10c1f60 (`DEF_RE` を直した commit。以降のコード変更は §10 の判定修正)。環境: `[RETDEC]` v5.0・`[EMSDK]` 6.0.12 (emcc)・clang 同梱、`fl-win64`、`work-*` 系は未使用。

**判定の修正**: `DEF_RE` の `[^;=]*` が改行をまたぎ、定義行を見落としていた。`[^\n;=]*` / `[^\n;{}]*` に直した。残った `no_definition` 件数と原因は §10 を正本とする (本節の表は a10c1f60 時点の値)。

**修復なしの emcc `-c` (関数単位・修正後 DEF_RE、`emcc_per_function.py`)**:

| 項目 | block19091 | block23676 |
|---|---|---|
| 関数数 (pdata 併合後) | 19,816 | 19,826 |
| RetDec 定義あり | 19,812 | 19,822 |
| emcc `-c` 通過 (修復なし) | 16,815 | 16,821 |
| emcc exit | 40 ファイル全て 1 | 40 ファイル全て 1 |
| error 行 | 11,432 | 11,475 |
| emcc 所要 (合計) | 9.72 s | 9.63 s |

**helper 宣言の補修 (`retdec_repair.py`) 後**:

| 項目 | block19091 | block23676 |
|---|---|---|
| 補った宣言 | 919 | 922 |
| emcc `-c` 通過 | 17,758 | 17,769 |
| error 行 | 3,433 | 3,432 |
| emcc 所要 (合計) | 8.67 s | 8.83 s |

- 補修内容: 本体で呼ばれるが宣言の無い helper (`__asm_*`・`llvm_*`・`__read*` 等) を `int64_t NAME();` で宣言する。非破壊 (入力は変えない)。
- **未修復 (残り error の内訳, block19091 `0_` 単一ファイル例)**: int/pointer 混在 (`int64_t v7 = &v3` 等、`-Wint-conversion` 系 約 50 件)、goto 由来の `break` / `statement not in loop` (約 15 件)、`use of undeclared label` (3 件)、残りの未宣言 helper (約 60 件)。goto/break は C の制御構造を変えるため機械的修復は行わない (silent miscompile の危険)。
- 通過数は `emcc_exit` が全て 1 のため、通過はファイル内の帰属で数えた値。`unattributed_error_lines` は 1 件 (fail-closed で 1 ファイルを失敗扱い)。

**wasm link・採用方式 (受入条件 2・3)**: 未実施。修復済みでも 40 ファイル全てが `emcc -c` で exit 1 のため、link に進めない。wasm link の所要・サイズは未測定。採用方式は未決定 (§7 の暫定 x64c 候補は変更なし)。

**本 run で未達のもの → 子 issue**: goto/break・int/pointer 混在の修復と emcc exit 0 化 → #1521 (HB-H31)。`no_definition` 残り 4 件の原因、wasm link の所要・サイズ、方式比較表の完成 → #1522 (HB-H32)。
