# REPORT_4522 — 0x413340 の 2 site の r8・r9 接続 (#4522 / CI-192、親 #3451)

前段: #4521 (CI-191・PR #4571) で `function_412fc0` を 5 引数化し、呼出元 3 site の rcx・rdx・5 番目を接続した。
本件はその残件で、0x413340 の 2 site の r8・r9 が IR で 0 のままだった (REPORT_4521 §4)。
r9 の残件 (`0x412fc0` の rcx・r9 の接続) は #3450・#4521 の時点で接続済み (下記 §1)。

## 0. 結論

- 0x413340 の 2 site (0x41338b・0x4133bc) の r8 を `arg2` (0x413340 の入口 rdx、`[rsp+0x38]`)、r9 を `zext(arg3)` (`ebx`) へ接続した。
- 修復 pass `fix_abi_4522.py` を追加し、`ldfix_e2e.sh` の step 1e3 に入れた。機械語 (capstone) の呼出し直前 2 区間を全命令で照合してから IR を書き換える。
- 受入条件 1 (0x413340 の 2 site の付け直し) は達成。受入条件 2 (0x412ffc の 1 本目 rcx・4 本目 r9) は #3450・#4521 で既に接続済みのため、本 PR では新たに変えていない (§1)。
- 製品 KPI (起動): 本 PR は起動の経路 (FLEngine dispatch 数) を変えない。`stage4` の unit 数 (17/942) と survey (ok 136 / miss 14 / trap 9) は base と同一。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| 0x413340 の 2 site・`m11_tr_function_412fc0` を機械語の rcx・rdx・r8・5 番目と照合して付け直す | 達成。2 site の r8・r9 を接続。rcx は site1=0 (機械語 `xor ecx,ecx` @0x41337a)・site2=`*(arg1)` (fix_site_3326 が接続済み)。rdx は site1=0・site2=`edi` (既存)。5 番目は `r13d` → `%14` (#4521 で接続済み) |
| `0x412ffc` の 1 本目 rcx・4 本目 r9 を機械語の値へ接続 | 既に接続済み: 修復後 IR の `function_412fc0` は `call @function_41c8c0(i64 %r5, …, i64 %arg4, …)` (#4521)。rcx = 5 番目/既定値・r9 = `%arg4` (素通し)。本 PR では変えない |

注: 受入条件 2 は #4521 で満たされていた。本 PR の目的は、残件だった 0x413340 側 (呼出元) の r8・r9 の接続。

## 2. 機械語 ↔ IR (呼出元 0x413340、修復後)

| site | call (VA) | rcx | rdx | r8 (機械語) | r9 (機械語) | 5 番目 (機械語) | IR 修復後 |
|---|---|---|---|---|---|---|---|
| 1 | 0x41338b | 0 (`xor ecx,ecx` 0x41337a) | 0 (`xor edx,edx` 0x41337c) | `[rsp+0x38]` = arg2 (0x41337e) | `ebx` = zext(arg3) (0x413383) | `r13d` (0x413386) | `0, 0, %arg2, %ldfx4522_r9a, %14` |
| 2 | 0x4133bc | `*(arg1)` (0x4133aa `mov rcx,[rax]`) | `edi` (0x4133ad) | `[rsp+0x38]` = arg2 (0x4133af) | `ebx` (0x4133b4) | `r13d` (0x4133b7) | `%20, %18, %arg2, %ldfx4522_r9b, %14` |

- `%ldfx4522_r9a` / `%ldfx4522_r9b` は `zext i32 %0 to i64` (`%0` = `trunc arg3`、0x413340 の 0x413353 `mov ebx,r8d` と同じ下位 32 bit)。
- site 2 の rcx (`*(arg1)`) は `fix_site_3326.py` (step 1c) が接続済みで、本 PR では触らない。

## 3. 検証

測定 commit: **`3d1d40841`** (main 取り込み後の HEAD。コード変更の最後の commit は `164b087aa`)。
`git diff 164b087aa 3d1d40841 -- tools/m11/ldfix/` の出力は REPORT_4522.md のみ (コード差分 0)。

### 3.1 e2e (`ldfix_e2e.sh`・rc 0)

`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` (commit `3d1d40841`・wall 61 s・load 0.83 (16:03 時点)。`164b087aa` でも同一結果・wall 60 s):

| 指標 | base | fix | 判定 |
|---|--:|--:|---|
| stage4 到達 | 4/6 | 4/6 | OK |
| GetMem / FreeMem / FastMM_GetMem | 16 / 6 / 17 | 17 / 6 / 18 | OK (fix 増加 +1) |
| units_run / units_total / init_count / icall_ok | 17 / 942 / 18 / 24 | 同一 | OK |
| survey ok / miss / trap | 136 / 14 / 9 | 136 / 14 / 9 | OK |
| judge (`STAGE4_JUDGE`) | `pass: true` | | |

`wasm_size` は base 6025704 / fix 6026047。

### 3.2 GetMem の +1 の切り分け

fix 側の GetMem が 16 → 17 になったのは本 PR の変更 (r8・r9 の接続) によるもの。同じ前段チェーンで 1e3 (4522) だけ外して比べた (15:58〜16:00 の作業ツリー。修復 IR の内容は `164b087aa` と同一)。

| 版 | fix の GetMem | fix の FastMM_GetMem | icall_ok | survey ok |
|---|--:|--:|--:|--:|
| 4522 を外した (4521 まで) | 16 | 17 | 24 | 136 |
| 4522 込み (本 PR) | 17 | 18 | 24 | 136 |

判定 (`judge_e2e.py`) は「probe 減無し」で、+1 は逆行ではない。4522 込みの版でも survey・units・icall は変わらない。

### 3.3 照合

- `fix_abi_4522.py` (機械照合 13 項目 OK・IR 2 行置換 OK)。
- `verify_abi_3426.py --fixed412` (4521 の IR を照合): 照合 OK 35 項目。`C412` は 4521 の形のまま (4522 の照合は `fix_abi_4522.py` の `check_ir` へ分離)。
- `fix_abi_4522.py --negctl` (修復後 IR に対する N5・N6 の 2 件): 拒否 OK 2 件・NG 0 件。
- `verify_abi_3426.py --negctl` (4521 の IR): NG 0 件。
- 4522 後の IR に修復 pass を再適用すると行が無く停止する (二重適用の防止)。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 0x413340 の呼出元の値 (arg2・arg3 の由来) は、呼出元 (0x413340 を呼ぶ 2 site・`function_413a90` など) の引数の照合までは行っていない | 0x413340 の入口引数が正しいかは本 PR の範囲外。r8・r9 は 0x413340 の入口値を素通しするだけ | #3451 (親) の受入で確認 |
| DEFECTS.md への類型登録 (REPORT_3450 §6 の行案) | 類型カタログに未登録 | PM 判断 (`docs/WORKFLOW.md` §5) |
