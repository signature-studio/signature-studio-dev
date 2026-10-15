# liftdiff REPORT 付録: LD-253 (#5032) 8 byte struct の 1 レジスタ引数を比較器で正しく切る

親 #4306 (LD-209)。前提は #4306 の再測定 (main `695ef5514`): `4256c0` の `wasm_trap` (missing WindowFromPoint) は解消済みで、残る不一致は `import_arg_diff`。

測定 commit: **`c9bf76573`** (修正 commit。`git diff 80c2576b5 HEAD -- tools/liftdiff` の範囲で、比較器・stub 生成・テストのみ変更)。
比較の基準は **`80c2576b5`** (origin/main の修正前)。両方とも同じ素材 (`fl-win64`・`toolchain-emsdk`・`work-m11`・`work-liftdiff`) で、`work/` は同一の展開物を使った。

## 結論

- **規則は入った**: 8 byte の struct (`%tagPOINT`) を 1 レジスタで受ける import は、wasm 引数 k を `(native レジスタ, シフト量)` で引く (`slots`)。規則を壊すとテストが落ちる (mutant で rc=1 を確認)。
- **`4256c0` の不一致は解消していない**。判定は修正前後で同一 (`mismatch`)。最初の不一致は修正前から arg0 (`WindowFromPoint arg0 native=0x3 wasm=0x0`) で、修正後も同じ。
- つまり issue の仮説「arg1 (rdx) の誤比較が主因」は**当たっていない**。arg1 の誤比較は、`cmp_calls` が最初の不一致で止まるため、arg0 の差分に隠れていた。修正で arg1 の比較は正しくなったが、残るのは arg0 (POINT の x) の差分。
- 残差の原因 (native の x=0x3 に対し wasm の x=0 が来る) は未確定。候補は、呼出し側のケース生成 (pattern `s`・`p0` の引数組み立て) と、関数 `4256c0` 自体への入力の違い。本 run では切り分けていない。

## 1. 測定条件

- 素材: `fl-win64` → `$RUNNER_TEMP/fl-win64` (`FL_WIN64_DIR`)・`toolchain-emsdk` → `$RUNNER_TEMP/emsdk-root`・`work-m11` → `tools/m11/work/`・`work-liftdiff` → `tools/liftdiff/work/`。`$ARTIFACTS_DIR` に 4 件とも実在を確認して展開した。
- 対象: `targets/ld52_11.txt` の 11 関数 (`batch targets/m11.json --set file:targets/ld52_11.txt --shards 4 --state auto`)。
- 機: 4 vCPU。load 0.26〜0.71。各 batch は foreground で 1 本ずつ実行 (修正後 18.9 秒・修正前 15.5 秒。build を含む)。
- wasm: 修正後 `wasm_size` 4464620・`sig_mismatch` 0・`undefined` 0。`stubs: 363 (skipped 0)`。

## 2. 結果 (`results/ld253_ld52_11.tsv`・raw は `work/ld253/`)

| commit | 一致 / 不一致 | `4256c0` の判定 | `4256c0` の `import_arg_diff` |
|---|---|---|---|
| `80c2576b5` (修正前) | 2 / 9 | mismatch | arg0 native=0x3 wasm=0x0 |
| `c9bf76573` (修正後) | 2 / 9 | mismatch | arg0 native=0x3 wasm=0x0 |

11 関数の判定は両 commit で全て同一 (一致 `40c660`・`40c750`、他 9 件は不一致)。

## 3. 方法

- `irtool.gen_stubs` が引数ごとの `(reg, shift)` を `gen_stubs.slots` に記録し、`build_wasm` が `stubs.json` に `slots` を出す。`session` が `stub_info` に載せ、`compare.native_arg` が wasm 引数 k の native 値を `(a[reg] >> shift) & M64` で取る。
- `slots` の無い旧 `stubs.json` は従来どおり `a[k]` (後方互換)。
- テスト: `tests/test_ld253_point_arg_slot.py` (規則を壊すと rc=1)。既存の `test_ld200_struct_stub.py`・`test_compare_ld11.py` (23 件) も通る。

## 4. 未確認 (次の一手)

- 残る arg0 の差分 (native x=0x3・wasm x=0): 呼出し側でケースが POINT の x を渡せていないのか、wasm 側の引数組み立てが落ちているのかは未切り分け。`4256c0` の trace (`trace_head`) では、native の entry 引数 a0=0x3 に対し wasm は 0。
- 11 関数の残る不一致 9 件の内訳 (`callsite_arg_drop`・`callee_divergence`・`icall_drop` など) は本 issue の対象外。

## 5. 子 issue

- 残差 (`4256c0` の x=0x3 → wasm 0) の切り分けは、親 #4306 (LD-209) の続きとして扱う。本 run では起票しない (子に切ると親の受入判定が追えなくなるため。親の本文にチェックリストとして追記する)。

## 6. 再現

```sh
cd tools/liftdiff
FL_WIN64_DIR=<fl-win64 展開先> python3 liftdiff.py batch targets/m11.json --set file:targets/ld52_11.txt --shards 4 --state auto --out work/ld253/ld52_11.jsonl
python3 tests/test_ld253_point_arg_slot.py
```
