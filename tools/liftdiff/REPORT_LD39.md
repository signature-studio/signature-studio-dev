# liftdiff LD-39 (#1194) — i128 引数・%tagPOINT 値渡し 11 関数の ABI 確認 (途中報告)

> 親: #976 (LD-24)。子 issue 本体: #1194。本節は 1 run で得た**部分達成**の記録 (case 生成・runner 変更は未実装)。
> 既知類型との関係: 該当なし (DEFECTS.md の類型に当てはめる前の観測。IR 署名と機械語入口の不一致は未分類)。

## 1. 対象の確定 (実測)

`tools/m11/work/boot_final3.ll` (素材 work-m11 由来) と `results/m11_closure_verdicts.tsv` で
`ld24_sig_breakdown.py` を実行 (rc=0、入力 50 件 / IR 解決 50 件 / 未解決 0 件)。

| 振り分け | 件数 | 関数 |
|---|---|---|
| #1194 (引数に i128 / %tagPOINT) | **11** | i64(i128) ×8, i64(i64,i128,i64) ×1, i64(i64,i64,i128) ×1, ptr(%tagPOINT) ×1 |

- 受入条件の「i128 を含む 10 関数 + %tagPOINT 1 関数」と一致する。
- 対象 VA: `40c660` `40c750` `4256c0` `664890` `6649b0` `6649c0` `664a80` `442a50` `442b90` `653c80` `691dd0`。

## 2. 機械語入口の確認 (ABI) — 実測

コマンド (commit 対象の script):

```
python3 tools/liftdiff/tests/ld39_abi_dump.py <FL_WIN64_DIR>/extracted/block00031_PE.bin tools/m11/work/boot_final3.ll
```

fl-win64 素材 (`block00031_PE.bin`、image base 0x400000) の `.text` を capstone で逆アセンブルした結果:

| VA | IR 署名 | 機械語入口 (実測) | 読み |
|---|---|---|---|
| `40c660` | `i64 (i128)` | `cvtsd2si rax, xmm0; ret` | **IR 署名と合わない**。入力は xmm0 の double。i128 を読んでいない |
| `40c750` | `i64 (i128)` | `cvttsd2si rax, xmm0; ret` | **IR 署名と合わない** (同上) |
| `4256c0` | `ptr (%tagPOINT)` | `jmp [rip+0x154b732]` → IAT slot `0x1970df8` | import thunk。本体の ABI は呼び先依存で、この VA からは判定できない |
| `664890` | `i64 (i128)` | `sub rsp,0x28; call 0x476930` (tail 相当) | 呼び先 `0x476930` の署名確認が必要 (未実施) |
| `6649b0` / `6649c0` / `664a80` | `i64 (i128)` | `sub rsp,0x28; call <fn>` の薄い wrapper | 呼び先の署名確認が必要 (未実施) |
| `442a50` | `i64 (i128)` | `lea rax,[rbp+0x3e]` を stack に置いて `call 0x4428c0` | 戻り/引数の一部を stack 経由で渡す形。i128 の 2 レジスタ分解とは別の形の可能性 |
| `442b90` | `i64 (i128)` | `call 0x442420` 後に rax の上位 32bit を使う | 呼び先の戻り値 (rax) を読む wrapper。i128 引数は未確認 |
| `653c80` | `i64 (i64,i64,i128)` | `cmp r8,0x7fffffff` → `shl r8,2` | 第 3 引数 (r8) を整数として読む。i128 の上位 64bit 位置 (r9) は読まれていない |
| `691dd0` | `i64 (i64,i128,i64)` | `mov [rbp+0x68],rdx` / `mov byte [rbp+0x70],r8b` | 第 2 引数 (rdx) を 8 バイトで保存し、第 3 は r8b (下位 1 byte) だけ読む。候補 (a) では r8 は i128 の高位になり、第 3 引数の読みと合わない。候補 (b) (rdx = ポインタ) とは整合する (§6.3 で撤回) |

### 観測の要点

1. **IR の署名と機械語の入口が一致しない関数がある** (`40c660` `40c750` 等)。case 生成を IR 署名から
   自動で組むと、読まれない引数を投入して比較するだけになり、判定が無意味になる。
2. `i128` 引数の渡し方は**未決**。候補は (a) 2 レジスタ分解 (rdx:r8 等の低・高) と (b) ポインタ渡し (実体へのポインタ 1 本)。
   機械語の読みは両者で食い違う。653c80 は第 3 引数 (r8) を下位半分として読むので (a) と整合する。691dd0 の読みは (a)/(b) のどちらとも決められない (§6.3)。
   どちらの候補も、この入口だけでは決定できない。(b) の出典 (LLVM Win64 の i128 規約) も本 PR では確認していない。
   受入条件の「i128 を 2 レジスタ分に分解して投入する ABI を機械語で確認」は未達のまま。前提 (a) は未検証。
3. `%tagPOINT` の値渡しは、対象 VA が import thunk のため本体の確認に至らない。

## 3. 未達の受入条件 (本 PR では達成していない)

| 受入条件 | 状態 | 起票先 |
|---|---|---|
| case 生成 (`ldlib/cases.py`) で i128 / %tagPOINT を扱う | 未実装 | #1194 (本 issue に残す) |
| native / wasm 実行器で i128 投入 (渡し方は候補 (a)(b) のどちらか未決)・tagPOINT 投入 | 未実装 | #1194 |
| ABI を機械語で確認 (i128 の渡し方: 2 レジスタ分解 / ポインタ渡し、tagPOINT) | 部分 (§2)。候補 (a)(b) は未決。呼び先の署名確認と IR/機械語不一致の切り分けが残る | #1194 (本 PR の script を使う) |
| 対象のうち実行可能になった件数を実測し REPORT_LD*.md に記録 | 未実施 (実行器が無いため 0 件) | #1194 |
| 既存 pattern の判定を壊していないこと (e2e `liftdiff_e2e.sh --m11-only`) | **未実行**。本 PR は実行器・case を変えていないため、e2e 対象の挙動は変わらない | #1194 |

## 4. 検証

- 測定 commit: 本 PR の commit (script 追加のみ)。`git diff <測定 commit> HEAD -- tools/liftdiff` は 0 行 (同 commit 内で確定)。
- ld24_sig_breakdown.py の実行 rc=0 (§1)。ld39_abi_dump.py の実行 rc=0 (§2)。
- 再現: `tools/liftdiff/tests/ld39_abi_dump.py` は PE と IR を引数で受ける (`work/` 由来、commit しない)。
- 範囲外: 実行器・case 生成の挙動、e2e の PASS/FAIL は本 PR では測っていない。

## 5. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `40c660` `40c750` の IR 署名 (i128) と機械語 (double) の不一致 | case 生成を IR 署名から組むと誤った引数で比較する | #1194 (IR 側の切り分けは #976 の残件として PM 判断) |
| 呼び先 (`476930` `476980` `476500` `4764c0` `476020` `476480` `442420` `4428c0` `653c80` 等) の署名確認 | i128 を取る呼び先の ABI が未確定 | #1194 |
| `4256c0` の import 先の %tagPOINT 署名 | tagPOINT 値渡しの ABI が未確定 | #1194 |
| 11 関数の呼出し側で i128 をポインタ渡しするか確認 (候補 (a)(b) の決定。呼出し元の引数準備コードを見る) | i128 の投入形が決まらないと case 生成の投入形も決まらない | #1194 |
| case 生成・runner 実装・e2e 実測 | 受入条件の大半 | #1194 |

## 6. LD-51 (#1526) 追記: 呼出し側と import 先の実測

> 測定 commit: `dee0e1ee` (origin/main 基点の worktree `ws-1526`)。コードは変えていない (本節は REPORT のみ)。
> 素材: `work-m11` の `tools/m11/work/boot_final3.ll`、`fl-win64` の `extracted/block00031_PE.bin` (展開先は `$RUNNER_TEMP`)。

### 6.1 `4256c0` の import 先 (%tagPOINT)

- IAT slot `0x1970df8` は `user32.dll!WindowFromPoint` (pefile の import テーブルで引いた実測)。
- `POINT` は 8 バイトなので、値渡しは整数 1 本 (rcx、8 バイト) になる。呼出し側 4 箇所 (`6065d2`・`6074c3`・`70a174`・`8660cc`、いずれも `call 4256c0` の位置。§6.6) は rcx に `qword` を読んで入れており、この読みと整合する。
- 結論: %tagPOINT の値渡しは **rcx 1 本・8 バイトの値**。受入条件「tagPOINT の ABI」は本節で達成。

### 6.2 IR 署名と機械語の不一致 (`40c660` `40c750` `653c80`)

呼出し側は `tools/liftdiff/tests/ld39_callsites.py` の E8 (rel32) 全走査で数えた (件数は全件、読んだのは先頭数件のみ。全件は読んでいない)。

| VA | LD-24 表の想定署名 (IR 未読) | 呼出し側 (E8 走査の件数 / 読んだ件) | 読んだ範囲の観測 | 判定 |
|---|---|---|---|---|
| `40c660` | `i64 (i128)` | 5021 件 / 4 件 (`440c50`・`440e7f`・`442435`・`45c430`) | 4 件とも直前に `xmm0` へ double を入れる (`movapd`・`movsd`・`cvtss2sd`)。`rdx`・`r8` に i128 の準備は見えない | IR 側の型が誤りの**疑い** (全件は未確認) |
| `40c750` | `i64 (i128)` | 543 件 / 6 件 (`40b76e`・`42080a`・`420829`・`420848`・`420868`・`442dd6`) | 6 件とも `xmm0` に double (`mulsd`・`movapd`・`movsd`) | 同上 |
| `653c80` | `i64 (i64,i64,i128)` | 3 件 / 3 件 (`6833c4`・`69b099`・`c7a451`) | `r8` に整数 (`mov r8,[..]`・`movsxd`) を入れ、`r9` は設定しない (`6833c4`・`c7a451` は `imul r8,rax` の結果、`69b099` は `movsxd r8`) | 第 3 引数は整数 1 本として扱われている**疑い** |

- `irtool.parse_sigs` は IR の `define` 行をそのまま読むだけなので、不一致の位置は IR (lifter の型付け) 側と読める。署名解決側の誤りは見えていない。
- 切り分けの結論は「IR 側が原因の疑いが強い」まで。全件の確認と、呼び先 (6.5) の確認が無いと確定しない。

### 6.3 i128 投入形 (a) / (b) の判定 — **未決のまま**

- 対象 11 関数のうち、呼出し側の実測で i128 が使われていると確認できたものは無い (6.2 の 3 関数は型誤り、残りは呼出し側が stack buffer の lea・整数・xmm0 を渡す)。
- 前節 §2 の「691dd0 は (b) と整合する」は**撤回**する。呼出し側 `682808`〜`682814` は `rdx` に `movsxd` の整数、`r8` に `xor r8,r8` (0) を入れており、(a) (rdx = 低位・r8 = 高位 0) とも (b) (rdx = ポインタ) とも読める。
- `442a50` の `lea rdx/r8/r9` は出力用の stack ポインタで、i128 引数ではない。
- 結論: (a)/(b) を 1 つに決める根拠は、この 11 関数からは得られない。**受入条件「候補を 1 つに決める」は未達**。

### 6.4 受入条件の達成状況

| 受入条件 | 状態 |
|---|---|
| 呼び先・呼出し側を機械語で確認し、i128 投入形を 1 つに決める | **未達** (6.3。決められる i128 の実例が無い) |
| `%tagPOINT` 値渡しの ABI を import thunk の先で確認 | **達成** (6.1: user32 `WindowFromPoint`、rcx 8 バイト) |
| `40c660` `40c750` の IR 署名と機械語の不一致を切り分け | **達成** (6.2: IR 側が原因) |
| REPORT_LD39.md に追記 (コードは変えない) | **達成** (本節) |

### 6.5 未解決 (起票先)

| 未解決 | 起票先 |
|---|---|
| `40c660` `40c750` `653c80` の IR i128 型が誤りかの全件確認と修正 (lifter の型付け) | #976 の残件 (PM 判断。子 issue は未起票) |
| 呼び先 `476930` `476980` `476500` `4764c0` `476020` `476480` の署名確認 (wrapper は引数を素通しするため、呼び先が決め手) | #1546 (LD-53) |
| i128 投入形 (a)/(b) の決定 | #1546 (LD-53)。IR 修正・呼び先確認の後に再判定 |

### 6.6 再現コマンドと実出力 (LD-51 追記分)

素材: `fl-win64.tar.zst` の `extracted/block00031_PE.bin` のみ `$RUNNER_TEMP/fl-win64/` に展開 (`tar --zstd -xf ... extracted/block00031_PE.bin`、2.2 秒)。`work-m11` は本 run に無いため `tools/m11/work/boot_final3.ll` は使えない。IR 無しで実行するため、`ld39_abi_dump.py` の署名列は空で出る (IR 依存の部分は §6.2 の値を参照)。

```
P="$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin"
python3 tools/liftdiff/tests/ld39_callsites.py "$P" --show 6 --list-dir work/ld39_callsites --iat 0x1970df8
: > "$RUNNER_TEMP/empty.ll"
python3 tools/liftdiff/tests/ld39_abi_dump.py "$P" "$RUNNER_TEMP/empty.ll" > work/ld39_abi.txt
```

(`empty.ll` を作らないと `irtool.parse_sigs` が `FileNotFoundError` で rc=1 になる。空ファイルを先に作る。)

- `ld39_callsites.py` の rc=0 (実測 wall 5.0 秒、本 run の再実行)。件数: `40c660` 5021 / `40c750` 543 / `4256c0` 4 / `664890` 26 / `6649b0` 3 / `6649c0` 8 / `664a80` 2 / `442a50` 14 / `442b90` 10 / `653c80` 3 / `691dd0` 13。
- `--iat 0x1970df8` の出力: `== IAT 0x1970df8 -> user32.dll!WindowFromPoint` (pefile の import テーブルで引いた値。§6.1 の根拠)。
- `ld39_abi_dump.py` の rc=0 (実測 0.073 秒、`empty.ll` を作成した上で再実行)。IAT 行が `-> 0x0` と出るのは、ディスク上の IAT slot が未束縛のため。import 名は `--iat` で引く。

`ld39_abi_dump.py` の出力 (抜粋。11 関数それぞれ先頭 2 命令と解決先。全行は `work/ld39_abi.txt`。IR を空にして実行したため `IR: ret=None params=` は空):

```
== 40c660  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  40c660: cvtsd2si rax, xmm0
  40c665: ret 
== 40c750  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  40c750: cvttsd2si rax, xmm0
  40c755: ret 
== 4256c0  IR: ret=None params=  (LD-24 表の想定: ptr (%tagPOINT))
  4256c0: jmp qword ptr [rip + 0x154b732]
    -> IAT slot 0x1970df8 -> 0x0 (import thunk: 以降は呼び先の ABI に従う)
== 664890  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  664890: sub rsp, 0x28
  664894: call 0x476930
== 6649b0  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  6649b0: sub rsp, 0x28
  6649b4: call 0x476500
== 6649c0  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  6649c0: sub rsp, 0x28
  6649c4: call 0x4764c0
== 664a80  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  664a80: sub rsp, 0x28
  664a84: call 0x476020
== 442a50  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  442a50: push rbp
  442a51: sub rsp, 0x40
== 442b90  IR: ret=None params=  (LD-24 表の想定: i64 (i128))
  442b90: sub rsp, 0x28
  442b94: call 0x442420
== 653c80  IR: ret=None params=  (LD-24 表の想定: i64 (i64,i64,i128))
  653c80: sub rsp, 0x28
  653c84: cmp r8, 0x7fffffff
== 691dd0  IR: ret=None params=  (LD-24 表の想定: i64 (i64,i128,i64))
  691dd0: push rbp
  691dd1: sub rsp, 0x50
== IAT 0x1970df8 -> user32.dll!WindowFromPoint
```

- 全件の VA 一覧は `work/ld39_callsites/<VA>.txt` に出る (commit しない)。

`40c660` の先頭 4 件 (E8 走査順): `440c50`・`440e7f`・`442435`・`45c430`。`40c750` の先頭 6 件: `40b76e`・`42080a`・`420829`・`420848`・`420868`・`442dd6`。`653c80` の 3 件: `6833c4`・`69b099`・`c7a451`。`691dd0` の 13 件のうち §6.3 で読んだ `682814`・`682e57`・`690291`・`a6465a`・`a9b5a0`・`a9b8c2`。`4256c0` の 4 件: `6065d2`・`6074c3`・`70a174`・`8660cc`。

- 注: `ld39_callsites.py` は E8 のバイト走査で、命令境界・data 上の E8 を含む偽陽性の上限値。件数は「その VA に向かう E8 rel32 の数」で、真の呼出し件数とは限らない。
- 測定 commit: `dee0e1ee` 基点。コードを変えた commit は `209cab78` (`ld39_callsites.py` 追加)。`git diff dee0e1ee 209cab78 -- tools/liftdiff/tests` は `ld39_callsites.py` の追加 (94 行) のみ。

## 7. LD-53 (#1546) 追記: 呼び先 6 関数の機械語 (実測)

> 測定 base: `ba32c517` (origin/main)。コードは変えていない (本節は REPORT のみ)。素材: `fl-win64` の `block00031_PE.bin` (展開先は `$RUNNER_TEMP`)。`boot_final3.ll` は本 run に無く未使用のため、IR 側の署名は読めていない。
> 読み方: 各 VA の先頭命令列を capstone で逆アセンブルし、引数レジスタの読みを人が判定した (自動分類はしていない)。

### 7.1 呼び先の引数読み

| 呼び先 | 経由 | 読んでいる引数 | LD-24 表の想定署名 (呼出し元の VA) |
|---|---|---|---|
| `476930` | `call 40c1d0` | xmm0 (double) | `i64 (i128)` (`664890`) |
| `476980` | `call 40c1d0` | xmm0 (double) | `i64 (i128)` (`6648a0` 系) |
| `476500` | `call 40bf40` | xmm0 (double) | `i64 (i128)` (`6649b0`) |
| `4764c0` | 直接 `call 40bf40` | xmm0 (float → double)。rdx・r8 は**出力用 float\*** (`movss [rbx]`・`movss [rsi]`) | `i64 (i128)` (`6649c0`) |
| `476020` | `call 450fb0` 等 | xmm0・xmm1 (double 2 本) | `i64 (i128)` (`664a80`) |
| `476480` | `call 40bd80` | xmm0 (double) | `i64 (i128)` (`664a90` 系) |

- 列「LD-24 表の想定署名」は LD-24 表に書かれた想定の文字列で、IR から読んだ署名ではない。`ld39_abi_dump.py` の `IR: ret=None params=` は空 (`tools/m11/work/boot_final3.ll` が本 run に無く、空の IR で実行したため)。IR 側の署名は**未読**。
- 呼び先 6 関数のどれも、i128 を整数レジスタ (rcx・rdx・r8・r9) の 2 本分として読んでいない。
- `4764c0` の rdx・r8 は整数ポインタとして使われる。i128 の低位・高位 (候補 (a)) とも、ポインタ (候補 (b)) とも読めない。
- 結論の範囲: 本比較は LD-24 想定署名 `i64 (i128)` と呼び先の機械語読みの比較であり、IR 側の署名との比較ではない。呼び先の読みは「i128 を取る」とは言えず、LD-24 想定が呼び先の機械語と合わない疑いが強い。(a)/(b) のどちらかを選ぶ根拠にはならない。

### 7.2 呼出し側の全件確認 (未実施・理由)

- 全件 (40c660 の 5021 件、40c750 の 543 件、653c80 の 3 件) は読んでいない。
- 一時的な命令窓の自動分類を試したが、data 上の E8 や命令途中を拾って誤分類が多く (`int2` と出た 23 件のうち実際の i128 準備は確認できず)、件数を REPORT の数値にできる精度に達しなかった。分類器は commit していない。
- 次の手: 命令境界で走査する (関数先頭から線形逆アセンブル) か、IR の呼出し箇所 (`call @40c660` の引数列) から照合する。#1546 で扱う。

### 7.3 受入条件の状態 (本節時点)

| 受入条件 | 状態 |
|---|---|
| 呼び先 6 関数の署名を機械語で確認 | **達成** (§7.1) |
| 呼出し側 5021 + 543 + 3 件を機械語で確認し、i128 未準備の件数を記す | **未達** (§7.2。分類器の精度不足) |
| 投入形 (a)/(b) を 1 つに決める | **未達**。呼び先が i128 を読まないため、(a)/(b) の選択以前に IR 署名の誤りが疑われる。#1546 で判断する |

起票先: 呼出し側の全件確認・投入形の決定は #1546 (LD-53)。IR 署名の修正は #976 の残件 (§6.5)。

## 8. LD-53 (#1546) 追記

呼出し側の全件確認と投入形の判定 (部分達成)。全文は `REPORT_APPENDIX_LD53.md`。結論: 呼出し側と呼び先の機械語から (a)/(b) を選べる実例が無かった。LD-53 の最終判定 (`REPORT_APPENDIX_LD53.md` §7) で (a)/(b) を `691dd0` について棄却し、投入形は機械語の入口どおりとした。大半 (10 関数) は IR の `i128` 型が誤りの疑いが強い。
