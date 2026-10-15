# BACKLOG — shimx 実装バックログ (優先度順, 実測)

> 正本: `tools/shimx/BACKLOG.md` (未解決一覧・解決済みは削除可)。
> **行数目安**: 本ファイルは未解決一覧の上限 300 行を超過 (`docs/DOC_MAP.md` §1 の上限ルール参照)。
> 超過分は Git 履歴に残る形での分割移動を推奨 (**内容は削除しない**)。

優先度の定義 (必須性→使用頻度): **P0** = M11 init closure が declare する API または OTT undefined 24 種 / **P1** = FLEngine 静的呼出サイト ≥10 または 3 プラグイン以上が使用 / **P2** = FLEngine 静的 import のその他 / **P3** = delay-load・プラグイン専用 / **X** = 他担当 DLL (対象外)。
呼出サイト数 = FLEngine_x64.dll の `jmp [IAT]` thunk への call/jmp/lea 参照数 (静的, `scripts/import_scan.py`)。

## 集計

| 優先 | API 数 | 機能実装 | スタブ | libc | 序数(同定・実装済) | 序数(未解決) | 未実装 | 対象外 |
|---|---|---|---|---|---|---|---|---|
| P0 | 194 | 176 | 18 | 0 | 0 | 0 | 0 | 0 |
| P1 | 38 | 34 | 4 | 0 | 0 | 0 | 0 | 0 |
| P2 | 165 | 64 | 100 | 1 | 0 | 0 | 0 | 0 |
| P3 | 111 | 63 | 34 | 8 | 5 | 1 | 0 | 0 |
| X | 544 | 0 | 0 | 0 | 0 | 0 | 0 | 544 |

## 一覧 (P0〜P3。X は件数のみ — 全件は data/inventory.csv)

| 優先 | API | DLL | 呼出サイト | M11 | OTT | プラグイン | 状態 | 実装 | 備考 |
|---|---|---|---|---|---|---|---|---|---|
| P0 | LeaveCriticalSection | kernel32 | 799 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P0 | EnterCriticalSection | kernel32 | 699 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c | Win64 40B レイアウトを直接実装 |
| P0 | MulDiv | kernel32 | 164 | ● |  |  | 機能実装 | str.c |  |
| P0 | FreeLibrary | kernel32 | 106 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P0 | RegCloseKey | advapi32 | 99 | ● |  | FL64/Serum2 | 機能実装 | reg.c |  |
| P0 | timeGetTime | winmm | 79 | ● |  | OTT | 機能実装 | timer.c | M4 継承 (emscripten_get_now) |
| P0 | CloseHandle | kernel32 | 73 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | handles.c |  |
| P0 | DeleteCriticalSection | kernel32 | 65 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P0 | InitializeCriticalSection | kernel32 | 65 | ● |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P0 | GetLastError | kernel32 | 61 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P0 | GetCurrentThreadId | kernel32 | 51 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | thread.c |  |
| P0 | LoadLibraryW | kernel32 | 48 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c | モジュール表+load フック。実体ロードは hostbridge |
| P0 | VariantInit | oleaut32 | 48 | ● |  |  | 機能実装 | ole.c |  |
| P0 | RegQueryValueExW | advapi32 | 46 | ● |  | FL64/Serum2 | 機能実装 | reg.c |  |
| P0 | GlobalUnlock | kernel32 | 44 | ● |  | OTT/Serum2 | 機能実装 | heap.c | M4 互換 (ロック済みなら TRUE) |
| P0 | GetTickCount | kernel32 | 42 | ● |  | OTT/Serum2 | 機能実装 | timer.c |  |
| P0 | GetModuleHandleW | kernel32 | 37 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P0 | Sleep | kernel32 | 33 | ● |  | OTT/Serum2 | 機能実装 | timer.c |  |
| P0 | GetCurrentProcess | kernel32 | 31 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | thread.c |  |
| P0 | DeleteFileW | kernel32 | 28 | ● |  | OTT/Serum2 | 機能実装 | file.c |  |
| P0 | CoTaskMemFree | ole32 | 27 | ● |  | FreshAir/Serum2 | 機能実装 | ole.c |  |
| P0 | GlobalLock | kernel32 | 27 | ● |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P0 | GetComputerNameExW | kernel32 | 26 | ● |  |  | 機能実装 | env.c |  |
| P0 | QueryPerformanceCounter | kernel32 | 25 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | timer.c |  |
| P0 | RegOpenKeyExA | advapi32 | 25 | ● |  | Serum2 | 機能実装 | reg.c |  |
| P0 | CompareStringW | kernel32 | 24 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P0 | GetModuleFileNameW | kernel32 | 22 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P0 | MoveFileW | kernel32 | 20 | ● |  |  | 機能実装 | file.c |  |
| P0 | UnmapViewOfFile | kernel32 | 20 | ● |  | Serum2 | 機能実装 | file.c |  |
| P0 | SetLastError | kernel32 | 19 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P0 | GlobalAlloc | kernel32 | 18 | ● |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P0 | GlobalFree | kernel32 | 18 | ● |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P0 | CreateEventW | kernel32 | 17 | ● |  | FreshAir/OTT | 機能実装 | wait.c |  |
| P0 | SetEvent | kernel32 | 17 | ● |  | FreshAir/OTT | 機能実装 | wait.c |  |
| P0 | ShellExecuteW | shell32 | 17 | ● |  | Serum2 | スタブ(エラー/無し返却) | shell.c | shimx_set_shell_execute_hook 経由 |
| P0 | WaitForSingleObject | kernel32 | 16 | ● |  | OTT/Serum2 | 機能実装 | wait.c |  |
| P0 | CreateFileW | kernel32 | 15 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c | Win→FS パス写像 + 大小無視再探索 |
| P0 | SetErrorMode | kernel32 | 15 | ● |  |  | スタブ(エラー/無し返却) | env.c |  |
| P0 | CoCreateInstance | ole32 | 14 | ● |  | OTT/Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P0 | RegOpenKeyExW | advapi32 | 14 | ● |  | FL64 | 機能実装 | reg.c | メモリ内レジストリ |
| P0 | GetCurrentProcessId | kernel32 | 13 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | thread.c |  |
| P0 | GetLocaleInfoW | kernel32 | 13 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c | en-US 固定データ (LCID 名のみ数種) |
| P0 | GetFileAttributesW | kernel32 | 12 | ● |  | FL64/OTT/Serum2 | 機能実装 | file.c |  |
| P0 | GetProcAddress | kernel32 | 12 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c | 組込み表 (proctable) + 外部フック。未知名は NULL |
| P0 | GetStdHandle | kernel32 | 11 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P0 | MultiByteToWideChar | kernel32 | 11 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c | CP 1252/437近似/Latin1/ASCII/UTF-8。DBCS (932 等) は ERROR_INVALID_PARAMETER |
| P0 | OutputDebugStringW | kernel32 | 11 | ● |  | OTT/Serum2 | スタブ(エラー/無し返却) | env.c |  |
| P0 | LocalFree | kernel32 | 10 | ● |  | FL64/Serum2 | 機能実装 | heap.c |  |
| P0 | GetThreadLocale | kernel32 | 9 | ● |  |  | 機能実装 | locale.c |  |
| P0 | MapViewOfFile | kernel32 | 9 | ● |  | Serum2 | 機能実装 | file.c |  |
| P0 | WideCharToMultiByte | kernel32 | 9 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P0 | WriteFile | kernel32 | 9 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P0 | CharNextW | user32 | 8 | ● |  |  | 機能実装 | str.c |  |
| P0 | GetFileAttributesExW | kernel32 | 8 | ● |  | OTT/Serum2 | 機能実装 | file.c |  |
| P0 | GetTempPathW | kernel32 | 8 | ● |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P0 | QueryPerformanceFrequency | kernel32 | 8 | ● |  | OTT/Serum2 | 機能実装 | timer.c |  |
| P0 | ResetEvent | kernel32 | 8 | ● |  | FreshAir/OTT | 機能実装 | wait.c |  |
| P0 | SetFileAttributesW | kernel32 | 8 | ● |  |  | 機能実装 | file.c |  |
| P0 | CoUninitialize | ole32 | 7 | ● |  |  | 機能実装 | ole.c |  |
| P0 | CreateFileMappingW | kernel32 | 7 | ● |  | Serum2 | 機能実装 | file.c | 共有バッファ方式 (Unmap/Flush で書戻し) |
| P0 | GetVersionExW | kernel32 | 7 | ● |  | OTT/Serum2 | 機能実装 | env.c | 10.0.19045 (shimx_set_version で変更) |
| P0 | VerSetConditionMask | kernel32 | 7 | ● |  |  | 機能実装 | env.c |  |
| P0 | VirtualFree | kernel32 | 7 | ● |  |  | 機能実装 | heap.c |  |
| P0 | VirtualQuery | kernel32 | 7 | ● |  |  | 機能実装 | heap.c |  |
| P0 | FileTimeToSystemTime | kernel32 | 6 | ● |  | FL64/FreshAir/Serum2 | 機能実装 | timer.c |  |
| P0 | FindClose | kernel32 | 6 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P0 | FindFirstFileW | kernel32 | 6 | ● |  | Serum2 | 機能実装 | file.c | 先頭で全列挙→大小無視ソート |
| P0 | GetSystemInfo | kernel32 | 6 | ● |  | Serum2 | 機能実装 | env.c |  |
| P0 | LocalAlloc | kernel32 | 6 | ● |  | FL64 | 機能実装 | heap.c |  |
| P0 | SetFilePointer | kernel32 | 6 | ● |  | OTT/Serum2 | 機能実装 | file.c |  |
| P0 | SysFreeString | oleaut32 | 6 | ● |  |  | 機能実装 | ole.c |  |
| P0 | VirtualAlloc | kernel32 | 6 | ● |  |  | 機能実装 | heap.c | weak (m11_rt.c 強定義が優先) |
| P0 | VirtualProtect | kernel32 | 6 | ● |  | Serum2 | 機能実装 | heap.c |  |
| P0 | FileTimeToLocalFileTime | kernel32 | 5 | ● |  |  | 機能実装 | timer.c |  |
| P0 | FormatMessageW | kernel32 | 5 | ● |  | OTT/Serum2 | 機能実装 | locale.c |  |
| P0 | GetACP | kernel32 | 5 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P0 | GetFileSize | kernel32 | 5 | ● |  | Serum2 | 機能実装 | file.c |  |
| P0 | GetLocalTime | kernel32 | 5 | ● |  |  | 機能実装 | timer.c |  |
| P0 | OleUninitialize | ole32 | 5 | ● |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P0 | SetCurrentDirectoryW | kernel32 | 5 | ● |  | FL64 | 機能実装 | file.c |  |
| P0 | SetDllDirectoryW | kernel32 | 5 | ● |  |  | 機能実装 | module.c |  |
| P0 | CoInitialize | ole32 | 4 | ● |  |  | 機能実装 | ole.c | スレッド毎カウント |
| P0 | EnumCalendarInfoW | kernel32 | 4 | ● |  |  | 機能実装 | locale.c |  |
| P0 | FileTimeToDosDateTime | kernel32 | 4 | ● |  |  | 機能実装 | timer.c |  |
| P0 | FindResourceW | kernel32 | 4 | ● |  | OTT | 機能実装 | module.c |  |
| P0 | GetEnvironmentVariableW | kernel32 | 4 | ● |  |  | 機能実装 | env.c |  |
| P0 | GetTimeZoneInformation | kernel32 | 4 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | timer.c |  |
| P0 | GetVersion | kernel32 | 4 | ● |  |  | 機能実装 | env.c |  |
| P0 | OleInitialize | ole32 | 4 | ● |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P0 | SafeArrayPtrOfIndex | oleaut32 | 4 | ● |  |  | 機能実装 | ole.c |  |
| P0 | TlsGetValue | kernel32 | 4 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P0 | VerQueryValueW | version | 4 | ● |  |  | 機能実装 | shell.c |  |
| P0 | CreateThread | kernel32 | 3 | ● |  | OTT/Serum2 | 機能実装 | thread.c | CREATE_SUSPENDED 対応/threadId 修正 (M4 差分) |
| P0 | ExpandEnvironmentStringsW | kernel32 | 3 | ● |  |  | 機能実装 | env.c |  |
| P0 | FindNextFileW | kernel32 | 3 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P0 | GetCPInfo | kernel32 | 3 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P0 | GetCommandLineW | kernel32 | 3 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P0 | GetCurrentThread | kernel32 | 3 | ● |  | OTT | 機能実装 | thread.c |  |
| P0 | GetDriveTypeW | kernel32 | 3 | ● |  | FL64/FreshAir/Serum2 | 機能実装 | file.c |  |
| P0 | GetFileVersionInfoSizeW | version | 3 | ● |  |  | 機能実装 | shell.c |  |
| P0 | GetFileVersionInfoW | version | 3 | ● |  |  | 機能実装 | shell.c | 合成版情報 (FL 26.1.7.5653) |
| P0 | GetProcessHeap | kernel32 | 3 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P0 | GetSystemDefaultUILanguage | kernel32 | 3 | ● |  |  | 機能実装 | locale.c |  |
| P0 | GetVolumeInformationW | kernel32 | 3 | ● |  |  | 機能実装 | file.c |  |
| P0 | GlobalAddAtomW | kernel32 | 3 | ● |  |  | 機能実装 | env.c |  |
| P0 | GlobalDeleteAtom | kernel32 | 3 | ● |  |  | 機能実装 | env.c |  |
| P0 | HeapFree | kernel32 | 3 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P0 | IsValidLocale | kernel32 | 3 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c |  |
| P0 | MsgWaitForMultipleObjects | user32 | 3 | ● |  |  | 機能実装 | wait.c | weak。kernel object 待ちのみ (メッセージ無し) |
| P0 | ReadFile | kernel32 | 3 | ● |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P0 | RegEnumKeyExW | advapi32 | 3 | ● |  |  | 機能実装 | reg.c |  |
| P0 | SHGetFolderPathW | shfolder | 3 | ● |  |  | 機能実装 | shell.c |  |
| P0 | SafeArrayGetLBound | oleaut32 | 3 | ● |  |  | 機能実装 | ole.c |  |
| P0 | SafeArrayGetUBound | oleaut32 | 3 | ● |  |  | 機能実装 | ole.c |  |
| P0 | SetThreadErrorMode | kernel32 | 3 | ● |  |  | スタブ(エラー/無し返却) | env.c |  |
| P0 | SwitchToThread | kernel32 | 3 | ● |  |  | 機能実装 | timer.c |  |
| P0 | SysAllocStringLen | oleaut32 | 3 | ● |  |  | 機能実装 | ole.c |  |
| P0 | VariantClear | oleaut32 | 3 | ● |  |  | 機能実装 | ole.c |  |
| P0 | VariantCopy | oleaut32 | 3 | ● |  |  | 機能実装 | ole.c |  |
| P0 | VerifyVersionInfoW | kernel32 | 3 | ● |  |  | 機能実装 | env.c |  |
| P0 | acmMetrics | msacm32 | 3 | ● |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P0 | lstrlenW | kernel32 | 3 | ● |  |  | 機能実装 | str.c |  |
| P0 | CharLowerBuffW | user32 | 2 | ● |  |  | 機能実装 | str.c |  |
| P0 | CharUpperBuffW | user32 | 2 | ● |  |  | 機能実装 | str.c |  |
| P0 | CharUpperW | user32 | 2 | ● |  | Serum2 | 機能実装 | str.c | weak (tools/gui が上書き可) |
| P0 | CreateDirectoryW | kernel32 | 2 | ● |  | OTT | 機能実装 | file.c |  |
| P0 | DosDateTimeToFileTime | kernel32 | 2 | ● |  |  | 機能実装 | timer.c |  |
| P0 | DuplicateHandle | kernel32 | 2 | ● |  |  | 機能実装 | handles.c |  |
| P0 | ExitProcess | kernel32 | 2 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c | exit hook + exit() |
| P0 | GetDateFormatW | kernel32 | 2 | ● |  | FL64/Serum2 | 機能実装 | timer.c |  |
| P0 | GetFullPathNameW | kernel32 | 2 | ● |  | FL64/FreshAir/Serum2 | 機能実装 | file.c |  |
| P0 | GetUserDefaultUILanguage | kernel32 | 2 | ● |  |  | 機能実装 | locale.c |  |
| P0 | GlobalFindAtomW | kernel32 | 2 | ● |  |  | 機能実装 | env.c |  |
| P0 | HeapAlloc | kernel32 | 2 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P0 | ImageNtHeader | imagehlp | 2 | ● |  |  | 機能実装 | module.c |  |
| P0 | LCMapStringW | kernel32 | 2 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P0 | LocalFileTimeToFileTime | kernel32 | 2 | ● |  |  | 機能実装 | timer.c |  |
| P0 | RegCreateKeyExW | advapi32 | 2 | ● |  |  | 機能実装 | reg.c |  |
| P0 | RegEnumValueW | advapi32 | 2 | ● |  |  | 機能実装 | reg.c |  |
| P0 | RemoveDirectoryW | kernel32 | 2 | ● |  | OTT/Serum2 | 機能実装 | file.c |  |
| P0 | ResumeThread | kernel32 | 2 | ● |  |  | 機能実装 | thread.c |  |
| P0 | SHAppBarMessage | shell32 | 2 | ● |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P0 | SHGetMalloc | shell32 | 2 | ● |  |  | 機能実装 | ole.c | IMalloc (Win64 vtable) |
| P0 | SafeArrayCreate | oleaut32 | 2 | ● |  |  | 機能実装 | ole.c |  |
| P0 | SetFileTime | kernel32 | 2 | ● |  | Serum2 | 機能実装 | file.c |  |
| P0 | SetThreadLocale | kernel32 | 2 | ● |  |  | 機能実装 | locale.c |  |
| P0 | TerminateProcess | kernel32 | 2 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P0 | TlsSetValue | kernel32 | 2 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P0 | timeBeginPeriod | winmm | 2 | ● |  | OTT | スタブ(エラー/無し返却) | timer.c |  |
| P0 | timeEndPeriod | winmm | 2 | ● |  |  | スタブ(エラー/無し返却) | timer.c |  |
| P0 | timeGetDevCaps | winmm | 2 | ● |  |  | スタブ(エラー/無し返却) | timer.c |  |
| P0 | AddAtomW | kernel32 | 1 | ● |  |  | 機能実装 | env.c |  |
| P0 | CharLowerW | user32 | 1 | ● |  | Serum2 | 機能実装 | str.c |  |
| P0 | DeleteAtom | kernel32 | 1 | ● |  |  | 機能実装 | env.c |  |
| P0 | EnumSystemLocalesW | kernel32 | 1 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c |  |
| P0 | FindAtomW | kernel32 | 1 | ● |  |  | 機能実装 | env.c |  |
| P0 | GetConsoleOutputCP | kernel32 | 1 |  | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | ini.c |  |
| P0 | GetExitCodeThread | kernel32 | 1 | ● |  | Serum2 | 機能実装 | thread.c |  |
| P0 | GetLogicalDriveStringsW | kernel32 | 1 | ● |  |  | 機能実装 | file.c |  |
| P0 | GetStartupInfoW | kernel32 | 1 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P0 | InternetGetConnectedState | wininet | 1 | ● |  |  | スタブ(エラー/無し返却) | net.c | FALSE |
| P0 | IsDebuggerPresent | kernel32 | 1 |  | ● | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | env.c |  |
| P0 | LoadLibraryExW | kernel32 | 1 | ● | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P0 | LoadResource | kernel32 | 1 | ● |  | OTT/Serum2 | 機能実装 | module.c |  |
| P0 | LockResource | kernel32 | 1 | ● |  | OTT/Serum2 | 機能実装 | module.c |  |
| P0 | PathCleanupSpec | shell32 | 1 | ● |  |  | 機能実装 | file.c |  |
| P0 | QueryDosDeviceW | kernel32 | 1 | ● |  |  | 機能実装 | file.c |  |
| P0 | RegFlushKey | advapi32 | 1 | ● |  |  | 機能実装 | reg.c |  |
| P0 | RegQueryInfoKeyW | advapi32 | 1 | ● |  |  | 機能実装 | reg.c |  |
| P0 | RegSetValueExW | advapi32 | 1 | ● |  |  | 機能実装 | reg.c |  |
| P0 | SHGetFolderPathW | shell32 | 1 | ● |  |  | 機能実装 | shell.c |  |
| P0 | SetEnvironmentVariableW | kernel32 | 1 | ● |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P0 | SetThreadPriority | kernel32 | 1 | ● |  | OTT | 機能実装 | thread.c | 値保持のみ |
| P0 | SizeofResource | kernel32 | 1 | ● |  | OTT/Serum2 | 機能実装 | module.c |  |
| P0 | SysReAllocStringLen | oleaut32 | 1 | ● |  |  | 機能実装 | ole.c |  |
| P0 | UnhandledExceptionFilter | kernel32 | 1 |  | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c |  |
| P0 | VariantCopyInd | oleaut32 | 1 | ● |  |  | 機能実装 | ole.c |  |
| P0 | VirtualQueryEx | kernel32 | 1 | ● |  |  | 機能実装 | heap.c |  |
| P0 | midiOutShortMsg | winmm | 1 | ● |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P0 | GetConsoleMode | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | ini.c |  |
| P0 | GetFinalPathNameByHandleW | kernel32 | 0 | ● |  |  | 機能実装 | file.c |  |
| P0 | GetLogicalProcessorInformation | kernel32 | 0 | ● |  |  | 機能実装 | env.c |  |
| P0 | GetNativeSystemInfo | kernel32 | 0 | ● |  | Serum2 | 機能実装 | env.c |  |
| P0 | GetStringTypeW | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P0 | GetSystemDefaultLocaleName | kernel32 | 0 | ● |  |  | 機能実装 | locale.c |  |
| P0 | IsProcessorFeaturePresent | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c | FASTFAIL(23)/AVX 系は FALSE |
| P0 | LocaleNameToLCID | kernel32 | 0 | ● |  |  | 機能実装 | locale.c |  |
| P0 | RtlCaptureContext | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c |  |
| P0 | RtlLookupFunctionEntry | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c |  |
| P0 | RtlPcToFileHeader | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c |  |
| P0 | RtlVirtualUnwind | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c |  |
| P0 | SetUnhandledExceptionFilter | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c |  |
| P0 | WTSRegisterSessionNotification | wtsapi32 | 0 | ● |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P0 | WriteConsoleW | kernel32 | 0 |  | ● | FL64/FreshAir/OTT/Serum2 | 機能実装 | ini.c |  |
| P1 | IsEqualGUID | ole32 | 114 |  |  |  | 機能実装 | ole.c |  |
| P1 | CopyFileW | kernel32 | 35 |  |  |  | 機能実装 | file.c |  |
| P1 | ReleaseStgMedium | ole32 | 18 |  |  |  | 機能実装 | ole.c |  |
| P1 | RaiseException | kernel32 | 5 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c | VEH→SEH frame 鎖 (longjmp 捕捉)→UEF→fail-fast (継続可能例外のみ復帰) |
| P1 | GetCurrentDirectoryW | kernel32 | 4 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | SetEndOfFile | kernel32 | 3 |  |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetFileInformationByHandle | kernel32 | 2 |  |  | FL64/FreshAir/Serum2 | 機能実装 | file.c |  |
| P1 | GetFileType | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetUserDefaultLCID | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c |  |
| P1 | GetOEMCP | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | RtlUnwindEx | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c | SEH frame 巻き戻し (frame 未登録は fail-fast) |
| P1 | SystemTimeToTzSpecificLocalTime | kernel32 | 1 |  |  | FL64/FreshAir/Serum2 | 機能実装 | timer.c |  |
| P1 | TlsAlloc | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | TlsFree | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | DecodePointer | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | EncodePointer | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | FindFirstFileExW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | FlushFileBuffers | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | FreeEnvironmentStringsW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | GetCommandLineA | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | GetEnvironmentStringsW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | GetFileSizeEx | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetModuleHandleExW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P1 | GetSystemTimeAsFileTime | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | timer.c |  |
| P1 | HeapReAlloc | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | HeapSize | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | InitializeCriticalSectionAndSpinCount | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | InitializeCriticalSectionEx | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | InitializeSListHead | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | InterlockedFlushSList | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | IsValidCodePage | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | LCMapStringEx | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | PeekNamedPipe | kernel32 | 0 |  |  | FL64/FreshAir/Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P1 | ReadConsoleW | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | ini.c |  |
| P1 | RtlUnwind | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c | SEH frame 巻き戻し (frame 未登録は fail-fast) |
| P1 | SetFilePointerEx | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | SetStdHandle | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | WaitForSingleObjectEx | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | 機能実装 | wait.c |  |
| P2 | InternetCloseHandle | wininet | 9 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P2 | SetProcessAffinityMask | kernel32 | 9 |  |  |  | スタブ(エラー/無し返却) | thread.c |  |
| P2 | GlobalSize | kernel32 | 8 |  |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P2 | memset | api-ms-win-crt-string-l1-1-0 | 7 |  |  |  | libc 解決 |  |  |
| P2 | RegisterDragDrop | ole32 | 6 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P2 | RevokeDragDrop | ole32 | 6 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P2 | CreateStreamOnHGlobal | ole32 | 5 |  |  | OTT/Serum2 | 機能実装 | ole.c | IStream (Win64 vtable 8B スロット) |
| P2 | HttpQueryInfoA | wininet | 5 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | OleSetClipboard | ole32 | 5 |  |  | Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P2 | SetPriorityClass | kernel32 | 5 |  |  | OTT | スタブ(エラー/無し返却) | thread.c |  |
| P2 | CertGetNameStringW | crypt32 | 4 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | CoGetInterfaceAndReleaseStream | ole32 | 4 |  |  |  | 機能実装 | ole.c |  |
| P2 | CoMarshalInterThreadInterfaceInStream | ole32 | 4 |  |  |  | 機能実装 | ole.c |  |
| P2 | CryptMsgGetParam | crypt32 | 4 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | EnumPrintersW | winspool.drv | 4 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | GetPrivateProfileStringW | kernel32 | 4 |  |  |  | 機能実装 | ini.c |  |
| P2 | ILFree | shell32 | 4 |  |  |  | 機能実装 | shell.c |  |
| P2 | SHGetDesktopFolder | shell32 | 4 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SetThreadExecutionState | kernel32 | 4 |  |  |  | スタブ(エラー/無し返却) | thread.c |  |
| P2 | WinVerifyTrust | wintrust | 4 |  |  | FL64 | スタブ(エラー/無し返却) | net.c | NOSIGNATURE (shimx_set_trust_ok で成功化) |
| P2 | WritePrivateProfileStringW | kernel32 | 4 |  |  |  | 機能実装 | ini.c |  |
| P2 | midiOutGetDevCapsW | winmm | 4 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiOutGetNumDevs | winmm | 4 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | CreateILockBytesOnHGlobal | ole32 | 3 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | GetExitCodeProcess | kernel32 | 3 |  |  |  | 機能実装 | thread.c |  |
| P2 | GetProcessAffinityMask | kernel32 | 3 |  |  |  | 機能実装 | thread.c |  |
| P2 | GetTempFileNameW | kernel32 | 3 |  |  |  | 機能実装 | file.c |  |
| P2 | ImageRvaToVa | imagehlp | 3 |  |  |  | 機能実装 | module.c |  |
| P2 | InternetOpenW | wininet | 3 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | InternetReadFile | wininet | 3 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P2 | OleGetClipboard | ole32 | 3 |  |  | Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P2 | SHFileOperationW | shell32 | 3 |  |  | Serum2 | 機能実装 | shell.c |  |
| P2 | SHGetPathFromIDListW | shell32 | 3 |  |  |  | 機能実装 | shell.c |  |
| P2 | SafeArrayGetElement | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayPutElement | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | ShellExecuteExW | shell32 | 3 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | StgCreateDocfileOnILockBytes | ole32 | 3 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | WaitForMultipleObjectsEx | kernel32 | 3 |  |  |  | 機能実装 | wait.c |  |
| P2 | midiInGetNumDevs | winmm | 3 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c | デバイス 0 台 (weak; Web MIDI は下流) |
| P2 | CertFindCertificateInStore | crypt32 | 2 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | CertFreeCertificateContext | crypt32 | 2 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | ClosePrinter | winspool.drv | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | CoTaskMemAlloc | ole32 | 2 |  |  |  | 機能実装 | ole.c |  |
| P2 | CreateProcessW | kernel32 | 2 |  |  |  | スタブ(エラー/無し返却) | env.c | 常に ERROR_FILE_NOT_FOUND |
| P2 | CryptQueryObject | crypt32 | 2 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | DoDragDrop | ole32 | 2 |  |  | OTT/Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P2 | DocumentPropertiesW | winspool.drv | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | DragAcceptFiles | shell32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | DragQueryFileW | shell32 | 2 |  |  | OTT/Serum2 | スタブ(エラー/無し返却) | shell.c |  |
| P2 | GetActiveObject | oleaut32 | 2 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | GetDiskFreeSpaceW | kernel32 | 2 |  |  | Serum2 | 機能実装 | file.c |  |
| P2 | GetLogicalDrives | kernel32 | 2 |  |  |  | 機能実装 | file.c |  |
| P2 | GetThreadPriority | kernel32 | 2 |  |  |  | 機能実装 | thread.c |  |
| P2 | HeapDestroy | kernel32 | 2 |  |  | Serum2 | 機能実装 | heap.c |  |
| P2 | ILCreateFromPathW | shell32 | 2 |  |  |  | 機能実装 | shell.c |  |
| P2 | InternetGetLastResponseInfoW | wininet | 2 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | InternetOpenUrlW | wininet | 2 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | IsBadWritePtr | kernel32 | 2 |  |  |  | 機能実装 | heap.c |  |
| P2 | IsDBCSLeadByteEx | kernel32 | 2 |  |  |  | 機能実装 | str.c |  |
| P2 | SHGetFileInfoW | shell32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHGetSpecialFolderLocation | shell32 | 2 |  |  |  | 機能実装 | shell.c |  |
| P2 | WNetCloseEnum | mpr | 2 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | acmDriverClose | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamClose | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamConvert | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamPrepareHeader | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamSize | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | midiInAddBuffer | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInGetDevCapsW | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInPrepareHeader | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | AddVectoredExceptionHandler | kernel32 | 1 |  |  |  | 機能実装 | seh.c |  |
| P2 | AssignProcessToJobObject | kernel32 | 1 |  |  |  | スタブ(エラー/無し返却) | env.c |  |
| P2 | CLSIDFromString | ole32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | CertCloseStore | crypt32 | 1 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | ChangeTimerQueueTimer | kernel32 | 1 |  |  |  | 機能実装 | thread.c |  |
| P2 | CharNextExA | user32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | CharToOemBuffW | user32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | CoGetClassObject | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | CompareFileTime | kernel32 | 1 |  |  |  | 機能実装 | timer.c |  |
| P2 | CompareStringA | kernel32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | CreateDataAdviseHolder | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | CreateTimerQueueTimer | kernel32 | 1 |  |  |  | 機能実装 | thread.c |  |
| P2 | CryptMsgClose | crypt32 | 1 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | DeleteTimerQueueTimer | kernel32 | 1 |  |  |  | 機能実装 | thread.c |  |
| P2 | DragFinish | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | DragQueryPoint | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | ExitThread | kernel32 | 1 |  |  | OTT/Serum2 | 機能実装 | thread.c |  |
| P2 | FreeResource | kernel32 | 1 |  |  |  | 機能実装 | module.c |  |
| P2 | GetCPInfoExW | kernel32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | GetComputerNameW | kernel32 | 1 |  |  |  | 機能実装 | env.c |  |
| P2 | GetConsoleCP | kernel32 | 1 |  |  |  | 機能実装 | ini.c |  |
| P2 | GetDefaultPrinterW | winspool.drv | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | GetErrorInfo | oleaut32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | GetSystemDirectoryW | kernel32 | 1 |  |  | OTT | 機能実装 | env.c |  |
| P2 | GetTokenInformation | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | GetWindowsDirectoryW | kernel32 | 1 |  |  |  | 機能実装 | env.c |  |
| P2 | GlobalMemoryStatus | kernel32 | 1 |  |  |  | 機能実装 | heap.c |  |
| P2 | HeapCreate | kernel32 | 1 |  |  | Serum2 | 機能実装 | heap.c |  |
| P2 | HttpAddRequestHeadersW | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | HttpEndRequestW | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | HttpOpenRequestW | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | HttpQueryInfoW | wininet | 1 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P2 | HttpSendRequestExW | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | ImageDirectoryEntryToData | imagehlp | 1 |  |  |  | 機能実装 | module.c |  |
| P2 | InternetConnectW | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | InternetSetOptionW | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | InternetWriteFile | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | IsAccelerator | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | LoadLibraryA | kernel32 | 1 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
| P2 | LresultFromObject | oleacc | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | MsgWaitForMultipleObjectsEx | user32 | 1 |  |  |  | 機能実装 | wait.c |  |
| P2 | OleDraw | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | OleFlushClipboard | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | OleIsCurrentClipboard | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | OleSetMenuDescriptor | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | OpenFileMappingW | kernel32 | 1 |  |  |  | 機能実装 | file.c |  |
| P2 | OpenPrinterW | winspool.drv | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | OpenProcess | kernel32 | 1 |  |  |  | 機能実装 | thread.c |  |
| P2 | OpenProcessToken | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | PathUnExpandEnvStringsW | shlwapi | 1 |  |  |  | 機能実装 | shell.c |  |
| P2 | ProgIDFromCLSID | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | RegDeleteKeyW | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | RegDeleteValueW | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | SHAddToRecentDocs | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHChangeNotifyDeregister | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHChangeNotifyRegister | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SafeArrayAccessData | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayGetElemsize | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayUnaccessData | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SetVolumeLabelW | kernel32 | 1 |  |  |  | スタブ(エラー/無し返却) | file.c |  |
| P2 | ShellExecuteA | shell32 | 1 |  |  | FL64/OTT | スタブ(エラー/無し返却) | shell.c |  |
| P2 | Shell_NotifyIconW | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SignalObjectAndWait | kernel32 | 1 |  |  |  | 機能実装 | wait.c |  |
| P2 | StringFromCLSID | ole32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SuspendThread | kernel32 | 1 |  |  |  | スタブ(エラー/無し返却) | thread.c | カウントのみ (実停止不可) |
| P2 | SystemTimeToFileTime | kernel32 | 1 |  |  | Serum2 | 機能実装 | timer.c |  |
| P2 | TzSpecificLocalTimeToSystemTime | kernel32 | 1 |  |  | Serum2 | 機能実装 | timer.c |  |
| P2 | VariantChangeType | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | WNetEnumResourceW | mpr | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | WNetGetUniversalNameW | mpr | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | WNetOpenEnumW | mpr | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | WaitForMultipleObjects | kernel32 | 1 |  |  |  | 機能実装 | wait.c |  |
| P2 | acmDriverDetailsA | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmDriverEnum | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmDriverOpen | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmFormatChooseW | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmFormatSuggest | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamMessage | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamOpen | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamUnprepareHeader | msacm32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | midiInClose | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInGetErrorTextW | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | midiInOpen | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInReset | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInStart | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInStop | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInUnprepareHeader | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiOutClose | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiOutGetErrorTextW | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | midiOutLongMsg | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiOutOpen | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiOutPrepareHeader | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiOutUnprepareHeader | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | GetOpenFileNameW | comdlg32 | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c | キャンセル扱い (Web ファイル選択は下流) |
| P2 | GetSaveFileNameW | comdlg32 | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P3 | AcquireSRWLockExclusive | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P3 | AcquireSRWLockShared | kernel32 | 0 |  |  | Serum2 | 機能実装 | locks.c |  |
| P3 | AreFileApisANSI | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | CertGetNameStringA | crypt32 | 0 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P3 | CloseThreadpoolWork | kernel32 | 0 |  |  | Serum2 | 機能実装 | thread.c |  |
| P3 | CoCreateGuid | ole32 | 0 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P3 | CompareStringEx | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | str.c |  |
| P3 | CreateFileA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | CreateFileMappingA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | CreateIoCompletionPort | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | thread.c |  |
| P3 | CreateMutexW | kernel32 | 0 |  |  | Serum2 | 機能実装 | wait.c |  |
| P3 | CreateSymbolicLinkW | kernel32 | 0 |  |  |  | スタブ(エラー/無し返却) | file.c |  |
| P3 | CreateThreadpoolWork | kernel32 | 0 |  |  | Serum2 | 機能実装 | thread.c |  |
| P3 | CryptAcquireContextA | advapi32 | 0 |  |  | Serum2 | 機能実装 | crypt.c |  |
| P3 | CryptCreateHash | advapi32 | 0 |  |  | Serum2 | 機能実装 | crypt.c |  |
| P3 | CryptDecodeObject | crypt32 | 0 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P3 | CryptDestroyHash | advapi32 | 0 |  |  | Serum2 | 機能実装 | crypt.c |  |
| P3 | CryptGetHashParam | advapi32 | 0 |  |  | Serum2 | 機能実装 | crypt.c |  |
| P3 | CryptHashData | advapi32 | 0 |  |  | Serum2 | 機能実装 | crypt.c |  |
| P3 | DeleteFileA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | DeviceIoControl | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P3 | ExtractAssociatedIconW | shell32 | 0 |  |  | OTT | スタブ(エラー/無し返却) | shell.c |  |
| P3 | FindResourceA | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
| P3 | FlsAlloc | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | teb.c |  |
| P3 | FlsFree | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | teb.c |  |
| P3 | FlsGetValue | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | teb.c |  |
| P3 | FlsSetValue | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | teb.c |  |
| P3 | FlushViewOfFile | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | FormatMessageA | kernel32 | 0 |  |  | Serum2 | 機能実装 | locale.c |  |
| P3 | FreeLibraryAndExitThread | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | thread.c |  |
| P3 | FreeLibraryWhenCallbackReturns | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | thread.c |  |
| P3 | GetDiskFreeSpaceA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | GetFileAttributesA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | GetFullPathNameA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | GetHGlobalFromStream | ole32 | 0 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P3 | GetLocaleInfoEx | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | locale.c |  |
| P3 | GetModuleFileNameA | kernel32 | 0 |  |  | Serum2 | 機能実装 | module.c |  |
| P3 | GetModuleHandleA | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
| P3 | GetQueuedCompletionStatus | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | thread.c |  |
| P3 | GetSystemTime | kernel32 | 0 |  |  | Serum2 | 機能実装 | timer.c |  |
| P3 | GetTempPathA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | GetTickCount64 | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | timer.c |  |
| P3 | GetTimeFormatW | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | timer.c |  |
| P3 | GetTimeZoneInformationForYear | kernel32 | 0 |  |  |  | 機能実装 | timer.c |  |
| P3 | GetUserPreferredUILanguages | kernel32 | 0 |  |  |  | 機能実装 | locale.c |  |
| P3 | HeapCompact | kernel32 | 0 |  |  | Serum2 | 機能実装 | heap.c |  |
| P3 | HeapValidate | kernel32 | 0 |  |  | Serum2 | 機能実装 | heap.c |  |
| P3 | InitOnceBeginInitialize | kernel32 | 0 |  |  | Serum2 | 機能実装 | locks.c |  |
| P3 | InitOnceComplete | kernel32 | 0 |  |  | Serum2 | 機能実装 | locks.c |  |
| P3 | InitializeConditionVariable | kernel32 | 0 |  |  | OTT | 機能実装 | locks.c |  |
| P3 | InitializeSRWLock | kernel32 | 0 |  |  | OTT | 機能実装 | locks.c |  |
| P3 | InterlockedPushEntrySList | kernel32 | 0 |  |  | Serum2 | 機能実装 | locks.c |  |
| P3 | InternetOpenA | wininet | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P3 | InternetOpenUrlA | wininet | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P3 | InternetSetStatusCallbackW | wininet | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P3 | IsWow64Process | kernel32 | 0 |  |  |  | スタブ(エラー/無し返却) | env.c |  |
| P3 | LockFile | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P3 | LockFileEx | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P3 | MoveFileExW | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | NormalizeString | kernel32 | 0 |  |  |  | 機能実装 | str.c |  |
| P3 | OutputDebugStringA | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | env.c |  |
| P3 | PropVariantClear | ole32 | 0 |  |  |  | 機能実装 | ole.c |  |
| P3 | PropVariantToBooleanWithDefault | propsys | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P3 | PropVariantToFileTime | propsys | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P3 | PropVariantToStringWithDefault | propsys | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P3 | PropVariantToVariant | propsys | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P3 | ReadDirectoryChangesW | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P3 | RegDeleteKeyExW | advapi32 | 0 |  |  |  | 機能実装 | reg.c |  |
| P3 | ReleaseSRWLockExclusive | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P3 | ReleaseSRWLockShared | kernel32 | 0 |  |  | Serum2 | 機能実装 | locks.c |  |
| P3 | SHCreateDirectoryExW | shell32 | 0 |  |  | Serum2 | 機能実装 | shell.c |  |
| P3 | SHCreateItemFromParsingName | shell32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | shell.c |  |
| P3 | SHCreateStreamOnFileEx | shlwapi | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | shell.c |  |
| P3 | SHGetKnownFolderPath | shell32 | 0 |  |  | FreshAir/Serum2 | 機能実装 | shell.c |  |
| P3 | SHGetSpecialFolderPathW | shell32 | 0 |  |  | OTT | 機能実装 | shell.c |  |
| P3 | SHOpenFolderAndSelectItems | shell32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | shell.c |  |
| P3 | SetThreadAffinityMask | kernel32 | 0 |  |  | OTT | 機能実装 | thread.c |  |
| P3 | ShellExecuteExA | shell32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | shell.c |  |
| P3 | SleepConditionVariableCS | kernel32 | 0 |  |  | OTT | 機能実装 | locks.c |  |
| P3 | SleepConditionVariableSRW | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P3 | SubmitThreadpoolWork | kernel32 | 0 |  |  | Serum2 | 機能実装 | thread.c |  |
| P3 | TerminateThread | kernel32 | 0 |  |  | OTT | スタブ(エラー/無し返却) | thread.c | 状態のみ完了扱い |
| P3 | TryAcquireSRWLockExclusive | kernel32 | 0 |  |  | Serum2 | 機能実装 | locks.c |  |
| P3 | TryEnterCriticalSection | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P3 | UnlockFile | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P3 | UnlockFileEx | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P3 | UuidCreate | rpcrt4 | 0 |  |  |  | 機能実装 | ole.c |  |
| P3 | VariantToPropVariant | propsys | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P3 | WSACleanup | ws2_32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P3 | WSAGetLastError | ws2_32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P3 | WSAPoll | ws2_32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P3 | WSAStartup | ws2_32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c | WSASYSNOTREADY (ネットワーク無し) |
| P3 | WTSUnRegisterSessionNotification | wtsapi32 | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P3 | WakeAllConditionVariable | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P3 | WakeConditionVariable | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P3 | accept | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |
| P3 | bind | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |
| P3 | closesocket | ws2_32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P3 | getsockname | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |
| P3 | listen | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |
| P3 | lstrcmpA | kernel32 | 0 |  |  | FL64 | 機能実装 | str.c |  |
| P3 | ntohs | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |
| P3 | ord1 | d2d1 | 0 |  |  | Serum2 | 序数 import (未解決) |  |  |
| P3 | ord12 | shlwapi | 0 |  |  | Serum2 | 序数 import (同定・実装済み) |  |  |
| P3 | ord155 | shell32 | 0 |  |  | Serum2 | 序数 import (同定・実装済み) |  |  |
| P3 | ord190 | shell32 | 0 |  |  | Serum2 | 序数 import (同定・実装済み) |  |  |
| P3 | ord219 | shlwapi | 0 |  |  | Serum2 | 序数 import (同定・実装済み) |  |  |
| P3 | ord74 | shell32 | 0 |  |  | OTT | 序数 import (同定・実装済み) |  |  |
| P3 | recv | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |
| P3 | send | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |
| P3 | socket | ws2_32 | 0 |  |  | Serum2 | libc 解決 |  |  |

## 下流で実体化が必要な「口」(スタブ→実装の昇格候補)

| 項目 | 現状 | 昇格に必要なもの | 想定担当 |
|---|---|---|---|
| LoadLibrary/GetProcAddress の実体 | モジュール表+フック | wasm モジュール連結 (hostbridge) が `shimx_set_load_hook`/`shimx_proc_register` を呼ぶ | hostbridge |
| VFS (Emscripten FS) マウント | `shimx_set_path_mapper` | IDBFS/WORKERFS 等のマウント構成と Win パス写像規約の確定 | runtime |
| ShellExecute / ファイル選択 | フック/キャンセル | ブラウザの `window.open` / File System Access API 接続 | gui |
| MIDI (winmm midi*) | デバイス 0 台 (weak) | Web MIDI 接続 (強定義で上書き) | audio/midi |
| SEH 実巻き戻し | fail-fast | lift 側 (.pdata/UHANDLER 8,021) で setjmp/例外タグへ変換、`shimx_set_raise_hook` に接続 | lift |
| COM オブジェクトの関数ポインタ | Win64 vtable 8B スロットに wasm 関数ポインタ | lifted コードの間接呼出し規約ブリッジ (i64↔i32 署名) | hostbridge |
| 暗号ハッシュ (advapi32 Crypt*) | 常に失敗 | MD5/SHA を実装 (Serum2 ライセンス系のみ。FL 対象外) | plugins |
| レジストリ永続化 | `shimx_reg_export_text/import_text` | IndexedDB への保存/復元 | runtime |

## SHX-T9 (#177) 実機 DllMain 経路の残

結論: DllMain closure は未完。逐次起動の停止要因は lift 側 #232 (`_UStrAsg` OOB)。測定値は `tools/shimx/REPORT_SHX-T9.md` §2・§4 が正本。

| 未解決項目 | 起票先 |
|---|---|
| GetProcAddress 名前空 miss (非 GUI) | P1/P2 追加候補 (`tools/shimx/REPORT_SHX-T9.md` §2.1) |
| GetProcAddress GUI 系 miss | tools/gui |
| GetProcAddress 序数 miss | R1 (`tools/shimx/REPORT_R1-R8.md`) |
| LoadLibrary 失敗 (Msctf / avrt / PowrProf) | R4 (`tools/shimx/REPORT_R1-R8.md`) |
| EnterCriticalSection (NULL) の shimx fail-fast | R7 (`tools/shimx/REPORT_R1-R8.md`) |
| LoadStringW fail-fast (plain 逐次起動) | tools/gui |
| DllMain closure 完走 | #232 (CLOSED・停止点のみ記録) |
| survey unit 160 以降の挙動 | #773 |
