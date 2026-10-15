# #1325 (LD-46): first-deref-not-entry の支配関係つき修復・survey 到達の再測定 — 部分達成

**判定: 部分達成**。audit 上の first-deref-not-entry 21 組 (20 関数) のうち、最初の deref の IR ブロックが置換対象の全使用を支配する **11 組を修復**した。残り 10 組は関数ごとに見送り理由を記録した (§3)。修復後の動的確認 (修復対象 11 関数の wasm 比較) は未実施で、子 issue に移した。survey 到達は再測定し JSON を添えた (§4)。

測定 commit: `f63b5953` (コードを変えた最後の commit)。コード差分の範囲と結果は §7。

## 1. 受入条件別 (縮小後)

| 受入条件 | 結果 |
|---|---|
| first-deref-not-entry を支配関係つきで修復、または関数ごとに修復不能理由を記録 | **達成** (修復 11 組・残り 10 組は理由記録。§2・§3) |
| 修復の wasm を survey で比較し、修復前後の動的挙動を記録 (7/7) | **一部**。survey の比較と 509 系の動的確認 5/5 は実施 (§5。基準は ldfix 無しの IR)。修復対象 11 関数の動的確認は未実施 → 子 issue |
| §2.1 の survey 到達数を再測定し、出力 JSON を添える | **達成** (`results/reach_1325_prev.json`・`results/reach_1325_head.json`。§4) |

## 2. 修復 (`ldfix/ldfix.py` の `fix_f3c_use`)

- 従来: 機械語の最初の deref が entry ブロック外なら見送った (`f3c_use_not_entry`)。
- 追加: 最初の deref の機械語ブロック先頭 VA に対応する IR ブロック B を求め、B が置換対象の全使用を支配するなら、B の label 直後へ `load` を挿入する (`f3c_use_dom_at`)。
  - 見送り: B の IR が無い / B に phi がある / 支配されない使用がある (`f3c_use_not_dom`)。
- 支配関係は IR の CFG から反復データフローで計算する (`ir_succ`・`ir_dominators`)。entry 内の経路は変更なし。
- 先頭 deref の位置は出所 `'arg'` の deref だけで決める (`argv` は数えない。REPORT_1324 §2 の規則を継承)。

## 3. 関数ごとの判定 (audit 上の first-deref-not-entry 21 組 = 20 関数)

列: keep = 機械語の生の使用数 / rep = 置換対象の使用数 / dom = そのうち B に支配される数。判定語は `dom_1325.py` の定義 (`results/dom_1325.json`)。「IR 変化」は正規化後 (§6) の差分。

| 関数 | 引数 | ptr | 最初の deref | B (IR) | keep/rep/dom | 判定 | IR 変化 |
|---|---|---|---|---|---|---|---|
| 40fe90 | arg1 | i64 | 40fe99 | 40fe99 | 1/1/1 | dominated | 有 |
| 41b8d0 | arg1 | i64 | 41b8de | 41b8de | 0/1/1 | dominated | 有 |
| 41b970 | arg1 | i64 | 41b97e | 41b97e | 0/1/1 | dominated | 有 |
| 449550 | arg4 | i64 | 44957e | 44957a | 1/1/1 | dominated | 有 |
| 44f040 | arg1 | i64 | 44f069 | 44f062 | 0/2/2 | dominated | 有 |
| 44fb40 | arg1 | i64 | 44fb71 | 44fb6a | 0/2/2 | dominated | 有 |
| 47ad70 | arg2 | i64 | 47ad82 | 47ad82 | 1/1/1 | dominated | 有 |
| 784ed0 | arg1 | ptr | 784f36 | 784f32 | 1/1/1 | dominated | 有 |
| 806740 | arg3 | i64 | 80678f | 806784 | 1/1/1 | dominated | 有 |
| c40420 | arg4 | i64 | c4065b | c40632 | 1/1/1 | dominated | 有 |
| f552a0 | arg1 | i64 | f552b6 | f552b4 | 1/2/2 | dominated | 有 |
| 6905f0 | arg2 | i64 | 69072a | 69071c | 4/2/2 | dominated | 無 (下記) |
| 101d180 | arg3 | i64 | 101d477 | 101d469 | 0/3/0 | rep-not-dominated | 無 |
| 10626e0 | arg3 | ptr | 1062752 | 1062752 | 1/1/0 | rep-not-dominated | 無 |
| 12f9730 | arg3 | i64 | 12f9872 | 12f986d | 0/2/1 | rep-not-dominated | 無 |
| 41a670 | arg1 | i64 | 41a6a0 | 41a69c | 2/2/0 | rep-not-dominated | 無 |
| 786d50 | arg3 | ptr | 787019 | 786fe7 | 0/1/0 | rep-not-dominated | 無 |
| 787380 | arg3 | ptr | 78753f | 787523 | 0/1/0 | rep-not-dominated | 無 |
| 1050f90 | arg2 | i64 | 1051098 | 1051070 | 3/1/- | w32 (32bit deref あり) | 無 |
| 1050f90 | arg3 | i64 | 105114c | 105112e | 3/1/- | w32 (32bit deref あり) | 無 |
| 10628d0 | arg1 | i64 | 10628d8 | (無し) | 1/2/- | no-ir-block | 無 |

- 修復 11 組 (11 関数)。
- 6905f0 arg2: 支配は成立するが、全パスを通した実行では IR が変わらない。本体 `Machine` では最初の deref の後に生の使用が 3 件あり (`raw-after`)、門 (b) で置換されないと読める。前段パスとの相互作用は確認していない (本節の初版の説明は取り下げ)。訂正は REPORT_3195 §3。
- rep-not-dominated 6 組: 置換対象の使用が B に支配されない。B 以外からの経路で値を使う形で、単純な B 先頭の load では表せない (未解決 U-2)。
- w32 2 組・no-ir-block 1 組: 既存の門 (64bit 限定) と IR の対応が取れない (未解決 U-2)。

全体 (fix の母集団 = 出所 `'arg'` の deref を持つ非 entry の (関数, 引数) 487 組、`dom_1325.py`): dominated 12 / rep-not-dominated 6 / raw-after 445 / w32 10 / no-rep-use 12 / no-ir-block 2。audit 外で内容が変わるのは c62780 のみ (§6)。

## 4. survey 到達の再測定 (`ldfix/reach_509.sh`、対象 23 関数 = REPORT_930 §3 の一覧、942 unit)

| 関数 | 修復前 (origin/main `56bfc979`) unit / 入口通過 | 修復後 (`f63b5953`) unit / 入口通過 | 実行 unit (先頭) |
|---|---|---|---|
| 40fe90 | 2 / 6 | 2 / 8 | 745 895 |
| 44f040 | 3 / 3 | 3 / 3 | 144 158 280 |
| 47ad70 | 7 / 15 | 7 / 15 | 95 101 114 291 296 302 304 |
| 他 20 関数 | 0 / 0 | 0 / 0 | — |

- 到達 (入口に hit) は修復前後で同じ 3 関数・同じ unit 集合。kind=ok で入口に hit するのは 44f040 (unit 158) と 47ad70 (unit 95・101・291・296・302・304)。40fe90 は kind=ok で hit せず、oob (unit 745) と halt0 (unit 895) だけ。入口通過の総数は 40fe90 だけ 6 → 8 (unit 745 の oob 4 → 6 回)。
- REPORT_930 §3 は 47ad70 の kind=ok を 5 unit / 入口通過 10 としている。本表 (同じ 942 unit・本 PR の reach 実行) は 6 unit / 14 hit。REPORT_930 は別の IR で測った記録なので直さない。差の原因は未確認。本 REPORT では本表の JSON を採る。
- JSON: `results/reach_1325_prev.json`・`results/reach_1325_head.json` (各 942 行、`{unit, kind, hits}`)。`hits` のキーは下の VA 列の 0 始まり添字 (5 = 40fe90、9 = 44f040、11 = 47ad70)。
- VA 列 (23 関数、VA 昇順 = REPORT_930 §3 の並び):
  `101d180,1050f90,10626e0,10628d0,12f9730,40fe90,41b8d0,41b970,449550,44f040,44fb40,47ad70,5c44b0,6905f0,75a180,784ed0,786d50,787380,c40420,db6480,dc27c0,ddd4d0,f552a0`
- 実行: `EMSDK_ENV=<[EMSDK] の emsdk_env.sh> bash tools/m11/ldfix/reach_509.sh <上の VA 列> results/reach_1325_head.json` (IR は既定の `$M11_WORK/boot_final3.ll` = 修復後)。prev は IR だけを `56bfc979` の `ldfix.py` で作った boot_final3.ll に替える (`IR=<prev の boot_final3.ll>`)。本 run では再実行していない (work-m11 が無い)。

## 5. survey・動的確認 (`ldfix/ldfix_509_e2e.sh`、commit `f63b5953`、`PREV_REF=56bfc979`)

- 実行: foreground 1 回・rc 0・3 分 47 秒・load 0.12 (開始)。出力 `$RUNNER_TEMP/ldfix_509_e2e` 配下 (コミットなし)。
- 基準 (修復前 wasm): step 1 の `M11_LDFIX=0` で生成した IR (ldfix を一切かけない) を `M11_ALLOW_LDFIX_DISABLED=1` で build した wasm。修復後 wasm: 同じ IR に HEAD の `ldfix.py` を適用した wasm (`ldfix=applied`)。下の 7/7 の PASS 変化は、main に既にある ldfix (#509 までの修復) を含む全体の効果で、本 PR の増分 (`56bfc979` 版との差) ではない。
- 2/7 (IR): 旧版 (`56bfc979`) と新版 (HEAD) の出力を同じ修復前 IR に適用して比べた。関数単位の差分は §6 (boot_final3 入力) に記録する。手元 run の `[overlay]` 件数は本 REPORT に内訳が無いため採らない。
- 6/7 (survey 942 unit): 修復なし (ldfix 無効) → `f63b5953`: ok 870 → 872。**ok 退行 unit 0**。kind 以外を含む記録差 14 unit (A と B の比較で、修復の効果を含む)。
- 6/7 (修復の効果だけ): 修復前 `56bfc979` の wasm と `f63b5953` の wasm は別物 (sha256 `59e58e29…` と `bbed05ed…`)。survey の unit 記録差は **0** (ok 872 = 872)。到達 3 関数は §4 の通り。
- 7/7 (`dyn_509.mjs`・509 系 5 関数): 基準 (ldfix 無し) の wasm で FAIL 5/5 → 修復後 PASS 5/5 (c62780・7e5240・409c80・41a670・1063090)。この 5 関数は本 issue の修復対象 (§3) ではない。7e5240・409c80・41a670・1063090 は §6 の IR 変化の対象外なので、PASS は main の ldfix (#509 の store 形 fix) による。c62780 だけが §6 の名前の差分を持つ (ldfxn 採番のずれと推定、U-4)。よって 5/5 の PASS は本 PR の増分の証拠にならない。
- 本 issue の修復対象 11 関数の動的確認 (修復前後の直接呼び出し) は **未実施**。survey で到達するのは 3 関数だけで、残りは survey からは判定できない → 子 issue。
- **#4039 (2026-10-15) の追記**: 測定 commit `f07ef8dc9` (`ldfix_509_e2e.sh` の NC 期待値と `dyn_509.mjs` の 47ad70 期待値を補った commit)。foreground 1 回・rc 0・real 6 分 55.8 秒・load 開始 0.44 / 終了 1.00 (uptime の 1 分平均)。素材は `work-m11` / `fl-win64` (PE のみ) / `toolchain-emsdk` を展開して実行。
  - 旧版 NC: store 形 SUSPECT 8 関数 / 11 site (806740 を含む)。nc_store: 806740 を 1 件検出。nc_use: 1063090 を use 形で検出。NC 期待値は `grep` の条件を「旧版は 806740 を store 形で検出する」に直した (前 HEAD は「旧版は store 0」を要求し、正しい挙動を失敗扱いしていた)。
  - survey: ok 871 → 873、ok 退行 unit 0、記録差 14 unit (§5 の 6/7 と同じ)。
  - 7/7 `dyn_509.mjs`: 修復前 FAIL → 修復後 PASS が c62780・7e5240・409c80・41a670・1063090 の 5 件。ただし修復対象 (11 関数 + c62780) に入るのは **c62780 の 1 件だけ**。7e5240・409c80・41a670・1063090 は対象外で、PASS は main 由来 (本 PR の増分の証拠にならない)。**47ad70 は修復対象だが修復前後とも FAIL (`KNOWN`)**: 機械語 `mov rdx,[rcx]` (配列基点 = `*arg1`) が IR で落ち、IR は `%arg1` を配列の基点に使う。修復 (`fix_f3c_use`) は value 側 (`*arg2`) だけを直しており、配列側は未修復。`DYN_SUMMARY after_fail=0/5 known=1`。`known` 行は #4439 で 47ad70 が PASS になったら外す。
  - 対象 11 関数 + c62780 のうち、本 PR で PASS を確認できたのは c62780 の 1 件。47ad70 は known FAIL。残り 10 関数 (40fe90・41b8d0・41b970・449550・44f040・44fb40・784ed0・806740・c40420・f552a0) は未実施 (#4438)。期待値は、呼び先 (`410010`・`410820`・`4109f0`・`40f910`・`44aeb0`・`420530`・`4203d0` ほか) の機械語を読まないと決まらない。本 run では推定で期待値を書かない。
- **#4041 の現 head 再測定** (測定 commit `adf298d3b`、`PREV_REF=56bfc979`、`FL_WIN64_DIR`・`EMSDK_ENV`・`M11_WORK` を指定、`timeout 1500` 付きで foreground 1 回・この run の素材 `fl-win64` / `work-m11` / `toolchain-emsdk` を展開して実行): rc 0・real 7m30.97s (451 秒)・load 開始 0.70 / 終了 1.53 (uptime の 1 分平均)。
  - 2/7: 旧版/新版で本体が異なる関数 33 / 7421 (旧版の関数外テキストは一致、report の f3c 以外のキー差 0)。F3c 関数 旧 36 → 新 46 (旧の全てを含む)。
  - 4/7: `boot_final.ll` へ F3c を重ねた結果 F3c=43、overlay 43 件、うち新版出力と alloca 行を除いて同一 43。
  - 5/7 NC: 旧版は store 形 0・use 形 (pure) 23 関数 (1063090 を含まない) と記録した。ただし同じ旧版 (`PREV_REF=56bfc979`) の測定 `f07ef8dc9` (上の追記) は store 形 8 関数 / 11 site (806740 を含む) で、両者は食い違う。この 0 / 23 の値は REPORT_2144 の ldfix 適用後 (post: SUSPECT_VAS 0・SUSPECT_USE_VAS 23) と一致し、ldfix 無し (pre: store 8・use 52) とは一致しない。そのため「旧版」の行が適用後の IR を指していた可能性がある (推定。出力 `nc_prev.txt` が残っておらず未確認)。どちらの測定が正しいかは未確定 (PR 本文の未解決表)。nc_store は 806740 を store 1 件検出 (use 形 14、1063090 を含まない)。nc_use は 1063090 を use 形で検出 (use 形 14)。
  - 6/7 survey: 942 unit、instrumented 26 関数。ok 退行 unit 0。kind 以外も含む記録差 14 unit `[114, 144, 158, 280, 291, 296, 302, 304, 314, 493, 659, 880, 888, 895]` (reviewer の再実行 `adf298d3b` と同一)。
  - 7/7: `DYN_SUMMARY after_fail=0/5` (c62780・7e5240・409c80・41a670・1063090 がすべて before FAIL → after PASS)。
- **#4041 の再測定** (測定 commit `5e17a9229`、`PREV_REF=56bfc979`、`FL_WIN64_DIR`・`EMSDK_ENV`・`M11_WORK` を指定して `ldfix_509_e2e.sh` を foreground 1 回): rc 0・real 432 秒・load 開始 0.19 / 終了 1.00。step 2〜7 完走、7/7 `DYN_SUMMARY after_fail=0/5`。survey の記録差は 14 unit (`[114, 144, 158, 280, 291, 296, 302, 304, 314, 493, 659, 880, 888, 895]`。§5 の上の 2 段と同じ母集団)。NC は 806740 の store と 1063090 の use を各 1 件検出 (「旧版 store 0」は 91 行目と同じ未確定の測定で、`f07ef8dc9` の旧版 store 8 関数と食い違う)。

| 直した不具合 (issue #4041) | 状況 |
|---|---|
| 1. 旧版の `ldframe.py` 欠落 (`ModuleNotFoundError`) | `git archive PREV_REF tools/m11/ldfix` で旧版 ldfix 一式を取り出す。`009e823` の ldfix.py は ldframe を import しないので、`PREV_REF=56bfc979` 以降で必要。 |
| 2. `"$CFG"` の glob が複数引数になる | **この HEAD では再現せず**。`ldfix_img.py` は `CFG` を 1 引数で受け、`ldmach_img` が `glob` する。挙動は変えていない。 |
| 3. 修復後 wasm の `r8b`・`ld115` 未記録で build 拒否 | 修復後経路で `r8b=disabled ld115=disabled` を記録し、`M11_ALLOW_R8B_DISABLED=1 M11_ALLOW_LD115_DISABLED=1` を付けた (A/B の差を ldfix だけに揃える)。 |
| (付随) NC の失敗が rc 0 で隠れていた | NC の期待値 (806740 の store・1063090 の use を検出、旧版は store 0) を assert し、失敗は rc に反映する。NC の 806740 は新版で use 側 `ldfxu` になるため、正規表現を `ldfx[nu]` に広げた。 |

## 6. IR 差分の読み方

- `ldfxu%d` の SSA 名は関数をまたいで通し番号のため、修復が増えると後続関数の名前だけが変わる。HEAD 版と修正版の関数単位の生差分は 33 関数だが、名前 (`ldfxu\d+`) を正規化すると内容が変わったのは **12 関数**: 修復対象 11 組の関数 (40fe90・41b8d0・41b970・449550・44f040・44fb40・47ad70・784ed0・806740・c40420・f552a0) と c62780。
- 入力 `work/boot_final3.ll` (修復前 IR 相当): F3c 関数 33 → 43、`f3c_use_dom` 11 組、`f3c_use_not_dom` 7 組、`f3c_use_replaced` 66 → 80、`f3c_fn_stores` 10 → 9、errors 0。数値の出典は §7 の再現コマンドの手元 run の出力 (コミットなし)。
- 入力 `work/boot_final.ll` (gen の修復前 IR): F3c 36 → 46 (手元 run の `ldfix_report.json`、コミットなし)。
- `f3c_use_replaced` の +14 は、§3 の 11 組の rep の和 (1+1+1+1+2+2+1+1+1+1+2 = 14) と一致する。c62780 は置換の対象ではない。
- **`f3c_fn_stores 10 → 9`**: 外れたのは 806740 の store 形 1 site。REPORT_484 の `store i64 %arg3` (機械語 806792) で、§3 の 806740 (rep 1/1/1) の唯一の使用に当たる。`fix_f3c_use` がこれを先に `load` の値へ置換するため、`fix_f3c_fn` の候補 (`f3c_ir_stores` は `store %argN` だけを拾う) から外れる。store 形の内訳 (409c80 1・41a670 1・5c0270 2・66e080 3・7e5240 1・806740 1・c62780 1 = 10) の 806740 が 1 減った。意図した経路であり、回帰とは見ていない (推定)。
- ただし、置換後の load は B の先頭 (最初の deref より前) に置き、旧形 (`fix_f3c_fn`) は store の直前に置く。B の先頭から最初の deref までに、同じ先を書く store・call が無いことは未確認 (U-3)。806740 は REPORT_509 で unexec (native 側が NULL deref) のため、動的確認もできない。
- **#4421: 間接 call を含む B の除外** (`f3c_indirect_call_before`・測定 commit `dcb46250c`): 最初の deref より前 (B の先頭から) に、呼出先が即値でない call があれば置換しない (`f3c_use_indirect_call`)。対象は c40420 (§9 の唯一の該当)。入力 `work/boot_final3.ll`: 除外前 `f3c_use_replaced` 80・`f3c_use_dom` 11・`F3c` 43 → 除外後 79・10・42 (`f3c_use_indirect_call` 1)。修復 site 数は 11 → 10 組。正規化後に IR が変わった関数は c40420 のみ (`ldfx[nu]\d+` 正規化・手元比較)。c40420 の本体に `ldfx` 行は残らない (`ldfix_509_e2e.sh` の [c40420] assert)。
  - e2e (`ldfix_509_e2e.sh`、測定 commit `dcb46250c`、`PREV_REF=56bfc979`、foreground 1 回): rc 0・real 434 秒・終了時 load 1.01 (開始時は未採取)。`[c40420] 新版 IR に修復 load 無し`。survey: 基準 (ldfix 無し) ok 871 → 修復後 ok 873 (同一 run の比較)、ok 退行 0、記録差 14 unit (前 run と同じ集合)。7/7 `DYN_SUMMARY after_fail=0/5`。
  - 単体: `test_f3c_indirect_4421.py` 5/5 PASS。判定関数を壊すと 2 件 FAIL (mutation)。
  - 除外の効果 (c40420 の差) だけを切り出した survey は取っていない。survey の ok 増 2 件 (unit 158・493) は本変更の効果と断定しない。
- **c62780 の差分 (U-4 確認済み, #4041)**: `fix_f3c_fn` の SSA 名 `ldfxn%d` は `ctr_f3cn` (プロセス内で関数をまたぐ通し番号) で採番される。`ldfxn\d+` を `LDFXN` に正規化すると、c62780 の旧版 (`56bfc979`) と新版 (HEAD) の本体は**完全一致**する (md5 一致。新版に `ldfxu` は無い)。採番のずれ (推定) は正しかった。根拠 (`$RUNNER_TEMP/ldfix_509_e2e/{prev,new}.ll` の `function_c62780` 定義行を抽出し `re.sub(r'ldfxn\d+','LDFXN',…)` 後に md5): 旧版 `694f8999609b4c0e4a51692f71b65e6b`・新版 `694f8999609b4c0e4a51692f71b65e6b` (一致)。正規化前は `a0d59b9a…` と `4cafc0d0…` で不一致。
- **§6 の全関数の差分 (#4041 で追加確認)**: `ldfx[nu]\d+` を正規化しても、新旧の IR 全体は一致しない (50 行)。残る差分は F3c の件数増 (36→46) による関数の本体変化 (`ldfx` の挿入行) で、採番のずれではない。806740 は旧版では fn 側 (`ldfxn9`)、新版では use 側 (`ldfxu32`) で同じ修復が入る。§6 の正規化対象に `ldfxn` を足しても、33 関数の差分は消えない。

## 7. 再現・測定 commit

```
cd tools/m11
python3 ldfix/dom_1325.py ldfix/results/dom_1325.json           # §3 (約 25 秒)
python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe work/extracted/block00031_PE.bin --report out.json   # §6 (約 35 秒)
cd .. && PREV_REF=56bfc979 EMSDK_ENV=<[EMSDK] の emsdk_env.sh> PE=<block00031_PE.bin> bash tools/m11/ldfix/ldfix_509_e2e.sh   # §5
```

入力: `tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst` (`tools/m11/work/`)・`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/m11/work extracted/block00031_PE.bin`・`tar --zstd -xf $ARTIFACTS_DIR/toolchain-emsdk.tar.zst`。

- 測定 commit `f63b5953` からのコード差分: e2e 一式 (`ldfix.py`・`dom_1325.py`・`ldfix_509_e2e.sh`・`reach_509.sh`・`dyn_509.mjs`・`audit_lsf.py`・`ldmach.py`・`ldmach_img.py`・`ldfix_img.py`・`m11_build.sh`・`m11_gen_ir2.sh`・`m11_cond.py`・`lb_base.py`・`trap_triage`・`tools/shim`・`tools/shared`) を `git diff --stat f63b5953 HEAD -- <上の pathspec>` で見ると、コード 0 行。`tools/shared` の差分は REPORT md 2 件 (`oss/blend2d/REPORT_AGG2D.md`・`REPORT_APPENDIX_AGG2D.md`、main 取り込み) の 54 行の追加のみ。
- `tools/m11/ldfix` 全体の差分は、本 REPORT・`REPORT_2688.md`・`f3d_9site_2688.sh`・`results/candidate_verdicts_2688.jsonl` (main 取り込みの #2688) と `results/reach_1325_{prev,head}.json`。e2e はこれらを呼ばない。
- prev (`56bfc979`) と修正版の比較は、修正版の commit 前の作業ツリー (`ldfix.py` の内容は commit と同一) で実施。§4 の prev の到達は `56bfc979` の `ldfix.py` を `git show` で入れた同じビルド手順で測定。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U-1 修復対象 11 関数と c62780 の動的確認 (修復前後の直接呼び出し・7/7 相当) | 修復の正しさが survey の到達 3 関数以外では確かめられていない | #3194 (LD-148) |
| U-2 支配されない 6 組・w32 2 組・no-ir-block 1 組の修復 (6905f0 は理由の訂正のみ・REPORT_3195 §3) | 11 組の修復のみ。残りは現状のまま | #3195 (LD-149) で不能理由を記録 (REPORT_3195 §2)。修復の設計は PM 判断 (未起票) |
| U-3 B 先頭の load 配置の安全性: §9 の機械語確認で、10 組は同じ先を書く store・call が無いことを確認。c40420 は間接 call を含むため #4421 で置換を除外 (§6)。即値の直接 call (806740) は除外の対象外 | 間接 call を含む関数の修復は今後も対象外。呼出先の特定 (#4069 の残件) は未実施 | #4069 (LD-190) |
| U-4 は #4041 で解消 (c62780 は `ldfxn\d+` 正規化で一致。§6)。全関数の一致は 33 関数の F3c 件数増による本体変化のため、採番だけでは一致しない | — | — |
| `REPORT_930` の 23/24 と 30/33 の不一致、および 47ad70 の kind=ok 5 と 6 の差 | 分類の母集団・IR の差 (本 REPORT の 21 組は `audit_509_pre.json` 基準) | #1134 (既存) |

## 9. U-3 機械語確認 (#4040)

- 対象: 修復 11 site。B の先頭から最初の deref (`fix_f3c_use` の先頭 deref VA) の直前までの命令を、PE (`block00031_PE.bin`) から逆アセンブルした。判定は `ldfix/u3_check_4040.py` (`call`・メモリ書込・`lock`/`rep` の数)。
- 結果:

| 関数 | B | 最初の deref | call | 書込 | 判定 |
|---|---|---|---|---|---|
| 40fe90 | 40fe99 | 40fe99 | 0 | 0 | 問題なし (B 先頭が deref) |
| 41b8d0 | 41b8de | 41b8de | 0 | 0 | 問題なし (B 先頭が deref) |
| 41b970 | 41b97e | 41b97e | 0 | 0 | 問題なし (B 先頭が deref) |
| 449550 | 44957a | 44957e | 0 | 0 | 問題なし |
| 44f040 | 44f062 | 44f069 | 0 | 0 | 問題なし |
| 44fb40 | 44fb6a | 44fb71 | 0 | 0 | 問題なし |
| 47ad70 | 47ad82 | 47ad82 | 0 | 0 | 問題なし (B 先頭が deref) |
| 784ed0 | 784f32 | 784f36 | 0 | 0 | 問題なし |
| 806740 | 806784 | 80678f | 1 (`call 0x806820`) | 0 (呼出先の書込は下記) | 問題なし (下記) |
| c40420 | c40632 | c4065b | 1 (間接 `call [slot]`) | 1 (`mov [rsi+0x14], 0` 等) | **見直し要 (#4069)** |
| f552a0 | f552b4 | f552b6 | 0 | 0 | 問題なし |

- 806740: 間の `call 0x806820` が書くのは `this+0x6ac`〜`0x6d0` と `this+0x6c8` (`rcx` 基準)。置換対象の deref 先は呼出元のスタック上の引数 (`rdx`/`r8` 経由)。5 つの呼出元 (0xc81f39・0xf0c0bb・0xf0c14e・0xf61bc9・0x1038e61) の `r8` はいずれも `rbp` 基準のスタック局所で、`this+0x6ac` 系とは重ならない。
- c40420: 最初の deref (0xc4065b) より前に、`call qword ptr [0x15e1908]` (`.data` の slot、中身は `.bss` の VA `0x16b8360` を指す実行時ポインタ) がある。呼出先が静的に決まらず、同じ先を書くかを否定できない。`mov [rsi+0x14], 0` 等の store も同じ区間にある。
- 残件: c40420 の呼出先の特定と、修復の見直し要否の判定は #4069 (LD-190)。
- 動的確認は未実施 (この確認は機械語の静的読みのみ)。
