"""FLEngine_x64.dll の API 分類表 (AU-8 #194)。fl_thread_surface.py と mixer_reach.py が共有する。
クラス: thread_create (スレッド/タイマ生成) / blocking_wait (待機系) / nonblocking_sync (非ブロッキング同期) /
atomic / thread_attr (TLS・優先度・affinity)。"""
CLASSES = {
    "thread_create": {"CreateThread", "_beginthreadex", "_beginthread", "CreateRemoteThread", "QueueUserWorkItem",
                      "CreateThreadpoolWork", "SubmitThreadpoolWork", "CreateTimerQueueTimer", "SetTimer", "timeSetEvent"},
    "blocking_wait": {"WaitForSingleObject", "WaitForSingleObjectEx", "WaitForMultipleObjects", "WaitForMultipleObjectsEx",
                      "MsgWaitForMultipleObjects", "MsgWaitForMultipleObjectsEx", "Sleep", "SleepEx", "SwitchToThread",
                      "SignalObjectAndWait", "GetQueuedCompletionStatus", "WaitOnAddress", "SleepConditionVariableCS",
                      "SleepConditionVariableSRW", "EnterCriticalSection", "AcquireSRWLockExclusive", "AcquireSRWLockShared",
                      "WaitForThreadpoolWorkCallbacks"},
    "nonblocking_sync": {"InitializeCriticalSection", "InitializeCriticalSectionAndSpinCount", "LeaveCriticalSection",
                         "TryEnterCriticalSection", "DeleteCriticalSection", "SetEvent", "ResetEvent", "CreateEventA", "CreateEventW",
                         "CreateEventExW", "CreateSemaphoreA", "CreateSemaphoreW", "ReleaseSemaphore", "CreateMutexA", "CreateMutexW",
                         "ReleaseMutex", "ReleaseSRWLockExclusive", "ReleaseSRWLockShared", "WakeByAddressSingle", "WakeByAddressAll",
                         "WakeConditionVariable", "WakeAllConditionVariable", "InitializeSRWLock"},
    "atomic": {"InterlockedIncrement", "InterlockedDecrement", "InterlockedExchange", "InterlockedExchangeAdd",
               "InterlockedCompareExchange", "InterlockedCompareExchange64", "InterlockedExchange64"},
    "thread_attr": {"SetThreadPriority", "GetThreadPriority", "SetThreadAffinityMask", "SetProcessAffinityMask", "GetCurrentThreadId",
                    "TlsAlloc", "TlsGetValue", "TlsSetValue", "TlsFree", "FlsAlloc", "FlsGetValue", "FlsSetValue",
                    "AvSetMmThreadCharacteristicsA", "AvSetMmThreadCharacteristicsW", "SetThreadIdealProcessor", "ExitThread",
                    "TerminateThread", "SuspendThread", "ResumeThread"},
}
API2CLASS = {a: c for c, s in CLASSES.items() for a in s}
