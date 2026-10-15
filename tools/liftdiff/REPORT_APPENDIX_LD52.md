# liftdiff LD-52 (#1528) — i128 引数の機械語入口型による case 投入と実行可能件数の実測

> 親: #1194 (LD-39)。前提: #1526 (LD-51)、投入形の判定は #1546 (LD-53・PR #2791・`REPORT_APPENDIX_LD53.md` §7)。
> 測定 commit: `46bc0cd35` (§2.1・§3 の実測はこの commit)。§2 本表の 5 件は `f6abfd073` の値で、`46bc0cd35` でも変わらない (`f6abfd073..46bc0cd35` の ldlib 差分は `MACHINE_ENTRY` の 6 行のみ)。`46bc0cd35` から現 HEAD までのコード差分は §5。**現 HEAD では未再測定** (§5)。
> 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`)・`work-m11`・`work-liftdiff`・`toolchain-emsdk`。
> `work-liftdiff` の `ld_wasm.cjs` は現行の `rt/ld_wasm.c` と export の引数数が合わない (`ld_w_snapshot`) ため使えず、`python3 liftdiff.py build targets/m11.json` (emsdk) で再 build した。

## 1. 方式

IR の `i128` 引数は、機械語では xmm0 (double) か整数レジスタ 1 本の値 (LD-53 §7.1)。入口型どおりに投入する。

| VA | IR 署名 | 投入 (native sig) | 根拠 (LD-53) |
|---|---|---|---|
| `40c660` | `i64 (i128)` | `double` (xmm0) | 本体は `__asm_cvtsd2si(i128 %arg1)` (xmm0 の値)。xmm0 の参照 1 件・i128 の参照 0 件 |
| `40c750` | `i64 (i128)` | `double` (xmm0) | 本体は xmm0 の参照のみ |
| `653c80` | `i64 (i64,i64,i128)` | `i64,i64,i64` (r8 のみ使用) | 本体は `cmp r8,0x7fffffff`・`shl r8,2`。r9 の参照 0 件 |
| `691dd0` | `i64 (i64,i128,i64)` | `i64,i64,i64` (rcx ポインタ・rdx i64・r8 flag) | (a)/(b) を棄却した入口 (§7.1) |

LD-180 (#3863) で追加した 6 件 (機械語を呼び先まで辿って読んだ入口。IR の呼出しは `xor i64 0, 0` の placeholder を含み、IR 上の引数とは一致しない):

| VA | 投入 (native sig) | 根拠 (機械語) |
|---|---|---|
| `442a50` | `double,i64,i64,i64` | `4428c0` の rdx/r8/r9 は出力 word\* (`442420`→`40c660` が xmm0 を読む) |
| `442b90` | `double` | `442420` → `40c660` (xmm0 のみ) |
| `664890` | `double` | `476930` → `40c1d0` (xmm0 のみ) |
| `6649b0` | `double,i64,i64` | `476500` → `40bf40` が xmm0 を読み、rdx/r8 は出力 ptr |
| `6649c0` | `float,i64,i64` | `4764c0` が xmm0 を float として読み (`cvtss2sd`)、rdx/r8 は出力 float\* |
| `664a80` | `double,double` | `476020` が xmm0・xmm1 (double 2 本) を読む |

実装 (`ldlib/cases.py` `MACHINE_ENTRY` / `machine_sig`):
- native は sig の型どおりに投入する (`rt/ld_native.c` は変更なし)。
- wasm は `m11_tr_<fn>` (i64×8 を受け、IR 引数へ `zext`) を `tr=1` で呼ぶ。`wsig=i64,...` で raw 64bit を渡す (`rt/ld_runner.mjs`)。`zext` により xmm0 の下位 64bit が入力値になる。
- 比較 (`ldlib/compare.py` `cmp_trace`): 入口型の関数 (`machine_sig` が付ける `ir_params` を持つ関数) について、IR の i128 位置だけを比べない。wasm の entry 記録 (`irtool.instrument`) は IR の i128 引数を `0` と記録するため (§4 の未解決)。i64 の位置 (`653c80` の rcx・rdx、`691dd0` の rcx・r8) は入口型どおりに比べる。戻り値・memory・calls も比べる。入口型でない関数の判定は変えない。除外の検査は `tests/test_ld52_machine_sig.py`。

## 2. 対象 11 関数の実行可能件数 (測定 `f6abfd073`・§2.1 の 6 件は `46bc0cd35`。現 HEAD は未再測定 (§5))

対象は `targets/ld52_11.txt` の 11 VA (sigs.json の定義済み関数のうち、params に `i128` を含む 10 関数 (`ret` が i128 の `1311ea0` は LD-24 の対象外) と `%tagPOINT` 1 関数)。

実測コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 liftdiff.py batch targets/m11.json --set file:targets/ld52_11.txt --shards 4 --nobuild --state auto --out work/ld52_11.jsonl` (7.4 秒)

| VA | IR 署名 | 判定 | 内容 |
|---|---|---|---|
| `40c660` | `i64 (i128)` | **match** | 11/11 パターンとも equal (ret・memory・calls が native と wasm で一致) |
| `40c750` | `i64 (i128)` | **match** | 11/11 パターンとも equal |
| `653c80` | `i64 (i64,i64,i128)` | unexec (`native_fault_all_patterns`) | 11 パターンとも native segv。segv の fault addr は記録されず原因未特定 (§4) |
| `691dd0` | `i64 (i64,i128,i64)` | unexec (`native_fault_all_patterns`) | z・s は rcx=0/3 の参照で segv (addr `0xc0`/`0xc3`・rip `0x6919f8`)。p0 等は rcx が blob の値を指して segv。オブジェクトの有効な内容が要る (§4) |
| `4256c0` | `ptr (%tagPOINT)` | unexec (`unsupported_sig`・測定 `46bc0cd35` 以前) | 機械語の入口は rcx の 8 バイト POINT 値 (x = 下位 32bit, y = 上位 32bit)。`main` 取り込み (`4edbf8a95`) で `MACHINE_ENTRY` に `0x4256c0: ['i64']` が入ったため、現 HEAD の判定は**未測定** (§5)。m11_tr_ の生成が a0 から組むことは単体テスト `test_ld179_tagpoint_tr` で確認 (PASS)。実機 batch は未測定 (§4) |
| `442a50` `442b90` `664890` `6649b0` `6649c0` `664a80` | `i64 (i128)` | **mismatch** | LD-180 (#3863) で入口型を確定 (§1・`cases.MACHINE_ENTRY`)。不一致の内訳は §2.1 (IR 側の引数落ち・呼び先 entry 欠落。§4) |

### 2.1 LD-180 (#3863) の 6 件 (測定 commit `46bc0cd35`・現 HEAD `4edbf8a95` では未再測定 (§5))

測定: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 liftdiff.py batch targets/m11.json --set file:targets/ld52_11.txt --shards 4 --nobuild --state auto` (7 秒)。

| VA | 判定 (前) | 判定 (後) | 主な差分 (後) |
|---|---|---|---|
| `442a50` | unexec (`unsupported_sig`) | **mismatch** | `callsite_arg_drop`: `4428c0` arg0 が native `0x11` / wasm `0` (IR の呼出しが引数を落とす) |
| `442b90` | unexec (`unsupported_sig`) | **mismatch** | `native_extra_entry` (#2): wasm の `442420` が `40c660` を呼ばない |
| `664890` | unexec (`unsupported_sig`) | **mismatch** | `wasm_trap`: `unreachable` (呼び先 `function_4128b0` 系の chain) |
| `6649b0` | unexec (`unsupported_sig`) | **mismatch** | `callsite_arg_drop`: `40bf40` arg0 が native `0x11` / wasm `0` |
| `6649c0` | unexec (`unsupported_sig`) | **mismatch** | `callsite_arg_drop`: `4764c0` arg0 が native `0x11` / wasm `0` |
| `664a80` | unexec (`unsupported_sig`) | **mismatch** | `native_extra_entry` (#4) |

- 対象 11 件の結果 (測定 `46bc0cd35`): 一致 2 / 不一致 6 / 実行不能 3 (`unsupported_sig` 1 = `4256c0`・`native_fault_all_patterns` 2 = `653c80` `691dd0`)。前は 一致 2 / 不一致 0 / 実行不能 9。
- 不一致 6 件の差分は、いずれも IR の呼出し側が引数 (`xor i64 0, 0` の placeholder) を落とすか、呼び先の entry が wasm で欠けることに由来する。入口型の読み (機械語) は変えていない。IR 側の修正は §4。
- sample:800 では `442b90` の 1 件だけが含まれ、unexec → mismatch (実行不能 206→205・不一致 234→235)。他 5 件は sample:800 に含まれない。

- 変更前 (origin/main `09b96c12f`・同じ build 手順・同じ batch): 一致 0 / 不一致 0 / 実行不能 11 (`unsupported_sig` 11)。
- 変更後 (`f6abfd073`): 一致 2 / 不一致 0 / 実行不能 9 (`unsupported_sig` 7・`native_fault_all_patterns` 2)。実行に入ったのは 4 関数 (うち 2 関数が一致)。
- 試行中の差分 (`callsite_arg_drop`・`xmm_arg_drop`) は、すべて wasm entry 記録の `i128 → 0` によるものだった。§1 の比較の扱いで取り除いた (取り除く前の版は 40c660・40c750 とも不一致)。

## 3. e2e (`bash tools/liftdiff/liftdiff_e2e.sh --m11-only`)

sample:800 (`--shards 12 --state auto`) の判定。`--m11-only` の所要 (実測・各 run の exit と `LIFTDIFF_E2E PASS`)。下表は測定 commit `46bc0cd35` の行 (最終行) を含め、現 HEAD `4edbf8a95` では**未再測定** (§5)。

| run | 測定コード | exit | 所要 | sample:800 一致 / 不一致 / 実行不能 |
|---|---|---|---|---|
| 同手順の比較 (再 build) | origin/main `09b96c12f` | 0 (PASS) | 193 s | 361 / 233 / 206 |
| 前版 run 1 | `b37494bec` と同じ版 (`f6abfd073` より前・入口引数を全て除外する版) | 0 (PASS) | 191 s | 360 / 234 / 206 |
| 前版 run 2 | `b37494bec` と同じ版 (`f6abfd073` より前・同上) | 0 (PASS) | 189 s | 360 / 234 / 206 |
| 前版 HEAD | `b37494bec` (`f6abfd073` より前・同上) | 0 (PASS) | 185 s | 360 / 234 / 206 |
| 前版 HEAD | `f6abfd073` (i128 位置だけを除外) | 0 (PASS) | 177 s | 360 / 234 / 206 |
| **LD-180 (#3863)** | **`46bc0cd35`** (6 件の MACHINE_ENTRY 追加) | **0 (PASS)** | **178 s** (実測 2m58s・開始前 load 0.14・終了直後 4.56) | **360 / 235 / 205** |

- `f6abfd073` の所要は実行前後の `uptime` の時刻差 (05:02:39 → 05:05:36)。負荷は開始前 1 分 load 0.22、終了直後 5.56。
- HEAD の `[0/4]` に追加したテスト `tests/test_ld52_machine_sig.py` は PASS (`PASS test_ld52_machine_sig`)。
- 前版 (`b37494bec`) の sample:800 と origin/main の判定差は 6 関数 (`1060950` `1266e70` `43a3f0` `50abe0` `5c5500` `959a40`)。同一コードの run 1 と run 2 でも 4 関数が揺れる (`959a40` は REPORT_APPENDIX.md の run 依存 1 件と同じ。`50abe0` `5c5500` は hang と native_fault の入れ替わり)。差の出る関数はいずれも i128・%tagPOINT を持たず、変更は入口型の関数にしか分岐を足していないため、判定の差は run 間の揺れの範囲とみなす。sample:800 に `40c660` `40c750` は含まれない (`batch_sample_800.jsonl` で 0 件)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `4256c0` (%tagPOINT) は `MACHINE_ENTRY` に `['i64']` を追加済み (`main` 取り込み `4edbf8a95`)。`m11_tr_` の POINT 値の組立ては単体テスト PASS。実機 batch の判定は未測定 (§5) | 実行不能 1 (測定時点) | #3862 ([LD-179]) |
| 6 件 (`442a50` `442b90` `664890` `6649b0` `6649c0` `664a80`) は入口型を確定 (§1) したが、IR の呼出し側の引数落ち (`xor i64 0, 0` placeholder) と呼び先 entry の欠落で不一致 (§2.1)。IR 側の修正が要る | 不一致 6 | #4193 ([LD-201]・#3863 の子) |
| `653c80` `691dd0` の native segv (691dd0 は rcx のオブジェクト内容、653c80 は fault addr 未記録)。`irtool.instrument` が IR の i128 入口を `0` と記録する (callee の入口比較の偽陽性の源。sample:800 への影響は未測定) | 実行不能 2・比較の信頼性 | #3864 ([LD-181]) |

## 5. 検証

- 測定 commit `46bc0cd35` (LD-180 / #3863・`ldlib/cases.py` の `MACHINE_ENTRY` 6 行追加)。§2.1・§3 の実測はこの commit のコード。
- 測定 commit 以降のコード差分 (`main` 取り込み merge `4edbf8a95` を含む)。`git diff 46bc0cd35 HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/tests tools/liftdiff/liftdiff_e2e.sh` は 0 行ではない:
  ```
  tools/liftdiff/ldlib/cases.py                  |  1 +
  tools/liftdiff/liftdiff_e2e.sh                 |  4 ++-
  tools/liftdiff/rt/ld_core.h                    | 14 +++++---
  tools/liftdiff/rt/ld_ms_call.S                 |  6 +++-
  tools/liftdiff/tests/test_ld179_tagpoint_tr.py | 48 ++++++++++++++++++++++++++
  5 files changed, 67 insertions(+), 6 deletions(-)
  ```
  内容: `cases.py` の `0x4256c0: ['i64']` (main 側 #3862)。`ld_core.h` は `ld_int_arg` を追加し、`MultiByteToWideChar`・`WideCharToMultiByte` の int 引数を下位 32bit の符号付きで読む。`ld_ms_call.S` は `LD_STK_ENTRY28` 分岐 (既定のコードは従来と同じ)。`liftdiff_e2e.sh` は `test_ld179` の追加と `LD_STK_ENTRY28` 分岐。
- **未再測定の理由**: この run の `$ARTIFACTS_DIR` は `fl-win64` のみで、`tools/m11/work`・`tools/liftdiff/work`・`tools/ott/work` が無い (`work-m11`・`work-liftdiff` は未取得)。m11 の再 build は RetDec 路線で、この run の上限 (58 分) に収まらないと判断した。PR 本文に `oc_artifacts` 行を追加したが、取得されるのは次回の起動から。そのため §2・§2.1・§3 の数値は `46bc0cd35` の値で、現 HEAD の値ではない。推定値は書かない。
- 現 HEAD で実施した単体の確認 (実測): `python3 tools/liftdiff/tests/test_ld52_machine_sig.py` → PASS、`python3 tools/liftdiff/tests/test_ld179_tagpoint_tr.py` → PASS。
- 前回の測定 commit `f6abfd073`。`git diff f6abfd073 46bc0cd35 -- tools/liftdiff/ldlib` は `cases.py` の `MACHINE_ENTRY` 6 行追加のみ。
- 単体: `python3 tools/liftdiff/tests/test_ld52_machine_sig.py` → `PASS test_ld52_machine_sig`。
- 素材の展開: Actions の `oc_artifacts` 素材 `fl-win64`・`work-m11`・`work-liftdiff` を展開 (`fl-win64` は `FL_WIN64_DIR`、`docs/REFERENCES.md` の `[WIN64]`)。emcc は `[EMSDK]` (6.0.12) を使用。
- 機械語の読み (6 件) は作業用の一時スクリプトで capstone を使って行った (commit しない)。LD-53 の `ld53_arg_regs.py` の計数は使わず、呼び先の本体を人が読んだ (§1 の表が根拠)。
- 単体: `python3 tools/liftdiff/tests/test_ld52_machine_sig.py` → `PASS test_ld52_machine_sig` (e2e `[0/4]` に追加)。
- 製品 KPI (FLEngine 起動・最初のウィンドウ): 本 PR は起動・GUI に関わらないため書かない。
- 範囲外: 入口型の未確定 6 件と 4256c0 は実装していない (§4)。
