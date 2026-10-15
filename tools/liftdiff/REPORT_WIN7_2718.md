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

## 5. WIN-9 (#2760): S20 の同定・実カタログ供給の実験・応答表

測定 commit: `ba6f438cd` (実行コードの最後の変更。直前の `4776150a6` の応答表の分類誤りを直し、同 commit で再測定)。
その後の差分は §5.9 (コメント・docstring のみ。実行に影響するトークン列は不変)。
再現コマンド (素材: fl-win64・work-liftdiff・work-m11 を展開済み):

- 既定: `cd tools/liftdiff && FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 spike_cfi.py targets/flelift.json`
- 実カタログ: `LD_CATALOG_MO=$RUNNER_TEMP/fl-win64/extracted/block25158_DATA.bin FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 python3 spike_cfi.py targets/flelift.json`
- e2e: `FL_WIN64_DIR=$RUNNER_TEMP/fl-win64 bash tools/liftdiff/liftdiff_e2e.sh --m11-only`

### 5.1 結果 (実測・各 1 run。実行時間は `time` の real)

| 項目 | 既定 | 実カタログ (`LD_CATALOG_MO`) |
|---|---|---|
| hybrid 到達 `units_run` / `first_fail` | 928/942・830 | 928/942・895 |
| CreateFruityInstance の止まり (`rip_rva`) | `0x4e0fab` (rdx=0 の null 読み) | `0x12a25` (`rep movsq`・rcx=0x25・rsi=0) |
| 呼ばれた import 数 | 35 | 33 |
| 戻り候補 (`[rsp+0x28]`、VA) | `0x8e1a36` | `0x417bcd` |
| MessageBoxA の文面 / caption | 呼ばれず | `Runtime error 201 at 0000000000417BCD` / `Error` |
| ExitProcess | 呼ばれず | `0xc9` (201) |
| 実行時間 (real) | 16.302 s | 15.955 s |

実行時間は各 1 run の単発値。load average と並列数は測定時に記録していないため、比較の根拠にしない (§5.7)。

### 5.2 S20 の loader の呼出元 (受入 1 の一部)

loader 自体 (`default.moe`・rva `0x4e0fab`) の同定は `tools/liftdiff/REPORT.md` §2.2 で済んでいる。本節は、その呼出元と magic 検査の位置を追加する。
機械語は fl-win64 の `extracted/block00031_PE.bin` (FLEngine_x64.dll・VA = 0x400000 + rva) を `objdump -d` で確認した (本 fix run)。

- 止まりの関数は rva `0x4e0fa0` (VA `0x8e0fa0`)。機械語は `push rbx; sub rsp,0x20; mov r8d,r8d; add rdx,r8; mov ebx,[rdx]`。引数 rdx=バッファ・r8=オフセットで、`add` の後の `[rdx]` (rva `0x4e0fab`) が `[rdx+r8]` の読みに当たる。`rdx=0`・`r8=0` の null 読みで segv する。
- 呼出元は rva `0x4e1a31` (VA `0x8e1a31`) の `call 0x4e0fa0` (直前は `xor r8,r8`)。戻り VA `0x8e1a36` (`mov %eax,0xac(%rbp)`) は上の戻り候補と一致する。直後の rva `0x4e1a3c` (VA `0x8e1a3c`) で `cmpl $0x950412de,0xac(%rbp)` の gettext `.mo` の magic 検査を行う。
- `[obj+0x40]` は rva `0x4e199f`〜`0x4e19b6` で `call 0x9410` の確保結果を入れる。確保サイズは rva `0x4e1973`〜`0x4e1991` で、ストリーム (`[obj+0xb0]`) の vtable `+0x18` (サイズ取得) の戻り値を使う。
- 既定では `CreateFileW`・`SetFilePointer` が 0 を返し、サイズが 0 になり確保も NULL になる。`ReadFile` は呼ばれず、magic の比較で NULL を読んで segv する。
- 開いている path は UTF-16 PEEK で実測した `\System\Languages\\LC_MESSAGES\default.moe` (`\\` は実値)。CAB-233 の unit 830 (`tools/liftdiff/REPORT.md` §2.2) と同一の経路。
- **訂正**: #2760 の本文は、この止まりを S20 (設定ロード系) と推定していた。実測した止まりは言語カタログ (`default.moe`) の読込みだった。`tools/startup/STARTUP.md` の S20 は `0x13751e0` (cmdline 解析・スプラッシュ・BeforeRunning の設定ロード) の段で、この読込みがその段の子として呼ばれるかは未確認。呼出し連鎖と S12〜S22 の対応表は子 issue に移す。

### 5.3 実カタログ供給の結果 (`LD_CATALOG_MO`)

`rt/ld_core.h` の `LD_CATALOG_MO` 分岐 (環境変数指定時だけ。既定と wasm は従来どおり) で、`GetFileAttributesW`=0x80・`CreateFileW`=仮 handle `0x65000001`・`SetFilePointer` (FILE_END) = 47,405 (`0xb92d`)・`ReadFile` = 47,405 B の copy (戻り 1) を返す。

- magic 検査 (rva `0x4e1a3c`) は通り、`.mo` の読込みまで進む。boot の unit 830 も通過し、first_fail は 895 へ移る (units_run は 928 のまま)。
- その後の範囲検査: `Runtime error 201` の `at` (rva `0x17bcd`) は、rva `0x17bc8` の `call 0x409730` の戻り番地に当たる (機械語で確認)。その分岐は `[rbp+0x60] < 0` で 0x17bc8 に落ちる。`[rbp+0x60]` の値の出所は未同定。→ `MessageBoxA` → `ExitProcess(0xc9)`。stub が戻った後、rva `0x12a25` の `rep movsq` (`mov $0x25,%ecx` の直後・rsi=0 = コピー元 NULL) で segv する。
- 結論: `.mo` の `CreateFileW`・`SetFilePointer`・`ReadFile` を実物の値にすると、S20 の null 読みは消える。次の止まりは、範囲検査の値と NULL のコピー元の同定 (子 issue)。

**旧実験との関係** (`REPORT.md` §2.2 の 3.・`rt/ld_core.h` の旧コメント):

- 旧実験 (block25158 を CreateFileW→仮 handle + ReadFile で供給) は revert 済みで、commit にも応答表の記録にも残っていない。そのため応答の完全な比較はできない。
- 確認できる差分は、本節の応答に `GetFileAttributesW`=0x80 と `SetFilePointer` の size 応答 (47,405) が加わること。その結果 unit 830 は magic 検査まで届き、first_fail は 830 → 895 へ移る (§5.1)。旧記録の応答が無いため、この移動が応答の追加による因果だとは断定しない。
- 旧記録の「magic 検査の後、rva `0x513da9` の VMT 仮想 call で rbp が破壊される」は、本節の応答では**未確認**。`0x513da9` (VA `0x913da9`) の機械語は `call *0x18(%rdi)` で、旧記録の記述と一致する (`objdump` で確認)。ただし本 fix run は spike を実行できない (素材 `tools/m11/work/boot_final3.ll`・work-liftdiff が無い)。確認方法は `LD_STEP_N`・`LD_STEP_OUT` の命令単位 trace (`rt/ld_native.c`) で、結果は §5.7 の未解決に残す。

### 5.4 import 応答表 (受入 4・既定の spike `spike_cfi.json` より)

「既定の応答」は `rt/ld_core.h` の `ld_model_call` に明示の分岐がある import (実装あり) か、既定の 0 を返す stub か。

| import | 回数 | 既定の応答 | 戻り (初回) | 引数 (先頭 3) |
|---|---:|---|---|---|
| timeGetTime | 1 | 実装あり (ld_model_call) | 0x3f8 | 0xc0, 0xede95a, 0xff00000 |
| VirtualAlloc | 2 | 実装あり (ld_model_call) | 0x3e20000 | 0x0, 0x440000, 0x101000 |
| InitializeCriticalSection | 6 | stub (既定 0) | 0x0 | 0x1e3d7c8, 0x0, 0x0 |
| TlsGetValue | 5 | 実装あり (ld_model_call) | 0x1d10000 | 0x1, 0x0, 0x1 |
| GetClassInfoW | 1 | stub (既定 0) | 0x0 | 0x400000, 0x52a7c8, 0x7fffffffb8d8 |
| RegisterClassW | 1 | stub (既定 0) | 0x0 | 0x13be810, 0x555555742940, 0x4 |
| CreateWindowExW | 1 | stub (既定 0) | 0x0 | 0x80, 0x52a7c8, 0x52a8f4 |
| SetWindowLongPtrW | 1 | stub (既定 0) | 0x0 | 0x0, 0xfffffffc, 0x2970f99 |
| CompareStringW | 1 | stub (既定 0) | 0x0 | 0x400, 0x1, 0x1e46820 |
| WideCharToMultiByte | 1 | 実装あり (ld_model_call) | 0xe | 0xfde9, 0x0, 0x1e3d910 |
| GetFileAttributesW | 2 | 実装あり (ld_model_call) | 0xffffffffffffffff | 0x1e336b0, 0x1e31c01, 0x7fffffffa70c |
| GetLastError | 2 | 実装あり (ld_model_call) | 0x0 | 0x500, 0x555555742ac0, 0x70 |
| FindFirstFileW | 2 | stub (既定 0) | 0x0 | 0x1e336b0, 0x7fffffffa450, 0x0 |
| FindClose | 2 | stub (既定 0) | 0x0 | 0x0, 0x555555742b40, 0x0 |
| GetCurrentThreadId | 1 | 実装あり (ld_model_call) | 0x1234 | 0x1e26a90, 0x1e33720, 0x7fffffffa5fc |
| CreateFileW | 1 | stub (既定 0) | 0x0 | 0x1e336b0, 0x80000000, 0x1 |
| SetFilePointer | 4 | stub (既定 0) | 0x0 | 0x0, 0x0, 0x7fffffffa3dc |
| CloseHandle | 1 | 実装あり (ld_model_call) | 0x1 | 0x0, 0x1, 0x0 |

### 5.5 不足 shim・素材 (受入 5)

| 種別 | 内容 | 入力先 |
|---|---|---|
| 素材 (VFS) | `\System\Languages\LC_MESSAGES\default.moe` = fl-win64 素材の `extracted/block25158_DATA.bin` (47,405 B・magic `0x950412de`・正規の gettext `.mo`) | WIN-4・WIN-5 と `tools/startup/assettrace` |
| shim (実験で有効化) | `GetFileAttributesW` (path=`*.moe`)、`CreateFileW`・`SetFilePointer`・`ReadFile` (仮 handle・実バイト) | 本節の `LD_CATALOG_MO` 分岐 |
| stub (既定 0 のまま) | `CreateFileW`・`SetFilePointer` (0 は size 0 で NULL 確保)、`FindFirstFileW` (0)、`CreateWindowExW`・`RegisterClassW`・`GetClassInfoW` (0)、`MessageBoxA`・`ExitProcess` | 次段 (子 issue) |

### 5.6 回帰 (受入 6)

- 既定の spike: 928/942・first_fail 830・segv `0x4e0fab`・import 35 (本節の変更前と同一)。
- `liftdiff_e2e.sh --m11-only` (測定 commit `ba6f438cd`・単発 1 run): `LIFTDIFF_E2E PASS`・real 3m04.7s・exit 0。`CHECK_INITUNITS PASS`・hybrid `units_run=928/942 first_fail=830`。sample:800 は 一致 361 / 不一致 233 / 実行不能 206。
- sample:800 の揺れは本節では評価しない (n=1)。以前の記録にあった「同じ e2e コードの直前 2 回 (360/234/206)」は commit hash と実行条件が本 REPORT に無いため、根拠から外した。e2e の対象 (`ld_core.h` の既定分岐) は変えていない (§5.9)。

### 5.7 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| `.mo` 供給後の範囲検査 (rva `0x17bcd`) の値の出所と、`rep movsq` (rva `0x12a25`) の NULL コピー元の同定。S12〜S22 の対応表 | 窓の生成に届かない | #3556 ([WIN-33]) |
| `CreateWindowExW` の呼出元 VA (trace 無し)、surface の画素統計 (headless host) | #2760 の受入 2・3 未達 | #3557 ([WIN-34]) |
| 本 PR の応答で rva `0x513da9` の rbp 破壊が起きるか (命令単位 trace)。旧記録との整合 | 旧記録の再現可否が未確定。本 fix run では素材不足で未実行 | #2760 (次の review run で `LD_STEP_N`・`LD_STEP_OUT` により確認。子は起票しない) |
| 実行時間・sample:800 の load average と並列数 (測定時に未記録)・sample:800 の揺れ (n=1) | §5.1・§5.6 の所要と揺れを比較に使えない | #2760 (再測定時に記録。子は起票しない) |

### 5.8 KPI

KPI は PR 本文の表を参照 (`docs/WORKFLOW.md` §7)。

### 5.9 fix の範囲 (コード差分の扱い)

測定 commit `ba6f438cd` から本 fix の commit までの差分は、次の 2 件 (コメント・docstring のみ):

- `tools/liftdiff/rt/ld_core.h`: 旧実験の記録コメント (§2.2 の 3. と同じ内容) を、`LD_CATALOG_MO` 分岐 (`ld_cat_on`) と区別して書き直した。
- `tools/liftdiff/spike_cfi.py`: docstring に `LD_CATALOG_MO` 指定時の出力名 (`spike_cfi_cat.json`) を 1 行足した。

確認 (本 fix run・素材 fl-win64 のみで実行可能な範囲): `gcc -E -P rt/ld_native.c` の前処理結果が変更前後で一致 (コメントを除いた結果)。`spike_cfi.py` は docstring 以外の AST が変更前後で一致。実行結果に影響する部分は変わらないため、§5.1・§5.6 の測定値は測定 commit のまま扱い、再測定はしていない。素材 (work-m11・work-liftdiff) が揃う次の review run で同じ spike を再実行して確認する (§5.7)。

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
- 既定の応答を変えるため、本 PR では直さない → 子 issue [LD-170] (boot 928/942 と sample:800 への影響を測る)。
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
| stk 位置 (entry+28 ≠ 第5引数 entry+40) | MultiByteToWideChar/WideCharToMultiByte の a4/a5 が誤り得る | 子 issue [LD-170] |
| 呼出元 rva 0x12a8c3 の関数名 | 未同定 (推定: Classes.AllocateHWnd) | 追跡のみ (PR 本文の未解決表に記載) |
