# SHX-T30 (#2579): function_8c5eb0 の unreachable に至る分岐と値の出所、D19/D22/D23 との切り分け (親 #2446 / 関連 #699・#1630)

既知類型との関係: 該当なし (D1a〜D23 のいずれとも違う。新類型 D24 として `docs/DEFECTS.md` に記録。§6)

## 1. 結論

- `function_8c5eb0` の `unreachable` は RetDec の誤変換ではない。**D19 修復 pass `tools/m11/guard699/m11_guard699.py` が挿入した fail-fast ブロック `dec_label_pc_8c5ef5_g699_t` (`call void @llvm.trap()` + `unreachable`)** である。function_8c5eb0 の IR にある `unreachable` はこの 1 箇所だけ。
- trap に至る分岐は次の 2 条件の連言: **件数 `i32 [X+0x14]` ≤ 0** (`icmp sle`) かつ **`arg2` の下位 byte ≠ 0**。
- 機械語では同じ経路は正常に進む。件数 ≤ 0 で本体を飛ばした後、`arg2` 下位 byte ≠ 0 なら、`arg3` ≠ 0 のとき先に `8c6071`〜`8c607f` で `call 0x8ca670(arg3, obj)` を呼び、続けて `8c608d` で `call 0x410360` を呼んでその戻り値を `[rbp+0x80]` に格納し、`8c60df` で返す (§4)。`_t` の fail-fast はこの正常経路を止めている。`m11_guard699.py` の「8c608d の rdx は未確定」という理由は成り立たない。機械語は 8c608d〜8c6094 で呼出し側が rdx を設定せず、`410360` は rdx を読まずに vtable 先へ渡す (§4)。
- D19・D22・D23 のいずれとも違う。件数 0 のガードは IR に正しく復元されている (§6)。よって新類型 **D24** (修復 pass の fail-fast が正常経路を止める) として `docs/DEFECTS.md` に記録する。
- 試験 (work 内の IR を直接パッチし、commit していない): `_t` を「`call 410360(obj)` → その戻り値を返す」に置換すると、同じ locale0 対照で unit 57 を越え、`units_run` 53 → 110・`dllmain_done=true` になる (§7)。この置換が正しいのは arg3 == 0 の呼出し経路だけで、arg3 ≠ 0 では `call 8ca670(arg3, obj)` を先に行う必要がある (§4・§7)。修復の適用と以後の実測は親 #2446 の受入 3 に移す。
- 未確定: 件数が 0 になる上流 (`function_8c67a0(obj)` の先で list に項目が積まれない理由) は特定していない (§5・§9)。

## 2. 測定条件

- 測定 commit: `26f90ada` (`origin/main`。本 PR の base。本 PR はコードを変えず、REPORT と DEFECTS・DOC_MAP だけを変える)。
- 素材 `work-m11` (`tools/m11/work/`・gitignore) は stale。`boot_final3.ll` の sha256 は `010451ad…` で、REPORT_SHX-T27 §4-F の stale IR と一致する。
- IR の作り直し (REPORT_SHX-T27 §2 と同じ手順): `tools/m11/work/lift_pe.sha256` に `block00031_PE.bin` の sha256 `b2c64da4…` を手で書き、`m11_e2e.sh` (非 `--full`) を実行した。RetDec lift は boot5 だけ。
  - 指紋の出自は未検証 (`--full` は Ghidra が要るため実行できない)。傍証として、ldfix が capstone で PE と突合して `applied` (`ld108=applied` を含む) になっている。
  - `ir_conditions.json`: `ldfix=applied`・`qstore=applied`・`ld108=applied`・`ir_sha256=de46cada…` (boot_final.ll)。`boot_final3.ll` の sha256 は `b96b0c1c…`。
  - REPORT_SHX-T27 の `ir_sha256 6909f85d…` は `ld108` (D20 の修復) 導入前の IR。本 HEAD の IR とは別物。ただし shimx 側の値は §3 のとおり REPORT_SHX-T27 §4-A/§4-D と一致する。
- 機械語: `tools/m11/work/boot2.drc.dsm` (VA 付きの逆アセンブル)。
- 所要: `m11_e2e.sh` 1 分 57 秒。shimx の build は 8.6 秒。`t27_relink.sh locale0` は 2.4 秒。load average と並列数は測定時に記録していない (未記録。以前の「load は低い」は根拠の無い記述だったため削除)。

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
| `8c6071`〜`8c607f` | `mov rcx,[rbp+0x90]`・`mov rdx,[rbp+0x80]`・`call 0x8ca670` | arg3 ≠ 0 のときだけ実行。`8c6084` の前に `call 8ca670(arg3, obj)` (guard699 の `_e` 枝と同じ呼出し) |
| `8c6084`〜`8c608b` | `cmp byte [rbp+0x88],0`・`je 0x8c60df` | `arg2` 下位 byte。0 なら `8c60df` へ |
| `8c608d` | `mov rcx,[rbp+0x80]` | 引数は rcx のみ。**呼出し側は rdx を設定しない** (`410360` は rdx を読まず、`call [rbx-0x50]` で vtable 先へそのまま渡す) |
| `8c6094` | `call 0x410360` | 直接 call (vtable ではない) |
| `8c6099` | `mov [rbp+0x80],rax` | 戻り値を obj スロットへ |
| `8c60a0` | `jmp 0x8c60df` | |
| `8c60df` | `mov rax,[rbp+0x80]`・`ret` | 戻り値 = 410360 の戻り値 |

- 件数 ≤ 0 かつ `arg2` 下位 byte ≠ 0 の機械語の挙動は、arg3 == 0 のとき「`410360(obj)` を呼び、その戻り値を返す」、arg3 ≠ 0 のとき「先に `8ca670(arg3, obj)` を呼び、続けて同じ `410360(obj)` の呼出しと返却」。IR の `_t` (trap) はどちらとも違う。`_t` の修復は arg3 で分ける必要がある。
- 直接 `call 0x8c5eb0` の呼出し元は 111 件 (`E8` rel32 の全走査)。**窓の定義**: 呼出し命令の直前 14 命令で、同じ関数 (`.pdata` の BeginAddress 以降) の中に限る。逆アセンブルは `objdump -d -M intel` の線形列。窓の中で `dl` (`rdx`) と `r8` を明示的に書く最後の命令で判定する (`mov dl, imm` の imm ≠ 0 を dl≠0、`xor edx,edx` を dl=0、`xor r8,r8`・`mov r8, 0` を r8 の定数 0)。窓の外で設定された値は見ていない。結果: dl≠0 が 99 件 (うち r8 が定数 0 が 46 件、定数 0 でない (例: `8d045f` は `mov r8, rsi`) が 53 件)、dl=0 (`xor edx,edx`) が 12 件。定数 0 でない 53 件は arg3 ≠ 0 の経路になりうるが、実行時の値は未確認。`8d03f7`〜`8d03fc` (`mov dl,1`・`xor r8,r8`・`call`) は arg3 == 0 の例。`_t` の修復は arg3 の分岐を含める。
- **再現**: `python3 tools/m11/m11_t30_callsites.py <block00031_PE.bin>` (素材は fl-win64 の `extracted/block00031_PE.bin`、sha256 `b2c64da4…`)。出力は `direct calls to 0x8c5eb0: 111`・`dl: nz=99 zero=12 none=0 nonconst=0`・`dl nz の r8: zero=46 nonconst=53 none=0` で、本節の値と一致する (2026-10-14 実測)。
- `m11_guard699.py` の docstring の「8c608d の rdx は未確定」と、`REPORT_699.md` §1 の注釈「機械語 8c608d は vtable 呼出し」は、逆アセンブルと一致しない。修復時に直す (§9)。
- `function_8c5eb0` の IR で `unreachable` を含むのは `_t` だけ。`function_8c67a0`・`function_8c7c80`・`function_8c5c90`・`function_8c7450`・`function_410360` などの呼出し先にも `unreachable` は無い。`unreachable` の関数名の走査では、stale IR の 99 件から、新 IR で 100 件に増えたのは `function_8c5eb0` の 1 件 (`_t`) だけ。よって trap は `_t` で発生し、trap の発生は「件数 ≤ 0 かつ flag ≠ 0」の成立と同値。

## 5. 条件値の出所

- **flag (`arg2` 下位 byte)**: 呼出し元 `function_56fde0` の IR (`boot_final3.ll` の 200789 行・200802 行) では `arg2 = (定数 & -256) | 1` で、下位 byte は定数 `1`、`arg3` は `i64 0`。機械語 (`.pdata` の `56fde0`〜`5702bf`) では、epilogue `5702ba` の直前に `570291 mov dl,1`・`570293 xor r8,r8`・`570296 call 0x8c5eb0` があり、同様に `5702a9 mov dl,1`・`5702ab xor r8,r8`・`5702ae call 0x8c5eb0` がある。呼出しの個数 (2) と値 (dl の下位 byte = 1、arg3 = 0) は IR の記述と整合する。ただし IR の行番号と VA の 1 対 1 の対応は未突合 (`boot_final3.ll` は本 run に無い)。同型の例として `0x8d03f7`〜`0x8d03fc` (`.pdata` 上 `8d0380` 始まりの別関数) も arg3 == 0。他の呼出し元の arg3 は §4 のとおり一様ではない。
- **件数 (`[X+0x14]`, i32)**: `X = function_8c67a0(obj)` = `function_8c7c80(function_8c5c90(), obj)`。機械語 `8c67a0`〜`8c67b3` は rdx に 0 を入れず、`8c5c90` の戻り値を rcx、`obj` を rdx にして `8c7c80` を呼ぶ。`8c5c90` (`8c5c94`〜`8c5cb3`) は引数を読まず、遅延初期化済みのグローバル `[rip+0xb49d1e]` を返す getter。`obj` は 56fde0 が渡す定数アドレス (LVA の `1469800` / `1470128`)。件数 ≤ 0 は trap の発生から確定する (§4)。**件数の正確な値と、どの処理で件数が 0 になるかは未測定**。GetLocaleInfoW の 0 返却との因果も確認していない。

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
- 有効範囲: 試験 A の置換は arg3 == 0 の経路 (56fde0 → 8c5eb0) でだけ機械語と一致する。arg3 ≠ 0 では `8c6071`〜`8c607f` の `call 8ca670(arg3, obj)` が抜けるため、この置換を arg3 ≠ 0 の呼出しに使うと機械語と食い違う。
- 修復案 (未試験・#2446 受入 3 で検証): `_t` を arg3 で分ける。arg3 == 0 のときは試験 A と同じく `call 410360(obj)`・`ret`。arg3 ≠ 0 のときは先に `call 8ca670(arg3, obj)` (`_e` 枝と同じ呼出し) を行い、続けて同じ `call 410360(obj)`・`ret`。

## 8. 検証の鮮度

- 測定 commit: `26f90ada` (コードを変えた最後の commit)。本 PR はコードを変えない (変更は REPORT_SHX-T30.md・DEFECTS.md・DOC_MAP.md のみ)。差分の確認は `git diff 26f90ada acc12101 -- tools/m11 tools/shimx ':!tools/m11/REPORT_SHX-T30.md'` (出力 0 行)。範囲の終点を固定 hash (`acc12101`・再測定した HEAD) にしたので、merge 後も同じ結果になる。`acc12101` より後に `tools/m11` へ増えたのは再現スクリプト `m11_t30_callsites.py` だけで、`git diff --stat acc12101 HEAD -- tools/m11 tools/shimx ':!tools/m11/REPORT_SHX-T30.md'` で確認できる。最終 HEAD の hash は PR 本文の『検証』に書く。
- コミット済み HEAD `acc12101` で、IR を元に戻したうえで `build.sh --trace --soft` と `t27_relink.sh` (`locale0`) を再実行し、§3 の baseline (`units_run=17`) と対照 (`units_run=53`・`threw=unreachable`・`total_calls=173`) が再現することを確認した。以後の commit は REPORT の文言だけを変えている。
- `work-m11` の IR は stale。本 REPORT の IR は §2 の手順で作り直したもので、指紋の出自は未検証。

## 9. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 件数 0 の上流 (`function_8c67a0(obj)` の list に項目が積まれない理由。GetLocaleInfoW 0 との因果) | trap の直接の原因 (`_t`) は確定したが、件数 0 を生む根元は未特定 | #2446 (unit 57 の切り分け) にコメント |
| `_t` の修復 (arg3 で分けた機械語化・§4・§7) の適用と、units_run ≥ 58 の実測 | 現行 IR は unit 57 で止まる | #2446 受入 3 (arg3 ≠ 0 の分岐を含めること) |
| guard699 の docstring (rdx 未確定) と `REPORT_699.md` §1 の注釈 (vtable 呼出し) の誤り | 次に読む人を誤らせる | 上の修復と同じ作業 (#2446) |
| `m11_e2e.sh` の gate が `survey ok=874 != 期待 872` で rc 1 | 回帰ゲートが落ちる。ld108 修復で値が変わったと推定 (未確認) | PM 判断 (`tools/m11/e2e_expect.env` の更新。本 PR では変えない) |
