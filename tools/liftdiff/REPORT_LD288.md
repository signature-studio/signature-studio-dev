# liftdiff LD-288 (#5888) — `40c420` の wasm 戻り値が常に 0 になる原因 (lift 側) と修正

> 親 #5886 (LD-287) の停止報告 (run 38919389757) の未解決 1 件。判定器 `tests/ld215_retprop.py` の候補 `40c420` の型判定 (#5886 受入 1) の前提。

## 1. 結論

- 原因は **lift 側**。harness ではない。
- IR の `define i128 @function_40c420()` は引数を持たず、入口で `xor i128 0, 0` を使う。機械語は入口で **xmm0 (double)** を読む (`movapd xmm3, xmm0` が先頭)。そのため wasm は入力 0 から計算し、結果 0 を返した。
- 修正: (a) `ldlib/cases.py` の `MACHINE_ENTRY` に `0x40c420: ['double']` を追加 (入口型の投入)。(b) IR を `fix_xmm_args.py --only-funcs function_40c420` で `double %in.xmm0` に直し、wasm の入口 `m11_tr_function_40c420` が `%a0` を double に bitcast して渡す (`tests/ld288_40c420_xmm0.py` で生成)。
- (a) だけでは不足 (実測 A で `wasm_trap`)。(b) だけでも不足 (実測 A の前段で `wasm_x0=0`)。両方そろって `verdict=match` (11 case 全 `equal`)。
- 戻り型は double (`native_x0` が 1.5 付近の double bits `0x3ffa…` / `0x4024…`)。ただし型の確定は #5886 の受入 1 の作業で、本 PR は `40c420` の入力・戻り値の比較の成立までを扱う。`m11.json` の `ret_override` は変えていない。

既知類型との関係 (DEFECTS.md): **D5** (float/double 引数の xmm 落ち。入口 live-in の xmm0 が read-before-write)。既存の `fix_xmm_args.py` (M11_XMM_ARGS) が扱う類型と同じ。icall REPORT §4 とは別体系。

## 2. 測定

| 項目 | 値 |
|---|---|
| 測定 commit | `c2efe08ef` (`fix(liftdiff): restore 40c420 entry xmm0 input`。コードを変えた最後の commit) |
| 環境 | `FL_WIN64_DIR=$RUNNER_TEMP/ld288/fl-win64` (fl-win64.tar.zst を展開)・`EMSDK=$RUNNER_TEMP/ld288/emsdk` (toolchain-emsdk)。`tools/m11/m11_gen_ir2.sh` を先に実行 (54 秒・ir_conditions.json 生成) |
| 負荷 | 測定開始時 load average 0.42 (4 コア) |
| e2e (`liftdiff_e2e.sh --m11-only`) | **PASS** (rc 0)・所要 224.9 秒 (3m44.928s wall)・user 6m13.9s |
| closure sample:800 | 801 件: **一致 360 / 不一致 236 / 実行不能 205** (batch 128 秒)。LD-233 の 360 / 236 / 205 と同値 |
| 単体 (修正版) `run m11_ld288 --fn function_40c420` | `verdict=match`・11 case 全 `equal` (native=ok wasm=ok) |
| m11 route (`m11.json`・無修正 IR) `run --fn function_40c420` | `verdict=unexec reason=unsupported_sig` (HEAD でも変わらず。m11 の判定は不変) |

## 3. 原因の切り分け (実測)

| 実測 | 条件 | 結果 |
|---|---|---|
| 0 | `m11.json` (`40c420` の ret_override なし) | `unexec unsupported_sig` (ret i128 の入力が無い) |
| 1 | `ret_override: double` のみ | `mismatch` · `native_x0=0x3ffa5364a40c7cd9` / `wasm_x0=0x0` (全 11 case)。tag `xmm_arg_drop` |
| 2 | 1 + `MACHINE_ENTRY` のみ (IR は `()` のまま) | `mismatch` · `native_x0=0x40248ec7bda226c8` / `wasm_x0=0x0` (全 11 case)。入力を渡しても IR が受けない |
| 3 | 1 + IR 修正 (`double %in.xmm0`) + trampoline 修正、`MACHINE_ENTRY` なし | `wasm_trap` (`Cannot convert 1.5 to a BigInt`)。harness が double を i64 の wsig に渡す経路が無い |
| 4 | **IR 修正 + trampoline 修正 + `MACHINE_ENTRY`** (本 PR) | **`match`** 11/11 |
| 5 (NEG) | 4 から `MACHINE_ENTRY` 行だけを外す | `wasm_trap` (case z) → 行が必須であることを確認 |

- 実測 1 と 2 の `wasm_x0=0x0` が、harness の戻り取得の誤りではないことの根拠: harness は `6ed480` で `match` (LD-233) になっており、`40c420` 固有の差は IR の入力欠落だけ。

### 3.1 harness 側の確認
`rt/fle_runner.mjs`・`rt/ld_runner.mjs` は `double` の戻りを `_fle_ld_xmm0()` / 下位 64bit で読む。`6ed480` の match がその経路の正しさを示す。`40c420` の差は戻り経路ではなく入力経路。

## 4. 修正内容

| ファイル | 変更 |
|---|---|
| `tools/liftdiff/ldlib/cases.py` | `MACHINE_ENTRY` に `0x40c420: ['double']` を 1 行追加 (LD-52 の機械語入口型。`40c660`・`40c750` と同じ形) |
| `tools/liftdiff/tests/ld288_40c420_xmm0.py` | 新規。`fix_xmm_args.py --only-funcs function_40c420` + trampoline の 1 箇所置換で修正 IR を生成。入力 IR は `tools/m11/work/boot_final3.ll` |
| `tools/liftdiff/targets/m11_ld288.json` | 新規。`m11.json` の複製で `ir` を `work/ld288/` の修正 IR に、`ret_override` に `function_40c420: double` を追加 |

`m11.json` と m11 route の IR (`tools/m11/work/boot_final3.ll`) は変えていない。

## 5. 再現手順

```sh
export FL_WIN64_DIR=$RUNNER_TEMP/ld288/fl-win64 EMSDK=$RUNNER_TEMP/ld288/emsdk TMPDIR=$RUNNER_TEMP
python3 tools/liftdiff/tests/ld288_40c420_xmm0.py $FL_WIN64_DIR/extracted/block00031_PE.bin \
  tools/m11/work/boot_final3.ll tools/liftdiff/work/ld288/boot3_40c420_tr.ll
python3 tools/liftdiff/liftdiff.py run tools/liftdiff/targets/m11_ld288.json --fn function_40c420 -v   # → verdict=match
bash tools/liftdiff/liftdiff_e2e.sh --m11-only                                                         # → LIFTDIFF_E2E PASS
```

## 6. 測定 commit からの差分

`git diff c2efe08ef HEAD -- tools/liftdiff` は本節の REPORT 追記のみ (コード差分 0 行)。

## 7. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 戻り型の確定 (`40c420` = double) は本 PR の対象外。`m11.json` の `ret_override` にも入れていない | 型判定 (#5886 受入 1) は未達 | #5886 (親) |
| 残りの候補 (`ba05f0`・`6a3ac0`・`40f210`・`677820`) の入力 xmm 欠落の有無は未確認 | 同類の lift 欠陥が残る可能性 | #5886 |
| m11 route (`m11.json`) の `40c420` は `unexec` のまま (IR 修正は liftdiff 用 target のみ) | m11 の 40c420 の判定は変わらない | #5886 |
| `wasm_trap` 件数の増減 (`m11_ld288` の closure 全数) は未測定 | 修正の副作用範囲は sample:800 の一致数で確認 (不変) | #5886 |
