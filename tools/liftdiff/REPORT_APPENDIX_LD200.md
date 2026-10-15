# liftdiff LD-200 (#4184) — `WindowFromPoint` の wasm harness 解決と `4256c0` の判定

> 親: #3862 (LD-179)。前提の付録: `REPORT_APPENDIX_LD52.md` (11 関数 batch)。
> 測定 commit: `318ffa941` (現 head で build と 11 関数 batch を実行した commit)。素材: `fl-win64`・`toolchain-emsdk`・`work-m11`・`work-liftdiff` (`$ARTIFACTS_DIR` の 4 件を展開して使用)。

## 1. 結論

- `WindowFromPoint` の stub skip を解消した。`origin/main` (`ac51e9316`) では `skipped 1` (`undefined 1`) で、wasm では import が未定義のまま残る。本 PR の現 head では `skipped 0` (`undefined 0`)。
- `4256c0` は `wasm_trap` でなくなった。`origin/main` では `wasm_trap` (`missing function: WindowFromPoint`)、本 PR では `mismatch` (`import_arg_diff`)。wasm は実行され、判定が出る。
- 受入条件の `match` は未達。差分は `WindowFromPoint` の第 1 引数 (x) が wasm で 0 になる件 (§3・§5)。
- 11 関数 batch の判定は、本 PR の現 head と `origin/main` で `4256c0` 以外が一致する (§3)。
- `WindowFromPoint` の戻り値の仕様 (`gui_core.c` の `hit_test`) は wasm の harness に入っていない。wasm の `ld_stub` は既定応答 0 を返す (`rt/ld_core.h` の `ld_model_call`)。native も同じ既定応答 0 で、戻り値は一致している。

## 2. 変更

| 箇所 | 変更 |
|---|---|
| `tools/liftdiff/ldlib/irtool.py` | `struct_table` を新設。要素が scalar で 2 要素以下の `type` 定義を読み、`gen_stubs` が by-value の struct 引数を要素ごとの引数に展開する。`%tagPOINT` (`{ i32, i32 }`) は `(unsigned a0, unsigned a1)` になる |
| `tools/liftdiff/ldlib/cases.py` | `MACHINE_ENTRY` に `0x4256c0: ['i64']` を足す (rcx の POINT 値 1 本。LD-39 §6.1 の読みと整合) |
| `tools/m11/m11_post.py` | `%tagPOINT` の引数を `m11_tr_` が i64 から組み立てる。従来は `zeroinitializer` を渡していた |
| `tools/liftdiff/tests/test_ld200_struct_stub.py` | 新規。struct 展開・skip 件数・幅を検査。`irtool.py` を HEAD に戻すと AttributeError で非 0 終了することを確認 |
| `tools/liftdiff/liftdiff_e2e.sh` | 上のテストを 1 行追加 |

## 3. 実測 (測定 commit `318ffa941`)

素材の展開: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)、`work-m11` → `tools/m11/work/`、`work-liftdiff` → `tools/liftdiff/work/` (gitignore 対象。commit していない)。

手順: `python3 ldlib/build_wasm.py targets/m11.json --force` → `python3 liftdiff.py batch targets/m11.json --set file:targets/ld52_11.txt --shards 4 --nobuild --out work/ld200_head.jsonl`。比較用に `origin/main` (`ac51e9316`) で同じ手順を実行した。

build (rc 0・wall 9 秒)

| 項目 | 現 head `318ffa941` | `origin/main` `ac51e9316` |
|---|---|---|
| `stubs` / `skipped` | 363 / 0 | 362 / 1 (`WindowFromPoint`) |
| `undefined` / `sig_mismatch` | 0 / 0 | 1 / 0 |
| wasm サイズ | 4,464,468 B | 4,464,346 B |

batch (rc 0・wall 9 秒・shards 4・開始時 load 0.35 / 終了時 0.37)

| 項目 | 現 head `318ffa941` | `origin/main` `ac51e9316` |
|---|---|---|
| 一致 / 不一致 / 実行不能 | 2 / 7 / 2 | 2 / 7 / 2 |

関数ごとの判定 (現 head。`origin/main` と比べた違いは `4256c0` のみ)

| 関数 | 現 head | `origin/main` |
|---|---|---|
| `40c660` | match | match |
| `40c750` | match | match |
| `4256c0` | mismatch (`import_arg_diff`) | mismatch (`wasm_trap`: missing function `WindowFromPoint`) |
| `664890` | mismatch (`wasm_trap`: unreachable in `4128b0`) | 同左 |
| `6649b0` | mismatch (`callsite_arg_drop`・`callee_divergence`) | 同左 |
| `6649c0` | mismatch (`callsite_arg_drop`・`callee_divergence`) | 同左 |
| `664a80` | mismatch (`callee_divergence`) | 同左 |
| `442a50` | mismatch (`callsite_arg_drop`・`callee_divergence`) | 同左 |
| `442b90` | mismatch (`callee_divergence`) | 同左 |
| `653c80` | unexec (`native_fault_all_patterns`) | 同左 |
| `691dd0` | unexec (`native_null_deref_all_patterns`) | 同左 |

`4256c0` の差分の中身 (現 head): `WindowFromPoint` の第 1 引数 (x) が native `0x3`、wasm `0x0` (`kind: call_arg`・`import_arg_diff`)。callee を呼ぶ前の入口の差で、`4256c0` 自身の欠陥ではない。`%tagPOINT` を LLVM wasm32 がどう分解して渡すかは未確定。

単体テスト (現 head `318ffa941`・素材不要。全て rc 0): `test_ld200_struct_stub` OK・`test_ld181_i128_entry` PASS・`test_ld179_tagpoint_tr` PASS・`test_ld203_slot_fill` PASS・`test_ld52_machine_sig` PASS・`test_compare_ld11` OK。

## 4. 測定 commit と差分

- 測定 commit: `318ffa941`。§3 の数値はこの commit で測った値。
- 測定 commit から HEAD までのコード差分: `git diff 318ffa941 HEAD -- tools/liftdiff tools/m11 ':!*.md'` は 0 行 (以後の commit は REPORT の md だけ)。
- `origin/main` (`ac51e9316`) から HEAD までのコード差分: `git diff ac51e9316 HEAD -- tools/liftdiff tools/m11 ':!*.md'` は 7 files (+78/-97)。内訳は `irtool.py`・`liftdiff_e2e.sh`・`test_ld200_struct_stub.py`・`m11_post.py` (本 PR) と、`ld211_fvm_probe.py`・`dyn_509.mjs`・`ldfix_509_e2e.sh` (main 側で削除・変更された分)。
- 旧測定 `5dc9ac0a0` の batch (2 / 1 / 8) と現 head (2 / 7 / 2) の差は、`origin/main` でも同じ判定になるため、本 PR の変更ではなく main 取り込み分による。本 PR が判定を変えたのは `4256c0` だけ。
- `origin/main` で `4256c0` を見ると `wasm_trap` (`WindowFromPoint` 未定義) のため、受入条件 1 (`wasm_trap` の解消) は本 PR の効果として現 head で確認した。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `4256c0` の第 1 引数 (x) が wasm で 0 になる (POINT の wasm32 受け渡し) | `4256c0` が match にならない (mismatch のまま) | #4240 ([LD-205]) |
| wasm harness の `WindowFromPoint` が `gui_core.c` の `hit_test` 実装を使わず、既定応答 0 | 戻り値が点を含むウィンドウを返す場合の差を検出できない | #4243 ([LD-206]) |
