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
- **web 側の directory picker 実装の見送り**: 呼出の有無が未確定で、仕様 (picker の UI・戻り値のステージング先) を決められない。
- **次に必要な素材**: `work-m11` (`oc_artifacts` に追加)。trace 版の再 build が必要な場合は `tools/m11/REPORT_N1050.md` §5 の手順に従う。

## 4. 残作業 (起票先)

1. FL の `SHBrowseForFolderA/W` と `IFileDialog` の実呼出を `SHIMX_TRACE` で確認し、結果を本付録に追記する (#1179 で継続)。
2. 呼出ありと確定した場合: Web の対応 (File System Access directory picker) を実装し、node + mock 検査を `tools/gui/test` に追加する (#1179 で継続)。
3. 呼出なしと確定した場合: 未対応を fail-fast で明示する (`shimx` の登録と strict abort) し、`IMPORTS.md` を再生成する (#1179 で継続)。

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

## 6. 静的 call 箇所の再確認 (run 2026-10-14、コード差分 0)

検証起点: `origin/main` `3d21715b` (worktree `ws-1179`)。素材 `fl-win64` を `$RUNNER_TEMP/fl1179` に展開 (25,166 ファイル)。PE の IAT と `.text` の `call` / `jmp` を Python で直接走査した (IR を使わない独立確認)。

| 対象 PE | import 解決 | 静的 call 箇所 |
|---|---|---|
| `block00005_PE.bin` (FL 本体 EXE, PE32) | `SHBrowseForFolderA` = IAT `0x407154`、`CoCreateInstance` = IAT `0x407284` | `call [0x407154]` が `0x40432a` (SHBrowseForFolderA)、`call [0x407284]` が `0x402073` (CoCreateInstance)。いずれも 32bit 絶対 `FF 15 disp32` |
| `block00031_PE.bin` (FLEngine_x64.dll, PE32+) | `SHBrowseForFolder*` は**無し**。`GetOpenFileNameW` / `GetSaveFileNameW` / `CoCreateInstance` / `ShellExecute*` / `SHGetPathFromIDListW` 等は有り | RIP 相対 `FF 25` (jmp thunk) が 9 箇所 (`0x4690c0` CoCreateInstance、`0x5937e0` GetOpenFileNameW、`0x5937f0` GetSaveFileNameW ほか) |

判定:
- **フォルダ選択 (`SHBrowseForFolder*`) の静的 call は FL 本体 EXE の `0x40432a` 1 箇所**。その関数は IR の定義範囲 (`function_` は `0x406e60` 以降のみ) より前にあり、**lift closure の外**。IR に宣言が無いのはこのため。
- FLEngine 側の IR に `GetOpenFileNameW` 等の宣言が無いのは、`jmp` thunk 経由の呼出が lift で解決されていないことを示す (`REPORT_N1050.md` / `REPORT.md` §1 の間接 call 脱落と同根)。
- 呼出の**実行時の有無**は依然として未確定。closure 外の関数で、unit 17 の trap (#1050) より後に到達するため、実 boot の trace では判定できない。
- 受入条件 1 は**未達のまま**。方針決定 (受入条件 2) と gui mock 検査 (受入条件 3) も未着手。

### 5-1. 判定

- **実 boot ではフォルダ選択は呼ばれていない**。ただし、呼ばれていないと言えるのは unit 17 で `memory access out of bounds` により止まるまでの範囲に限る。
- 止まった位置より後の UI 経路 (設定画面など) で呼ばれるかは、この実行では分からない。`REPORT_N1050.md` §4 のとおり、unit 17〜18 付近の trap (`function_8c5eb0` が D19 と同一関数かは未確認) が先に解消されない限り、そこへ到達しない。
- IR に `SHBrowseForFolder*` の宣言が無いことは、FL の PE が静的 import しているという §1 の事実と食い違う。`boot_final3.ll` は lift 対象の範囲に限られるため、宣言が無いことを「呼ばれない」の根拠にはしない。
- 結論: 受入条件 1 (実呼出の確認) は**未達**。方針決定 (受入条件 2) と gui mock 検査 (受入条件 3) は、この結論に依存するため未着手。

### 5-2. 未解決 (起票先)

| 未解決 | 影響 | 起票先 |
|---|---|---|
| boot が unit 17〜18 付近で `memory access out of bounds` により停止する問題の解消 | 停止より後の UI 経路 (フォルダ選択の呼出位置) に到達できず、呼出有無が確定しない | #1050 (既存、`REPORT_N1050.md` §4) |
| `SHBrowseForFolder*` / `GetOpenFileNameW` 等の IR 宣言が無いことの原因 (lift の import 解決範囲) | IR 上の宣言だけでは呼出を判定できない | #1179 で継続 (lift 側の確認が必要な場合は子 issue) |
