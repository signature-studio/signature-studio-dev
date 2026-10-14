# #1325 (LD-46): first-deref-not-entry の支配関係つき修復・survey 到達の再測定 — 部分達成

**判定: 部分達成**。audit 上の first-deref-not-entry 21 組 (19 関数) のうち、最初の deref の IR ブロックが置換対象の全使用を支配する **11 組を修復**した。残り 10 組は関数ごとに見送り理由を記録した (§3)。修復後の動的確認 (修復対象 12 関数の wasm 比較) は未実施で、子 issue に移した。survey 到達は再測定し JSON を添えた (§4)。

測定 commit: `f63b5953` (コードを変えた最後の commit)。`git diff f63b5953 HEAD -- tools/m11/ldfix` は本 REPORT の commit 以外のコード差分 0 (§7)。

## 1. 受入条件別 (縮小後)

| 受入条件 | 結果 |
|---|---|
| first-deref-not-entry を支配関係つきで修復、または関数ごとに修復不能理由を記録 | **達成** (修復 11 組・残り 10 組は理由記録。§2・§3) |
| 修復の wasm を survey で比較し、修復前後の動的挙動を記録 (7/7) | **一部**。survey の比較と 509 系の動的確認 5/5 は実施 (§5)。修復対象 12 関数の動的確認は未実施 → 子 issue |
| §2.1 の survey 到達数を再測定し、出力 JSON を添える | **達成** (`results/reach_1325_prev.json`・`results/reach_1325_head.json`。§4) |

## 2. 修復 (`ldfix/ldfix.py` の `fix_f3c_use`)

- 従来: 機械語の最初の deref が entry ブロック外なら見送った (`f3c_use_not_entry`)。
- 追加: 最初の deref の機械語ブロック先頭 VA に対応する IR ブロック B を求め、B が置換対象の全使用を支配するなら、B の label 直後へ `load` を挿入する (`f3c_use_dom_at`)。
  - 見送り: B の IR が無い / B に phi がある / 支配されない使用がある (`f3c_use_not_dom`)。
- 支配関係は IR の CFG から反復データフローで計算する (`ir_succ`・`ir_dominators`)。entry 内の経路は変更なし。
- 先頭 deref の位置は出所 `'arg'` の deref だけで決める (`argv` は数えない。REPORT_1324 §2 の規則を継承)。

## 3. 関数ごとの判定 (audit 上の first-deref-not-entry 21 組)

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
- 6905f0 arg2: 支配は成立するが、全パスを通した実行では IR が変わらない。`fix_f3c_use` 単独 (前段パス無し) では修復される。前段パスとの相互作用は未切り分け (未解決 U-1)。
- rep-not-dominated 6 組: 置換対象の使用が B に支配されない。B 以外からの経路で値を使う形で、単純な B 先頭の load では表せない (未解決 U-2)。
- w32 2 組・no-ir-block 1 組: 既存の門 (64bit 限定) と IR の対応が取れない (未解決 U-2)。

全体 (fix の母集団 = 出所 `'arg'` の deref を持つ非 entry の (関数, 引数) 487 組、`dom_1325.py`): dominated 12 / rep-not-dominated 6 / raw-after 445 / w32 10 / no-rep-use 12 / no-ir-block 2。audit 外の修復は 1 組 (c62780・§6)。

## 4. survey 到達の再測定 (`ldfix/reach_509.sh`、対象 23 関数 = REPORT_930 §3 の一覧、942 unit)

| 関数 | 修復前 (origin/main `56bfc979`) unit / 入口通過 | 修復後 (`f63b5953`) unit / 入口通過 | 実行 unit (先頭) |
|---|---|---|---|
| 40fe90 | 2 / 6 | 2 / 8 | 745 895 |
| 44f040 | 3 / 3 | 3 / 3 | 144 158 280 |
| 47ad70 | 7 / 15 | 7 / 15 | 95 101 114 291 296 302 304 |
| 他 20 関数 | 0 / 0 | 0 / 0 | — |

- 到達 (kind=ok で入口に hit) は修復前後で同じ 3 関数・同じ unit。入口通過の総数は 40fe90 だけ 6 → 8。
- JSON: `results/reach_1325_prev.json`・`results/reach_1325_head.json` (対象 23 関数の計装付き survey、942 unit)。

## 5. survey・動的確認 (`ldfix/ldfix_509_e2e.sh`、commit `f63b5953`、`PREV_REF=56bfc979`)

- 実行: foreground 1 回・rc 0・3 分 47 秒・load 0.12 (開始)。出力 `$RUNNER_TEMP/ldfix_509_e2e` 配下。
- 2/7 (IR): 修復前 IR に対する ldfix の出力。`[overlay]` は boot_final.ll から変わった 43 関数すべてが、新版出力と alloca 行を除いて一致 (件数の内訳は §6)。
- 6/7 (survey 942 unit): 修復なし (ldfix 無効) → `f63b5953`: ok 870 → 872。**ok 退行 unit 0**。kind 以外を含む記録差 14 unit (A と B の比較で、修復の効果を含む)。
- 6/7 (修復の効果だけ): 修復前 `56bfc979` の wasm と `f63b5953` の wasm は別物 (sha256 `59e58e29…` と `bbed05ed…`)。survey の unit 記録差は **0** (ok 872 = 872)。到達 3 関数は §4 の通り。
- 7/7 (`dyn_509.mjs`・509 系 5 関数): 修復前 FAIL 5/5 → 修復後 **PASS 5/5** (c62780・7e5240・409c80・41a670・1063090)。ただし、この 5 関数は本 issue の修復対象 (§3) ではない。c62780 は audit 外で内容が変わった関数 (§6)。
- 本 issue の修復対象 12 関数の動的確認 (修復前後の直接呼び出し) は **未実施**。survey で到達するのは 3 関数だけで、残りは survey からは判定できない → 子 issue。

## 6. IR 差分の読み方

- `ldfxu%d` の SSA 名は関数をまたいで通し番号のため、修復が増えると後続関数の名前だけが変わる。HEAD 版と修正版の関数単位の生差分は 33 関数だが、名前 (`ldfxu\d+`) を正規化すると内容が変わったのは **12 関数**: 修復対象 11 組の関数 (40fe90・41b8d0・41b970・449550・44f040・44fb40・47ad70・784ed0・806740・c40420・f552a0) と c62780。
- 入力 `work/boot_final3.ll` (修復前 IR 相当): F3c 関数 33 → 43、`f3c_use_dom` 11 組、`f3c_use_not_dom` 7 組、`f3c_use_replaced` 66 → 80、`f3c_fn_stores` 10 → 9、errors 0。
- 入力 `work/boot_final.ll` (gen の修復前 IR): F3c 36 → 46 (`ldfix_report.json`)。

## 7. 再現・測定 commit

```
cd tools/m11
python3 ldfix/dom_1325.py ldfix/results/dom_1325.json           # §3 (約 25 秒)
python3 ldfix/ldfix.py work/boot_final3.ll out.ll --pe work/extracted/block00031_PE.bin --report out.json   # §6 (約 35 秒)
cd .. && PREV_REF=56bfc979 EMSDK_ENV=<[EMSDK] の emsdk_env.sh> PE=<block00031_PE.bin> bash tools/m11/ldfix/ldfix_509_e2e.sh   # §5
```

入力: `tar --zstd -xf $ARTIFACTS_DIR/work-m11.tar.zst` (`tools/m11/work/`)・`tar --zstd -xf $ARTIFACTS_DIR/fl-win64.tar.zst -C tools/m11/work extracted/block00031_PE.bin`・`tar --zstd -xf $ARTIFACTS_DIR/toolchain-emsdk.tar.zst`。

- 測定 commit `f63b5953` のコード差分: `git diff f63b5953 HEAD -- tools/m11/ldfix` (本 REPORT の commit のみ)。
- prev (`56bfc979`) と修正版の比較は、修正版の commit 前の作業ツリー (`ldfix.py` の内容は commit と同一) で実施。§4 の prev の到達は `56bfc979` の `ldfix.py` を `git show` で入れた同じビルド手順で測定。

## 8. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| U-1 修復対象 12 関数の動的確認 (修復前後の直接呼び出し・7/7 相当) | 修復の正しさが survey の到達 3 関数以外では確かめられていない | #3194 (LD-148) |
| U-2 支配されない 6 組・w32 2 組・no-ir-block 1 組・6905f0 (支配は成立するが前段パスとの相互作用で未変化) の修復 | 11 組の修復のみ。残りは現状のまま | #3195 (LD-149) |
| `REPORT_930` の 23/24 と 30/33 の不一致 | 分類の母集団の差 (本 REPORT の 21 組は `audit_509_pre.json` 基準) | #1134 (既存) |
