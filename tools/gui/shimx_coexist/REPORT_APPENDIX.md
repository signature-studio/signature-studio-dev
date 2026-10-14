# REPORT 付録 — フォルダ選択 (SHX-T22 #1179)

本体 `REPORT.md` の §6 から参照する。親 #957 (SHX-T14) の受入条件「フォルダ選択 (BIF 系) の扱いを決め、未対応なら明示」の調査記録。

検証起点: `origin/main` `481eb2d7` (worktree `ws-1179`)。コード変更なし。e2e は未実行 (変更が無いため)。

## 1. 実施内容と結果

| 項目 | 結果 |
|---|---|
| 素材 | `fl-win64` を `$RUNNER_TEMP/fl-win64` に展開 (`extracted/` 25,166 ファイル)。`toolchain-retdec` / `toolchain-emsdk` は実在。`work-m11` は取得されず (未指定)。 |
| FL 本体の静的 import | `block00005_PE.bin` (FL 本体 EXE) が `SHELL32.dll!SHBrowseForFolderA` と `ole32.dll!CoCreateInstance` を import。 |
| 同梱 DLL の静的 import | `block00020_PE.bin` (InstallOptions.dll)・`block21296` (`editor_x64.dll`)・`block23609` (`engineV2_x64.dll`)・`block23610` (`engine_x64.dll`)・`block24344`・`block25162` が `SHBrowseForFolderW` を import (`SHGetPathFromIDListW` と同時)。 |
| FileOpenDialog / FileSaveDialog の CLSID | バイト列が PE ブロックに現れる (FileOpenDialog 82 ブロック・FileSaveDialog 81 ブロック)。`IID_IFileDialog` は 148 ブロック。 |
| shimx の登録状況 | `SHBrowseForFolderA/W` は `tools/shimx/src/proctable.c` に無い。`GetProcAddress` の未登録は `SetLastError(ERROR_PROC_NOT_FOUND)` で NULL を返す (strict 時のみ abort)。 |
| `IFileDialog` (COM) | `CoCreateInstance` は `ole.c` で `REGDB_E_CLASSNOTREG` を返す。FileOpenDialog の CLSID は実装されていない。 |

## 2. 判定

- **FL は `SHBrowseForFolderA` / `W` を静的 import している。** issue 本文と REPORT G4 の「呼ばれると黙って失敗する」は、shimx 側の状態として正しい。
- **実際に呼ばれるかは未確定。** 静的 import は解決されているだけで、呼出は実行 trace でしか確定できない。`work-m11` 無し・trace 用 `FS` export 版の再 build が必要 (`tools/m11/REPORT_N1050.md` §5) のため、本 run では確認できなかった。
- **IFileDialog (COM 経路) は実呼出の有無を含めて未確認。** `CoCreateInstance` は shimx で `REGDB_E_CLASSNOTREG` になるため、呼ばれれば黙って失敗する。

## 3. 未実施と理由

- **fail-fast 実装の見送り**: `SHBrowseForFolderA/W` を未登録のまま strict abort にすると、呼ばれない import でも起動時に落ちる可能性がある。shimx の import 解決タイミングをコードから確定できなかったため、根拠なしに変えない。
  - **覆した (2026-10-14、§7 で実施)**: 上の見送りは、次の事実で覆した。`tools/shimx/src/` で `GetProcAddress(` を呼ぶ箇所は無い (定義 `module.c:315`・宣言 `shimx.h:849`・エラー文字列 `module.c:355` のみ。コメント 1 件 `shord.c:6` の `GetProcAddress(序数)` を除く)。shimx は PE の import を `GetProcAddress` 経由で解決しない。静的 import の結線は m11 の IR 宣言と `gen_link.py` の stub 生成が担う。よって §7 の分岐は**動的な名前解決 (`GetProcAddress("SHBrowseForFolderA/W")`) にしか効かず、静的 import の起動時には効かない**。
- **web 側の directory picker 実装の見送り**: 呼出の有無が未確定で、仕様 (picker の UI・戻り値のステージング先) を決められない。
- **次に必要な素材**: `work-m11` (`oc_artifacts` に追加)。trace 版の再 build が必要な場合は `tools/m11/REPORT_N1050.md` §5 の手順に従う。

## 4. 残作業 (起票先)

注 (2026-10-14): #1179 は本 PR で閉じる。以下 1〜3 の残りは §7-3 の未解決表へ移した (受入 1 は既存 #942、IFileDialog は #2916、gui 検査は #2917)。

1. FL の `SHBrowseForFolderA/W` と `IFileDialog` の実呼出を `SHIMX_TRACE` で確認し、結果を本付録に追記する (§7-3 へ移管)。
2. 呼出ありと確定した場合: Web の対応 (File System Access directory picker) を実装し、node + mock 検査を `tools/gui/test` に追加する (§7-3 へ移管)。
3. 呼出なしと確定した場合: 未対応を fail-fast で明示する (`shimx` の登録と strict abort) し、`IMPORTS.md` を再生成する (§7-3 へ移管)。

## 5. 再測定 (work-m11 展開・trace variant 再 build、run 2026-10-13)

検証起点: `origin/main` `d040c7f8` (worktree `ws-1179`)。コード差分 0 (`tools/m11` / `tools/shimx` は読取のみ)。生成物は `tools/m11/work/` と `work/` (gitignore 対象)。

| 項目 | 結果 |
|---|---|
| 素材 | `work-m11.tar.zst` を worktree ルートへ `tar --zstd -xf` で展開 (2.2 s)。`boot_final3.ll` を含む。 |
| trace variant 再 build | `bash tools/m11/shimx_link/build.sh --trace --soft` rc=0 / 12.1 s / `signature mismatch=1 undefined symbol=0 duplicate=0`。`FS` を export した `.cjs` を生成。 |
| 保存済み `.cjs` での ftrace 取得 | rc=1 `Aborted('FS' was not exported)`。保存物は `FS` 未 export の旧版。 |
| 再 build 版の実 boot (ftrace) | `SHIMX_TRACE_FILE=/tmp/ftrace.jsonl node tools/m11/shimx_link/run_trace.mjs ...` rc=0。`boot_stage=1` `units_run=17` `dllmain_done=false` `threw="memory access out of bounds"` `icall_ok=24` `icall_miss=1`。trace `total_calls=97` `distinct_called=28` `dropped=0`。`m11_sx_trace_soft.ftrace.jsonl` は **0 行**。 |
| 注意 (手順) | `SHIMX_TRACE_FILE` は MEMFS 上のパスを指定する (例 `/tmp/ftrace.jsonl`)。ホストパス (`$PWD/...`) を渡すと `fopen` が失敗し、0 行のまま `ftrace_error: No such file or directory` になる。 |
| IR の宣言 (`boot_final3.ll`) | `SHBrowseForFolderA/W` の宣言 **0**。`SHGetPathFromIDList` / `SHGetSpecialFolderPath` / `SHILCreateFromPath` / `SHCreateItemFromParsingName` / `GetOpenFileNameW` も **0**。`CoCreateInstance` は宣言 1 件・呼出 2 件 (`function_4690c0` 経由。呼出元は `function_c53c60` と `m11_tr_function_4690c0`)。 |
| trace で実際に呼ばれた API (run.json) | 26 種。GetCommandLineW・GetLocaleInfoW・GetProcAddress・LoadStringW・GetModuleFileNameW 等。file API と SHBrowseForFolder / IFileDialog 系は 0。 |

### 5-1. 判定

- **実 boot ではフォルダ選択は呼ばれていない**。ただし、呼ばれていないと言えるのは unit 17 で `memory access out of bounds` により止まるまでの範囲に限る。
- 止まった位置より後の UI 経路 (設定画面など) で呼ばれるかは、この実行では分からない。`REPORT_N1050.md` §4 のとおり、unit 17〜18 付近の trap (`function_8c5eb0` が D19 と同一関数かは未確認) が先に解消されない限り、そこへ到達しない。
- IR に `SHBrowseForFolder*` の宣言が無いことは、FL の PE が静的 import しているという §1 の事実と食い違う。`boot_final3.ll` は lift 対象の範囲に限られるため、宣言が無いことを「呼ばれない」の根拠にはしない。
- 結論: 受入条件 1 (実呼出の確認) は**未達**。方針決定 (受入条件 2) と gui mock 検査 (受入条件 3) は、この結論に依存するため未着手。

### 5-2. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| boot が unit 17〜18 付近で `memory access out of bounds` により停止する問題の解消 | 停止より後の UI 経路 (フォルダ選択の呼出位置) に到達できず、呼出有無が確定しない | #942 (既存・open、boot の `threw` の切り分け。#1050 は 2026-10-14 に CLOSED のため付け替え) |
| `SHBrowseForFolder*` / `GetOpenFileNameW` 等の IR 宣言が無いことの原因 (lift の import 解決範囲) | IR 上の宣言だけでは呼出を判定できない | 原因は未特定。§6 で FL 本体 EXE の呼出は closure 外と判明。残りは #942 へのコメントに併記 (trace 判定の前提として) |

## 6. 静的 call 箇所の再確認 (run 2026-10-14、コード差分 0)

検証起点: `origin/main` `3d21715b` (worktree `ws-1179`)。素材 `fl-win64` を `$RUNNER_TEMP/fl1179` に展開 (25,166 ファイル)。PE の IAT と `.text` の `call` / `jmp` を Python で直接走査した (IR を使わない独立確認)。

| 対象 PE | import 解決 | 静的 call 箇所 |
|---|---|---|
| `block00005_PE.bin` (FL 本体 EXE, PE32) | `SHBrowseForFolderA` = IAT `0x407154`、`CoCreateInstance` = IAT `0x407284` | `call [0x407154]` が `0x40432a` (SHBrowseForFolderA)、`call [0x407284]` が `0x402073` (CoCreateInstance)。いずれも 32bit 絶対 `FF 15 disp32` |
| `block00031_PE.bin` (FLEngine_x64.dll, PE32+) | `SHBrowseForFolder*` は**無し**。`GetOpenFileNameW` / `GetSaveFileNameW` / `CoCreateInstance` / `ShellExecute*` / `SHGetPathFromIDListW` 等は有り | RIP 相対 `FF 25` (jmp thunk) のうち、3 API (`CoCreateInstance` / `GetOpenFileNameW` / `GetSaveFileNameW`) を指すものは **3 箇所** (`0x4690c0` CoCreateInstance、`0x5937e0` GetOpenFileNameW、`0x5937f0` GetSaveFileNameW)。`SHBrowseForFolder*` を指す thunk は 0 箇所 |

走査条件 (`block00031_PE.bin`): `.text` (VA `0x1000`・raw サイズ `min(VirtualSize, SizeOfRawData)`) を先頭から 1 バイトずつ走査し、`FF 25 disp32` の 6 バイトを RIP 相対 (`VA + 6 + disp`) で解決して IAT (import directory) と照合。`FF 25` の総数は 1031 件、うち飛び先が IAT に解決できたものは 832 件 (IAT を指す thunk の総数は 832 件。前版の「9」は誤りで、3 API に限定した数は 3 件)。

判定:
- **フォルダ選択 (`SHBrowseForFolder*`) の静的 call は FL 本体 EXE の `0x40432a` 1 箇所**。その関数は IR の定義範囲 (`function_` は `0x406e60` 以降のみ) より前にあり、**lift closure の外**。IR に宣言が無いのはこのため。
- FLEngine 側の IR に `GetOpenFileNameW` 等の宣言が無いのは、`jmp` thunk 経由の呼出が lift で解決されていないことを示す (`REPORT_N1050.md` / `REPORT.md` §1 の間接 call 脱落と同根)。
- 呼出の**実行時の有無**は依然として未確定。closure 外の関数で、unit 17 の trap (#1050) より後に到達するため、実 boot の trace では判定できない。
- 受入条件 1 は**未達のまま**。方針決定 (受入条件 2) と gui mock 検査 (受入条件 3) も未着手。

## 7. 明示 fail-fast の追加と再測定 (run 2026-10-14、SHX-T22)

測定 commit: `bc6b8a32` (コードを変えた最後の commit。基点 `26f90ada`)。素材 `work-m11` を展開 (snapshot IR)。`bash tools/m11/shimx_link/build.sh --trace --soft` は `signature mismatch=1` (#1628 残件) で rc=0。

**適用範囲 (差し戻し対応 2026-10-14、B2 (b))**: 本節の数値は `work-m11` (snapshot IR) 上の**相対比較**に限る。`docs/WORKFLOW.md` §11 は `work-m11` を「survey の基準には使わない」と定めるため、IR の正 (`bash tools/m11/m11_e2e.sh --full` の出力) での基点と head の survey は本 PR では取り直していない。取り直しは #942 へ移した (§7-3)。よって 7-1 の「init unit の呼出 0 件」は受入条件 1 の根拠にしない。
- 基点 `26f90ada` 以降、main (`665a704d`。差し戻し時の main は `b2b052ce`) では `tools/m11/ldfix`・`tools/m11/trap_triage` 等が変わっている (対象 dir で 13 files)。merge 後の挙動が本節の数値と一致する保証は無い。

所要の注 (m3): 基点・測定の所要 (2 分 43 秒) は測定時の load average・並列数を採取していないため、比較の根拠にならない。差し戻し後のレビュー run (head `38f66a44`) で同じ survey は 5 分 23 秒 (load average 未記録) で、差の原因は未確定。WORKFLOW §5 の形 (所要 + load average + 並列数) の記録は次回の測定から行う。

| 項目 | 基点 `26f90ada` | 測定 `bc6b8a32` |
|---|---|---|
| 逐次 boot (`run_trace.mjs`) | `units_run=17` `threw="memory access out of bounds"` `total_calls=97` | 同左 |
| unit 隔離 survey (942 unit、`survey_trace.mjs`) | ok 789・oob 95・closure_outside 47・halt0 9・clobber 1・noproc 1・`api_units` 69・abort 0 (2 分 43 秒。load average・並列数は未記録) | 同左 (abort 0。所要・load average の記録なし) |
| survey の `GetProcAddress miss` (`SHIMX_TRACE=1`) | 名前付きの miss は `dwmapi`・`user32`・`comctl32` 等。`SHBrowseForFolder` は 0 件。`shell32.dll!` の miss は 1 件 (unit 137・名前は空で同定できず) | 同左 |
| `SHBrowseForFolderW/A`・`GetOpenFileNameW`・`GetSaveFileNameW`・`CoCreateInstance` の呼出 (survey) | 0 件 (abort 以外の unit は trap 前の呼出を計数) | 同左 |
| IR (`boot_final3.ll`) の宣言 | `SHBrowseForFolder*`・`GetOpenFileNameW` 0 件。`CoCreateInstance` 宣言 1・呼出 2 | 同じ IR のため同左 |

### 7-1. 判定

- 受入条件 1 (実呼出の確認): **未達**。逐次 boot は unit 17 で止まる (`dllmain_done=false`)。UI 操作 (メッセージ処理後の呼出) は、この測定では観測していない。snapshot 上の unit 隔離 survey の観測 (フォルダ選択・ファイル選択・`CoCreateInstance` の呼出 0 件) は相対比較の参考に留め、受入 1 の根拠にしない (適用範囲の節を参照)。
- 受入条件 2 (未対応の明示): **部分**。`GetProcAddress("SHBrowseForFolderA/W")` の未登録を、`DWriteCreateFactory` と同じ `shim_unimplemented` で名前を出して fail-fast にした (`tools/shimx/src/module.c`、`test.sh` の `shbrowse`)。IFileDialog (`CoCreateInstance` の FileOpenDialog / FileSaveDialog) は**未対応のまま** (`REGDB_E_CLASSNOTREG` で黙って失敗する)。子 issue へ移した (7-3)。
- 受入条件 3 (gui の node + mock 検査): **未達** (未着手)。子 issue へ移した (7-3)。
- 効く範囲 (B3): この fail-fast は `GetProcAddress` の動的名前解決にしか効かない (§3 の「覆した」節の根拠)。測定 build は `--trace --soft` で、IR に `SHBrowseForFolder*` の宣言は無い (§5)。`--soft` は GUI/audio 未提供 API を 0 返却にする (`build.sh` 6 行目)。よって測定した経路では、この fail-fast は発火していない。
- 挙動変化 (m2): 非 strict の既定モードでも、動的 `GetProcAddress("SHBrowseForFolderA/W")` は従来の NULL 返却から、`shim_unimplemented` (`teb.c:208`、無条件 `abort()`) による全体 abort に変わる。`DWriteCreateFactory` と同じ方針で、「黙って失敗」から「アプリ停止」への変化を伴う。

### 7-2. 副作用の実測 (原因未特定)

同じ `GetProcAddress` に、次の変種を入れて survey を取った (すべて `build.sh --trace --soft` 後に 1 回ずつ。`ok`・`api_units` の順に列挙)。

| 変種 | survey 結果 |
|---|---|
| 長いメッセージ `SHBrowseForFolder (フォルダ選択は Web 未対応…)` の `shim_unimplemented` | ok 784・**abort 1** (unit 102: `unresolved function call: function_535c2e`)・`api_units` 49。survey は 1 秒で終わる (基点は 2 分 43 秒) |
| 同じ分岐を `noinline` の補助関数へ移動 | 上と同じ (ok 784・abort 1) |
| 無効分岐と新しい関数 1 個だけ (文字列なし) | 基点と一致 (ok 789・api 69) |
| データだけ追加 (52 B の文字列配列) | 基点と一致 |
| **短いメッセージ `SHBrowseForFolder`** (採用) | 基点と一致 (ok 789・api 69・abort 0) |

- unit 102 の別実行 (前 unit を走らせた後に unit 102 だけ呼ぶ probe。noinline 版で実施) でも、変更版は VirtualAlloc 125 MB を繰り返した後に `function_535c2e` で abort する。`SHBrowseForFolder` の fail-fast は呼ばれていない。
- 推定 (未検証): メッセージの長さやコードの配置で、m11 の lift 済みコードが参照する未初期化の領域やアドレスが変わる。この測定では原因を特定していない。以後、shimx の変更のたびに survey を取り直すこと。

既知類型との関係 (WORKFLOW §4-3): **該当なし**。`docs/DEFECTS.md` の D1a〜D23・`tools/icall/REPORT.md` §4 の D1〜D13 のどれにも一致しない (abort の文言 `unresolved function call` は既存の症状名で、類型への紐付けはできない)。新類型の疑いは残るため、WORKFLOW §5 の行案を次に置く (DEFECTS.md の直接編集は PM 判断)。

| 項目 | 行案 (未確定を含む) |
|---|---|
| 症状 | shimx の `shim_unimplemented` 文字列の長さを変えると、同一 IR の survey で unit 102 が `unresolved function call: function_535c2e` で abort する (ok 784・abort 1) |
| 根本原因 | **未特定**。推定 (未検証): 変更で wasm の静的データ・heap の配置が変わり、lift 済みコードの参照先が変わる |
| 観測 | 7-2 の 5 変種 (同一 IR・同一 build 手順)。短いメッセージでは基点と一致 |
| 検出信号 | shimx 変更ごとの survey で `ok`・`abort` の件数が基点と違う |
| 修復 | 未定。当面は shimx の変更ごとに survey を取り直す (本節の運用)。原因の特定は下表の起票先 |

### 7-3. 未実施と起票先 (WORKFLOW §5)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| 受入 1 (UI 経路の実呼出の確認) と FLEngine の起動 KPI (dispatch 数・通過 unit 数) の再測定。逐次 boot は snapshot IR で unit 17 `memory access out of bounds` により停止 (`dllmain_done=false`) | フォルダ選択の呼出有無が確定しない。KPI は未測定 (survey の `ok` 数が基点と一致するのみ) | 既存 #942 へのコメント (boot の OOB 停止の切り分けに、本節の停止位置・件数を追記。停止の解消後に確認する)。#1050 は CLOSED のため付け替え。#2444 (unit 18・新 IR・入れ子手続) と #2446 (unit 57) は停止位置と IR が異なるため、同一原因とは判定していない |
| IR 宣言 0 件の原因 (§5-2・§6) | IR 上の宣言だけでは呼出を判定できない | 既存 #942 へのコメントに併記 (trace 判定の前提) |
| IFileDialog (`CoCreateInstance`) の明示 fail-fast (受入 2 の残り) | IFileDialog 経路は黙って失敗する | 新規子 #2916 (SHX-T33、`親: #1179`) |
| gui の node + mock 検査 (受入 3) | 検査が無い | 新規子 #2917 (SHX-T34、`親: #1179`) |
| IR の正 (`m11_e2e.sh --full`) での基点・head の survey 取り直し (適用範囲の節) | 本節の数値は snapshot 上の相対比較に限る | 既存 #942 へのコメント (#2877 は 2026-10-14 に CLOSED のため付け替え。#942 は本文に survey base/fix の再測定を含むが、IR 正 (`m11_e2e.sh --full`) の指定は無いためコメントで依頼) |
| 文字列長で survey の結果が変わる原因 (7-2 の行案) | shimx 変更ごとに survey の再測定が要る | 既存 #942 へのコメント (survey の検出力に関わるため同じ issue へ。#2877 は CLOSED。再測定の受入に 7-2 の 5 変種のうち長いメッセージの版を加える。原因の特定は未着手) |

## 8. IFileDialog (CoCreateInstance) の明示 fail-fast (SHX-T33 #2916)

親 #1179 の §7-3 の子。測定 commit: `c9eb2d8e` (コードを変えた最後の commit。基点 `9286a6bb` = origin/main)。

| 項目 | 結果 |
|---|---|
| 素材 | `fl-win64` と `toolchain-emsdk` は `$ARTIFACTS_DIR` に実在を確認。`work-m11` は本 issue の oc_artifacts に無く、未取得 |
| CLSID の照合 | 追加した GUID 2 件は、FL の tar をストリームで走査 (展開なし) して FL 本体の PE 内のバイト列と一致を確認。FileOpenDialog `DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7` 82 件・FileSaveDialog `C0B4E2F3-BA21-4773-8DBA-335EC946EB8B` 81 件 (§1 と同じ件数) |
| 実装 | `tools/shimx/src/ole.c` の `CoCreateInstance`: 2 CLSID の一致時のみ `shim_unimplemented("CoCreateInstance(FileOpenDialog)")` / `shim_unimplemented("CoCreateInstance(FileSaveDialog)")`。clsid が NULL なら従来どおり |
| shimx 単体 (`bash tools/shimx/test.sh`、HEAD `c9eb2d8e`) | 所要 14 s。load average 0.25 → 0.42 (nproc 4)。step 1 (ビルド・生成物) PASS、2 MT PASS (8 グループ)、3 ST PASS |
| step 4 fail-fast | `ifiledialog` exit=1 ✓ (`CoCreateInstance(FileOpenDialog)`)、`ifilesave` exit=1 ✓ (`CoCreateInstance(FileSaveDialog)`)。既存の fail-fast 11 件も全て ✓ |
| 他の CLSID (受入 2) | MT/ST 単体 (test_ole_shell.c): ShellLink `{00021401-...}`・乱数 GUID・clsid=0 は、従来どおり `REGDB_E_CLASSNOTREG` かつ `obj == NULL` (abort しない) |
| step 5 (M4 互換) | **FAIL**: `tools/shim/test/test_main.c:204` (`HeapFree` に範囲外ポインタ → `GetLastError()==ERROR_INVALID_FUNCTION`)。`origin/main` `9286a6bb` を detached worktree で `test.sh` 実行した結果も同じ行で同じ FAIL。本変更は heap に触れない。step 5 以降は未実行 |
| step 6 署名 | `test/sig/sig_test.sh` ALL PASS (rc=0)。カバレッジ (`scripts/gen_inventory.py` 単独実行): 未実装 0・M4 53/53・担当範囲 100% |
| 生成物 | `gen_inventory.py` は `tools/m11/work` が無いと M11 列を変えて `inventory.csv`・`BACKLOG.md` を誤って書き換える (この worktree で P0 194 → 0 等)。コミットせず `git restore` で戻した。生成は work-m11 がある環境でのみ行う |

挙動変化 (m2): IFileDialog の CoCreateInstance は従来 `REGDB_E_CLASSNOTREG` で呼出元へ戻った。今後は、この 2 CLSID の呼出で名前を出して abort する (`DWriteCreateFactory` と同じ方針)。呼出元が失敗戻りを前提に fallback していた場合、その経路は abort になる。また clsid の指す GUID を読むため、不正なポインタは従来の戻り値ではなく wasm の境界外アクセスになり得る (他の clsid 参照 API と同じ扱い)。

### 8-1. 判定

- 受入 1 (fail-fast): **満たす** (`test.sh` step 4 の 2 件、名前出力を確認)。
- 受入 2 (他 CLSID の呼出元を壊さない): **部分**。単体で他 CLSID の戻り値は確認。実 boot の呼出元 (IR の呼出元 2 件 `function_c53c60`・`m11_tr_function_4690c0` が渡す CLSID) は work-m11 が無いため未確認。
- 受入 3 (test.sh の検査): **満たす** (`expect_fail ifiledialog` / `ifilesave`)。ただし test.sh 全体は step 5 の既存 FAIL で rc=1 のまま。

### 8-2. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| IR の CoCreateInstance 呼出元 2 件が渡す CLSID の確定と、他 CLSID 呼出元の挙動の確認 (受入 2 の残り)。work-m11 が要る | 実 boot での IFileDialog 呼出の有無と、abort の影響が未確定 | 既存 #942 へのコメント (`m11_e2e.sh --full` の IR で確認を依頼) |
| 本変更後の m11 survey の再測定 (§7-2 の文字列長による結果変化の再確認を含む) | shimx の変更で survey 結果が変わる実績がある | 既存 #942 へのコメント (§7-3 と同じ issue へ) |
| step 5 (M4 互換 MT) の heap 範囲外ポインタ検査の既存 FAIL (`origin/main` で再現) | test.sh の step 5 以降 (M4・カバレッジ・署名・OTT) が通らない | 既存 issue なし。PM 判断 (起票を依頼) |
| FLEngine 起動 KPI (dispatch 数・通過 unit 数) の前後 | 動かしていない。逐次 boot は #942 の停止 (unit 17) で止まる | 既存 #942 へのコメント (§7-3 と同じ) |
