# REPORT 付録 — #1521 (HB-H31): int/pointer・frontend helper の修復と emcc 通過数

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §9。本付録は REPORT §9 の全文を分割移動したもの (内容は削除していない)。
> 結論 1 行: int/pointer 混在 (`-Wint-conversion`) は修復済み (block19091 で 46 → 0)。emcc exit 0 は 40 ファイル中 1 件のみで、受入条件 3 は未達 (子 issue #1679・#1680)。

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

**残り error の内訳** (block19091 修復後, 全 40 ファイル, 合計 1,377 = 表の error 行と一致):

| 類型 (emcc 診断) | 件数 | 修復可否 |
|---|---|---|
| `incompatible pointer types passing` (RetDec の引数型推定 `int16_t*` 等と実引数の不一致) | 1,245 | 不可。同じ宣言を補うと型が固定されるだけで、正しい型の推測は silent miscompile になり得る |
| `'break' statement not in loop or switch statement` | 78 | 不可。`break -> 0x...` は RetDec の goto 相当の復元。機械的に `goto` 等へ変えると制御構造が変わる (DEFECTS D19 型) |
| `use of undeclared label` | 16 | 不可。上記 goto と同根 |
| `incompatible pointer types assigning to` | 17 | 不可。int/pointer 以外の型不一致で、型推測を伴う |
| `incompatible pointer types initializing` | 13 | 同上 |
| `assigning to ... from incompatible type` | 3 | 同上 |
| `use of undeclared identifier` | 2 | 未分類 (未宣言の識別子。関数呼び出しではない) |
| `member reference base type ... is not a structure or union` | 2 | 未分類 |
| `integer literal is too large to be represented in any integer type` | 1 | 未分類 |
| 合計 | 1,377 | |

- 前版 (`bb076c69` 系) の「`call to undeclared function` 63 件」「約 1,245」「約 35」は、この数え直しで再現しなかった (emcc 出力に該当 0 件)。上表の正確な件数に置き換える。

**数え直しの手順** (block19091, 修復後の `r19091/*.c` を 1 ファイルずつ `emcc -c -w -O0 -fno-strict-aliasing -ferror-limit=0` に通す):
- error 行の抽出: `grep -E '^[^ ]+:[0-9]+:[0-9]+: (fatal )?error: '` → 1,377 行。
- 分類: 行頭の `file:line:col: error: ` を除き、引用符内を `X` に置換して `sort | uniq -c`。
- `error generated` 行は件数集計の対象外 (ファイルごとの合計表示)。

**本 run の再測定** (fix モード、PR #1681 の差し戻し対応。コードは変更していない):
- `retdec_batch.py` (block19091): lift 19,812 / 19,816 (no_definition 4) を再現。所要 254.74 s / 249.40 s (2 回。`retdec_seconds_all`)。
- `retdec_repair.py --int-ptr`: 宣言 921、`&` 1,993 (上表と一致)。
- `emcc_per_function.py`: 通過 18,932・error 行 1,377・exit 0 は 1 / 40・`failclosed_files` 1・`unattributed_error_lines` 1・emcc 合計 6.02 s (上表と一致)。
- 計測環境: `[RETDEC]` v5.0・`[EMSDK]` 6.0.12・`fl-win64` (`$RUNNER_TEMP` に展開)。load average (1 分値) は計測開始時 1.10。

**受入条件の判定**:
- 受入条件 1 (int/pointer 混在の修復): 達成。`-Wint-conversion` 行は block19091_0.c 単体で 46 → 0 件、全 40 ファイルでも修復後 0 件 (実測)。全 40 ファイルの error 行は 11,432 → 1,377。
- 受入条件 2 (goto/break の扱い): 判断を記録。`break`・`undeclared label` (計 94 件) は機械的修復を行わない。根拠は上表 (C の制御構造を変える修復は silent miscompile になり得る)。
- 受入条件 3 (emcc exit 0 件数): 未達。exit 0 は block19091 / block23676 とも 40 件中 1 件。残るのは goto/break (94 件) と引数型の不一致 (1,245 件) で、これは上表の「不可」類型のため、機械的修復では 40 件全てを exit 0 にできない。

**未解決 (起票先)**: goto/break・undeclared label の制御構造復元 → #1679 (HB-H35)。引数型不一致 (1,245 件) の型推定修復 → #1680 (HB-H36)。

**未検証 (本 run の範囲外)**:
- `(int64_t)&x` の値が RetDec の意図と一致するかは、wasm 実行系が無いため未検証。wasm32 では `void*` 4B・`int64_t` 8B で、キャストは番地を拡張するだけという実測のみ (`(int64_t)&g94` = `0x10bb0`)。
- 修復後の関数が機械語どおりに動くかは未検証 (link・実行は未実施)。
- `no_definition` 4 件の原因は未特定 (§8 と同じ)。

## 8 の判定修正段落 (分割移動・#1522 判定修正前の記述)

`DEF_RE` の `[^;=]*` が改行をまたぎ、前関数の閉じ `}` 直後のコメント行から次の定義行までを 1 つの一致に飲み込んでいた。その結果、定義行が見えず `no_definition` になっていた。`[^\n;=]*` / `[^\n;{}]*` に直して再計算すると、93 件のうち 89 件は定義あり。残り 4 件 (0x41c480・0x570b30 と block19091 の 0x86ab10 / 0x87cdf0、block23676 の 0x86a970 / 0x87cfc0) は RetDec 出力に定義が無い。`no_definition` の 4 件は §1 の decode 不能範囲とは重ならない。原因は未特定。`0x86ab10` / `0x86a970` は CreatePlugInstance。
(この 4 件の後続の扱いは REPORT §10 を正本とする。)
