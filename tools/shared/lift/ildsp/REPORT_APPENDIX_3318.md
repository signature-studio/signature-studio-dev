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
- 測定 commit: `374feea46` (検査を `i64(i64)` に直し、trap の定義を引数付きにした。コードを変えた最後の commit)。以降の変更は `ci_census.py` の orphan 検査 `7cbb217a6` (#5749。`ci_lift.sh` の census を rc 1 にする) と docs。§3 の実測は、この検査を含む現 head `63f896abe` (`0e1000df5` に `origin/main` を merge) で取った値。`git diff 0e1000df5 HEAD -- tools/shared/lift` は空。`0e1000df5` 以降の `tools/shared/lift` の実行経路の差分は 0。
- trap 化の理由: 間接 call の 2 件は CFG/XFG dispatch を経由し、宛先は実行時の `rax` で決まる。IR の固定名 declare (`function_1801cb5e0`・`function_1801cb600`) からは宛先が一意に決まらないため、IR の呼出しを実行するとどの宛先かを決められず、到達時に止める形 (`__builtin_trap`) にした。
  - slot `0x268260` (`GuardCFDispatchFunctionPointer`): 呼出し元 `0x1aedf6` (helper `0x1aedc0`)。file 値 `0x1cb5e0` は `jmp rax`。`rax` は引数から辿る vtable の index 8 で、オブジェクトは実行時の値。
  - slot `0x268268` (`GuardXFGDispatchFunctionPointer`): 呼出し元 `0x1b6f6c` (helper `0x1b6f4c`)。file 値 `0x1cb600` は `jmp [0x268260]`。`rax` は `0x1b6f88` の戻り値で、実行時の値。
  - 静的解析の根拠は `REPORT_APPENDIX_3346.md` §3 (CFG/XFG dispatch → `rax`・trap 化)。到達条件は未確定で、到達の実測は #3250 (`REPORT_APPENDIX_3250.md`・`REPORT_APPENDIX_4230.md`)。

## 3. 実測 (現 head `63f896abe`・RetDec v5.0・emsdk 6.0.12・4 core・測定 run 1–3)
素材: `fl-win64` (`fl-win64.tar.zst` を `tar --zstd -xf` で展開、`extracted/block24360_PE.bin` 4197376 B)。
RetDec は `RetDec-v5.0-Linux-Release.tar.xz` (GitHub release、`retdec-decompiler --version` = v5.0)、emsdk は `emsdk install 6.0.12` (`emcc --version` = 6.0.12)。この 2 つは **台帳外の取得** で、`docs/REFERENCES.md` の `toolchain-retdec`・`toolchain-emsdk` の取得元欄には反映していない (両方とも `[未確認]` のまま)。runner の既定の場所 (`[EMSDK]`・`[RETDEC]` の想定先) に無かったので、上の手順で用意した。

**実測 1 (`ci_lift.sh` 全体・3 回)**: 3 回とも rc 1 (census の orphan 検査で止まる。#5749 の意図した gate)。stdout は 3 回とも同一 (md5 `867d9a5454fb5a8c87e2b43ff15c8900`)。末尾は `[census] FAIL` で、範囲外の define 9 件 (`function_1801af090` ほか 8 件) が IR のどの call からも参照されない。実行時間 2.202 / 2.232 / 2.233 s (`date` で計測)、load 0.49 / 0.49 / 0.49 (実行前の 1 分平均)。

**実測 2 (census 以降を単独実行・3 回)**: `ci_lift.sh` の census 以降の行 (`ir_normalize.py`・`gen_helpers.py`・uselistorder 除去・`emcc -c`・trap 検査・`emcc -c`) を同じ順序で手で実行した。3 回とも rc 0。実行時間 0.500 / 0.500 / 0.500 s (`date` で計測)、load 0.49 / 0.49 / 0.49。stdout は 3 回とも同一:
```
[ci] emcc obj OK (uselistorder 除去後の IR と helper)
[ci] traps: function_1801cb5e0, function_1801cb600
[ci] trap obj OK
```
生成物 (現 head・3 回の実行後): `ci.rs.ll` md5 `4811e83e9e4343ad70e6ec883023641f`、`ci_helpers.c` md5 `497d886223a0625f2b236d105c7df119`、`ci.emc.ll` md5 `f2e5325d016ed7c67ab49c6112ca35ba`、`ci_traps.c` md5 `9bb7fd2852761815b28c38b59c572adf` (`uint64_t function_1801cb5e0(uint64_t a) { (void)a; __builtin_trap(); return 0; }` と同形の `function_1801cb600` の 2 行)。

RetDec 出力の該当行 (原文・`work/lift/ci/ci.rs.ll` の 2262・2264 行目):
```
declare i64 @function_1801cb5e0(i64) local_unnamed_addr
declare i64 @function_1801cb600(i64) local_unnamed_addr
```

なお、`ci_lift.sh` 全体が rc 1 のため、受入 3 の検証は「census を通す」形では完了していない。census の orphan 検査 (#5749) は (b) の欠落を正しく検出しており、検査は弱めていない。後段の単独実行が通ることだけを §3 の実測 2 で示す。

## 4. ネガティブコントロール
trap 検査部分 (`ci_lift.sh` の python ブロックそのもの) を、現 head の実 RetDec の `ci.emc.ll` に対して直接実行した (実測 2 と同じ生成物)。

| 名前 | 壊し方 | 結果 |
|---|---|---|
| 正例 (実 IR) | 実 RetDec の `ci.emc.ll` をそのまま入力 | `[ci] traps: function_1801cb5e0, function_1801cb600`・rc 0 |
| NC-A | `declare i64 @function_1801cb600(...)` の行を削除 | `[ci] indirect call target not declared as i64(i64): function_1801cb600`・rc 1 |
| NC-B | `function_1801cb5e0` の declare を `()` に書き換え (2c4b02070 の検査が受理した形) | `[ci] indirect call target not declared as i64(i64): function_1801cb5e0`・rc 1 |
| NC-C | `function_1801cb600` の declare を `(i64, i64)` に書き換え (引数個数違い) | `[ci] indirect call target not declared as i64(i64): function_1801cb600`・rc 1 |

注: NC-B は 2c4b02070 の検査 (`()` 限定) が実 IR では誤って落ちることの確認。そのため `(i64)` に直した。

## 5. emcc のリンク時の未解決 (未対応・#3318 に残す)
`ci.emc.o` の未定義シンボル (`llvm-nm` の `U`) のうち、ci_helpers.o / ci_traps.o で定義されないもの (現 head で 14 件を再確認。リンクは未実施。集合差の手順は §6):
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
- 再現 (census まで): `FL_WIN64_DIR=<fl-win64 展開先> RETDEC_BIN=<retdec/bin/retdec-decompiler> EMSDK_ENV=<emsdk_env.sh> bash tools/shared/lift/ildsp/ci_lift.sh`。現 head では census の FAIL で rc 1 になる (§3 実測 1)。
- 再現 (census 以降): census の後段 (`ir_normalize.py`・`gen_helpers.py`・`grep -v '^ *uselistorder '`・`emcc -c`・trap 検査・`emcc -c`) を `ci_lift.sh` と同じ順序で実行する。rc 0 になる (§3 実測 2)。
- 未解決 14 件の再現: `comm -23 <(llvm-nm -u work/lift/ci/ci.emc.o | awk '{print $NF}' | sort -u) <(llvm-nm --defined-only work/lift/ci/ci_helpers.o work/lift/ci/ci_traps.o | awk '{print $NF}' | sort -u)` (`llvm-nm` は emsdk の `upstream/bin`。`ci_lift.sh` は `und_left.txt` を書かない。`ci_traps.o` の trap 2 件は定義済みとして差し引く。`work/` は gitignore 対象)。
