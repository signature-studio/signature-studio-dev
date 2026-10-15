# REPORT_4521 — function_412fc0 の 5 番目引数と既定値分岐の修復 (#4521 / CI-191、親 #3451)

前段: #3426 (REPORT_3426.md) で 412fc0 の機械語↔IR の不一致を特定。#3450 (CI-163) が 0x41c8c0 を 8 引数化済み。

## 0. 結論

- `function_412fc0` を 3 引数から 5 引数 (rcx・rdx・r8・r9・5 番目) にし、5 番目が 0 のとき `0x15e6a28` の既定値を使う分岐を IR に入れた。
- 呼出元 3 site (`function_413340` の 2 site と `m11_tr_function_412fc0`) を新しい引数列に接続した。
- 機械語照合 (`verify_abi_3426.py --fixed412`) と ネガティブコントロール 4 件 (`--negctl`) を追加。**4/4 拒否、NG 0 件**。
- 呼出元の r8・r9 (機械語の `mov r8,[rsp+0x38]`・`mov r9d,ebx`) の接続は CI-192 の範囲で、本 PR は 0 のまま残す。

## 1. 受入条件

| 受入条件 | 結果 |
|---|---|
| 412fc0 を rcx・rdx・r8・r9・5 番目の形にし、5 番目 0 で `0x15e6a28` の既定値を使う分岐を入れる | 達成 (`fix_abi_4521.py`) |
| `verify_abi_3426.py` の照合を新しい形に合わせて更新 | 達成 (`check_fixed_412`・`--fixed412`) |
| ネガティブコントロール (既定値分岐の改変・呼出元の 5 番目の取り違え) | 達成 (N1〜N4) |

## 2. 機械語 ↔ IR の対応 (修復後)

| 項目 | 機械語 (VA) | 修復後の IR |
|---|---|---|
| 入口の引数 | rcx・rdx・r8・r9・5 番目 (入口 `[rsp+0x28]`) | `function_412fc0(i32 %arg1, i32 %arg2, i64 %arg3, i64 %arg4, i64 %arg5)` |
| 5 番目の既定値 | 0x412fc4 `cmp [rsp+0x70],0`・0x412fc9 `jne`・0x412fcb `mov eax,[0x15e6a28]` | `icmp eq i32 %c5, 0` → 0 のとき `load i32 ... 22964776` (= 0x15e6a28) |
| 41c8c0 の rcx | 0x412ff7 `mov ecx,eax` (5 番目/既定値) | `%r5` (zext の 5 番目/既定値) |
| 41c8c0 の rdx | 0x412ff9 `mov edx,r10d` (= 0) | `i64 0` |
| 41c8c0 の r8・r9 | 素通し | `%arg3`・`%arg4` |
| 41c8c0 の 5〜8 番目 | `[rsp+0x20]` = arg1、`[rsp+0x28]` = arg2、0、0 | `%0`・`%1`・`0`・`0` |

呼出元 (修復後): `%15 = call @function_412fc0(i32 0, i32 0, i64 0, i64 0, i64 %14)`、
`%21 = call @function_412fc0(i32 %20, i32 %18, i64 0, i64 0, i64 %14)`、
`m11_tr_function_412fc0` は a0〜a4 を渡す。`%14` (= `movzx si`) は機械語の 5 番目 (`mov [rsp+0x20],r13d`) に対応する。

## 3. 検証

測定 commit: コード変更の最後の commit (本 PR の commit)。

`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` (rc 0・wall 58.77 s・user 53.34 s・load 0.68 (10:00 時点)):

| 指標 | base | fix | 判定 |
|---|--:|--:|---|
| stage4 到達 | 4/6 | 4/6 | OK |
| GetMem / FreeMem / FastMM_GetMem | 16 / 6 / 17 | 16 / 6 / 17 | OK |
| units_run / units_total / init_count / icall_ok | 17 / 942 / 18 / 24 | 同一 | OK |
| survey ok / miss / trap | 136 / 14 / 9 | 136 / 14 / 9 | OK |
| judge (`STAGE4_JUDGE`) | `pass: true` | | |

`wasm_size` は base 6025344 / fix 6025689。

`verify_abi_3426.py ... --fixed412` (照合 OK: 35 項目)・`--fixed412 --negctl` (NG 0 件)・既存の `verify_abi_3426.py` (修復前 IR 照合 OK・NC5 拒否 OK) を実行して通過。

## 4. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 呼出元 `0x413340` の r8・r9 (機械語 `mov r8,[rsp+0x38]`・`mov r9d,ebx`) が IR で 0 のまま | `function_412fc0` が受け取る r8・r9 が届かない。0x41c8c0 の r8・r9 も 0 | CI-192 (呼出元と rcx・r9 の接続) |
