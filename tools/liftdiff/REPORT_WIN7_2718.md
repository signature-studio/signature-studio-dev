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
