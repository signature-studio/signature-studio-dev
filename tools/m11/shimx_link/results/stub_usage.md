# shimx スタブ (inventory status=S) のうち起動経路で呼ばれたもの

- FLEngine 静的 import に対するスタブ: 115 本 (inventory S, 全 scope 重複除く: 126)
- 17 unit 通常起動 + #18 で呼ばれたスタブ: なし
- 942 unit survey (隔離実行) で呼ばれたスタブ: SetErrorMode, acmMetrics
- fail-fast 系 (RtlUnwind/RtlUnwindEx/RaiseException) の closure declare 数: 0 / 到達: なし
- shimx 解決 184 名のうちスタブ 13 名: CoCreateInstance, InternetGetConnectedState, OutputDebugStringW, SHAppBarMessage, SetErrorMode, SetThreadErrorMode, ShellExecuteW, WTSRegisterSessionNotification, acmMetrics, midiOutShortMsg, timeBeginPeriod, timeEndPeriod, timeGetDevCaps
- shimx 内部の fail-fast (shim_unimplemented) に当たったもの: unit 115: [shim] FAIL-FAST: unimplemented Win32 API: EnterCriticalSection (NULL/misaligned)
