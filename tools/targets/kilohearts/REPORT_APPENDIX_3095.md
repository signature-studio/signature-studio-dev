# #3095 (KH-43) Delay の SIMD 疑似関数・swi の規則 (付録)

- **結論**: #3096 (`26b003692`) 取り込み前の main の Delay emcc 残件 576 件のうち、SIMD 疑似関数 25 件 (13 種) を shim に**実装**し、swi 21 件を **fail-fast** (abort) とした。現 HEAD (測定 commit `ab01412df`・§9) の emcc 残件は **441 件** (SIMD・swi の未宣言 0)。main 取り込み後の `abee0a1ff` (§8) は 463 件、統合前 (`12647936d`) の 506 件は取り込み前の値。Gain/Haas/Gate は 1000/1000 bit-exact (回帰なし)。実装 13 種はホスト x86 intrinsics と 200,000 試行で一致 (ネガティブコントロールは FAIL)。
- **現 HEAD の値は §9** (測定 commit `ab01412df`): emcc 残件 **441 件**。§8 (`abee0a1ff`) は 463 件 (main の #3096 で code 間接呼出し 21 件、#3800 で引数過不足 22 件が消えた分を含む)、§9 は #3802 の取り込みで未定義 identifier・未関数化 callee が減った分をさらに含む。突合と回帰の結果は同じ。
- **入力の訂正**: issue 本文の「SIMD 40 件・swi(3) 21 件」は測定 commit `7d1d0e2e` の値 (emcc 601 件) である。現 main では SIMD 25 件。差 15 件 (ABS 10・ZEXT416 2・maxps 2・vpsrldq_avx 1) は #3071 で shim に定義済み。swi 21 件の内訳は **swi(3) 17 件 + swi(0x29) 4 件** (issue の「swi(3) 21 件」は誤り)。

## 1. 測定の前提

- 素材: `plugins-kilohearts` (Installer zip → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B、`work/` に手展開)、`toolchain-emsdk` (emcc 6.0.12)。
- Ghidra 12.1.4 ([GHIDRA]): 公式 release zip を run 内で取得し、sha256 `ddac49f9…d2db` の一致を確認。JDK 21 (temurin-21)。
- decompile: lift 集合 141 件。`snapins/snapins.json` の `delay.lift` を**挿入順**で渡す (昇順では emcc 577 件になり、601 は再現しない)。結果 **141/141 OK** (wall 28〜29 s, n=1)。Gain/Haas/Gate は 10 関数で **10/10 OK** (27 s)。
- load: 測定時 0.4〜0.6 (4 vCPU)。

## 2. 規則

| 疑似関数 | 件数 (現 main, 変更前) | 規則 | 定義の内容 |
|---|---|---|---|
| `SUB84(x, off)` | 3 | 実装 | lvalue から `off` の 4 byte を切り出す (`kh_sub84`) |
| `SUB168(x, off)` | 5 | 実装 | V128 値から `off` (0/8) の 8 byte を切り出す |
| `ZEXT816(v)` | 2 | 実装 | 下位 64bit に v、上位 64bit は 0 (movq) |
| `minps` | 1 | 実装 | lane 毎 `a < b ? a : b` (NaN は b)。`maxps` と対称 |
| `vcvtdq2pd_avx` | 3 | 実装 | 下位 2 個の int32 → 2 個の double |
| `vcvtpd2dq_avx` | 1 | 実装 | 2 個の double → int32 (既定丸め = 最近接偶数)。NaN・範囲外は 0x80000000、上位 64bit は 0 |
| `vshufps_avx` | 2 | 実装 | Intel の SHUFPS 選択 (imm の 2bit ずつ) |
| `vpmovsxdq_avx` | 2 | 実装 | 下位 2 個の int32 を符号拡張して int64 |
| `vpsubq_avx` / `vpsubd_avx` | 1 / 1 | 実装 | src1 − src2 (lane 毎・wrap) |
| `vpsrlq_avx` | 1 | 実装 | lane 毎の論理右シフト。imm ≥ 64 は 0 |
| `vpand_avx` / `vpor_avx` | 1 / 2 | 実装 | 128bit の論理積・論理和 |
| `swi(n)` (17 + 4) | 21 | **fail-fast** | `kh_swi_fail()` = `abort()`。引数は評価しない |
| `ABS` / `ZEXT416` / `maxps` / `vpsrldq_avx` | (現 main では 0) | 既存 | #3071 で定義済み (`fabs`・`ZEXT416`・`maxps`・`vpsrldq_avx`)。本 issue では変更なし |

- 実装 13 種の合計は 25 件 (= 3+5+2+1+3+1+2+2+1+1+1+1+2)。
- SUB168・SUB84 の未宣言エラーは消えるが、同じ行の V128 同士の `*` (`auVar6 * auVar3`) と `^` は型不一致として残る (#3096)。SIMD 行に残った 17 件はレーン参照 (#3094) と型不一致 (#3096)。
- **swi の根拠**: x86 の `int 3` は breakpoint、`int 0x29` は `__fastfail` で、どちらも未処理なら戻らない trap (`int 3` は例外ハンドラや debugger で再開できる)。直後は `(*pcVar1)();` (間接呼出し) で、正常系の戻りは無い。未処理なら Windows では process が終わるため、abort による fail-fast が同じ観測結果になる。到達の有無は native 突合で確認する (#3073)。

## 3. emcc 残件の変化 (`ghidra_route/emcc_census.py`、排他分類)

| 分類 | 601 (`7d1d0e2e` 再現) | 576 (#3096 前の main, 変更前) | 506 (`12647936d`) |
|---|---|---|---|
| 未関数化 callee | 6 | 6 | 6 |
| レーン型 (`undefined1[N]`・メンバ参照) | 200 | 190 | 166 |
| 引数数不一致 | 108 | 108 | 108 |
| SIMD・AVX・swi 疑似関数 | 61 | 46 | **0** |
| code 型の間接呼出し | 21 | 21 | 21 |
| 未定義 identifier | 17 | 17 | 17 |
| 演算・代入の型不一致 | 186 | 186 | 186 |
| その他 | 2 | 2 | 2 |
| **合計** | **601** | **576** | **506** |

- 576 → 506 (−70): SIMD・swi −46 と、同じ行に付随していたレーン型 −24。変更前後で、疑似関数を含まない行のエラーは 489 件で不変 (行単位で照合)。
- 601 → 576 (−25): SIMD −15 (#3071 の定義による。`7d1d0e2e` の shim を `git archive` で取り出し、同じ out141 から 601 件を再現して確認)。レーン −10 は原因未特定。

## 4. 検証 (測定 commit `12647936d`・`git archive HEAD` の clean export で再実行)

- **単体突合** (`ghidra_route/simd_shim_check.c`): 実装 13 種を、ホストの x86 intrinsics (`_mm_sub_epi64`・`_mm_min_ps`・`_mm_cvtpd_epi32`・`_mm_shuffle_ps` 等) と各 200,000 試行で比較。入力は乱数の 128bit (vcvtpd2dq は任意ビット列の double で NaN・Inf・範囲外を含む、vshufps は代表 16 通りの即値)。**mismatches: 0** (rc 0)。
- **ネガティブコントロール**: `-DKH_NEG=1` で vpsubq の参照を `b − a` にすると **mismatches: 200000、rc 1**。検査が誤りを検出することを確認した。
- **vcvtpd2dq の境界**: 単体突合の入力は乱数ビットの double なので、丸めの境界 (x.5 ちょうど・2^31 近傍) はほぼ踏まない。mismatches 0 は乱数入力の範囲の保証で、境界値の保証ではない (境界値の数点の追加は未実施)。
- **回帰** (`build_cmp.sh <n> 1000 7 bitcast,intload,stackpair,assoc,concat`、clean HEAD):
  - Gain **1000/1000** bit-exact (calls 4999/4999, wasm 15,161 B)
  - Haas **1000/1000** (calls 5500/5500, wasm 16,878 B)
  - Gate **1000/1000** (calls 4999/4999, wasm 17,367 B)
  - 3 本とも wasm サイズは §10-7q ⑤ と一致。生成 C は変更前の converter の出力と `cmp` で一致 (3 本とも差分 0)。
- **未実施**: Delay の native 突合 (emcc が 506 件で通らないため)。#3073 の範囲。

## 5. 測定 commit の証跡

- 測定 commit = `12647936d` (コード変更は `ghidra_route/ghidra_shim.h`・`ghidra_route/ghidra_to_c.py`・新規 `ghidra_route/simd_shim_check.c`)。
- `git diff 12647936d HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` の出力は 0 行 (この節を含む REPORT の commit は範囲外)。

## 6. 再現

```sh
cd tools/targets/kilohearts
# (1) decompile: DecompEach.java に lift 集合 141 件を挿入順の 10 進で渡す (snapins.json の delay.lift)
python3 ghidra_route/ghidra_to_c.py delay work/gr/x work/ghidra/out141 work/winpkg/HeartCore.core_64 --fix bitcast,intload,stackpair,assoc,concat
emcc -c -ferror-limit=0 -I ghidra_route work/gr/x/delay.c -o work/gr/x/delay.o 2> work/gr/x/emcc.log
python3 ghidra_route/emcc_census.py work/gr/x/emcc.log            # 合計 441 (測定 commit ab01412df・§9)
# (1') 件数の数え方 (§2・§3 の 576 列)。件数は emcc のエラー行で数える。
#      SIMD 46 (= 13 種 25 + swi 21) と swi 21 は 26b003692 の変換器・shim で同じ out141 から作った emcc ログでも再現する
#      (work/c26b/emcc.log。git archive 26b003692 の ghidra_route と snapins/{lift,scripts} を使う)。この log の総数は 555 (= 576 − code 間接呼出し 21)
grep -cE "call to undeclared function '(SUB84|SUB168|ZEXT816|minps|vcvtdq2pd_avx|vcvtpd2dq_avx|vshufps_avx|vpmovsxdq_avx|vpsubq_avx|vpsubd_avx|vpsrlq_avx|vpand_avx|vpor_avx)'" work/c26b/emcc.log   # SIMD 25
grep -c "call to undeclared function 'swi'" work/c26b/emcc.log                                                              # swi 21
grep -oE 'swi\([^)]*\)' work/gr/x/delay.c | sort | uniq -c                                                                  # swi(3) 17・swi(0x29) 4 (生成 C)
# (2) 単体突合 (emscripten.h のスタブを置く)
printf '#define EMSCRIPTEN_KEEPALIVE\n' > work/simd_check/emstub/emscripten.h
gcc -O1 -mavx2 -Wno-unused-function -I ghidra_route -I work/simd_check/emstub ghidra_route/simd_shim_check.c -o work/simd_check/pos -lm && work/simd_check/pos   # mismatches: 0
gcc -O1 -mavx2 -DKH_NEG=1 -Wno-unused-function -I ghidra_route -I work/simd_check/emstub ghidra_route/simd_shim_check.c -o work/simd_check/neg -lm && work/simd_check/neg   # mismatches: 200000, rc 1
# (3) 回帰
bash ghidra_route/build_cmp.sh gain 1000 7 bitcast,intload,stackpair,assoc,concat   # haas / gate も同じ
```

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| レーン参照 166 件 (既定の `--fix`。`undefined1[N]` のメンバ参照。`auStack_x._8_4_`・`auVar._0_16_` 等) | Delay の emcc が通らない | #3808 [KH-67] (`undefined1[64]` 106 件)・#3809 [KH-68] (`aauStack_f8` 11 件)・新規子 #3953 [KH-78] (残り 49 件 = 166 − 117、内訳は未確定) |
| 引数過不足 86 件 (#3800 の 22 件は main で解消) | 同上 | #3844 [KH-79] 33 件・#3847 [KH-73] 53 件 |
| 型不一致 186 件 (V128 同士の `*`・`^` を含む) | 同上 | #3801 [KH-65] |
| 未定義 identifier 2 (`LAB_180fd2aab`・`PTR__guard_dispatch_icall_1813a1d38`) | 同上 | #3835 [KH-70] (親 #3802) |
| 未関数化 callee 1 (`func_0x0001802ecfc0`) | 同上 | #4014 [KH-85] (親 #3802) |
| 実装 13 種のオペランド順 (Ghidra pcodeop の規約: 先頭が vvvv の src1) を機械語で個別確認していない。swi の到達は未確認 | 反転・到達の誤りは Delay の native 突合でしか検出できない | #3073 [KH-41] |
| レーン 200 → 190 の 10 件の原因 (`7d1d0e2e` 以降の変更のどれか) | 件数の説明のみ | #3953 [KH-78] へのコメントで扱う (原因未特定) |

- #3813 の lanes 規則は `--fix lanes` の opt-in で、既定の --fix 外。本 census (既定の --fix) には入っていない。
- #3808 (106) と #3809 (11) の計 117 件は、#3813 の post-lanes 測定の `member reference base type` 残件 117 件と同じ数 (#3094 の本文)。
- 子 issue の本文の件数 (#3801 の「型不一致 187」・#3802 の「未関数化 callee 5」) は #3096 の記録 (census 556) の値。本 HEAD の census は 186・6 (§8)。件数の差の原因は §8 に書く。

## 8. main 取り込み後の再測定 (測定 commit `abee0a1ff`)

- 経緯: PR 作成後に main が進み、取り込みは 4 段階 (merge commit は 5 つ)。(1) `origin/main` (`45182bf1b` → `5ebde52cc`) は merge commit `793662e84`・`537247f81` で取り込み済み (`docs/DOC_MAP.md` の競合は両行を残した)。(2) `origin/main` (`ce3f5eac7`) は merge commit `934c8dd71` で取り込んだ。`ghidra_shim.h` が #3108 (`eb5532ae9`) の `SUB168` 追加と競合したため、main 側の `SUB168` (下位・上位 8 byte) を残し、本 PR 側の `SUB168` を削除した (意味は同じ)。(3) `origin/main` (`396f9f8b6`・#3800 の delay ABI 規則 22 件を `patches.py` に追加) は merge commit `ecc91a700` で取り込んだ (`DOC_MAP.md` の競合は KH-43 と KH-64 の両行を残した)。(4) `origin/main` (`df2f768ea`・#3094 の `lanes` 規則を `ghidra_to_c.py` に追加。既定の `--fix` 一覧に含まれないため census は不変) は merge commit `abee0a1ff` で取り込んだ。
- 測定は (4) の HEAD (`abee0a1ff`) で取り直した。(2) の HEAD (`934c8dd71`) の census は 485 件 (引数過不足 108)、(3) で 463 件 (引数過不足 86) に変わった。差 22 件は #3800 の規則による。
- 前提: §1 と同じ素材・道具。`plugins-kilohearts` の `Kilohearts Offline Installer.zip` → `payload.dat` → `windows.zip/1ccb1df8c8f10745` → `HeartCore.core_64` 76,642,304 B。Ghidra 12.1.4 (公式 zip sha256 `ddac49f9…` 一致)、JDK 21、emcc 6.0.12 ([EMSDK])。
- decompile (挿入順の lift 集合 141 件を 10 進で渡す): **141/141 OK**。Gain/Haas/Gate の 10 関数 (`run_all.sh` [2] と同じ) は **10/10 OK**。
- emcc (`--fix bitcast,intload,stackpair,assoc,concat`・`emcc -c -ferror-limit=0`): wall 10.4 s、rc 1 (残件あり)。census は **463 件**。Win API・LOCK・MXCSR は 0 件のため表から省いた。

| 分類 | 506 (`12647936d`, §3) | 485 (`934c8dd71`) | 463 (`abee0a1ff`) |
|---|---|---|---|
| 未関数化 callee | 6 | 6 | 6 |
| レーン型 | 166 | 166 | 166 |
| 引数数不一致 | 108 | 108 | 86 |
| SIMD・AVX・swi 疑似関数 | 0 | 0 | 0 |
| code 型の間接呼出し | 21 | 0 (main #3096 で解消) | 0 |
| 未定義 identifier | 17 | 17 | 17 |
| 演算・代入の型不一致 | 186 | 186 | 186 |
| その他 | 2 | 2 | 2 |
| **合計** | **506** | **485** | **463** |

- 件数の差 (#3096 の記録との 1 件): `26b003692` の変換器・shim で同じ out141 から作った census は **555 件** (未関数化 6・レーン 190・引数 108・SIMD 46・未定義 17・型不一致 186・その他 2) で、#3096 の記録 556 (未関数化 5・レーン 191・型 187) と 1 件ずれる。原因は未特定 (`snapins/snapins.json`・`scripts/ghidra`・`emcc_census.py` は `26b003692` から HEAD まで不変。`patches.py` だけが後から変わった)。`abee0a1ff` の未関数化 6・型 186 は `26b003692` の再生成と一致する。
- 単体突合 (`simd_shim_check.c`・`gcc -O1 -mavx2`): 実装 13 種 × 200,000 試行 **mismatches: 0** (rc 0)。ネガティブコントロール (`-DKH_NEG=1`) は **mismatches: 200000** (rc 1)。
- 回帰 (`build_cmp.sh <n> 1000 7 bitcast,intload,stackpair,assoc,concat`): Gain **1000/1000** (calls 4999/4999・wasm 15,161 B)、Haas **1000/1000** (calls 5500/5500・wasm 16,878 B)、Gate **1000/1000** (calls 4999/4999・wasm 17,367 B)。wasm サイズは §4 と一致。
- 再現の注意: `build_cmp.sh` は `snapins/work/<n>/` が無いと `native_ref` が segfault する (`run_all.sh` [1] は `mkdir -p` している)。本測定では事前に作成した。
- 未実施: Delay の native 突合 (emcc が 463 件で通らないため)。#3073 の範囲。
- 測定 commit から HEAD までのコード差分: 測定 commit = `abee0a1ff` (コードを変えた最後の commit = main 取り込みの merge)。§8 執筆時点の HEAD では `git diff abee0a1ff HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` の出力は 0 行だった (この節を含む REPORT・DOC_MAP の commit は範囲外)。その後の現 head (`17f4adda2`) との差分 `abee0a1ff..17f4adda2` は 76 行で、main の #3802 の変更を含む。現 head の判定は §9。

## 9. 競合解消後の再測定 (測定 commit `ab01412df`)

- 経緯: PR #3812 が main と競合した (watchdog 依頼)。`origin/main` (`a9afb18ec`) を merge した (`ab01412df`、rebase・force push なし)。競合は `docs/DOC_MAP.md` の 1 箇所 (両側とも別行の追加。PR 側の `REPORT_APPENDIX_3095.md` 行と main 側の `REPORT_APPENDIX_3802.md`・`_3802_DIFF.md` 行を残した)。`ghidra_shim.h` は競合しない (`SUB168` は 1 定義のまま)。`ghidra_to_c.py` は自動マージ (origin/main との差分は `maxps` 行の 1 行のみ)。main 側の #3802 (`6323671e7`〜`b201ce387`) が `ghidra_route` を変えたため §8 の測定は HEAD と一致しなくなり、取り直した。
- 前提: §1 と同じ素材・道具 (Ghidra 12.1.4 公式 zip の sha256 `ddac49f9…` 一致・JDK 21・emcc 6.0.12)。`HeartCore.core_64` 76,642,304 B。
- decompile (挿入順の lift 集合 141 件・重複 1 件を除く): **141/141 OK**。Gain/Haas/Gate の 10 関数は **10/10 OK** (Ghidra wall 32 s)。
- emcc (`--fix bitcast,intload,stackpair,assoc,concat`・`emcc -c -ferror-limit=0`): wall 11.2 s、rc 1 (残件あり)。census は **441 件**。

| 分類 | 463 (`abee0a1ff`, §8) | 441 (`ab01412df`) |
|---|---|---|
| 未関数化 callee | 6 | 1 |
| レーン型 | 166 | 166 |
| 引数数不一致 | 86 | 86 |
| SIMD・AVX・swi 疑似関数 | 0 | 0 |
| code 型の間接呼出し | 0 | 0 |
| 未定義 identifier | 17 | 2 |
| 演算・代入の型不一致 | 186 | 186 |
| その他 | 2 | 0 |
| **合計** | **463** | **441** |

- 減った 22 件は、#3802 の commit `6323671e7` のメッセージ「未定義 identifier 15・未関数化 callee 5・スタブ衝突 2 を解消」と件数が合う (各分類の対応は commit 本文で確認していない)。
- 残件の名前 (emcc log): 未定義 identifier 2 = `PTR__guard_dispatch_icall_1813a1d38`・`LAB_180fd2aab`、未関数化 callee 1 = `func_0x0001802ecfc0`。§7 の「未定義 identifier 17・未関数化 callee 6・その他 2 (計 25 件)」は §8 (`abee0a1ff`) の値で、現 HEAD では 3 件。
- 単体突合 (`simd_shim_check.c`・`gcc -O1 -mavx2`): 実装 13 種 × 200,000 試行 **mismatches: 0** (rc 0)。ネガティブコントロール (`-DKH_NEG=1`) は **mismatches: 200000** (rc 1)。
- 回帰 (`build_cmp.sh <n> 1000 7 bitcast,intload,stackpair,assoc,concat`): Gain **1000/1000** (calls 4999/4999・wasm 15,161 B)、Haas **1000/1000** (calls 5500/5500・16,878 B)、Gate **1000/1000** (calls 4999/4999・17,367 B)。wasm サイズは §4・§8 と一致。
- 測定 commit から HEAD までのコード差分: 測定 commit = `ab01412df` (コードを変えた最後の commit = main 取り込みの merge)。`git diff ab01412df HEAD -- tools/targets/kilohearts/ghidra_route tools/targets/kilohearts/snapins/scripts` の出力は 0 行 (この節を含む REPORT の commit は範囲外)。
