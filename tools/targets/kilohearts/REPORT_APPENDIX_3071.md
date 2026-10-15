# KH-39 (#3071) 付録: Stereo の emcc 残件の機械修復 (REPORT_APPENDIX §10-7r の本体)

#### 10-7r. #3071 (KH-39) 1 単位: Stereo の emcc 残件の機械修復 (部分・emcc 39 → 10 件・Stereo はビルド未通過)
- **既知類型との関係 (DEFECTS.md)**: `in_XMM3` の参照は D5 に該当しない (下記「in_XMM の live-in 判定」: 全読出しが先行書込みに支配される、または dst で未使用)。xmm1 の `0.0` 仮置き (規則 9) は入口 live-in の置換で D5 に該当 (未解決 3)。
- **結論**: Stereo の emcc は 39 → **10 件** に減った (未達)。引数なし呼出・引数数不一致・型・SIMD 近似 (rsqrtps)・ABS/ZEXT416 は解消。Gain/Haas/Gate は 1000/1000 bit-exact を維持し、生成 C は修復前と diff 0 行。ただし Stereo は**数値未検証**: callee の戻り値 (xmm0/xmm1) を C 化していないため、emcc が通っても数値は正しくない (未解決 2・3)。`in_XMM3` の入口 live-in は無い (下記)。xmm1 は規則 9 の `0.0` 仮置き (未解決 3)。emcc 通過は値の正しさを示さない。
- 測定 commit: `44230a54` (`feat(kh)`: converter / shim / patches の最終変更)。`50661465` (`test(kh)`: rsqrt 突合 C の追加) は突合 C のみで、`git diff 44230a54 50661465 -- ghidra_route/ghidra_to_c.py ghidra_shim.h patches.py` = **0 行** (測定値は 44230a54 のコードで取得)。main 取り込み (`710cdac9`) 後の `git diff 50661465 HEAD -- tools/targets/kilohearts/ghidra_route` は 4 ファイル・61 行追加・3 行削除 (main 側: shim の `code`/`undefined`/`sbyte` typedef・LOCK/Win API stub、`ghidra_to_c.py` の thunk 正規化と delay 登録、`selfcall_check.py` 新規。patches.py は本節のラベル・コメント)。**HEAD の再測定は round 3 review run が測定 HEAD `8043dfcb` で実施済み** (decompile 18/18 OK・stereo emcc 10・生成 C の gain/haas/gate/stereo の 4 関数が `44230a54` と diff 0 行・回帰 Gain/Haas/Gate 各 1000/1000。未解決 5)。本 commit は文書のみで、`git diff 8043dfcb HEAD -- tools/targets/kilohearts/ghidra_route` = 0 行。
- 素材: `work/` の既存展開物 (HeartCore.core_64 76,642,304 B) を流用。Ghidra 12.1.4 の sha256 先頭 16 桁は round 3 review run で `ddac49f903da9d5b` と一致を確認。decompile は gain/haas/gate 閉包 10 関数 + stereo 8 関数 = 18 関数を `DecompEach.java` で再実行 → **18/18 OK** (`work/ghidra/out` を union で再生成。stereo 8 関数の出力は退避版と cmp 一致)。
- 修復前の基準: `ghidra_to_c.py stereo` (fix なし) → `emcc -c -w -O1 -ferror-limit=0 -Wno-error=int-conversion` → **39 件** (`grep -c error:`、rc 1、再現一致)。注: §10-7h の実測 (`grep -c 'error:'` = 40 = clang 診断 39 + ドライバ行 1) と 1 件ずれる。ずれの原因は未確認 (数え方の差か)。件数の比較は本節の 39 → 10 同士で行う。

**emcc 件数の内訳 (39 → 10、照合済み: 残り 2+6+2 = 10)**

| 修復前カテゴリ | 修復前 | 修復後 | 修復 |
|---|---|---|---|
| 引数不足 (引数なし呼出) | 8 | 0 | ABI 規則 (下表) |
| 引数数不一致 (expected 2, have 1) | 2 | 0 | ABI 規則 (placeholder 0.0 ・下表) |
| `undefined1[16]` メンバ参照 (`in_XMM3._0_8_` 4 + `in_XMM3._8_8_` 2) | 6 | 0 | `in_XMMn` を V128 化・`_0_8_d` (double 視点)。入口 live-in は無い (下記 in_XMM 節) |
| `undefined1[16]` 代入不可 (`in_XMM3 = ZEXT416`) | 1 | 0 | V128 化 (同上。emcc 通過は値の正しさを示さない) |
| 未宣言 `ZEXT416` | 1 | 0 | shim `ZEXT416` |
| 未宣言 `rsqrtps` (+ V128 への int 代入) | 1 (+1) | 0 | converter の `rsqrtps` helper |
| 未宣言 `maxps` (+ V128 への int 代入) | 1 (+1) | 0 | shim `maxps` (x86 MAXPS 順序) |
| 未宣言 `ABS` | 3 | 0 | shim `ABS` = fabs |
| 未宣言 `vpsrldq_avx` (+ V128 への int 代入) | 1 (+1) | 0 | shim `vpsrldq_avx` (右 n バイト) |
| 未知型 `sbyte` | 2 | 0 | shim `typedef int8_t sbyte` |
| 未宣言 `SUB168` | 2 | **2** | 未修復 (未解決 1) |
| `V128` 二項演算 (`auVar * auVar`・`+`) | 6 | **6** | 未修復 (未解決 1) |
| 未関数化 `FUN_180fd8aac` | 2 | **2** | 未修復 (未解決 2) |
| **合計** | **39** | **10** | |

- 途中段階: P1 (ABI・helper・型・ABS/ZEXT416) の後で 14 件、P2 の maxps・vpsrldq_avx の後で 10 件。

**ABI 規則 (stereo, `patches.py` の `ABI['stereo']`、11 規則・各規則の件数 = 1 を assert で確認)**
- 呼出元の機械語 (capstone, `snapins/scripts/pe_dis.py` 相当) で、呼出し直前に xmm0 へ入る値の源を経路ごとに確定。callee は入力を xmm0 のビット列で読む (`vmovq r11,xmm0` / `movsd [rsp+0x60],xmm0`) ため、引数は `d2u(...)` (double のビット列) で渡す。

- 行番号の基準 (本ファイル全体): 特記しない限り、rsqrtps helper (23 行) を入れる前の生成 C (`stereo.c`) の行。現 HEAD の `stereo.c` では +23 (例: 185→208・186→209・567→590)。

| # | 修復前行 (呼出元) | callee | 引数 (xmm0 の源) | 機械語の根拠 (呼出元) |
|---|---|---|---|---|
| 1 | 465 (FUN_180fcd690) | FUN_180fdc700 | `param_1` (元入力) | `movq rdx,xmm0`@180fcd6a1 → `movq xmm0,rdx`@180fcd9e0 → call@9e5 |
| 2 | 468 (FUN_180fcd690) | FUN_180fdfdb0 | `ABS(param_1)` | `btr r10,0x3f`@180fcd6b3 → `movq xmm0,r10`@180fcd6cc → call@9be |
| 3 | 502 (FUN_180fcd690, flag≠0) | FUN_180fdc470 | `ABS(param_1)` | `btr r9,0x3f`@180fcd9f8 → `vmovq xmm0,r9`@180fcdabd → 経路 ac9 → bd0 → call@bd5 |
| 4 | 528 (FUN_180fcd690, flag≠0) | FUN_180fdc700 | `param_1` (入口値のまま) | 入口 xmm0 の未変更経路 (9f0→a04→ab7→bf0) → call@bf0 |
| 5 | 571 (FUN_180fce0d0, flag≠0) | FUN_180fdc470 | `param_1` | `vmovq r9,xmm0`@180fce460 → `vmovq xmm0,r9`@528 → jae 534 → call@630 |
| 6 | 598 (FUN_180fce0d0, flag≠0) | FUN_180fdc6d8 | `param_1` (入口値のまま) | 460 以降 xmm0 未変更 → jg 476 → 515 → je 522 → call@640 |
| 7 | 631 (FUN_180fce0d0, flag==0) | FUN_180fdc6d8 | `param_1` | `movq rdx,xmm0`@180fce0e1 → 経路 437 → `movq xmm0,rdx`@180fce450 → call@455 |
| 8 | 634 (FUN_180fce0d0, flag==0) | FUN_180fdfdb0 | `ABS(param_1)` | `btr r10`@180fce0ed → `movq xmm0,r10`@180fce0ff → jae 10b → call@439 |
| 9 | 185 (FUN_18080d4d0) | FUN_180fce0d0 | 2 個目 (xmm1) **未設定** → `0.0` 仮置き | 呼出元 18080d4d0〜d527 に xmm1 の書込みなし (入力依存・未モデル) |
| 10 | 186 (FUN_18080d4d0) | FUN_180fcd690 | 2 個目 (xmm1) = 直前 call の戻り → `0.0` 仮置き | 18080d527 の call 後の xmm1 は callee 出力 (未モデル) |
| 11 | 567 (FUN_180fce0d0, flag≠0) | FUN_180fdc660 | `param_1` (C の `uVar1` は ulonglong で、double 引数へ数値変換していた) | `vmovq xmm0,r9`@180fce528 → jae 534 → call@53a |

- 件数: 規則 1〜11 はすべて 1 件 (assert 通過)。内訳: 引数なし呼出 8 (規則 1〜8、callee 4 種 × 2 箇所)・引数数不一致 2 (規則 9・10、placeholder)・型誤り 1 (規則 11、silent な数値変換の修正)。引数の源は、元入力 `param_1` = 規則 1・4・5・6・7・11 の 6 件、`ABS(param_1)` = 規則 2・3・8 の 3 件、xmm1 未設定 = 規則 9・10 の 2 件。
- 注: 規則 11 は emcc では検出されず (ulonglong → double の暗黙変換)、機械語で確かめて手で直した silent 誤り。
- 規則 11 の行番号は **567** に統一 (`patches.py` のラベル・コメントを 590 から 567 へ直した。ラベルは assert の表示と辞書キーにしか使わず、生成 C に影響しない)。根拠は表の機械語: `FUN_180fce0d0` 内で call@53a (行 567) < call@630 (行 571・規則 5) < call@640 (行 598・規則 6) と、行番号と番地が単調に並ぶ。590 だと行 571 と 598 の間に入り、番地順と合わない。修復前 C の 567 行は `uVar3 = FUN_180fdc660(uVar1);` で、規則 11 の呼出しと一致する (round 2 review run が素材の decompile 出力で確認)。

**ネガティブコントロール**: 作業コピー (`work/negctl/ghidra_route`) で規則 3 (502) の正規表現を壊す (該当 0 件) と、`python3 ghidra_to_c.py stereo ...` は `AssertionError: ABI rule hit 0: stereo 502 FUN_180fdc470 xmm0 = ABS (vmovq xmm0,r9 180fcdabd)` で停止し、**終了コード rc=1** (assert が効くことを確認)。この実測は round 2 の review run による (implementer 側では未再実行)。

**rsqrtps helper の検証**
- 実装: `RSQRTPS_HELPER` (`kh_rsqrt_exact` は `gen_simd.py` と同一の式・同一指数則 `190-((e+1)>>1)`、表は `load_approx_tables()` の `rsq_odd`/`rsq_even`)。rcpps も `kh_rcpps` の macro 形 (`#define rcpps(dst,src) kh_rcpps(src)`) に揃えた (dst は未使用で、resonator の `in_XMM` V128 化と型を合わせるため)。
- 突合: `ghidra_route/rsqrtps_helper_check.c` (`_mm_rsqrt_ps` と 4 lane bit 一致、入力は seed 7 の 32bit 乱数 = 負数・NaN 含む): **8,000,000 lanes mismatch 0** (`-O2`・`-O0` 両方、ホスト CPU = AuthenticAMD)。ただし突合対象は 9950X ではなくホスト CPU の `_mm_rsqrt_ps` で、表の出所 (9950X) との同一性は未検証。
- rcpps 既存突合 (`snapins/scripts/rcpps_helper_check.c`, macro 化後): mismatch 0 (8,000,000 lanes)。

**回帰 (fix = `bitcast,intload,stackpair,assoc,concat`, 1000 trial / seed 7, `build_cmp.sh`)**
- Gain **1000/1000 bit-exact** (calls 4999/4999, wasm 15,161 B)
- Haas **1000/1000 bit-exact** (calls 5500/5500, wasm 16,878 B)
- Gate **1000/1000 bit-exact** (calls 4999/4999, wasm 17,367 B)
- wasm サイズは §10-7n と一致。
- 生成 C: `ghidra_to_c.py gain/haas/gate` (fix なし) の出力を修復前 (`work/gr/base/<n>/`) と `diff` → **0 行** (sigs.json・globals.json も一致)。修復はすべて stereo 限定の規則か、stereo にしか現れない形 (`in_XMM`・`maxps`・`ZEXT416`・`ABS`・`sbyte`) なので、gain/haas/gate には影響しない。
- 注意: `build_cmp.sh` は `snapins/work/<name>/` が無いと `native_ref` が segfault する (§10-7l と同じ。mkdir -p で解消)。

**in_XMM の live-in 判定 (D5 観点)**
- 変換の意味: `undefined1 in_XMMn[16]` を V128 にした (`in_XMMn._0_8_` は `_0_8_d` の double 視点)。`in_XMMn` は Ghidra が関数入口の値に付ける名前で、V128 ローカルは入口では未初期化のまま。emcc が通ることは値の正しさを示さない。先行書込みの無い読出しは D5 (`docs/DEFECTS.md`: 関数入口 live-in の xmm0-3) と同型の silent 誤りになる。
- `in_XMM3` の参照の判定 (round 2 review run が素材 `plugins-kilohearts` の decompile 出力 `18080d4d0.c` で確認。implementer 側では未再確認): `grep -n in_XMM3` の参照は 9 行 = 宣言 1・`in_XMM3._0_8_` 4 (行 52 書・55 読・83 書・86 読)・`in_XMM3._8_8_` 2 (行 53・84 書)・`in_XMM3 = ZEXT416` 1 (行 202、ループ内の書込み)・`rsqrtps` の dst 1 (行 213)。修復前 emcc の member 参照 error 6 件の内訳は `in_XMM3._0_8_` 4 + `in_XMM3._8_8_` 2 (修復前 `stereo.c` の 201・202・204・232・233・235 行)。
- 読出し 55・86 は、それぞれ直前の書込み 52・83 と同じ直線ブロック内で必ず先行される (else 節 49〜70・81〜101 に分岐なし)。よって入口 live-in は無い。
- 行 213 の `in_XMM3` は `rsqrtps` の dst 引数。`kh_rsqrtps(src)` は dst を使わないので値に影響しない。
- 結論: `in_XMM3` の参照は全て先行書込みに支配される、または dst で未使用。**D5 に該当しない**。
- xmm1 の `0.0` 仮置き (規則 9・10) の D5 判定:
  - 規則 9 (行 185・呼出元 `FUN_18080d4d0`): 表の機械語 (18080d4d0〜d527) に xmm1 の書込みが無い。2 個目の引数は関数入口の xmm1 そのもので、`0.0` はその入口 live-in を silent に置換している → **D5 に該当** (未解決 3)。
  - 規則 10 (行 186): 直前の call (規則 9 の callee `FUN_180fce0d0`) の戻り xmm1。callee 出力なので D5 ではなく、**KH-46 の多値戻りの未モデル** (未解決 2)。

**未解決 (子 issue。親 #3071。本 run で起票: KH-45・KH-46)**
1. **[KH-45] V128 二項演算 6 件 + SUB168 2 件 + 未関数化 FUN_180fd8aac 2 件 (計 10 件・emcc 残件の全部)**: `auVar * auVar + auVar` (行 725・726・733・839・840・846) と `SUB168(x, 8)` (725・839: 128bit の上位 8 バイト抽出)。乗算・加算の lane 型 (mulps/mulpd 等) を機械語で確定してから shim 化する。
   未関数化 callee `FUN_180fd8aac` 2 件 (内訳の 2 件目)**: `also` へ足すと閉包が広がる (§10-7j・§10-7l の前例 13→26)。追加前に件数を測る。
2. **[KH-46] callee の多値戻り (xmm0 / xmm1) の未モデル (最重要・emcc で見えない silent 誤り)**: `FUN_180fdc470`・`FUN_180fdfdb0`・`FUN_180fdc660` 系は rax に四分象限のみ C 化され、reduce 後の値 (xmm0、dfdb0 は xmm1 も) は C 本体に出ない。呼出元の `extraout_XMM0_Qa*` の読み 6 箇所が未代入 (未初期化)。stereo の数値は native vec (`snapins/work/stereo/vec_1000_7.bin`) との突合でのみ判定可能で、本 run では未実施 (emcc 未通過)。
3. **[KH-46] 引数 2 個目 (xmm1) の 2 件 (規則 9・10) は 0.0 仮置き**: 呼出元で未設定の入力のため、実値の特定 (FUN_18080d4d0 の呼出元の解析) が要る。規則 9 は入口 live-in の置換で D5 に該当、規則 10 は規則 9 の callee の戻り xmm1 (多値戻り・未解決 2) (上記「in_XMM の live-in 判定」)。
4. **[KH-46] stereo の bit 型修復 (fix 未適用)**: `bitcast`・`intload`・`assoc` などの `--fix` 群を stereo に適用していない (例: 行 223 の `(float)((uint)(fVar13-fVar18) & _DAT_1813d6fc0)`)。突合で検出する。
5. **[再測定] 解消 (round 3 review run・測定 HEAD `8043dfcb`)**: decompile 18/18 OK・stereo emcc 10 (`grep -c error:`)・生成 C の gain/haas/gate/stereo 4 関数が `44230a54` と diff 0 行・回帰 Gain/Haas/Gate 各 1000/1000。main 側の thunk 正規化・shim の typedef は stereo の件数と生成 C を変えていない。以降の HEAD が `8043dfcb` から変わる場合は、`git diff 8043dfcb HEAD -- tools/targets/kilohearts/ghidra_route` の差分の分だけ再測定する (`docs/WORKFLOW.md` §6)。
- 未実施: Stereo の native 突合・ablation・ネガコン (emcc 未通過のため)。
- 注: REPORT.md 本体への導線 1 行は、commit 範囲 (ghidra_route + REPORT_APPENDIX) の指示どおり未追加。§10-7p は本ファイル群に存在しないため、本節は REPORT_APPENDIX.md の §10-7q (#3072) の後に置いてあったものを分割移動した。

## §KH-74 (#3853): callee FUN_180fdc660 の戻り xmm0 を機械語の式で C 化

- `1227b9e92` 時点の測定 (main 取り込み前)。その後 `2063ac5da` (main 取り込みの merge) で `ghidra_route` が 90 行変わった (`ghidra_shim.h` +17・`ghidra_to_c.py` +36/−3・`patches.py` +40)。そのため本節の『0 行』の主張は `1227b9e92` 時点のものに限る。現 head の測定は下の『再測定』節 (測定 commit `2063ac5da` = コードを変えた最後の commit・`git diff 2063ac5da HEAD -- tools/targets/kilohearts/ghidra_route` は 0 行) を正とする。
- 素材: `plugins-kilohearts` の Installer zip → payload.dat → windows.zip → `HeartCore.core_64` (76,642,304 B) を手展開。Ghidra 12.1.4 (sha256 先頭 16 桁 `ddac49f903da9d5b` 一致)、emsdk 6.0.12。
- 式 (capstone 逆アセンブル、180fdc660〜180fdc6d6・ret は 180fdc6d6 の 1 本): `k = fma(x, 2/π, 1.5·2^52) − 1.5·2^52`、`t1 = fma(−k, π/2 上位, x)`、戻り xmm0 (180fdc6c5 `vmovapd xmm0,xmm2`) = `fma(−k, 6.123e−17, t1)`、rax = `int(k) & 3`。定数は PE の `0x18228a860`・`…a8a0`・`…a870`・`…a880` (rip 相対で解決)。
- (1227b9e92 時点) 突合 (`ghidra_route/xmm0_check.c`・`kh_xmm0.h` を gcc で native 実行と比較): 1,000,000 試行 (乱数ビット・一様・k·π/2 近傍・特殊値) で **rax 不一致 0・xmm0 不一致 0 (PASS)**。NaN 同士の payload 差は 28,623 件 (一致扱いで別計上)。
- (1227b9e92 時点) ネガティブコントロール: `kM2` の仮数 1 bit を変えた版は 100,000 試行で **xmm0 不一致 23,716 (FAIL・rc=1)**。突合が効くことの確認。
- (1227b9e92 時点) 生成 C: `ghidra_to_c.py stereo` の出力 `stereo.c` 914 → 934 行 (+20 = `kh_xmm0.h`)。`extraout_XMM0_Qa*` の読出し **6 → 4** (解消 2: 180fcd690 の 82 行・180fce0d0 の 24 行)。残 4 = `FUN_180fdc470` 2 件・`FUN_180fdfdb0` 2 件 (子 issue へ)。
- (1227b9e92 時点) emcc (`-c -w -O1 -ferror-limit=0`): base (`e03d588ee`) 12 行 → HEAD 12 行。エラーは同一の残件 (KH-45 の V128 演算・SUB168・未関数化 FUN_180fd8aac・行番号のみ +20 シフト)。新規エラー 0。
- (1227b9e92 時点) 回帰: gain / haas / gate の生成 C は `e03d588ee` の `ghidra_to_c.py` と HEAD の差分 0 行 (3 本とも・sigs.json 一致)。stereo 限定の規則のため。gain/haas/gate の 1000/1000 bit-exact (§10-7r の測定) は生成 C 不変のため引き継ぐ。
- 未測定: Stereo 全体の native 1000 trial 突合 (#3073)。本節は callee 単体の突合まで。
- 再測定 (main 取り込み後): 測定 commit `2063ac5da` (`df2f768ea` を merge した commit。コード変更はこの merge だけ)。コミット済み HEAD・作業ツリーはクリーン。`git diff 2063ac5da HEAD -- tools/targets/kilohearts/ghidra_route` は本 commit の時点で 0 行。
  - 素材: `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8…` → `HeartCore.core_64` (76,642,304 B)。Ghidra 12.1.4 (zip sha256 先頭 `ddac49f9…` 一致)、emsdk 6.0.12。
  - decompile: stereo の閉包 `closure.py stereo` = 49 関数・反復 12・FAIL 0 (5 分 23 秒)。gain/haas/gate の 10 関数 = 10/10 OK (analyzeHeadless wall 26.4 s)。
  - xmm0_check 1,000,000 試行: rax 不一致 0・xmm0 不一致 0 (PASS・NaN 同士の payload 差 28,623 件は別計上)。`kh_xmm0.h`・`xmm0_check.c` は PR の測定 commit `aaf3f6f41` から差分 0 行。
  - 生成 C (stereo): HEAD 936 行 / `origin/main` 916 行 (`origin/main` = 取り込み元の `df2f768ea`)。差分は `kh_xmm0.h` の 20 行と置換 3 箇所 (本体 1・呼出元 2) のみ。`emcc -c -w -O1 -ferror-limit=0` は HEAD・`origin/main` ともに error 0 (rc 0)。
  - `extraout_XMM0_Qa*` の読出し件数 (`origin/main` → HEAD): **2 減**。呼出元 2 件の ABI 規則 (`stereo 82 caller 180fcd690`・`stereo 24 caller 180fce0d0`) が各 1 件の `dVar2 = extraout_XMM0_Qa_00;` を `kh_xmm0_180fdc660` に置換する (`ghidra_to_c.py` は ABI 規則ごとに closure 全体の件数 1 を assert)。本体の規則と `stereo 468・502・571・634` は読出しを消さない (lookahead のみ)。生成 C の直接計数は本 run では未実施 (runner に Ghidra 無し)。参考: 『(1227b9e92 時点)』の生成 C 実測で同じ 2 件が 6 → 4。
  - 生成 C (gain / haas / gate): HEAD と `origin/main` の差分 0 行 ×3・`sigs.json` 一致。`build_cmp.sh` の突合は 1000/1000 bit-exact (gain 4999/4999・haas 5500/5500・gate 4999/4999。wasm 15,161 / 16,878 / 17,367 B。§10-7t と同値)。
  - stereo の native 突合: HEAD 0/1000・`origin/main` 0/1000 (RESULT 行で確認。HEAD は trial 0 から FAIL・`18080d4d0` @self+0x80)。数値の状態は main と変わらない (#3073 の範囲)。

## §KH-77 (#3885): callee FUN_180fdfdb0 の戻り xmm0 (縮約値) を機械語の式で C 化

- 結論: `FUN_180fdfdb0` の戻り **xmm0** を機械語 132 命令の順で C 化し、呼出元 2 箇所の `extraout_XMM0_Qa` (無添字) の読出し **2 → 0 件**。callee 単体の突合は rax・xmm0 とも 1,000,000 試行で一致 (PASS)。**戻り xmm1 は未対応** (子 issue)。Stereo 全体の数値突合は未達 (#3073)。
- 測定 commit: `e2e31a569` (コード変更: `ghidra_route/kh_xmm0.h`・`patches.py`・`xmm0_check.c`)。コミット済み HEAD で再現した。
- 素材: `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/…` → `HeartCore.core_64` (76,642,304 B、REPORT §KH-74 と同サイズ)。Ghidra 12.1.4 (zip sha256 先頭 `ddac49f9…` 一致)、JDK 21、emsdk (runner 同梱)。`scripts/extract_installer.sh` は mac の dmg (`7z` 展開) を要求し、素材に dmg が無いため Windows 側だけを手で展開した。
- 式 (capstone 逆アセンブル、180fdfdb0〜180fdffb6・ret は 180fdffb6 の 1 本・132 命令)。命令の順は C 写しの骨格で、段ごとの積の順 (`kPiA·hh` 等) を SSE レーン順と 1 命令ずつ照合した記録は無い (突合 PASS で値は一致した)。照合は未実施:
  - 入力 x の仮数 m (暗黙の 1 付き) と指数から、table (PE `0x18228ac50` の 168 B) の 3 語 A・Bl・Bh を選び、`A·m`・`Bl·m`・`Bh·m` の 64×64→128 積を `mul` 3 本で作る (180fdfdfa・180fdfe08・180fdfe26)。
  - 128bit 整数の和 (`add`・`adc`) で窓の積を合わせ、`j = e & 7` のシフトで商 k の整数部 (`rax`) と小数部を分ける。`rax & 3` が戻り rax (180fdfe64)。
  - 小数部を正規化して `d0` (上 53bit) と残差 `rr` を作り、`d0` の上 27bit を `hh`、残り `ll = d0 − hh`。
  - 戻り xmm0 (180fdffa2 `addsd xmm0,xmm1` の結果) = `x0 + t`。`x0 = d0·PIH`・`t` は `kPiA`・`kPiB` の積の和 (`kPiA = 0x3ff921fb50000000`・`kPiB = 0x3e5110b460000000`・`kPiH = 0x3ff921fb54442d18`・`kPiT = 0x3c91a62633145c06`、c1〜c3 の PE 実値 `0x18228ab30・ab40・ab50` から取った)。
  - 定数の出所は table 実バイトと PE の定数領域 (`0x18228ab30`・`ab40`・`ab50`)。
- 突合 (`ghidra_route/xmm0_check.c` の第 4 引数 `dfdb0`): 入力は呼出元の ABS 規則に合わせ |x| を使い、|x| < 1 は除外 (呼出元の分岐 `dVar2 < Inf` 側・table の添字が範囲外になる)。
  - 本番 1,000,000 試行 (seed 7): **rax 不一致 0・xmm0 不一致 0 (PASS)**。skipped (|x| < 1) 423,419 件は突合の対象外。
  - ネガティブコントロール: `kPiA` の 1 bit を変えた版 (`0x3ff921fb50000001`) で **xmm0 不一致 1,000,000 件・rc=1 (FAIL)**。突合が効くことの確認。
  - 回帰: 660 (KH-74) の突合も 1,000,000 試行 PASS (`kh_xmm0_check RESULT: PASS`)。
  - 注記: 開発中に `kPiB` の 1 bit 変異は突合で検出されなかった (寄与が小さい)。検出力は `kPiA` で確認した。
  - 開発中に見つけた誤り: `rax` を後段の縮約で上書きしていたため、戻り rax が誤った。機械語 180fdfe68 (`mov [rsp],rax`) の退避値を使う形に直した (`quad` 変数)。
- 生成 C (`ghidra_to_c.py stereo --fix bitcast,intload,stackpair,assoc,concat`): **1025 → 1026 行** (+1 = `kh_xmm0_180fdfdb0` の宣言)。
  - `patches.py` の ABI 規則 2 件 (呼出元 `stereo 603 caller 180fcd690`・`stereo 769 caller 180fce0d0`) が各件数 1 で適用 (件数 1 を assert)。
  - `extraout_XMM0_Qa` (無添字・代入右辺) の読出し: **2 → 0**。残る `extraout_XMM0_Qa_01` 2 件は `FUN_180fdc470` (KH-76・#3884)。
  - emcc (`emcc -c -w -O1 -ferror-limit=0 -Wno-error=int-conversion -I ghidra_route`): HEAD・測定 commit ともに **error 行 0 (rc 0)**。
  - 生成 C の差分は 2 行 (呼出元の読出し)・+1 行 (宣言) のみ。
- 回帰 (gain / haas / gate): 測定 commit の `ghidra_to_c.py` と HEAD (`967dfec5d`) の生成 C の差分 **0 行 ×3** (`diff -q` 無出力)。stereo 限定の規則のため。
- 閉包: `closure.py stereo` = 49 関数・反復 12・FAIL 0 (3 分 6 秒・load は実行中 0.8 前後)。
- 未測定: Stereo 全体の native 1000 trial 突合 (#3073)。`build_cmp.sh stereo` の数値突合は本 PR では再実行していない (KH-74 時点で 0/1000 のまま・数値は変わらない)。
- 未解決:
  1. 戻り **xmm1** (残差・1e-19 台) は未対応。呼出元 180fcd9c8・180fce43e が `movapd xmm4, xmm1` で読む。→ #4705 (KH-114)。
  2. `FUN_180fdc470` の xmm0 (呼出元の `extraout_XMM0_Qa_01` 2 件) → #3884 (KH-76)。
  3. Stereo の数値突合 0/1000 → #3073。

#### 10-7t. #3108 (KH-45) run: Stereo の emcc 残件 10 件の解消 (emcc 10 → 0 件・Stereo 突合は 0/1000 で未達)
- 結論: Stereo の emcc は **10 → 0 件** (`grep -c error:` = 0、終了コード 0)。Gain/Haas/Gate は 1000/1000 bit-exact を維持し、生成 C は修復前と diff 0 行。Stereo の数値は突合で **0/1000 bit-exact** (未達)。emcc が通ったことは数値の正しさを示さない (§10-7r の注記どおり)。`FUN_180fd8aac` は関数化せず、到達で abort する stub にした (未解決 2)。
- 測定 commit: `eb5532ae9` (コード変更: `ghidra_route/ghidra_shim.h`・`patches.py`・`ghidra_to_c.py`)。コミット済み HEAD で再現した。
- 素材: `plugins-kilohearts` の Installer zip → `payload.dat` → `windows.zip/1ccb1df8…` → `HeartCore.core_64` (76,642,304 B)。Ghidra 12.1.4 = `[GHIDRA]` (zip sha256 先頭 `ddac49f9…` 一致)、JDK 21 (`[JDK21]`)、emsdk 6.0.12 = `[EMSDK]` (runner 同梱の既存導入)。
- decompile: 19 関数 (gain/haas/gate 10・stereo 8・`FUN_180fd8aac` 1) すべて OK (`analyzeHeadless` wall 34.2 s、n=1)。

**残件 10 件の内訳 (修復前の emcc error 10 件を原因ごとに割り当てた表。件数は `*` を単位に数える)**

| 原因 | 件数 | 修復前の行 (§10-7r の行番号) | 修復 (`V128OPS` の規則・assert 値) |
|---|---|---|---|
| `*` (`auVar = auVar * auVar + auVar;` の行。`+` は同じ式内のため別件に数えない) | 2 | 733 (180fdc470 l37)、846 (180fdfdb0 l36) | 規則 1 = 2 件 (`v128_add(v128_mul64(a, b), c)`) |
| `*` (`SUB168(auVar * auVar, n)` の内側) | 4 | 725・726 (180fdc470 l29・l30)、839・840 (180fdfdb0 l29・l30) | 規則 2 = 4 件 (`v128_mul64(a, b)`) |
| 未宣言 `SUB168` | 2 | 725 (180fdc470 l29)、839 (180fdfdb0 l29) | shim `SUB168(x, off)` |
| 未関数化 `FUN_180fd8aac` | 2 | 未確定 (§10-7r に行番号の記録なし。呼出元は 180fdc6d8 l11・180fdc700 l11) | 到達で abort する stub (`SNAPINS['stereo']['stubs']`) |
| **合計** | **10** | | |

- 件数の根拠 (機械語): `*` は 2 関数 × 3 本 = 6。`180fdc470` は `mul rcx` @180fdc4ba・4c8・4e6 と 128bit 加算 @180fdc4d4〜4d7、`180fdfdb0` は `mul rcx` @180fdfdfa・fe08・fe26 と 128bit 加算 @180fdfe17 (adc)。両オペランドの上位 qword は呼出し直前に 0 (`auVarN._8_8_ = 0`) なので、積は 64×64→128 の符号なし積。lane 型は整数で、`mulps`/`mulpd` ではない。`+` は 128bit 整数加算。
- 行対応の確度: 件数 (2・4・2・2) は §10-7r の実測と `V128OPS` の assert 値が一致する。`*` の行を規則 1・規則 2 のどちらに割り当てるかは、`V128OPS` コメントの decompile 行 (l29・l30・l36・l37) と §10-7r の行番号の差が関数内で一定 (180fdc470: 725−29 = 726−30 = 733−37 = 696、180fdfdb0: 839−29 = 840−30 = 846−36 = 810) であることからの推定。pre-fix の stereo.c は再生成していない (Ghidra 未展開) ため、emcc による行単位の再照合は未実施。
- `FUN_180fd8aac` の行番号は未記録のため未確定 (件数 2 は §10-7r の実測)。
- shim (`ghidra_shim.h`): `v128_mul64` (`unsigned __int128`)・`v128_add`・`SUB168(x, off)` (Ghidra SUBPIECE: `off`=0 で下位 8 バイト、8 で上位)。
- 書換え表 `patches.py` の `V128OPS['stereo']`: 件数を assert (規則 1 = 2 件・規則 2 = 4 件)。stereo 以外には適用しない。
- `FUN_180fd8aac` 2 件 (`180fdc6d8` l11・`180fdc700` l11、9 引数): 指数全 1・仮数 0 の入力 (Inf) でのみ到達する FP 例外の報告経路。呼び先は `FUN_180fd622c`・`FUN_180fd89f0`・`FUN_180fd5bcc`・`FUN_180fd5f30`・`FUN_180fd8988`・`FUN_181327120`・`func_0x000180fe2788`。`also` へ足すと閉包が広がる (§10-7j・§10-7l の前例) ため、`SNAPINS['stereo']['stubs']` に `void FUN_180fd8aac() { abort(); }` を置いた (到達で abort し、突合で検出する)。`also` へ足した場合の件数は**未測定** (閉包 7 関数の追加が要る)。

**実測 (測定 commit `eb5532ae9`、コミット済み HEAD で再現。load 0.22 0.30 0.19 → 0.28 0.31 0.19)**
- Stereo emcc (`emcc -c -w -O1 -ferror-limit=0 -Wno-error=int-conversion`): error 行 **0**、0.18 s。修復前 (`e2cefb36a`) は 10。
- Gain **1000/1000** bit-exact (calls 4999/4999、wasm 15,161 B、emcc 0.3 s)。
- Haas **1000/1000** bit-exact (calls 5500/5500、wasm 16,878 B、emcc 0.3 s)。
- Gate **1000/1000** bit-exact (calls 4999/4999、wasm 17,367 B、emcc 0.3 s)。wasm サイズは §10-7r と一致。
- 生成 C: `ghidra_to_c.py gain/haas/gate` の出力を修復前 (`work/gr_base/`) と `diff` → **0 行** (sigs.json も一致)。
- Stereo 突合 (`build_cmp.sh stereo 1000 7 bitcast,intload,stackpair,assoc,concat`): **0/1000 bit-exact** (`exact-region diff`、trial 0 から FAIL)。abort は発火せず、RESULT 行まで完走した。原因は未切り分け (KH-46 の多値戻り (xmm0/xmm1) の未モデルが有力。未解決 1)。
- 測定 commit 以降のコード差分: `git diff eb5532ae9 HEAD -- tools/targets/kilohearts/ghidra_route` は本節の追記 commit の時点で 0 行 (REPORT のみ)。

**未解決**
1. Stereo の数値突合 0/1000 (未一致の原因の切り分けは未実施。KH-46 の多値戻りが有力) → #3109 (KH-46)。
2. `FUN_180fd8aac` は関数化せず abort stub (閉包 7 関数の追加と件数の測定が未実施) → #3821 [KH-69]。

## §KH-114 (#4705): callee FUN_180fdfdb0 の戻り xmm1 (残差) の式を機械語で確定 (helper 追加・突合 PASS、呼出元の配線は未)
- 測定 commit: `e1bf5e929` (HEAD)。`ghidra_route` の内容は `d59c33886` と同一 (`git diff d59c33886 HEAD -- tools/targets/kilohearts/ghidra_route` = 0 行)。初回の式の確定 (機械語の読み) は `ebd0c63cf` (基点は `origin/main` = `8c785332e`)。
- 素材: `plugins-kilohearts` (`tar --zstd -xf` で展開) → `Kilohearts Offline Installer.zip` 内の `payload.dat` (zip・store) → `windows.zip` (55,114,108 B) → `HeartCore.core_64` (76,642,304 B、sha256 `d55ce8b4c0ad7ebedf1a4a1f74443a91d255596be887a514e54269ec8751441e`)。展開先は `/tmp/opencode/kh/win/` (repo 外・gitignore 対象外のため commit しない)。`HeartCore.core_64` の所在は `7z l` の一覧に出ないネスト zip 内で、`grep -b` の一致位置から `windows.zip` を特定した。
- 初回の decompile (`ebd0c63cf` 時点): Ghidra 12.1.4 (zip sha256 先頭 `ddac49f9…` 一致)、JDK 21。decompile 20 関数 OK (30.6 s、`DecompEach.java`)。今 run の Ghidra は未実行 (下記未実施)。
- 機械語 (`FUN_180fdfdb0`、capstone 132 命令、ret は 180fdffb6 の 1 本): ret 直前の xmm1 は `180fdff09 movq xmm0,r10` 後の double-double の下位成分。
  - `movlhps` (180fdff24・27) で xmm0 = (d0,d0)、xmm2 = (d0−hh, hh) を作り、`mulpd` (180fdff6d〜75) と `addsd` 列 (180fdff83〜9a) で積和。`addsd xmm0,xmm1` (180fdffa2) が xmm0 = S = x0 + t、`subsd xmm2,xmm0`・`addsd xmm1,xmm2` (180fdffa6・aa) が xmm1 = t + (x0 − S)。
  - よって `kh_xmm1_180fdfdb0 = t + (x0 − kh_xmm0_180fdfdb0)` (Fast2Sum の誤差項)。
- 突合 (`ghidra_route/xmm0_check.c dfdb0`、native 実行と bit 一致。|x| ≥ 1 の定義域。現 HEAD `e1bf5e929` で再実行。ビルド `gcc -O1 -ffp-contract=off -Wall` rc 0・警告なし):
  - seed 7 × 1,000,000 試行: rax 不一致 0・xmm0 不一致 0・**xmm1 不一致 0・PASS** (skipped 423,419・実時間 0.076 s)。
  - seed 1 × 1,000,000: rax 0・xmm0 0・xmm1 0・**PASS** (skipped 420,733)。
  - KH-74 回帰 (`660`、seed 7 × 1,000,000): rax 0・xmm0 0・xmm1 0・**PASS** (NaN both の bit 差 28,623 は NaN 同士の一致扱い)。
  - ネガコン (`kPiA` の仮数 1 bit を `0x3ff921fb50000001` に変えたコピーを `/tmp/opencode/neg/` でビルド、`dfdb0` seed 7 × 100,000): **FAIL** (rax 0・xmm0 不一致 100,000・xmm1 不一致 77,936・rc=1)。
- 生成 C (stereo、`ghidra_to_c.py stereo ... --fix bitcast,intload,stackpair,assoc,concat`): 修正前 (`origin/main`) と差分は 3 箇所のみ: コメント 1 行 (未対応 → 式だけ持つ)・helper 宣言 (`kh_xmm1_180fdfdb0` の追加)・式 1 行。未配線のため呼出し側は不変。`extraout_XMM0_Qa*` の読出しは 9 件のまま (`FUN_180fdc470` の `extraout_XMM0_Qa_01` 系 #3884 の範囲)。
- gain / haas / gate の生成 C: `kh_` を含まない (stereo 専用の規則) ため、kh_xmm0.h の変更で生成 C は変わらない (ghidra_to_c.py の規則からの論証。実測は未実施 — 素材 `plugins-kilohearts` が必要)。
- 未達 (配線・子 #4722 KH-115 で扱う): 呼出元 180fcd9c8 (`movapd xmm4, xmm1`) と 180fce43e の xmm1 の読出し先は、生成 C に `extraout_XMM1` として現れない (Ghidra が xmm1 を戻り値として C に出していない)。`patches.py` の置換規則は、この読出し先 (xmm4 経由で多項式の補正項に入る経路) を機械語で確定してから書く。子 issue へ。
- **鮮度**: 初回の式確定 (`ebd0c63cf`) から現 HEAD `e1bf5e929` までの `git diff ebd0c63cf HEAD -- tools/targets/kilohearts/ghidra_route` は 0 行ではない (`kh_xmm0.h` 101 行・`patches.py` 4 行・`xmm0_check.c` 27 行変更。計 3 files・122 insertions(+)・10 deletions(-))。`main` 取り込み由来 (KH-76 の `kh_tab470`・`kh_fn_180fdc470`・`470` モード。`patches.py` の `ulonglong` 4 件は KH-110 #4687)。PR 本文の差分 (`origin/main...HEAD`) は 3 ファイル・34 insertions / 7 deletions。上の突合の数値は、この差分を含む現 HEAD `e1bf5e929` での実測。
- **未実施**: 生成 C (stereo) の前後差分 (`ghidra_to_c.py` の Ghidra 再実行・emcc 通過) は、この run に Ghidra (`analyzeHeadless`) と emcc が無いため未実施。gain / haas / gate の実測も未実施 (上の論証のまま)。
- **NaN の扱い**: `xmm0_check.c` は NaN 同士を一致扱いで計上する (xmm0 と xmm1 とも。payload は見ない)。突合の PASS 条件は NaN 以外の bit 一致。
