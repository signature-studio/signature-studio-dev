# REPORT_3426 — 0x412fc0 の呼出規約 (レジスタ引数・5 番目引数) の機械照合 (#3426 / CI-157、親 #3416)

既知類型との関係: **DEFECTS.md D5 系** (引数が落ち、代役の値が入る → 引数追加 f2) に近い。ただし完全一致の既知類型は無い (§3)。
本 PR は IR を変えない。修復は子 **#3450 (CI-163)** と **#3451 (CI-164)** へ移した。

## 0. 結論

- issue 本文の前提「IR の引数列 (arg1, arg2, 0, 0) が機械語と一致しない」は**半分だけ正しい**。
  スタック部 (`[rsp+0x20..0x38]` = arg1, arg2, 0, 0) は一致する。不一致はレジスタ部と 5 番目引数の既定値分岐。
- `0x412fc0` の IR は 3 引数で、機械語の 5 番目引数 (`[rsp+0x70]`) の読みと既定値の分岐が無い (§2)。
- 呼出先 `0x41c8c0` の IR は 4 引数 (機械語の 5〜8 番目のスタック引数) しか持たない。機械語の rcx〜r9 は無改変で
  `0x4070e0` へ渡るが、IR では `xor i64 0, 0` に化けて WideCharToMultiByte の CodePage・lpWideCharStr・cchWideChar が定数になる。
- 修復には `0x41c8c0` の 4→8 引数化 (CI-163・呼出元 4 箇所) と、`0x412fc0` の 3→5 引数化 (CI-164・呼出元 3 箇所) が要る。
  呼出元の機械照合を伴い 1 run に収まらないため分割した。
- 本 PR は機械照合の検査器 `verify_abi_3426.py` (IR 非変更・negctl 付き) と対応表。e2e は IR が変わらないので差分 0 (§5)。

## 1. 検査器

`tools/m11/ldfix/verify_abi_3426.py`: capstone で `0x412fc0`・`0x41c8c0`・`0x4070e0` の機械語を照合し、
`boot_final3.ll` の該当 2 関数の形を照合する。不一致は assert で止める (fail-closed)。

- 照合 OK: 機械語 32 命令 + IR 6 項目 (`python3 tools/m11/ldfix/verify_abi_3426.py tools/m11/work/boot_final3.ll --pe <PE>`)。
- ネガティブコントロール 5 件 (`--negctl`): NC1 2 番目スタック引数の位置・NC2 分岐の向き (jne→je)・NC3 既定値 VA の改変・
  NC4 `0x41c8c0` の呼出先・NC5 IR に分岐を追加。**5/5 拒否、NG 0 件**。

## 2. 機械語 ↔ IR の対応表 (`0x412fc0` → `0x41c8c0`)

機械語は `sub rsp,0x48` の後の `[rsp+0x70]` が入口の `[rsp+0x28]` (= 5 番目引数)。

| 項目 | 機械語 (VA) | IR (`boot_final3.ll`) | 判定 |
|---|---|---|---|
| 入口の引数 | rcx = arg1・rdx = arg2・r8 = arg3 と r9 = arg4 は読まず素通し・5 番目は入口 `[rsp+0x28]` | `define function_412fc0(i32 %arg1, i32 %arg2, i64 %arg3)`。5 番目なし。`%arg3` は本体で未使用 | 不一致 (引数数) |
| 5 番目の既定値 | 0x412fc4 `cmp dword [rsp+0x70],0` → 0x412fc9 `jne 0x412fd5`。0 のとき 0x412fcb `mov eax,[rip+0x11d3a57]` (参照先 VA 0x15e6a28) → 0x412fd1 `mov [rsp+0x70],eax` | 分岐なし (1 ブロック) | 不一致 (分岐欠落) |
| 呼出先の rcx | 0x412ff7 `mov ecx,eax` (5 番目または既定値、zero-ext) | 第 1 引数 `sext arg1` (= スタック 5 番目と同じ値) | 不一致 (機械語の rcx は 5 番目 / 既定値) |
| 呼出先の rdx | 0x412ff9 `mov edx,r10d` (r10 = 0) | 第 2 引数 `sext arg2` | 不一致 (機械語は 0) |
| スタック 5 番目 `[rsp+0x20]` | 0x412fdc `mov [rsp+0x20],rcx` (= 元の arg1) | 第 1 引数 | 一致 |
| スタック 6 番目 `[rsp+0x28]` | 0x412fe1 `mov [rsp+0x28],edx` (= 元の arg2 の下位 32 bit) | 第 2 引数 | 一致 |
| スタック 7・8 番目 | 0x412fe5・0x412fee `mov qword [rsp+0x30|0x38],0` | 第 3・4 引数 `i64 0, i64 0` | 一致 |
| r8・r9 | 0x412fc0 では読まず、そのまま 0x41c8c0 へ渡る | 呼出し引数に含まれない | 欠落 |

`0x41c8c0` (WideCharToMultiByte の薄いラッパ):

| 項目 | 機械語 (VA) | IR (`function_41c8c0`) | 判定 |
|---|---|---|---|
| 引数 | 0x41c8c4〜0x41c8eb が `[rsp+0x70..0x88]` (= 5〜8 番目) を読み `[rsp+0x20..0x38]` へ転送 | 4 引数 `i64 %arg1..%arg4` (= 5〜8 番目と対応) | 一致 (スタック部) |
| レジスタ引数 | rcx・rdx・r8・r9 は無改変で 0x41c8f0 `call 0x4070e0` へ渡る | `%1..%4 = xor i64 0, 0`。CodePage・dwFlags・lpWideCharStr (null)・cchWideChar が定数 0 | 欠落 (4 本) |
| 呼出先 | 0x4070e0 = `jmp qword [rip+0x156a5e2]` (IAT thunk) | `call i32 @WideCharToMultiByte(...)` | 本 run では IAT 名を未照合 |

呼出元 (IR): `0x412fc0` を呼ぶのは `function_413340` の 2 site (`%15 = call (i32 0, i32 0, %14)`・`%21 = call (%20, %18, %14)`) と
`m11_tr_function_412fc0` (8 引数を受けて 3 引数で呼ぶ。a4〜a7 を捨てる)。
`%14` (= `and %rsi.0, 65535`) は機械語の 5 番目 (`mov [rsp+0x20], r13d`) の値で、IR では 3 番目の位置に出ている (#3416 §0)。

## 3. 分類

- **D5 系** (`docs/DEFECTS.md` D5: 引数が落ち、代役の値が入る。修復は引数追加 f2): 最も近い。ただし D5 は xmm 引数の取り違え。
  本件は整数レジスタ引数 (rcx〜r9) の欠落と、5 番目以降の引数の欠落。
- **D7 (スタック引数の 8B ずれ) は該当しない**: 5〜8 番目のスタック位置 (`[rsp+0x20..0x38]`) は一致している (§2)。
- **D21 (呼出し引数が定数でなくスタック番地)** は別。現 IR では出ていない。
- **新規の下位類型候補**: 「呼出先 IR 関数の引数数が機械語の引数 (レジスタ 4 + スタック) より少なく、レジスタ由来の値が `xor 0` へ化ける」。
  DEFECTS.md への登録は修復 (CI-163) と同じ PR で行う。本 PR は docs/DEFECTS.md を変えない。

## 4. issue 本文の前提の訂正

| issue 本文 | 実測 |
|---|---|
| IR の引数列 (arg1, arg2, 0, 0) が機械語 (eax・0・r8/r9 素通し・スタック arg1, arg2, 0, 0) と一致しない | スタック部は一致。不一致はレジスタ部 (rcx = 5 番目/既定値、rdx = 0、r8/r9 の素通し) と 5 番目の既定値分岐 |
| 機械照合付き IR 修復 pass を書く | 修復は IR の関数シグネチャ変更 (0x41c8c0 と 0x412fc0) を伴い、呼出元 7 site の機械照合が要る。1 run に収まらないため CI-163・CI-164 へ分割。本 PR は検査器のみ |

## 5. 検証

測定 commit: **`b0ba2523b`** (コード変更の最後の commit = `verify_abi_3426.py`)。
e2e は IR を変えない (`ldfix_e2e.sh` は検査器を呼ばない)。実測は次の通り。

`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` (rc 0・wall 48.39 s・load 0.41 → 0.91):

| 指標 | base | fix | 判定 |
|---|--:|--:|---|
| stage4 到達 | 4/6 | 4/6 | OK |
| GetMem / FreeMem / FastMM_GetMem | 16 / 6 / 17 | 16 / 6 / 17 | OK |
| units_run / units_total / init_count / icall_ok | 17 / 942 / 18 / 24 | 同一 | OK |
| survey ok / miss / trap | 136 / 14 / 9 | 136 / 14 / 9 | OK |
| judge (`STAGE4_JUDGE`) | `pass: true` | | |

`wasm_size` は base 6025281 / fix 6025495 で差がある。これは既存の修復 pass 群 (`ldfix.py`・`fix_450560.py`・`fix_site_3326.py`) の寄与で、本 PR 由来ではない。

コード差分 (測定 commit から HEAD まで): `git diff b0ba2523b HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/ldfix_e2e.sh` は空 (本 PR の後の commit は REPORT 系のみ)。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `0x41c8c0` の rcx〜r9 が IR に無い (4 引数化・呼出元 4 site) | WideCharToMultiByte の CodePage・lpWideCharStr・cchWideChar が定数 0 / null。呼出元の値が届かない | #3450 (CI-163) |
| `0x412fc0` の 5 番目引数・既定値分岐・3 引数の形・呼出元 `0x413340` の引数取り違え | `%14` (si & 0xffff) の 5 番目を 3 番目と誤認。既定値分岐が無い | #3451 (CI-164) |
| 0x4070e0 の IAT 名 (WideCharToMultiByte) の照合 | 本 run では未照合。IR の名前を前提にしている | #3450 (CI-163) の受入に含める |
