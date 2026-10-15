# reverb_delay REPORT 付録 (#523 PLG-F4-2 追補)

本体 `REPORT.md` の §12 に続く節。 250 行上限のため分割して置く。

## 13. #523 追補 (2026-10-13 · 測定起点 HEAD 986e7415 · 再測定)

- **測定起点**: main **986e7415** (§13 の測定はこの HEAD で行った。 本 PR は docs のみで engine コードは変更していない)。 `REPORT.md` §12 の起点 97f28539 は E6 修正 (b5372ec3) の親で、作業ブランチ `523-plg-f4-2-engine-lift` の起点。 両者は祖先関係 (97f28539 → 986e7415) にある。
- **素材の確認 (本 PR の fix run、2026-10-13 17:54 UTC)**: `$HOME/artifacts` には `fl-win64.tar.zst` (2.3 GB) のみ実在。 `toolchain-retdec` / `toolchain-emsdk` / `work-*` / `plugins-ott` は確認時点で不在。 したがって本 run では e2e・engine lift を再実行できず、 下表の数値は再現していない。 §13 の測定時に上記素材が揃っていたかは、 PR 本文の記録以外に確認できない。
- **run の別**: 19165 の測定は §12 (15:37:59–15:48:22 UTC、wall 10 分 23 秒、summary.csv 行あり) と §13 (wall 6 分 42 秒) の 2 回として記録されている。 条件 (IPPCODE 除外 + AVX 系 78 除外) は同じで、 wall が一致しないため同一 run の再掲ではないと判断した。 §13 の run の開始時刻は記録していない。 各 run は 1 回のみ。
- engine の正しさは示さない (到達性のみ)。 負荷 (load) は測定していない。

| engine | 条件 | lift rc | define | f80 関数 | `emcc -c` rc | lift 秒 (PR 本文) | wall (PR 本文) |
|---|---|--:|--:|--:|--:|--:|--:|
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 (`avx_bad_ranges.py`) | 0 | 2,608 | 6 | **139 (segfault)** | 391 | 6 分 42 秒 |
| 19165 同上 | 同 + `PLUG_F80_LOWER=1` | 0 | 2,608 | 0 | **1** | 416 | 6 分 57 秒 |
| 19000 Delay 3 | `PLUG_F80_LOWER=1` (全 3,632 関数) | 0 | 4,107 | 0 | **0** | 未記録 | 2 分 7 秒 |

- 秒の列は PR 本文の値のみ。 旧版の付録は表見出しを「秒 (lift+emcc)」としていたが、本文の lift 時間 (391 s) と wall の内訳は記録になく、wall を正とする。

- **19165 segfault の位置**: `emcc` は `function_1800ceec0` の WebAssembly 命令選択 (DAG combine の `visitSTORE`) で落ちる。 同関数は x86_fp80 を含む (`final.ll` の f80 関数 6 本のうち 1 本)。 `PLUG_F80_LOWER=1` で f80 を外すと segfault は消える。
- **19165 の次の類型 (f80 lowering 後)**: `e.final.ll:273362: invalid cast opcode for cast from 'double' to 'i80'`。 `p0c/f80_lower.py` は `bitcast x86_fp80 to i80` (f80 のビット列を読む命令) を double に置換するが、`bitcast double to i80` を残す。 f80 のビット操作を扱えないことが原因と推定。 この類型は共有鎖 (`p0c/f80_lower.py`) の修正が必要で、T0/T1 の退行確認 (#523 受入条件 2) を伴うため、本 run では未修正。 **新類型 E7 (f80 ビット操作の lowering 漏れ)** として記録。 **§14 で改訂 (推定)**: 上流の lift 側の型誤りが本体の可能性が高い。 対処の順序は §14 を参照。
- **19000 の f80 lowering**: `PLUG_F80_LOWER=1` は f64 化で精度を落とす (53 bit 仮数)。 19000 の f80 関数 (`function_1800bcb00` ほか) の精度影響は未検証。 既定 (`PLUG_F80_LOWER=0`) では `emcc -c` が rc 1 のまま (REPORT §12 の既存結果)。
- 19165 の segfault の起点 (`function_1800ceec0`) と f80 6 本の内訳は測定時の `work/reverb_delay/engine19165_noipp_nobad/` (gitignore) に残したが、 本 runner の `work/` には存在しない。 再現手順は下記。

### 再現手順

```
source tools/plugins/reverb_delay/env.sh
python3 tools/plugins/reverb_delay/avx_bad_ranges.py 19165 > work/reverb_delay/bad19165.out
ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges $PWD/work/reverb_delay/bad19165.out" \
  ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_lift.sh 19165 1200
PLUG_F80_LOWER=1 bash tools/plugins/reverb_delay/engine_lift.sh 19000 800
```

注: `--exclude-ranges` には絶対パスを渡す (`engine_lift.sh` が `tools/plugins` へ cd するため相対パスは解決されない)。 再現には `fl-win64` に加えて `toolchain-retdec` / `toolchain-emsdk` が要る。

### 受入条件への対応 (#523)

1. 19000 は `PLUG_F80_LOWER=1` で `emcc -c` rc 0 (到達性のみ・精度未検証)。 19165 は未達 (E7)。 既定 (f80 lowering 無し) では両方未達。
2. 共有鎖 (`p0c/f80_lower.py`) は未変更のため退行確認は不要だが、E7 の修正時に必要。 未実施。
3. IPPCODE の扱い: 未決 (#38 [IPP-10] と PM 判断)。
4. LoadLibrary 結合解析: 未実施。

## 14. #523 E7 の切り分け (2026-10-13 · コード変更なし · 未再現)

- **位置付け**: §13 の E7 記述を本節で改訂する (診断は下記の推定を採る)。 測定値・rc・再現手順は §13 が正本。 本節は未再現の転記で、再測定はしていない。
- **IR 位置 (未再現・転記)**: `e.final.ll` の `function_1800ceec0` 内、ブロック `dec_label_pc_1800ceffe` の `bitcast x86_fp80 %12 to i80` → `trunc i80 to i64` → `inttoptr` (行 273381・273392 付近)、`sext i32 to i80` → `bitcast i80 to x86_fp80` (行 273480・273633 付近)。 行番号は f80 lowering 前基準。 別経路の同型は行 348058 以降。 `%12` は `load x86_fp80, x86_fp80* %11`、`%11 = bitcast ptr %rcx to x86_fp80*` と記録されているが、IR 抜粋は未確認。
- **推定原因 (推定)**: `%11` のポインタ型が f80 と推定されたのは lift 側 (RetDec の型推定) の誤りの可能性が高い。 整数スロットを f80 として読んでいるなら、`bitcast` 以前に型が違う。 `p0c/f80_lower.py` の通常モード (`token_lower`) は `x86_fp80`→`double` の型名置換と f80 定数・intrinsic 名の変換を行うが、`bitcast` 命令を書き換える規則を持たない。 そのため `bitcast x86_fp80 to i80` が `bitcast double to i80` になり、i80 を含む規則が無いまま残る。 これは `f80_lower.py` のコードを読んだうえの推定で、実行による確認はしていない。
- **対処方針 (未実施)**: (a) lift 側の型修復で `%11` の load を `i64` に差し替える (先に試す)。 (b) `f80_lower.py` に i80 ビット列の規則を足す (共有鎖のため T0/T1 退行確認が必要)。
- **残りの類型 (転記・未再現)**: 同 IR で `do not know how to soften fp_extend` と `no libcall available for fp_round with type f80` が出る (`f80_lower` 無し時と記録)。 E7 を消しても f80 の libcall が残るため、19165 が `emcc -c` rc 0 になるには E7 の修正に加えて f80 の扱いを決める必要がある。

## 15. #523 E7 の engine-local 修復の試行 (2026-10-13 · 実測 · 負の結果)

- **HEAD**: `80c32a06` (origin/main 起点の作業ブランチ。 測定コードは共有鎖を含めて未変更)。
- **再現 (lift + emcc, `ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges <78 件>" ENGINE_TAG=_noipp_nobad engine_lift.sh 19165 900`)**: summary `19165,2000,0,2608,6,241,139,0,139,612,2,445,0,608,2606`。 lift rc 0 / define 2,608 / f80 6 / `emcc -c` rc **139** (segfault) / wall 10 分 28 秒 / load 1.15 (5 分平均 0.99)。 §13 の 2 回目 (6 分 42 秒) と一致し、E7 の `invalid cast` は既定の経路では出ない (segfault が先に出る)。
- **試行 (engine-local)**: `e.final.ll` の x87 `load x86_fp80` (26 箇所) を `load i80` + `bitcast i80 to x86_fp80` に置換して `emcc -c` を再実行した。 結果は **rc 139 (segfault)** のまま。 IR 構文は有効になり、`do not know how to soften fp_extend` / `no libcall available for sint_to_fp with type f80` が出た。 置換は 7 秒で終わる再実行で、lift の再実行は不要。
- **判断**: segfault は `load` の型だけでは消えない。 §14 の推定 (E7 = 型誤り) は、少なくとも単独では成立しなかった。 残る経路は (a) f80 の libcall 不足 (`fp_extend` / `sint_to_fp` / `fp_round`) の共有鎖での扱い、(b) `function_1800ceec0` の DAG combine の segfault。 いずれも共有鎖 (`p0c/f80_lower.py` / lift) の変更になり、T0/T1 の退行確認 (#523 受入条件 2) が必要。 engine-local の試行は本節で打ち切り、修正コードは commit しない。

## 16. #523 segfault の切り分け (2026-10-13 · 実測 · 診断のみ · コード変更なし)

- **HEAD**: `13bdc5fe` (origin/main)。 測定入力は §15 と同じ `80c32a06` 系の engine lift 出力 (lift 側の差分 0。 `git diff 512c53ab origin/main -- tools/plugins/reverb_delay tools/lift tools/p0c` は空)。
- **再現 (19165, IPPCODE 除外 + AVX 系 78 除外)**: summary `19165,2000,0,2608,6,148,139,0,139,601,...`。 lift rc 0 / define 2,608 / f80 6 / `emcc -c` **rc 139**。 §15 と define・f80・rc が一致。 unimpl helper は 148 (§15 の 241 とは不一致。 未切り分け)。 601 は lift 段の秒数 (`engine_lift.sh` の `t1-t0`)。
- **スタック上限は原因でない**: `ulimit -s unlimited` でも rc 139。 クラッシュは `WebAssembly Instruction Selection` 中の `DAGCombiner::visitSTORE` (LLVM の DAG combine)。
- **落ちる関数は 2 つ**: 関数単位でスタブ化 (`unreachable` 置換・診断専用・コミットせず) して `emcc -c` を再実行したところ、`function_1800ceec0` (f80 参照 859 箇所) を外すと次は `function_1801439a0` (f80 参照 879 箇所) で落ち、両方を外すと segfault は消えた (rc 1)。 いずれも x87 を大量に含む。
- **両スタブ外し後の残り (ferror-limit=0)**: `emcc -c` rc 1 / error 296 件。 内訳は `no libcall available for fmul with type f80` 134、`fadd` 116、`do not know how to soften fp_extend` 22、`fp_round` 19、`sint_to_fp` 4、`frem` 1。 segfault 以外の未解決はすべて f80 の libcall 不足。
- **判断**: 19165 の `emcc -c` rc 0 の前提は「f80 の扱い」の 1 点に集約される。 f80 を f64 に下げる (`PLUG_F80_LOWER=1`) と segfault は消えた (§13 で 19165 rc 1 = E7)。 一方で E7 の型誤り推定は §15 で単独では成立しなかった。 次の判断は PM 側で、(a) f80 を持つ関数の扱い (精度を落とす lowering か、関数単位の除外か)、(b) x87 を含む 2 関数の DAG combine 回避 (LLVM 側・wasm backend の回避策) のどちらを取るか。
- **注意**: スタブ版の wasm は生成していない (関数を消すため miscompile)。 本節の数値は到達性の診断であり、engine の正しさは示さない。

## 17. #523 f80 関数の関数単位除外による部分集合の `emcc -c` (2026-10-15 · 実測 · 到達性のみ)

- **測定 commit**: `83e92e2c1` (`engine_f80_stub.py` / `engine_f80_subset.sh` を追加した commit。 gate はこの commit で実行)。 19165 の lift 出力は `42357b73e` で生成し、そのまま再利用。 19000 は `83e92e2c1` で lift からやり直した。 `git diff 42357b73e 83e92e2c1 -- tools/lift tools/p0c tools/plugins/reverb_delay/engine_lift.sh` は空 (lift 鎖は未変更)。
- **方法**: `engine_f80_stub.py` が `e.fixcmp.ll` の `x86_fp80` を含む関数の定義を `declare` に置換する (本体は捨てる。 除外は関数単位で、 名前・VA・理由を `f80_excluded.tsv` に記録)。 `engine_f80_subset.sh` が部分集合を `emcc -c` し、gate を判定する。 gate: rc 0 かつ define 数が除外数だけ減る (除外が f80 関数以外に及んでいないことの確認)。 NC は同じ入力の無改変 `emcc -c` rc (`engine_lift.sh` の summary 第 9 列)。

| engine | 条件 | lift rc | define | f80 関数 (除外) | NC: 無改変 `emcc -c` | 部分集合 `emcc -c` | gate |
|---|---|--:|--:|--:|--:|--:|---|
| 19000 Delay 3 | 全 3,632 関数 (IPPCODE 対象外) | 0 | 4,107 | 1 | 1 | **0** | PASS (define 4,106 = 4,107 − 1) |
| 19165 Multiband Delay | IPPCODE 除外 + AVX 系 78 除外 | 0 | 2,608 | 6 | 139 (segfault) | **0** | PASS (define 2,602 = 2,608 − 6) |

- 除外 VA: 19000 は `0x1800bcb00` の 1 本。 19165 は `0x18006fea0` / `0x1800ceec0` / `0x1801434a0` / `0x1801439a0` / `0x1801dbbe0` / `0x1801e12fc` の 6 本。 19165 の segfault の 2 関数 (§16) はいずれも除外集合に含まれる。
- 部分集合に残る `x86_fp80` は `__frontend_reg_load.fpr` / `__frontend_reg_store.fpr` の宣言 2 行のみで、呼出は 0 件。 定義本体に f80 は残らない。
- 実測時間: 19000 lift 108 s (`83e92e2c1`、再実行。 前回 `42357b73e` は 107 s)。 19165 lift 386 s (wall 6 分 36 秒、`42357b73e`)。 部分集合の `emcc -c` は 19000 が 2 s、19165 が 6 s (python 込み)。 load は未測定。
- **注意**: 除外した関数は外部宣言になるため、部分集合の挙動は元の engine と無関係。 正しさ・精度・f80 の扱いは未検証 (到達性のみ)。 19000 の既存 `PLUG_F80_LOWER=1` (精度低下あり) とは別経路。
- **再現手順**: `bash tools/plugins/reverb_delay/engine_lift.sh 19000 800` → `bash tools/plugins/reverb_delay/engine_f80_subset.sh 19000`。 19165 は `python3 tools/plugins/reverb_delay/avx_bad_ranges.py 19165` の出力 (絶対パス) を `--exclude-ranges` に渡し、`ENGINE_RANGE_ARGS="--exclude IPPCODE --exclude-ranges <絶対パス>" ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_lift.sh 19165 900` → `ENGINE_TAG=_noipp_nobad bash tools/plugins/reverb_delay/engine_f80_subset.sh 19165`。 `emcc` が PATH に無いときは `EMSDK_ENV` に `[EMSDK]` (`docs/REFERENCES.md`) の `emsdk_env.sh` を指定する。

### 受入条件への対応 (#523・本節)

1. **部分集合で達成** (19000: 4,106 / 4,107 define、19165: 2,602 / 2,608 define、除外理由とともに記録。 gate と NC 付き)。 全件 (f80 関数 7 本を含む) の達成ではない。 残り (f80 関数の lift) は #3447 ([PLG-F4-5])。
2. 共有鎖 (`lift/` `p0c/`) を変えていないため、本 PR では T0/T1 の退行確認は要らない。 共有鎖を変える場合は #3447 で実施する。
3. IPPCODE の扱い: #3445 ([PLG-F4-3])。
4. LoadLibrary 結合解析: #3446 ([PLG-F4-4])。
