# Kilohearts REPORT 付録 (分割移動)

> 本付録は `tools/targets/kilohearts/REPORT.md` §10-7b・§10-7c の全文を、250 行上限のため分割移動したもの。内容は削除していない。

### 10-7b・10-7c (#556 2 回目・3 回目 run)

#### 10-7b. #556 2 回目 run (Resonator の emcc 再現・callee 追加 decompile)
- 素材: `plugins-kilohearts` の Windows Installer zip のみ展開 (`extract_installer.sh` は dmg を必須とするため HeartCore 抽出を手で再現)。Ghidra 12.1.4 は GitHub release から再取得 (sha256 一致)。`pefile`・`capstone` は pip 導入。
- Resonator 7 関数 (修復なし) → `ghidra_to_c.py` → emcc: **失敗を再現** (`resonator.c` 21 件)。内訳: 128bit レーン `_8_8_`/`_4_12_`/`_0_8_` (V128 未定義)、`ushort` 型未定義、`rcpps` 未実装、`func_0x…` 形式の未解決 callee。
- callee 5 関数 (`0x180fd62dc` `0x180fd6320` `0x180fb6ce0` `0x180fd648c` `0x180fbdef4`) を追加 decompile: 計 12 件 OK。ただし Ghidra 出力の `func_0x…` は未関数化アドレスのため、emcc の未解決は残る。
- shim に `ushort` を追加 (機械的な型定義のみ)。128bit レーンと `rcpps` は未対応。
- 突合・ablation・ネガコンは未実施。Stereo / Delay は未着手。

#### 10-7c. #556 3 回目 run (callee 6 関数を converter の `also` に追加 = also 計 12 件)
- 素材: `plugins-kilohearts` の Windows Installer zip → payload.dat → windows.zip → HeartCore.core_64 を手で展開 (dmg 不要)。Ghidra 12.1.4 = GitHub release, sha256 `ddac49f9…d2db` 一致。emsdk 6.0.12 は [EMSDK] で動作。
- Ghidra 再 decompile: 13 関数 (Resonator + callee 12) すべて OK。import 込み 17.8 s (n=1)。
- `ghidra_to_c.py` の `resonator.also` は既存 6 件 (`0x180fbc1f4` `0x180fbbfb8` `0x180fbdfcc` `0x180fbe018` `0x180fcf904` `0x180fd54cc`) に、本 PR で 6 件 (`0x180fd62dc` `0x180fd6320` `0x180fb6ce0` `0x180fd648c` `0x180fbdef4` `0x180fe5dfc`) を追加し、計 12 件 (commit 本 PR)。emcc は **依然失敗** (`-ferror-limit` 20 件で打ち切り)。
- 件数の注意: 10-7b の記録は `resonator.c` 21 件、本 run は 20 件で打ち切りのため、件数は同一基準の比較ではない。件数の増減は退行ではなく、callee を足したことで未解決 callee が見えた切り分けの進展と解釈するが、前 run と同一基準での再計測は未実施。
- 起票先: Resonator の emcc 残件 → #1215 [KH-23] / Stereo・Delay の実ビルド・突合 → #1216 [KH-24]。
- 残る未解決 (emcc 出力): (a) V128 lane `_8_8_`/`_4_12_`/`_0_8_`、(b) `rcpps` 未実装 (`gen_simd.py` の `kh_rcp_exact` 系を移植すれば入る見込み。未検証)、(c) 引数なし呼出の `param_1` 不足、(d) 推移的な未関数化 callee `0x180fd6498`・`0x180fd662c`・`0x180fe5f40`・`0x180fd3144`、(e) `UNK_182280000` 未定義。
- 突合・ablation・ネガコンは本 run でも未実施。Stereo / Delay は未着手。

#### 10-7g. #1215 (KH-23) 再 run: 呼出名 `func_0x…` の統一 (部分・converter 1 箇所)
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → HeartCore.core_64 (手展開)。Ghidra 12.1.4 = zip (sha256 `ddac49f9…d2db` 一致)、JDK 21、emsdk 6.0.12 ([EMSDK])。
- 原因の特定: 10-7e の残件 `func_0x000180fd648c`・`6498`・`662c`・`bdfcc`・`bdef4`・`81e4`・`81ec` は、Ghidra が未命名 callee を `func_0x<va>` で呼ぶ名前であり、`also` で同じ va を `FUN_<va>` と定義していた。`ghidra_to_c.py` に呼出名の統一がなかったため未解決として残っていた (10-7e の「未確認」を解消)。`81e4`・`81ec` は IAT thunk (10-7f) で、`also` に入っていないため不一致のまま。
- 変更: `ghidra_to_c.py` に `func_0x000180f…` → `FUN_180f…` の書換えを 4 行追加 (定義済み va のみ)。
- decompile (`also` 17 + 4 件・同 HEAD 相当の集合): 20 関数すべて OK (summary.tsv, n=1, import 込み 36.4 s wall)。
- emcc (resonator, 修復なし, `-ferror-limit=0`): **31 → 25 件** (`grep -c error:`)。消えたもの: `func_0x…648c/6498/662c/bdfcc/bdef4` と `FUN_180fe5f40`・`FUN_180fd3144` 由来の呼出エラー。
- 残件 (emcc 25 件): `MXCSR` 8・`param_1` 不足 3 (引数なし呼出)・`FUN_180fd4f30` 2・`func_0x…81e4`/`81ec` 1 件ずつ (IAT thunk)・`GetLastError`/`SetLastError` 各 1・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1・`rcpps` 2 引数形 1・引数型不一致 3 (`undefined4[8]`→`short*`・`uint*`→`ushort*`・`float*`→`uint*`)・`too many arguments` 1・`V128` への int 代入 1。Resonator のビルドは**依然失敗**。
- 回帰確認 (同一 HEAD・同一 shim, `build_cmp.sh` の fix 全部): Gain 1000/1000 bit-exact (wasm 15,161 B, emcc 0.3 s)・Haas 1000/1000 (16,878 B, 0.3 s)・Gate 1000/1000 (17,367 B, 0.3 s)。wasm サイズは §10-3 と一致。
- 未実施: Resonator の native 突合 (emcc 未通過のため)。

#### 10-7h. #1216 (KH-24) 1 単位: Stereo の C 化と emcc 試行 (未達・突合未実施)
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → HeartCore.core_64 (手展開)。Ghidra 12.1.4 = GitHub release (sha256 `ddac49f9…d2db` 一致)、JDK 21。emsdk は `[EMSDK]` (6.0.12)。
- 変更 (`ghidra_route/ghidra_to_c.py` のみ): `SNAPINS` に `stereo` を追加 (proc `0x18080d4d0`、`also` = lift 値の残り 7 関数 `0x180fcd690` `0x180fce0d0` `0x180fdc470` `0x180fdc660` `0x180fdc700` `0x180fdfdb0` `0x180fdc6d8`)。
- decompile (`DecompEach.java`, 8 関数): 8 件すべて OK (summary.tsv, import 込み 35.5 s wall, n=1)。
- **再実測 (fix run, HEAD `b992fc57`・コード同一。素材 `plugins-kilohearts` → Installer zip → payload.dat → windows.zip → HeartCore.core_64 を手展開、Ghidra 12.1.4 (zip sha256 `ddac49f9…d2db` 一致)、JDK 21、emsdk 6.0.12 ([EMSDK]))**: decompile 8/8 OK (`analyzeHeadless` wall 33.3 s, n=1)。`ghidra_to_c.py stereo` 生成 rc 0 (`stereo.c`・`sigs.json`)。
- native 参照: `native_ref ... stereo 1000 7` で `vec_1000_7.bin` を生成 (0.21 s, n=1)。
- emcc (stereo, 修復なし, `-ferror-limit=0`, `emcc` 6.0.12): **失敗 (rc 1, wall 0.17 s, load 1.11 0.57 0.25)**。`grep -c 'error:' emcc.log` = **40**。内訳は clang 診断 39 行 (`file:line:col: error:`) + ドライバ行 1 行 (`emcc: error: '…clang…' failed (returned 1)`)。`build_cmp.sh` の既定 `-ferror-limit` では 20 件で打ち切り。
- 件数の内訳 (clang 診断 39 行・再実測の分類): 未宣言関数 11 (`ABS` 3・`SUB168` 2・`FUN_180fd8aac` 2・`ZEXT416`・`rsqrtps`・`maxps`・`vpsrldq_avx` 各 1)・`param_1` 引数不足 8・引数数不一致 2 (expected 2, have 1)・`undefined1[16]` へのメンバ参照 6・`V128` 同士の二項演算 6・`V128` への int 代入 3・`sbyte` 未知型 2・`undefined1[16]` 代入不可 1 (line 351)。合計 39 + ドライバ 1 = 40。
- 前回記録 (合計 38) との差: 分類から line 351 の代入不可 1 件が落ちていた。ドライバ行は件数に数えていた。前回の「40 件は未再現」は本再実測で再現した (40 行)。
- 行ごとの生ログは `tools/targets/kilohearts/work/gr/stereo/emcc.log` (gitignore 対象の `work/`)。
- 残件の意味 (未対応): (a) `rsqrtps` は §10-4 の census (Stereo 1 件) と一致。`maxps`・`vpsrldq_avx`・`ZEXT416`・`SUB168` は shim 未定義の SIMD 疑似関数だが、§10-4 の census に Stereo の記載は無く census 外の新出 (本 run の実測のみ)。(b) `FUN_180fd8aac` は未関数化 callee (Resonator の `func_0x…` 閉包と同じ種類)。(c) `param_1` 不足 8 は引数なし呼出で、§10-4 の ABI 復元と同じ類型 (census の Stereo 件数は無い)。
- 突合・ablation・ネガコン・第二 oracle: 未実施 (emcc 未通過のため)。
- 回帰: 本 run は `SNAPINS` にエントリを足しただけで、Gain / Haas / Gate の converter 経路は変えていない (`run_all.sh` は再実行せず、値は §10-3 を引用)。
- 起票: 残件は #1216 (KH-24) の範囲。新規起票は今 run では行っていない。

#### 10-7i. #1405 (KH-25) 1 単位: MXCSR を shim の状態変数に置換 (部分)
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → HeartCore.core_64 (手展開)。Ghidra 12.1.4 = GitHub release (zip sha256 `ddac49f9…d2db` 一致)、JDK 21 (Temurin)。emsdk 6.0.12 ([EMSDK])。
- 変更 (`ghidra_route/ghidra_shim.h` のみ、+3 行): `MXCSR` を `static uint MXCSR = 0x1F80` として定義。callee `180fd6498` (読み) と `180fd662c` (書き) の参照を対象とする。初期値 `0x1F80` は x86 の MXCSR 既定値 (全例外マスク・丸め最近接・FTZ/DAZ 無効)。wasm に制御レジスタが無いための代替で、その意味は突合で検証する。
- decompile (Resonator 集合 17 関数): 17 件 OK (summary.tsv)。
- emcc (resonator, 修復なし, `-ferror-limit=0`): **依然失敗**。clang 診断 22 件 → 14 件 (`MXCSR` 未宣言 8 件が消えた、22 − 8 = 14)。残件 (合計 14 件、列挙の和と照合済み): `param_1` 引数不足 3・未宣言 `FUN_180fd4f30` 2・引数数不一致 1・`rcpps` 1・`func_0x…81e4`/`81ec` 各 1 (IAT thunk)・`GetLastError`/`SetLastError` 各 1・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1・`V128` への int 代入 1。
- 回帰 (同一 shim・`build_cmp.sh` の fix 全部, `native_ref` 1000 trial / seed 7): Gain 1000/1000 bit-exact (wasm 15,161 B)・Haas 1000/1000 (16,878 B)・Gate 1000/1000 (17,367 B)。wasm サイズは §10-3 と一致。
- 計測基準の注: 「22」は本 run の clang 診断件数で、保存ログが無く再集計できない (`work/` なし・`plugins-kilohearts` 未取得)。10-7g の 25 件は `grep -c error:` による別基準・別 HEAD の数値で、22 と直接比較できない。10-7g の非 MXCSR 17 件と本 run の 14 件の差 (3) の原因は未確認。基準を揃えた再計測は未実施。
- 未実施: Resonator の native 突合・ablation・ネガコン (emcc 未通過のため)。Stereo / Delay は未着手。

#### 10-7j. #1215 (KH-23) 再 run: 残件の基準付き再計測と未関数化 callee 3 件の試行 (未達・コード変更は採用せず)
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → HeartCore.core_64 (手展開, dmg 不要)。Ghidra 12.1.4 = GitHub release `ghidra_12.1.4_PUBLIC_20260921.zip` (sha256 は本 run 未照合: zip を保持していないため照合不可。前 run の `ddac49f9…d2db` 一致記録は 10-7 節を参照)、JDK 21 (Temurin 21.0.12)、emsdk 6.0.12 ([EMSDK])。測定 HEAD = `7958f568` (コード = `tools/targets/kilohearts`・`tools/liftlib`・`tools/liftdiff` の REPORT_APPENDIX.md を除く差分は origin/main `3d21715b` と同一)。
- 現状 (HEAD 同一・修復なし・`ghidra_to_c.py resonator`・`emcc -c -ferror-limit=0`): **emcc error 14 件** (`grep -c 'error:'`, rc 1)。残件: `param_1` 引数不足 3・`FUN_180fd4f30` 未宣言 2・引数数不一致 1・`rcpps` 1・`func_0x…81e4`/`81ec` 各 1 (IAT thunk)・`GetLastError`/`SetLastError` 各 1・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1・`V128` への int 代入 1。10-7i の 14 件と一致 (MXCSR は shim 定義で消えている)。10-7g の 25 件は MXCSR を含む旧基準のため、残件の比較は本値を用いる。
- Ghidra decompile (Resonator 17 関数 + 未関数化 callee 3 件 `0x180fd4f30` `0x180fd51cc` `0x180fd2d38`): **20/20 OK** (`summary.tsv`, `analyzeHeadless` wall 19.4 s, n=1)。
- 試行: 上記 3 件を `also` に追加した場合、emcc error は **14 → 26 件に悪化**。内訳は確定分 17 件のみ: `puStack_28` 3・`ppuStack_10` 2・`undefined` 2・`DAT_184162358` 1・`HeapAlloc`/`HeapFree` 各 1 (計 2)・`GetLastError` 2・`func_0x000180fe5c6c`・`func_0x000180fb6c0c`・`FUN_180fd2c90`・`FUN_180fd2c10`・`FUN_180fd1ac4` 各 1 (いずれも未関数化・計 5)。**残り 9 件は未分類** (保存ログが無く再集計できない)。追加 3 callee (`FUN_180fd4f30` 2・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1) の未宣言エラーが消えたかは未確認 (ログ無し・再実行不可)。この変更は採用せず、`ghidra_to_c.py` は HEAD のまま (`git status` に変更なし)。
- 結論: 残件の閉包は 3 callee の追加では閉じない。`also` を広げる方向は、閉包を全件確定させる (decompile 集合の固定) まで退行する。次の一手は Win API (`HeapAlloc`/`HeapFree`/`GetLastError`/`SetLastError`) の stub 規則と、未関数化 callee の閉包を一括で確定する仕組みを先に決めること。
- 未実施: `rcpps` 2 引数形 (`gen_simd.py` の 1 引数形のみ対応・ABI 未確定)・引数なし呼出の `param_1` ABI 推定・Resonator の native 突合・ablation・ネガコン。Stereo / Delay は未着手。

#### 10-7o. #1405 (KH-25) 1 単位: rcpps 代入形の固定と converter ガード (部分・Resonator は emcc 未通過)
- 素材: `plugins-kilohearts` (Installer zip) → payload.dat → windows.zip (`1ccb1df8…`) → `HeartCore.core_64` を手展開。Ghidra 12.1.4 = GitHub release `ghidra_12.1.4_PUBLIC_20260921.zip` (sha256 `ddac49f9…d2db` 一致)、JDK 21 (Temurin 21)、emsdk 6.0.12 (`git clone` + `emsdk install 6.0.12`, `emcc 6.0.12`)。
- **測定 commit**: `1ecf9bb3` (`ghidra_route/ghidra_to_c.py` にガードを入れた最後の commit)。`git diff 1ecf9bb3 HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` は 0 行 (本節の数値はこの commit で実測)。
- 変更 (diff 実態。`git diff 5bbfa3d2 1ecf9bb3 -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` で確認):
  1. `ghidra_to_c.py`: `RCPPS_HELPER` の入力読み出しを `*(uint32_t*)` から `memcpy` に変更 (strict aliasing で `-O2` が誤値を返すため)。helper は `V128 rcpps(undefined1 dst[16], V128 src)` で、戻り値を返す。dst は使わない。
  2. `ghidra_to_c.py`: `rcpps(` を含む行が `^\s*\w+ = rcpps\(\w+,\s*\w+\);\s*$` に合わない場合 (戻り値を捨てる形) は `SystemExit` で停止するガードを追加 (commit `1ecf9bb3`)。
  3. `ghidra_shim.h`: `GetLastError`/`SetLastError` を追加 (**常に 0 を返す stub**・`SetLastError` は無視。native harness `scen_khmath`/`scen_khmaster` と同じ扱い。状態変数 `g_last_error` は使っていない)。
  4. `snapins/scripts/rcpps_helper_check.c`: 戻り値 `rcpps(NULL, s)` を `_mm_rcp_ps` と突合する形に書き直し。
- **rcpps の実源・代入先 (decompile 実測)**: `plugins-kilohearts` の `HeartCore.core_64` から `DecompEach.java` で Resonator の 17 関数を decompile → 17/17 OK (`summary.tsv`, `analyzeHeadless` wall 32 s)。`rcpps(` を含む行は **1 件** (`180743390.c:63`):
  ```c
  auVar26._8_8_ = 0;
  auVar30 = rcpps(in_XMM2,auVar26);
  fVar18 = auVar30._0_4_;
  ```
  - 逆アセンブル (`objdump -M intel`, `0x180743419`): `rcpps xmm2,xmm1` → `mulps xmm1,xmm2`。
  - 引数: 第 1 引数 `in_XMM2` は未使用の旧 dst、**源は第 2 引数 `auVar26`**。結果の代入先は `auVar30` (後続で読まれる)。
  - 関数: `0x180743390` (`FUN_180743390`) の内部。harness 記録の `0x180743419` と一致。
- **代入形の件数 (本測定)**: Resonator 17 関数の `rcpps(` 行 = **1 件**、うち代入形 `X = rcpps(D, S);` = 1 件、非代入形 = 0 件。ガードは代入形 1 件を通し、非代入形の probe (`rcpps(in_XMM2,auVar26);`) を停止することを確認。
- **生成 C の不変性 (Gain/Haas/Gate)**: `5bbfa3d2` の converter と `1ecf9bb3` の converter で、Gain 1 関数・Haas 5 関数・Gate 3 関数の生成 C を `diff` し、3 本ともバイト一致 (`ghidra_route` 変更は rcpps 関数内と shim の追加のみで、Gain/Haas/Gate の生成 C は不変)。
- **rcpps 突合 (`snapins/scripts/rcpps_helper_check.c`, 測定 HEAD `1ecf9bb3`)**: 2,000,000 × 4 = 8,000,000 lane (seed 7)、`-O2` mismatch **0** (0.14 s)、`-O0` mismatch **0** (0.25 s)。修正前 (`*(uint32_t*)` 読み, `-O2`) は mismatch 7,984,440 / 8,000,000 (同一 harness の旧測定値)。
- **Resonator emcc (測定 HEAD `1ecf9bb3`, `ghidra_to_c.py resonator --fix bitcast,intload,stackpair,assoc,concat`, `emcc -c -ferror-limit=0`)**: error **7 件**・rc 1。rcpps 由来 **0 件**。残件 (件数の正本): ポインタ型不一致 3 件 (`resonator.c:529`・`616`・`744`: `float[6]`/`float*`/`uint*` と `ushort*`・`uint*` の不一致) と未関数化 callee 4 件 (`FUN_180fd51cc`・`FUN_180fd2d38`・`FUN_180fd4f30` × 2)。`GetLastError`/`SetLastError` 由来 0 件。IAT thunk `81e4`/`81ec` 由来 0 件 (`98885e93` で stub 化済み)。
  - 旧 converter (`5bbfa3d2`) の同条件 emcc は 13 件 (同じ decompile・`--fix` 同一)。差分は rcpps 代入形の変換 (`rcpps_w` → 値返し helper) と THUNK 表の反映によるもので、件数差の内訳は本節では分解していない。
- **回帰 (`native_ref` 1000 trial / seed 7, `build_cmp.sh` と同じ emcc 条件, 測定 HEAD `1ecf9bb3`)**: Gain **1000/1000** bit-exact (wasm 15,161 B, emcc 0.69 s)・Haas **1000/1000** (16,878 B, 0.65 s)・Gate **1000/1000** (17,367 B, 0.65 s)。wasm サイズは §10-3 と一致。
- 未実施: Resonator の native 全バイト突合 (1000 trial)・ablation・ネガコン (emcc 未通過のため)。残件の起票先は PR 本文の未解決表を参照。
- 注: `main` の `98885e93` (#1746) で IAT thunk `81e4`/`81ec` は fail-fast stub 化済み (取り込み済み。#1746 は close 済み)。
#### 10-7k. #1746 (KH-26) run: IAT thunk 2 件の fail-fast stub 化 (部分・Resonator はビルド未通過)
- 素材: `plugins-kilohearts` の Installer zip のみ展開 → payload.dat → windows.zip → HeartCore.core_64 (手展開, dmg 不要)。Ghidra 12.1.4 = GitHub release (zip sha256 `ddac49f9…d2db` 一致)、JDK 21 (Temurin 21)、emsdk 6.0.12 ([EMSDK])。測定 HEAD = `98885e93`。
- IAT thunk の同定 (PE import table・x64 disassembly): `0x180fd81e4` = `jmp [rip+…]` → IAT `KERNEL32!FlsGetValue`、`0x180fd81ec` = 同 → `KERNEL32!FlsSetValue`。呼出元 (`0x180fd3144`・`0x180fd3xxx` 系) は引数を register で渡すが、Ghidra の C 出力はその引数を落として `func_0x000180fd81e4()`・`func_0x000180fd81ec(...)` と呼ぶ。
- 変更 (`ghidra_route/ghidra_to_c.py` のみ、+7 行): `THUNK` 表を追加し、`func_0x000<va>()` の fail-fast stub (`abort()`) を生成する。Win API の意味は実装しない (到達時に abort し、突合で検出する方針。既存の `FUN_18004cf20` と同じ扱い)。
- decompile (Resonator 集合 17 + 未関数化 callee 3 件 + Gain/Haas/Gate 10 関数 = 計 30 関数): **30/30 OK** (`summary.tsv`, `analyzeHeadless` wall 35.5 s, n=1)。
- emcc (resonator, 修復なし, `-ferror-limit=0`, `emcc -c`, HEAD `98885e93`): **15 件** (`grep -c 'error:'`, rc 1, wall 0.12 s)。修復前 (同じ converter・同じ decompile 集合、THUNK 表なし) は **17 件** を同日に計測しており、本 run の修復で **17 → 15 件** (IAT thunk 2 件 `func_0x…81e4`・`81ec` の未宣言エラーのみ消えた)。§10-7i の 14 件とは基準 HEAD が異なるため直接比較しない。
- 残件 (emcc 15 件): `param_1` 引数不足 3・`FUN_180fd4f30` 未宣言 2・引数数不一致 1・`rcpps` 1・`GetLastError`/`SetLastError` 各 1・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1・引数型不一致 3 (`undefined4[8]`→`short*`・`uint*`→`ushort*`・`float*`→`uint*`)・`V128` への int 代入 1。
- 回帰 (同一 HEAD `98885e93`, 1000 trial / seed 7, fix `bitcast,intload,stackpair,assoc,concat`): Gain **1000/1000** (calls 4999/4999, wasm 15,161 B)・Haas **1000/1000** (calls 5500/5500, 16,878 B)・Gate **1000/1000** (calls 4999/4999, 17,367 B)。wasm サイズは §10-3 と一致。
- 未実施: Resonator の native 突合・ablation・ネガコン (emcc 未通過のため)。`GetLastError`/`SetLastError` の stub 規則は未決定 (本 run は IAT thunk のみ)。

#### 10-7m. #1994 (KH-32) run: rcpps 2 引数形の対応 (部分・Resonator はビルド未通過)
- 素材: `plugins-kilohearts` の Installer zip のみ `tar --zstd -xf` で取り出し → payload.dat → windows.zip → HeartCore.core_64 (手展開, dmg 不要)。Ghidra 12.1.4 = GitHub release (zip sha256 `ddac49f9…d2db` 一致・`/opt` 配下に無かったため runner の一時領域に展開)、JDK 21 (Temurin)、emsdk 6.0.12 ([EMSDK])。測定 commit = `730709ae` (コード変更は `ghidra_route/ghidra_to_c.py` のみ、HEAD = 同 commit)。
- 変更: `ghidra_to_c.py` に `rcpps(dest, src)` (V128 を返す 2 引数形) を追加。近似表は `snapins/scripts/approx_tables.b64` を `gen_simd.load_approx_tables()` 経由で読み、`rcp` 表のみ出力 (`rcpps(` を含む出力にだけ差し込む)。指数則・特殊値の扱いは `gen_simd.py` の `kh_rcp_exact` と同一。`gen_simd.py` (RetDec route) は変更していない。
- decompile (Resonator 集合 22 関数 = proc + `also` 16 + 未関数化 callee 3 + IAT thunk 2 件): **22/22 OK** (`summary.tsv`, `analyzeHeadless` wall 17.5 s, n=1)。
- emcc (resonator, 修復なし, `-ferror-limit=0`, `emcc -c`, rc 1):
  - 変更前 (HEAD `7726ccb5`): **10 件** (`grep -c error:`)。
  - 変更後 (HEAD `730709ae`): **8 件**。消えたもの = `rcpps` 未宣言 1・`V128` への `rcpps` 戻り値代入 1。
  - 残件 8 件: `param_1` 引数不足 3 (引数なしで呼ばれる側の関数: `FUN_180fcf904`・`FUN_180fbdfcc`。呼出元 3 件の内訳は未検証 — 本 run の emcc ログを手元で再取得できなかった。呼出元ごとの確認が要る)・引数数不一致 1 (`FUN_180fbdef4` expected 2, have 3)・未宣言 callee 4 (`FUN_180fd4f30` 2・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1 = 閉包は [KH-31] #1989 の範囲)。
  - 件数の基準: 本 run は `grep -c error:` の clang 診断行数で、§10-7i/§10-7j の 14 件・§10-7k の 15 件とは HEAD が異なるため直接比較しない (同一 HEAD 同士の 10 → 8 のみ比較可能)。
- 回帰 (測定 commit `730709ae` と同一 C 生成, `build_cmp.sh` の fix 全部 = `bitcast,intload,stackpair,assoc,concat`, `native_ref` 1000 trial / seed 7, 各 wall ~0.3 s):
  - Gain **1000/1000 bit-exact** (calls 4999/4999, wasm 15,161 B)
  - Haas **1000/1000 bit-exact** (calls 5500/5500, wasm 16,878 B)
  - Gate **1000/1000 bit-exact** (calls 4999/4999, wasm 17,367 B)
  - wasm サイズは §10-3 と一致。
- 未実施: Resonator の native 突合・ablation・ネガコン (emcc 未通過のため)。`rcpps` 2 引数形の出力が native と一致することは Resonator 突合でのみ確認でき、本 run では未確認。残件 `param_1` 3 件 (引数なし呼出) の ABI 推定 (呼出元から引数を復元する規則) は未決定。
- 注: 本 run は素材の展開のみ `work/` 配下で行い、`work/` は gitignore のため commit していない。

#### 10-7l. #1926 (KH-30) run: GetLastError/SetLastError の shim (native oracle と同じ 0 返却・無視) (部分・Resonator はビルド未通過)
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → HeartCore.core_64 (手展開, dmg 不要, `work/winpkg/` = gitignore)。Ghidra 12.1.4 = GitHub release `ghidra_12.1.4_PUBLIC_20260921.zip` (sha256 先頭 16 桁 `ddac49f9…` 一致)、JDK 21 (Temurin 21.0.12)、emsdk 6.0.12 ([EMSDK])。
- 初回 run の測定 commit = `50652246`。review 対応で shim を変えたため、以下の再測定の測定 commit は `a2e0386a` (下記 review 対応の項) に置き換える。
- 変更 (`ghidra_route/ghidra_shim.h` のみ、+4 行 → review 対応で 3 行): `GetLastError()` は常に `0`、`SetLastError(uint)` は値を無視する (native oracle と同じ)。native harness (`snapins/harness/scen_khmath.h`・`scen_khmaster.h` の `n_/khb_GetLastError`・`SetLastError`、`gen_stubs_sigs.py` の `rax = 0;`) がいずれも同じ規則のため。当初は状態変数 (`LastErrorState`) としていたが、SetLastError → GetLastError の経路で wasm と native oracle が食い違うため撤回した。
- review 対応の再測定 (HEAD `a2e0386a`, 測定 commit = `a2e0386a`): decompile (`DecompEach`, Resonator 本体 1 + `also` 16 + Gain/Haas/Gate 閉包 10 = 27 関数) **27/27 OK** (`summary.tsv`, n=1)。emcc (resonator, `-ferror-limit=0`, `emcc -c`): **13 件** (`grep -c 'error:'`、`GetLastError`/`SetLastError` の診断 0 件)。回帰 (1000 trial / seed 7, fix `bitcast,intload,stackpair,assoc,concat`, `build_cmp.sh`): Gain **1000/1000** (calls 4999/4999, wasm 15,161 B)・Haas **1000/1000** (calls 5500/5500, 16,878 B)・Gate **1000/1000** (calls 4999/4999, 17,367 B)。review の指摘 (Gain/Haas/Gate の decompile に GetLastError/SetLastError が現れるか) は、`work/ghidra/out/*.c` を grep して確認: 現れるのは `180fd3144.c` (Resonator の `also` のみ) で、Gain/Haas/Gate の閉包 (`1804b0380`・`1804d0280`・`1804d0180`・`1804cff00`・`1804cff90`・`1804d0720`・`1804c2f50`・`180295f20`・`180020e70`) には 0 件。
- decompile (Resonator 17 + 未関数化 callee 3 + Gain/Haas/Gate 10 = 計 30 関数): **30/30 OK** (`summary.tsv`, `analyzeHeadless` wall 17–19 s, n=1)。
- emcc (resonator, 修復なし, `-ferror-limit=0`, `emcc -c`): **15 → 13 件** (`grep -c 'error:'`)。shim 変更前 (HEAD `00083cdb`) は本 run で 15 件を再現。消えたのは `GetLastError`・`SetLastError` 各 1 件のみ。
- 残件 13 件 (列挙の和 = 13): `param_1` 引数不足 3・未宣言 `FUN_180fd4f30` 2・引数数不一致 1・`undefined4[8]`→`short*` 1・`uint*`→`ushort*` 1・`float*`→`uint*` 1・`rcpps` 2 引数形 1・未宣言 `FUN_180fd51cc` 1・未宣言 `FUN_180fd2d38` 1・`V128` への int 代入 1。
- 試行 (採用せず、`ghidra_to_c.py` は HEAD のまま): `also` に `0x180fd4f30`・`0x180fd51cc`・`0x180fd2d38` を追加すると **13 → 26 件に悪化**。新規分は `puStack_28` 3・`ppuStack_10` 2・`undefined` 2・`DAT_184162358` 1・`HeapAlloc`/`HeapFree` 各 1・未関数化 `func_0x000180fe5c6c`・`func_0x000180fb6c0c`・`FUN_180fd2c90`・`FUN_180fd2c10`・`FUN_180fd1ac4` 各 1 ほか。callee を足すと閉包が広がるという §10-7j の結論と同じ。
- 回帰 (commit `50652246`, 1000 trial / seed 7, fix `bitcast,intload,stackpair,assoc,concat`, `build_cmp.sh`): Gain **1000/1000** (calls 4999/4999, wasm 15,161 B)・Haas **1000/1000** (calls 5500/5500, 16,878 B)・Gate **1000/1000** (calls 4999/4999, 17,367 B)。wasm サイズは §10-7k と一致。
- 注意: `snapins/work/<name>/` が無いと `native_ref` が segfault する (ディレクトリ未作成が原因。`mkdir -p` 後に解消)。
- 未実施: Resonator の native 突合・ablation・ネガコン (emcc 未通過のため)。`rcpps` 2 引数形・`param_1` ABI・未関数化 callee 閉包・型不一致は未着手。

#### 10-7n. #2087 (KH-33) run: Resonator emcc の param_1 引数 ABI 復元 (部分・Resonator はビルド未通過)
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → HeartCore.core_64 (手展開)。Ghidra 12.1.4 = GitHub release `ghidra_12.1.4_PUBLIC_20260921.zip` (sha256 先頭 16 桁 `ddac49f9…` 一致)、JDK 21 (Temurin)、emsdk 6.0.12 ([EMSDK])。測定 commit = `81090e96` (コード変更は `ghidra_route/ghidra_to_c.py`・`ghidra_route/patches.py` のみ)。
- 素材展開 (fix run 2 / HEAD `0d6c73a5`): `plugins-kilohearts.tar.zst` → `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` (76,642,304 B, REPORT 値と一致)。Ghidra 12.1.4 の zip sha256 先頭 16 桁 `ddac49f903da9d5b` 一致。emsdk 6.0.12 を `emsdk install` で導入。
- 呼出元・callee の確定 (本 run で Ghidra decompile 5 関数 + capstone 逆アセンブル、`analyzeHeadless` wall 29.2 s):
  - 宣言型 (Ghidra 出力を引用):
    - `FUN_180fbbfb8`: `short FUN_180fbbfb8(float *param_1,float param_2,int param_3)` → `param_2` は **float**。
    - `FUN_180fbc1f4`: `float afStackX_8 [2];` → `afStackX_8[0]` は **float**。
    - `FUN_180fcf904`: `void FUN_180fcf904(undefined4 param_1)` (Ghidra の宣言。戻り値は呼出元の `sVar1` / `sVar2` = short)。
    - `FUN_180fbdfcc`: `short FUN_180fbdfcc(short *param_1)`。
    - `FUN_180fbdef4`: `ulonglong FUN_180fbdef4(ushort *param_1,short param_2)` → 引数は **2 個**。
  - 機械語の確認: 呼出元 `FUN_180fbbfb8` は `movaps xmm0, xmm6` (xmm6 = `param_2`) の直後に `call 0x180fcf904` (`0x180fbbfe9`)。呼出元 `FUN_180fbc1f4` は `movaps xmm6, xmm0` (xmm0 = 入力 float) の後に `call 0x180fcf904` (`0x180fbc206`)。callee `FUN_180fcf904` は `movss [rsp+8], xmm0` で xmm0 を読み、戻り値は `ax` (`shr eax,0x10; and eax,0x8000`)。よって引数は float、戻り値は short で、`FUN_180fcf904(float)` の規則は機械語と一致する。
  - `FUN_180fbdef4` の読みレジスタ (callee 本体 213 B を capstone で全命令走査): 入力として読むのは **rcx・dx の 2 つのみ**。冒頭 `mov r8, rcx` は rcx からのコピーで、r8 は読む前に書かれる。r9 は `mov r9d, 0x96` で先に書かれてから読まれる。`xor edx,edx` は零化で入力ではない。呼出元 `FUN_180fbc1f4` は `lea rcx,[rsp+0x48]` と `xor edx,edx` の後に `call 0x180fbdef4` (`0x180fbc24e`) で、r8 は設定しない。よって 3 個目の引数 (r8) を落とす規則は正しい。
  - `FUN_180fbdfcc` の呼出元 `FUN_180fbbfb8` は `mov rbx, rcx` (rcx = 入力 `param_1`) の後に `call 0x180fbdfcc` (`0x180fbbfde`)。
- 変更: `patches.py` の ABI 表 (resonator 7 規則) は本 run で変更なし (`git diff 81090e96 HEAD -- tools/targets/kilohearts/ghidra_route` = 0 行)。ABI 表の各規則は生成 C で 1 件ずつ適用されていることを確認 (`resonator.c`: `FUN_180fcf904(float param_1)`・`FUN_180fbdef4(ushort*, short)` の宣言)。
- 変更: `patches.py` に `ABI` 表 (resonator 7 規則)、`ghidra_to_c.py` で適用し各規則の件数が 1 でなければ停止 (assert)。gain/haas/gate には適用されない。
- emcc (resonator, 修復なし, `-ferror-limit=0`, `emcc -c`, rc 1, `grep -c 'error:'`):
  - 変更前 (HEAD `b7cfd62e` = origin/main 時点の resonator 生成, §10-7m と同じ件数): **8 件**。
  - 変更後 (HEAD `81090e96`): **4 件**。消えたもの = `param_1` 不足 3 (`FUN_180fcf904` 呼出元 2 件・`FUN_180fbdfcc` 呼出元 1 件) と引数数不一致 1 (`FUN_180fbdef4`)。
  - 再測定 (fix run 2, HEAD `0d6c73a5`, 同じ Ghidra 出力を再生成): `build_cmp.sh` の `-Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=incompatible-pointer-types-discards-qualifiers` を付けると **4 件** (未宣言 callee のみ)。フラグを付けない `emcc -c -ferror-limit=0 -w -Ighidra_route` では **7 件** (うち pointer 型不一致 3 件 = `resonator.c:527`・`:614`・`:742`。`build_cmp.sh` は同フラグで warning 扱いにして通している既存挙動で、本 run の ABI 規則とは無関係)。
  - 残件 4 件 = 未宣言 callee のみ: `FUN_180fd4f30` 2・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1。閉包は [KH-31] #1989 の範囲 (§10-7j の試行で callee 追加は 13→26 件に悪化するため、本 run では扱わない)。
- 回帰 (HEAD `81090e96`, 1000 trial / seed 7, fix `bitcast,intload,stackpair,assoc,concat`, `build_cmp.sh`): Gain **1000/1000** (calls 4999/4999, wasm 15,161 B)・Haas **1000/1000** (calls 5500/5500, 16,878 B)・Gate **1000/1000** (calls 4999/4999, 17,367 B)。wasm サイズは §10-7m と一致。
- 注意: `snapins/work/<name>/` が無いと `native_ref` が segfault する (§10-7l と同じ。`mkdir -p` で解消)。
- 未実施: Resonator の native 突合・ablation・ネガコン (emcc 未通過のため)。`FUN_180fcf904` の ABI (float 引数・short 戻り値) は呼出元 2 件と callee 本体の機械語で確認済み (上記「呼出元・callee の確定」)。native 突合での実行検証は未実施。

#### 10-7p. #1216 (KH-24) run: Stereo / Delay の Ghidra 実ビルド試行 (部分・両者とも emcc 未通過)
- 測定 commit: `f847e8c6` (`ghidra_route/ghidra_to_c.py` の変更を含む最後の commit 時点の値)。現行の件数は下の 10-7p-2 (Delay 601・Stereo 39)。
- 環境: Ghidra 12.1.4 = `Ghidra_12.1.4_build` の zip (sha256 `ddac49f9…d2db` 一致) を [GHIDRA] (`GHIDRA_HOME`) に展開 (素材外のため run ごとに取得が必要)、JDK 21 (temurin-21)、emsdk 6.0.12 ([EMSDK])。素材 `plugins-kilohearts` は Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` を手展開 (`extract_installer.sh` は dmg を要求するため使わず)。
- 手順 (再現): `DecompEach.java` を snapins.json の lift 集合 (Stereo 8 / Delay 141 = proc + also) で実行 → `ghidra_to_c.py <name> work/gr/<name> <out> <core> --fix bitcast,intload,stackpair,assoc,concat` → `emcc -ferror-limit=0` (`build_cmp.sh` と同じ flags)。

| snap-in | 関数 | decompile (import 込み wall, n=1) | C 化 | emcc (clang エラー行, `-ferror-limit=0`) |
|---|---|---|---|---|
| Stereo | 8 | **8/8 OK** (32.8 s) | 891 行・0.07 s | **失敗 39 件** |
| Delay | 141 | **141/141 OK** (29.0 s) | 7,247 行・2.7 s | **失敗 710 件** (emcc 14.1 s) |

- [f847e8c6 時点・粗い分類] Stereo の残件 (粗い正規表現分類、件数): 引数数不一致 (引数なし呼出 `param_1` 不足) 10・未宣言の SIMD/Ghidra 疑似関数 9 (`rsqrtps`・`maxps`・`ZEXT416`・`SUB168`・`ABS`・`vpsrldq_avx`)・128bit レーン型 (`V128`/`undefined1[16]`) 9・未宣言の型/識別子 9・未関数化 callee 2。
- [f847e8c6 時点・粗い分類] Delay の残件 (件数): 未宣言の型/識別子 350 (`code`・`sbyte`・`undefined` とローカル宣言の欠落 `pcVar1` 等)・引数数不一致 108・演算の型不一致 (実数未取得。旧記録の「約 100」は約表記のため撤回)・128bit レーン型 47・未宣言の Win API 46 (`HeapAlloc`/`HeapFree`/`GetCurrentProcess`/`IsProcessorFeaturePresent`/`TerminateProcess` 等)・未宣言の SIMD 疑似関数 37・`LOCK`/`UNLOCK` 20・未関数化 callee 5。旧内訳の合計 713 は総数 710 と合わない (分類が重複。ad hoc 正規表現で、再現するスクリプトが無かった)。排他的な内訳は `emcc_census.py` で再測定して出す (10-7p-2)。
- 手作業パッチ (`patches.py` の ASSOC/ABI 表): Stereo / Delay とも 0 件 (規則は未追加)。残件はすべて emcc の clang エラーとして残る。
- 変更 (`f847e8c6`・`ghidra_to_c.py` 2 行): (1) `SNAPINS` に `delay` を追加 (proc `0x1802ed7f0` + also 140 件)。IAT thunk `0x180fd81e4`・`0x180fd81ec` は THUNK 辞書で stub 化するため also から除外 (入れると署名抽出で停止する)。(2) Ghidra が jmp thunk を `thunk_FUN_<飛び先>` と出す関数 (Delay 4 件: `180f8791c`・`180f87cac`・`180f87d40`・`180fc61dc`) の署名名を `FUN_<va>` に揃える (本体の同一性は未検証)。修正前は `signature not found` で停止していた。本体の呼出 `thunk_FUN_*` の扱いは 10-7p-2 で変更した (旧版は本体の呼出まで自関数の VA に置換し、自己再帰を作っていた)。
- 回帰 (`f847e8c6`, 1000 trial / seed 7, `build_cmp.sh gain`): Gain **1000/1000** bit-exact (calls 4999/4999, wasm 15,161 B)。Haas / Gate は同じ converter 経路のため本 run では未再測定 (件数は §10-7o の値)。
- 未実施: Stereo / Delay の 1000 trial 突合・ネガコン・第二 oracle の結論 (emcc 未通過のため)。子 issue #3071 [KH-39] (Stereo)・#3072 [KH-40] (Delay)・#3073 [KH-41] (突合・ネガコン・結論) に分割。
- 注意: `snapins/work/<name>/` が無いと `native_ref` が segfault する (§10-7l と同じ。build_cmp.sh 単体では作られないため `mkdir -p` が要る)。
- 差分確認: 測定後のコード変更は 10-7p-2 を参照 (現行の測定 commit `6f5e17fa`)。

#### 10-7p-2. #1216 差し戻し対応 (round 2・3): 本体の thunk 呼出は飛び先 `FUN_<X>` へ写す・census の分類規則を修正
- 経緯: 差し戻し B1 (c2003a0c) の規則 (本体の呼出 `thunk_FUN_<X>` を「X を飛び先に持つ thunk の VA」へ写し、0 本・2 本以上なら停止) は、`thunk_FUN_180fb6bf8` の写し先が 2 本 (`180f8791c`・`180f87d40`) あり `候補 2 件 (停止)` で止まった。本体の呼出は lift 順の raw で 3 件 (`1802ed640` に 2 件、`180f87cac` に 1 件)。round 2 の「raw の本体 thunk 呼出 0 件」は再現しなかった (§10-7q ① の注記どおり、decompile の順序で出力が変わる)。
- 採用 (merge `ad3c5235`・round 3 で承認): main 側 (`7d1d0e2e`) の規則 = 飛び先 `FUN_<X>` へ写す。定義ヘッダは `THUNK_HDR` で `FUN_<va>`。
- jmp の同一性 (PE バイト・`HeartCore.core_64`): `180f8791c` → `jmp` → `180f87d40` → `jmp` → `180fb6bf8`、`180fc61dc` → `jmp` → `180fd66a0`、`180f87cac` → `jmp` → `180f878e0` (本体の `thunk_FUN_180fd66a0` は thunk `180fc61dc` を指す)。いずれも単一の `jmp rel32`。
- 測定 commit: `6f5e17fa` (census の規則修正。converter は `ad3c5235` から不変)。`git diff 6f5e17fa HEAD -- tools/targets/kilohearts/ghidra_route` の出力は 0 行。
- 環境: 素材 `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B、手展開)・`toolchain-emsdk` ([EMSDK] 6.0.12)・[GHIDRA] 12.1.4 (sha256 `ddac49f9…d2db` 一致)・JDK 21。repo 外で作業。n=1。

| 項目 (`6f5e17fa`) | 結果 |
|---|---|
| decompile (lift 141 / stereo 8) | **141/141 OK**・**8/8 OK** (`summary.tsv`)。0x 付きの引数では 137 件目で `NumberFormatException` により中断したため、10 進で再実行 |
| C 化 | delay 7,248 行・stereo 891 行。残存 `thunk_FUN_` 0・自己呼出し 0 (`selfcall_check.py`) |
| emcc (`emcc -c -ferror-limit=0`・`2> emcc.log`) | delay **601** (7.3 s)・stereo **39** (0.08 s) |
| C の byte 一致 | delay・stereo を `origin/main` の converter (`git archive`) で出した C と `cmp` 一致 (本 run)。gain・haas・gate は `ad3c5235` 時点で一致 |
| `thunk_map_check.py` | RESULT 7/7 (本 run) |

- census (`emcc_census.py`・排他的・合計 = error 行数。`grep -c 'error:'` は 601 / 39 でドライバ行 0): delay 601 = 未関数化 callee 6・レーン 200・引数数不一致 108・SIMD/AVX/swi 61・Win API 0・code 間接呼出 21・未定義 identifier 17・型不一致 186・その他 2 (`conflicting types`)。stereo 39 = 2・16・10・9・0・0・0・2・0。
- 起票先: #3094 [KH-42] = レーン 200 / #3095 [KH-43] = SIMD/AVX/swi 61 / #3096 [KH-44] = 残り 340 (引数 108・型不一致 186・code 21・未定義 identifier 17・未関数化 6・その他 2)。§10-7q ④ は main 側の旧分類で区切りが異なる。件数の正本はこの census。
- 旧記録: §10-7p の 710 は `f847e8c6` 時点の旧値。Gain/Haas/Gate の 1000 trial は §10-7q ⑤ を引き継ぐ。未実施: Stereo / Delay の 1000 trial 突合・ネガコン・第二 oracle (#3073)、n≥3 の所要。
- 再現 (`<G>` = [GHIDRA]、`<C>` = `HeartCore.core_64`、`<gr>`・`<out>` は repo 外。lift = `snapins/snapins.json` の `delay.lift` の一意アドレスを 10 進で渡す):
  ```
  JAVA_HOME=<JDK21> <G>/support/analyzeHeadless <proj> kh -import <C> -noanalysis -scriptPath scripts/ghidra -postScript DecompEach.java <out>/delay <lift 10進...> -deleteProject
  python3 ghidra_route/ghidra_to_c.py delay <gr>/delay <out>/delay <C> --fix bitcast,intload,stackpair,assoc,concat
  emcc -c -ferror-limit=0 -I ghidra_route <gr>/delay/delay.c -o <gr>/delay/delay.o 2> <gr>/delay/emcc.log; python3 ghidra_route/emcc_census.py <gr>/delay/emcc.log
  python3 ghidra_route/selfcall_check.py <gr>/delay/delay.c; python3 ghidra_route/thunk_map_check.py
  ```

#### 10-7q. #3072 (KH-40) run: Delay の Ghidra 変換 (型名・LOCK・Win API stub・thunk 正規化) (部分・emcc は未通過)
- 結論: Delay の lift 141 関数はすべて decompile OK。thunk 正規化は**列 0 の定義行だけ**に限定した (`7d1d0e2e`)。これで本体の thunk 呼出し行が自己呼出しに変わる誤書換えを止めた。emcc clang 診断は **601 件** (測定 commit `7d1d0e2e`)。旧記載の 736 → 526 は本 run で再現しなかった (③)。Gain/Haas/Gate 1000/1000 bit-exact (回帰なし)。残件 601 件の内訳と起票先は ④。
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip/`1ccb1df8…` → `HeartCore.core_64` (76,642,304 B, 手展開)。Ghidra 12.1.4 = `[GHIDRA]` (zip sha256 `ddac49f9…d2db` 一致)、JDK 21 (temurin-21)、emsdk 6.0.12 (`[EMSDK]`)。

**① 自己呼出し (レビュー指摘 1)**
- 原因: 旧正規表現 `^([\w \*]+?)\s+thunk_FUN_[0-9a-f]+\(` の `[\w \*]` は空白を含む。そのため本体のインデント付き呼出し行 `  thunk_FUN_<X>(...)` にも一致し、`count=1` によって関数ごとに最初の 1 箇所が `FUN_<その関数の va>(...)` (自己呼出し) に変わっていた。
- 修正: `^(\w[\w \*]*?)[ \t]+thunk_FUN_[0-9a-f]+\(` (列 0 の定義行だけ・空白は `[ \t]` に限定。`\s` は改行を跨ぐため使わない)。呼出し行は従来どおり `thunk_FUN_` → `FUN_` の置換で飛び先の `FUN_<飛び先>` になる。
- 実データでの発生 (lift 順 141 関数の decompile・`work/ghidra/out141`): 本体のインデント付き `thunk_FUN_` 呼出しは 3 行 (`1802ed640` の行 37・79、`180f87cac` の行 10)。旧版は `1802ed640` の行 37 を `FUN_1802ed640();` (自己呼出し) にした。`1802ed640` の 1 関数・1 行。修正版は 0 件。
- 件数では検出できない: 旧版と修正版の生成 C の差分は 4 行だけで、emcc 件数は両方 601 (自己呼出しは C として通るため)。
- 測定 (`ghidra_route/selfcall_check.py`、関数本体が自分の `FUN_<va>` を呼ぶ箇所を数える): 修正版 **0 件**、旧版 **1 関数 (1 行)**。
- decompile の結果は実行順で変わる (未検証の推定: Ghidra の関数作成順の影響): 同じ 141 関数を昇順で decompile した union 実行 (150 関数) では、3 ファイル (`1802ed640`・`1802ed7f0`・`180f87cac`) の出力が lift 順と異なり、呼出しは `func_0x000180fc61dc` 形になって `thunk_FUN_` の呼出し行は出なかった。この union 実行の emcc は 602 件。本節の測定は lift 順 (141 関数) で行った。

**② Delay 測定 (測定 commit `7d1d0e2e`、コミット済み HEAD で再現)**
- decompile: lift 集合 141 件 (`snapins.json` の delay.lift の一意アドレス) → **141/141 OK** (`analyzeHeadless` wall 27.7 s, decompile の内訳は `work/ghidra/out141/summary.tsv`, n=1)。
- C 化: `ghidra_to_c.py delay` → コード集合 139 件 (exports 1 + also 138)。lift 141 = コード集合 139 + IAT thunk 2 件 (`180fd81e4`・`180fd81ec`、THUNK 表へ)。
- 自己呼出し: 修正版 0 件 / 旧版 1 関数 (①)。
- emcc (`emcc -c -ferror-limit=0 -I ghidra_route delay.c`, `grep -c 'error:'`): 修正版 **601** (15.6 s)。旧版 601 (件数は変わらない)。
- 更新前の数値との関係: 旧記載の 710 → 736 (正規化で増えた) の原因は本 run では未特定。自己呼出し 1 件は件数を変えない (601 = 601)。正規化なしの対照は測れない (定義 `thunk_FUN_<X>` が `FUN_<va>` に直されず、`signature not found` で停止するため)。

**③ 526 の再現不能 (旧記載の訂正)**
- 旧記載 (測定 commit `dfe3592e`) の emcc 526 件は、同じ commit 内容・同じ shim・同じ数え方の本 run では再現しなかった。同じ内容で decompile の順序だけを変えると 601 (lift 順 141 件) / 602 (昇順 150 件)。`build_cmp.sh` の `-Wno-error=…` 付きの起動では 499 件 (昇順 150 件での測定)。526 を出した条件は未特定。本節の数値は 601 で置き換える。

**④ 残件 601 件の内訳 (`emcc` の `error:` 行を種類で分けた。合計 = 601)**

| 種類 | 件数 | 起票先 |
|---|---|---|
| レーン参照 `undefined1[64]`・`[16]` のメンバ参照 ("member reference base type") | 138 | #3094 [KH-42] |
| SIMD/AVX 疑似関数の未宣言 (ABS 10・SUB168 5・SUB84 3・ZEXT816/416 各 2・vcvtdq2pd_avx 3 ほか) | 40 | #3095 [KH-43] |
| `swi(3)` 未宣言 | 21 | #3095 [KH-43] |
| 引数の過不足 ("too few arguments" 84・"too many arguments" 24) | 108 | #3096 [KH-44] |
| 型不一致・ポインタ型 (invalid operands・assigning to・int-conversion・incompatible pointer 等) | 248 | #3096 [KH-44] |
| `code` 型の間接呼出し ("called object type 'code'") | 21 | #3096 [KH-44] |
| 未定義 identifier (`DAT_`・`uRam`・`LAB_`・`PTR__`) | 17 | #3096 [KH-44] |
| 未関数化 callee (`func_0x…`・`FUN_…` の未宣言 call) | 6 | #3096 [KH-44] |
| その他 (`FUN_18004cf20` の STUB 宣言と本体の型の衝突 "conflicting types") | 2 | #3096 [KH-44] |
| **合計** | **601** | #3094 138 / #3095 61 / #3096 402 |

- 振り分け (`error:` 行のメッセージ語で 1 行 1 種類): `member reference base type` → レーン / `'swi'` → swi / `undeclared function` で `func_0x`・`FUN_` → 未関数化 callee、それ以外 → SIMD・AVX 疑似関数 / `undeclared identifier` → 未定義 identifier / `too few`・`too many arguments` → 引数 / `called object type` → code 間接呼出し / `invalid operands`・`assigning to`・`incompatible`・`passing`・`indirection`・`operand of type` → 型不一致 / 残り → その他。

**⑤ 回帰 (HEAD `7d1d0e2e`、`build_cmp.sh <name> 1000 7 bitcast,intload,stackpair,assoc,concat`)**
- Gain **1000/1000** (calls 4999/4999, wasm 15,161 B)・Haas **1000/1000** (calls 5500/5500, 16,878 B)・Gate **1000/1000** (calls 4999/4999, 17,367 B)。wasm サイズは §10-7n と一致。
- Gain/Haas/Gate の生成 C は旧版 (`e45456e4`) と 3 本とも差分 0 行 (この 3 本の decompile には、インデント付き `thunk_FUN_` 呼出しが無い)。

**⑥ 測定 commit の証跡**
- 測定 commit = `7d1d0e2e` (コード変更: `ghidra_route/ghidra_to_c.py` と新規 `ghidra_route/selfcall_check.py`)。
- `git diff 7d1d0e2e HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` は 0 行 (この節の追記 commit は REPORT のみ)。

- 未実施: Delay の native 突合 (emcc 未通過のため)。#3073 [KH-41] の範囲。`swi(3)` と SIMD 疑似関数の意味付けは #3095 [KH-43]。
#### 10-7r. #3071 (KH-39) 1 単位: Stereo の emcc 残件の機械修復 (部分・emcc 39 → 10 件・Stereo はビルド未通過)
- 結論・測定・ABI 規則 1〜11・未解決 1〜5 の全文は付録 `REPORT_APPENDIX_3071.md` §10-7r へ分割移動した (本ファイル 250 行上限・内容は削除していない)。
