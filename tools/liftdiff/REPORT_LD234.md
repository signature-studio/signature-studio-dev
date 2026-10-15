# REPORT_LD234 — liftdiff_e2e.sh --m11-only の所要時間・load・[4/4] 結果の実測 (#4667)

親: #4429 (LD-215)。LD-215 の `[4/4]` (sample:800) は時間上限のため所要時間を取れなかった。本 REPORT は、そこを実測で埋める。

## 1. 結論

- `FL_WIN64_DIR=<展開先> bash tools/liftdiff/liftdiff_e2e.sh --m11-only` の有効な単独 run は 2 回。
  - run 2: 専用 worktree (commit `fbb19946c`)。`LIFTDIFF_E2E PASS`、rc 0。ただし run 2 の端末ログは保存されていない (§6)。
  - run 3: 専用 worktree (commit `fbb19946c`、detached)。`LIFTDIFF_E2E PASS`、rc 0、実時間 **206 s**。round 3 の差し戻しを受けて再測定した。
  - run 1 は共有 main チェックアウトでの実行 (WORKFLOW §1-1 違反)。有効な測定には数えず、参考値として残す。
- 所要時間 (run 3): real **206 s**。`[4/4]` バッチ単体は **125 s** (run 2 は 116 s)。
- `[4/4]` の件数は run 2・run 3 で同一: **801 関数 = 一致 360 / 不一致 235 / 実行不能 206**。
- ただし timeout/hang/crash を含む case の件数は run 間で揺れる (§4・§6)。run 3 は **326 (関数 74)**。
- 測定 commit は **`fbb19946c`** (main)。run 3 の HEAD までの `tools/liftdiff` 差分は REPORT 追加のみ (§5)。

## 2. 測定条件

- 測定 commit: `fbb19946c` (`Merge pull request #4649`)。コードは変更していない。
- 素材 (run 3): `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff` を `$ARTIFACTS_DIR` で実在確認した上で、次のとおり使った。
  - `fl-win64` は `$RUNNER_TEMP/fl-win64` に展開し、`FL_WIN64_DIR` に指定した。
  - `work-m11`・`work-liftdiff` は測定 worktree の `tools/m11/work/`・`tools/liftdiff/work/` に展開した (gitignore 対象)。
  - `toolchain-emsdk` は展開していない。[EMSDK] (Emscripten 6.0.12) が既にあり、`emcc --version` が 6.0.12 を返すことを確認した。
- run 1: 作業ツリーは共有 main のチェックアウト (WORKFLOW §1-1 違反)。有効な測定として数えない。参考値としてのみ残す。
- run 2: 専用 worktree `ws-4667` (branch `4667-ld234-m11-e2e-timing`、commit `fbb19946c`)。
- run 3: 専用 worktree `ws-4667-m11` (detached、commit `fbb19946c`)。PR ブランチの HEAD は別のまま。
- 機器: 4 vCPU・メモリ 15 GiB。
- 実行コマンド: `timeout 2300 bash liftdiff_e2e.sh --m11-only`。実時間は `date +%s` の差分で計った。

## 3. 実測

| 項目 | run 1 | run 2 | run 3 |
|---|---|---|---|
| 実行 | 共有 main チェックアウト (規約違反・参考値) | worktree `ws-4667` (fbb19946c) | worktree `ws-4667-m11` (fbb19946c・detached) |
| 有効 | 数えない | 有効 | 有効 |
| real | 3m15.559s | 3m13.983s | 206 s (11:08:02 → 11:11:28) |
| uptime 開始 (1 分平均) | load 1.00 (10:48:43) | load 2.00 (10:53:01) | load 3.77 (11:08:02。素材展開の直後) |
| uptime 終了 (1 分平均) | load 4.72 (10:51:59) | load 4.92 (10:56:15) | load 7.15 (11:11:28) |
| `[4/4]` バッチ | 116 s | 116 s | 125 s |
| 結果 | `LIFTDIFF_E2E PASS` | `LIFTDIFF_E2E PASS` | `LIFTDIFF_E2E PASS` |

run 2 の real (3m13.983s) と run 1 の real は、run 2 の REPORT 記録からの転記。run 3 は date の差分で計ったため、run 2 と計測方法が違う。

step ごとの結果 (run 3 の端末ログより):

- `[0/4]` 単体テスト: `test_ld52_machine_sig`・`test_ld181_i128_entry`・`test_ld179_tagpoint_tr`・`test_ld203_slot_fill`・`test_ld225_sample_vmo` すべて PASS。ネガコン込みの比較系テストも ok。
- `[3/4]` unit #18 の原因特定: `_UStrAsg` の mem diff・`Delphi Move(409c80)` の `spill_slot_deref`・`4123c0` の resourcestring 脱落 (native entry 67 > wasm 46、`callsite_arg_drop`、mem diff 7) を PASS。
- `[3b/4]` `CHECK_INITUNITS PASS` (units は precondition ok=False で空振り、hybrid は ok=True で diff 11)。
- `[4/4]` は下の §4。

## 4. `[4/4]` の内訳 (sample:800、801 関数)

| 区分 | run 1 | run 2 | run 3 |
|---|---|---|---|
| 一致 | 360 | 360 | 360 |
| 不一致 | 235 | 235 | 235 |
| 実行不能 | 206 | 206 | 206 |
| timeout/hang/crash を含む case | 304 (関数 70) | 306 (関数 71) | 326 (関数 74) |

- 不一致のうち callee を呼ばずに差分が出たもの: 52 (run 2・run 3)。wasm trap を含むもの: 70 (run 2・run 3)。
- run 3 の不一致の主因 / 該当数: `callee_divergence` 57 / 104、`wasm_trap` 44 / 70、`memory_semantics` 25 / 26、`callsite_arg_drop` 23 / 23、`icall_drop` 19 / 23。run 2 と同一。
- run 3 の実行不能の内訳: `native_fault_all_patterns` 123・`native_null_deref_all_patterns` 44・`hang` 39。合計 206。**前回記録 (119 / 49 / 38) とは内訳が違う**。前回 REPORT の「両 run 同一」は誤りで、ここで訂正する。
- timeout 系の件数は 304 → 306 → 326 と揺れている。`[4/4]` の一致・不一致・実行不能の件数は 3 回とも同じ。原因は未調査 (§6)。

## 5. 差分 (測定 commit から HEAD まで)

測定 commit `fbb19946c` から PR ブランチ HEAD までの `tools/liftdiff` の差分は、REPORT の追加だけ。コード差分は 0。

```
$ git diff fbb19946c HEAD --stat -- tools/liftdiff
 tools/liftdiff/REPORT_LD234.md | 81 +++++++++++++++++++++++++++++++++++++++++++++++
```

測定値の鮮度はコード差分 0 で、HEAD でも有効。

## 6. 未解決

- timeout 系 case の件数の揺れ (304 / 306 / 326)。run 3 の 326 は run 2 より大きい。原因は未調査。
- 実行不能の内訳 (native_fault / null_deref / hang) が run 2 と run 3 で違う (§4)。合計 206 は一致。原因は未調査。
- run 2 の端末ログは保存されていない。run 2 の step ごとの PASS 行は実行記録の転記。run 3 の端末ログは work 領域 (gitignore、commit しない) にあり、リポジトリ外には残っていない。
- run 1 の作業ツリーが共有 main だったこと (§2)。参考値として残す。
- LD-215 の `[4/4]` の時間は、この REPORT で実測済み。
