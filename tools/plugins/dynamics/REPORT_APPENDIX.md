> **正本**: `tools/plugins/dynamics/REPORT.md`。本書は REPORT の付録 (250 行上限のため分割移動。内容は無変更)。

# tools/plugins/dynamics/REPORT_APPENDIX.md — #1412 脱落の原因 (付録)

## A. `.pdata` define 脱落の原因 (#1412)

REPORT §4 の「脱落の原因」の全文。 本付録は本体から分割移動した。

- 既定の RetDec 呼出し (`--disable-static-code-detection` 無し) が、定数 libc 系の関数を
  「statically linked function」として除去する (`e.retdec.log` の `Running phase: removing functions from standard libraries`)。
  19048 の欠落 210 件のうち **208 件** は dsm の `statically linked function` 行の開始 VA と一致 (`e.drc.dsm`)。 残る 2 件は
  `CreateEngine` (0x18000b1a0) / `entry_point` (0x18000bb98) で、RetDec は名前付きの `function:` として出力しており、
  `define @CreateEngine` / `define @entry_point` は final.ll に存在する。 `engine_defs.py` は `function_<VA>` 形式しか見ないため、この 2 件は偽陽性。
- ネガティブ/切替の実測: `PLUG_NO_STATIC_DETECT=1 bash tools/plugins/dynamics/engine_lift.sh 19048` で `missing_define` 210 → **2** (97 B)、`missing_ref` 67 → **0**、`define` 1,504 → 1,712。
- 残りの 2 件 (19252 の 165 B / 19048 の 97 B) は、いずれも dsm で `function: <名前> at <VA>` として出る `CreateEngine` / `entry_point` で、`final.ll` に `define @CreateEngine` / `define @entry_point` が存在する。 `engine_defs.py` の偽陽性だったため、本 run で名前付き define を計上するように修正した (commit db4fe1f0)。 これで両 engine の実在の欠落は 0 件。
- 既定値 (`lift_ranges.sh` の `PLUG_NO_STATIC_DETECT:-1`) は commit 0d51d876 (#1536) で切替済み。 本 run は既定のまま測定した。
- `engine_fixcmp.py` の `%penv` 修正は commit 5457975c (#1163) で入っており、切替後の 19048 は fixcmp 後 `emcc -c` rc 0。 raw の `final.ll` は `%arg2` i32/i64 の型不整合で rc 1 のまま (既存の修正対象。 `engine_fixcmp.py` で吸収)。

## B. fixcmp の call 引数拡張による 19048 の `emcc -c` 解消 (#1163 run)

- 原因: `engine_fixcmp.py` は `icmp ptr` の被演算子しか扱わず、`call` の `ptr` 引数に i64 仮引数を渡す箇所 (`call i1 @FreeEnvironmentStringsW(ptr %penv)`、`%penv` は i64) が残っていた。 `emcc -c` は最初の型エラーで止まる。
- 修正: `engine_fixcmp.py` に、`call` の `ptr` 引数で i64 値の箇所へ `inttoptr` を挿入する処理を追加 (engine 局所。共有 lift 鎖には入れない)。
- 測定 (`engine_lift.sh` 単独実行、HEAD = 本 PR の commit):

| engine | unimpl | emcc_c_rc (final.ll) | fixcmp patched | emcc_c_rc_after_fixcmp | missing_define | lift 秒 |
|---|--:|--:|--:|--:|--:|--:|
| 19252 Transient | 5 | 0 | 0 | 0 | 2 | 16 |
| 19048 Multiband | 5 | 1 | 2 | 0 | 97 B / 2 件 | 63 |

- 変更前 (main) の 19048 は `emcc_c_rc_after_fixcmp` = 1 (`%penv` の型)。 変更後は 0。
- 生成 helper C (`tools/plugins/work/dynamics/simdchk<B>/m11_simd.c`、`msimd11_core.h` を親 dir に置いて `emcc -c`): 19252 rc 0 / 19048 rc 0。
- 未実装 helper の残件は両 engine とも 5 件 (`movntps`・`vmovsd` store・`vcomisd`・`vucomisd`・`vucomiss`。19048 は `vcomisd__22` を含む)。 #1408 の範囲。
- 共有鎖 (`lift/passes/`・`lift_ranges.sh`) への影響なし (本変更は `dynamics/engine_fixcmp.py` のみ)。

## C. 旧測定 (REPORT §4 から分割移動)

- 測定 commit `c0afd85b` (本 HEAD、`engine_lift.sh` 単独実行、19252 23 s / 19048 61 s)。 `engine_lift.sh` の出力: 19252 `unimpl 12 / emcc_c_rc 0 / missing_define 2`、19048 `unimpl 6 / emcc_c_rc 1 → fixcmp 後 0 / missing_define 210`。 `711d9ece` の値と一致 (表は変更なし)。
- 生成 helper C (`*_simd.c`) の `emcc -c`: 本 HEAD の `m11_simd2.py` で `tools/plugins/work/dynamics/simdchk<B>/m11_simd.c` を生成 (入力 `work/dynamics/engine<B>/e.final.ll`、`python3 lift/passes/m11_simd2.py <final.ll> > m11_simd.c`)。 `#include "../msimd11_core.h"` を `"msimd11_core.h"` に書換えて `emcc -c -msimd128 -w -O0 m11_simd.c -o o.o`。 結果: 19252 rc 0、19048 rc 0。 両 engine とも `__asm_int3` の宣言は `declare i64 @__asm_int3()` (戻り値あり版) のため、int3 の `void` 版の経路は通らない。
- 測定 commit `711d9ece` 以降のコード差分: `git diff 711d9ece HEAD -- tools/plugins/lift/passes/m11_simd2.py` は int3 の 1 行のみ (`f2bbad10`)。 `hs_callee_disasm.py` は `engine_lift.sh` の実行経路外 (reviewer 確認)。 この差分を含む `c0afd85b` で再測定し、表の値は一致した。
- int3 の影響: 両 engine の `e.final.ll` の `__asm_int3` は `i64` 戻り値の宣言 (1 件ずつ) のため、旧 void 版の `return 0;` 問題には当たらない。 `void` 版の修正そのものは合成 `.ll` のみで確認 (下記)。
- int3 修正 (`m11_simd2.py`・本 HEAD): `void` 版は `abort()` のみ、戻り値あり版は `abort(); return 0;` を生成する。 `int3` を含む合成 `.ll` (`declare void @__asm_int3()` と `declare i32 @__asm_int3__1()`) で生成した C を `clang -c -Wall -Werror=return-type` で検査: 修正後 rc 0、修正前 (`f50ca8ad`) は `void function '__asm_int3' should not return a value` で rc 1。 engine 出力での確認は、上の「生成 helper C」の `emcc -c` rc 0 (両 engine、`c0afd85b`) で行った。 合成 `.ll` の検査は `void` 版の分岐を直接見るためのもの。
- 以上は到達性の実測で、engine の正しさは何も示していない。

## D. #1698: lift_ranges.sh 既定化 (PLUG_NO_STATIC_DETECT=1) の batch 系への影響 (engine_lift 経由)

- 測定 commit: **30a7b5b4** (ws-1698 の起点 = origin/main。本 run はコードを変更していない)。
  `git diff 30a7b5b4 HEAD -- tools/plugins/lift tools/plugins/dynamics` の出力は 0 行 (下の検証節を参照)。
- 環境: fl-win64 (`$RUNNER_TEMP/fl-win64`)・toolchain-retdec (RetDec v5.0)・toolchain-emsdk (emcc 6.0.12)。 `engine_lift.sh <block>` の出力 summary.csv を比較。
- 実行: `bash dynamics/engine_lift.sh <block> <timeout>` (既定) と `PLUG_NO_STATIC_DETECT=0 bash dynamics/engine_lift.sh <block> <timeout>` (従来)。
  load は各回の開始時 0.45〜0.91 (1 分平均)。 4 vCPU。

| block | 条件 | lift_rc | defines | unimpl | emcc_c_rc | fixcmp | after_fixcmp | lift_s | missing_define | missing_bytes | missing_ref | function_defines |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 19048 | 既定 (1) | 0 | 1712 | 5 | 1 | 2 | 0 | 63 | **0** | **0** | **0** | 1710 |
| 19048 | 既定 (1)・再実行 | 0 | 1712 | 5 | 1 | 2 | 0 | 63 | 0 | 0 | 0 | 1710 |
| 19048 | 従来 (0) | 0 | 1504 | 1 | 1 | 1 | 0 | 61 | **208** | **22819** | **67** | 1502 |
| 19252 | 既定 (1) | 0 | 551 | 5 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 549 |
| 19252 | 従来 (0) | 0 | 551 | 5 | 0 | 0 | 0 | 16 | 0 | 0 | 0 | 549 |

- 19048 (Multiband Compressor comp_eng): 既定化で `missing_define` 208→0・`missing_bytes` 22819→0・`missing_ref` 67→0、`defines` 1504→1712。 既定の再実行で同一値を再現。 `emcc_c_rc_after_fixcmp` は両条件 0。
- 19048 の差は、既定で 208 件の「statically linked function」が define されることによる (§A と一致)。 `unimpl` (5 vs 1) と `fixcmp` (2 vs 1) も変わったが、原因は未調査 (下の未解決表)。
- 19252 (Transient Processor engine): 既定と従来で summary が完全一致。 既定化の影響なし。
- 判断 (暫定): engine 2 本では既定化を悪化させる欠落は出なかった (19048 は欠落 0、19252 は不変)。 `unimpl` 増加 (19048 の 1→5) の原因が確定するまで、既定化は暫定で維持する。
- 未実施: `batch_lift.sh` 本体は、素材に無い inventory 成果物 (`work/win_pe_scan.json`・`nsis_blockmap.json`・`winfuncs/`・`block_manifest.json`) を要するため実行できなかった。
  また `synth/cpp_lift.sh` の 7 本 (従来 (0) の再測定) も本 run では流していない。 `batch_lift.sh` 系の summary 比較は起票先の残件とする。

### D-1. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 19048 の `unimpl` 1→5・`fixcmp` 1→2 の原因 (既定化で増えた define 由来か) | 既定化で未実装 helper が増える。 到達性のみの指標で正しさは未確認 | PM 判断 (切り分けは次の lift 検証 run。本 PR では子 issue を起票しない) |
| `batch_lift.sh` 本体の既定/従来比較 | `batch_lift.sh` 経由の summary.csv は未測定 (inventory 成果物 `win_pe_scan.json`・`nsis_blockmap.json`・`winfuncs/`・`block_manifest.json` が素材に無い) | PM 判断 (素材の追加要否。許可名に該当する素材が無いため、本 PR では起票しない) |

### D-2. 検証

- 測定 summary (`work/dynamics/engine<B>/summary.csv`) は `work/` (gitignore 対象) にあり commit しない。
- コード差分 (§D の「出力は 0 行」の根拠・`docs/WORKFLOW.md` §6): `git diff 30a7b5b4 HEAD -- tools/plugins/lift tools/plugins/dynamics ':!*.md' | wc -l` → **0**。 `:!*.md` を外した形は文書 (`REPORT.md`・`REPORT_APPENDIX.md`) の差分だけが出る (`git diff --stat 30a7b5b4 HEAD -- tools/plugins/lift tools/plugins/dynamics` の対象は この 2 件のみ)。 測定 commit `30a7b5b4` は HEAD の祖先。
