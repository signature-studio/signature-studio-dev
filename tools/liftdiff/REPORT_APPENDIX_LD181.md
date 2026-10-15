# 付録: liftdiff LD-181 (#3864): 653c80 / 691dd0 の native segv の原因と、irtool.instrument の i128 入口記録

> 親: #1528 (LD-52)。前提: `REPORT_APPENDIX_LD52.md` §4 の未解決。
> 測定 commit: `d256d3432` (コードを変えた最後の commit。検証 HEAD = 測定 commit)。`57a146a96` からの差分は §5。
> 基準 (修正前): origin/main `feec9980a` (同じ build 手順・同じ素材)。

## 結論

- **691dd0**: native segv の原因は、小サイズ用アロケータ (`0x407a50`) のビン読み `0x407a97` (`mov rax,[rdx+0x18]`) で、rdx=0 (ビン先頭 `[rbx+8]` が 0)。fault addr は `0x18`。boot 状態を読んでも同じ segv で、LD-159 の「大域ビン (`0x407a50` の表) が 0 のまま」と同型。`691dd0` は rcx のオブジェクト (`[rcx+0x78]`・`[rcx+0x94]`・`[rcx+0x8c]`) を読んで確保 (`0x409410`) を呼ぶ。有効なオブジェクトを渡す case は作れていない (§2)。**判定には入らない** (11 パターンとも `native_null_deref_all_patterns`)。
- **653c80**: segv の rip は **0** (`rip_rva=0xffffffffffc00000`)。`0x653c8d` の `call qword ptr [rip+0xf9f7ed]` が、.bss の slot (`VA 0x15f3480`) が 0 のまま null を呼ぶ。r8 が `0x7fffffff` 未満の経路 (`cmp r8,0x7fffffff` → `jge` を取らない) で発生する。fault addr は記録されず、呼び先 slot は boot 状態でも未設定 (§2)。**判定には入らない** (11 パターンとも `native_fault_all_patterns`)。
- **irtool.instrument の i128 入口記録**: 修正した (受入 (a))。i128 引数を `trunc i128 %x to i64` で下位 64bit として `ld_trace` に記録する。旧版は `0` と記録していた。sample:800 の判定差は前の測定 (`57a146a96`) で **0 件** (360/234/206 のまま。関数単位の判定差 0・§3)。HEAD `d256d3432` の実測は 361/233/206 (§5)。
- `cmp_trace` の i128 位置の除外 (`compare.py`) は**残した**。除外を外すと、xmm0 を trunc した値と native の値が合うかの確認が要るため、この PR では判定の経路を変えない (§4 の未解決)。

## 1. 方式

- `ldlib/irtool.py` `instrument`: i128 引数の分岐を追加 (`trunc i128 → i64`)。他の型の分岐は変えていない。
- 単体: `tests/test_ld181_i128_entry.py` (`[0/4]` に追加)。ネガコン: `trunc` を `0` に戻すとテストが exit 1 で落ちることを確認 (`NEG_EXIT=1`・`POS_EXIT=0`)。

## 2. segv の原因 (機械語)

逆アセンブルは `pefile` + `capstone` で `block00031_PE.bin` (ImageBase `0x400000`) を読んだ。

| 関数 | 単発の実行 (`liftdiff.py run --fn ... --pattern z`) | 機械語の位置 | 原因 |
|---|---|---|---|
| `691dd0` (`i64 (i64,i128,i64)`) | `native_fault`・`segv`・`fault: addr=0x18 rip=0x407a97`・`rdx=0` | `0x407a93` `mov rdx,[rbx+8]` → `0x407a97` `mov rax,[rdx+0x18]` (小サイズ確保のビン読み) | ビン先頭が 0。boot 状態 (`work/m11/boot_state.json`) でも同じ。LD-159 と同型 |
| `653c80` (`i64 (i64,i64,i128)`) | `native_fault`・`segv`・`fault: None`・`rip_rva=0xffffffffffc00000` (rip=0) | `0x653c8d` `call [rip+0xf9f7ed]` (間接 call。slot `VA 0x15f3480`) | slot が未設定 (.bss・PE の file image は 0)。null を呼ぶ |

- `691dd0` の入口は `0x691f50` (`0x68b3a0` を呼ぶ・vtable 呼出し・`0x6919f0`・`0x409440`) を経て、`0x409410` (確保) を呼ぶ。rcx が指すオブジェクトの中身 (`[rcx+0x78]`・`[rcx+0x94]`) が要るため、zero の rcx では確保経路のビン (0x407a50) が未初期化のまま読まれる。
- `653c80` は `i128` の値を使わず (LD-53 §7.1)、`r8` の整数だけを見る。r8 が `0x7fffffff` 以上なら `0x409c80` へ、未満なら間接 call へ行く。全 11 パターンで間接 call の slot が 0 のため segv する。

**判定に入る case を作れるか**: `691dd0` は有効なオブジェクトを渡せば入る見込みだが、オブジェクトの内容 (vtable・ビン) を作る経路が未確立。`653c80` の slot は、その呼び先を boot 状態から埋める必要がある。どちらも本 PR では判定に入らない。受入 (1) の「判定に入るか、入らない理由」は、上記の原因と「入らない」結論で満たす。

## 3. i128 入口記録の修正と判定の差 (受入 (2)・(3))

- 修正: `irtool.instrument` が i128 引数を `trunc` して `ld_trace` に渡す (`653c80` の 3 番目・`40c660` の 1 番目)。計装結果 (`work/m11/ir_instr.ll`) で `trunc i128` が 264 箇所入ることを確認。
- LD-52 の 11 関数 (`targets/ld52_11.txt`・`--shards 4 --state auto`): 一致 2 / 不一致 0 / 実行不能 9 (LD-52 と同じ)。
- **sample:800** (`--shards 12 --state auto`・`batch_sample_800.jsonl`):

| 版 | 一致 | 不一致 | 実行不能 | 関数単位の判定差 |
|---|---|---|---|---|
| 修正前 `feec9980a` | 360 | 234 | 206 | — |
| 修正後 `57a146a96` (前の測定) | 360 | 234 | 206 | **0 件** (800 件を突合) |
| 修正後 HEAD `d256d3432` (実測 2 回) | 361 | 233 | 206 | 2 回とも同値 (1 回目と 2 回目の関数単位の判定差 0 件) |

- 突合は修正前の `batch_sample_800.jsonl` (退避) と修正後の出力の `verdict`・`unexec_reason` の比較。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `cmp_trace` の i128 位置の除外を外せるか (xmm0 を trunc した wasm 値と native の xmm0 が一致するか) | 比較の除外が残り、i128 位置の不一致を見逃す経路が残る | #4195 ([LD-202]) |
| `691dd0` の有効オブジェクトを作る case (rcx の vtable・ビン)。判定に入る条件 | 実行不能 1 | #4200 ([LD-203]) |
| `653c80` の間接 call slot (`VA 0x15f3480`) を boot 状態で埋める | 実行不能 1 | #4200 ([LD-203]) |

## 5. 検証

- 測定 commit `d256d3432` (検証 HEAD)。実測は素材 `fl-win64`・`work-m11`・`work-liftdiff`・`toolchain-emsdk` を `$RUNNER_TEMP` / `tools/{m11,liftdiff}/work` に展開して行った (`tools/m11/m11_gen_ir2.sh` で `ir_conditions.json` を作ってから)。
- e2e: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 TMPDIR=$RUNNER_TEMP bash tools/liftdiff/liftdiff_e2e.sh --m11-only` → **exit 0・`LIFTDIFF_E2E PASS`・`real 3m14.299s`** (開始時 load 0.73・終了直後 5.21)。
- 単体 (e2e の `[0/4]`・`[3/4]`): `PASS test_ld52_machine_sig`・`PASS test_ld181_i128_entry`・`PASS test_ld179_tagpoint_tr`・`PASS` の 3 件 (UStrAsg・Move・4123c0)・`CHECK_INITUNITS PASS`。
- sample:800 (`--shards 12 --state auto`): e2e 内の batch は `done 113s`・結果 `361 / 233 / 206`。同 HEAD で `liftdiff.py batch` を単独で再実行 (`real 1m54.597s`) しても `361 / 233 / 206`。関数単位の判定は 2 回の突合で 0 件差。
- 前の測定 (`57a146a96`) は `360 / 234 / 206`。HEAD の実測は 1 件ずれて `361 / 233 / 206` で、2 回とも同じ。HEAD の値を正とする。
- 前の測定 `57a146a96` の e2e: `real 2m44.456s`。修正前 `feec9980a`: `real 2m44.474s` (load 0.03)。
- `57a146a96` から HEAD までのコード差分 (`git diff 57a146a96 d256d3432 -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/tests tools/liftdiff/liftdiff_e2e.sh`):

  ```
   tools/liftdiff/ldlib/cases.py                  |  7 ++++
   tools/liftdiff/ldlib/pe.py                     |  9 +++++
   tools/liftdiff/ldlib/session.py                | 26 ++++++++++----
   tools/liftdiff/liftdiff_e2e.sh                 |  4 ++-
   tools/liftdiff/rt/ld_core.h                    | 14 +++++---
   tools/liftdiff/rt/ld_ms_call.S                 |  6 +++-
   tools/liftdiff/tests/test_ld179_tagpoint_tr.py | 48 ++++++++++++++++++++++++++
   7 files changed, 102 insertions(+), 12 deletions(-)
  ```

  出どころは main 取り込み (#4186 (LD-179)・#4187 (LD-180) など) で、本 PR の変更ではない。全文 (234 行) は REPORT の行数上限 (250 行) を超えるため、上の stat と上記コマンドで再現する。
- 単体: `PASS test_ld52_machine_sig`・`PASS test_ld181_i128_entry` (e2e の `[0/4]`)。
- 製品 KPI (FLEngine 起動・最初のウィンドウ): 本 PR は起動・GUI に関わらないため書かない。
