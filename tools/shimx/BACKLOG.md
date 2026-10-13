# BACKLOG — shimx 実装バックログ (優先度順, 実測)

優先度の定義 (必須性→使用頻度): **P0** = M11 init closure が declare する API または OTT undefined 24 種 / **P1** = FLEngine 静的呼出サイト ≥10 または 3 プラグイン以上が使用 / **P2** = FLEngine 静的 import のその他 / **P3** = delay-load・プラグイン専用 / **X** = 他担当 DLL (対象外)。
呼出サイト数 = FLEngine_x64.dll の `jmp [IAT]` thunk への call/jmp/lea 参照数 (静的, `scripts/import_scan.py`)。

## 集計

| 優先 | API 数 | 機能実装 | スタブ | libc | 序数(同定・実装済) | 序数(未解決) | 未実装 | 対象外 |
|---|---|---|---|---|---|---|---|---|
| P0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P1 | 124 | 111 | 13 | 0 | 0 | 0 | 0 | 0 |
| P2 | 267 | 158 | 108 | 1 | 0 | 0 | 0 | 0 |
| P3 | 117 | 68 | 35 | 8 | 5 | 1 | 0 | 0 |
| X | 544 | 0 | 0 | 0 | 0 | 0 | 0 | 544 |

## 一覧 (P0〜P3。X は件数のみ — 全件は data/inventory.csv)

| 優先 | API | DLL | 呼出サイト | M11 | OTT | プラグイン | 状態 | 実装 | 備考 |
|---|---|---|---|---|---|---|---|---|---|
| P1 | LeaveCriticalSection | kernel32 | 799 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | EnterCriticalSection | kernel32 | 699 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c | Win64 40B レイアウトを直接実装 |
| P1 | MulDiv | kernel32 | 164 |  |  |  | 機能実装 | str.c |  |
| P1 | IsEqualGUID | ole32 | 114 |  |  |  | 機能実装 | ole.c |  |
| P1 | FreeLibrary | kernel32 | 106 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P1 | RegCloseKey | advapi32 | 99 |  |  | FL64/Serum2 | 機能実装 | reg.c |  |
| P1 | timeGetTime | winmm | 79 |  |  | OTT | 機能実装 | timer.c | M4 継承 (emscripten_get_now) |
| P1 | CloseHandle | kernel32 | 73 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | handles.c |  |
| P1 | DeleteCriticalSection | kernel32 | 65 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | InitializeCriticalSection | kernel32 | 65 |  |  | OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | GetLastError | kernel32 | 61 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | GetCurrentThreadId | kernel32 | 51 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | thread.c |  |
| P1 | LoadLibraryW | kernel32 | 48 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c | モジュール表+load フック。実体ロードは hostbridge |
| P1 | VariantInit | oleaut32 | 48 |  |  |  | 機能実装 | ole.c |  |
| P1 | RegQueryValueExW | advapi32 | 46 |  |  | FL64/Serum2 | 機能実装 | reg.c |  |
| P1 | GlobalUnlock | kernel32 | 44 |  |  | OTT/Serum2 | 機能実装 | heap.c | M4 互換 (ロック済みなら TRUE) |
| P1 | GetTickCount | kernel32 | 42 |  |  | OTT/Serum2 | 機能実装 | timer.c |  |
| P1 | GetModuleHandleW | kernel32 | 37 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P1 | CopyFileW | kernel32 | 35 |  |  |  | 機能実装 | file.c |  |
| P1 | Sleep | kernel32 | 33 |  |  | OTT/Serum2 | 機能実装 | timer.c |  |
| P1 | GetCurrentProcess | kernel32 | 31 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | thread.c |  |
| P1 | DeleteFileW | kernel32 | 28 |  |  | OTT/Serum2 | 機能実装 | file.c |  |
| P1 | CoTaskMemFree | ole32 | 27 |  |  | FreshAir/Serum2 | 機能実装 | ole.c |  |
| P1 | GlobalLock | kernel32 | 27 |  |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | GetComputerNameExW | kernel32 | 26 |  |  |  | 機能実装 | env.c |  |
| P1 | QueryPerformanceCounter | kernel32 | 25 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | timer.c |  |
| P1 | RegOpenKeyExA | advapi32 | 25 |  |  | Serum2 | 機能実装 | reg.c |  |
| P1 | CompareStringW | kernel32 | 24 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | GetModuleFileNameW | kernel32 | 22 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P1 | MoveFileW | kernel32 | 20 |  |  |  | 機能実装 | file.c |  |
| P1 | UnmapViewOfFile | kernel32 | 20 |  |  | Serum2 | 機能実装 | file.c |  |
| P1 | SetLastError | kernel32 | 19 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | GlobalAlloc | kernel32 | 18 |  |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | GlobalFree | kernel32 | 18 |  |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | ReleaseStgMedium | ole32 | 18 |  |  |  | 機能実装 | ole.c |  |
| P1 | CreateEventW | kernel32 | 17 |  |  | FreshAir/OTT | 機能実装 | wait.c |  |
| P1 | SetEvent | kernel32 | 17 |  |  | FreshAir/OTT | 機能実装 | wait.c |  |
| P1 | ShellExecuteW | shell32 | 17 |  |  | Serum2 | スタブ(エラー/無し返却) | shell.c | shimx_set_shell_execute_hook 経由 |
| P1 | WaitForSingleObject | kernel32 | 16 |  |  | OTT/Serum2 | 機能実装 | wait.c |  |
| P1 | CreateFileW | kernel32 | 15 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c | Win→FS パス写像 + 大小無視再探索 |
| P1 | SetErrorMode | kernel32 | 15 |  |  |  | スタブ(エラー/無し返却) | env.c |  |
| P1 | CoCreateInstance | ole32 | 14 |  |  | OTT/Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P1 | RegOpenKeyExW | advapi32 | 14 |  |  | FL64 | 機能実装 | reg.c | メモリ内レジストリ |
| P1 | GetCurrentProcessId | kernel32 | 13 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | thread.c |  |
| P1 | GetLocaleInfoW | kernel32 | 13 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c | en-US 固定データ (LCID 名のみ数種) |
| P1 | GetFileAttributesW | kernel32 | 12 |  |  | FL64/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetProcAddress | kernel32 | 12 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c | 組込み表 (proctable) + 外部フック。未知名は NULL |
| P1 | GetStdHandle | kernel32 | 11 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | MultiByteToWideChar | kernel32 | 11 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c | CP 1252/437近似/Latin1/ASCII/UTF-8。DBCS (932 等) は ERROR_INVALID_PARAMETER |
| P1 | OutputDebugStringW | kernel32 | 11 |  |  | OTT/Serum2 | スタブ(エラー/無し返却) | env.c |  |
| P1 | LocalFree | kernel32 | 10 |  |  | FL64/Serum2 | 機能実装 | heap.c |  |
| P1 | WideCharToMultiByte | kernel32 | 9 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | WriteFile | kernel32 | 9 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetTempPathW | kernel32 | 8 |  |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | FileTimeToSystemTime | kernel32 | 6 |  |  | FL64/FreshAir/Serum2 | 機能実装 | timer.c |  |
| P1 | FindClose | kernel32 | 6 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetACP | kernel32 | 5 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | RaiseException | kernel32 | 5 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c | VEH→SEH frame 鎖 (longjmp 捕捉)→UEF→fail-fast (継続可能例外のみ復帰) |
| P1 | GetCurrentDirectoryW | kernel32 | 4 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetTimeZoneInformation | kernel32 | 4 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | timer.c |  |
| P1 | TlsGetValue | kernel32 | 4 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | FindNextFileW | kernel32 | 3 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetCPInfo | kernel32 | 3 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | GetCommandLineW | kernel32 | 3 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | GetDriveTypeW | kernel32 | 3 |  |  | FL64/FreshAir/Serum2 | 機能実装 | file.c |  |
| P1 | GetProcessHeap | kernel32 | 3 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | HeapFree | kernel32 | 3 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | IsValidLocale | kernel32 | 3 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c |  |
| P1 | ReadFile | kernel32 | 3 |  |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | SetEndOfFile | kernel32 | 3 |  |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | ExitProcess | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c | exit hook + exit() |
| P1 | GetFileInformationByHandle | kernel32 | 2 |  |  | FL64/FreshAir/Serum2 | 機能実装 | file.c |  |
| P1 | GetFileType | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetFullPathNameW | kernel32 | 2 |  |  | FL64/FreshAir/Serum2 | 機能実装 | file.c |  |
| P1 | GetUserDefaultLCID | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c |  |
| P1 | HeapAlloc | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | LCMapStringW | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | TerminateProcess | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | TlsSetValue | kernel32 | 2 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | EnumSystemLocalesW | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locale.c |  |
| P1 | GetConsoleOutputCP | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | ini.c |  |
| P1 | GetOEMCP | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | GetStartupInfoW | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | IsDebuggerPresent | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | env.c |  |
| P1 | LoadLibraryExW | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P1 | RtlUnwindEx | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c | SEH frame 巻き戻し (frame 未登録は fail-fast) |
| P1 | SetEnvironmentVariableW | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | SystemTimeToTzSpecificLocalTime | kernel32 | 1 |  |  | FL64/FreshAir/Serum2 | 機能実装 | timer.c |  |
| P1 | TlsAlloc | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | TlsFree | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | UnhandledExceptionFilter | kernel32 | 1 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c |  |
| P1 | DecodePointer | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | EncodePointer | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | teb.c |  |
| P1 | FindFirstFileExW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | FlushFileBuffers | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | FreeEnvironmentStringsW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | GetCommandLineA | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | GetConsoleMode | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | ini.c |  |
| P1 | GetEnvironmentStringsW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c |  |
| P1 | GetFileSizeEx | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | GetModuleHandleExW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | module.c |  |
| P1 | GetStringTypeW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | GetSystemTimeAsFileTime | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | timer.c |  |
| P1 | HeapReAlloc | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | HeapSize | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | heap.c |  |
| P1 | InitializeCriticalSectionAndSpinCount | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | InitializeCriticalSectionEx | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | InitializeSListHead | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | InterlockedFlushSList | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | 機能実装 | locks.c |  |
| P1 | IsProcessorFeaturePresent | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | env.c | FASTFAIL(23)/AVX 系は FALSE |
| P1 | IsValidCodePage | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | LCMapStringEx | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | str.c |  |
| P1 | PeekNamedPipe | kernel32 | 0 |  |  | FL64/FreshAir/Serum2 | スタブ(エラー/無し返却) | file.c |  |
| P1 | ReadConsoleW | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | ini.c |  |
| P1 | RtlCaptureContext | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c |  |
| P1 | RtlLookupFunctionEntry | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c |  |
| P1 | RtlPcToFileHeader | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c |  |
| P1 | RtlUnwind | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c | SEH frame 巻き戻し (frame 未登録は fail-fast) |
| P1 | RtlVirtualUnwind | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | スタブ(エラー/無し返却) | seh.c |  |
| P1 | SetFilePointerEx | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | SetStdHandle | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | file.c |  |
| P1 | SetUnhandledExceptionFilter | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | seh.c |  |
| P1 | WaitForSingleObjectEx | kernel32 | 0 |  |  | FreshAir/OTT/Serum2 | 機能実装 | wait.c |  |
| P1 | WriteConsoleW | kernel32 | 0 |  |  | FL64/FreshAir/OTT/Serum2 | 機能実装 | ini.c |  |
| P2 | GetThreadLocale | kernel32 | 9 |  |  |  | 機能実装 | locale.c |  |
| P2 | InternetCloseHandle | wininet | 9 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P2 | MapViewOfFile | kernel32 | 9 |  |  | Serum2 | 機能実装 | file.c |  |
| P2 | SetProcessAffinityMask | kernel32 | 9 |  |  |  | スタブ(エラー/無し返却) | thread.c |  |
| P2 | CharNextW | user32 | 8 |  |  |  | 機能実装 | str.c |  |
| P2 | GetFileAttributesExW | kernel32 | 8 |  |  | OTT/Serum2 | 機能実装 | file.c |  |
| P2 | GlobalSize | kernel32 | 8 |  |  | OTT/Serum2 | 機能実装 | heap.c |  |
| P2 | QueryPerformanceFrequency | kernel32 | 8 |  |  | OTT/Serum2 | 機能実装 | timer.c |  |
| P2 | ResetEvent | kernel32 | 8 |  |  | FreshAir/OTT | 機能実装 | wait.c |  |
| P2 | SetFileAttributesW | kernel32 | 8 |  |  |  | 機能実装 | file.c |  |
| P2 | CoUninitialize | ole32 | 7 |  |  |  | 機能実装 | ole.c |  |
| P2 | CreateFileMappingW | kernel32 | 7 |  |  | Serum2 | 機能実装 | file.c | 共有バッファ方式 (Unmap/Flush で書戻し) |
| P2 | GetVersionExW | kernel32 | 7 |  |  | OTT/Serum2 | 機能実装 | env.c | 10.0.19045 (shimx_set_version で変更) |
| P2 | VerSetConditionMask | kernel32 | 7 |  |  |  | 機能実装 | env.c |  |
| P2 | VirtualFree | kernel32 | 7 |  |  |  | 機能実装 | heap.c |  |
| P2 | VirtualQuery | kernel32 | 7 |  |  |  | 機能実装 | heap.c |  |
| P2 | memset | api-ms-win-crt-string-l1-1-0 | 7 |  |  |  | libc 解決 |  |  |
| P2 | FindFirstFileW | kernel32 | 6 |  |  | Serum2 | 機能実装 | file.c | 先頭で全列挙→大小無視ソート |
| P2 | GetSystemInfo | kernel32 | 6 |  |  | Serum2 | 機能実装 | env.c |  |
| P2 | LocalAlloc | kernel32 | 6 |  |  | FL64 | 機能実装 | heap.c |  |
| P2 | RegisterDragDrop | ole32 | 6 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P2 | RevokeDragDrop | ole32 | 6 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P2 | SetFilePointer | kernel32 | 6 |  |  | OTT/Serum2 | 機能実装 | file.c |  |
| P2 | SysFreeString | oleaut32 | 6 |  |  |  | 機能実装 | ole.c |  |
| P2 | VirtualAlloc | kernel32 | 6 |  |  |  | 機能実装 | heap.c | weak (m11_rt.c 強定義が優先) |
| P2 | VirtualProtect | kernel32 | 6 |  |  | Serum2 | 機能実装 | heap.c |  |
| P2 | CreateStreamOnHGlobal | ole32 | 5 |  |  | OTT/Serum2 | 機能実装 | ole.c | IStream (Win64 vtable 8B スロット) |
| P2 | FileTimeToLocalFileTime | kernel32 | 5 |  |  |  | 機能実装 | timer.c |  |
| P2 | FormatMessageW | kernel32 | 5 |  |  | OTT/Serum2 | 機能実装 | locale.c |  |
| P2 | GetFileSize | kernel32 | 5 |  |  | Serum2 | 機能実装 | file.c |  |
| P2 | GetLocalTime | kernel32 | 5 |  |  |  | 機能実装 | timer.c |  |
| P2 | HttpQueryInfoA | wininet | 5 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | OleSetClipboard | ole32 | 5 |  |  | Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P2 | OleUninitialize | ole32 | 5 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P2 | SetCurrentDirectoryW | kernel32 | 5 |  |  | FL64 | 機能実装 | file.c |  |
| P2 | SetDllDirectoryW | kernel32 | 5 |  |  |  | 機能実装 | module.c |  |
| P2 | SetPriorityClass | kernel32 | 5 |  |  | OTT | スタブ(エラー/無し返却) | thread.c |  |
| P2 | CertGetNameStringW | crypt32 | 4 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | CoGetInterfaceAndReleaseStream | ole32 | 4 |  |  |  | 機能実装 | ole.c |  |
| P2 | CoInitialize | ole32 | 4 |  |  |  | 機能実装 | ole.c | スレッド毎カウント |
| P2 | CoMarshalInterThreadInterfaceInStream | ole32 | 4 |  |  |  | 機能実装 | ole.c |  |
| P2 | CryptMsgGetParam | crypt32 | 4 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | EnumCalendarInfoW | kernel32 | 4 |  |  |  | 機能実装 | locale.c |  |
| P2 | EnumPrintersW | winspool.drv | 4 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | FileTimeToDosDateTime | kernel32 | 4 |  |  |  | 機能実装 | timer.c |  |
| P2 | FindResourceW | kernel32 | 4 |  |  | OTT | 機能実装 | module.c |  |
| P2 | GetEnvironmentVariableW | kernel32 | 4 |  |  |  | 機能実装 | env.c |  |
| P2 | GetPrivateProfileStringW | kernel32 | 4 |  |  |  | 機能実装 | ini.c |  |
| P2 | GetVersion | kernel32 | 4 |  |  |  | 機能実装 | env.c |  |
| P2 | ILFree | shell32 | 4 |  |  |  | 機能実装 | shell.c |  |
| P2 | OleInitialize | ole32 | 4 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P2 | SHGetDesktopFolder | shell32 | 4 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SafeArrayPtrOfIndex | oleaut32 | 4 |  |  |  | 機能実装 | ole.c |  |
| P2 | SetThreadExecutionState | kernel32 | 4 |  |  |  | スタブ(エラー/無し返却) | thread.c |  |
| P2 | VerQueryValueW | version | 4 |  |  |  | 機能実装 | shell.c |  |
| P2 | WinVerifyTrust | wintrust | 4 |  |  | FL64 | スタブ(エラー/無し返却) | net.c | NOSIGNATURE (shimx_set_trust_ok で成功化) |
| P2 | WritePrivateProfileStringW | kernel32 | 4 |  |  |  | 機能実装 | ini.c |  |
| P2 | midiOutGetDevCapsW | winmm | 4 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiOutGetNumDevs | winmm | 4 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | CreateILockBytesOnHGlobal | ole32 | 3 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | CreateThread | kernel32 | 3 |  |  | OTT/Serum2 | 機能実装 | thread.c | CREATE_SUSPENDED 対応/threadId 修正 (M4 差分) |
| P2 | ExpandEnvironmentStringsW | kernel32 | 3 |  |  |  | 機能実装 | env.c |  |
| P2 | GetCurrentThread | kernel32 | 3 |  |  | OTT | 機能実装 | thread.c |  |
| P2 | GetExitCodeProcess | kernel32 | 3 |  |  |  | 機能実装 | thread.c |  |
| P2 | GetFileVersionInfoSizeW | version | 3 |  |  |  | 機能実装 | shell.c |  |
| P2 | GetFileVersionInfoW | version | 3 |  |  |  | 機能実装 | shell.c | 合成版情報 (FL 26.1.7.5653) |
| P2 | GetProcessAffinityMask | kernel32 | 3 |  |  |  | 機能実装 | thread.c |  |
| P2 | GetSystemDefaultUILanguage | kernel32 | 3 |  |  |  | 機能実装 | locale.c |  |
| P2 | GetTempFileNameW | kernel32 | 3 |  |  |  | 機能実装 | file.c |  |
| P2 | GetVolumeInformationW | kernel32 | 3 |  |  |  | 機能実装 | file.c |  |
| P2 | GlobalAddAtomW | kernel32 | 3 |  |  |  | 機能実装 | env.c |  |
| P2 | GlobalDeleteAtom | kernel32 | 3 |  |  |  | 機能実装 | env.c |  |
| P2 | ImageRvaToVa | imagehlp | 3 |  |  |  | 機能実装 | module.c |  |
| P2 | InternetOpenW | wininet | 3 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | InternetReadFile | wininet | 3 |  |  | Serum2 | スタブ(エラー/無し返却) | net.c |  |
| P2 | MsgWaitForMultipleObjects | user32 | 3 |  |  |  | 機能実装 | wait.c | weak。kernel object 待ちのみ (メッセージ無し) |
| P2 | OleGetClipboard | ole32 | 3 |  |  | Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P2 | RegEnumKeyExW | advapi32 | 3 |  |  |  | 機能実装 | reg.c |  |
| P2 | SHFileOperationW | shell32 | 3 |  |  | Serum2 | 機能実装 | shell.c |  |
| P2 | SHGetFolderPathW | shfolder | 3 |  |  |  | 機能実装 | shell.c |  |
| P2 | SHGetPathFromIDListW | shell32 | 3 |  |  |  | 機能実装 | shell.c |  |
| P2 | SafeArrayGetElement | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayGetLBound | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayGetUBound | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayPutElement | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | SetThreadErrorMode | kernel32 | 3 |  |  |  | スタブ(エラー/無し返却) | env.c |  |
| P2 | ShellExecuteExW | shell32 | 3 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | StgCreateDocfileOnILockBytes | ole32 | 3 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | SwitchToThread | kernel32 | 3 |  |  |  | 機能実装 | timer.c |  |
| P2 | SysAllocStringLen | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | VariantClear | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | VariantCopy | oleaut32 | 3 |  |  |  | 機能実装 | ole.c |  |
| P2 | VerifyVersionInfoW | kernel32 | 3 |  |  |  | 機能実装 | env.c |  |
| P2 | WaitForMultipleObjectsEx | kernel32 | 3 |  |  |  | 機能実装 | wait.c |  |
| P2 | acmMetrics | msacm32 | 3 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | lstrlenW | kernel32 | 3 |  |  |  | 機能実装 | str.c |  |
| P2 | midiInGetNumDevs | winmm | 3 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c | デバイス 0 台 (weak; Web MIDI は下流) |
| P2 | CertFindCertificateInStore | crypt32 | 2 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | CertFreeCertificateContext | crypt32 | 2 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | CharLowerBuffW | user32 | 2 |  |  |  | 機能実装 | str.c |  |
| P2 | CharUpperBuffW | user32 | 2 |  |  |  | 機能実装 | str.c |  |
| P2 | CharUpperW | user32 | 2 |  |  | Serum2 | 機能実装 | str.c | weak (tools/gui が上書き可) |
| P2 | ClosePrinter | winspool.drv | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | CoTaskMemAlloc | ole32 | 2 |  |  |  | 機能実装 | ole.c |  |
| P2 | CreateDirectoryW | kernel32 | 2 |  |  | OTT | 機能実装 | file.c |  |
| P2 | CreateProcessW | kernel32 | 2 |  |  |  | スタブ(エラー/無し返却) | env.c | 常に ERROR_FILE_NOT_FOUND |
| P2 | CryptQueryObject | crypt32 | 2 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | DoDragDrop | ole32 | 2 |  |  | OTT/Serum2 | スタブ(エラー/無し返却) | ole.c |  |
| P2 | DocumentPropertiesW | winspool.drv | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | DosDateTimeToFileTime | kernel32 | 2 |  |  |  | 機能実装 | timer.c |  |
| P2 | DragAcceptFiles | shell32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | DragQueryFileW | shell32 | 2 |  |  | OTT/Serum2 | スタブ(エラー/無し返却) | shell.c |  |
| P2 | DuplicateHandle | kernel32 | 2 |  |  |  | 機能実装 | handles.c |  |
| P2 | GetActiveObject | oleaut32 | 2 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | GetDateFormatW | kernel32 | 2 |  |  | FL64/Serum2 | 機能実装 | timer.c |  |
| P2 | GetDiskFreeSpaceW | kernel32 | 2 |  |  | Serum2 | 機能実装 | file.c |  |
| P2 | GetLogicalDrives | kernel32 | 2 |  |  |  | 機能実装 | file.c |  |
| P2 | GetThreadPriority | kernel32 | 2 |  |  |  | 機能実装 | thread.c |  |
| P2 | GetUserDefaultUILanguage | kernel32 | 2 |  |  |  | 機能実装 | locale.c |  |
| P2 | GlobalFindAtomW | kernel32 | 2 |  |  |  | 機能実装 | env.c |  |
| P2 | HeapDestroy | kernel32 | 2 |  |  | Serum2 | 機能実装 | heap.c |  |
| P2 | ILCreateFromPathW | shell32 | 2 |  |  |  | 機能実装 | shell.c |  |
| P2 | ImageNtHeader | imagehlp | 2 |  |  |  | 機能実装 | module.c |  |
| P2 | InternetGetLastResponseInfoW | wininet | 2 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | InternetOpenUrlW | wininet | 2 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | IsBadWritePtr | kernel32 | 2 |  |  |  | 機能実装 | heap.c |  |
| P2 | IsDBCSLeadByteEx | kernel32 | 2 |  |  |  | 機能実装 | str.c |  |
| P2 | LocalFileTimeToFileTime | kernel32 | 2 |  |  |  | 機能実装 | timer.c |  |
| P2 | RegCreateKeyExW | advapi32 | 2 |  |  |  | 機能実装 | reg.c |  |
| P2 | RegEnumValueW | advapi32 | 2 |  |  |  | 機能実装 | reg.c |  |
| P2 | RemoveDirectoryW | kernel32 | 2 |  |  | OTT/Serum2 | 機能実装 | file.c |  |
| P2 | ResumeThread | kernel32 | 2 |  |  |  | 機能実装 | thread.c |  |
| P2 | SHAppBarMessage | shell32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHGetFileInfoW | shell32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHGetMalloc | shell32 | 2 |  |  |  | 機能実装 | ole.c | IMalloc (Win64 vtable) |
| P2 | SHGetSpecialFolderLocation | shell32 | 2 |  |  |  | 機能実装 | shell.c |  |
| P2 | SafeArrayCreate | oleaut32 | 2 |  |  |  | 機能実装 | ole.c |  |
| P2 | SetFileTime | kernel32 | 2 |  |  | Serum2 | 機能実装 | file.c |  |
| P2 | SetThreadLocale | kernel32 | 2 |  |  |  | 機能実装 | locale.c |  |
| P2 | WNetCloseEnum | mpr | 2 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | acmDriverClose | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamClose | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamConvert | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamPrepareHeader | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | acmStreamSize | msacm32 | 2 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | midiInAddBuffer | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInGetDevCapsW | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | midiInPrepareHeader | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
| P2 | timeBeginPeriod | winmm | 2 |  |  | OTT | スタブ(エラー/無し返却) | timer.c |  |
| P2 | timeEndPeriod | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | timer.c |  |
| P2 | timeGetDevCaps | winmm | 2 |  |  |  | スタブ(エラー/無し返却) | timer.c |  |
| P2 | AddAtomW | kernel32 | 1 |  |  |  | 機能実装 | env.c |  |
| P2 | AddVectoredExceptionHandler | kernel32 | 1 |  |  |  | 機能実装 | seh.c |  |
| P2 | AssignProcessToJobObject | kernel32 | 1 |  |  |  | スタブ(エラー/無し返却) | env.c |  |
| P2 | CLSIDFromString | ole32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | CertCloseStore | crypt32 | 1 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | ChangeTimerQueueTimer | kernel32 | 1 |  |  |  | 機能実装 | thread.c |  |
| P2 | CharLowerW | user32 | 1 |  |  | Serum2 | 機能実装 | str.c |  |
| P2 | CharNextExA | user32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | CharToOemBuffW | user32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | CoGetClassObject | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | CompareFileTime | kernel32 | 1 |  |  |  | 機能実装 | timer.c |  |
| P2 | CompareStringA | kernel32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | CreateDataAdviseHolder | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | CreateTimerQueueTimer | kernel32 | 1 |  |  |  | 機能実装 | thread.c |  |
| P2 | CryptMsgClose | crypt32 | 1 |  |  | FL64 | スタブ(エラー/無し返却) | net.c |  |
| P2 | DeleteAtom | kernel32 | 1 |  |  |  | 機能実装 | env.c |  |
| P2 | DeleteTimerQueueTimer | kernel32 | 1 |  |  |  | 機能実装 | thread.c |  |
| P2 | DragFinish | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | DragQueryPoint | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | ExitThread | kernel32 | 1 |  |  | OTT/Serum2 | 機能実装 | thread.c |  |
| P2 | FindAtomW | kernel32 | 1 |  |  |  | 機能実装 | env.c |  |
| P2 | FreeResource | kernel32 | 1 |  |  |  | 機能実装 | module.c |  |
| P2 | GetCPInfoExW | kernel32 | 1 |  |  |  | 機能実装 | str.c |  |
| P2 | GetComputerNameW | kernel32 | 1 |  |  |  | 機能実装 | env.c |  |
| P2 | GetConsoleCP | kernel32 | 1 |  |  |  | 機能実装 | ini.c |  |
| P2 | GetDefaultPrinterW | winspool.drv | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | GetErrorInfo | oleaut32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | GetExitCodeThread | kernel32 | 1 |  |  | Serum2 | 機能実装 | thread.c |  |
| P2 | GetLogicalDriveStringsW | kernel32 | 1 |  |  |  | 機能実装 | file.c |  |
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
| P2 | InternetGetConnectedState | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c | FALSE |
| P2 | InternetSetOptionW | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | InternetWriteFile | wininet | 1 |  |  |  | スタブ(エラー/無し返却) | net.c |  |
| P2 | IsAccelerator | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | LoadLibraryA | kernel32 | 1 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
| P2 | LoadResource | kernel32 | 1 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
| P2 | LockResource | kernel32 | 1 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
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
| P2 | PathCleanupSpec | shell32 | 1 |  |  |  | 機能実装 | file.c |  |
| P2 | PathUnExpandEnvStringsW | shlwapi | 1 |  |  |  | 機能実装 | shell.c |  |
| P2 | ProgIDFromCLSID | ole32 | 1 |  |  |  | スタブ(エラー/無し返却) | ole.c |  |
| P2 | QueryDosDeviceW | kernel32 | 1 |  |  |  | 機能実装 | file.c |  |
| P2 | RegDeleteKeyW | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | RegDeleteValueW | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | RegFlushKey | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | RegQueryInfoKeyW | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | RegSetValueExW | advapi32 | 1 |  |  |  | 機能実装 | reg.c |  |
| P2 | SHAddToRecentDocs | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHChangeNotifyDeregister | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHChangeNotifyRegister | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SHGetFolderPathW | shell32 | 1 |  |  |  | 機能実装 | shell.c |  |
| P2 | SafeArrayAccessData | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayGetElemsize | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SafeArrayUnaccessData | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SetThreadPriority | kernel32 | 1 |  |  | OTT | 機能実装 | thread.c | 値保持のみ |
| P2 | SetVolumeLabelW | kernel32 | 1 |  |  |  | スタブ(エラー/無し返却) | file.c |  |
| P2 | ShellExecuteA | shell32 | 1 |  |  | FL64/OTT | スタブ(エラー/無し返却) | shell.c |  |
| P2 | Shell_NotifyIconW | shell32 | 1 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
| P2 | SignalObjectAndWait | kernel32 | 1 |  |  |  | 機能実装 | wait.c |  |
| P2 | SizeofResource | kernel32 | 1 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
| P2 | StringFromCLSID | ole32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SuspendThread | kernel32 | 1 |  |  |  | スタブ(エラー/無し返却) | thread.c | カウントのみ (実停止不可) |
| P2 | SysReAllocStringLen | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | SystemTimeToFileTime | kernel32 | 1 |  |  | Serum2 | 機能実装 | timer.c |  |
| P2 | TzSpecificLocalTimeToSystemTime | kernel32 | 1 |  |  | Serum2 | 機能実装 | timer.c |  |
| P2 | VariantChangeType | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | VariantCopyInd | oleaut32 | 1 |  |  |  | 機能実装 | ole.c |  |
| P2 | VirtualQueryEx | kernel32 | 1 |  |  |  | 機能実装 | heap.c |  |
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
| P2 | midiOutShortMsg | winmm | 1 |  |  |  | スタブ(エラー/無し返却) | midi_conv.c |  |
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
| P3 | GetFinalPathNameByHandleW | kernel32 | 0 |  |  |  | 機能実装 | file.c |  |
| P3 | GetFullPathNameA | kernel32 | 0 |  |  | Serum2 | 機能実装 | file.c |  |
| P3 | GetHGlobalFromStream | ole32 | 0 |  |  | OTT/Serum2 | 機能実装 | ole.c |  |
| P3 | GetLocaleInfoEx | kernel32 | 0 |  |  | FL64/Serum2 | 機能実装 | locale.c |  |
| P3 | GetLogicalProcessorInformation | kernel32 | 0 |  |  |  | 機能実装 | env.c |  |
| P3 | GetModuleFileNameA | kernel32 | 0 |  |  | Serum2 | 機能実装 | module.c |  |
| P3 | GetModuleHandleA | kernel32 | 0 |  |  | OTT/Serum2 | 機能実装 | module.c |  |
| P3 | GetNativeSystemInfo | kernel32 | 0 |  |  | Serum2 | 機能実装 | env.c |  |
| P3 | GetQueuedCompletionStatus | kernel32 | 0 |  |  | Serum2 | スタブ(エラー/無し返却) | thread.c |  |
| P3 | GetSystemDefaultLocaleName | kernel32 | 0 |  |  |  | 機能実装 | locale.c |  |
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
| P3 | LocaleNameToLCID | kernel32 | 0 |  |  |  | 機能実装 | locale.c |  |
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
| P3 | WTSRegisterSessionNotification | wtsapi32 | 0 |  |  |  | スタブ(エラー/無し返却) | shell.c |  |
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
