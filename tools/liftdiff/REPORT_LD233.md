# liftdiff LD-233 (#4666) — 確定した戻り型 `6ed480` = double を `m11.json` の `ret_override` に反映

> 親 #4666 の受入 1 (確定値の反映と `--m11-only` PASS)。入力は子 #5276 (候補 7 件・未確定 13 件) と #5277 (`6ed480` = double, `REPORT_LD263.md`)。
> 本 PR で反映したのは `6ed480` の 1 件だけ。他の候補 6 件 (`ba05f0`・`40c420`・`1311ea0`・`6a3ac0`・`40f210`・`677820`) と未確定 13 件は型が決まっていないため入れていない。

## 1. 結論

- `targets/m11.json` の `ret_override` に `function_6ed480: double` を追加 (8 件 → 9 件)。
- `--m11-only` e2e は測定 commit `c77cd1093` で `LIFTDIFF_E2E PASS` (rc 0)。
- 単体 `run --fn function_6ed480` は `verdict=match` (11 case 中 `native_fault` 3 件は native 側の segv で、wasm は ok)。

## 2. 測定

| 項目 | 値 |
|---|---|
| 測定 commit | `c77cd1093` (`targets/m11.json` の変更を含む最後のコード commit) |
| 環境 | `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64`・`EMSDK=$RUNNER_TEMP/emsdk`。`m11_gen_ir2.sh` を先に実行して `ir_conditions.json` を作成 |
| e2e 所要 | 191 秒 (wall。`elapsed_s=191`)。batch 単体は 110 秒 |
| 負荷 | 実行開始時 load average 2.98 (4 コア) |
| e2e 結果 | `LIFTDIFF_E2E PASS` (rc 0) |
| closure sample:800 | 801 件: 一致 360 / 不一致 236 / 実行不能 205 (変更前と同数) |
| `run --fn function_6ed480` | `verdict=match` (6 秒) |

注: sample:800 の 801 件に `6ed480` は含まれない。したがって batch の数値は今回の変更の効果を示さない。`6ed480` の効果は単体 `run --fn` で確認した。

## 3. 測定 commit からの差分

`git diff c77cd1093 HEAD -- tools/liftdiff/targets tools/liftdiff/ldlib tools/liftdiff/liftdiff.py` は本節の REPORT 追記後も 0 行 (コード差分なし)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 候補 6 件 (`ba05f0`・`40c420`・`1311ea0`・`6a3ac0`・`40f210`・`677820`) の戻り型 | 未確定のため `ret_override` 未登録。誤った型は silent miscompile | #4666 (チェックリスト) |
| 未確定 13 件 (`7ce2e0` `12657b0` `442670` `5b0970` `442890` `6a3a90` `1311f70` `13114b0` `40c650` `4421d0` `45e3c0` `45ee00` `8e6660`) | 理由はいずれも `call` (間接 call・深さ超過) | #4666 (チェックリスト) |
