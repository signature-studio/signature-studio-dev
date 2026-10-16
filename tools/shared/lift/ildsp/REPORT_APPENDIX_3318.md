# ildsp CreateInstance closure の wasm 化の入口 (T-SH-65 #3318・部分達成) の付録

親: #3318。REPORT_CI.md §8 の結論の詳細。測定値の正本はこの付録。

## 1. 範囲
- 作ったもの: (a) RetDec 出力の use-list 指令 (`uselistorder`) を除いた IR (`ci.emc.ll`) の emcc obj 化 gate、(b) 間接 call 2 件の trap 定義 (`ci_traps.c`)。
- 作らないもの (#3318 に残す): IAT 10 種の stub、外部グローバル 2 種、範囲外の直接 call 先 1 種、`__stack_pointer` の供給、画像敷設、wasm のリンク・実行、native 差分、受入 4・5 の REPORT 確定。

## 2. 変更点 (コード)
- `tools/shared/lift/ildsp/ci_lift.sh`:
  - `ci.rs_norm.ll` から `uselistorder` 行を除いて `ci.emc.ll` を作る。LLVM 21 系の emcc が `uselistorder i64 %arg1, { 1, 0, 2 }` の index 数を受け付けず、`clang` が `wrong number of indexes, expected 4` で止まったため (順序メタ情報で意味は持たない)。
  - `ci.emc.ll` を `-c` で obj 化、`ci_helpers.c` も obj 化。
  - 間接 call 2 件の宛先 `function_1801cb5e0`・`function_1801cb600` の declare (i64) を検査し、`uint64_t f(void){ __builtin_trap(); }` を `ci_traps.c` に生成して obj 化。declare が無ければ exit 1。
- 測定 commit: `6220b651d` (gate と trap を入れた最後のコード commit)。`4ed054729` はヘッダコメントだけの変更で、`git diff 6220b651d HEAD -- tools/shared/lift/ildsp/ci_lift.sh` はコメント 3 行の差分 (実行経路は同じ)。HEAD `4ed054729` でも §3 の値を再測定した (下の注)。

## 3. 実測 (測定 commit `6220b651d`・HEAD `4ed054729` で再測定・4 core・n=3)
| 項目 | 値 |
|---|---|
| 実行時間 (`date` で計測) | 6220b651d: 1.816 / 1.774 / 1.870 s。HEAD 4ed054729: 1.837 / 1.801 / 2.065 s |
| load (実行前の 1 分平均) | 6220b651d: 0.36 / 0.41 / 0.41。HEAD: 0.26 / 0.26 / 0.32 |
| 3 回の stdout | `cmp` で 3 回とも一致 (両 commit)。rc 0・ALL OK・`[ci] emcc obj OK`・`[ci] traps: function_1801cb5e0, function_1801cb600` |
| 生成物 `ci.rs.ll` | md5 `4811e83e9e4343ad70e6ec883023641f` (§7-2 と同じ) |
| 生成物 `ci_helpers.c` | md5 `497d886223a0625f2b236d105c7df119` (§7-2 と同じ) |

## 4. ネガティブコントロール
| 名前 | 壊し方 | 結果 |
|---|---|---|
| NC-trap | `ci.emc.ll` から `declare i64 @function_1801cb600` を削除して検査だけを実行 | `[ci] indirect call target not declared as i64: function_1801cb600`・rc 1 |

## 5. emcc のリンク時の未解決 (未対応・#3318 に残す)
`ci.emc.o` の未定義シンボル (`llvm-nm` の `U`) のうち、ci_helpers.o / ci_traps.o で定義されないもの (`tools/shared/work/lift/ci/und_left.txt` の 14 件。リンクは未実施):
| シンボル | 種別 | 件数・出どころ |
|---|---|---|
| EnterCriticalSection・FlsGetValue・FlsSetValue・GetLastError・HeapAlloc・HeapFree・LeaveCriticalSection・RaiseException・RtlPcToFileHeader・SetLastError | IAT (10 種) | 受入 2 (IAT stub) |
| `function_1801aef40` | 範囲外の直接 call 先 (jcc 先・.pdata 無し) | §2-2 (a)。受入 5 |
| `global_var_1803f6610` | `external global i64` (IR 27 行目で宣言のみ・定義なし。IR 45 行目以降で参照) | 画像敷設 (受入 1) |
| `__unnamed_1` | IR 中の `@0` (`external global i32`・`ret i64 ptrtoint (ptr @0 ...)`) の出どころ | 画像敷設 (受入 1) |
| `__stack_pointer` | wasm の shadow stack (リンク時に供給される) | リンク設定 |

注: 間接 call の宛先 2 件 (`function_1801cb5e0`・`function_1801cb600`) は `ci_traps.o` の trap で定義済み (`ci.emc.o` の U に残るが `und_left.txt` からは外れている)。リンクは未実施 (wasm 化は #3318 に残す)。

## 6. 検証範囲 / 範囲外
- 範囲: IR を emcc で obj 化できること・trap 定義の生成と検査。
- 範囲外: wasm のリンク・実行、IAT の意味、閉包の取りこぼし (a)(b)、分岐複製の扱い (受入 4)、native 差分。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> RETDEC_BIN=<retdec/bin/retdec-decompiler> bash tools/shared/lift/ildsp/ci_lift.sh`
