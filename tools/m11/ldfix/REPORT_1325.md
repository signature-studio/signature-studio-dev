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
- 6905f0 arg2: 支配は成立するが、全パスを通した実行では IR が変わらない。`fix_f3c_use` 単独 (前段パス無し) では修復される。前段パスとの相互作用は未切り分け (未解決 U-2)。
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

## 6. IR 差分の読み方

- `ldfxu%d` の SSA 名は関数をまたいで通し番号のため、修復が増えると後続関数の名前だけが変わる。HEAD 版と修正版の関数単位の生差分は 33 関数だが、名前 (`ldfxu\d+`) を正規化すると内容が変わったのは **12 関数**: 修復対象 11 組の関数 (40fe90・41b8d0・41b970・449550・44f040・44fb40・47ad70・784ed0・806740・c40420・f552a0) と c62780。
- 入力 `work/boot_final3.ll` (修復前 IR 相当): F3c 関数 33 → 43、`f3c_use_dom` 11 組、`f3c_use_not_dom` 7 組、`f3c_use_replaced` 66 → 80、`f3c_fn_stores` 10 → 9、errors 0。数値の出典は §7 の再現コマンドの手元 run の出力 (コミットなし)。
- 入力 `work/boot_final.ll` (gen の修復前 IR): F3c 36 → 46 (手元 run の `ldfix_report.json`、コミットなし)。
- `f3c_use_replaced` の +14 は、§3 の 11 組の rep の和 (1+1+1+1+2+2+1+1+1+1+2 = 14) と一致する。c62780 は置換の対象ではない。
- **`f3c_fn_stores 10 → 9`**: 外れたのは 806740 の store 形 1 site。REPORT_484 の `store i64 %arg3` (機械語 806792) で、§3 の 806740 (rep 1/1/1) の唯一の使用に当たる。`fix_f3c_use` がこれを先に `load` の値へ置換するため、`fix_f3c_fn` の候補 (`f3c_ir_stores` は `store %argN` だけを拾う) から外れる。store 形の内訳 (409c80 1・41a670 1・5c0270 2・66e080 3・7e5240 1・806740 1・c62780 1 = 10) の 806740 が 1 減った。意図した経路であり、回帰とは見ていない (推定)。
- ただし、置換後の load は B の先頭 (最初の deref より前) に置き、旧形 (`fix_f3c_fn`) は store の直前に置く。B の先頭から最初の deref までに、同じ先を書く store・call が無いことは未確認 (U-3)。806740 は REPORT_509 で unexec (native 側が NULL deref) のため、動的確認もできない。
- **c62780 の差分**: `fix_f3c_fn` の SSA 名 `ldfxn%d` は `ctr_f3cn` (プロセス内で関数をまたぐ通し番号) で採番される。806740 の候補が 1 つ減ると、後続の store 形の関数の採番が 1 つずれる。store 形の関数で 806740 より後の VA にあるのは c62780 だけ (IR の定義順が VA 昇順であることを仮定)。§6 の正規化は `ldfxu\d+` だけなので、c62780 が名前の差分として残る。`ldfxn\d+` も正規化して一致することは work-m11 が無いため未確認 (U-4)。

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
| U-2 支配されない 6 組・w32 2 組・no-ir-block 1 組・6905f0 (支配は成立するが前段パスとの相互作用で未変化) の修復 | 11 組の修復のみ。残りは現状のまま | #3195 (LD-149) |
| U-3 B 先頭の load 配置の安全性: B の先頭から最初の deref までに、同じ先を書く store・call が無いことの確認 (806740 は unexec で動的確認不可) | 11 組の修復値が機械語と一致するかが未確認 | #3194 (LD-148) |
| U-4 c62780 の名前だけの差分 (`ldfxn` 採番) の確認: `ldfxn\d+` も正規化して HEAD と prev の IR が一致するか | §6 の c62780 の説明は推定のまま | #3194 (LD-148) |
| `REPORT_930` の 23/24 と 30/33 の不一致、および 47ad70 の kind=ok 5 と 6 の差 | 分類の母集団・IR の差 (本 REPORT の 21 組は `audit_509_pre.json` 基準) | #1134 (既存) |
