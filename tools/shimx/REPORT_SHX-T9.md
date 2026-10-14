# tools/shimx REPORT 付録 — SHX-T9 (#177) DllMain closure の SHIMX_TRACE 収集と残一覧

> 本体: `tools/shimx/REPORT.md` §6 (T9)。収集の再現は `tools/m11/shimx_link/e2e.sh` (前提: `tools/m11/m11_e2e.sh` の出力 = `tools/m11/work/`。素材 `oc_artifacts: fl-win64 work-m11 work-liftdiff`)。
> 数値の出典は commit 済みの `tools/m11/shimx_link/results/` (自動生成物)。PR 基点 `e398b2c` (main)。
> 2026-10-13 修正: 差し戻し (reviewer) を受けて、survey の数値を commit 済み results の値に揃えた。

## 1. 結論

- DllMain closure は**未完** (Todo 維持)。逐次起動 (`trace_soft_fix`) は unit #18 の `_UStrAsg` OOB (#232) で止まり、unit 完走 (stage 5/6) は未達。
- SHIMX_TRACE の収集は `results/survey.md` の集計から行った。GetProcAddress miss 65 件 / LoadLibrary 失敗 3 種 / CreateProcess 拒否 0 件。
- survey の unit 160 以降の range 連鎖 (783 件) は、`survey_trace.mjs` が InitTable 破壊 (unit 159 の OOB で `*(0x11eac90)` が 0 になる) を見ずに続行したことが原因と実測で確定し、harness を修正した (§3・#773)。

## 2. 実測 (出典: commit 済み results)

| 項目 | 値 | 出典 |
|---|---|---|
| リンク 5 variant | signature mismatch 0 / undefined 0 / duplicate 0 | `tools/m11/shimx_link/REPORT.md` (前回 run の値。本修正では再測していない) |
| 逐次起動 `trace_soft_fix` | init_count 18 / units_run 17 / threw = memory access out of bounds (#232) | `results/trace_units.md` |
| 逐次起動 `plain_failfast` | init_count 16 / units_run 15 / threw = Aborted (GUI `LoadStringW` の fail-fast) | `results/runs.json` |
| survey 942 unit 全体 | abort 1 / closure_outside 46 / halt0 53 / ok 800 / oob 41 / noproc 1 (合計 942) | `results/survey.md` |

### 2.1 GetProcAddress miss (`results/survey.md` の SHIMX_TRACE 集計, 計 65 件)

ログ行には名前部分が出ていない (`kernel32.dll!` の後が空) ため、DLL 単位で集計する。

| 対象 | 件数 | 初回 unit | 区分 | 扱い |
|---|---|---|---|---|
| kernel32 `#39682` (序数) | 1 | 2 | 序数 | R1 (`shimx_set_intptr_limit` 等 / 敷設 ≥0x10000) |
| kernel32 | 11 | 36 | 非 GUI | 未調査 |
| ntdll.dll | 1 | 18 | 非 GUI | 未調査 |
| ole32 | 6 | 107 | 非 GUI | 未調査 |
| shell32 | 1 | 137 | 非 GUI | 未調査 |
| advapi32 | 1 | 146 | 非 GUI | 未調査 |
| dwmapi | 23 | 146 | GUI 系 | tools/gui |
| user32 | 8 | 146 | GUI 系 | tools/gui |
| comctl32 | 12 | 299 | GUI 系 (common controls) | tools/gui |
| shcore | 1 | 146 | GUI 系 | tools/gui |

- 集計: 非 GUI 20 (kernel32 11 + ntdll 1 + ole32 6 + shell32 1 + advapi32 1) / GUI 系 44 (dwmapi 23 + user32 8 + comctl32 12 + shcore 1) / 序数 1。計 65。
- comctl32 は DLL 名で GUI 系に分類した (common controls は GUI 担当の領域)。ログに名前が出ていないため、個々の API 名での分類は未確認。
- R3 (lifttab) で kernel32 UI 言語 3 名はトークン解決済み (`[shimx] lifttab:` 行で確認)。`(null)` 行は DLL 名を出さないため、序数 miss の DLL 帰属は未確認。

### 2.2 LoadLibrary 失敗

| DLL | 初回 unit | 扱い |
|---|---|---|
| Msctf.dll | 104 | R4 (擬似 DLL 登録の要否は未決) |
| avrt | 146 | R4 |
| PowrProf.dll | 146 | R4 |

### 2.3 CreateProcess 拒否 / ShellExecute

`results/survey.md` の SHIMX_TRACE 行に 0 件。ShellExecuteW は survey の API 呼出表にも無い。

### 2.4 fail-fast 到達

- **逐次起動 `trace_soft_fix` (soft モード, 17 unit + #18) では shimx 起因の fail-fast は 0**。停止要因は `_UStrAsg` OOB (lift 側の #232)。
- **逐次起動 plain (既定 fail-fast) では shimx 起因の fail-fast で停止する**: `m11_sx_plain_failfast` / `m11_sx_trace_failfast_fix` とも `[shim] FAIL-FAST: unimplemented Win32 API: LoadStringW` (top frame `shim_unimplemented`) で Aborted。init_count 16 / units_run 15 で止まる。survey の LoadStringW 初出も unit 16。LoadStringW は GUI 系 API のスタブだが、shimx 側の fail-fast であることに変わりはない。
- **survey の unit 115**: shimx 版では fail-fast せず halt0 (§3.1)。baseline の abort (`EnterCriticalSection`、shim 側の未登録 CS) は shim 側の差であり、shimx 起因の fail-fast には数えない。R7 (`tools/shimx/REPORT_R1-R8.md`) の既定方針 (NULL は fail-fast のまま) は、本 survey の他の NULL 到達事例にのみ適用する。
- **plain 逐次起動の LoadStringW fail-fast**: 上記 (§2 の表) の通り shimx 起因として数える。起票先: tools/gui (GUI stub の実装側)。

## 3. survey の unit 160 以降 (#773 で切り分け済み)

実測 (`tools/m11/shimx_link/e2e.sh` の foreground 再実行, 素材 work-m11 / work-liftdiff, origin/main a5adb2fc):

- 修正前 (`survey_trace.mjs`): `SXL_SURVEY` の kinds は ok 137 / oob 6 / closure_outside 14 / halt0 2 / **range 783** / reboots 0。trace 無しの `m11_sx_plain_soft` でも同じ 783 件 (trace 機能とは無関係)。
- 原因: unit 159 (1 始まり, VA 0x26d1a0) の OOB 後、`*(0x11eac90)` (InitTable ポインタ) が `0xf768b0` から 0 に変わる。`m11_call_unit` は `tbl==0` で -1 を返すため、160 以降の全 unit が `lva=0x0` の range になる。
- 修正 (`survey_trace.mjs`): baseline (`m11_survey.mjs`) と同じく InitTable (先頭・末尾の proc VA) の破壊を検出し、その unit を `clobber` と記録して boot をやり直す。image の書き戻し方式は採らない (書き戻すと closure_outside が 796 件に増えた。shimx の import 状態が壊れるため)。
- 修正後: `SXL_SURVEY` kinds は ok 789 / oob 95 / closure_outside 47 / halt0 9 / clobber 1 / noproc 1 / reboots 1。range は 0。
- baseline (`m11_boot`) は ok 800 / oob 50 / halt0 44 / closure_outside 46 / abort 1 / noproc 1 (reboots 1)。ログ: `tools/m11/alloca/results/run/m11_boot_surveytrace.out` (`SXL_SURVEY` 行、追跡済み)。
- 裏付け (`tools/shimx/evidence_773/`、全出力は `survey_full_*.txt`、image sha256 は `image_sha256.txt`): `[EMSDK]` 6.0.12 で `build.sh` を clean rebuild (obj / gen / *.cjs 削除後) した image (`m11_sx_trace_soft_fix.cjs`, sha256 `b674477d…`) に対する foreground 実測。修正前 harness (a5adb2fc) は range 783 (ok 137 / oob 6 / closure_outside 14 / halt0 2)、修正後 harness (本 PR) は ok 789 / oob 95 / closure_outside 47 / halt0 9 / clobber 1 / noproc 1 / reboots 1 / range 0。baseline (`m11_boot.cjs`) は ok 800 / oob 50 / halt0 44 / closure_outside 46 / abort 1 / noproc 1 / reboots 1。修正後・baseline は PR の値と一致。
- 素材 `work-m11` 同梱の `m11_sx_trace_soft_fix.cjs` (sha256 `f100dd66…`, 2026-10-10 build, `.cjs.wasm` 同梱) は別 image。修正後 harness で測ると ok 800 / oob 41 / halt0 53 / closure_outside 46 / abort 1 / noproc 1 / reboots 1 / clobber 0 / range 0 (`survey_full_material_work-m11_f100dd66.txt`)。この image では range 783 も clobber も出ない。よって本節の数値は上の clean rebuild image に対するものに限る。
- 差分の説明 (未完): baseline は unit 115 で `EnterCriticalSection` の fail-fast (abort) に当たって reboot するが、shimx 版では同 unit が halt0 になり fail-fast に当たらない。以後の unit は状態がずれ、oob と halt0/ok が unit 単位で入れ替わる (unit 単位の差分は 81 件)。oob 増 (50→95) の内訳を unit 単位で説明するところまでは未達。起票先: 子 issue #1255 (`[SHX-T9c]`)。

### 3.1 #1255 の切り分け (実測)

測定 commit: `604e900f` (origin/main)。shimx 版は `tools/m11/shimx_link/build.sh --trace --soft --fix` で clean rebuild (17 秒・`[sxlink] OK`、sha256 `c6461194…`)。baseline は素材 `work-m11` の `m11_boot.cjs` (sha256 `e826e6c0…`)。survey は `SHIMX_TRACE=1 node survey_trace.mjs` (foreground 5 分 13 秒)。load 0.38–0.47 (4 CPU)。

- shimx 版: ok 789 / oob 95 / closure_outside 47 / halt0 9 / clobber 1 / noproc 1 / reboots 1 (`evidence_773` の集計と一致)。
- baseline: ok 800 / oob 50 / halt0 44 / closure_outside 46 / abort 1 / noproc 1 / reboots 1。
- 差分 81 unit の kind 遷移: ok→oob 31 / halt0→oob 26 / halt0→ok 10 / oob→ok 10 / halt0→closure_outside 1 / abort→halt0 1 / oob→halt0 1 / oob→clobber 1。差分は全 100 unit 区間にわたる (最多 0 区間 13)。
- 最初の差分は **unit 23** (LVA 0x67f00、baseline halt0 → shimx closure_outside)。unit 115 より前。

**unit 115 の差 (受入条件 1)**: 同じ前処理 (unit 1〜114 を順に実行) で、baseline は `m11_boot.cjs` 単独でも `EnterCriticalSection (未初期化/未登録)` で abort する (`tools/shim/src/sync.c`: CS を表に登録した後の mutex 写影で、表に無い CS を fail-fast)。shimx 版は同じ unit で `EnterCriticalSection` 18 回・`LeaveCriticalSection` 18 回が対で通り、halt0 (正常停止) になる (`tools/shimx/src/locks.c` は ゼロ初期化の CS を未ロック扱いし、NULL/非整列のみ fail-fast)。差は「未登録 CS を abort するか、未ロックとして扱うか」の実装差が差の直接の機構と推定する。shimx 版の halt0 は、この実装差により fail-fast に当たらず到達したものと読む。CS ポインタの具体値 (両者の一致) は未比較のため、両者が同一の CS を見ているかは未確認。

**unit 23 の分岐 (#1465 受入条件 1)**: 実測の確定事項は survey JSON (`evidence_1255/*.survey.json`) の kind のみ。unit 23 (LVA 0x67f00) は baseline `halt0` → shimx 版 `closure_outside` で、両者とも `shim_calls` は空。unit 30 (LVA 0xfa9390) は両 variant とも `closure_outside`・`shim_calls` 空。

- 未再現: 以前の記述にあった「unit 23 の icall miss 2 件 (target `0x457860`)」「unit 30 の `0x457860` miss」の実測は、この commit からは再現できない。根拠の probe (`tools/m11/work/probe_unit23.mjs`) は作業域のみに置かれ commit されておらず、survey JSON にも icall 情報が無い。よってこの数値は本 REPORT の結論に使わない。
- 機構の仮説 (未検証・コード根拠のみ): unit 23 (`function_467c40`) は `.bss` 0x15f10e0 の関数ポインタ slot を `call` する。この slot は `function_457c70` が `GetProcAddress(oleaut32, "VarBstrFromBool")` で埋める。`function_457c40` は解決失敗時の fallback として `0x457860` を返す (`tools/m11/m11_ov.c:1173-1175` の注釈)。shimx 版でこの `0x457860` が dispatch 表に無ければ icall miss になる、という説明は未確認の仮説である。
- baseline の `m11_win.c:90` は `GetProcAddress` が常に 0 を返す。baseline の unit 23 がこの slot 経路に入らない理由 (`0xf960` 以降の分岐) は未確定。
- 未確定 (受入条件 1 の残り): shimx 版で `function_457c70` が呼ばれる unit と `GetModuleHandleW(oleaut32)` の戻り値は未確認。「shimx の GetProcAddress が NULL を返すから」とは断定しない。`0xf960` 以降の分岐条件の特定も未了 (起票先: #1607 `[SHX-T9e]`)。
- unit 23 の icall miss の再現手順 (hook・入力・実行コマンド) は未確定。再現させる場合は、probe を追跡対象パスに commit してから本節に実行コマンドを書く。

**oob 増 (受入条件 2)**: oob 増 57 件 (ok→oob 31 / halt0→oob 26) と減 12 件 (oob→ok 10 / oob→halt0 1 / oob→clobber 1)。shimx 版の oob 95 件のうち shim 呼出しを伴うものは 12 件、baseline の oob 50 件のうち shim 呼出しを伴うものは 0 件 (`evidence_1255/baseline_m11_boot.survey.json` の `per_unit`・`shim_calls`)。増分 57 件の unit 単位の frame 分類は未完 (起票先: 子 issue #1607 `[SHX-T9e]`)。`evidence_1255/unit_diff_out.txt` が unit 別の遷移一覧。

再現: `python3 tools/shimx/evidence_1255/unit_diff.py <baseline.survey.json> <shimx.survey.json>` (per-unit JSON は `evidence_1255/` に保存)。

再現 (§3.5): `node tools/m11/shimx_link/survey_frames.mjs <cjs> --out DIR [--only 88,161,...] [--iso]` (`--iso` は 1 unit ずつ新インスタンス)。増分 57 unit は `tools/shimx/evidence_1986/gain57_units.txt`、結果は `gain57_frames.tsv`。

### 3.2 検証の commit と差分 (WORKFLOW §6)

- 測定 commit: `604e900f` (origin/main)。本 PR の変更は `tools/shimx/REPORT_SHX-T9.md` と `tools/shimx/evidence_1255/` のみで、測定対象のコード (`tools/m11/shimx_link/`・`tools/shimx/src`) には差分が無い。

### 3.3 unit 23 の icall miss と slot 0x15f10e0 (#1607 SHX-T9e の実測)

測定: `tools/m11/shimx_link/probe_unit23.mjs` (unit 1〜22 を順に実行した後、unit 23 (index 22) を 1 回実行)。shimx 版は `build.sh --trace --soft --fix` (clean rebuild, `[sxlink] OK`)、baseline は `work-m11` の `m11_boot.cjs`。load 約 0.3 (4 CPU)。出力は `tools/shimx/evidence_1607/probe_u23_{shimx,baseline}.txt`。

| 項目 | shimx 版 | baseline |
|---|---|---|
| unit 23 (LVA 0x67f00) の戻り値 | `ret=2` (closure_outside) | `halt0` |
| icall miss (unique / total) | 2 / 3 (`0x4476d0`・**`0x457860`**) | 0 / 0 |
| `.bss` 0x15f10e0 (VarBstrFromBool slot) の値: unit 23 の前 / 後 | 0x0 / 0x0 | 0x0 / 0x0 |
| unit 20〜22 の間の GetProcAddress 呼出し (sxt 計数) | 6 → 6 (unit 22 で GetModuleHandleW 6 → 7) | sxt 計数なし (未取得) |

- unit 23 の miss 先 `0x457860` は REPORT §3.1 の仮説 (slot の fallback) と一致した。shimx 版でのみ発生する。
- unit 23 の直前まで slot 0x15f10e0 は 0 のまま。`function_457c70` (slot を `GetProcAddress(oleaut32,"VarBstrFromBool")` で埋める) が unit 1〜22 の中で呼ばれていないことが sxt 計数から読める (unit 22 までの GetProcAddress 増分は 0)。
- 未確定: `function_457c70` の呼出し元 (`function_458020` 経由) が unit 何番で起きるか、`GetModuleHandleW(oleaut32)` / `GetProcAddress` の戻り値。sxt 計数は呼出し回数のみで戻り値を持たないため、戻り値は wrapper の追加が要る。起票先: #1985 (`[SHX-T9f]`)。
- baseline 側は sxt 計数が無く (`m11_boot.cjs` に `_sxt_*` 無し)、GetProcAddress 呼出しの有無は未取得。baseline の unit 23 が `0xf960` 以降どの分岐に入るかも未特定。起票先: #1985 (`[SHX-T9f]`)。
- oob 増 57 件の unit 単位 frame 分類は未着手。起票先: #1986 (`[SHX-T9g]`)。

#### 3.3.1 戻り値の実測 (SHX-T9f #1985)

- 測定 commit: `7e9940ac` (戻り値記録を追加したコード。clean rebuild `build.sh --trace --soft --fix` → `[sxlink] OK`)。実行は `probe_unit23.mjs` (unit 1〜22 の後に unit 23 を 1 回)。load 0.33 (4 CPU)。出力は `tools/shimx/evidence_1985/probe_u23_shimx_ret.txt`。
- 戻り値は `gen_link.py` が生成する trace wrapper を経由して `GetModuleHandleW` / `GetProcAddress` だけ記録する (`RET_LOG`・`trace_rt.c` の `sxt_ret`)。他の shimx 呼出しは従来どおり回数のみ。

| unit | 呼出し | 引数・戻り値 (実測) |
|---|---|---|
| 22 | `GetModuleHandleW` | `"oleaut32.dll"` → `0x11443000` (非 NULL) |
| 22 | `GetProcAddress` | 呼ばれていない (unit 22 の GetProcAddress 増分 0) |
| 23 | shimx 呼出し | 0 件 (`CALL` 行なし)。`ret=2`・icall miss 2 件 (`0x4476d0`・`0x457860`) |

- `function_457c70` (IR: `boot_final3.ll` L160490 付近) は先頭で `GetModuleHandleW(L"oleaut32.dll")` を呼ぶ。unit 22 の上の呼出しがこれに一致する (引数の一致による**推定**)。wrapper は呼出し元アドレスを記録していないため、この呼出しが `function_457c70` 由来であることは**未確定** (記録には wrapper への呼出し元 PC 追加が要る)。IR 上、`GetModuleHandleW` の戻り値 (`%0`) は `function_457c70` 内で一度も使われない。`function_457c40` は第 1 引数 (`stack_var_-56` の alloca) の `+40` を読み、0 なら fallback (`arg3`) を返す。実測では unit 22〜23 に `GetProcAddress("VarBstrFromBool")` の呼出しが無く、slot は 0 のまま残った。「`+40` が 0 だから fallback する」は IR からの推測で、`+40` の実行時値は未測定。
- 上の経路の是正は受入条件外。今回の実測は「`GetModuleHandleW(oleaut32)` は非 NULL を返すが、戻り値が GetProcAddress に渡らない」まで。
- baseline (`m11_boot.cjs`・sxt 無し): unit 23 は `halt0` のまま。戻り値ログは取れない (wrapper 無し)。`0xf960` 以降の分岐条件は未特定 → 子 issue へ。
- 証跡: `tools/shimx/evidence_1985/probe_u23_shimx_ret.txt` / `probe_u23_baseline.txt`。

#### 3.3.2 slot アドレスの訂正と分岐点の実測 (SHX-T9f #1985 続き)

- **訂正**: §3.3.1 までの probe は slot を VA `0x15f10e0` で読んでいた (0 のまま見えた)。wasm 線形メモリでは LVA = VA − 0x400000 なので正しい位置は **LVA `0x11f10e0`**。`.data` の関数ポインタ `0x11e3af0` が `0x11f10e0` を指すことも確認 (`function_467c40` の `Q(Q(R(0x11e3af0)))`)。`probe_unit23.mjs` の参照を LVA に修正 (commit `c718dd00`)。
- 修正後の slot 値: unit 22 の後 (unit 23 の前) に両版とも **`0x457860`** (fallback) が入っている。すなわち `function_457c70` による `GetProcAddress` 埋めは unit 1〜22 で起きていない。
- 分岐点 (`TRACE` = `m11_set_trace` + `SHIMX_TRACE=1`、clean rebuild、unit 1〜22 の後に unit 23 を 1 回):
  - baseline: `icall 0x67f00` → `FormatMessageW` (stub) → `UStrAsg dest=0x315f0` → Halt0。**`0xf960` に入らない**。
  - shimx: `icall 0x67f00` → **`icall 0xf960`** (`function_40f960` = TObject.NewInstance) → `icall-miss 0x457860` → `UStrAsg` 多数 → `ret=2`。
  - よって baseline の halt0 は `0x67f00` の先頭直後で起き、shimx 版の `0xf960` 進入 (NewInstance) と分岐する。
- 既存の「`ret=2` vs `halt0`」の食い違いは、古い `work/shimx_link/obj/` 由来の成果物が原因だった。`build.sh --trace --soft --fix` の clean rebuild (`obj/`・`gen/` を削除) で `ret=2` が再現する。
- 未確定: `0x67f00` の中で shimx 版だけ `0xf960` に進む条件 (icall の直前の比較値)。`function_467f00` (IR L174409) の分岐は `0x11f1114` の一度きりの初期化フラグのみで、unit 23 の `0x67f00` (LVA) 本体の icall 列は未読。`FormatMessageW` / `LoadStringW` の戻り値が差の候補。起票先: #1985 に残す。
- 証跡: `tools/shimx/evidence_1985/probe_u23_{shimx,baseline}_slotfix.txt` / `trace_u23_{shimx,baseline}_head.txt`。trace の再現は `tools/m11/shimx_link/probe_trace_unit.mjs`。
- 測定 commit: `98508612` (trace 取得に使った `probe_trace_unit.mjs` を追加した commit)。slot 訂正の commit は `c718dd00` (`probe_unit23.mjs` の 4 行)。`git show 98508612:tools/m11/shimx_link/probe_trace_unit.mjs` と作業ツリーのファイルは byte 一致。
- `git diff 98508612 HEAD -- tools/m11/shimx_link tools/shimx/src`: 出力 0 行 (測定後の変更は REPORT と evidence のみ)。

#### 3.3.3 unit 23 直前の状態と --fix 依存の確認 (SHX-T9f #1985 続き)

- 測定: `tools/m11/shimx_link/probe_flag_1985.mjs` (unit 1〜22 の後、unit 23 の直前の状態を読んでから unit 23 を 1 回 trace)。shimx 版は `build.sh --trace --soft --fix` の clean rebuild (`obj/`・`gen/` 削除後、`[sxlink] OK`、load 0.96 / 4 CPU)。証跡: `tools/shimx/evidence_1985/probe_flag_{shimx_fix,shimx_nofix,baseline}.txt`。
- 結果 (3 版とも同じ入口状態):

| 版 | unit 23 直前の `0x11f1114` (初期化フラグ) | `Q(6712)` | slot `0x11f10e0` | unit 23 の結果 |
|---|---|---|---|---|
| shimx `--fix` (clean rebuild) | 0 | `0x1c0200250000` | `0x457860` | `ret=2` (`0xf960` 進入 → icall-miss `0x457860`) |
| shimx `--fix` 無し | 0 | 同左 | 同左 | `halt0` (`FormatMessageW` 経路に入らず `0x67f00` 直後で Halt0) |
| baseline (`m11_boot.cjs`) | 0 | 同左 | 同左 | `halt0` |

- 確定: `ret=2` は `--fix` の IR に依存する (`--fix` 無しの shimx は baseline と同じ `halt0`)。`0x11f1114` と `Q(6712)` は 3 版で一致しており、unit 23 の入口状態は分岐の原因ではない。
- 確定: `function_467f00` (IR) は flag==0 のとき `function_40f9e0(arg, (arg2&~0xff)|1)` を無条件に呼ぶ。`function_40f9e0` は下位バイトが非 0 なら `function_410320` (`_ClassCreate`) → `ICALL_AT(Q(self-0x30))` = `0xf960` へ進む。したがって shimx 版の `0xf960` 進入は IR の構造どおり。
- 未確定: baseline が `0x67f00` の直後に `FormatMessageW` へ進む理由。`m11_boot.cjs` は `--fix` 無しの別 IR 由来で、`0x67f00` の入口 `arg2` (icall 時の引数) と `m11_icall` の dispatch 先の比較は未実測。残りの差はここにある (起票先: #1985 に残す)。
- 注記: `probe_flag_shimx_fix.txt` は先頭 80 行のみ保存 (`[m11][UStrAsg]` の繰り返しを省略)。全行は再現コマンドで得られる。

### 3.4 検証の commit と差分 (WORKFLOW §6)

- 測定の基底: `522da441` (origin/main)。測定に使った probe は本 PR で `tools/m11/shimx_link/probe_unit23.mjs` として追加 (測定対象の shimx・m11 のコードは未変更)。
- `git diff 522da441 HEAD -- tools/m11/shimx_link tools/shimx/src` の差分は probe 1 本の追加のみ。

### 3.5 oob 増 57 件の unit 単位 trap frame 分類 (#1986 SHX-T9g の実測)

- 測定: `tools/m11/shimx_link/survey_frames.mjs` (新規・survey_trace と同じ unit 隔離順で wasm trap frame を残す)。shimx 版は `build.sh --trace --soft --fix` の clean rebuild (sha256 `c6461194…`)、baseline は `work-m11` の `m11_boot.cjs`。
- 再現実測 (順次 = survey と同じ harness): shimx ok 789 / oob 95 / halt0 9 / closure_outside 47 / clobber 1 / noproc 1。baseline ok 800 / oob 50 / halt0 44 / closure_outside 46 / abort 1 / noproc 1。`evidence_1255` の値と一致。
- 単独実測 (`--iso`: 増 57 unit を毎回新インスタンスで 1 unit ずつ実行。前 unit の状態を持ち越さない): shimx 57/57 が oob。baseline は 37 ok / 18 halt0 / 2 oob。
- trap site (top wasm frame): shimx の 57 件のうち **56 件が `function_407a50__lifted`** (単独実測でも 57 件同じ)。残り 1 件 (unit 88) が `function_418190`。
- 既存との関係: baseline の oob 50 件のうち 32 件も同じ関数 `function_407a50__lifted` で trap している (baseline の offset は 0x13ccb9、shimx は 0x17ffe3 で、offset はビルド間で比べられない)。増分 57 件はこの既存 oob 関数への到達が増えたもの。
- shim 呼出しの有無: 57 件のうち順次 shim 呼出しを伴うのは 6 件 (`evidence_1986/gain57_frames.tsv`)。trap frame の上位に shim 関数は無い (`__wrap_m11_icall` / `m11_icall` は呼出経路の下位にだけ現れる)。
- 対照実験 (`--fix` の有無だけ変えた shimx 版を単独実行): `m11_sx_trace_soft.cjs` (`--fix` 無し) では同じ 57 unit が ok 35 / halt0 20 / oob 2。`--fix` 有り (`m11_sx_trace_soft_fix.cjs`) は 57/57 oob。よって増分 57 件の oob は shimx の import 差ではなく、`build.sh --fix` の alloca 拡幅 (`fix_alloca.py`) が IR を変えたことによる。
- 分類 (受入条件 1): 増分 57 件は「`--fix` IR で `function_407a50__lifted` の oob に到達するようになった」もの。shim の差分ではない。`--fix` の拡幅が `function_407a50` の到達経路 (呼出し元の stack 配置) を変えたと推定するが、機構は未特定。`fix_report.json` は 407a50 に触れていない。
- 単独実行で再現するため、前 unit の状態持ち越しではない。baseline の oob 50 件のうち 32 件も同じ関数で trap する (既存の oob 要因)。

### 3.6 検証の commit と差分 (WORKFLOW §6)

- 測定に使ったコード: 既存の測定対象 (`tools/m11/shimx_link/` の既存ファイル・`tools/shimx/src`) は origin/main `5229fe5f` と同一 (`git diff --stat 5229fe5f HEAD -- tools/m11/shimx_link tools/shimx/src` は `survey_frames.mjs` の追加のみ)。shimx 版は同じ build.sh で clean rebuild (sha256 `c6461194…`)、baseline は `work-m11` の `m11_boot.cjs`。
- 本 PR の差分: 追加 `tools/m11/shimx_link/survey_frames.mjs`・`tools/shimx/evidence_1986/`、更新 `tools/shimx/REPORT_SHX-T9.md`。既存の測定コードは変更していない。

## 4. 残一覧 (BACKLOG 反映用の要約)

| 区分 | 件数 | 起票先 |
|---|---|---|
| DllMain closure 完走 (stage 5/6) | 未達 | #232 (CLOSED・停止点 `_UStrAsg` OOB のみ記録) |
| GetProcAddress 名前空 miss (非 GUI) | 20 | shimx BACKLOG (P1/P2 追加候補) |
| GetProcAddress GUI 系 miss | 44 | tools/gui |
| GetProcAddress 序数 miss (kernel32 `#39682`) | 1 | R1 (intptr 閾値 / 敷設) |
| LoadLibrary 失敗 (Msctf / avrt / PowrProf) | 3 | R4 (`tools/shimx/REPORT_R1-R8.md`) |
| plain 逐次起動の shimx fail-fast (LoadStringW, GUI stub) | 1 | tools/gui |
| survey unit 160 以降の range 連鎖 | 解消 (harness 修正) | #773 |
| survey の unit 単位差分: unit 115 の fail-fast 差 | 差の機構を推定 (§3.1)。CS ポインタ一致は未比較 | #1255 (`[SHX-T9c]`) |
| survey の unit 単位差分: unit 23 の分岐・oob 増 57 件の内訳 | 未説明 | #1465 (`[SHX-T9d]`) |
| unit 23 の slot 0x15f10e0 の埋まり経路 (`function_457c70` の呼出し unit・戻り値) と baseline の 0xf960 以降の分岐 | 未説明 (miss 先 0x457860 は実測で確定) | #1985 (`[SHX-T9f]`) |
| oob 増 57 件の unit 単位 frame 分類 | 未説明 | #1986 (`[SHX-T9g]`) |

## 5. 再現性

- 測定 commit: `c17ac666` (`build.sh` の PATH 修正 05b2c71b を含む)。測定後のコード差分 (`git diff c17ac666 HEAD -- tools/m11/shimx_link/survey_trace.mjs tools/m11/shimx_link/build.sh tools/shimx/src`) は出力 0 行。素材は `oc_artifacts: fl-win64 work-m11 work-liftdiff` で展開 (`tools/m11/work/`・`tools/liftdiff/work/`)。IR 再生成 (`m11_gen_ir2.sh`) は行わず、素材の `boot_final3.ll` / `m11_image.bin` を使用。image は `e2e.sh` で clean rebuild (obj / gen を削除してから実行)。
- image の build には `[EMSDK]` (6.0.12) が必要。`emsdk_env.sh` は PATH の `upstream/bin` を外すため、`build.sh` の `llvm-nm` が見つからず 5 本とも失敗する (失敗しても `e2e.sh` は exit 0 を返す)。`build.sh` で `upstream/bin` を PATH に戻して解消 (symlink 不要。HEAD の build.sh で確認済み)。build ログの `[sxlink] OK` で成功を確認すること。
- `e2e.sh` を再実行すると `tools/m11/shimx_link/results/` の自動生成物が書き換わる (commit 済みと生成元が異なる)。本 PR では results を HEAD に戻し、裏付けは `evidence_773/` に置いた。
