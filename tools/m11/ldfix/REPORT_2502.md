# REPORT_2502 — function_450560 の 2 段 deref 脱落を IR 修復 pass で直す (#2502 / CI-100)

既知類型との関係: **DEFECTS.md D4** (引数 reg 経由の disp=0 deref 脱落 → 値がアドレスのまま使われる)。
新規類型ではない。#662 (`function_8c7710` の spill 経由の引数 deref) と同じ機構の再発。

## 0. 結論

- `function_450560` の base IR は、スピルした `arg1` 経由の 2 段目 load (`*arg1`) と、`arg2` 経由の `*arg2` を落とし、アドレスそのものを値として渡していた (機械語 18 命令と突合して確定)。
- 修復 pass `tools/m11/ldfix/fix_450560.py` (機械語照合付き・fail-closed) で関数本体を機械語どおりの IR に置換した。`ldfix_e2e.sh` の step 1b で適用する。
- 修復 IR は、既存の C 転記 (`m11_ov.c` の `function_450560`) と**同じ実行結果** (GetMem 16 / FastMM 17 / icall_ok 24) を IR だけで再現した。
- **未達**: 受入 2 (同類型の全数の IR 側確認) は、機械語側の候補 15 関数 (22 deref 箇所) の数え上げまで。IR 側の確認と修復は子 issue #2555 ([CI-103]) へ。
- トラップ位置 (`function_4133f0` の `memory access out of bounds`, unit #18) は不変。本件で OOB は解消しない。

## 1. 機械語と base IR の対照 (修正箇所の根拠)

PE (`block00031_PE.bin`, VA 0x450560, capstone 線型 disasm) の実行:

| VA | 機械語 | base IR (`boot_final3.ll`) | 修復後 IR |
|---|---|---|---|
| 0x450576〜0x450583 | `rcx=[rsp+0x68]` (=arg2) / `rax=[rsp+0x60]` (=arg1) / `rdx=[rax]` (=*arg1) / `call 4133f0(arg2, *arg1)` | `call 4133f0(arg2, arg2)` | `%v1 = load [arg1]` → `call 4133f0(arg2, %v1)` |
| 0x450588〜0x45058d | `rax=[rsp+0x68]` / `cmp qword [rax],0` (=*arg2) | `icmp eq arg2, 0` | `%v2 = load [arg2]` → `icmp eq %v2, 0` |
| 0x45059f〜0x4505ac | `rax=*arg1`; `test rax` で nil ガード後 `esi = dword[rax-4]` | `load i32 (arg2-4)` を無条件に実行 | `*arg1 != 0` の分岐の下で `load i32 (*arg1-4)`、`phi` で 0 と合流 |
| 0x4505af〜0x4505be | `edi=0`; `rax=*arg2`; nil ガード後 `edi = dword[rax-4]` | `%5` を再利用 (`arg2-4` の load) | `*arg2 != 0` の分岐の下で `load i32 (*arg2-4)`、`phi` |
| 0x4505c6〜0x4505d9 | `r13 = 414850(*arg1)`; `rax = 414850(*arg2)` | `414850(arg2)` ×2 | `414850(load [arg1])`、`414850(load [arg2])` |
| 0x4505f4 | `LCMapStringW(loc, 0x1000100, r13, esi, rax, edi)` | 引数 `(arg3, 16777472, %8, %5, %9, %5)` | `(arg3, 16777472, src, esi, dst, edi)` |
| 0x4505fd | `call 44cb40` (rcx/rdx は未設定の残骸) | `44cb40(zext arg3, 16777472)` | 同左 (**未検証**・据え置き) |

修正箇所を IR 修復 pass にした理由: 落ちた段は「スピルした引数経由の 2 段目 deref」で、既存 ldfix の F1〜F4 (`ldfix.py` の修復パターン) のどれにも当たらない。lift 段 (RetDec) の挙動を直すには RetDec 側の変更が要るので、当面は関数単位の機械照合付き pass にする。nil ガードの分岐は base IR に無いので、本 pass で書き直した。

## 2. 修復 pass と適用

- `tools/m11/ldfix/fix_450560.py`: (a) 機械語 18 命令 (`EXPECT`、mnemonic と operand 文字列の完全一致) を capstone で照合。(b) IR は `call 4133f0(i64 %arg2, i64 %arg2)` が 1 件のときだけ本体を置換。どちらも外れたら assert で停止 (fail-closed)。
- `tools/m11/ldfix/ldfix_e2e.sh` の step 1b で `ldfix.py` の直後に適用。
- `tools/m11/ldfix/stage4.sh` は `S4_EXTRA_CF` を `CF` に足すだけの変更 (既定は空で、従来の挙動は不変)。fix 側の実行だけ `-DM11_OV_NO_450560` を渡す。
- `tools/m11/m11_ov.c`: `function_450560` の転記を `#ifndef M11_OV_NO_450560` で囲んだ (既定は従来どおり有効)。
- IR の差分: `ldfix_only.ll` と `ldfix_fixed.ll` の差は 72 行で、全て `function_450560` の本体 (行 158609〜158637) に限られる。

## 3. 測定 (測定 commit `8ec1def3`・コード差分の最終 commit)

- 実行: `cd ws-2502 && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh` → **real 1m08.7s**・rc=0・JUDGE `pass: true`。環境 4 vCPU・起動時 load average 0.08 (1 分)。
- 比較変種 (同じ `stage4.sh` と `survey_stage4.mjs`、既存の素材 `tools/m11/work/` を読込のみ):

| 変種 | IR | `m11_ov.c` の 450560 転記 | GetMem | FastMM GetMem | icall_ok | wasm_size | threw | survey ok / miss / trap |
|---|---|---|---|---|---|---|---|---|
| base (e2e の base) | boot_final3 (ldfix 前) | 有効 (既定) | 16 | 17 | 24 | 6021140 | OOB | 136 / 14 / 9 |
| base_noov | boot_final3 | 無効 | 17 | 18 | 25 | 6020925 | OOB | 136 / 14 / 9 |
| ldfix_only | ldfix 適用・fix_450560 無し | 無効 | 17 | 18 | 25 | 6021172 | OOB | 136 / 14 / 9 |
| fix (e2e の fix) | ldfix + fix_450560 | 無効 | **16** | **17** | **24** | 6021264 | OOB | 136 / 14 / 9 |

- units_run 17/942 (全変種)、stage4 は 4/6 到達 (全変種)。survey の trap 9 件の内訳は OOB 8・Halt0→longjmp 1 (全変種)。
- 読み方:
  - base_noov → ldfix_only: 変化なし (既存の ldfix F3a/F3c/F4 はこの 2 指標に効かない)。
  - ldfix_only → fix: GetMem −1、icall_ok −1 (IR 修復の効果)。値は C 転記 (base) と一致する。
  - トラップ: OOB の位置は不変 (`4133f0` ← `446400`、unit #18)。wasm 関数番号は build ごとに変わる (`REPORT_SHX-T26.md` の注記) ので、番号 14871 (base) と 14872 (fix) は同一関数の別番号。名前の突合は未実施。
  - 結論: 450560 の IR 修復は実行経路に効く (GetMem と icall の数が変わる) が、OOB の原因ではなかった。#942 受入 1 (OOB 解消) は本件では進まない。

## 4. 同類型の数え上げ (受入 2 の一部)

- 走査: `python3 tools/m11/ldfix/scan_spill_deref_2502.py tools/m11/work/boot_final3.ll --pe $FL_WIN64_DIR/extracted/block00031_PE.bin --out <json>`
- 定義 (機械語): (S) 引数レジスタ rcx/rdx/r8/r9 を `[rsp+X]` に退避 → (L) `[rsp+X]` を別レジスタに読み直す → (D) その値を 1 段 deref して引数レジスタへ入れる → (C) D の後 6 命令以内に `call`。
- 結果: IR 関数 7421 / .pdata 有り 6969 / **候補関数 15 / deref 箇所 22**。

| VA | 退避元の引数 | deref 箇所 (VA) → call (VA) |
|---|---|---|
| 0x413340 | rcx | 0x4133aa → 0x4133bc |
| 0x413c00 | rcx | 0x413c55 → 0x413c65 |
| 0x414c70 | rcx | 0x414cbf → 0x414ccf |
| 0x416750 | rdx | 0x416953→0x416956, 0x416964→0x416967, 0x416975→0x416978, 0x4169d0→0x4169d3, 0x4169da→0x4169dd, 0x4169e8→0x4169ee |
| 0x439f90 | rcx | 0x43a0bb → 0x43a0be |
| 0x44f040 | rcx | 0x44f090 → 0x44f095 |
| 0x44f240 | rcx | 0x44f250 → 0x44f264 |
| 0x44fb40 | rcx | 0x44fbb9 → 0x44fbbc |
| 0x450420 | rcx | 0x450454 → 0x450457 |
| **0x450560** | rcx / rdx | **0x450580 → 0x450583, 0x4505c6 → 0x4505c9, 0x4505d6 → 0x4505d9** |
| 0x4506e0 | rcx | 0x450739 → 0x45073c |
| 0x47b4a0 | rcx | 0x47b4f5 → 0x47b50b |
| 0x47cf10 | rcx | 0x47cf92 → 0x47cfa4 |
| 0x6074b0 | rcx | 0x6074c0 → 0x6074c3 |
| 0xc40770 | r9 | 0xc409c0 → 0xc409d6 |

- 陽性対照: 0x450560 の 3 箇所が全て検出される。
- 取りこぼし (既知): **0x7888f0** は引数 (`rcx`) を `rbx` に複写してから `mov rdx,[rbx]` する形で、S→L→D に当たらず検出されない。ただし IR では `call 4133f0(arg2, arg2)` の 2 件目がここにあり、同類型の疑いが強い (修復前 IR の 2 件目。修復後も残る。`call 43c3f0(0,0)` など別の欠落も併存)。
- 複写も追う版 (`--copy-alias`) は 65 関数 / 133 箇所に膨らみ、正常な間接参照 (`mov rbx,rcx; mov rcx,[rbx]; call` の vtable 等) を多数含むため採用しない。
- **IR 側の確認は未実施**: 15 関数それぞれについて、機械語の deref 相当の値が IR の call 引数で落ちているかは未判定。→ 子 #2555 ([CI-103])。

## 5. ネガティブコントロール

- NC1 (二重適用): 修復済み IR に `fix_450560.py` を再適用 → `AssertionError: base 形 (call i64 @function_4133f0(i64 %arg2, i64 %arg2) が 1 件) でない` で停止 (rc=1、出力ファイル無し)。
- NC2 (機械照合): `EXPECT` の 0x450583 を `call 0x413780` に差し替えて `verify_machine` → `AssertionError: 機械語 0x450583 が想定と違う: ('call', '0x4133f0') != ('call', '0x413780')`。
- 陽性対照 (走査): §4 のとおり 0x450560 の 3 deref 箇所を検出。

## 6. 未解決

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 同類型 15 関数 22 deref 箇所の IR 側確認と修復、および 0x7888f0 (走査の取りこぼし) | #942 の残り OOB 系統の一部。全数の VA 一覧は §4 | 子 #2555 ([CI-103]) |
| 本番配線: `fix_450560.py` を `m11_gen_ir2.sh` の ldfix 直後に常設し、`m11_ov.c` の 450560 転記を既定 OFF にする。`m11_e2e.sh --full` で実 build の wasm を測る | 現在の本番 wasm は C 転記で動いており、IR 修復は ldfix_e2e の測定でのみ使われる | 子 #2556 ([CI-104]) |
| `44cb40` の引数 (LCMapStringW 失敗時のみ) は機械語で未設定。base の値を据え置いた | 失敗経路のみ。未検証 | #2556 ([CI-104]) の受入に含める |
| トラップ `4133f0` の OOB (unit #18) は本件で解消しない | #942 受入 1 | #942 にコメント (本 PR 後) |
| issue の検証方法の `tools/m11/ldfix/normal_boot_probe.mjs` と `pe_disasm_va.py` は repo に無い | 検証手段の欠落 | 代替: 機械照合は `fix_450560.py` 内 (capstone 18 命令)、通常 boot の計測は `ldfix_e2e.sh` の stage4・survey。記録のみ |

## 7. 再現

```sh
cd <worktree>            # branch 2502-m11-fix-450560
ln -s <main>/tools/m11/work tools/m11/work          # 素材 work-m11 (gitignore 対象・読込のみ)
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/m11/ldfix/ldfix_e2e.sh
FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP S4_EXTRA_CF=-DM11_OV_NO_450560 bash tools/m11/ldfix/stage4.sh tools/m11/ldfix/work/ldfix_only.ll ldfix_only   # ldfix のみ (事前に ldfix.py で作る)
python3 tools/m11/ldfix/scan_spill_deref_2502.py tools/m11/work/boot_final3.ll --pe $RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin --out work/scan_2502.json
```

- 測定 commit: `8ec1def3` (コード差分の最終 commit)。本 REPORT を含む後続 commit はドキュメントのみ。
- `git diff 8ec1def3 HEAD -- tools/m11/ldfix/fix_450560.py tools/m11/ldfix/scan_spill_deref_2502.py tools/m11/ldfix/stage4.sh tools/m11/ldfix/ldfix_e2e.sh tools/m11/m11_ov.c | wc -l` → `0` (コード差分 0 行)。後続の差分は `REPORT_2502.md` と `docs/DOC_MAP.md` のみ (`git diff --stat 8ec1def3 HEAD`)。
