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

## E. [PLG-F3-15] #1778: 19252 の残 helper `__asm_vmovsd(i64,i128)` (store 形) の宛先の原因

- 測定 commit: **f9c89955** (origin/main)。 `engine_lift.sh 19252` を単独実行 (`timeout 900`、foreground)。 load average (1 分) 0.08 (実行前後とも低負荷)。
- 結果 (`summary.csv`): `19252,522,0,551,0,5,0,0,0,17,0,0,0,29,549` (lift_rc 0 / define 551 / f80 0 / unimpl 5 / emcc_c_rc 0 / lift 17 s)。 `emcc -c` は fixcmp の前後とも rc 0。
- `e.simd.log` の残件 5 行: `__asm_movntps(i128,i128)`・`__asm_vcomisd(i128,i64)`・`__asm_vmovsd(i64,i128)`・`__asm_vucomisd(i128,i64)`・`__asm_vucomiss(i128,i128)`。 `vmovsd` store は受入条件の対象のまま未達。

### E-1. 原因 (実測)

- `e.final.ll` の `__asm_vmovsd(i64 %10, i128 %7)` 等 3 箇所 (`function_180019c20`) の宛先 `%8`・`%9`・`%10` は、`e.drc.ll` (RetDec の直後) では `load i64, i64* %1`。 `%1` は `alloca i64` で、**関数内に一度も store されない** (`store` で `%1` を書く行は 0 件)。
- `e.lift.ll` 以降では同じ行が `xor i64 0, 0` になる。 これは RetDec ではなく、**自前の B1 (`tools/plugins/lift/passes/ir5_patch.py` の `patch_uninit_alloca`)**。 B1 は「store の無い alloca からの load を 0 に置換する」規則で、`e.ir5.json` の `b1_fixed` は 579 件。
- 元の機械語は `0x18001a861: vmovsd qword ptr [rsp + 0x20], xmm0` (`0x18001a867` は `[rsp+0x30]`)。 これは**スタック上の spill** で、直後の `0x18001a86d: mov rdx, qword ptr [rsp + 0x20]` で読み戻される。 宛先は定数 0 ではない。
- つまり issue の「上流 (RetDec の定数畳み込み) で定数 0 になる」は不正確。 RetDec は rsp 相対の spill 領域を、store の無い `alloca` (`%1`) に写している。 その後 B1 が 0 に埋めている。 2 段の組合せで宛先が 0 になる。
- **同じ `%8`・`%9`・`%10` は store 先だけでなく分岐・演算にも使われる** (`and i64 %10`・`switch i64 %10`・`urem i64 %10`・`icmp eq i64 %10, -9223372036854775808` 等)。 そのため `vmovsd` 復元だけでは直らず、spill 読み戻しの値が 0 になることで、この関数の分岐が無音で誤る可能性がある。 `emcc -c` が通っても正しさは保証されない (到達性のみの指標)。

### E-2. 採らなかった方式

- (a) `lower_asm_store` / `m11_simd2.py` で `vmovsd` を store 化する: 宛先が 0 のままなので address 0 への誤った store になる (issue の記述どおり)。 不採用。
- (b) B1 の 0 埋めを止める: 共有 lift 鎖 (全 plugin の lift) の挙動が変わるため、本 issue の範囲を超える。 不採用 (影響範囲の測定が要る)。
- (c) `vmovsd` を no-op や `abort` に委譲して unimpl から消す: 宛先を失ったまま stub を消すと silent miscompile が検出できなくなる (DECISIONS D15 と同じ理由)。 不採用。

### E-3. 起票

- 修正先は RetDec の spill 領域の写像 + B1 の 0 埋めの組合せ。 復元 (spill slot を store として戻す) は共有 lift 鎖の変更を伴うため、子 issue **#2017 ([PLG-F3-18])** として起票した。
- 本 PR では、残件 (`vmovsd` store) を子へ移し、原因の特定と方式の記録までを完了とする。

### D-2. 検証

- 測定 summary (`work/dynamics/engine<B>/summary.csv`) は `work/` (gitignore 対象) にあり commit しない。
- コード差分 (§D の「出力は 0 行」の根拠・`docs/WORKFLOW.md` §6): `git diff 30a7b5b4 HEAD -- tools/plugins/lift tools/plugins/dynamics ':!*.md' | wc -l` → **0**。 `:!*.md` を外した形は文書 (`REPORT.md`・`REPORT_APPENDIX.md`) の差分だけが出る (`git diff --stat 30a7b5b4 HEAD -- tools/plugins/lift tools/plugins/dynamics` の対象は この 2 件のみ)。 測定 commit `30a7b5b4` は HEAD の祖先。

## F. [PLG-F3-18] #2017: vmovsd store 宛先の経路 (実測・HEAD c171b9dc)

- 測定 HEAD: **c171b9dc** (origin/main)。 `timeout 1000 bash tools/plugins/dynamics/engine_lift.sh 19252 900` を foreground で単独実行。 load average (1 分) 0.99 (実行時)。
- 結果 (`summary.csv`) と残件は §E の結果を参照 (測定値の正本は §E)。 本節の HEAD では §E と同一の値を得た。

### F-1. 経路 (IR と機械語の照合)

- 注: 本節の `fn.drc.ll` の store 先と `e.lift.ll` の `xor i64 0, 0` の件数 (322 件) は `work/` の成果物からの観察で、本 PR には添付していない。 数値の確定は子 #2047 の REPORT で実測値として行う。
- `function_180019c20` の `%1 = alloca i64` からの load は 3 件 (`%8`・`%9`・`%10`、いずれも entry block)。 **この関数内で `%1` への store は 0 件**。
- 機械語の spill 書込は `0x180019c50` (`[rsp+0x20]`・`[rsp+0x30]`) と `0x18001a861` (`vmovsd [rsp+0x20], xmm0`・`[rsp+0x30], xmm1`)。 RetDec の IR には、これらに対応する `store` が無い (`fn.drc.ll` の store 先は `%stack_var_*.reg2mem` と `%rax.0.reg2mem` 等のみ)。
- したがって `%8`・`%9`・`%10` は、RetDec が rsp 相対の spill 領域を **1 本の未 store `alloca i64`** に併合した結果。 併合の位置は RetDec 側 (`e.drc.ll`) で既にそうなっている。
- B1 (`ir5_patch.py` `patch_uninit_alloca`) はこの 3 load を `xor i64 0, 0` にする。 `e.lift.ll` 全体では `xor i64 0, 0` が **322 件** (B1 の対象は関数横断。 この 322 件の内訳は未測定)。

### F-2. store 形 `__asm_vmovsd` が復元されない理由 (実測)

- `fix_asm_stores.py` の `PAT` は `movlps|movlpd|movhps|movhpd|movsd|movq` だけを対象にし、**`vmovsd` を含まない**。 そのため `__asm_vmovsd(i64, i128)` (store 形) は store に変換されず `unimplemented` に残る。
- ただし `vmovsd` を PAT に足すだけでは不十分: 宛先 (`%8`・`%9`・`%10`) は B1 で既に 0 のため、store は address 0 へ書く誤りになる (E-2 (a) と同じ)。 宛先の復元が前提。

### F-3. 方式の候補 (未実装・次の子で選ぶ)

- 候補 A: B1 の 0 埋めを「その alloca が spill 領域の併合であるとき」に限る。 判定条件は RetDec の `%1` の使用箇所 (store 先 = `vmovsd` の宛先と一致させる) で決める。 共有 lift 鎖を変えるため、全 plugin の lift の差分測定が要る (E-2 (b) の懸念)。
- 候補 B: RetDec 出力の spill 併合 (`%1`) を、機械語の rsp オフセット (`0x20`・`0x30`) ごとの slot に分けて store / load を復元する pass を追加する。 対象は `function_180019c20` 系の rsp 併合に限り、B1 の挙動は変えない。 方式選定は子 issue で行う。

### F-4. 判定 (本 run)

- 受入条件のうち「`vmovsd` store が unimpl から消える」「B1 の方式を選び、共有鎖への影響を測定する」は**未達**。 本 run では実装しない (共有鎖の測定が 1 run に収まらない)。
- 受入条件 4 (19252 の `function_180019c20` の分岐が spill 読み戻し値と一致) は、F-1 の経路が確定した時点で確認できる。 その確認は子 issue に含める。
