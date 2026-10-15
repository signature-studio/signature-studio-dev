# liftdiff LD-52 (#1528) — i128 引数の機械語入口型による case 投入と実行可能件数の実測

> 親: #1194 (LD-39)。前提: #1526 (LD-51)、投入形の判定は #1546 (LD-53・PR #2791・`REPORT_APPENDIX_LD53.md` §7)。
> 測定 commit: `b37494bec` (コードを変えた最後の commit)。`b37494bec` から HEAD までのコード差分は §5。
> 素材: `fl-win64` (`$RUNNER_TEMP/fl-win64/extracted/block00031_PE.bin`)・`work-m11`・`work-liftdiff`・`toolchain-emsdk`。
> `work-liftdiff` の `ld_wasm.cjs` は現行の `rt/ld_wasm.c` と export の引数数が合わない (`ld_w_snapshot`) ため使えず、`python3 liftdiff.py build targets/m11.json` (emsdk・約 9 秒) で再 build した。

## 1. 方式

IR の `i128` 引数は、機械語では xmm0 (double) か整数レジスタ 1 本の値 (LD-53 §7.1)。入口型どおりに投入する。

| VA | IR 署名 | 投入 (native sig) | 根拠 (LD-53) |
|---|---|---|---|
| `40c660` | `i64 (i128)` | `double` (xmm0) | 本体は `__asm_cvtsd2si(i128 %arg1)` (xmm0 の値)。xmm0 の参照 1 件・i128 の参照 0 件 |
| `40c750` | `i64 (i128)` | `double` (xmm0) | 本体は xmm0 の参照のみ |
| `653c80` | `i64 (i64,i64,i128)` | `i64,i64,i64` (r8 のみ使用) | 本体は `cmp r8,0x7fffffff`・`shl r8,2`。r9 の参照 0 件 |
| `691dd0` | `i64 (i64,i128,i64)` | `i64,i64,i64` (rcx ポインタ・rdx i64・r8 flag) | (a)/(b) を棄却した入口 (§7.1) |

実装 (`ldlib/cases.py` `MACHINE_ENTRY` / `machine_sig`):
- native は sig の型どおりに投入する (`rt/ld_native.c` は変更なし)。
- wasm は `m11_tr_<fn>` (i64×8 を受け、IR 引数へ `zext`) を `tr=1` で呼ぶ。`wsig=i64,...` で raw 64bit を渡す (`rt/ld_runner.mjs`)。`zext` により xmm0 の下位 64bit が入力値になる。
- 比較 (`ldlib/compare.py` `cmp_trace`): wsig を持つ関数**自身**の入口引数だけは比べない。wasm の entry 記録 (`irtool.instrument`) は IR の i128 引数を `0` と記録するため (§4 の未解決)。戻り値・memory・calls は比べる。他の関数の判定は変えない (wsig は machine-entry の sig 上書きにだけ付く)。

## 2. 対象 11 関数の実行可能件数 (HEAD `b37494bec`)

対象は sigs.json の定義済み関数のうち、params に `i128` を含む 10 関数 (`ret` が i128 の `1311ea0` は LD-24 の対象外) と `%tagPOINT` 1 関数。

実測コマンド: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 liftdiff.py batch targets/m11.json --set file:work/ld52_11.txt --shards 4 --nobuild --state auto` (7.9 秒)

| VA | IR 署名 | 判定 | 内容 |
|---|---|---|---|
| `40c660` | `i64 (i128)` | **match** | 11/11 パターンとも equal (ret・memory・calls が native と wasm で一致) |
| `40c750` | `i64 (i128)` | **match** | 11/11 パターンとも equal |
| `653c80` | `i64 (i64,i64,i128)` | unexec (`native_fault_all_patterns`) | 11 パターンとも native segv。segv の fault addr は記録されず原因未特定 (§4) |
| `691dd0` | `i64 (i64,i128,i64)` | unexec (`native_fault_all_patterns`) | z・s は rcx=0/3 の参照で segv (addr `0xc0`/`0xc3`・rip `0x6919f8`)。p0 等は rcx が blob の値を指して segv。オブジェクトの有効な内容が要る (§4) |
| `4256c0` | `ptr (%tagPOINT)` | unexec (`unsupported_sig`) | `m11_tr_function_4256c0` が `%tagPOINT zeroinitializer` を渡し、a0 (POINT 値) を捨てる (§4) |
| `442a50` `442b90` `664890` `6649b0` `6649c0` `664a80` | `i64 (i128)` | unexec (`unsupported_sig`) | 入口型の未確定 (LD-53 の方式で未読。§4) |

- 変更前 (origin/main `09b96c12f`・同じ build 手順・同じ batch): 一致 0 / 不一致 0 / 実行不能 11 (`unsupported_sig` 11)。
- 変更後: 一致 2 / 不一致 0 / 実行不能 9 (`unsupported_sig` 7・`native_fault_all_patterns` 2)。実行に入ったのは 4 関数 (うち 2 関数が一致)。
- 試行中の差分 (`callsite_arg_drop`・`xmm_arg_drop`) は、すべて wasm entry 記録の `i128 → 0` によるものだった。§1 の比較の扱いで取り除いた (取り除く前の版は 40c660・40c750 とも不一致)。

## 3. e2e (`bash tools/liftdiff/liftdiff_e2e.sh --m11-only`)

sample:800 (`--shards 12 --state auto`) の判定。`--m11-only` の所要 (実測・each run の exit と `LIFTDIFF_E2E PASS`)。

| run | commit | exit | 所要 | sample:800 一致 / 不一致 / 実行不能 |
|---|---|---|---|---|
| 同手順の比較 (再 build) | origin/main `09b96c12f` | 0 (PASS) | 193 s | 361 / 233 / 206 |
| 変更後 run 1 | 変更前 (コミット前の同一コード) | 0 (PASS) | 191 s | 360 / 234 / 206 |
| 変更後 run 2 | 変更前 (コミット前の同一コード) | 0 (PASS) | 189 s | 360 / 234 / 206 |
| **HEAD** | **`b37494bec`** | **0 (PASS)** | **185 s** | **360 / 234 / 206** |

- HEAD の `[0/4]` に追加したテスト `tests/test_ld52_machine_sig.py` は PASS。
- 負荷: HEAD の e2e 開始前 1 分 load 1.53、終了直後 4.75 (本 run の runner 上、他 job なし)。
- origin/main と HEAD の sample:800 の判定差は 6 関数 (`1060950` `1266e70` `43a3f0` `50abe0` `5c5500` `959a40`)。同一コードの run 1 と run 2 でも 4 関数が揺れる (`959a40` は REPORT_APPENDIX.md の run 依存 1 件と同じ。`50abe0` `5c5500` は hang と native_fault の入れ替わり)。差の出る関数はいずれも i128・%tagPOINT を持たず、変更は sig の上書きにしか分岐を足していないため、判定の差は run 間の揺れの範囲とみなす。sample:800 に `40c660` `40c750` は含まれない (`batch_sample_800.jsonl` で 0 件)。

## 4. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `4256c0` (%tagPOINT) の POINT 値が `m11_tr_` で渡らない (`tools/m11/m11_post.py` の生成が `zeroinitializer` を渡す)。`MACHINE_ENTRY` に入れられない | 実行不能 1 | [LD-179] |
| 残り 6 件 (`442a50` `442b90` `664890` `6649b0` `6649c0` `664a80`) の入口型を機械語で確定していない | 実行不能 6 | [LD-180] |
| `653c80` `691dd0` の native segv (691dd0 は rcx のオブジェクト内容、653c80 は fault addr 未記録)。`irtool.instrument` が IR の i128 入口を `0` と記録する (callee の入口比較の偽陽性の源。sample:800 への影響は未測定) | 実行不能 2・比較の信頼性 | [LD-181] |

## 5. 検証

- 測定 commit `b37494bec`。`git diff b37494bec HEAD -- tools/liftdiff/ldlib tools/liftdiff/rt tools/liftdiff/tests tools/liftdiff/liftdiff_e2e.sh` の出力は 0 行 (本節の REPORT・DOC_MAP の commit のみが続く)。
- 単体: `python3 tools/liftdiff/tests/test_ld52_machine_sig.py` → `PASS test_ld52_machine_sig` (e2e `[0/4]` に追加)。
- 製品 KPI (FLEngine 起動・最初のウィンドウ): 本 PR は起動・GUI に関わらないため書かない。
- 範囲外: 入口型の未確定 6 件と 4256c0 は実装していない (§4)。
