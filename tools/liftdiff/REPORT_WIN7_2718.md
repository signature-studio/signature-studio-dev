# REPORT — WIN-7 参照実行 spike (native): 実機械語の CreateFruityInstance (#2718)

親: [`REPORT.md`](REPORT.md)。手順の正本は `spike_cfi.py` (本 PR)。

測定 commit: `38ae268d` (コード変更の最後の commit)。再測定を省く根拠 (`docs/WORKFLOW.md` §6): `git diff --name-status 38ae268d HEAD -- tools/liftdiff` の出力は `A tools/liftdiff/REPORT_WIN7_2718.md` の 1 件だけ (コード差分 0)。
再現コマンド: `cd tools/liftdiff && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 spike_cfi.py targets/flelift.json`
素材: fl-win64・work-liftdiff・work-m11 (`tools/liftdiff/work/`・`tools/m11/work/` に展開)・toolchain-emsdk/retdec (本 spike は不使用)。
実行環境: GitHub Actions runner (load average 0.3 台)。

## 1. 結果 (実測・単一 run)

| 項目 | 値 |
|---|---|
| hybrid の到達 (boot) | `units_run=928/942`・`first_fail=830`・entry_point は InitCount=246 で segv (REPORT_LD26 §1 と一致) |
| native の `CreateFruityInstance` 呼出し | 有り。`CreateFruityInstance(0xC0, 0xEDE95A, host, &iface)` (VA `0x1375990`) |
| case の status | `segv` (rip_rva `0x4e0fab`) |
| 呼ばれた import 数 | 35 (`calls_over` 0) |
| `RegisterClassW` / `CreateWindowExW` の呼出し | 有り (FL の実機械語から。`RegisterClassW` は GetClassInfoW の後・`CreateWindowExW` は直後) |
| `iface` (戻り) | 0 (未設定。関数は戻らず segv) |
| 実行時間 | 12.3 秒 (`spike_cfi.py` 全体・boot 込み) |
| 再現 | 測定 commit `38ae268d` で 2 回目も同一 (status・rip・calls 列が一致) |

### 1.1 呼出し import の列 (順序どおり・応答は stub の既定 `ld_model_call`)

`timeGetTime VirtualAlloc InitializeCriticalSection InitializeCriticalSection VirtualAlloc InitializeCriticalSection ×4 TlsGetValue ×5 GetClassInfoW RegisterClassW CreateWindowExW SetWindowLongPtrW CompareStringW WideCharToMultiByte GetFileAttributesW GetLastError FindFirstFileW FindClose GetCurrentThreadId GetFileAttributesW GetLastError FindFirstFileW FindClose CreateFileW SetFilePointer ×4 CloseHandle`

対応する起動段 (`tools/startup/STARTUP.md` §2) の目安: `timeGetTime` = S12、`GetFileAttributesW`/`FindFirstFileW` = S05・S15 (ユーザデータ dir 解決)、`RegisterClassW("TApplication")` + `CreateWindowExW` = S19 (STARTUP.md §2 の S19 行: TApplication の不可視ウィンドウ)。**S19 まで到達した** (実測は `RegisterClassW`・`CreateWindowExW` の呼出し)。`CreateFileW`・`SetFilePointer`・`CloseHandle` を S20 の設定ロードに対応づけるのは**推定**: STARTUP.md §5 は設定を TRegistry (HKCU) 経由と書くため、ファイル読込みは設定以外の経路 (テーマ・dir 等) の可能性がある。呼出元の段は未同定 (§1.2)。

### 1.2 止まった地点

- 関数: rva `0x4e0fa0` (push rbx; sub rsp,0x20; mov r8d,r8d; add rdx,r8; **mov ebx,[rdx]**)。`rdx=0`・`r8=0` で null ポインタを読んで segv (`rip_rva=0x4e0fab`)。
- 戻りアドレス候補 (`[rsp+0x28]`): `0x8e1a36` (VA)。呼出元の段は未同定 (推定: S20 の設定ロード系)。
- 原因は未調査。null 読みは設定ファイルの読込み結果 (`SetFilePointer`・`CloseHandle` の後) が stub 応答 (0) のまま使われた可能性が高い (推定。stub の戻り値を実物の値に変えて確かめる必要がある)。

## 2. 実装 (本 PR)

- `rt/ld_native.c`: `POKE <i:rva|a:off|h:off> <hex>` を追加 (既存の命令は不変)。
- `ldlib/boot.py`: `build_state(..., post=None)` を追加。`post(r, sess)` は unit 初期化の後・状態採取の前に呼ばれ、戻り値は `detail['post']`。既定 None なので `bootstate` の挙動は不変 (e2e 未実行。`bootstate --mode hybrid` を §1 で再現 = 928/942 一致)。
- `spike_cfi.py`: 新規。(1) TEB の TLS 配列ポインタから heap の絶対アドレスを求める (`teb[0x58/8] = ld_heap + 0x1000`)。(2) heap 末尾 1 MiB (`heap_size - 0x100000`) に THostInstance (0x38 B: `+8=1`・`+0x18="FL Studio"`・`+0x30=cmdline 空バッファ`) を POKE。(3) `CreateFruityInstance` を export 表から引き、CASE で 1 回呼ぶ。(4) 戻り・iface・status・import 列を `work/flelift/spike_cfi.json` に書く。
- THostInstance の `+0` (vtable) は 0 のまま。エンジンが host の vtable を呼ぶ段に入れば、そこが次の止まり地点になる (未確認)。

## 3. 未解決 (起票先付き)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| S20 の null 読み (rva `0x4e0fab` (VA `0x8e0fab`)・呼出元の戻り候補 VA `0x8e1a36`) の原因。stub 応答 (CreateFileW・SetFilePointer 等) を実物の値に変える | S20 以降に進めない (S20 は推定)。窓の画素は未得 | #2760 |
| 画素統計 (w×h・非背景画素・色数・sha256) と GUI の headless host への接続 | 受入条件 4 未達 (本 PR では動かしていない) | #2760 |
| import 解決の応答表 (実物 shim / 仮応答 / stub の区別) と不足 shim・素材の一覧 | 受入条件 5・6 未達 | #2760 |
| `CreateWindowExW` の呼出元 VA (trace 無し) | 受入条件 3 の「呼出元 VA」が未達 | #2760 |
| liftdiff e2e (`liftdiff_e2e.sh`) の回帰確認 | 受入条件 8 の残り。本 PR では未実行 (素材 work-m11・work-liftdiff が本 run に無い) | #2760 |

## 4. KPI (`docs/WORKFLOW.md` §7・起動に関わる PR)

| KPI | 前 | 後 |
|---|---|---|
| native での `CreateFruityInstance` 呼出し | 無し | 有り (segv で戻らず) |
| 最終到達 (起動段) | hybrid は S09 の unit 初期化まで (928/942) | S19 相当 (TApplication 窓の作成) の後、未同定の段で segv (S20 は推定) |
| `RegisterClassW`/`CreateWindowExW` の呼出し (FL の実機械語) | 0 | 各 1 |
| FLEngine 起動の dispatch 数・通過 unit 数 | 928/942 (first_fail 830) | 変化なし (boot の段は不変。post は unit 初期化の後に実行) |
| surface の画素 | 無し | **動かしていない** (画素は未取得) |

## 6. WIN-34 (#3557): 窓 import の呼出元 VA・引数の trace (部分達成。画素統計は子 issue へ)

測定 commit: `913063ebe` (コード変更の最後の commit)。再測定を省く根拠 (`docs/WORKFLOW.md` §6): `git diff 913063ebe HEAD -- tools/liftdiff/rt tools/liftdiff/spike_cfi.py tools/liftdiff/ldlib` の出力は空 (この節の commit は REPORT_WIN7_2718.md のみ)。
再現: `cd tools/liftdiff && FL_WIN64_DIR=<fl-win64 展開先> python3 spike_cfi.py targets/flelift.json` (`SPIKE_WINTRACE=0` で窓の記録を切る)。
素材: fl-win64・toolchain-emsdk・work-m11・work-liftdiff。実行環境: GitHub Actions runner (4 CPU)、`uptime` の load average 0.33 (e2e 直前)。

### 6.1 窓 import の呼出元と引数 (実測・spike 1 回)

| import | 呼出元 VA (rva) | 引数 (実測) | 戻り |
|---|---|---|---|
| GetClassInfoW | 0x52a825 (0x12a825) | class="TPUtilWindow" | 0 |
| RegisterClassW | 0x52a85e (0x12a85e) | class="TPUtilWindow"・style=0x0・wndproc rva=0x24920・hInstance=0x400000 | 0 |
| CreateWindowExW | 0x52a8c3 (0x12a8c3) | ex=0x80・class="TPUtilWindow"・wname=""・style=0x80000000・x=y=w=h=0・parent=0・menu=0・hInstance=0x400000・lpParam=0 | 0 |

- 既定の応答は変えていない (記録の追加のみ)。窓の戻り値は従来どおり 0 で、CreateFruityInstance は従来どおり rva `0x4e0fab` で segv する。
- **訂正**: §1.1 は S19 の窓を `TApplication` と推定していたが、実測の class は `TPUtilWindow` (隠し 0×0 の WS_POPUP 窓)。Delphi の `Classes.AllocateHWnd` の引数並びと一致 (推定)。`TApplication` の窓はこの時点では作られていない。
- 呼出元 (rva 0x12a8c3 付近) の関数名は未同定。

### 6.2 stk 位置の不一致 (既存の挙動。本 PR では未修正)

- `ld_ms_call.S` の `ld_stub_common` は `leaq 212(%rsp)` で stk を渡す。実測 `stk_minus_entry=28` (entry rsp からの差)。MS x64 の第5引数は entry+0x28 (=40) にある。
- 影響: `MultiByteToWideChar`・`WideCharToMultiByte` の a4/a5 (`stk[0]`・`stk[1]`) が誤る。実測の spike で `WideCharToMultiByte` の a4 は `0x55844ec000000000` (ホスト値)。
- 既定の応答を変えるため、本 PR では直さない → 子 issue [LD-168] (boot 928/942 と sample:800 への影響を測る)。
- 本 PR の trace は entry+0x28 から直接読む (`wt_rec`)。その値は CreateWindowExW の第5〜12引数として整合 (x=y=w=h=0・hInstance=イメージ基底)。

### 6.3 既定の挙動の回帰 (spike: FLEngine 起動の KPI)

| 項目 | 変更前 (基準 `42c6bcfdd`。`tools/liftdiff` は origin/main と差分 0) | 変更後 (`913063ebe`) |
|---|---|---|
| units_run / first_fail | 928/942・830 | 928/942・830 (2 回とも同じ) |
| CreateFruityInstance | segv rip_rva `0x4e0fab` | 同じ |
| 呼出し import 数 | 35 | 35 |
| 記録オフ (`SPIKE_WINTRACE=0`) 2 回の差 | — | 完全一致 (呼出し 35 件の全項目) |
| 基準 vs 記録オフ | — | 戻り値・関数名は 35 件全件一致。引数は 20 件のみ差 (使われない未初期化レジスタの残り値 = ホストの `0x5555…`・stack の `0x7fff…`) |

ネガティブコントロール: `SPIKE_WINTRACE=0` で窓の記録行 0 行 (`spike_wintrace.txt`)、既定で 9 行 (cfi 3 件 + 他 case 6 件)。

### 6.4 liftdiff e2e の回帰 (`bash liftdiff_e2e.sh --m11-only`・受入 3)

| 実行 | commit | 一致 / 不一致 / 実行不能 | 所要 | 結果 |
|---|---|---|---|---|
| 基準 | `01f1b7e51` (origin/main) | 360 / 234 / 206 | 3 分 04 秒 | LIFTDIFF_E2E PASS (rc 0) |
| 新 1 | `913063ebe` | 361 / 233 / 206 | 3 分 05 秒 | PASS (rc 0) |
| 新 2 | `913063ebe` | 360 / 234 / 206 | 3 分 03 秒 | PASS (rc 0) |

関数単位 (800 件) の突合 (case outcome の変化・verdict の変化。再現: `python3 tests/batch_flips.py <基準の batch.jsonl> <新の batch.jsonl>`):

| 比較 | case outcome 変化の関数数 | verdict 変化 |
|---|---|---|
| 基準 vs 新 1 | 7 | 1 |
| 基準 vs 新 2 | 4 | 0 |
| 新 1 vs 新 2 (同じコード) | 6 | 1 |

同じコード同士でも同程度に揺れる (hang・timeout の分類、ホストのアドレスを含む比較)。件数の差は実行ごとの揺れの範囲内で、既定の挙動の変化とは判定しない。

### 6.5 KPI (起動・GUI に関わる。PR 本文に転記)

| KPI | 前 | 後 |
|---|---|---|
| 最初のウィンドウ (surface の画素) | 無し | **無し・動かしていない**。作られるのは隠し窓 `TPUtilWindow` (0×0)。可視窓 (TApplication) は rva 0x4e0fab の segv より後の段 |
| CreateWindowExW の呼出元 | 未記録 | VA `0x52a8c3` (rva `0x12a8c3`)、引数を記録 |
| FLEngine 起動の dispatch 数・通過 unit 数 | 928/942 (first_fail 830) | 同じ (928/942・830) |

### 6.6 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| headless host への接続と surface 画素統計 (受入 2)。PNG は作らない (受け渡し: PM 判断待ち) | 可視窓の画素は未取得。前提は `.mo` 読込み後の止まりの解消 (#3556) | 子 issue [WIN-35] (依存: #3556) |
| stk 位置 (entry+28 ≠ 第5引数 entry+40) | MultiByteToWideChar/WideCharToMultiByte の a4/a5 が誤り得る | 子 issue [LD-168] |
| 呼出元 rva 0x12a8c3 の関数名 | 未同定 (推定: Classes.AllocateHWnd) | 追跡のみ (PR 本文の未解決表に記載) |
