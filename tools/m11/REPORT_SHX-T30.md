# SHX-T30 (#2579): function_8c5eb0 の unreachable に至る分岐と値の出所、D19/D22/D23 との切り分け (親 #2446 / 関連 #699・#1630)

## 1. 結論

- `function_8c5eb0` の `unreachable` は RetDec の誤変換ではない。**D19 修復 pass `tools/m11/guard699/m11_guard699.py` が挿入した fail-fast ブロック `dec_label_pc_8c5ef5_g699_t` (`call void @llvm.trap()` + `unreachable`)** である。function_8c5eb0 の IR にある `unreachable` はこの 1 箇所だけ。
- trap に至る分岐は次の 2 条件の連言: **件数 `i32 [X+0x14]` ≤ 0** (`icmp sle`) かつ **`arg2` の下位 byte ≠ 0**。
- 機械語では同じ経路は正常に進む。件数 ≤ 0 で本体を飛ばした後、`arg2` 下位 byte ≠ 0 なら `8c608d` で `call 0x410360` を呼び、その戻り値を `[rbp+0x80]` に格納して `8c60df` で返す (§4)。`_t` の fail-fast はこの正常経路を止めている。`m11_guard699.py` の「8c608d の rdx は未確定」という理由は、機械語の 8c608d〜8c60a0 が rdx を使わないため成り立たない。
- D19・D22・D23 のいずれとも違う。件数 0 のガードは IR に正しく復元されている (§6)。よって新類型 **D24** (修復 pass の fail-fast が正常経路を止める) として `docs/DEFECTS.md` に記録する。
- 試験 (work 内の IR を直接パッチし、commit していない): `_t` を機械語どおり「`call 410360(obj)` → その戻り値を返す」に置換すると、同じ locale0 対照で unit 57 を越え、`units_run` 53 → 110・`dllmain_done=true` になる (§7)。修復の適用と以後の実測は親 #2446 の受入 3 に移す。
- 未確定: 件数が 0 になる上流 (`function_8c67a0(obj)` の先で list に項目が積まれない理由) は特定していない (§5・§9)。

## 2. 測定条件

- 測定 commit: `26f90ada` (`origin/main`。本 PR の base。本 PR はコードを変えず、REPORT と DEFECTS・DOC_MAP だけを変える)。
- 素材 `work-m11` (`tools/m11/work/`・gitignore) は stale。`boot_final3.ll` の sha256 は `010451ad…` で、REPORT_SHX-T27 §4-F の stale IR と一致する。
- IR の作り直し (REPORT_SHX-T27 §2 と同じ手順): `tools/m11/work/lift_pe.sha256` に `block00031_PE.bin` の sha256 `b2c64da4…` を手で書き、`m11_e2e.sh` (非 `--full`) を実行した。RetDec lift は boot5 だけ。
  - 指紋の出自は未検証 (`--full` は Ghidra が要るため実行できない)。傍証として、ldfix が capstone で PE と突合して `applied` (`ld108=applied` を含む) になっている。
  - `ir_conditions.json`: `ldfix=applied`・`qstore=applied`・`ld108=applied`・`ir_sha256=de46cada…` (boot_final.ll)。`boot_final3.ll` の sha256 は `b96b0c1c…`。
  - REPORT_SHX-T27 の `ir_sha256 6909f85d…` は `ld108` (D20 の修復) 導入前の IR。本 HEAD の IR とは別物。ただし shimx 側の値は §3 のとおり REPORT_SHX-T27 §4-A/§4-D と一致する。
- 機械語: `tools/m11/work/boot2.drc.dsm` (VA 付きの逆アセンブル)。
- 所要: `m11_e2e.sh` 1 分 57 秒 (load は低い)。shimx の build は 8.6 秒。`t27_relink.sh locale0` は 2.4 秒。

## 3. 実測 (測定 commit `26f90ada`・shimx の trace soft 構成)

| 条件 | units_run | init_count_var | icall ok/miss | dllmain_done | boot_rc | threw | total_calls | ftrace 行 |
|---|---|---|---|---|---|---|---|---|
| baseline (差し替え無し) | 17 | 0 | 24/1 | true | 1 | null | 106 | 未計測 |
| 対照 locale0 (`t27_relink.sh locale0`) | 53 | 57 | 236/3 | false | null | **unreachable** | 173 | 0 |
| 試験 A: locale0 + `_t` を機械語化 (§7。未コミット) | 110 | 0 | 437/4 | true | 1 | null | 未記録 | 0 |

- baseline と locale0 は REPORT_SHX-T27 §4-A・§4-D の値と完全に一致する (`units_run` 17 / 53・`threw` null / unreachable・`total_calls` 106 / 173)。
- `m11_e2e.sh` (非 `--full`・本 HEAD): `reached_stage=4`、`stop_reason = trap "unreachable" @ function_8c5eb0 <- function_56fde0 <- m11_tr_function_56fde0 <- m11_icall <- function_4120c0`。ただし judge が `TOLERANT_GATE_FAILED: survey ok=874 != 期待 872` を出し、`m11_e2e.sh` は rc 1 で終わった (§9)。

## 4. 分岐の特定 (IR と機械語の突合)

IR (`boot_final3.ll`・guard699 適用後の `function_8c5eb0`):

```
dec_label_pc_8c5ef5:
  %6 = call i64 @function_8c67a0(i64 %stack_var_8.0.reload)   ; X = %6
  %9 = load i32, ptr [X+20]                                   ; 件数
  %g699 = icmp sle i32 %9, 0
  br i1 %g699, label %dec_label_pc_8c5ef5_g699, label %dec_label_pc_8c5f23
dec_label_pc_8c5ef5_g699:
  %g699a = and i64 %arg2, 255
  %g699b = icmp ne i64 %g699a, 0
  br i1 %g699b, label %..._g699_t, label %..._g699_e          ; ..._t が trap
..._g699_t:
  call void @llvm.trap()
  unreachable
```

機械語 (`boot2.drc.dsm`):

| VA | 命令 | 対応 |
|---|---|---|
| `8c5f15`〜`8c5f18` | `cmp`・`jg 0x8c6066` | 件数 ≤ 0 で本体を飛ばす。guard の `icmp sle` と一致 |
| `8c6066`〜`8c606f` | `cmp qword [rbp+0x90],0`・`je 0x8c6084` | arg3 == 0 |
| `8c6084`〜`8c608b` | `cmp byte [rbp+0x88],0`・`je 0x8c60df` | `arg2` 下位 byte。0 なら `8c60df` へ |
| `8c608d` | `mov rcx,[rbp+0x80]` | 引数は rcx のみ。**rdx は設定もされず使われもしない** |
| `8c6094` | `call 0x410360` | 直接 call (vtable ではない) |
| `8c6099` | `mov [rbp+0x80],rax` | 戻り値を obj スロットへ |
| `8c60a0` | `jmp 0x8c60df` | |
| `8c60df` | `mov rax,[rbp+0x80]`・`ret` | 戻り値 = 410360 の戻り値 |

- 件数 ≤ 0 かつ `arg2` 下位 byte ≠ 0 の機械語の挙動は「`410360(obj)` を呼び、その戻り値を返す」。IR の `_t` (trap) はこれと違う。
- `m11_guard699.py` の docstring の「8c608d の rdx は未確定」と、`REPORT_699.md` §1 の注釈「機械語 8c608d は vtable 呼出し」は、逆アセンブルと一致しない。修復時に直す (§9)。
- `function_8c5eb0` の IR で `unreachable` を含むのは `_t` だけ。`function_8c67a0`・`function_8c7c80`・`function_8c5c90`・`function_8c7450`・`function_410360` などの呼出し先にも `unreachable` は無い。`unreachable` の関数名の走査では、stale IR の 99 件から、新 IR で 100 件に増えたのは `function_8c5eb0` の 1 件 (`_t`) だけ。よって trap は `_t` で発生し、trap の発生は「件数 ≤ 0 かつ flag ≠ 0」の成立と同値。

## 5. 条件値の出所

- **flag (`arg2` 下位 byte)**: 呼出し元 `function_56fde0` の IR (`boot_final3.ll` の 200789 行・200802 行) では `arg2 = (定数 & -256) | 1` で、下位 byte は定数 `1`、`arg3` は `i64 0`。機械語にも同型の呼出し `mov dl,1`・`xor r8,r8`・`call 0x8c5eb0` がある (`0x8d03f7`〜`0x8d03fc`)。ただし `56fde0` 本体の VA と IR の対応は未突合。
- **件数 (`[X+0x14]`, i32)**: `X = function_8c67a0(obj)` = `function_8c7c80(function_8c5c90(obj,0), obj)`。`obj` は 56fde0 が渡す定数アドレス (LVA の `1469800` / `1470128`)。件数 ≤ 0 は trap の発生から確定する (§4)。**件数の正確な値と、どの処理で件数が 0 になるかは未測定**。GetLocaleInfoW の 0 返却との因果も確認していない。

## 6. D19 / D22 / D23 との切り分け

| 類型 | 既存の症状・機構 | 本件との比較 | 判定 |
|---|---|---|---|
| D19 | 件数 0 のループで本体が実行される (先頭ガード脱落) | ガードは IR に復元済み。件数 ≤ 0 で本体を飛ばす分岐は機械語 `8c5f18` と一致する。停止は本体ではなく、復元したガードの後の `_t` | 違う |
| D22 | callee が書いた stack の内部 read が undef になる | `_t` の条件は `arg2` と件数で、どちらも IR 上で undef に依存しない | 違う |
| D23 | 入れ子手続が親フレームを読み、unit 18 で Halt0 | 停止は unit 57。unit 18 の D23 は baseline で残るが、unit 57 の trap とは別の停止 | 違う |
| **D24 (新)** | 修復 pass の fail-fast が正常経路を止める | 本件。機械語は `410360` を呼んで返すが、`_t` は trap | **新規** |

## 7. 修復案の試験 (未コミット・work 内のみ)

- 試験 A: `boot_final3.ll` の `_t` だけを次に置換した (元の IR は `$RUNNER_TEMP` に退避し、試験後に `cmp` で一致を確認して戻した)。

```
dec_label_pc_8c5ef5_g699_t:
  %g699t = call i64 @function_410360(i64 %stack_var_8.0.reload)
  ret i64 %g699t
```

- 結果: locale0 対照で `units_run=110`・`init_count_var=0`・`dllmain_done=true`・`boot_rc=1`・`threw=null`。unit 57 の trap は消え、DllMain の完了まで進んだ。ftrace は 0 行 (file API には届かない)。
- この試験は shimx 経路 (`build.sh --trace --soft` → `t27_relink.sh locale0`) で行った。`m11_build.sh` は `boot_final3.ll` を再生成するため、試験 IR を m11 経路の検証には使っていない。

## 8. 検証の鮮度

- 測定 commit: `26f90ada`。本 PR はコードを変えない (変更は REPORT_SHX-T30.md・DEFECTS.md・DOC_MAP.md のみ)。
- 本 PR の commit 後の HEAD で、IR を元に戻したうえで `build.sh --trace --soft` と `t27_relink.sh locale0` を再実行し、§3 の値 (baseline 17 / locale0 53 / unreachable) が再現することを確認する (§10)。
- `work-m11` の IR は stale。本 REPORT の IR は §2 の手順で作り直したもので、指紋の出自は未検証。

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 件数 0 の上流 (`function_8c67a0(obj)` の list に項目が積まれない理由。GetLocaleInfoW 0 との因果) | trap の直接の原因 (`_t`) は確定したが、件数 0 を生む根元は未特定 | #2446 (unit 57 の切り分け) にコメント |
| `_t` の修復 (機械語化・§7) の適用と、units_run ≥ 58 の実測 | 現行 IR は unit 57 で止まる | #2446 受入 3 (本 issue の結論を先行として使う) |
| guard699 の docstring (rdx 未確定) と `REPORT_699.md` §1 の注釈 (vtable 呼出し) の誤り | 次に読む人を誤らせる | 上の修復と同じ作業 (#2446) |
| `m11_e2e.sh` の gate が `survey ok=874 != 期待 872` で rc 1 | 回帰ゲートが落ちる。ld108 修復で値が変わったと推定 (未確認) | PM 判断 (`tools/m11/e2e_expect.env` の更新。本 PR では変えない) |
