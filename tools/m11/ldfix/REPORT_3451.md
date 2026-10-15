# REPORT_3451 — function_412fc0 の 5 引数化・5 番目の既定値分岐と呼出元 0x413340 の付け直し (#3451 / CI-164、親 #3426 / CI-157)

既知類型との関係: **DEFECTS.md D5 系** (引数が落ち代役の値が入る) と **D26 (#3450 で登録候補)** の併発。呼出先の引数数不足 (D26) を #3450 で解いた後に残った、呼出元の 5 番目引数の取り違え (0x413340 の 3 番目と 5 番目) と既定値分岐の欠落。

## 0. 結論

- `function_412fc0` を機械語の引数形 (rcx・rdx・r8・r9・5 番目) の **5 引数** にした。5 番目が 0 のとき既定値 global (VA 0x15e6a28) を使う分岐 (`select`) を入れた。
- 呼出元 3 site を付け直した: `0x413340` の 2 site (0x41338b・0x4133bc) と `m11_tr_function_412fc0`。
  0x413340 の 3 番目 (`%14`) の取り違えは、5 番目 (`[rsp+0x20]` = `r13d` = `si`) へ直した。
- #3450 の残件 (412fc0 の rcx と r9 が 0 のまま) は、これで解消した。
- e2e (`ldfix_e2e.sh`) は rc 0・judge `pass: true`。stage4 は base・fix ともに 4/6、survey は ok 136・miss 14・trap 9 で同一。
  **ただし stage4 の GetMem が base 16 → fix 17 に変わった (§4-2)**。因果は未確認。

## 1. 機械語 ↔ IR の対応 (修復後)

`0x412fc0` (入口): rcx = arg1・rdx = arg2・r8 = arg3・r9 = arg4 (素通し)・5 番目 = 入口 `[rsp+0x28]` (`[rsp+0x70]` は sub 後)。

| 項目 | 機械語 (VA) | 修復後の IR (`function_412fc0`) |
|---|---|---|
| 引数形 | rcx・rdx・r8・r9・5 番目 | `(i64 %arg1..%arg5)` |
| 5 番目の既定値 | 0x412fc4 `cmp [rsp+0x70],0` → 0x412fcb `mov eax,[0x15e6a28]` | `%p5z = icmp eq %p5, 0`・`%dflt = load [18770472]`・`%cp32 = select` |
| CodePage (呼出先 rcx) | 0x412ff7 `mov ecx,eax` (5 番目/既定値) | `%cp = zext %cp32` |
| dwFlags (呼出先 rdx) | 0x412ff9 `mov edx,r10d` (= 0) | `i64 0` |
| lpWideCharStr (呼出先 r8) | 素通し (r8 = 入口 r8) | `%arg3` |
| cchWideChar (呼出先 r9) | 素通し (r9 = 入口 r9) | `%arg4` |
| lpMultiByteStr・cbMultiByte (stack 5・6) | 0x412fdc `[rsp+0x20]=rcx`・0x412fe1 `[rsp+0x28]=edx` | `%arg1`・`%arg2` |

呼出元 (0x413340・修復後):

| site | call (VA) | rcx | rdx | r8 | r9 | 5 番目 |
|---|---|---|---|---|---|---|
| 1 | 0x41338b | 0 (`xor ecx,ecx`) | 0 (`xor edx,edx`) | `arg2` | `zext(arg3)` | `%14` (`r13d` = zext si) |
| 2 | 0x4133bc | `*arg1` (`mov rcx,[rax]`・前段 `%ldfx3326a`) | `edi` (site1 の結果) | `arg2` | `zext(arg3)` | `%14` |

- 旧 IR は site1・site2 とも 3 番目に `%14` を入れていた (機械語の r8 = arg2 と取り違え)。
- 機械照合: `fix_abi_3451.py` の `check_fixed3_machine` が 59 項目 OK (412fc0 の 5 引数形・既定値 global・0x413340 の 2 site の直前区間を capstone で完全一致)。
- site2 の rcx は、前段 `fix_site_3326` が入れた `%ldfx3326a` (= `*arg1`) をそのまま使う。前段と同じ load を二重に入れない。

## 2. 検証

測定 commit: **`71a70dbfb`** (コード変更の最後の commit。`fix_abi_3451.py` の新設と `ldfix_e2e.sh` への 1g 追加)。
ここから HEAD までのコード差分: `git diff 71a70dbfb HEAD -- tools/m11/ldfix/*.py tools/m11/ldfix/ldfix_e2e.sh` は、本 REPORT の追加のみ (commit 後に追加した REPORT_3451.md・DOC_MAP の登録以外に差分は無い)。

### 2-1. 機械照合・ネガティブコントロール (`fix_abi_3451.py --negctl`)

| 検査 | 結果 |
|---|---|
| `check_fixed3_machine` (修復前 IR に適用する gate) | 59 項目 OK |
| 修復後 IR の `check_fixed3_ir` | 6 項目 OK |
| NC1 413340 site2 の 5 番目を 3 番目 (`%18`) に戻す | 拒否 OK |
| NC2 412fc0 の既定値 global の番地を +8 | 拒否 OK |
| NC3 412fc0 の 5 番目分岐 (select) を除去 | 拒否 OK |
| NC4 site1 の r9 を zext(arg4) に改変 | 拒否 OK |
| NC5 機械語 0x413383 の `mov r9d,ebx` を `mov r9d,esi` に改変 (gate) | 拒否 OK |
| **NG 件数** | **0** |

### 2-2. e2e 実測 (測定 commit `71a70dbfb`・`FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh`)

- rc 0・wall **57 s**・load average 開始 0.66 → 終了 0.66 (uptime の 1 分平均)・並列 2 (base/fix の survey)。
- 素材: `fl-win64` は `extracted/block00031_PE.bin` のみ展開。`work-m11`・`work-liftdiff`・`toolchain-emsdk`・`toolchain-retdec` は展開済み。`tools/m11/work/` は読込のみ。

| 指標 | base | fix | 判定 |
|---|--:|--:|---|
| stage4 到達 | 4/6 | 4/6 | OK |
| GetMem | 16 | 17 | +1 (§4-2・因果未確認) |
| FreeMem | 6 | 6 | OK |
| FastMM_GetMem(407a50) | 17 | 18 | +1 (GetMem と同じ増分) |
| units_run / units_total / init_count / icall_ok | 17 / 942 / 18 / 24 | 同一 | OK |
| survey ok / miss / trap | 136 / 14 / 9 | 136 / 14 / 9 | OK |
| wasm_size | 6025478 | 6025756 | +278 B (1g 単独の寄与は未測定) |
| judge (`STAGE4_JUDGE`) | `pass: true` | | OK |

### 2-3. 参照用: 前回測定 (#3450 測定 commit `4c3404cff`) との比較

stage4 base 4/6・survey 136/14/9 は前回と同じ。wasm_size は前回 fix 6025510 → 今回 fix 6025756 (+246 B)。
この差は 1g (本修復) を含む。1g 単独の寄与は測っていないので、「本修復分は +N B」とは書かない。

### 2-4. KPI

起動・GUI に関わる PR ではない。ただし stage4 (起動の段階) は base と同じ 4/6 で、最初のウィンドウの有無は本 run では測っていない (動かしていない)。

## 3. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| stage4 の GetMem 16 → 17 (FastMM_GetMem 17 → 18) の因果 | 5 番目既定値分岐の導入で、従来 0 だった `CodePage`・`cchWideChar` の経路が変わった可能性。stage4 のブート本体で 1 回多く確保されている。判定 (judge) は増加を許容する設定 | 次回の stage4 追跡で、GetMem 呼出元の差分を取る (本 PR の範囲外) |
| wasm_size の 1g 単独の寄与 | 本修復分の寄与が未測定 | 同上 |
| DEFECTS.md への D26 登録 | 類型カタログに未登録 | PM 判断 (`docs/WORKFLOW.md` §5) |

## 4. 補足

### 4-1. 既定値 global の参照

既定値 global は VA 0x15e6a28 (IR では `inttoptr (i64 18770472)`)。機械語の `mov eax,[rip+0x11d3a57]` の参照先と一致することを `verify_default_global` で確認した (既存の検査)。

### 4-2. GetMem の増分

survey (unit 隔離) では GetMem・FreeMem・FastMM 系は全 unit で 0 のまま、件数・trap 種別・`first_trap_units` も base と同一。
増分は stage4 のブート本体 (`ldfix_e2e` の `STAGE4_RESULT`) 側だけに出る。
survey の `top_frame_idx` は、前回と同じ 5 キーが +1 ずれている (wasm 関数インデックス。#3450 の REPORT と同じ現象で、本修復では変わらない)。

## 5. 再現

```
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
python3 tools/m11/ldfix/fix_abi_3451.py tools/m11/work/boot_final3.ll out.ll --pe "$FL_WIN64_DIR/extracted/block00031_PE.bin" --negctl
```

`tools/m11/work/` と `tools/m11/ldfix/work/` は commit しない (gitignore)。
