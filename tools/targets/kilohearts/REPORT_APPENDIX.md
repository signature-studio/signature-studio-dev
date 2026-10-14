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

#### 10-7k. #1405 (KH-25) 1 単位: rcpps 2 引数形と GetLastError/SetLastError (部分・Resonator は未通過)
- 素材: `plugins-kilohearts` (Installer zip) → `extract_installer.sh` (KH_SRC 指定) で `work/winpkg/HeartCore.core_64`。Ghidra 12.1.4 = GitHub release `ghidra_12.1.4_PUBLIC_20260921.zip` (sha256 `ddac49f9…d2db` 一致)、JDK 21 (Temurin 21)、emsdk は `/opt/emsdk` (6.0.12)。`extract_installer.sh` は mac 側の `llvm-lipo` が無く末尾で失敗するが、win 側 (`HeartCore.core_64`) は抽出済み。
- 変更 (`ghidra_route/` のみ): (1) `ghidra_shim.h` に `GetLastError`/`SetLastError` を `g_last_error` の状態変数で定義 (Win API の最終エラー値。wasm に OS 状態は無い)。(2) `ghidra_to_c.py`: `rcpps(dst, src)` の 2 引数形を生成する `RCPPS_HELPER` を追加。実機 (AMD Ryzen 9 9950X) の rcp 近似表 `snapins/scripts/approx_tables.b64` を読み、`gen_simd.py` の `kh_rcp_exact` と同一の指数則で 4 lane を計算する。`rcpps(` を含む出力のときだけ埋め込む。(3) `undefined1 in_XMM\d+ [16]` も `V128` に変換 (入力レジスタ宣言の型不一致を解消)。
- Ghidra decompile (Resonator 17 関数): **17/17 OK** (`summary.tsv`, `analyzeHeadless` wall 24.6 s, n=1)。
- emcc (resonator, 修復なし, `-ferror-limit=0`・`-Wno-error=` は build_cmp.sh と同じ): **14 → 10 件**。解消: `GetLastError`/`SetLastError` 2 件。`rcpps` 2 件はコンパイル解消のみ (未宣言・V128 代入の構文エラーが消えた。**数値は未検証**)。残件 (10 件): `param_1` 引数不足 3・引数数不一致 1 (`FUN_180fbdef4(…,0,0)` 3 引数)・`func_0x…81e4`/`81ec` 各 1 (IAT thunk)・`FUN_180fd51cc` 1・`FUN_180fd2d38` 1・`FUN_180fd4f30` 2。
- 参考: `-Wno-error=` を付けずに出すと `incompatible-pointer-types` 3 件 (`FUN_180fd54cc`・`FUN_180fbdfcc`・`FUN_180fe5dfc` の引数型) が出る。build_cmp.sh の既定フラグでは警告扱いで、解消は未実施。
- 回帰 (同一 HEAD・同一 shim/converter, `native_ref` 1000 trial / seed 7, fix `bitcast,intload,stackpair,assoc,concat`): Gain 1000/1000 bit-exact (wasm 15,161 B, emcc 0.8 s)・Haas 1000/1000 (16,878 B, 0.5 s)・Gate 1000/1000 (17,367 B, 0.5 s)。wasm サイズは §10-3 と一致。
- `rcpps` の数値検証 (本 run で実施):
  - 源オペランドの確認: Ghidra decompile は本環境に無い (`plugins-kilohearts` 未取得・`work/` 無し) ため、`rcpps(` 行の貼付けと、戻り値の代入先の確認は**未実施**。
  - 根拠 (既存記録のみ): `snapins/harness/scen_resonator.h` が process 内 `rcpps xmm2, xmm1` (Intel 順 = dst, src) と記録している。この場合 `in_XMM2` は未使用の旧 dst で、真の源は第 2 引数。ただし記録のアドレス (`0x180743419`) と本件の callee (`0x180fd…`) の対応は未照合。
  - helper の引数: 第 2 引数 `src` を読み、第 1 引数 `dst` は読まない (`src` 読みで実装)。源が第 1 引数だった場合は誤りになる。
  - converter の安全策: `ghidra_to_c.py` は `rcpps(` が文頭の呼出し (戻り値の捨て) のとき `SystemExit` で止める。代入形 (`x = rcpps(...)`) は通す。
  - helper の native 突合: `snapins/scripts/rcpps_helper_check.c` が生成 helper を `_mm_rcp_ps` と比較。乱数 2,000,000 × 4 lane = 8,000,000 lane、不一致 **0** (`./rcpps_helper_check`、0.14 s、seed 7)。測定機は AMD EPYC 7763 (Zen 3)。表の抽出元は Ryzen 9 9950X。
- 未実施: Resonator 全体の native 突合 (1000 trial)・ablation・ネガコン (emcc 未通過のため)。残件 10 件は次の単位に分ける: (a) `param_1` 引数 ABI 推定 + 引数数不一致 (`FUN_180fbdef4`)、(b) IAT thunk (`81e4`/`81ec`) の stub 規則、(c) 未関数化 callee 閉包 (`FUN_180fd4f30`・`51cc`・`2d38`)。(d) `rcpps` の源オペランドと戻り値の代入先を Ghidra 出力で確認 (`plugins-kilohearts` を取得して 1 行貼付け)。
