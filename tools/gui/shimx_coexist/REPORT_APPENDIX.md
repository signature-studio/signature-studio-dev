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
