# 自動生成: `python3 tools/m2/shim_inventory*.py` (M2 機械生成・人手チェック版)

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

# SHIM_INVENTORY (M2 機械生成 + 人手チェック版)
自動生成: `tools/m2/shim_inventory.py` (win/mac/libwinbridge の import/export 走査 → `docs/REFERENCES.md` `[STRATEGY]` §3 12 行への写影。shim 一覧の正本は `tools/shim/README.md`)。

## (0) 入力と成立条件

| 項目 | 値 |
|---|---|
| win64 DLL | `tools/m2/work/block00031_PE.bin` (gitignore・検証時に再抽出) |
| win64 import 名数 | 738 (依存 DLL 24) |
| mac slide | `tools/m2/work/FLEngine_x86_64.dylib` (gitignore) |
| mac slice exports | 1 / imports(外部シンボル) 337 |
| libwinbridge slice | `tools/m2/work/libwinbridge.dylib_x86_64.dylib` (gitignore) |
| libwinbridge exports | 34 (Win32 shim 面) |

## (1) libwinbridge exports 一覧 (= shim 実装面の機械採取初版)

- `DoDragDrop`
- `IsDragDropRegistered`
- `ProcessDragDrop`
- `ProcessDragOver`
- `ProcessDraggingEntered`
- `ProcessDraggingExited`
- `ProcessDraggingUpdated`
- `RegCloseKey`
- `RegConnectRegistryW`
- `RegCreateKeyExW`
- `RegDeleteKeyExW`
- `RegDeleteKeyW`
- `RegDeleteValueW`
- `RegEnumKeyExW`
- `RegEnumValueW`
- `RegFlushKey`
- `RegGetStoragePath`
- `RegLoadKeyW`
- `RegOpenKeyExW`
- `RegQueryInfoKeyW`
- `RegQueryValueExW`
- `RegReplaceKeyW`
- `RegRestoreKeyW`
- `RegSaveAllChanges`
- `RegSaveKeyW`
- `RegSetValueExW`
- `RegUnLoadKeyW`
- `RegWriteStringValue`
- `RegisterDragDrop`
- `RevokeDragDrop`
- `WBDownloadFile`
- `WBDownloadFileWithError`
- `WBGetMemoryManager`
- `WBUploadFile`

## (2) win64 DLL import 面 → winbridge exports 突合

- win 全 import 名 738 中、winbridge export 名に **そのまま一致するのは 14 個** (覆盖 14 / 738 = 1.9%)
- 未覆盖 724 個 → winbridge に無い import 面 (mac 版は Cocoa/CoreAudio 系へ置換のため、それらは §3 各行の単位で主に自家実装)

注: mac 版の主target では Win32 API 直呼びが libwinbridge の export 面と FLEngine 内の platform abstract 化で置換されるため、上記数値は「参照照合」材料として使う

## (3) §3 12 行への写影表

| # | shim | win 側一致数 | mac 側一致数 | win 代表名 |
|---|---|---|---|---|
| 1 | DirectSound / ASIO → AudioWorklet + SAB | 2 | 0 | `DirectSoundCreate`, `DirectSoundEnumerateA` |
| 2 | Win32 FS → Emscripten FS | 19 | 2 | `CloseHandle`, `CopyFileW`, `CreateDirectoryW`, `CreateFileMappingW`, `CreateFileW`, `DeleteFileW` |
| 3 | time / .timer → performance | 7 | 0 | `GetTickCount`, `KillTimer`, `QueryPerformanceCounter`, `QueryPerformanceFrequency`, `SetTimer`, `timeBeginPeriod` |
| 4 | thread / 同期 → pthread (SAB) + Atomics | 18 | 1 | `CreateEventW`, `CreateThread`, `DeleteCriticalSection`, `EnterCriticalSection`, `ExitThread`, `InitializeCriticalSection` |
| 5 | GUI / MSG / GDI / Cocoa → OffscreenCanvas | 33 | 0 | `BeginPaint`, `BitBlt`, `CreateFontIndirectW`, `CreateFontW`, `CreateWindowExW`, `DispatchMessageA` |
| 6 | registry → メモリ (IndexedDB) | 10 | 0 | `RegCloseKey`, `RegCreateKeyExW`, `RegDeleteKeyW`, `RegDeleteValueW`, `RegEnumKeyExW`, `RegEnumValueW` |
| 7 | module / heap → 自前実装 | 14 | 0 | `FreeLibrary`, `GetModuleHandleW`, `GetProcAddress`, `GetProcessHeap`, `HeapAlloc`, `HeapCreate` |
| 8 | CRT / libc (Delphi RTL 面外の不足部) → Emscripten libc | 16 | 5 | `CertFreeCertificateContext`, `CoTaskMemAlloc`, `CoTaskMemFree`, `FreeLibrary`, `FreeResource`, `GetDiskFreeSpaceW` |
| 9 | 外部プロセス起動 / dlopen 外部依存 → stub | 4 | 0 | `CreateProcessW`, `ShellExecuteA`, `ShellExecuteExW`, `ShellExecuteW` |
| 10 | MIDI → Web MIDI API | 20 | 2 | `midiInAddBuffer`, `midiInClose`, `midiInGetDevCapsW`, `midiInGetErrorTextW`, `midiInGetNumDevs`, `midiInOpen` |
| 11 | ネットワーク / 認証 / クラウド → stub | 6 | 2 | `HttpOpenRequestW`, `HttpSendRequestExW`, `InternetConnectW`, `InternetGetConnectedState`, `InternetOpenUrlW`, `InternetOpenW` |
| 12 | プラグイン ABI ホスト (FL 内部ジェネレータIF) | 0 | 0 |  |

## (4) mac 側 FLEngine slice の import detail

| 依存 dylib | シンボル数 |
|---|---|
| AppKit | 12 |
| AudioToolbox | 10 |
| CoreAudio | 5 |
| CoreFoundation | 47 |
| CoreGraphics | 51 |
| CoreMIDI | 16 |
| CoreServices | 4 |
| CoreText | 9 |
| Foundation | 17 |
| QuartzCore | 1 |
| SystemConfiguration | 2 |
| WebKit | 5 |
| libSystem | 140 |
| libiconv | 3 |
| libobjc | 10 |
| libz | 5 |

**mac slice 依存 dylib 一覧**: __TEXT, __text, __TEXT, __stubs, __TEXT, __stub_helper, __TEXT, .fpc, __TEXT, __const, __TEXT, __objc_methname, __TEXT, __objc_methtype, __TEXT, __objc_classname, __TEXT, __unwind_info, __TEXT, __eh_frame, __TEXT, __DATA, __nl_symbol_ptr, __DATA, __got, __DATA, __la_symbol_ptr, __DATA, __mod_init_func, __DATA, __mod_term_func, __DATA, __const, __DATA, __objc_classlist, __DATA, __objc_protolist, __DATA, __objc_imageinfo, __DATA, __objc_const, __DATA, __objc_selrefs, __DATA, __objc_data, __DATA, __data, __DATA, __objc_clsrefs, __DATA, fpc.resources, __DATA, fpc.reshandles, __DATA, __common, __DATA, __bss, __DATA, __LINKEDIT, /Users/imageline/Jenkins/workspace/build-flstudio-mac/build/OsxFL64.app/Contents/Libs/FLEngine_x64.dylib (offset 24), /usr/lib/libSystem.B.dylib (offset 24), /usr/lib/libobjc.A.dylib (offset 24), /usr/lib/libiconv.2.dylib (offset 24), /usr/lib/libz.1.dylib (offset 24), /System/Library/Frameworks/Foundation.framework/Versions/C/Foundation (offset 24), /System/Library/Frameworks/Cocoa.framework/Versions/A/Cocoa (offset 24), /System/Library/Frameworks/QuartzCore.framework/Versions/A/QuartzCore (offset 24), /System/Library/Frameworks/CoreData.framework/Versions/A/CoreData (offset 24), /System/Library/Frameworks/AppKit.framework/Versions/C/AppKit (offset 24), /System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation (offset 24), /System/Library/Frameworks/WebKit.framework/Versions/A/WebKit (offset 24), /System/Library/Frameworks/SystemConfiguration.framework/Versions/A/SystemConfiguration (offset 24), /System/Library/Frameworks/CoreMIDI.framework/Versions/A/CoreMIDI (offset 24), /System/Library/Frameworks/AudioToolbox.framework/Versions/A/AudioToolbox (offset 24), /System/Library/Frameworks/CoreAudio.framework/Versions/A/CoreAudio (offset 24), /System/Library/Frameworks/AudioUnit.framework/Versions/A/AudioUnit (offset 24), /System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics (offset 24), /System/Library/Frameworks/CoreServices.framework/Versions/A/CoreServices (offset 24), /System/Library/Frameworks/CoreText.framework/Versions/A/CoreText (offset 24)

## (5) 注意点 (§3 結合時)

- 本 inventory は「import 面の静的重み関係」のみを記す。各 shim 行の実装面 (必要 Win32 依存部分の自家実装量) は §3 表の工数見積 (P0 40-58人週) とは別に、M4 での単体テストスイートで清掃能力を測定する意図。
- winbridge exports は「PL Registry 面 / DragDrop 面 / WB ソケット等の小さい意図」に留まる点に留意 (mac shim 面としては §3 の P0 各行とは別に新規面の増設が必要).
- win 側の registry 面 (advapi32 import) と winbridge の Reg* export は 一対として対応。WinInet/WinHTTP/WSASocket/winspool 等は消去対象・stub 対象で、§3 注記と §7.3 の遷移記述と対照で評価.
