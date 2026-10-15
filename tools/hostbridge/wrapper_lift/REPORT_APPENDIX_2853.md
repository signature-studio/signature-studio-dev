# REPORT 付録 — #2853 (HB-H47): RetDec 分割 lift C の残存 emcc error 8 件の切り分けと struct 宣言の修復

> **正本**: `tools/hostbridge/wrapper_lift/REPORT.md` §12。本付録は #2853 の計測の全文。
> 結論 1 行: 残り 8 件のうち struct 代入 3 件と member 参照 2 件 (計 5 件) は、`__asm_*` helper の宣言を RetDec 自身の struct 型に写す `retdec_repair.py --struct` で直る。未宣言 identifier 2 件と整数リテラル 1 件は直さない (§2)。両 block とも emcc error 51 → 46、exit 0 23 → 25 / 41。

測定 commit: `7e332cbf8` (`retdec_repair.py` の `--struct` を入れた最後の commit。この commit の後にコードは変えていない)。
基準: `bd4463eaa` (origin/main。`retdec_repair.py` は f70faf97 と同一。基準値は付録 `REPORT_APPENDIX_2071.md` §3 と一致)。
環境: `[RETDEC]` v5.0 (`toolchain-retdec`)・`[EMSDK]` 6.0.12 (`toolchain-emsdk`)・`fl-win64` (`block19091_PE.bin` / `block23676_PE.bin` のみ展開)。
load average (uptime 採取値) 0.39–0.53 (1 分値)。

## 1. 測定

手順: `retdec_batch.py` (raw C は両 block で新規に作成) → `retdec_repair.py <flags>` → `retdec_gotofix.py` → `emcc_per_function.py`。

| 条件 | block19091 exit 0 / error 行 / 関数通過 | block23676 exit 0 / error 行 / 関数通過 |
|---|---|---|
| 基準 (`bd4463eaa`・`--wide --int-ptr`) | 23 / 41・**51**・19,779 / 19,816 | 23 / 41・**51**・19,789 / 19,826 |
| 修復後 (`7e332cbf8`・`--struct --wide --int-ptr`) | 25 / 41・**46**・19,783 / 19,816 | 25 / 41・**46**・19,793 / 19,826 |
| 従来経路 (`7e332cbf8`・`--wide --int-ptr`、`--struct` 無し) | 23 / 41・51・19,779 | 23 / 41・51・19,789 |

- 従来経路の出力 (`rep` ディレクトリ) は基準と `diff -r` で一致 (差分 0。両 block)。`--struct` が opt-in であることの確認。
- `struct_decl_fixed` 5 件・`struct_error_lines_removed` 5 件 (両 block)。`functions_with_error` 34 → 30。
- 残り 46 行 = `statement not in loop` 27 + `use of undeclared label` 16 (#1954 の範囲・未変更) + 下の未修復 3 件。
- 所要: `retdec_batch.py` (raw 作成) block19091 231.0 s (41 回、fail 0)・block23676 198.3 s (41 回、fail 0)。修復から emcc まで block19091 25 s (基準 19 s)・block23676 28 s (基準 18 s)。`emcc_seconds_sum` 基準 5.3 s → 修復後 5.5 s / 7.0 s (負荷による変動あり)。

## 2. 8 件の切り分け (RetDec 出力 C の行と型の観点)

| 件 (block19091 位置) | 診断 | 原因 (RetDec 出力の根拠) | 処置 |
|---|---|---|---|
| 0.c:7894 `v1 = __asm_cpuid((int32_t)a2);` | assigning to `struct struct1` from `int64_t` | 代入先は `struct struct1 v1;` (0.c:7892)。helper は `int64_t __asm_cpuid();` と宣言されている | 修復: 宣言を `struct struct1 __asm_cpuid();` |
| 7500.c:9598 `v1 = __asm_cpuid(a1);` | 同 `struct struct3` | 代入先は `struct struct3 v1;` (直前行)。`__asm_cpuid` の呼出しはこの 1 箇所 | 修復: `struct struct3 __asm_cpuid();` |
| 7500.c:9658 `v1 = __asm_cpuid_6(1);` | 同 `struct struct1` | 代入先は `struct struct1 v1;`。`__asm_cpuid_6` の呼出しはこの 1 箇所 | 修復: `struct struct1 __asm_cpuid_6();` |
| 1500.c:11219 `uint32_t v1 = __asm_cpuid(1).e2;` | member reference base `int64_t` | `.e2` の持ち主は 1500.c で `struct struct1` のみ (定義 16 行) | 修復: `struct struct1 __asm_cpuid();` |
| 7500.c:9653 `if (__asm_cpuid_5(0).e0 == 0)` | 同 (`.e0`) | 代入が無く `.e0` のみ。7500.c の struct1/2/3 は同一レイアウト (int32 e0〜e3)。`.e0` の読みは tag に依存しない | 修復: `struct struct1 __asm_cpuid_5();` (同一レイアウトの中で定義が最初のもの) |
| 500.c:9017 `switch ((int32_t)v3)` | use of undeclared identifier `v3` | `v3` は `function_439b50` (8995 行〜) 内の宣言 (9003 行) で、参照は別関数 `function_439ba0` (9011 行〜)。関数跨ぎ | **直さない**。宣言を持ち上げると別関数の状態を共有する (RetDec のスコープ・型の誤り)。値の出所を推定することになる |
| 5000.c:7320 `switch ((int32_t)v4)` | 同 `v4` | `v4` は `function_536cc0` (7275 行〜) 内で、7320 行より前に宣言も代入も無い | **直さない**。値を推測することになる (silent miscompile の危険) |
| 500.c:2218 `while (... || v14 & -0x10000000000000000)` | integer literal is too large | 500.c:12 に `typedef int64_t int128_t;` (500.c の `int128_t` は 64bit)。`-2^64` は clang の整数リテラル上限 (64bit) を超える | **直さない**。前 run の提案 `((int128_t)-1 << 64)` は、この typedef では 64bit 型の 64 ビットシフト (未定義動作)。さらに `||` の右辺 `v14 & -2^64` は 128bit で v14 < 0 のとき真になるが、0 に置換すると常に偽になり、値が変わる |

- block23676 も同じ 8 件 (行番号が 1〜2 行ずれる: 1500.c:11218・7500.c:9599/9654/9659 ほか)。修復の結果は §1 の表の通り。
- 修復は `int64_t` → `struct` の宣言行の置換のみ (行数不変・本体の式は不変)。helper の実装は呼出し規約上は struct 戻り値 (sret) として扱われる。実装 (戻り値の 4 つの int32 の並び) は RetDec の推定で、実機の値は未検証。

## 3. 修復ルールの定義と負の対照

`retdec_repair.py --struct` (`struct_helper_fixes`) は次の条件を全て満たす helper だけ宣言を直す:
1. 宣言 `int64_t NAME();` が 1 つだけあり、診断 (`assigning to 'struct T' from 'int64_t'` / `member reference base type 'int64_t'`) の行にだけ `NAME(` が現れる (他の行の呼出しが無い)。
2. 代入先の struct T が一意 (複数なら直さない)。代入が無いときは、`.eN` の member を全て持つ struct のうち定義順で最初のもの。候補の layout が 1 種類だけのときだけ採る。
3. T は宣言より前に定義されている。
4. 直した後の emcc 診断の行が、直す前の部分集合 (新しい error 行が出たら戻す)。

負の対照 (合成入力、`struct_helper_fixes` を直接呼出し。入力は `$RUNNER_TEMP/nc`・測定 commit `7e332cbf8`):

| 入力 | 期待 | 結果 (宣言の行 / 除去した error 行) |
|---|---|---|
| `pos.c`: `v1 = __asm_cpuid(1);` (struct1 変数) のみ | struct1 に変わる | `struct struct1 __asm_cpuid();` / 1 |
| `neg_nonerr.c`: `pos.c` + 診断の無い行 `return __asm_cpuid(2);` (int64 戻り) | 変えない (呼出しが診断行の外) | `int64_t __asm_cpuid();` / 0 |
| `neg_tags.c`: struct1 と struct3 の変数へ代入 | 変えない (T が一意でない) | `int64_t __asm_cpuid();` / 0 |

## 4. 未検証・注意

- 修復後の C の wasm 実行 (bit 一致) は未検証。RetDec 路線の wasm link は REPORT §13 の通り未達で、採用経路は x64c。
- `__asm_cpuid*` の戻り値 struct の並びは RetDec の変数型からの推定。実 helper の戻り値との一致は未確認。
- 7500.c:9653 (`__asm_cpuid_5`) の tag は struct1 を選んだ。struct1/2/3 は同一レイアウトのため `.e0` の読みは同じ。tag の取り違えが起きても emcc の通過と値は変わらないが、推測を含む。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `v3` (500.c:9017)・`v4` (5000.c:7320)・`int128_t` の 64bit typedef による `-2^64` リテラル (500.c:2218) の 3 件。直さない | 500.c・5000.c の 2 ファイルが emcc exit 非 0 のまま (残 46 行の 3 行) | PM 判断 (RetDec 路線の残件。D5 により新規作業の起票を見送り) |
| `statement not in loop` 27・`use of undeclared label` 16 (両 block) | exit 0 の残り (25/41 の残り 16 ファイル) の主因 | #1954 (HB-H41) |
