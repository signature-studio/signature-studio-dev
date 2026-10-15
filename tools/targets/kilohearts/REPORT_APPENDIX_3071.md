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
