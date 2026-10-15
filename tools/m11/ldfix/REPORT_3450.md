# REPORT_3450 — function_41c8c0 (WideCharToMultiByte の薄いラッパ) の 8 引数化と呼出元の接続 (#3450 / CI-163、親 #3426 / CI-157)

既知類型との関係: **DEFECTS.md D5 系** (引数が落ち代役の値が入る) に近い。ただし D5 は xmm 引数の取り違えで、本件は整数レジスタ引数 (rcx〜r9) の欠落。新規の下位類型候補の修復 (§6 の行案)。

## 0. 結論

- `function_41c8c0` を 4 引数 (実際はスタック 5〜8 番目) から **8 引数** (rcx・rdx・r8・r9・5〜8 番目) にした。
  WideCharToMultiByte の CodePage・dwFlags・lpWideCharStr・cchWideChar は、`xor i64 0, 0` の 4 本を除き rcx〜r9 に接続した。
- 呼出元 4 箇所のうち **3 箇所は機械語の呼出し直前と照合して接続**した (`function_41c260` の 2 site・`m11_tr_function_41c8c0`)。
  `function_412fc0` の 1 site は、rdx・r8・スタック 5〜8 番目は照合済みだが、**rcx (5 番目/既定値) と r9 は IR に値が無く 0 のまま残した** (残件は #3451 CI-164)。
- ldfix_e2e の stage4・survey は base と同一 (stage4 到達 4/6、survey ok 136・miss 14・trap 9、judge `pass: true`)。wasm_size は +229 B (base 比)。

## 1. 呼出規約 (IR の正)

このプロジェクトの IR は、N 引数の関数が「機械語の rcx・rdx・r8・r9・5 番目・6 番目…」の先頭 N 個を受け取る形を取る
(他の関数の例: `function_102b700(i64 ×5)`・`m11_tr_function_102b700` が `a0..a4` を渡す)。
旧 `function_41c8c0(i64 %arg1..%arg4)` は 5〜8 番目だけを持ち、機械語の rcx〜r9 を受ける引数が無かった (REPORT_3426 §2)。

## 2. 機械語照合 (呼出し直前の rcx〜r9)

検査器 `verify_abi_3426.py --fixed` が capstone で照合する (直線区間の完全一致 + 引数レジスタ無改変)。

| 呼出元 | call (VA) | rcx | rdx | r8 | r9 | 5〜8 番目 | 判定 |
|---|---|---|---|---|---|---|---|
| `function_41c260` 1 site (arg1≠0 経路) | 0x41c2a8 | 0xfde9 (`mov ecx,0xfde9` @0x41c283) | 0 (`xor edx,edx` @0x41c288) | 素通し (区間内で未書込 = entry r8 = `%arg3`) | zext(edi) (`mov r9d,edi` @0x41c28a、edi は entry r9 @0x41c26c) | `%arg1` (rbx)・`%2` (esi・sext)・0・0 | 照合済み |
| `function_41c260` 2 site (arg1=0 経路) | 0x41c352 | 0xfde9 (@0x41c325) | 0 (@0x41c32a) | 素通し | zext(edi) (@0x41c32c) | 0・0・0・0 | 照合済み |
| `function_412fc0` | 0x412ffc | `mov ecx,eax` (@0x412ff7・eax は 5 番目/既定値) **IR に値なし → 0 のまま** | 0 (`xor r10,r10`・`mov edx,r10d` @0x412ff9) | 素通し (`%arg3`) | 素通し **IR に値なし → 0 のまま** | `%0`・`%1`・0・0 | 部分照合 (残件 #3451) |
| `m11_tr_function_41c8c0` | (icall 経由・間接) | a0 | a1 | a2 | a3 | a4〜a7 | 規約 (他の tr と同形) |

- 0x41c8c0 の区間 [0x41c8c0, 0x41c8f0) で rcx・rdx・r8・r9 を書く命令は 0 件 (`no_write`)。0x41c8f0 の `call 0x4070e0` は IAT thunk で、IAT の名前は **kernel32.dll!WideCharToMultiByte** (pefile で確認。REPORT_3426 §6 の持ち越し項目)。
- 412fc0 の rcx・r9 が IR に無いのは CI-164 の範囲 (5 番目引数の読みと既定値分岐、3 引数→5 引数化)。0x413340 の 412fc0 呼出しの第 3 引数も REPORT_3426 §2 のとおり取り違えがあり、CI-164 で扱う。

## 3. 修復の内容 (`fix_abi_3450.py`、行単位の完全一致置換・件数不一致で停止)

- 定義: `@function_41c8c0(i64 %arg1..%arg8)`。WideCharToMultiByte の引数は `CodePage=%arg1`・`dwFlags=%arg2`・`lpWideCharStr=%arg3`・`cchWideChar=%arg4`・`lpMultiByteStr=%arg5`・`cbMultiByte=%arg6`・`lpDefaultChar=%arg7`・`lpUsedDefaultChar=%arg8`。`xor i64 0, 0` 4 本は削除。
- 呼出元: 412fc0 1 本・41c260 2 本・tr 1 本の計 4 本を 8 引数化 (§2 の表どおり)。
- 変えた IR 行: 定義 1 行・本体 1 ブロック (`xor` 4 本を含む 13 行 → 9 行)・呼出し 4 行。

## 4. 検証

測定 commit: **`3fd7f1791`** (コード変更の最後の commit)。ここから HEAD までのコード差分:
`git diff 3fd7f1791 HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/ldfix_e2e.sh` は空 (本 PR の後の commit は REPORT のみ)。

### 4-1. 機械照合・ネガティブコントロール (`verify_abi_3426.py`)

| 検査 | 結果 |
|---|---|
| `fix_abi_3450.py` の機械照合 | 28 項目 OK |
| `verify_abi_3426.py --fixed` (修復後 IR) | 32 項目 OK (機械 28 + IR 4) |
| `verify_abi_3426.py --negctl` (修復前・従来 NC1〜NC5) | 5/5 拒否・NG 0 |
| `verify_abi_3426.py --fixed --negctl` | NC6 (0x41c8c0 の先頭に `xor ecx,ecx` を入れる = rcx 転送の改変) 拒否 OK、NC7 (41c260 の 1 呼出元を 4 引数に戻す) 拒否 OK。**NG 0** |
| 修復パイプラインの出力 `tools/m11/ldfix/work/ldfix_fixed.ll` に `--fixed` | 照合 OK |

### 4-2. e2e 実測 (HEAD `3fd7f1791`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh`)

- rc 0・wall **59.79 s** (user 56.95 s)・load average 開始 0.30 → 終了 0.79 (uptime、1 分平均)・並列 2 (base/fix の survey)。
- 再現 (修復前 commit `b0ba2523b` 時点の REPORT_3426 の測定) との比較: wasm_size は 6025495 → 6025510 (+15 B が本修復分。修復前の base は 6025281 のまま)。

| 指標 | base | fix | 判定 |
|---|--:|--:|---|
| stage4 到達 | 4/6 | 4/6 | OK |
| GetMem / FreeMem / FastMM_GetMem | 16 / 6 / 17 | 16 / 6 / 17 | OK |
| units_run / units_total / init_count / icall_ok | 17 / 942 / 18 / 24 | 同一 | OK |
| survey ok / miss / trap | 136 / 14 / 9 | 136 / 14 / 9 | OK |
| wasm_size | 6025281 | 6025510 | +229 B (修復 pass 群の寄与。本修復は +15 B) |
| judge (`STAGE4_JUDGE`) | `pass: true` | | OK |

- survey の `top_frame_idx` (trap の頂点フレームの wasm 関数インデックス) は、件数の並びは base と同じで、キー 5 本 (1877・5265・14877・14879・14881) が +1 ずれた (1878・5266・14878・14880・14882)。ok/miss/trap の件数・trap 種別は同一。
  wasm の関数並びが 1 つ動いたことによる (**推定**。本 run では関数 index の対応表を取っていない)。意味差は件数に出ていない。

### 4-3. KPI

起動・GUI に関わる PR ではない。ただし stage4 (起動の段階) は base と同じ 4/6 で、最初のウィンドウの有無は本 run では測っていない (動かしていない)。

## 5. 残件・未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `function_412fc0` の 1 site の rcx (5 番目/既定値) と r9 (素通し) が IR に無く、0 のまま | WideCharToMultiByte の呼出元 (412fc0 経由) の CodePage (0 = CP_ACP) と cchWideChar (0) は、修復前と同じ値。lpWideCharStr は r8 (`%arg3`) へ変わった (機械照合済み)。WideCharToMultiByte は cchWideChar=0 で 0 を返すため、本 run の stage4 では差が出ていない | #3451 (CI-164)。412fc0 を 5 引数化する際に、この site の rcx と r9 を置き換える |
| 0x413340 の 412fc0 呼出しの第 3 引数の取り違え (#3416 §0) | 412fc0 の r8 (`%arg3`) に入る値が機械語と違う可能性 | #3451 (CI-164) |
| DEFECTS.md への類型登録 (§6 の行案) | 類型カタログに未登録 | PM 判断 (`docs/WORKFLOW.md` §5: DEFECTS.md 自体の直接編集は PM 判断) |
| survey の `top_frame_idx` の 5 キーの +1 ずれの対応 (推定: wasm 関数並びの変化) | 件数は同一のため判定に影響なし | 次回の survey 更新時に関数 index の対応表で確認 (#3451 の再測定の範囲) |

## 6. DEFECTS.md の行案 (PM 判断用・本 PR では DEFECTS.md を変えない)

| ID | 分類 | 状態 | 症状 | 根本原因 | 観測 | 検出信号 | 修復 |
|---|---|---|---|---|---|---|---|
| D26 | fe (機構は IR で確認。発生源は未特定) | **新規** (#3426 / CI-157 の判定・修復 #3450) | 呼出先 IR 関数の引数数が機械語の引数 (rcx〜r9 + スタック) より少なく、レジスタ由来の値が `xor i64 0, 0` になる (WideCharToMultiByte の CodePage・dwFlags・lpWideCharStr・cchWideChar が定数 0 / null) | 呼出先 IR の定義がスタック 5〜8 番目だけを持ち、rcx〜r9 を受ける引数が無い | `0x41c8c0` (4 引数・`xor 0` 4 本) | 呼出先の機械語で rcx〜r9 が無改変で次の call へ渡ること (`no_write`) と、IR の `xor i64 0, 0` の本数 | 呼出先を機械語の順 (rcx〜r9・5〜8) で全数化し、呼出元を直前の rcx〜r9 と照合して接続 (`fix_abi_3450.py`) |

## 7. 再現

```
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
python3 tools/m11/ldfix/verify_abi_3426.py tools/m11/work/boot_final3.ll --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" [--negctl]
python3 tools/m11/ldfix/verify_abi_3426.py tools/m11/ldfix/work/ldfix_fixed.ll --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --fixed [--negctl]
```

素材: `fl-win64`・`work-m11`・`work-liftdiff`・`toolchain-emsdk`・`toolchain-retdec` (`oc_artifacts:` 行どおり)。`tools/m11/work/` は読込のみで commit していない。

検証 (`docs/WORKFLOW.md` §6): `git status --porcelain=v1 -- tools/m11/ldfix` は空 (work/ は gitignore)。`find tools/m11/ldfix -type f -size +20M -not -path '*/work/*'` は空。
