# ildsp CreateInstance closure の wasm 化の入口 (T-SH-65 #3318・部分達成) の付録

親: #3318。REPORT_CI.md §8 の結論の詳細。測定値の正本はこの付録。

## 1. 範囲
- 作ったもの: (a) RetDec 出力の use-list 指令 (`uselistorder`) を除いた IR (`ci.emc.ll`) の emcc obj 化 gate、(b) 間接 call 2 件の trap 定義 (`ci_traps.c`)。
- 作らないもの (#3318 に残す): IAT 10 種の stub、外部グローバル 2 種、範囲外の直接 call 先 1 種、`__stack_pointer` の供給、画像敷設、wasm のリンク・実行、native 差分、受入 4・5 の REPORT 確定。

## 2. 変更点 (コード)
- `tools/shared/lift/ildsp/ci_lift.sh`:
  - `ci.rs_norm.ll` から `uselistorder` 行を除いて `ci.emc.ll` を作る。LLVM 21 系の emcc が `uselistorder i64 %arg1, { 1, 0, 2 }` の index 数を受け付けず、`clang` が `wrong number of indexes, expected 4` で止まったため (順序メタ情報で意味は持たない)。
  - `ci.emc.ll` を `-c` で obj 化、`ci_helpers.c` も obj 化。
  - 間接 call 2 件の宛先 `function_1801cb5e0`・`function_1801cb600` の declare を検査し、`uint64_t f(uint64_t a){ (void)a; __builtin_trap(); }` を `ci_traps.c` に生成して obj 化。検査は `^declare i64 @<name>\(i64\) ` (引数 1 個の i64) に限る。declare が無い・引数の型や個数が違う場合は exit 1。
  - RetDec 出力の実際の declare は `declare i64 @function_1801cb5e0(i64) local_unnamed_addr` と `...cb600(i64)` で、引数は 1 個の `i64` (直前の `()` 版は実 IR と合わず exit 1 になった。§4 の NC-B)。
- 測定 commit: `6220b651d` (gate と trap を入れた時点)。以降の変更は `4ed054729` (ヘッダコメントのみ)・`5dd6a2118` (docs のみ)・`2c4b02070` (検査の正規表現)・本 fix の commit (検査を `i64(i64)` に直し、trap の定義を引数付きにした)。§3 の実測は測定 commit `374feea46` (コードを変えた最後の commit) で取った値。`374feea46..HEAD` の `tools/shared/lift` の差分は本付録の 1 行 (文言) のみで、実行経路の差分は 0 (`git diff 374feea46 HEAD -- tools/shared/lift/ildsp/ci_lift.sh` の出力は空)。

## 3. 実測 (測定 commit `374feea46`・RetDec v5.0・emsdk 6.0.12・4 core・n=3)
素材: `fl-win64` (`fl-win64` の tarball を `tar --zstd -xf` で展開、`extracted/block24360_PE.bin`)。RetDec は `RetDec-v5.0-Linux-Release.tar.xz` (GitHub release)、emsdk は `emsdk install 6.0.12`。この run の runner には `[EMSDK]`・`[RETDEC]` の入っていない環境だったので、上の取得で用意した (`docs/REFERENCES.md` の `toolchain-retdec`・`toolchain-emsdk`)。

| 項目 | 値 |
|---|---|
| 実行時間 (`date` で計測) | 2.812 / 2.759 / 2.759 s (run 1–3。直前の検証 run で 2.769 / 2.768 / 2.770 s) |
| load (実行前の 1 分平均) | 0.63 / 0.63 / 0.66 (run 1–3。`/proc/loadavg`) |
| rc | 0 / 0 / 0 |
| 3 回の stdout | `md5 e4d10020de6d16c6637d7a0e4a258fb5` で 3 回とも一致 (`cmp` 一致) |
| stdout の内容 | `[census] ALL OK`・`[ci] emcc obj OK (uselistorder 除去後の IR と helper)`・`[ci] traps: function_1801cb5e0, function_1801cb600` |
| 生成物 `ci.rs.ll` | md5 `4811e83e9e4343ad70e6ec883023641f` (§7-2 と同じ) |
| 生成物 `ci_helpers.c` | md5 `497d886223a0625f2b236d105c7df119` (§7-2 と同じ) |
| 生成物 `ci_traps.c` | `uint64_t function_1801cb5e0(uint64_t a) { (void)a; __builtin_trap(); return 0; }` と同形の `function_1801cb600` の 2 行 |

RetDec 出力の該当行 (原文・`work/lift/ci/ci.rs.ll` の 2262・2264 行目):
```
declare i64 @function_1801cb5e0(i64) local_unnamed_addr
declare i64 @function_1801cb600(i64) local_unnamed_addr
```

## 4. ネガティブコントロール
検査部分 (`ci_lift.sh` の python ブロックそのもの) を、実 RetDec の `ci.emc.ll` に対して直接実行した。

| 名前 | 壊し方 | 結果 |
|---|---|---|
| 正例 (実 IR) | 実 RetDec の `ci.emc.ll` をそのまま入力 | `[ci] traps: function_1801cb5e0, function_1801cb600`・rc 0 |
| NC-A | `declare i64 @function_1801cb600(...)` の行を削除 | `[ci] indirect call target not declared as i64(i64): function_1801cb600`・rc 1 |
| NC-B | `function_1801cb5e0` の declare を `()` に書き換え (2c4b02070 の検査が受理した形) | `[ci] indirect call target not declared as i64(i64): function_1801cb5e0`・rc 1 |
| NC-C | `function_1801cb600` の declare を `(i64, i64)` に書き換え (引数個数違い) | `[ci] indirect call target not declared as i64(i64): function_1801cb600`・rc 1 |

注: NC-B は 2c4b02070 の検査 (`()` 限定) が実 IR では誤って落ちることの確認。そのため本 fix で `(i64)` に直した。

## 5. emcc のリンク時の未解決 (未対応・#3318 に残す)
`ci.emc.o` の未定義シンボル (`llvm-nm` の `U`) のうち、ci_helpers.o / ci_traps.o で定義されないもの (14 件。リンクは未実施。集合差の手順は §6):
| シンボル | 種別 | 件数・出どころ |
|---|---|---|
| EnterCriticalSection・FlsGetValue・FlsSetValue・GetLastError・HeapAlloc・HeapFree・LeaveCriticalSection・RaiseException・RtlPcToFileHeader・SetLastError | IAT (10 種) | 受入 2 (IAT stub) |
| `function_1801aef40` | 範囲外の直接 call 先 (jcc 先・.pdata 無し) | §2-2 (a)。受入 5 |
| `global_var_1803f6610` | `external global i64` (IR 27 行目で宣言のみ・定義なし。IR 45 行目以降で参照) | 画像敷設 (受入 1) |
| `__unnamed_1` | IR 中の `@0` (`external global i32`・`ret i64 ptrtoint (ptr @0 ...)`) の出どころ | 画像敷設 (受入 1) |
| `__stack_pointer` | wasm の shadow stack (リンク時に供給される) | リンク設定 |

注: 間接 call の宛先 2 件 (`function_1801cb5e0`・`function_1801cb600`) は `ci_traps.o` の trap で定義済み。リンクは未実施 (wasm 化は #3318 に残す)。

## 6. 検証範囲 / 範囲外
- 範囲: IR を emcc で obj 化できること・trap 定義の生成と検査。
- 範囲外: wasm のリンク・実行、IAT の意味、閉包の取りこぼし (a)(b)、分岐複製の扱い (受入 4)、native 差分。
- 再現: `FL_WIN64_DIR=<fl-win64 展開先> RETDEC_BIN=<retdec/bin/retdec-decompiler> bash tools/shared/lift/ildsp/ci_lift.sh`
- 未解決 14 件の再現 (`ci_lift.sh` の出力 `work/lift/ci/` に対して): `comm -23 <(llvm-nm -u work/lift/ci/ci.emc.o | awk '{print $NF}' | sort -u) <(llvm-nm --defined-only work/lift/ci/ci_helpers.o work/lift/ci/ci_traps.o | awk '{print $NF}' | sort -u)` (`ci_lift.sh` は `und_left.txt` を書かない。上の集合差で得る。`ci_traps.o` の trap 2 件は定義済みとして差し引く。`work/` は gitignore 対象)。
