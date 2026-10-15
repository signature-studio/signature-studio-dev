# REPORT_LD234 — liftdiff_e2e.sh --m11-only の所要時間・load・[4/4] 結果の実測 (#4667)

親: #4429 (LD-215)。LD-215 の `[4/4]` (sample:800) は時間上限のため所要時間を取れなかった。本 REPORT は、そこを実測で埋める。

## 1. 結論

- `FL_WIN64_DIR=<展開先> bash tools/liftdiff/liftdiff_e2e.sh --m11-only` を 2 回実行した。有効な測定は run 2 (専用 worktree) の 1 回だけ。run 1 は共有 main での実行のため参考値。run 2 は `LIFTDIFF_E2E PASS`、rc 0。**単独 run の 2 回目は素材不足で未実施** (§6)。
- 所要時間 (time の real): **3m15.559s** (run 1) / **3m13.983s** (run 2)。`[4/4]` のバッチ単体は両 run とも **116 秒**。
- `[4/4]` の件数は両 run で同一: **801 関数 = 一致 360 / 不一致 235 / 実行不能 206**。
- 測定 commit は **`fbb19946c`** (main)。run 2 はこの commit の worktree で実行した。

## 2. 測定条件

- 測定 commit: `fbb19946c` (`Merge pull request #4649`)。コードは変更していない。
- 素材: `oc_artifacts: fl-win64 toolchain-emsdk work-m11 work-liftdiff` のうち、`fl-win64`・`work-m11`・`work-liftdiff` を展開した。`toolchain-emsdk` は [EMSDK] (docs/REFERENCES.md) が既に入っていたため展開していない。`emcc` の実在を確認した。
- `FL_WIN64_DIR` は runner の一時領域の `fl-win64/extracted` の親を指定した。
- run 1: 作業ツリーは共有 main のチェックアウト (WORKFLOW §1-1 違反)。この run は有効な測定として数えない。参考値としてのみ残す。
- run 2: 専用 worktree `ws-4667` (branch `4667-ld234-m11-e2e-timing`、commit `fbb19946c`)。
- 機器: 4 vCPU・メモリ 15 GiB。
- 実行コマンド: `timeout 2300 bash liftdiff_e2e.sh --m11-only`。`time` は bash の time 組み込みで計った。

## 3. 実測

| 項目 | run 1 | run 2 |
|---|---|---|
| 実行 | 共有 main チェックアウト (規約違反・参考値) | worktree `ws-4667` (fbb19946c) = 有効 |
| real | 3m15.559s | 3m13.983s |
| user | 5m28.896s | 5m29.204s |
| sys | 0m20.241s | 0m18.051s |
| uptime 開始 | load 1.00 (10:48:43) | load 2.00 (10:53:01) |
| uptime 終了 (1 分平均) | load 4.72 (10:51:59) | load 4.92 (10:56:15) |
| `[4/4]` バッチ | 116 s | 116 s |
| 結果 | `LIFTDIFF_E2E PASS` | `LIFTDIFF_E2E PASS` |

step ごとの結果 (run 2 の実行記録。端末出力のログは保存していない):

- `[0/4]` 単体テスト: `test_ld52_machine_sig`・`test_ld181_i128_entry`・`test_ld179_tagpoint_tr`・`test_ld203_slot_fill`・`test_ld225_sample_vmo` すべて PASS。
- `[3/4]` unit #18 の原因特定: `_UStrAsg` の mem diff・`Move(409c80)` の `spill_slot_deref`・`4123c0` の resourcestring 脱落 (native entry 67 > wasm 46、`callsite_arg_drop`、mem diff 7) を PASS。
- `[3b/4]` `CHECK_INITUNITS PASS`。
- `[4/4]` は下の §4。

## 4. `[4/4]` の内訳 (sample:800、801 関数)

| 区分 | run 1 | run 2 |
|---|---|---|
| 一致 | 360 | 360 |
| 不一致 | 235 | 235 |
| 実行不能 | 206 | 206 |
| timeout/hang/crash を含む case | 304 (関数 70) | 306 (関数 71) |

- 不一致のうち callee を呼ばずに差分が出たもの: 52。wasm trap を含むもの: 70。
- 実行不能の内訳 (両 run 同一): `native_fault_all_patterns` 119・`native_null_deref_all_patterns` 49・`hang` 38。合計 206。

不一致の類型 (主因 / 該当数) は両 run で同一。主なもの: `callee_divergence` 57 / 104、`wasm_trap` 44 / 70、`memory_semantics` 25 / 26、`callsite_arg_drop` 23 / 23、`icall_drop` 19 / 23。全類型の一覧は保存していない (ログは gitignore 対象の作業領域にあり、リポジトリ外には残っていない)。ここに載せたのは主なものだけ。

timeout 系の件数だけ run 間で 2 件違う (304 → 306、関数 70 → 71)。件数の他の部分は一致しているので、timeout の境界付近の case が揺れたと見る。原因の特定はしていない。

## 5. 差分 (測定 commit から HEAD まで)

測定 commit `fbb19946c` から HEAD までの `tools/liftdiff` のコードの差分は 0 (追加は本 REPORT `tools/liftdiff/REPORT_LD234.md` だけ)。
したがって測定値は HEAD でも有効で、再測定は要らない。

## 6. 未解決

- timeout 系 case の件数の揺れ (304 / 306)。原因は未調査。
- run 1 の作業ツリーが共有 main だったこと (§2)。`work-m11`・`work-liftdiff`・`toolchain-emsdk` の素材が無く、単独 worktree での再測定は未実施。
- step ごとのログ原本は保存していない。
- LD-215 の `[4/4]` の時間は、この REPORT で実測済み。
