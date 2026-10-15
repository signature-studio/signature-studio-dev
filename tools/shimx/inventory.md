# 自動生成: `tools/shimx` の export 走査

> **人手編集禁止** (生成元を直す)。本ファイルは測定・抽出結果の**単一の正本**。

# shimx inventory — 実装済み / 未実装 / 対象外 (実測)

## 結論

- **FLEngine_x64.dll 静的 import 738 個のうち shimx 実装 358 (機能 243 + スタブ 115) = 48.5%** (libc 解決の `memset` 込み 48.6%)。
- 他担当 DLL (user32/gdi32/comctl32/opengl32 = tools/gui, dsound = tools/audio) の **379 個を対象外** とすると、担当範囲 359 個に対するカバレッジは **100.0%** (未実装 0)。
- delay-load import 57 個: 実装 23 / 他担当 34 / 未実装 0。
- shimx 公開 API 618 本 (機能 457 + スタブ 161) + 運用フック 79 本。M4 の 53 API は **53/53 を継承** (M4 の unmodified test_main.c が shimx 実装で PASS)。
- M11 init closure (`boot_final2.ll`) の外部参照 557 件: shimx 提供 **182** / GUI・audio 担当 171 / lift 由来 203。非 GUI の Win/CRT は **100% 提供**。
- プラグイン OTT_vst2_win64.dll: import 375 (GUI/audio 除く担当 147) のうち shimx 提供 147、未提供: なし
- プラグイン OTT_vst3_win64.dll: import 380 (GUI/audio 除く担当 151) のうち shimx 提供 151、未提供: なし
- プラグイン Serum2_win64.vst3: import 332 (GUI/audio 除く担当 238) のうち shimx 提供 238、未提供: なし
- プラグイン FreshAir.dll: import 99 (GUI/audio 除く担当 98) のうち shimx 提供 98、未提供: なし
- プラグイン FL64.exe: import 112 (GUI/audio 除く担当 111) のうち shimx 提供 111、未提供: なし
- **OTT undefined 47 種 (M8)**: shimx リンクで **47 → 23 種**。Win/CRT API 24 種は **全て解決** (残 23 は `function_18*` = lift 欠落で shim の対象外)。t1 出力 SHA は baseline と一致。

状態記号: **F** 機能実装 / **S** スタブ (無い・失敗・キャンセルを返す) / **L** libc 解決 / **K** 序数 import (同定・実装済み) / **O** 序数 import (未解決) / **U** 未実装 / **X** 他担当。
全 import の行別データ: `data/inventory.csv`、優先度付き一覧: `BACKLOG.md`、機械可読な集計: `data/coverage.json`。

## 表A: DLL 別カバレッジ (FLEngine 静的 import 738)

| DLL | import 数 | F 機能 | S スタブ | L libc | 他担当 | 序数 | U 未実装 | カバレッジ(担当内) |
|---|---|---|---|---|---|---|---|---|
| user32.dll | 227 | 9 | 0 | 0 | 218 | 0 | 0 | 100% |
| kernel32.dll | 184 | 171 | 13 | 0 | 0 | 0 | 0 | 100% |
| gdi32.dll | 127 | 0 | 0 | 0 | 127 | 0 | 0 | — |
| comctl32.dll | 30 | 0 | 0 | 0 | 30 | 0 | 0 | — |
| ole32.dll | 29 | 15 | 14 | 0 | 0 | 0 | 0 | 100% |
| winmm.dll | 24 | 1 | 23 | 0 | 0 | 0 | 0 | 100% |
| shell32.dll | 22 | 8 | 14 | 0 | 0 | 0 | 0 | 100% |
| oleaut32.dll | 19 | 17 | 2 | 0 | 0 | 0 | 0 | 100% |
| wininet.dll | 15 | 0 | 15 | 0 | 0 | 0 | 0 | 100% |
| advapi32.dll | 14 | 14 | 0 | 0 | 0 | 0 | 0 | 100% |
| msacm32.dll | 14 | 0 | 14 | 0 | 0 | 0 | 0 | 100% |
| crypt32.dll | 7 | 0 | 7 | 0 | 0 | 0 | 0 | 100% |
| winspool.drv | 5 | 0 | 5 | 0 | 0 | 0 | 0 | 100% |
| mpr.dll | 4 | 0 | 4 | 0 | 0 | 0 | 0 | 100% |
| version.dll | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 100% |
| imagehlp.dll | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 100% |
| opengl32.dll | 2 | 0 | 0 | 0 | 2 | 0 | 0 | — |
| comdlg32.dll | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 100% |
| dsound.dll | 2 | 0 | 0 | 0 | 2 | 0 | 0 | — |
| shlwapi.dll | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 100% |
| wintrust.dll | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 100% |
| shfolder.dll | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 100% |
| oleacc.dll | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 100% |
| api-ms-win-crt-string-l1-1-0.dll | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 100% |
| **計** | **738** | **243** | **115** | **1** | **379** | **0** | **0** | **100.0%** |

## 表B: 実装済み API (shimx 公開関数 618 本; 記号 `*` = スタブ, `~` = weak 定義)

| ソース | 本数 | API |
|---|---|---|
| crypt.c | 6 | CryptAcquireContextA CryptCreateHash CryptDestroyHash CryptGetHashParam CryptHashData CryptReleaseContext |
| env.c | 36 | AddAtomW AssignProcessToJobObject* CreateProcessW* DeleteAtom ExitProcess ExpandEnvironmentStringsW FindAtomW FreeEnvironmentStringsW GetCommandLineA GetCommandLineW GetComputerNameExW GetComputerNameW GetEnvironmentStringsW GetEnvironmentVariableW GetLogicalProcessorInformation GetNativeSystemInfo GetStartupInfoW GetSystemDirectoryW GetSystemInfo GetVersion GetVersionExW GetWindowsDirectoryW GlobalAddAtomW GlobalDeleteAtom GlobalFindAtomW IsDebuggerPresent* IsProcessorFeaturePresent IsWow64Process* OutputDebugStringA* OutputDebugStringW* SetEnvironmentVariableW SetErrorMode* SetThreadErrorMode* TerminateProcess VerSetConditionMask VerifyVersionInfoW |
| file.c | 63 | AreFileApisANSI CopyFileW CreateDirectoryW CreateFileA CreateFileMappingA CreateFileMappingW CreateFileW CreateSymbolicLinkW* DeleteFileA DeleteFileW DeviceIoControl* FindClose FindFirstFileExW FindFirstFileW FindNextFileW FlushFileBuffers FlushViewOfFile GetCurrentDirectoryW GetDiskFreeSpaceA GetDiskFreeSpaceW GetDriveTypeW GetFileAttributesA GetFileAttributesExW GetFileAttributesW GetFileInformationByHandle GetFileSize GetFileSizeEx GetFileTime GetFileType GetFinalPathNameByHandleW GetFullPathNameA GetFullPathNameW GetLogicalDriveStringsW GetLogicalDrives GetStdHandle GetTempFileNameW GetTempPathA GetTempPathW GetVolumeInformationW LockFile* LockFileEx* MapViewOfFile MoveFileExW MoveFileW OpenFileMappingW PathCleanupSpec PeekNamedPipe* QueryDosDeviceW ReadDirectoryChangesW* ReadFile RemoveDirectoryW SetCurrentDirectoryW SetEndOfFile SetFileAttributesW SetFilePointer SetFilePointerEx SetFileTime SetStdHandle SetVolumeLabelW* UnlockFile* UnlockFileEx* UnmapViewOfFile WriteFile |
| handles.c | 4 | CloseHandle DuplicateHandle GetHandleInformation SetHandleInformation |
| heap.c | 35 | GetProcessHeap GlobalAlloc GlobalFlags GlobalFree GlobalHandle GlobalLock GlobalMemoryStatus GlobalMemoryStatusEx GlobalReAlloc GlobalSize GlobalUnlock HeapAlloc HeapCompact HeapCreate HeapDestroy HeapFree HeapLock HeapReAlloc HeapSetInformation HeapSize HeapUnlock HeapValidate IsBadReadPtr IsBadWritePtr LocalAlloc LocalFree LocalLock LocalReAlloc LocalSize LocalUnlock VirtualAlloc~ VirtualFree~ VirtualProtect~ VirtualQuery~ VirtualQueryEx~ |
| ini.c | 8 | GetConsoleCP GetConsoleMode* GetConsoleOutputCP GetPrivateProfileIntW GetPrivateProfileStringW ReadConsoleW* WriteConsoleW WritePrivateProfileStringW |
| locale.c | 18 | EnumCalendarInfoW EnumSystemLocalesW FormatMessageA FormatMessageW GetLocaleInfoEx GetLocaleInfoW GetSystemDefaultLocaleName GetSystemDefaultUILanguage GetThreadLocale GetThreadPreferredUILanguages GetThreadUILanguage GetUserDefaultLCID GetUserDefaultUILanguage GetUserPreferredUILanguages IsValidLocale LocaleNameToLCID SetThreadLocale SetThreadPreferredUILanguages |
| locks.c | 44 | AcquireSRWLockExclusive AcquireSRWLockShared DeleteCriticalSection EnterCriticalSection InitOnceBeginInitialize InitOnceComplete InitOnceExecuteOnce InitializeConditionVariable InitializeCriticalSection InitializeCriticalSectionAndSpinCount InitializeCriticalSectionEx InitializeSListHead InitializeSRWLock InterlockedAnd InterlockedCompareExchange InterlockedCompareExchange64 InterlockedCompareExchangePointer InterlockedDecrement InterlockedDecrement64 InterlockedExchange InterlockedExchange64 InterlockedExchangeAdd InterlockedExchangeAdd64 InterlockedExchangePointer InterlockedFlushSList InterlockedIncrement InterlockedIncrement64 InterlockedOr InterlockedPopEntrySList InterlockedPushEntrySList InterlockedXor LeaveCriticalSection MemoryBarrier QueryDepthSList ReleaseSRWLockExclusive ReleaseSRWLockShared SetCriticalSectionSpinCount SleepConditionVariableCS SleepConditionVariableSRW TryAcquireSRWLockExclusive TryAcquireSRWLockShared TryEnterCriticalSection WakeAllConditionVariable WakeConditionVariable |
| midi_conv.c | 18 | midiInAddBuffer*~ midiInClose*~ midiInGetDevCapsW*~ midiInGetNumDevs*~ midiInOpen*~ midiInPrepareHeader*~ midiInReset*~ midiInStart*~ midiInStop*~ midiInUnprepareHeader*~ midiOutClose*~ midiOutGetDevCapsW*~ midiOutGetNumDevs*~ midiOutLongMsg*~ midiOutOpen*~ midiOutPrepareHeader*~ midiOutShortMsg*~ midiOutUnprepareHeader*~ |
| module.c | 20 | FindResourceA FindResourceW FreeLibrary FreeResource GetModuleFileNameA GetModuleFileNameW GetModuleHandleA GetModuleHandleExW GetModuleHandleW GetProcAddress ImageDirectoryEntryToData ImageNtHeader ImageRvaToVa LoadLibraryA LoadLibraryExW LoadLibraryW LoadResource LockResource SetDllDirectoryW SizeofResource |
| net.c | 46 | CertCloseStore* CertFindCertificateInStore* CertFreeCertificateContext* CertGetNameStringA* CertGetNameStringW* CryptDecodeObject* CryptMsgClose* CryptMsgGetParam* CryptQueryObject* HttpAddRequestHeadersW* HttpEndRequestW* HttpOpenRequestW* HttpQueryInfoA* HttpQueryInfoW* HttpSendRequestA HttpSendRequestExW* HttpSendRequestW InternetCheckConnectionA InternetCheckConnectionW InternetCloseHandle* InternetConnectW* InternetGetConnectedState* InternetGetLastResponseInfoW* InternetOpenA* InternetOpenUrlA* InternetOpenUrlW* InternetOpenW* InternetReadFile* InternetSetOptionW* InternetSetStatusCallbackW* InternetWriteFile* WNetCloseEnum* WNetEnumResourceW* WNetGetUniversalNameW* WNetOpenEnumW* WSACleanup* WSAGetLastError* WSAPoll* WSASetLastError* WSASocketW* WSAStartup* WinVerifyTrust* closesocket* ioctlsocket* midiInGetErrorTextW*~ midiOutGetErrorTextW*~ |
| ole.c | 61 | CLSIDFromString CoCreateGuid CoCreateInstance* CoGetClassObject* CoGetInterfaceAndReleaseStream CoInitialize CoInitializeEx CoMarshalInterThreadInterfaceInStream CoTaskMemAlloc CoTaskMemFree CoTaskMemRealloc CoUninitialize CreateDataAdviseHolder* CreateILockBytesOnHGlobal* CreateStreamOnHGlobal DoDragDrop* GetActiveObject* GetErrorInfo* GetHGlobalFromStream IsAccelerator* IsEqualGUID OleDraw* OleFlushClipboard* OleGetClipboard* OleInitialize OleIsCurrentClipboard* OleSetClipboard* OleSetMenuDescriptor* OleUninitialize ProgIDFromCLSID* PropVariantClear RegisterDragDrop ReleaseStgMedium RevokeDragDrop SHGetMalloc SafeArrayAccessData SafeArrayCreate SafeArrayDestroy SafeArrayGetElement SafeArrayGetElemsize SafeArrayGetLBound SafeArrayGetUBound SafeArrayPtrOfIndex SafeArrayPutElement SafeArrayUnaccessData StgCreateDocfileOnILockBytes* StringFromCLSID StringFromGUID2 SysAllocString SysAllocStringByteLen SysAllocStringLen SysFreeString SysReAllocStringLen SysStringByteLen SysStringLen UuidCreate VariantChangeType VariantClear VariantCopy VariantCopyInd VariantInit |
| reg.c | 31 | GetTokenInformation OpenProcessToken RegCloseKey RegCreateKeyExA RegCreateKeyExW RegCreateKeyW RegDeleteKeyA RegDeleteKeyExW RegDeleteKeyValueW RegDeleteKeyW RegDeleteTreeW RegDeleteValueA RegDeleteValueW RegEnumKeyExA RegEnumKeyExW RegEnumKeyW RegEnumValueA RegEnumValueW RegFlushKey RegGetValueA RegGetValueW RegOpenKeyExA RegOpenKeyExW RegOpenKeyW RegQueryInfoKeyA RegQueryInfoKeyW RegQueryValueExA RegQueryValueExW RegSetKeyValueW RegSetValueExA RegSetValueExW |
| seh.c | 20 | AddVectoredExceptionHandler RaiseException RemoveVectoredExceptionHandler RtlCaptureContext* RtlLookupFunctionEntry* RtlPcToFileHeader RtlUnwind* RtlUnwindEx* RtlVirtualUnwind* SetUnhandledExceptionFilter UnhandledExceptionFilter __acrt_lock __acrt_unlock _amsg_exit _lock _lock_file _mlock _munlock _unlock _unlock_file |
| shell.c | 70 | ClosePrinter* CommDlgExtendedError* DocumentPropertiesW* DragAcceptFiles* DragFinish* DragQueryFileW* DragQueryPoint* EnumPrintersW* ExtractAssociatedIconW* GetDefaultPrinterW* GetFileVersionInfoSizeW GetFileVersionInfoW GetOpenFileNameW* GetSaveFileNameW* ILClone ILCloneFirst ILCombine ILCreateFromPathW ILFindLastID ILFree ILGetNext ILGetSize ILIsEqual ILRemoveLastID LresultFromObject* OpenPrinterW* PathUnExpandEnvStringsW PropVariantToBooleanWithDefault* PropVariantToFileTime* PropVariantToStringWithDefault* PropVariantToVariant* SHAddToRecentDocs* SHAppBarMessage* SHChangeNotifyDeregister* SHChangeNotifyRegister* SHCreateDirectoryExW SHCreateItemFromParsingName* SHCreateStreamOnFileEx* SHFileOperationW SHGetDesktopFolder* SHGetFileInfoW* SHGetFolderPathW SHGetKnownFolderPath SHGetPathFromIDListW SHGetSpecialFolderLocation SHGetSpecialFolderPathW SHOpenFolderAndSelectItems* ShellExecuteA* ShellExecuteExA* ShellExecuteExW* ShellExecuteW* Shell_NotifyIconW* VariantToPropVariant* VerQueryValueW WTSRegisterSessionNotification*~ WTSUnRegisterSessionNotification*~ acmDriverClose* acmDriverDetailsA* acmDriverEnum* acmDriverOpen* acmFormatChooseW* acmFormatSuggest* acmMetrics* acmStreamClose* acmStreamConvert* acmStreamMessage* acmStreamOpen* acmStreamPrepareHeader* acmStreamSize* acmStreamUnprepareHeader* |
| shord.c | 3 | QISearch SHCreateMemStream SHCreateStdEnumFmtEtc |
| str.c | 33 | CharLowerBuffW~ CharLowerW~ CharNextExA~ CharNextW~ CharToOemBuffW~ CharUpperBuffW~ CharUpperW~ CompareStringA CompareStringEx CompareStringW GetACP GetCPInfo GetCPInfoExW GetOEMCP GetStringTypeW IsDBCSLeadByteEx IsValidCodePage LCMapStringEx LCMapStringW MulDiv MultiByteToWideChar NormalizeString WideCharToMultiByte lstrcatW lstrcmpA lstrcmpW lstrcmpiA lstrcmpiW lstrcpyA lstrcpyW lstrcpynW lstrlenA lstrlenW |
| teb.c | 18 | DecodePointer EncodePointer FlsAlloc FlsFree FlsGetValue FlsSetValue GetLastError SetLastError TlsAlloc TlsFree TlsGetValue TlsSetValue __readgsbyte __readgsdword __readgsqword __readgsword __writegsdword __writegsqword |
| thread.c | 34 | ChangeTimerQueueTimer CloseThreadpoolWork CreateIoCompletionPort* CreateThread CreateThreadpoolWork CreateTimerQueue CreateTimerQueueTimer DeleteTimerQueueEx DeleteTimerQueueTimer ExitThread FreeLibraryAndExitThread FreeLibraryWhenCallbackReturns* GetCurrentProcess GetCurrentProcessId GetCurrentThread GetCurrentThreadId GetExitCodeProcess GetExitCodeThread GetPriorityClass* GetProcessAffinityMask GetProcessId GetQueuedCompletionStatus* GetThreadId GetThreadPriority OpenProcess ResumeThread SetPriorityClass* SetProcessAffinityMask* SetThreadAffinityMask SetThreadExecutionState* SetThreadPriority SubmitThreadpoolWork SuspendThread* TerminateThread* |
| timer.c | 27 | CompareFileTime DosDateTimeToFileTime FileTimeToDosDateTime FileTimeToLocalFileTime FileTimeToSystemTime GetDateFormatW GetLocalTime GetSystemTime GetSystemTimeAsFileTime GetTickCount GetTickCount64 GetTimeFormatW GetTimeZoneInformation GetTimeZoneInformationForYear LocalFileTimeToFileTime QueryPerformanceCounter QueryPerformanceFrequency Sleep SleepEx SwitchToThread SystemTimeToFileTime SystemTimeToTzSpecificLocalTime TzSpecificLocalTimeToSystemTime timeBeginPeriod*~ timeEndPeriod*~ timeGetDevCaps*~ timeGetTime |
| wait.c | 23 | CreateEventA CreateEventExW CreateEventW CreateMutexA CreateMutexW CreateSemaphoreA CreateSemaphoreW MsgWaitForMultipleObjects~ MsgWaitForMultipleObjectsEx~ OpenEventA OpenEventW OpenMutexW OpenSemaphoreW PulseEvent ReleaseMutex ReleaseSemaphore ResetEvent SetEvent SignalObjectAndWait WaitForMultipleObjects WaitForMultipleObjectsEx WaitForSingleObject WaitForSingleObjectEx |

運用フック (`shimx_*` + `vreg_*`): shimx_cb_translator shimx_cbtrans_calls shimx_cbtrans_get_invoke shimx_cbtrans_install shimx_cbtrans_registrations shimx_cbtrans_reset shimx_cbtrans_set_invoke shimx_cbtrans_slot_va shimx_cbtrans_slots shimx_drag_accepts shimx_drop_invoke shimx_get_callback_translator shimx_get_drop_target shimx_get_intptr_limit shimx_handle_stats shimx_hdrop_bytes shimx_hdrop_create shimx_ido_AddRef shimx_ido_GetData shimx_ido_NotImpl shimx_ido_QueryGetData shimx_ido_QueryInterface shimx_ido_Release shimx_init shimx_lifttab_count shimx_lifttab_name shimx_lifttab_proc_resolver shimx_lifttab_token shimx_lifttab_trampoline shimx_module_register shimx_path_to_posix shimx_proc_register shimx_reg_export_text shimx_reg_import_text shimx_reg_reset shimx_reg_set shimx_reg_set_dword shimx_reg_set_sz shimx_reg_stats shimx_seh_current_exception shimx_seh_depth shimx_seh_enter shimx_seh_leave shimx_seh_set_pad_resolver shimx_seh_set_typed_matcher shimx_set_acp shimx_set_callback_translator shimx_set_command_line shimx_set_cs_null_ok shimx_set_exe_path shimx_set_exit_hook shimx_set_file_close_hook shimx_set_intptr_limit shimx_set_load_hook shimx_set_locale shimx_set_midi_backend shimx_set_notify_hook shimx_set_path_mapper shimx_set_proc_resolver shimx_set_pseudo_load shimx_set_raise_hook shimx_set_resource_provider shimx_set_shell_execute_hook shimx_set_strict shimx_set_trace shimx_set_trace_file shimx_set_trust_ok shimx_set_version shimx_setenv_utf8 shimx_towlower shimx_towupper shimx_utf16_to_utf8 shimx_utf8_to_utf16 shimx_wininet_call_count vreg_clear_all vreg_clear_root vreg_export_root vreg_generation vreg_set_notify

## 表C: 未実装 (担当範囲内)

FLEngine 静的/delay import には担当範囲内の未実装 API は **ありません**。

序数 import のうち同定済み (実行時は GetProcAddress が返す): shell32!ord74=SHCreateStdEnumFmtEtc (同定済み・実装済み, GetProcAddress 序数表で解決), shell32!ord190=ILCreateFromPathW (同定済み・実装済み, GetProcAddress 序数表で解決), shell32!ord155=ILFree (同定済み・実装済み, GetProcAddress 序数表で解決), shlwapi!ord219=QISearch (同定済み・実装済み, GetProcAddress 序数表で解決), shlwapi!ord12=SHCreateMemStream (同定済み・実装済み, GetProcAddress 序数表で解決)
序数 import (名前解決不能。実体 API の特定が要る): d2d1!ord1

プラグイン専用で未提供 (BSD ソケット名は Emscripten libc が解決; 下記は Serum2 のみ): なし

## 表D: 対象外 (他担当 DLL)

| DLL | 担当 | FLEngine import 数 | 備考 |
|---|---|---|---|
| user32.dll | tools/gui | 227 | 名前一覧は data/inventory.csv。重複定義回避のため user32 の CharXxx/MsgWait* 等は shimx が weak 定義で保持 |
| gdi32.dll | tools/gui | 127 | 名前一覧は data/inventory.csv。重複定義回避のため user32 の CharXxx/MsgWait* 等は shimx が weak 定義で保持 |
| comctl32.dll | tools/gui | 30 | 名前一覧は data/inventory.csv。重複定義回避のため user32 の CharXxx/MsgWait* 等は shimx が weak 定義で保持 |
| opengl32.dll | tools/gui | 2 | 名前一覧は data/inventory.csv。重複定義回避のため user32 の CharXxx/MsgWait* 等は shimx が weak 定義で保持 |
| dsound.dll | tools/audio | 2 | 名前一覧は data/inventory.csv。重複定義回避のため user32 の CharXxx/MsgWait* 等は shimx が weak 定義で保持 |

## 方針差・制限 (M4 比 / 実装上の割り切り)

- ハンドル表: 256→16384 スロット、HANDLE=(idx+1)*4、参照カウント、`DuplicateHandle`、名前付き Event/Mutex/Semaphore/FileMapping の共有名前空間 (`Local\`/`Global\` 接頭辞は同一視)。
- LastError・TLS・FLS・TID・擬似 TEB(gs:) はスレッドローカル (M4 は LastError がプロセス単位)。TEB は Win64 オフセット (+0x30 Self/+0x68 LastError/+0x1480 TlsSlots) を再現。
- CRITICAL_SECTION は M4 の「ポインタ→mutex 表 (128 件上限)」から、クライアントメモリ上の Win64 40B 構造体直接実装に変更 (上限なし/ゼロ初期化メモリも未ロック扱い)。
- CreateThread: CREATE_SUSPENDED 対応、返す threadId は新スレッド自身の ID (M4 は作成側 ID)。全スレッド detached、終了は状態+futex 通知。SuspendThread/TerminateThread は状態のみ (実停止不可)。
- Heap/Global/Local: ユーザポインタ 16B 整列 (M4 は 4B)。GMEM_MOVEABLE は FIXED 写像 (M4 同様)。`GlobalUnlock` は M4 互換 (ロック済みなら TRUE)。HeapDestroy は配下ブロックを解放しない。
- Win64 レイアウト構造体 (SYSTEM_INFO/MEMORYSTATUS/STARTUPINFOW/MEMORY_BASIC_INFORMATION/EXCEPTION_RECORD/VARIANT/SAFEARRAY/SHFILEOPSTRUCT/SHELLEXECUTEINFO 他) はポインタ位置を 8B スロットで実装。`FormatMessage` の ARGUMENT_ARRAY は 8B 要素。
- パス: `C:\x` → `/c/x`、UNC → `/unc/...`、POSIX 絶対パスは素通し。FS 側未発見時は大小無視で再探索。`shimx_set_path_mapper` で VFS 連携。
- コードページ: 既定 ACP=1252。UTF-8/1252/Latin-1/ASCII のみ (932 等 DBCS は ERROR_INVALID_PARAMETER)。ロケールは en-US データ固定。
- `GetProcAddress` 未知名は NULL+ERROR_PROC_NOT_FOUND (strict モードで fail-fast)。関数ポインタは wasm テーブル index (lifted コードの間接呼出しとの整合は hostbridge 課題)。
- 序数判定 (`MAKEINTRESOURCE`/`CharUpperW(単一文字)`/ordinal GetProcAddress) は値 < 0x10000 を整数とみなす → ビルドの GLOBAL_BASE は 64KB 以上にすること (lifted 系は 0x10000000 で適合)。
- ws2_32: BSD ソケット名 (`socket` 等) は libc 名衝突のため未定義 (Emscripten libc が解決)。Windows 固有名 (WSAStartup=WSASYSNOTREADY 等) のみ提供。
- `__lock`/`__unlock` は musl 内部名と衝突するため定義しない (`_lock`/`_unlock`/`_mlock`/`_munlock`/`_lock_file`/`__acrt_lock` のみ)。
