# unit 隔離 survey (942 unit を 1 本ずつ実行; soft+fix ビルド, 計数ラッパ経由)

| 結果 | shimx リンク (soft+fix) | M11 既存ビルド (同じ手順で再測) |
|---|---|---|
| abort | 1 | 1 |
| closure_outside | 46 | 46 |
| halt0 | 53 | 44 |
| noproc | 1 | 1 |
| ok | 800 | 800 |
| oob | 41 | 50 |

既存ビルドとの unit 別差: oob→halt0 9 unit
(注: runtime が abort した unit の後は新インスタンスで継続するため、M11 REPORT の survey 数値 ok 812/OOB 34/Halt0 48 とは unit 間状態の引継ぎが異なり一致しない)

## SHIMX_TRACE=1 の [shimx] 出力 (survey 全体; GetProcAddress miss / LoadLibrary 失敗 / ShellExecute 等)

- `[shimx] GetProcAddress miss: kernel32.dll!#39682` x1 (最初 unit 2)
- `[shimx] lifttab: GetThreadPreferredUILanguages # orm=0 -> token 0x7f00000a` x1 (最初 unit 2)
- `[shimx] lifttab: SetThreadPreferredUILanguages # orm=0 -> token 0x7f00000b` x1 (最初 unit 2)
- `[shimx] lifttab: GetThreadUILanguage # orm=0 -> token 0x7f00000c` x1 (最初 unit 2)
- `[shimx] GetProcAddress miss: ntdll.dll!` x1 (最初 unit 18)
- `[shimx] cbtrans: EnumCalendarInfoW VA 0x4476d0 -> trampoline slot 0 (invoke=0x1)` x1 (最初 unit 18)
- `[shimx] cbtrans: EnumCalendarInfoW VA 0x4477a0 -> trampoline slot 1 (invoke=0x1)` x1 (最初 unit 18)
- `[shimx] GetProcAddress miss: kernel32.dll!` x11 (最初 unit 36)
- `[shimx] LoadLibrary 失敗: Msctf.dll` x1 (最初 unit 104)
- `[shimx] GetProcAddress miss: ole32.dll!` x6 (最初 unit 107)
- `[shimx] GetProcAddress miss: shell32.dll!` x1 (最初 unit 137)
- `[shimx] GetProcAddress miss: dwmapi.dll!` x23 (最初 unit 146)
- `[shimx] GetProcAddress miss: user32.dll!` x8 (最初 unit 146)
- `[shimx] LoadLibrary 失敗: avrt` x1 (最初 unit 146)
- `[shimx] GetProcAddress miss: advapi32.dll!` x1 (最初 unit 146)
- `[shimx] LoadLibrary 失敗: PowrProf.dll` x1 (最初 unit 146)
- `[shimx] GetProcAddress miss: shcore.dll!` x1 (最初 unit 146)
- `[shimx] lifttab: (null) # orm=16 -> token 0x7f000000` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=17 -> token 0x7f000001` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=18 -> token 0x7f000002` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=19 -> token 0x7f000003` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=21 -> token 0x7f000004` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=25 -> token 0x7f000005` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=152 -> token 0x7f000006` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=153 -> token 0x7f000007` x1 (最初 unit 239)
- `[shimx] lifttab: (null) # orm=155 -> token 0x7f000008` x1 (最初 unit 239)
- `[shimx] GetProcAddress miss: comctl32.dll!` x12 (最初 unit 299)

## fail-fast (abort) した unit

- unit 115 (init LVA 0x223840): [shim] FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (NULL/misaligned)

## survey で呼ばれた shim API (unit 数 / 呼出数 / 最初の unit / 区分 / 状態)

| API | unit 数 | 呼出数 | 最初 unit | 状態 |
|---|---|---|---|---|
| TlsGetValue | 53 | 61 | 41 | 機能 |
| MessageBoxA | 42 | 42 | 41 | X:gui |
| LoadStringW | 28 | 288112716 | 16 | X:gui |
| InitializeCriticalSection | 22 | 28 | 2 | 機能 |
| VirtualAlloc | 16 | 33 | 18 | 機能 |
| GetModuleHandleW | 12 | 17 | 2 | 機能 |
| GetProcAddress | 12 | 77 | 2 | 機能 |
| WideCharToMultiByte | 10 | 64 | 18 | 機能 |
| GetCurrentThreadId | 6 | 13 | 2 | 機能 |
| QueryPerformanceCounter | 5 | 5 | 46 | 機能 |
| GetACP | 3 | 3 | 2 | 機能 |
| GetSystemInfo | 3 | 3 | 2 | 機能 |
| GetVersionExW | 3 | 3 | 17 | 機能 |
| GetCPInfo | 3 | 3 | 18 | 機能 |
| CreateEventW | 3 | 4 | 42 | 機能 |
| LoadLibraryW | 3 | 7 | 104 | 機能 |
| RegisterClipboardFormatW | 3 | 4 | 168 | X:gui |
| RegisterWindowMessageW | 3 | 6 | 228 | X:gui |
| GetModuleFileNameW | 2 | 2 | 18 | 機能 |
| QueryPerformanceFrequency | 2 | 2 | 46 | 機能 |
| RegCloseKey | 2 | 4 | 96 | 機能 |
| RegOpenKeyExW | 2 | 5 | 96 | 機能 |
| GetCommandLineW | 1 | 1 | 2 | 機能 |
| GetStartupInfoW | 1 | 1 | 2 | 機能 |
| GetVersion | 1 | 2 | 2 | 機能 |
| SetThreadLocale | 1 | 1 | 2 | 機能 |
| VerSetConditionMask | 1 | 3 | 2 | 機能 |
| VerifyVersionInfoW | 1 | 1 | 2 | 機能 |
| EnumCalendarInfoW | 1 | 2 | 18 | 機能 |
| GetLocaleInfoW | 1 | 48 | 18 | 機能 |
| GetThreadLocale | 1 | 1 | 18 | 機能 |
| IsValidLocale | 1 | 1 | 18 | 機能 |
| FormatMessageW | 1 | 1 | 23 | 機能 |
| LocalFree | 1 | 1 | 23 | 機能 |
| MulDiv | 1 | 1 | 96 | 機能 |
| RegFlushKey | 1 | 1 | 96 | 機能 |
| CreatePalette | 1 | 1 | 96 | X:gui |
| GetDC | 1 | 2 | 96 | X:gui |
| GetDeviceCaps | 1 | 2 | 96 | X:gui |
| GetStockObject | 1 | 3 | 96 | X:gui |
| LoadIconW | 1 | 1 | 96 | X:gui |
| ReleaseDC | 1 | 2 | 96 | X:gui |
| SetErrorMode | 1 | 2 | 104 | スタブ |
| acmMetrics | 1 | 1 | 171 | スタブ |
| OleInitialize | 1 | 1 | 236 | 機能 |
| SHGetMalloc | 1 | 1 | 236 | 機能 |
| FindWindowW | 1 | 1 | 237 | X:gui |
| EnumDisplaySettingsW | 1 | 1 | 247 | X:gui |
| GetClipCursor | 1 | 1 | 273 | X:gui |
| GetSystemMetrics | 1 | 5 | 277 | X:gui |
| GlobalAddAtomW | 1 | 1 | 305 | 機能 |
