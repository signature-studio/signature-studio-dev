# liftdiff LD-200 (#4184) — `WindowFromPoint` の wasm harness 解決と `4256c0` の判定

> 親: #3862 (LD-179)。前提の付録: `REPORT_APPENDIX_LD52.md` (11 関数 batch)。
> 測定 commit: 本 PR の最後のコード commit (§4 の `git diff` の起点)。素材: `fl-win64`・`toolchain-emsdk`・`work-m11`・`work-liftdiff`。

## 1. 結論

- `WindowFromPoint` の stub skip を解消した。修正前は `skipped 1` (`undefined 1`) で、wasm では import が未定義のまま残った。修正後は `skipped 0` (`undefined 0`)。
- `4256c0` は `wasm_trap` でなくなり、`unexec` (`unsupported_sig`) から `mismatch` (`import_arg_diff`) に変わった。wasm は実行され、判定が出る。
- 受入条件の `match` は未達。差分は `WindowFromPoint` の第 2 引数 (y) が wasm 側で 0 になる件で、§3 の未解決に書く。
- `WindowFromPoint` の戻り値の仕様 (`gui_core.c` の `hit_test`) は wasm の harness に入っていない。wasm の `ld_stub` は既定応答 0 を返す (`rt/ld_core.h` の `ld_model_call`)。native も同じ既定応答 0 で、戻り値は一致している。

## 2. 変更

| 箇所 | 変更 |
|---|---|
| `tools/liftdiff/ldlib/irtool.py` | `struct_table` を新設。要素が scalar で 2 要素以下の `type` 定義を読み、`gen_stubs` が by-value の struct 引数を要素ごとの引数に展開する。`%tagPOINT` (`{ i32, i32 }`) は `(unsigned a0, unsigned a1)` になる |
| `tools/liftdiff/ldlib/cases.py` | `MACHINE_ENTRY` に `0x4256c0: ['i64']` を足す (rcx の POINT 値 1 本。LD-39 §6.1 の読みと整合) |
| `tools/m11/m11_post.py` | `%tagPOINT` の引数を `m11_tr_` が i64 から組み立てる。従来は `zeroinitializer` を渡していた |
| `tools/liftdiff/tests/test_ld200_struct_stub.py` | 新規。struct 展開・skip 件数・幅を検査。`irtool.py` を HEAD に戻すと AttributeError で非 0 終了することを確認 |
| `tools/liftdiff/liftdiff_e2e.sh` | 上のテストを 1 行追加 |

## 3. 実測 (`targets/ld52_11.txt`・`batch --shards 4`)

| 項目 | 修正前 (HEAD `17a3d0796`) | 修正後 |
|---|---|---|
| build `stubs` / `skipped` | 362 / 1 (`WindowFromPoint`) | 363 / 0 |
| build `undefined` / `sig_mismatch` | 1 / 0 | 0 / 0 |
| batch 一致 / 不一致 / 実行不能 | 2 / 0 / 9 | 2 / 1 / 8 |
| `4256c0` の verdict | `unexec` (`unsupported_sig`) | `mismatch` (`import_arg_diff`) |
| `4256c0` の wasm trap | (未実行) | 0 件 (`wasm_trap` なし) |

`4256c0` の差分の中身 (修正後): `WindowFromPoint` の第 1 引数 (x) は native と一致 (例: 3)。第 2 引数 (y) が wasm で 0 になる (native は 5 など)。`kind: call_arg`。`function_4256c0` の本体の `%tagPOINT` 受け渡しを LLVM wasm32 がどう分解するかが未確定で、stub 側 (2 引数) と call 側 (struct 1 個) の組が一致していないと推定する。callee を呼ぶ前の差なので、`4256c0` 自身の欠陥ではなく入口の ABI の扱いの差。

他の 10 関数の判定は修正前と同じ (`40c660` `40c750` が match、残りは `unexec` のまま)。

`liftdiff_e2e.sh` の対象テストは `test_ld52_machine_sig.py` (PASS)・`test_ld200_struct_stub.py` (OK)・`test_compare_ld11.py` (OK) で確認した。

## 4. 測定 commit と差分

- 測定 commit: `5dc9ac0a0` (本 PR のコードを変えた最後の commit)。§3 の数値はこの commit で測ったもの。
- `git diff 5dc9ac0a0 HEAD -- tools/liftdiff tools/m11 ':!*.md'` は **72 ファイル・+21537/-65 行** (現 head `6335a1e56` = main `71953e2e1` の取り込み merge で実測)。差分 0 ではない。内訳は main 取り込み (`7bae8537a` ほか) で入った LD-179・LD-39 系・frame_share・ldfix など (`tools/liftdiff/ldlib/pe.py`・`session.py`・`tools/m11/*.py`・`tools/m11/ldfix/*`・`tools/m11/frame_share/*` ほか)。
- 本 PR の変更が実行経路に入るのは `tools/m11/m11_post.py` の `%tagPOINT` 分岐の変数名のみ (`lo/sh/hi/p` → `px/ps/py/u`。生成する命令列は同一)。`tools/liftdiff/ldlib/cases.py` の `MACHINE_ENTRY` は main 取り込みで 6 エントリが増え、`0x4256c0` の行は両側の統合 (`['i64']`)。この増分が §3 の数値に入るかは再測定まで不明。
- HEAD での再測定は未実施。build に emsdk (`[EMSDK]`)・`tools/m11/work/boot_final3.ll` (素材 `toolchain-emsdk`・`work-m11`) が要るが、この run の `$ARTIFACTS_DIR` には `fl-win64` しか無い (`tools/m11/work/`・`tools/liftdiff/work/`・`/opt/retdec/bin`・`emcc` も無し)。再測定は子 #4441 ([LD-218]) で、素材を揃えた次の run で行う。
- 2026-10-15 (round 5) に再確認: `$ARTIFACTS_DIR` は `fl-win64` のみ (`toolchain-emsdk`・`work-m11`・`work-liftdiff`・`toolchain-retdec` は無い)。現 head での build・11 関数 batch は実行不能。§3 の数値は測定 commit `5dc9ac0a0` のまま。
- 現 head `5c4f3a33b` の `tests/test_ld200_struct_stub.py` は素材不要で OK (rc 0)。

## 5. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `4256c0` の y 引数が wasm で 0 になる (struct `%tagPOINT` の wasm32 受け渡しの分解) | `4256c0` が match にならない (mismatch のまま) | #4240 ([LD-205]) |
| wasm harness の `WindowFromPoint` が `gui_core.c` の `hit_test` 実装を使わず、既定応答 0 | 戻り値が点を含むウィンドウを返す場合の差を検出できない | #4243 ([LD-206]) |
