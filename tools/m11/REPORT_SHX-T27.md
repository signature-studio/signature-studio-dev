# SHX-T27 (#1630): unit 18 の GetLocaleInfoW 反復と OOB の切り分け、file API 到達経路と ftrace 件数 (親 #1493 / 関連 #1050)

## 1. 結論

- **unit 18 の OOB (`function_4133f0`) は、素材 `work-m11` の IR が古い (alloca 拡幅が現行より前の版。IR の差は §4-B の alloca 型のみ) ために出ていた。** 現行の生成手順 (`m11_e2e.sh`) で IR を作り直すと消える。前 2 run の「stack 最上段を export 名で解決」「呼出チェーンの静的確認」は、この古い IR 上の調査だった。
  - ネガコン (§4-B): 新 IR のうち `function_44bae0` の alloca (`stack_var_-88`: `i64` → `[11 x i64]`) だけを古い形に戻すと、OOB が同じ形 (`old=0x100000000`・`units_run=17`) で再現する。`446400` だけ・`44bb70` だけを戻しても再現しない。
- 「`GetLocaleInfoW` 66 回反復」は誤読だった。**66 は unit 18 の shimx 呼出の総数**で、`GetLocaleInfoW` は古い IR で 48 回・新 IR で 54 回。いずれも有限回で、無限反復ではない。呼出元は `function_446400` (§3)。
- 新 IR での逐次 boot は **別の欠陥で止まる**: `function_448490` の入れ子手続 `function_4483f0` が親フレームを正しく読めず、`VirtualAlloc(0x76910000)` を要求 → NULL → `MessageBoxA "Runtime error 0 at …"` → Halt0 → longjmp (`dllmain_done=true`、`units_run=17`)。新類型 **D23 候補** (§5)。
- `GetLocaleInfoW` を 0 返却に戻す対照 (§4-D) では unit 53 まで進み、止まるのは `function_8c5eb0` の `unreachable` (T26・#1629 と同じ)。この区間でも file API は 0 件で、ftrace も 0 行。
- file API (`GetFileAttributesW`) が最初に呼ばれるのは **unit 150** (§6)。逐次 boot では unit 18 と unit 57 の 2 つの停止の先にあり、停止前には到達しない。unit 隔離実行 (survey 方式) では ftrace が **10 行** (全て `GetFileAttributesW`)。逐次 boot の ftrace は 0 行のまま。

## 2. 測定条件

- 測定 commit: `e4be81ff030538ab524e2fd7a6adbc6de901f07c` (コード差分の最終 commit。本 REPORT のみが後続)。
- 場所: `git worktree add ../ws-1630` (main の共有ツリーは使わない)。`work-m11` を `tar --zstd -xf` で worktree に展開 (`tools/m11/work/` 233 エントリ・gitignore)。`fl-win64` は `$RUNNER_TEMP/fl-win64` に展開し `FL_WIN64_DIR` を指定。
- **IR の作り直し** (これが本 REPORT の前提): `work-m11` には `lift_pe.sha256` が無いため、そのままの `m11_e2e.sh` は `--full` (Ghidra 要) に入って落ちる (`functions_dll.csv` 無し)。PE の sha256 を `tools/m11/work/lift_pe.sha256` に書いてから `bash tools/m11/m11_e2e.sh` を実行した。
  - 結果: `gen_ir2` / `lift boot5 (RetDec)` / `gen_ir2 (boot5 追加)` / `m11_data_gen` / `m11_image_gen` / `build` が ok、所要 2 分 47 秒。`M11_SUMMARY`: `reached_stage=4`・`units_run_full=53`・`survey_ok=872`・`survey_trap=23`・停止は `function_8c5eb0`。`ir_conditions`: `ldfix=applied` `qstore=applied`、`ir_sha256=6909f85d…bacbcc62` (IR の sha256 は実行ごとに変わる。#1664)。
- 以降の shimx リンク測定は全てこの新 IR (`work/boot_final3.ll`) 上。測定時 load (1 分平均) 0.27〜0.7。

## 3. 受入条件ごとの回答

| 受入条件 | 判定 | 根拠 |
|---|---|---|
| `GetLocaleInfoW` 反復の呼出元と、止まらない理由 | 達成 | 呼出元は `function_446400` (薄いラッパ `function_446370` / `function_4463d0` 経由)。反復は有限 (48→54 回)。「止まらない」という前提が誤り。止まる要因は §1 の 2 段 (古い IR の OOB → 新 IR の入れ子手続欠陥)。IR 上の観察では、`function_446400` は locale の各項目を連続して読み、日付/時刻書式の変換 (`function_448350` → `function_448490`) を呼ぶ (Delphi の locale 書式設定の初期化に相当すると推定。実コードとの突合は未実施) |
| 停止より前に file API が呼ばれるべき経路と呼出順 | 達成 (経路は unit 隔離実行で確定。逐次 boot では未到達) | §6 |
| ftrace 件数 > 0 を実測 | 達成 (unit 隔離実行で 10 行)。逐次 boot は 0 行のまま | §4-E |
| 件数と api 内訳を REPORT に記録 | 達成 | §4-E |
| commit 済み HEAD で再現 | 達成 | §2 の測定 commit |
| (移管) `function_8c5eb0` の D19 と別原因の類型を DEFECTS.md 候補に記録 | **未達 → #2446 へ移管** | 原因の切り分けが先 (本文「原因切り分け後に類型名を付ける」)。#1630 の本文から外した。§7 |

## 4. 実測 (測定 commit `e4be81ff`)

### 4-A. 新 IR での trace build と実 boot

| 段階 | 結果 |
|---|---|
| `bash tools/m11/shimx_link/build.sh --trace --soft` | rc=0 / 7.6 s / `signature mismatch=1 undefined symbol=0 duplicate=0` |
| `SHIMX_TRACE_FILE=/ftrace.jsonl node tools/m11/shimx_link/run_trace.mjs <cjs> --out DIR` | rc=0 / 0.43 s / `units_run=17` `icall_ok=24` `icall_miss=1` `dllmain_done=true` `longjmp_hit=1` `boot_rc=1` `threw=null` |
| trace | `total_calls=106` `distinct_called=29` `dropped=0`。unit 18 は 75 呼出 (16 種)。`GetLocaleInfoW` は 54 回 (1 + `EnumCalendarInfoW` 2 + `GetCurrentThreadId` 1 + 53 連続) |
| ftrace | **0 行** (`ftrace_error` 無し) |

古い IR (前 run・`work-m11` そのまま): 同じ手順で `units_run=17` `threw="memory access out of bounds"` `total_calls=97`、unit 18 は 66 呼出 (13 種)、`GetLocaleInfoW` は 48 回 (1 + 47 連続)。ftrace 0 行。

### 4-B. ネガコン: 古い alloca に戻す (`experiments/t27_nc_swap.py`)

新 IR の指定関数だけを古い IR の本体に差し替える。差分は alloca の型 1〜2 行のみ (`446400`: `stack_var_-32` と `-80`、`44bb70`: `-416` が `[49 x i64]` ↔ `[52 x i64]`、`44bae0`: `-88` が `i64` ↔ `[11 x i64]`、`448350`: `-16`、`446370`: `-536` が `[64 x i64]` ↔ `[67 x i64]`)。

| 差し替え (古い形に戻す関数) | 結果 |
|---|---|
| 5 関数 (446400 44bb70 44bae0 448350 446370) | OOB 再現: `units_run=17` `dllmain_done=false` `total_calls=97`。`probe_t27_oob.mjs`: `dest=0x112e6328` `old=0x100000000` `hdr=0xfffffff0` |
| `44bae0` のみ | OOB 再現: `total_calls=99`。`old=0x100000000` |
| `446400` のみ / `44bb70` のみ (本 run の予備測定。commit 前の同一コード・同じ手順) | 再現せず (新 IR と同じ `dllmain_done=true` `total_calls=106`) |

- OOB の形: `function_4133f0` は Delphi の `_UStrAsg` 相当 (`*dest` を読み、非 0 なら参照カウント `[old-8]` を触る)。古い IR では `dest` の slot (`0x112e6328`、影スタック上) に `0x100000000` が入っており、64bit では非 0 だがアドレスは 32bit に wrap されて `[0xfffffff8]` を読み、範囲外で落ちる。slot の上位 4 B が 1 になる機構は、`m11_build.sh` と `tools/m11/alloca/REPORT.md` の R8 の記述 (`44bae0` の局所 record が 8 B の alloca に縮み、callee `44ba50` の書込みが隣の record を壊す) と一致する。slot がどの record かは未確認 (推定)。

### 4-C. 新 IR での停止点の stack (`probe_t27_stack.mjs`)

- `[m11][VA] #1 size=1989214208 (0x76910000)` の時点の呼出: `VirtualAlloc` ← `function_407770` ← `function_409410` ← `function_412c20` ← `function_4136a0` ← `function_413760` ← **`function_4483f0`** ← **`function_448490`** ← `function_448350` ← `function_446400` ← `function_44bb70` ← `function_455790` ← icall ← `function_4120c0` ← `m11_InitLib` ← `function_41d8f0` ← `entry_point`。
- 同じ stack から `MessageBoxA "Runtime error   0 at 000000001029E900"` が出る (`function_4127d0` ← … ← `function_413760` ← `function_4483f0`)。

### 4-D. 対照: `GetLocaleInfoW` / `EnumCalendarInfoW` を 0 返却 (`experiments/t27_relink.sh locale0`)

`units_run=53` `init_count_var=57` `icall_ok=236` `icall_miss=3` `threw="unreachable"` (stack 最上段は `function_8c5eb0` ← `function_56fde0`)。`total_calls=173` `distinct_called=35`。呼出のあった unit は 0・2・16・17・18・22・23・36・42・44・46・52。file API は 0 件 (`GetModuleFileNameW` のみ)。ftrace 0 行。リンク 4.1 s。

### 4-E. unit 隔離実行での ftrace (`probe_t27_ftrace.mjs <cjs> 300`)

survey_trace.mjs と同じ方式 (survey モード boot → unit 1〜300 を順に try/catch)。5 分 4 秒。

| 項目 | 値 |
|---|---|
| `SHIMX_TRACE_FILE` の行数 | **10 行** |
| api 内訳 | `GetFileAttributesW` 10 |
| 発生 unit | 150 (2 行・LVA `0x264260`)・159 (4 行・`0x26d1a0`)・191 (2 行・`0x2cf480`)・281 (2 行・`0x416010`)。全て各 unit で `GetModuleFileNameW` 3 回の後に `GetFileAttributesW`、unit は `oob` で終わる |
| 行の内容 | 全 10 行 `guest=""` (空文字列)・`ok=false`・`err=123` (ERROR_INVALID_NAME) |

## 5. 新しい停止: 入れ子手続の親フレーム共有 (D23 候補)

- 機械語 (`function_448490`): `function_4483f0` への call が 8 箇所あり、目視した直前の命令は `mov rcx, rbp`。`function_4483f0` は `[rbx+0x70]` (親の引数 `rcx` の home slot)・`[rbx+0x4c]`・`[rbx+0x48]` (親の局所) を読み、`[rbx+0x4c]` と `[rbx+0x48]` を +1 する Delphi の入れ子手続 (`Append`)。
- IR (`function_448490`): 渡される `%stack_var_-104` は `alloca [6 x i64]` (48 B) だが、callee が触るのは先頭から +0x48〜+0x78 (最大 120 B)。親の引数 (`%arg1`) と局所 `[rbp+0x48]` (`%stack_var_-32.*.reg2mem`) は SSA / 別 alloca で、`%stack_var_-104` の続きには無い。callee は影スタックの隣接領域を親の値として読む。
- 症状: `function_413760` (配列の unique 化) が壊れた長さで `VirtualAlloc(0x76910000)` を要求し、`GetMem` が NULL → Runtime error → Halt0。
- 関連: D22 (frame 内部 read が別 alloca になる)・D17/R8 (alloca 縮退)。D22 は親自身の内部 read、本件は **callee が親フレームを `rbp` 経由で読み書きする**点が違う。
- 確認の範囲: 機械語と IR の突合 (静的) ・§4-C の stack・§4-D の対照 (locale が空文字列になると入れ子手続を通らず先へ進む)。`this+0x70` の実値を動的に読む検証は未実施 (`function_4483f0` が wasm で frame を持たず引数が spill されないため、`probe_t27_oob.mjs` 方式では取れない)。

## 6. file API の到達経路と呼出順

unit 隔離実行 (§4-E) と、新 IR の survey (`survey_trace.mjs`・942 unit 隔離: ok 815 / halt0 8 / oob 70 / closure_outside 46 / unreachable 1 / abort 1 / noproc 1。5 分 12 秒。同一コード・同一 IR で commit 前に採取し、再実行していない) による。逐次 boot の順序で並べる:

| 順 | unit | 内容 | 逐次 boot での扱い |
|---|---|---|---|
| 1 | 18 | `GetLocaleInfoW` 54 回の後、入れ子手続欠陥で Halt0 (§5) | **停止 1** |
| 2 | 57 | `function_8c5eb0` の `unreachable` (T26・#1629。§4-D の対照で到達) | **停止 2** |
| 3 | 96・104・146・154・233・239・266・273 | `RegOpenKeyExW`・`LoadLibraryW`・`RegCreateKeyExW` (file API ではない) | 未到達 |
| 4 | **150**・159・191・281 | `GetModuleFileNameW` 3 回 → `GetFileAttributesW` (最初の file API)。いずれも直後に `oob` | 未到達 |

- survey に `CreateFileW` / `FindFirstFileW` / `ReadFile` は 1 件も出ない (file API は `GetFileAttributesW` の 4 unit のみ)。前記の `guest=""` から、これらの unit が組み立てる path が空になっている。原因は未確認 (unit 18 が Halt0 で終わり module 名などの初期化が抜けた影響かもしれないが、検証していない)。
- よって逐次 boot で ftrace > 0 にするには、停止 1 (§5) と停止 2 (T26) の両方を越える必要がある。

## 7. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 入れ子手続 (`function_4483f0` ほか) の親フレーム共有の修復と D23 の昇格 (§5) | unit 18 を越えられず、逐次 boot の ftrace が 0 のまま | #2444 (SHX-T28) |
| `function_8c5eb0` の `unreachable` (unit 57) の原因切り分けと DEFECTS.md への類型記録 (移管項目) | 停止 2。D19 と別原因の類型が未命名 | #2446 (SHX-T29) |
| unit 150 等の `GetFileAttributesW` が空 path になる原因 | file API の引数が意味を持たない | 上 2 件の解消後に再測定 (子は起票しない) |

## 8. 検証の鮮度

- 測定 commit: `e4be81ff030538ab524e2fd7a6adbc6de901f07c`。そこから HEAD までのコード差分: `git diff e4be81ff HEAD --stat -- tools/m11 tools/shimx ':!tools/m11/REPORT_SHX-T27.md'` の出力は **空** (差分 0。REPORT と `docs/` の文言変更のみが後続)。
- 再現: §2 の手順で IR を作り直し、§4 の各コマンドを実行する。`experiments/t27_nc_swap.py` の stale 側 IR は `work-m11.tar.zst` から `tools/m11/work/boot_final3.ll` だけを別 dir に展開して使う。

---

## 付録 A. 前 2 run の測定 (stale な `work-m11` IR。原因は §1・§4-B)

## A-1. 旧測定 (前 2 run。stale な `work-m11` IR での実測。§1・§4-B で原因が判明したため、結論は §1 が正)

旧版の §1 (結論)・§4 (未解決表)・§5 (鮮度) は本版の §1・§7・§8 に置き換えた (旧文は Git 履歴の `b589d48c`)。以下は旧版の測定表をそのまま残す。

測定 commit `5d167ecd` (再現 HEAD `7738ce46`、`b589d48c` までコード差分 0)。

| 段階 | コマンド | 結果 |
|---|---|---|
| trace variant build | `bash tools/m11/shimx_link/build.sh --trace --soft` | rc=0 / 13.9 s / `signature mismatch=1 undefined symbol=0 duplicate=0` |
| 実 boot (ftrace) | `SHIMX_TRACE_FILE=/ftrace.jsonl node tools/m11/shimx_link/run_trace.mjs $W/m11_sx_trace_soft.cjs --out $W/verify` (`$W` = `tools/m11/work/shimx_link` の絶対パス。`.cjs` は絶対パスで渡す) | rc=0 / 0.42 s / `boot_stage=1` `init_count_var=18` `units_run=17` `icall_ok=24` `icall_miss=1` `dllmain_done=false` `threw="memory access out of bounds"` |
| trace | 同上 (run.json) | `total_calls=97` `distinct_called=28` `dropped=0` |
| ftrace 行数 | `wc -l <tag>.ftrace.jsonl` | **0 行** (0 バイト)。`FS` は export 済み・`ftrace_error` 無し |

- 測定時 load (1 分平均): 0.69 (`uptime`、boot 直前)。
- 既存 `work-m11` の `.cjs` (旧 build) は `FS` 未 export のため `Aborted('FS' was not exported)` で落ちる。これは `build.sh` の現行版で再 build すると解消する。
- 参考: 比較用の旧 HEAD `9f968b27` から測定 commit `5d167ecd` までの `tools/m11`・`tools/shimx` の差分は 2 ファイル (`REPORT_APPENDIX_960.md`・`m11_sdiv_variant.py`) の追加のみ (+64 行)。`9f968b27` は測定対象ではない。

### A-1-1. unit 別の trace calls (run.json)

| unit | calls | distinct | 呼出 (new) |
|---|---|---|---|
| 0 | 5 | 5 | GetCurrentThreadId, TlsAlloc, LocalAlloc, TlsSetValue, TlsGetValue |
| 2 | 21 | 12 | VerSetConditionMask, VerifyVersionInfoW, GetModuleHandleW, GetProcAddress, SetThreadLocale, InitializeCriticalSection, GetVersion, GetSystemInfo, GetCommandLineW, GetStartupInfoW, GetACP |
| 16 | 3 | 2 | VirtualAlloc, LoadStringW |
| 17 | 2 | 2 | GetVersionExW |
| 18 | 66 | 13 | GetModuleFileNameW, WideCharToMultiByte, GetThreadLocale, GetCPInfo, IsValidLocale, GetLogicalProcessorInformation, GetLastError, **GetLocaleInfoW (反復)**, EnumCalendarInfoW |

- 末尾 12 件 (seq 85〜96) は全て unit 18 の `GetLocaleInfoW`。
- file API (CreateFileW / CreateFileA / GetFileAttributesW / FindFirstFileW / FindFirstFileExW / FindNextFileW / ReadFile) は 0 件。

### A-1-2. 再測定 (main `e051402a`・worktree `work/ws-1630`・branch `1630-shx-t27-locale-loop`)

| 段階 | 結果 |
|---|---|
| `build.sh --trace --soft` | rc=0 / 13.5 s / `signature mismatch=1 undefined symbol=0 duplicate=0` |
| 実 boot (`SHIMX_TRACE_FILE=/ftrace.jsonl`) | rc=0 / 0.41 s / `units_run=17` / `dllmain_done=false` / `threw="memory access out of bounds"` / `total_calls=97` / `distinct_called=28` / `dropped=0` |
| ftrace 行数 | 0 行 (0 バイト)。`ftrace_error` 無し |
| unit 18 の末尾 40 件 (`tail`) | 全て `GetLocaleInfoW` |

- ftrace の仕組み: `shimx_set_trace_file` は MEMFS に `fopen("w")` で空ファイルを作り、イベントは file API 呼出時にだけ `shx_ftrace_emit` で書く (`tools/shimx/src/trace.c`)。0 バイトは「file API が 1 件も呼ばれていない」ことを意味し、書き込み失敗ではない (`FS.readFile` は成功)。
- `trace_file` の空振りは計装の問題ではなく、停止までに file API が到達していないことの直接の証拠。

### A-1-3. 駆動関数の静的確認 (`boot0.drc.c`)

- `function_446400` (locale 情報収集) は 1 回の呼出で `function_4133f0` を含む多数の呼出を行う。ループ本体ではない。
- `function_44bb70` は `function_446400` を **1 回だけ** 呼ぶ (`bp-416` の初期化 → `function_44bae0` → `function_446400` → `function_416750` → `function_415c30`)。反復の駆動元ではない。
- `function_455790` は `g365` カウンタで初回だけ本処理に入り、2 回目以降は即 return する。ここも反復の駆動元とは考えにくい。
- 「`GetLocaleInfoW` 66 回反復」は誤読だった (66 は unit 18 の全 shimx 呼出数。`GetLocaleInfoW` は 48 回)。駆動元は §3 のとおり `function_446400` 自身。

## A-2. trap stack の解決 (export 名。stale IR)

`run_trace.mjs` の stack 注釈は `wasm-objdump` が無いため無効だった。代わりに `.cjs.wasm` の export section を直接読んで番号を解決した。

| wasm-function | 関数 | 役割 (IR 上) |
|---|---|---|
| 1352 (最上段・trap) | `function_4133f0` | 呼出元 `function_446400` 等から呼ばれる。役割の詳細は未確定 |
| 4468 | `function_446400` | locale 情報 (LCType 20・27・28…) を集める。`function_446370` 等を呼ぶ |
| 4522 | `function_44bb70` | `function_446400` の呼出元 |
| 4592 | `function_455790` | 上位の呼出元 |
| 11482 | `m11_tr_function_455790` | trace wrapper |
| 1328 | `m11_icall` | icall 経由 |
| 1346 | `function_4120c0` | 初期化 |
| 1347 | `m11_InitLib` | |
| 1350 | `function_41d8f0` | |

- 呼出チェーン (静的): `function_41d8f0` → `function_4120c0` → (icall) `function_455790` → `function_44bb70` → `function_446400` → `function_4133f0` (trap)。
- `function_446370` / `function_4463d0` は `GetLocaleInfoW` を 1 回だけ呼ぶ薄いラッパで、反復ループの本体ではない。`GetLocaleInfoW` の反復は `function_446400` の呼出元側に由来する (静的解析で確定できず)。

