/* shimx: Win32/CRT shim extension (M4 shim の上位互換)。
 *
 * - 型・定数は x64 Windows の幅に合わせる。ポインタ/HANDLE は wasm32 の 4B だが、
 *   lifted コード (Win64 機械語由来のバイトオフセット) と共有する構造体
 *   (SYSTEM_INFO/STARTUPINFO/MEMORY_BASIC_INFORMATION/EXCEPTION_RECORD/VARIANT/SAFEARRAY ...)
 *   は *Win64 レイアウト* (ポインタ位置を 8B スロット) で宣言する。
 * - 未対応 API は shim_unimplemented() で関数名を出して abort (M4 方針を維持)。
 * - M4 (tools/shim) の 53 API は全てこの実装が置換する (同一シンボル名・同一署名)。
 */
#ifndef SHIMX_H
#define SHIMX_H

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <setjmp.h>

#if defined(__EMSCRIPTEN__)
#include <emscripten.h>
#include <emscripten/threading_primitives.h>
#endif
#if defined(__EMSCRIPTEN_PTHREADS__)
#include <pthread.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define SHIMX_WEAK __attribute__((weak))

/* ---------------- 基本型 ---------------- */
typedef size_t   SIZE_T;
typedef uint8_t  BYTE;
typedef uint16_t WORD;
typedef uint32_t DWORD;
typedef uint32_t UINT;
typedef uint32_t ULONG;
typedef int32_t  LONG;
typedef int64_t  LONGLONG;
typedef uint64_t ULONGLONG;
typedef uint64_t DWORD64;
typedef int      BOOL;
typedef uint8_t  BOOLEAN;
typedef int32_t  HRESULT;
typedef uint16_t WCHAR;
typedef char     CHAR;
typedef char*    LPSTR;
typedef const char* LPCSTR;
typedef WCHAR*   LPWSTR;
typedef const WCHAR* LPCWSTR;
typedef void*    LPVOID;
typedef void*    PVOID;
typedef const void* LPCVOID;
typedef DWORD*   LPDWORD;
typedef LONG*    PLONG;
typedef BYTE*    LPBYTE;
typedef void*    LPSECURITY_ATTRIBUTES;
typedef void*    LPOVERLAPPED;
typedef size_t   ULONG_PTR;
typedef ULONG_PTR HANDLE;
typedef HANDLE*  LPHANDLE;
typedef HANDLE   HMODULE;
typedef HANDLE   HINSTANCE;
typedef HANDLE   HKEY;
typedef HKEY*    PHKEY;
typedef HANDLE   HGLOBAL;
typedef HANDLE   HLOCAL;
typedef HANDLE   HEAP_HANDLE;
typedef HANDLE   HRSRC;
typedef HANDLE   HWND;
typedef DWORD    LCID;
typedef DWORD    LCTYPE;
typedef WORD     LANGID;
typedef WORD     ATOM;
typedef uint64_t REGSAM_T;
typedef DWORD    REGSAM;
typedef LONG     LSTATUS;
typedef void*    PCRITICAL_SECTION;
typedef void*    PSRWLOCK;
typedef void*    PCONDITION_VARIABLE;
typedef void*    PINIT_ONCE;
typedef ULONG_PTR LPARAM_T;
typedef ULONG_PTR LRESULT_T;
typedef ULONG_PTR UINT_PTR_T;
typedef uint16_t USHORT_T;

#define INVALID_HANDLE_VALUE ((HANDLE)(ULONG_PTR)-1)
#ifndef TRUE
#define TRUE  1
#define FALSE 0
#endif
#ifndef WINAPI
#define WINAPI
#define APIENTRY
#define CALLBACK
#endif

typedef struct _LARGE_INTEGER { int64_t QuadPart; } LARGE_INTEGER, *PLARGE_INTEGER;
typedef struct _FILETIME { DWORD dwLowDateTime, dwHighDateTime; } FILETIME, *LPFILETIME;
typedef struct _SYSTEMTIME {
    WORD wYear, wMonth, wDayOfWeek, wDay, wHour, wMinute, wSecond, wMilliseconds;
} SYSTEMTIME, *LPSYSTEMTIME;

/* ---------------- 定数 ---------------- */
#define INFINITE            0xFFFFFFFFu
#define WAIT_OBJECT_0       0u
#define WAIT_ABANDONED_0    0x80u
#define WAIT_IO_COMPLETION  0xC0u
#define WAIT_TIMEOUT        258u
#define WAIT_FAILED         0xFFFFFFFFu
#define MAXIMUM_WAIT_OBJECTS 64
#define STILL_ACTIVE        259u
#define INVALID_SET_FILE_POINTER 0xFFFFFFFFu
#define INVALID_FILE_ATTRIBUTES  0xFFFFFFFFu
#define INVALID_FILE_SIZE        0xFFFFFFFFu
#define TLS_OUT_OF_INDEXES  0xFFFFFFFFu
#define FLS_OUT_OF_INDEXES  0xFFFFFFFFu

/* エラーコード */
#define ERROR_SUCCESS            0u
#define ERROR_INVALID_FUNCTION   1u
#define ERROR_FILE_NOT_FOUND     2u
#define ERROR_PATH_NOT_FOUND     3u
#define ERROR_TOO_MANY_OPEN_FILES 4u
#define ERROR_ACCESS_DENIED      5u
#define ERROR_INVALID_HANDLE     6u
#define ERROR_NOT_ENOUGH_MEMORY  8u
#define ERROR_INVALID_DATA       13u
#define ERROR_OUTOFMEMORY        14u
#define ERROR_NOT_SAME_DEVICE    17u
#define ERROR_NO_MORE_FILES      18u
#define ERROR_SHARING_VIOLATION  32u
#define ERROR_HANDLE_EOF         38u
#define ERROR_NOT_SUPPORTED      50u
#define ERROR_FILE_EXISTS        80u
#define ERROR_INVALID_PARAMETER  87u
#define ERROR_INSUFFICIENT_BUFFER 122u
#define ERROR_INVALID_NAME       123u
#define ERROR_CALL_NOT_IMPLEMENTED 120u
#define ERROR_NEGATIVE_SEEK      131u
#define ERROR_DIR_NOT_EMPTY      145u
#define ERROR_ALREADY_EXISTS     183u
#define ERROR_ENVVAR_NOT_FOUND   203u
#define ERROR_MORE_DATA          234u
#define ERROR_NO_MORE_ITEMS      259u
#define ERROR_NOT_OWNER          288u
#define ERROR_TOO_MANY_POSTS     298u
#define ERROR_PRIVILEGE_NOT_HELD 1314u
#define ERROR_NO_NETWORK         1222u
#define ERROR_MOD_NOT_FOUND      126u
#define ERROR_PROC_NOT_FOUND     127u
#define ERROR_RESOURCE_DATA_NOT_FOUND 1812u
#define ERROR_RESOURCE_TYPE_NOT_FOUND 1813u
#define ERROR_RESOURCE_NAME_NOT_FOUND 1814u
#define ERROR_NOT_FOUND          1168u
#define ERROR_TIMEOUT            1460u
#define ERROR_BAD_PATHNAME       161u
#define ERROR_INVALID_FLAGS      1004u
#define ERROR_INTERNET_CANNOT_CONNECT 12029u
#define ERROR_INTERNET_DISCONNECTED   12163u
#define ERROR_NO_UNICODE_TRANSLATION  1113u
#define ERROR_BAD_EXE_FORMAT     193u
#define ERROR_FILE_INVALID       1006u
#define ERROR_NO_TOKEN           1008u
#define ERROR_PRIVILEGE_NOT_HELD 1314u

#define E_NOTIMPL       ((HRESULT)0x80004001)
#define E_NOINTERFACE   ((HRESULT)0x80004002)
#define E_POINTER       ((HRESULT)0x80004003)
#define E_FAIL          ((HRESULT)0x80004005)
#define E_OUTOFMEMORY   ((HRESULT)0x8007000E)
#define E_INVALIDARG    ((HRESULT)0x80070057)
#define S_OK            ((HRESULT)0)
#define S_FALSE         ((HRESULT)1)
#define REGDB_E_CLASSNOTREG ((HRESULT)0x80040154)
#define CLASS_E_CLASSNOTAVAILABLE ((HRESULT)0x80040111)
#define CO_E_NOTINITIALIZED ((HRESULT)0x800401F0)
#define RPC_E_CHANGED_MODE ((HRESULT)0x80010106)
#define DISP_E_TYPEMISMATCH ((HRESULT)0x80020005)
#define DISP_E_BADVARTYPE ((HRESULT)0x80020008)
#define TRUST_E_NOSIGNATURE ((HRESULT)0x800B0100)
#define TRUST_E_PROVIDER_UNKNOWN ((HRESULT)0x800B0001)
#define HRESULT_FROM_WIN32(x) ((HRESULT)(x) <= 0 ? (HRESULT)(x) : (HRESULT)(((x) & 0x0000FFFF) | 0x80070000))
#define FAILED(hr) ((HRESULT)(hr) < 0)
#define SUCCEEDED(hr) ((HRESULT)(hr) >= 0)

/* CreateFile */
#define GENERIC_READ      0x80000000u
#define GENERIC_WRITE     0x40000000u
#define GENERIC_EXECUTE   0x20000000u
#define GENERIC_ALL       0x10000000u
#define FILE_SHARE_READ   1u
#define FILE_SHARE_WRITE  2u
#define FILE_SHARE_DELETE 4u
#define CREATE_NEW        1u
#define CREATE_ALWAYS     2u
#define OPEN_EXISTING     3u
#define OPEN_ALWAYS       4u
#define TRUNCATE_EXISTING 5u
#define FILE_BEGIN   0u
#define FILE_CURRENT 1u
#define FILE_END     2u
#define FILE_ATTRIBUTE_READONLY  0x1u
#define FILE_ATTRIBUTE_HIDDEN    0x2u
#define FILE_ATTRIBUTE_SYSTEM    0x4u
#define FILE_ATTRIBUTE_DIRECTORY 0x10u
#define FILE_ATTRIBUTE_ARCHIVE   0x20u
#define FILE_ATTRIBUTE_NORMAL    0x80u
#define FILE_ATTRIBUTE_TEMPORARY 0x100u
#define FILE_FLAG_BACKUP_SEMANTICS 0x02000000u
#define FILE_TYPE_UNKNOWN 0u
#define FILE_TYPE_DISK    1u
#define FILE_TYPE_CHAR    2u
#define FILE_TYPE_PIPE    3u
#define STD_INPUT_HANDLE  ((DWORD)-10)
#define STD_OUTPUT_HANDLE ((DWORD)-11)
#define STD_ERROR_HANDLE  ((DWORD)-12)
#define MOVEFILE_REPLACE_EXISTING 1u
#define MOVEFILE_COPY_ALLOWED     2u
#define GetFileExInfoStandard     0
#define FindExInfoStandard        0
#define FindExInfoBasic           1
#define FindExSearchNameMatch     0
#define DRIVE_UNKNOWN     0u
#define DRIVE_NO_ROOT_DIR 1u
#define DRIVE_REMOVABLE   2u
#define DRIVE_FIXED       3u
#define MAX_PATH          260
#define PAGE_NOACCESS     0x01u
#define PAGE_READONLY     0x02u
#define PAGE_READWRITE    0x04u
#define PAGE_WRITECOPY    0x08u
#define PAGE_EXECUTE_READWRITE 0x40u
#define FILE_MAP_COPY     1u
#define FILE_MAP_WRITE    2u
#define FILE_MAP_READ     4u
#define SEC_COMMIT        0x08000000u
#define MEM_COMMIT        0x1000u
#define MEM_RESERVE       0x2000u
#define MEM_DECOMMIT      0x4000u
#define MEM_RELEASE       0x8000u
#define MEM_FREE          0x10000u
#define MEM_PRIVATE       0x20000u
#define MEM_MAPPED        0x40000u
#define MEM_TOP_DOWN      0x100000u

/* GlobalAlloc / LocalAlloc / Heap */
#define GMEM_FIXED      0x0000u
#define GMEM_MOVEABLE   0x0002u
#define GMEM_ZEROINIT   0x0040u
#define GHND            (GMEM_MOVEABLE | GMEM_ZEROINIT)
#define GPTR            (GMEM_FIXED | GMEM_ZEROINIT)
#define LMEM_FIXED      GMEM_FIXED
#define LMEM_MOVEABLE   GMEM_MOVEABLE
#define LMEM_ZEROINIT   GMEM_ZEROINIT
#define HEAP_ZERO_MEMORY 0x00000008u
#define HEAP_NO_SERIALIZE 0x00000001u

/* スレッド / プロセス */
#define CREATE_SUSPENDED      0x00000004u
#define THREAD_PRIORITY_NORMAL 0
#define THREAD_PRIORITY_ERROR_RETURN 0x7FFFFFFF
#define NORMAL_PRIORITY_CLASS 0x20u
#define DLL_PROCESS_DETACH 0
#define DLL_PROCESS_ATTACH 1
#define DLL_THREAD_ATTACH  2
#define DLL_THREAD_DETACH  3
#define DUPLICATE_CLOSE_SOURCE 1u
#define DUPLICATE_SAME_ACCESS  2u
#define HANDLE_FLAG_INHERIT 1u
#define HANDLE_FLAG_PROTECT_FROM_CLOSE 2u
#define EVENT_MODIFY_STATE 2u
#define SYNCHRONIZE 0x00100000u
#define INIT_ONCE_ASYNC 2u
#define SRWLOCK_INIT {0}

/* ロケール / コードページ */
#define CP_ACP    0u
#define CP_OEMCP  1u
#define CP_MACCP  2u
#define CP_THREAD_ACP 3u
#define CP_UTF7   65000u
#define CP_UTF8   65001u
#define MB_PRECOMPOSED 1u
#define MB_COMPOSITE   2u
#define MB_ERR_INVALID_CHARS 8u
#define WC_COMPOSITECHECK 0x200u
#define WC_NO_BEST_FIT_CHARS 0x400u
#define WC_ERR_INVALID_CHARS 0x80u
#define CSTR_LESS_THAN    1
#define CSTR_EQUAL        2
#define CSTR_GREATER_THAN 3
#define NORM_IGNORECASE   1u
#define NORM_IGNORENONSPACE 2u
#define NORM_IGNORESYMBOLS 4u
#define SORT_STRINGSORT   0x1000u
#define LINGUISTIC_IGNORECASE 0x10u
#define LCMAP_LOWERCASE   0x100u
#define LCMAP_UPPERCASE   0x200u
#define LCMAP_SORTKEY     0x400u
#define LOCALE_USER_DEFAULT 0x0400u
#define LOCALE_SYSTEM_DEFAULT 0x0800u
#define LOCALE_NEUTRAL    0u
#define LOCALE_RETURN_NUMBER 0x20000000u
#define LOCALE_NOUSEROVERRIDE 0x80000000u
#define CT_CTYPE1 1u
#define CT_CTYPE2 2u
#define CT_CTYPE3 4u
#define C1_UPPER 1u
#define C1_LOWER 2u
#define C1_DIGIT 4u
#define C1_SPACE 8u
#define C1_PUNCT 0x10u
#define C1_CNTRL 0x20u
#define C1_BLANK 0x40u
#define C1_XDIGIT 0x80u
#define C1_ALPHA 0x100u
#define C1_DEFINED 0x200u
#define MAX_DEFAULTCHAR 2
#define MAX_LEADBYTES 12

typedef struct _CPINFO { UINT MaxCharSize; BYTE DefaultChar[MAX_DEFAULTCHAR]; BYTE LeadByte[MAX_LEADBYTES]; } CPINFO, *LPCPINFO;
typedef struct _CPINFOEXW {
    UINT MaxCharSize; BYTE DefaultChar[MAX_DEFAULTCHAR]; BYTE LeadByte[MAX_LEADBYTES];
    WCHAR UnicodeDefaultChar; UINT CodePage; WCHAR CodePageName[MAX_PATH];
} CPINFOEXW, *LPCPINFOEXW;

/* FormatMessage */
#define FORMAT_MESSAGE_ALLOCATE_BUFFER 0x100u
#define FORMAT_MESSAGE_IGNORE_INSERTS  0x200u
#define FORMAT_MESSAGE_FROM_STRING     0x400u
#define FORMAT_MESSAGE_FROM_HMODULE    0x800u
#define FORMAT_MESSAGE_FROM_SYSTEM     0x1000u
#define FORMAT_MESSAGE_ARGUMENT_ARRAY  0x2000u
#define FORMAT_MESSAGE_MAX_WIDTH_MASK  0xFFu

/* レジストリ */
#define HKEY_CLASSES_ROOT   ((HKEY)0x80000000u)
#define HKEY_CURRENT_USER   ((HKEY)0x80000001u)
#define HKEY_LOCAL_MACHINE  ((HKEY)0x80000002u)
#define HKEY_USERS          ((HKEY)0x80000003u)
#define HKEY_CURRENT_CONFIG ((HKEY)0x80000005u)
#define REG_NONE      0u
#define REG_SZ        1u
#define REG_EXPAND_SZ 2u
#define REG_BINARY    3u
#define REG_DWORD     4u
#define REG_DWORD_BIG_ENDIAN 5u
#define REG_LINK      6u
#define REG_MULTI_SZ  7u
#define REG_QWORD     11u
#define REG_OPTION_VOLATILE 1u
#define REG_CREATED_NEW_KEY     1u
#define REG_OPENED_EXISTING_KEY 2u
#define KEY_QUERY_VALUE 0x1u
#define KEY_SET_VALUE   0x2u
#define KEY_READ        0x20019u
#define KEY_WRITE       0x20006u
#define KEY_ALL_ACCESS  0xF003Fu
#define KEY_WOW64_64KEY 0x100u
#define KEY_WOW64_32KEY 0x200u
#define RRF_RT_REG_SZ    0x2u
#define RRF_RT_REG_DWORD 0x10u
#define RRF_RT_ANY       0xFFFFu
#define RRF_NOEXPAND     0x10000000u

/* 例外 */
#define EXCEPTION_NONCONTINUABLE 1u
#define EXCEPTION_MAXIMUM_PARAMETERS 15
#define EXCEPTION_CONTINUE_SEARCH    0
#define EXCEPTION_EXECUTE_HANDLER    1
#define EXCEPTION_CONTINUE_EXECUTION (-1)
#define SEM_FAILCRITICALERRORS 1u

/* Win64 layout 構造体 (ポインタ位置は 8B スロット) */
typedef struct _EXCEPTION_RECORD64 {
    DWORD ExceptionCode; DWORD ExceptionFlags;
    uint64_t ExceptionRecord; uint64_t ExceptionAddress;
    DWORD NumberParameters; DWORD _pad;
    uint64_t ExceptionInformation[EXCEPTION_MAXIMUM_PARAMETERS];
} EXCEPTION_RECORD64;                     /* 152 B */
typedef struct _EXCEPTION_POINTERS64 { uint64_t ExceptionRecord; uint64_t ContextRecord; } EXCEPTION_POINTERS64;
typedef LONG (*PVECTORED_EXCEPTION_HANDLER)(EXCEPTION_POINTERS64* ep);
typedef LONG (*LPTOP_LEVEL_EXCEPTION_FILTER)(EXCEPTION_POINTERS64* ep);

typedef struct _SYSTEM_INFO64 {
    WORD wProcessorArchitecture; WORD wReserved; DWORD dwPageSize;
    uint64_t lpMinimumApplicationAddress; uint64_t lpMaximumApplicationAddress;
    uint64_t dwActiveProcessorMask;
    DWORD dwNumberOfProcessors; DWORD dwProcessorType; DWORD dwAllocationGranularity;
    WORD wProcessorLevel; WORD wProcessorRevision;
} SYSTEM_INFO64;                          /* 48 B */
typedef struct _MEMORYSTATUS64 {
    DWORD dwLength; DWORD dwMemoryLoad;
    uint64_t dwTotalPhys, dwAvailPhys, dwTotalPageFile, dwAvailPageFile, dwTotalVirtual, dwAvailVirtual;
} MEMORYSTATUS64;                         /* 56 B */
typedef struct _MEMORYSTATUSEX {
    DWORD dwLength; DWORD dwMemoryLoad;
    ULONGLONG ullTotalPhys, ullAvailPhys, ullTotalPageFile, ullAvailPageFile,
              ullTotalVirtual, ullAvailVirtual, ullAvailExtendedVirtual;
} MEMORYSTATUSEX;                         /* 64 B */
typedef struct _OSVERSIONINFOEXW {
    DWORD dwOSVersionInfoSize, dwMajorVersion, dwMinorVersion, dwBuildNumber, dwPlatformId;
    WCHAR szCSDVersion[128];
    WORD wServicePackMajor, wServicePackMinor, wSuiteMask; BYTE wProductType, wReserved;
} OSVERSIONINFOEXW;                       /* 284 B */
typedef struct _STARTUPINFOW64 {
    DWORD cb; DWORD _p0; uint64_t lpReserved, lpDesktop, lpTitle;
    DWORD dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
    WORD wShowWindow, cbReserved2; DWORD _p1; uint64_t lpReserved2, hStdInput, hStdOutput, hStdError;
} STARTUPINFOW64;                         /* 104 B */
typedef struct _MEMORY_BASIC_INFORMATION64 {
    uint64_t BaseAddress, AllocationBase; DWORD AllocationProtect; WORD PartitionId; WORD _p0;
    uint64_t RegionSize; DWORD State, Protect, Type, _p1;
} MEMORY_BASIC_INFORMATION64;             /* 48 B */
typedef struct _PROCESS_INFORMATION64 { uint64_t hProcess, hThread; DWORD dwProcessId, dwThreadId; } PROCESS_INFORMATION64;
typedef struct _WIN32_FIND_DATAW {
    DWORD dwFileAttributes; FILETIME ftCreationTime, ftLastAccessTime, ftLastWriteTime;
    DWORD nFileSizeHigh, nFileSizeLow, dwReserved0, dwReserved1;
    WCHAR cFileName[MAX_PATH]; WCHAR cAlternateFileName[14];
} WIN32_FIND_DATAW;                       /* 592 B */
typedef struct _WIN32_FILE_ATTRIBUTE_DATA {
    DWORD dwFileAttributes; FILETIME ftCreationTime, ftLastAccessTime, ftLastWriteTime;
    DWORD nFileSizeHigh, nFileSizeLow;
} WIN32_FILE_ATTRIBUTE_DATA;
typedef struct _BY_HANDLE_FILE_INFORMATION {
    DWORD dwFileAttributes; FILETIME ftCreationTime, ftLastAccessTime, ftLastWriteTime;
    DWORD dwVolumeSerialNumber, nFileSizeHigh, nFileSizeLow, nNumberOfLinks, nFileIndexHigh, nFileIndexLow;
} BY_HANDLE_FILE_INFORMATION;
typedef struct _TIME_ZONE_INFORMATION {
    LONG Bias; WCHAR StandardName[32]; SYSTEMTIME StandardDate; LONG StandardBias;
    WCHAR DaylightName[32]; SYSTEMTIME DaylightDate; LONG DaylightBias;
} TIME_ZONE_INFORMATION;                  /* 172 B */

typedef DWORD (*LPTHREAD_START_ROUTINE)(LPVOID lpParameter);
typedef void  (*WAITORTIMERCALLBACK)(LPVOID, BOOLEAN);
typedef void  (*PFLS_CALLBACK_FUNCTION)(LPVOID);
typedef BOOL  (*PINIT_ONCE_FN)(PINIT_ONCE once, LPVOID param, LPVOID* ctx);
typedef BOOL  (*LOCALE_ENUMPROCW)(LPWSTR);
typedef BOOL  (*CALINFO_ENUMPROCW)(LPWSTR);

/* =============================================================
 * M4 継承: timer / time
 * ============================================================= */
uint64_t GetTickCount64(void);
DWORD    GetTickCount(void);
DWORD    timeGetTime(void);
BOOL     QueryPerformanceCounter(LARGE_INTEGER* out);
BOOL     QueryPerformanceFrequency(LARGE_INTEGER* out);
void     Sleep(DWORD ms);
DWORD    SleepEx(DWORD ms, BOOL alertable);
BOOL     SwitchToThread(void);

/* =============================================================
 * ハンドル表 / 同期 / スレッド
 * ============================================================= */
BOOL   CloseHandle(HANDLE h);
BOOL   DuplicateHandle(HANDLE srcProc, HANDLE src, HANDLE dstProc, LPHANDLE dst,
                       DWORD access, BOOL inherit, DWORD options);
BOOL   GetHandleInformation(HANDLE h, LPDWORD flags);
BOOL   SetHandleInformation(HANDLE h, DWORD mask, DWORD flags);
DWORD  WaitForSingleObject(HANDLE h, DWORD ms);
DWORD  WaitForSingleObjectEx(HANDLE h, DWORD ms, BOOL alertable);
DWORD  WaitForMultipleObjects(DWORD n, const HANDLE* hs, BOOL waitAll, DWORD ms);
DWORD  WaitForMultipleObjectsEx(DWORD n, const HANDLE* hs, BOOL waitAll, DWORD ms, BOOL alertable);
DWORD  SignalObjectAndWait(HANDLE sig, HANDLE wait, DWORD ms, BOOL alertable);
DWORD  MsgWaitForMultipleObjects(DWORD n, const HANDLE* hs, BOOL waitAll, DWORD ms, DWORD wakeMask);
DWORD  MsgWaitForMultipleObjectsEx(DWORD n, const HANDLE* hs, DWORD ms, DWORD wakeMask, DWORD flags);

HANDLE CreateEventW(LPSECURITY_ATTRIBUTES sa, BOOL manualReset, BOOL initialState, LPCWSTR name);
HANDLE CreateEventA(LPSECURITY_ATTRIBUTES sa, BOOL manualReset, BOOL initialState, const char* nameA);
HANDLE CreateEventExW(LPSECURITY_ATTRIBUTES sa, LPCWSTR name, DWORD flags, DWORD access);
HANDLE OpenEventW(DWORD access, BOOL inherit, LPCWSTR name);
HANDLE OpenEventA(DWORD access, BOOL inherit, const char* name);
BOOL   SetEvent(HANDLE h);
BOOL   ResetEvent(HANDLE h);
BOOL   PulseEvent(HANDLE h);
HANDLE CreateMutexW(LPSECURITY_ATTRIBUTES sa, BOOL initialOwner, LPCWSTR name);
HANDLE CreateMutexA(LPSECURITY_ATTRIBUTES sa, BOOL initialOwner, const char* name);
HANDLE OpenMutexW(DWORD access, BOOL inherit, LPCWSTR name);
BOOL   ReleaseMutex(HANDLE h);
HANDLE CreateSemaphoreW(LPSECURITY_ATTRIBUTES sa, LONG initial, LONG maximum, LPCWSTR name);
HANDLE CreateSemaphoreA(LPSECURITY_ATTRIBUTES sa, LONG initial, LONG maximum, const char* name);
HANDLE OpenSemaphoreW(DWORD access, BOOL inherit, LPCWSTR name);
BOOL   ReleaseSemaphore(HANDLE h, LONG release, PLONG prev);

HANDLE CreateThread(LPSECURITY_ATTRIBUTES sa, SIZE_T stackSize, LPTHREAD_START_ROUTINE start,
                    LPVOID param, DWORD flags, LPDWORD threadId);
void   ExitThread(DWORD exitCode);
BOOL   TerminateThread(HANDLE h, DWORD exitCode);
DWORD  GetCurrentThreadId(void);
HANDLE GetCurrentThread(void);
HANDLE GetCurrentProcess(void);
DWORD  GetCurrentProcessId(void);
DWORD  GetThreadId(HANDLE h);
DWORD  GetProcessId(HANDLE h);
DWORD  SuspendThread(HANDLE h);
DWORD  ResumeThread(HANDLE h);
BOOL   GetExitCodeThread(HANDLE h, LPDWORD code);
BOOL   GetExitCodeProcess(HANDLE h, LPDWORD code);
BOOL   SetThreadPriority(HANDLE h, int prio);
int    GetThreadPriority(HANDLE h);
ULONG_PTR SetThreadAffinityMask(HANDLE h, ULONG_PTR mask);
BOOL   GetProcessAffinityMask(HANDLE h, ULONG_PTR* proc, ULONG_PTR* sys);
BOOL   SetProcessAffinityMask(HANDLE h, ULONG_PTR mask);
BOOL   SetPriorityClass(HANDLE h, DWORD cls);
DWORD  GetPriorityClass(HANDLE h);
DWORD  SetThreadExecutionState(DWORD flags);
HANDLE OpenProcess(DWORD access, BOOL inherit, DWORD pid);
void   FreeLibraryAndExitThread(HMODULE m, DWORD code);

void   InitializeCriticalSection(PCRITICAL_SECTION cs);
BOOL   InitializeCriticalSectionAndSpinCount(PCRITICAL_SECTION cs, DWORD spin);
BOOL   InitializeCriticalSectionEx(PCRITICAL_SECTION cs, DWORD spin, DWORD flags);
DWORD  SetCriticalSectionSpinCount(PCRITICAL_SECTION cs, DWORD spin);
void   EnterCriticalSection(PCRITICAL_SECTION cs);
BOOL   TryEnterCriticalSection(PCRITICAL_SECTION cs);
void   LeaveCriticalSection(PCRITICAL_SECTION cs);
void   DeleteCriticalSection(PCRITICAL_SECTION cs);

void   InitializeSRWLock(PSRWLOCK l);
void   AcquireSRWLockExclusive(PSRWLOCK l);
void   ReleaseSRWLockExclusive(PSRWLOCK l);
void   AcquireSRWLockShared(PSRWLOCK l);
void   ReleaseSRWLockShared(PSRWLOCK l);
BOOLEAN TryAcquireSRWLockExclusive(PSRWLOCK l);
BOOLEAN TryAcquireSRWLockShared(PSRWLOCK l);
void   InitializeConditionVariable(PCONDITION_VARIABLE cv);
BOOL   SleepConditionVariableCS(PCONDITION_VARIABLE cv, PCRITICAL_SECTION cs, DWORD ms);
BOOL   SleepConditionVariableSRW(PCONDITION_VARIABLE cv, PSRWLOCK l, DWORD ms, ULONG flags);
void   WakeConditionVariable(PCONDITION_VARIABLE cv);
void   WakeAllConditionVariable(PCONDITION_VARIABLE cv);
BOOL   InitOnceBeginInitialize(PINIT_ONCE once, DWORD flags, BOOL* pending, LPVOID* ctx);
BOOL   InitOnceComplete(PINIT_ONCE once, DWORD flags, LPVOID ctx);
BOOL   InitOnceExecuteOnce(PINIT_ONCE once, PINIT_ONCE_FN fn, LPVOID param, LPVOID* ctx);

void   InitializeSListHead(void* head);
void*  InterlockedPushEntrySList(void* head, void* entry);
void*  InterlockedPopEntrySList(void* head);
void*  InterlockedFlushSList(void* head);
WORD   QueryDepthSList(void* head);

void   MemoryBarrier(void);
LONG   InterlockedIncrement(volatile LONG* v);
LONG   InterlockedDecrement(volatile LONG* v);
LONG   InterlockedExchange(volatile LONG* v, LONG newVal);
LONG   InterlockedExchangeAdd(volatile LONG* v, LONG add);
LONG   InterlockedCompareExchange(volatile LONG* v, LONG xchg, LONG cmp);
LONG   InterlockedAnd(volatile LONG* v, LONG m);
LONG   InterlockedOr(volatile LONG* v, LONG m);
LONG   InterlockedXor(volatile LONG* v, LONG m);
LONGLONG InterlockedIncrement64(volatile LONGLONG* v);
LONGLONG InterlockedDecrement64(volatile LONGLONG* v);
LONGLONG InterlockedExchange64(volatile LONGLONG* v, LONGLONG n);
LONGLONG InterlockedExchangeAdd64(volatile LONGLONG* v, LONGLONG a);
LONGLONG InterlockedCompareExchange64(volatile LONGLONG* v, LONGLONG xchg, LONGLONG cmp);
PVOID  InterlockedExchangePointer(volatile PVOID* v, PVOID n);
PVOID  InterlockedCompareExchangePointer(volatile PVOID* v, PVOID xchg, PVOID cmp);

DWORD  TlsAlloc(void);
BOOL   TlsFree(DWORD idx);
LPVOID TlsGetValue(DWORD idx);
BOOL   TlsSetValue(DWORD idx, LPVOID val);
DWORD  FlsAlloc(PFLS_CALLBACK_FUNCTION cb);
BOOL   FlsFree(DWORD idx);
PVOID  FlsGetValue(DWORD idx);
BOOL   FlsSetValue(DWORD idx, PVOID val);

HANDLE CreateTimerQueue(void);
BOOL   DeleteTimerQueueEx(HANDLE q, HANDLE completion);
BOOL   CreateTimerQueueTimer(LPHANDLE timer, HANDLE queue, WAITORTIMERCALLBACK cb, PVOID param,
                             DWORD due, DWORD period, ULONG flags);
BOOL   ChangeTimerQueueTimer(HANDLE queue, HANDLE timer, ULONG due, ULONG period);
BOOL   DeleteTimerQueueTimer(HANDLE queue, HANDLE timer, HANDLE completion);

/* =============================================================
 * 時刻
 * ============================================================= */
void   GetSystemTimeAsFileTime(FILETIME* ft);
void   GetSystemTime(SYSTEMTIME* st);
void   GetLocalTime(SYSTEMTIME* st);
BOOL   SystemTimeToFileTime(const SYSTEMTIME* st, FILETIME* ft);
BOOL   FileTimeToSystemTime(const FILETIME* ft, SYSTEMTIME* st);
BOOL   FileTimeToLocalFileTime(const FILETIME* ft, FILETIME* out);
BOOL   LocalFileTimeToFileTime(const FILETIME* ft, FILETIME* out);
BOOL   SystemTimeToTzSpecificLocalTime(const TIME_ZONE_INFORMATION* tz, const SYSTEMTIME* u, SYSTEMTIME* l);
BOOL   TzSpecificLocalTimeToSystemTime(const TIME_ZONE_INFORMATION* tz, const SYSTEMTIME* l, SYSTEMTIME* u);
DWORD  GetTimeZoneInformation(TIME_ZONE_INFORMATION* tz);
BOOL   GetTimeZoneInformationForYear(WORD year, void* dtzi, TIME_ZONE_INFORMATION* tz);
LONG   CompareFileTime(const FILETIME* a, const FILETIME* b);
BOOL   DosDateTimeToFileTime(WORD date, WORD time, FILETIME* ft);
BOOL   FileTimeToDosDateTime(const FILETIME* ft, WORD* date, WORD* time);
int    GetDateFormatW(LCID loc, DWORD flags, const SYSTEMTIME* st, LPCWSTR fmt, LPWSTR out, int cch);
int    GetTimeFormatW(LCID loc, DWORD flags, const SYSTEMTIME* st, LPCWSTR fmt, LPWSTR out, int cch);

/* =============================================================
 * ファイル / ディレクトリ / パス / マッピング
 * ============================================================= */
HANDLE CreateFileW(LPCWSTR fileName, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa,
                   DWORD disp, DWORD flagsAttr, HANDLE tmpl);
HANDLE CreateFileA(LPCSTR fileName, DWORD access, DWORD share, LPSECURITY_ATTRIBUTES sa,
                   DWORD disp, DWORD flagsAttr, HANDLE tmpl);
BOOL   ReadFile(HANDLE h, LPVOID buf, DWORD n, LPDWORD out, LPOVERLAPPED ov);
BOOL   WriteFile(HANDLE h, LPCVOID buf, DWORD n, LPDWORD out, LPOVERLAPPED ov);
DWORD  SetFilePointer(HANDLE h, LONG lo, PLONG hi, DWORD method);
BOOL   SetFilePointerEx(HANDLE h, LARGE_INTEGER dist, PLARGE_INTEGER newPos, DWORD method);
BOOL   SetEndOfFile(HANDLE h);
DWORD  GetFileSize(HANDLE h, LPDWORD hi);
BOOL   GetFileSizeEx(HANDLE h, PLARGE_INTEGER size);
DWORD  GetFileType(HANDLE h);
BOOL   GetFileInformationByHandle(HANDLE h, BY_HANDLE_FILE_INFORMATION* info);
BOOL   FlushFileBuffers(HANDLE h);
BOOL   SetFileTime(HANDLE h, const FILETIME* c, const FILETIME* a, const FILETIME* w);
BOOL   GetFileTime(HANDLE h, FILETIME* c, FILETIME* a, FILETIME* w);
BOOL   LockFile(HANDLE h, DWORD lo, DWORD hi, DWORD nlo, DWORD nhi);
BOOL   UnlockFile(HANDLE h, DWORD lo, DWORD hi, DWORD nlo, DWORD nhi);
BOOL   LockFileEx(HANDLE h, DWORD flags, DWORD rsv, DWORD nlo, DWORD nhi, LPOVERLAPPED ov);
BOOL   UnlockFileEx(HANDLE h, DWORD rsv, DWORD nlo, DWORD nhi, LPOVERLAPPED ov);
BOOL   DeleteFileW(LPCWSTR p);
BOOL   DeleteFileA(LPCSTR p);
BOOL   CopyFileW(LPCWSTR from, LPCWSTR to, BOOL failIfExists);
BOOL   MoveFileW(LPCWSTR from, LPCWSTR to);
BOOL   MoveFileExW(LPCWSTR from, LPCWSTR to, DWORD flags);
BOOL   CreateDirectoryW(LPCWSTR p, LPSECURITY_ATTRIBUTES sa);
BOOL   RemoveDirectoryW(LPCWSTR p);
DWORD  GetFileAttributesW(LPCWSTR p);
DWORD  GetFileAttributesA(LPCSTR p);
BOOL   GetFileAttributesExW(LPCWSTR p, uint64_t level, LPVOID info);
BOOL   SetFileAttributesW(LPCWSTR p, DWORD attr);
DWORD  GetFullPathNameW(LPCWSTR p, DWORD n, LPWSTR buf, LPWSTR* filePart);
DWORD  GetFullPathNameA(LPCSTR p, DWORD n, LPSTR buf, LPSTR* filePart);
DWORD  GetTempPathW(DWORD n, LPWSTR buf);
DWORD  GetTempPathA(DWORD n, LPSTR buf);
UINT   GetTempFileNameW(LPCWSTR dir, LPCWSTR prefix, UINT unique, LPWSTR out);
DWORD  GetCurrentDirectoryW(DWORD n, LPWSTR buf);
BOOL   SetCurrentDirectoryW(LPCWSTR p);
DWORD  GetLogicalDrives(void);
DWORD  GetLogicalDriveStringsW(DWORD n, LPWSTR buf);
UINT   GetDriveTypeW(LPCWSTR root);
BOOL   GetVolumeInformationW(LPCWSTR root, LPWSTR label, DWORD labelN, LPDWORD serial,
                             LPDWORD maxComp, LPDWORD flags, LPWSTR fsName, DWORD fsN);
BOOL   GetDiskFreeSpaceW(LPCWSTR root, LPDWORD spc, LPDWORD bps, LPDWORD freeC, LPDWORD totC);
BOOL   GetDiskFreeSpaceA(LPCSTR root, LPDWORD spc, LPDWORD bps, LPDWORD freeC, LPDWORD totC);
DWORD  QueryDosDeviceW(LPCWSTR dev, LPWSTR target, DWORD n);
BOOL   SetVolumeLabelW(LPCWSTR root, LPCWSTR label);
HANDLE FindFirstFileW(LPCWSTR pat, WIN32_FIND_DATAW* fd);
HANDLE FindFirstFileExW(LPCWSTR pat, int infoLevel, LPVOID fd, int searchOp, LPVOID filter, DWORD flags);
BOOL   FindNextFileW(HANDLE h, WIN32_FIND_DATAW* fd);
BOOL   FindClose(HANDLE h);
HANDLE CreateFileMappingW(HANDLE file, LPSECURITY_ATTRIBUTES sa, DWORD prot, DWORD hi, DWORD lo, LPCWSTR name);
HANDLE CreateFileMappingA(HANDLE file, LPSECURITY_ATTRIBUTES sa, DWORD prot, DWORD hi, DWORD lo, LPCSTR name);
HANDLE OpenFileMappingW(DWORD access, BOOL inherit, LPCWSTR name);
LPVOID MapViewOfFile(HANDLE m, DWORD access, DWORD offHi, DWORD offLo, SIZE_T n);
BOOL   UnmapViewOfFile(LPCVOID p);
BOOL   FlushViewOfFile(LPCVOID p, SIZE_T n);
DWORD  GetFinalPathNameByHandleW(HANDLE h, LPWSTR out, DWORD n, DWORD flags);
BOOL   CreateSymbolicLinkW(LPCWSTR link, LPCWSTR target, DWORD flags);
BOOL   DeviceIoControl(HANDLE h, DWORD code, LPVOID in, DWORD inN, LPVOID out, DWORD outN, LPDWORD ret, LPOVERLAPPED ov);
BOOL   ReadDirectoryChangesW(HANDLE h, LPVOID buf, DWORD n, BOOL sub, DWORD filter, LPDWORD ret, LPOVERLAPPED ov, LPVOID cr);
BOOL   PeekNamedPipe(HANDLE h, LPVOID buf, DWORD n, LPDWORD read, LPDWORD avail, LPDWORD left);
DWORD  GetPrivateProfileStringW(LPCWSTR sec, LPCWSTR key, LPCWSTR def, LPWSTR out, DWORD n, LPCWSTR file);
UINT   GetPrivateProfileIntW(LPCWSTR sec, LPCWSTR key, int def, LPCWSTR file);
BOOL   WritePrivateProfileStringW(LPCWSTR sec, LPCWSTR key, LPCWSTR val, LPCWSTR file);
HANDLE GetStdHandle(DWORD which);
BOOL   SetStdHandle(DWORD which, HANDLE h);
BOOL   GetConsoleMode(HANDLE h, LPDWORD mode);
UINT   GetConsoleCP(void);
UINT   GetConsoleOutputCP(void);
BOOL   WriteConsoleW(HANDLE h, LPCVOID buf, DWORD n, LPDWORD written, LPVOID rsv);
BOOL   ReadConsoleW(HANDLE h, LPVOID buf, DWORD n, LPDWORD read, LPVOID ctl);
BOOL   AreFileApisANSI(void);
BOOL   PathCleanupSpec(LPWSTR path, LPWSTR spec);

/* =============================================================
 * heap / Global / Local / Virtual
 * ============================================================= */
HEAP_HANDLE GetProcessHeap(void);
HEAP_HANDLE HeapCreate(DWORD flags, SIZE_T initial, SIZE_T maximum);
BOOL        HeapDestroy(HEAP_HANDLE heap);
LPVOID      HeapAlloc(HEAP_HANDLE heap, DWORD flags, SIZE_T bytes);
LPVOID      HeapReAlloc(HEAP_HANDLE heap, DWORD flags, LPVOID p, SIZE_T bytes);
BOOL        HeapFree(HEAP_HANDLE heap, DWORD flags, LPVOID p);
SIZE_T      HeapSize(HEAP_HANDLE heap, DWORD flags, LPCVOID p);
BOOL        HeapValidate(HEAP_HANDLE heap, DWORD flags, LPCVOID p);
SIZE_T      HeapCompact(HEAP_HANDLE heap, DWORD flags);
BOOL        HeapLock(HEAP_HANDLE heap);
BOOL        HeapUnlock(HEAP_HANDLE heap);
BOOL        HeapSetInformation(HEAP_HANDLE heap, int cls, PVOID info, SIZE_T n);
HGLOBAL     GlobalAlloc(DWORD flags, SIZE_T bytes);
HGLOBAL     GlobalReAlloc(HGLOBAL h, SIZE_T bytes, DWORD flags);
LPVOID      GlobalLock(HGLOBAL h);
BOOL        GlobalUnlock(HGLOBAL h);
HGLOBAL     GlobalFree(HGLOBAL h);
SIZE_T      GlobalSize(HGLOBAL h);
UINT        GlobalFlags(HGLOBAL h);
HGLOBAL     GlobalHandle(LPCVOID p);
HLOCAL      LocalAlloc(DWORD flags, SIZE_T bytes);
HLOCAL      LocalReAlloc(HLOCAL h, SIZE_T bytes, DWORD flags);
HLOCAL      LocalFree(HLOCAL h);
SIZE_T      LocalSize(HLOCAL h);
LPVOID      LocalLock(HLOCAL h);
BOOL        LocalUnlock(HLOCAL h);
void        GlobalMemoryStatus(MEMORYSTATUS64* ms);
BOOL        GlobalMemoryStatusEx(MEMORYSTATUSEX* ms);
LPVOID      VirtualAlloc(LPVOID addr, SIZE_T size, DWORD type, DWORD prot);
BOOL        VirtualFree(LPVOID addr, SIZE_T size, DWORD type);
BOOL        VirtualProtect(LPVOID addr, SIZE_T size, DWORD prot, LPDWORD old);
SIZE_T      VirtualQuery(LPCVOID addr, MEMORY_BASIC_INFORMATION64* mbi, SIZE_T len);
SIZE_T      VirtualQueryEx(HANDLE proc, LPCVOID addr, MEMORY_BASIC_INFORMATION64* mbi, SIZE_T len);
BOOL        IsBadWritePtr(LPVOID p, SIZE_T n);
BOOL        IsBadReadPtr(LPCVOID p, SIZE_T n);

/* =============================================================
 * 文字列 / ロケール / コードページ
 * ============================================================= */
int    MultiByteToWideChar(UINT cp, DWORD flags, LPCSTR mb, int cbMb, LPWSTR wc, int cchWc);
int    WideCharToMultiByte(UINT cp, DWORD flags, LPCWSTR wc, int cchWc, LPSTR mb, int cbMb,
                           LPCSTR defChar, BOOL* usedDef);
int    lstrlenW(LPCWSTR s);
int    lstrlenA(LPCSTR s);
int    lstrcmpA(LPCSTR a, LPCSTR b);
int    lstrcmpW(LPCWSTR a, LPCWSTR b);
int    lstrcmpiA(LPCSTR a, LPCSTR b);
int    lstrcmpiW(LPCWSTR a, LPCWSTR b);
LPWSTR lstrcpyW(LPWSTR d, LPCWSTR s);
LPWSTR lstrcpynW(LPWSTR d, LPCWSTR s, int n);
LPSTR  lstrcpyA(LPSTR d, LPCSTR s);
LPWSTR lstrcatW(LPWSTR d, LPCWSTR s);
int    MulDiv(int n, int num, int den);
int    CompareStringW(LCID loc, DWORD flags, LPCWSTR a, int na, LPCWSTR b, int nb);
int    CompareStringA(LCID loc, DWORD flags, LPCSTR a, int na, LPCSTR b, int nb);
int    CompareStringEx(LPCWSTR loc, DWORD flags, LPCWSTR a, int na, LPCWSTR b, int nb, LPVOID v, LPVOID r, LPARAM_T l);
int    LCMapStringW(LCID loc, DWORD flags, LPCWSTR src, int cch, LPWSTR dst, int cchDst);
int    LCMapStringEx(LPCWSTR loc, DWORD flags, LPCWSTR src, int cch, LPWSTR dst, int cchDst, LPVOID v, LPVOID r, LPARAM_T l);
BOOL   GetStringTypeW(DWORD type, LPCWSTR src, int cch, WORD* out);
int    GetLocaleInfoW(LCID loc, LCTYPE type, LPWSTR out, int cch);
int    GetLocaleInfoEx(LPCWSTR name, LCTYPE type, LPWSTR out, int cch);
BOOL   EnumSystemLocalesW(LOCALE_ENUMPROCW cb, DWORD flags);
BOOL   EnumCalendarInfoW(CALINFO_ENUMPROCW cb, LCID loc, DWORD cal, DWORD type);
BOOL   IsValidLocale(LCID loc, DWORD flags);
BOOL   IsValidCodePage(UINT cp);
LCID   GetUserDefaultLCID(void);
LCID   GetThreadLocale(void);
BOOL   SetThreadLocale(LCID loc);
LANGID GetSystemDefaultUILanguage(void);
LANGID GetUserDefaultUILanguage(void);
LANGID GetThreadUILanguage(void);
BOOL   GetThreadPreferredUILanguages(DWORD flags, ULONG* num, LPWSTR buf, ULONG* cch);
BOOL   SetThreadPreferredUILanguages(DWORD flags, LPCWSTR buf, ULONG* num);
LCID   LocaleNameToLCID(LPCWSTR name, DWORD flags);
int    GetSystemDefaultLocaleName(LPWSTR out, int cch);
BOOL   GetUserPreferredUILanguages(DWORD flags, ULONG* num, LPWSTR buf, ULONG* cch);
UINT   GetACP(void);
UINT   GetOEMCP(void);
BOOL   GetCPInfo(UINT cp, LPCPINFO info);
BOOL   GetCPInfoExW(UINT cp, DWORD flags, LPCPINFOEXW info);
BOOL   IsDBCSLeadByteEx(UINT cp, BYTE c);
int    NormalizeString(int form, LPCWSTR src, int cch, LPWSTR dst, int cchDst);
DWORD  FormatMessageW(DWORD flags, LPCVOID src, DWORD msgId, DWORD langId, LPWSTR buf, DWORD n, void* args);
DWORD  FormatMessageA(DWORD flags, LPCVOID src, DWORD msgId, DWORD langId, LPSTR buf, DWORD n, void* args);
LPWSTR CharUpperW(LPWSTR s);
LPWSTR CharLowerW(LPWSTR s);
DWORD  CharUpperBuffW(LPWSTR s, DWORD n);
DWORD  CharLowerBuffW(LPWSTR s, DWORD n);
LPWSTR CharNextW(LPCWSTR s);
LPSTR  CharNextExA(WORD cp, LPCSTR s, DWORD flags);
BOOL   CharToOemBuffW(LPCWSTR src, LPSTR dst, DWORD n);
uint32_t shimx_towlower(uint32_t c);
uint32_t shimx_towupper(uint32_t c);
int    shimx_utf16_to_utf8(const WCHAR* w, int nw, char* out, size_t outSize); /* nw<0: NUL終端, 戻り=バイト数(NUL含まず), -1=エラー */
int    shimx_utf8_to_utf16(const char* s, int ns, WCHAR* out, size_t outCch);  /* 戻り=WCHAR数 */

/* =============================================================
 * レジストリ (メモリ内)
 * ============================================================= */
LSTATUS RegOpenKeyExW(HKEY k, LPCWSTR sub, DWORD opt, REGSAM sam, PHKEY out);
LSTATUS RegOpenKeyExA(HKEY k, LPCSTR sub, DWORD opt, REGSAM sam, PHKEY out);
LSTATUS RegOpenKeyW(HKEY k, LPCWSTR sub, PHKEY out);
LSTATUS RegCreateKeyExW(HKEY k, LPCWSTR sub, DWORD rsv, LPWSTR cls, DWORD opt, REGSAM sam,
                        LPVOID sa, PHKEY out, LPDWORD disp);
LSTATUS RegCreateKeyExA(HKEY k, LPCSTR sub, DWORD rsv, LPSTR cls, DWORD opt, REGSAM sam,
                        LPVOID sa, PHKEY out, LPDWORD disp);
LSTATUS RegCreateKeyW(HKEY k, LPCWSTR sub, PHKEY out);
LSTATUS RegCloseKey(HKEY k);
LSTATUS RegFlushKey(HKEY k);
LSTATUS RegQueryValueExW(HKEY k, LPCWSTR name, LPDWORD rsv, LPDWORD type, LPBYTE data, LPDWORD cb);
LSTATUS RegQueryValueExA(HKEY k, LPCSTR name, LPDWORD rsv, LPDWORD type, LPBYTE data, LPDWORD cb);
LSTATUS RegGetValueW(HKEY k, LPCWSTR sub, LPCWSTR name, DWORD flags, LPDWORD type, PVOID data, LPDWORD cb);
LSTATUS RegSetValueExW(HKEY k, LPCWSTR name, DWORD rsv, DWORD type, const BYTE* data, DWORD cb);
LSTATUS RegSetValueExA(HKEY k, LPCSTR name, DWORD rsv, DWORD type, const BYTE* data, DWORD cb);
LSTATUS RegDeleteValueW(HKEY k, LPCWSTR name);
LSTATUS RegDeleteValueA(HKEY k, LPCSTR name);
LSTATUS RegDeleteKeyW(HKEY k, LPCWSTR sub);
LSTATUS RegDeleteKeyA(HKEY k, LPCSTR sub);
LSTATUS RegDeleteKeyExW(HKEY k, LPCWSTR sub, REGSAM sam, DWORD rsv);
LSTATUS RegEnumKeyExW(HKEY k, DWORD idx, LPWSTR name, LPDWORD cchName, LPDWORD rsv, LPWSTR cls,
                      LPDWORD cchCls, FILETIME* lastWrite);
LSTATUS RegEnumKeyExA(HKEY k, DWORD idx, LPSTR name, LPDWORD cchName, LPDWORD rsv, LPSTR cls,
                      LPDWORD cchCls, FILETIME* lastWrite);
LSTATUS RegEnumValueW(HKEY k, DWORD idx, LPWSTR name, LPDWORD cchName, LPDWORD rsv, LPDWORD type,
                      LPBYTE data, LPDWORD cb);
LSTATUS RegEnumValueA(HKEY k, DWORD idx, LPSTR name, LPDWORD cchName, LPDWORD rsv, LPDWORD type,
                      LPBYTE data, LPDWORD cb);
LSTATUS RegQueryInfoKeyW(HKEY k, LPWSTR cls, LPDWORD cchCls, LPDWORD rsv, LPDWORD nSub, LPDWORD maxSub,
                         LPDWORD maxCls, LPDWORD nVal, LPDWORD maxValName, LPDWORD maxValData,
                         LPDWORD secDesc, FILETIME* lastWrite);
/* vreg 拡張の追加 6 API (CAB-94/CAB-214 取込) */
LSTATUS RegGetValueA(HKEY k, LPCSTR sub, LPCSTR name, DWORD flags, LPDWORD type, PVOID data, LPDWORD cb);
LSTATUS RegEnumKeyW(HKEY k, DWORD idx, LPWSTR name, DWORD cch);
LSTATUS RegDeleteTreeW(HKEY k, LPCWSTR sub);
LSTATUS RegSetKeyValueW(HKEY k, LPCWSTR sub, LPCWSTR name, DWORD type, LPCVOID data, DWORD cb);
LSTATUS RegDeleteKeyValueW(HKEY k, LPCWSTR sub, LPCWSTR name);
LSTATUS RegQueryInfoKeyA(HKEY k, LPSTR cls, LPDWORD cchCls, LPDWORD rsv, LPDWORD nSub, LPDWORD maxSub, LPDWORD maxCls,
                         LPDWORD nVal, LPDWORD maxValName, LPDWORD maxValData, LPDWORD secDesc, FILETIME* lastWrite);
BOOL    OpenProcessToken(HANDLE proc, DWORD access, LPHANDLE tok);
BOOL    GetTokenInformation(HANDLE tok, int cls, LPVOID info, DWORD n, LPDWORD ret);
/* シード / 永続化 API (shimx 独自) */
int     shimx_reg_set(const char* path, const char* name, DWORD type, const void* data, DWORD cb);
int     shimx_reg_set_sz(const char* path, const char* name, const char* utf8);
int     shimx_reg_set_dword(const char* path, const char* name, DWORD v);
int     shimx_reg_import_text(const char* text);
char*   shimx_reg_export_text(void);    /* malloc 済み。free() すること */
void    shimx_reg_reset(void);
void    shimx_reg_stats(int* nKeys, int* nValues);
/* vreg 運用フック (CAB-94 で導入, CAB-214 で shimx 本体に取込。名前は vreg JS 側の
 * EXPORTED_FUNCTIONS (_vreg_generation 等) との互換のため vreg_ 接頭辞を維持) */
uint32_t vreg_generation(void);                    /* 変更世代 (値/キーの作成・削除・更新で増加) */
void     vreg_set_notify(void (*cb)(uint32_t gen));/* 変更通知 (Reg* を呼んだスレッドで、内部ロック解放後に同期呼出) */
char*    vreg_export_root(int root);               /* 0=HKCR 1=HKCU 2=HKLM 3=HKU 4=HKCC を .reg 形式 (UTF-8, LF) で。free() すること */
void     vreg_clear_root(int root);                /* 指定ルート配下を空にする (seed 再投入前に使用) */
void     vreg_clear_all(void);                     /* 全ルートを空にする (shimx 内蔵 seed も消す) */

/* =============================================================
 * モジュール / プロセス / 環境 / システム情報
 * ============================================================= */
HMODULE GetModuleHandleW(LPCWSTR name);
HMODULE GetModuleHandleA(LPCSTR name);
BOOL    GetModuleHandleExW(DWORD flags, LPCWSTR name, HMODULE* out);
DWORD   GetModuleFileNameW(HMODULE m, LPWSTR buf, DWORD n);
DWORD   GetModuleFileNameA(HMODULE m, LPSTR buf, DWORD n);
HMODULE LoadLibraryW(LPCWSTR name);
HMODULE LoadLibraryA(LPCSTR name);
HMODULE LoadLibraryExW(LPCWSTR name, HANDLE file, DWORD flags);
BOOL    FreeLibrary(HMODULE m);
void*   GetProcAddress(HMODULE m, LPCSTR name);
BOOL    SetDllDirectoryW(LPCWSTR p);
LPCWSTR GetCommandLineW(void);
LPCSTR  GetCommandLineA(void);
void    GetStartupInfoW(STARTUPINFOW64* si);
DWORD   GetEnvironmentVariableW(LPCWSTR name, LPWSTR buf, DWORD n);
BOOL    SetEnvironmentVariableW(LPCWSTR name, LPCWSTR val);
DWORD   ExpandEnvironmentStringsW(LPCWSTR src, LPWSTR dst, DWORD n);
LPWSTR  GetEnvironmentStringsW(void);
BOOL    FreeEnvironmentStringsW(LPWSTR p);
void    GetSystemInfo(SYSTEM_INFO64* si);
void    GetNativeSystemInfo(SYSTEM_INFO64* si);
DWORD   GetVersion(void);
BOOL    GetVersionExW(OSVERSIONINFOEXW* vi);
BOOL    VerifyVersionInfoW(OSVERSIONINFOEXW* vi, DWORD mask, ULONGLONG cond);
ULONGLONG VerSetConditionMask(ULONGLONG cond, DWORD typeMask, BYTE op);
BOOL    GetComputerNameW(LPWSTR buf, LPDWORD n);
BOOL    GetComputerNameExW(uint64_t type, LPWSTR buf, LPDWORD n);   /* enum 引数は RetDec 署名 (i64) */
BOOL    IsWow64Process(HANDLE h, BOOL* wow);
BOOL    GetLogicalProcessorInformation(void* buf, LPDWORD len);
UINT    SetErrorMode(UINT mode);
DWORD   SetThreadErrorMode(DWORD mode, LPDWORD old);
UINT    GetSystemDirectoryW(LPWSTR buf, UINT n);
UINT    GetWindowsDirectoryW(LPWSTR buf, UINT n);
void    OutputDebugStringW(LPCWSTR s);
void    OutputDebugStringA(LPCSTR s);
BOOL    IsDebuggerPresent(void);
BOOL    IsProcessorFeaturePresent(DWORD feature);
void    ExitProcess(UINT code);
BOOL    TerminateProcess(HANDLE h, UINT code);
BOOL    CreateProcessW(LPCWSTR app, LPWSTR cmd, LPVOID pa, LPVOID ta, BOOL inherit, DWORD flags,
                       LPVOID env, LPCWSTR dir, LPVOID si, PROCESS_INFORMATION64* pi);
BOOL    AssignProcessToJobObject(HANDLE job, HANDLE proc);
HRSRC   FindResourceW(HMODULE m, LPCWSTR name, LPCWSTR type);
HRSRC   FindResourceA(HMODULE m, LPCSTR name, LPCSTR type);
HGLOBAL LoadResource(HMODULE m, HRSRC r);
LPVOID  LockResource(HGLOBAL h);
DWORD   SizeofResource(HMODULE m, HRSRC r);
BOOL    FreeResource(HGLOBAL h);
ATOM    AddAtomW(LPCWSTR s);
ATOM    FindAtomW(LPCWSTR s);
ATOM    DeleteAtom(ATOM a);
ATOM    GlobalAddAtomW(LPCWSTR s);
ATOM    GlobalFindAtomW(LPCWSTR s);
ATOM    GlobalDeleteAtom(ATOM a);
PVOID   EncodePointer(PVOID p);
PVOID   DecodePointer(PVOID p);
DWORD   GetLastError(void);
void    SetLastError(DWORD e);

/* 例外 (SEH 第一手: スタブ + フック) */
void    RaiseException(DWORD code, DWORD flags, DWORD nargs, const uint64_t* args);   /* args は Win64 の 8B 要素 */
void    RtlUnwind(PVOID targetFrame, PVOID targetIp, EXCEPTION_RECORD64* rec, PVOID retval);
void    RtlUnwindEx(PVOID targetFrame, PVOID targetIp, EXCEPTION_RECORD64* rec, PVOID retval, PVOID ctx, PVOID hist);
PVOID   AddVectoredExceptionHandler(ULONG first, PVECTORED_EXCEPTION_HANDLER h);
ULONG   RemoveVectoredExceptionHandler(PVOID h);
LPTOP_LEVEL_EXCEPTION_FILTER SetUnhandledExceptionFilter(LPTOP_LEVEL_EXCEPTION_FILTER f);
LONG    UnhandledExceptionFilter(EXCEPTION_POINTERS64* ep);
void    RtlCaptureContext(PVOID ctx);
PVOID   RtlLookupFunctionEntry(DWORD64 pc, DWORD64* base, PVOID hist);
PVOID   RtlVirtualUnwind(DWORD type, DWORD64 base, DWORD64 pc, PVOID fe, PVOID ctx, PVOID* hdata,
                         DWORD64* frame, PVOID ctxptrs);
PVOID   RtlPcToFileHeader(PVOID pc, PVOID* base);
uint64_t __readgsqword(uint64_t off);
uint32_t __readgsdword(uint64_t off);
uint16_t __readgsword(uint64_t off);
uint8_t  __readgsbyte(uint64_t off);
void     __writegsqword(uint64_t off, uint64_t v);
void     __writegsdword(uint64_t off, uint32_t v);

/* CRT ロック群 (msvcrt/ucrt 互換) */
void    _lock(int n);
void    _unlock(int n);
void    _mlock(int n);
void    _munlock(int n);
void    _lock_file(void* fp);
void    _unlock_file(void* fp);
void    __acrt_lock(int n);
void    __acrt_unlock(int n);
void    _amsg_exit(int n);

/* =============================================================
 * ole32 / oleaut32
 * ============================================================= */
typedef struct _GUID { DWORD Data1; WORD Data2; WORD Data3; BYTE Data4[8]; } GUID, CLSID, IID;
typedef WCHAR* BSTR;
HRESULT CoInitialize(LPVOID rsv);
HRESULT CoInitializeEx(LPVOID rsv, DWORD flags);
void    CoUninitialize(void);
HRESULT OleInitialize(LPVOID rsv);
void    OleUninitialize(void);
LPVOID  CoTaskMemAlloc(SIZE_T n);
LPVOID  CoTaskMemRealloc(LPVOID p, SIZE_T n);
void    CoTaskMemFree(LPVOID p);
HRESULT CoCreateInstance(uint64_t clsid, LPVOID outer, DWORD ctx, const GUID* iid, LPVOID* out);
HRESULT CoGetClassObject(const GUID* clsid, DWORD ctx, LPVOID srv, const GUID* iid, LPVOID* out);
HRESULT CoCreateGuid(GUID* g);
BOOL    IsEqualGUID(const GUID* a, const GUID* b);
HRESULT CLSIDFromString(LPCWSTR s, GUID* g);
int     StringFromGUID2(const GUID* g, LPWSTR out, int cch);
HRESULT StringFromCLSID(const GUID* g, LPWSTR* out);
HRESULT ProgIDFromCLSID(const GUID* g, LPWSTR* out);
HRESULT CoGetInterfaceAndReleaseStream(LPVOID stm, const GUID* iid, LPVOID* out);
HRESULT CoMarshalInterThreadInterfaceInStream(const GUID* iid, LPVOID unk, LPVOID* stm);
HRESULT CreateStreamOnHGlobal(HGLOBAL h, BOOL del, LPVOID* stm);
HRESULT GetHGlobalFromStream(LPVOID stm, HGLOBAL* h);
HRESULT RegisterDragDrop(HWND w, LPVOID target);
HRESULT RevokeDragDrop(HWND w);
HRESULT DoDragDrop(LPVOID obj, LPVOID src, DWORD effects, DWORD* eff);
HRESULT OleGetClipboard(LPVOID* obj);
HRESULT OleSetClipboard(LPVOID obj);
HRESULT OleFlushClipboard(void);
HRESULT OleIsCurrentClipboard(LPVOID obj);
void    ReleaseStgMedium(LPVOID m);
HRESULT PropVariantClear(LPVOID pv);

BSTR    SysAllocString(const WCHAR* s);
BSTR    SysAllocStringLen(const WCHAR* s, UINT len);
BSTR    SysAllocStringByteLen(LPCSTR s, UINT len);
BOOL    SysReAllocStringLen(BSTR* b, const WCHAR* s, UINT len);
void    SysFreeString(BSTR b);
UINT    SysStringLen(BSTR b);
UINT    SysStringByteLen(BSTR b);
void    VariantInit(void* v);
HRESULT VariantClear(void* v);
HRESULT VariantCopy(void* dst, const void* src);
HRESULT VariantCopyInd(void* dst, const void* src);
HRESULT VariantChangeType(void* dst, const void* src, WORD flags, WORD vt);
void*   SafeArrayCreate(WORD vt, UINT dims, const void* bounds);
HRESULT SafeArrayDestroy(void* sa);
HRESULT SafeArrayAccessData(void* sa, void** pp);
HRESULT SafeArrayUnaccessData(void* sa);
HRESULT SafeArrayGetElement(void* sa, const LONG* idx, void* out);
HRESULT SafeArrayPutElement(void* sa, const LONG* idx, void* in);
HRESULT SafeArrayPtrOfIndex(void* sa, const LONG* idx, void** pp);
UINT    SafeArrayGetElemsize(void* sa);
HRESULT SafeArrayGetLBound(void* sa, UINT dim, LONG* out);
HRESULT SafeArrayGetUBound(void* sa, UINT dim, LONG* out);
HRESULT GetActiveObject(const GUID* clsid, LPVOID rsv, LPVOID* unk);
HRESULT GetErrorInfo(DWORD rsv, LPVOID* info);

/* =============================================================
 * shell32 / shlwapi / version / imagehlp / その他システム DLL (ほぼスタブ)
 * ============================================================= */
HRESULT SHGetFolderPathW(HWND w, int csidl, HANDLE tok, DWORD flags, LPWSTR path);
HRESULT SHGetKnownFolderPath(const GUID* id, DWORD flags, HANDLE tok, LPWSTR* path);
HRESULT SHGetSpecialFolderLocation(HWND w, int csidl, LPVOID* pidl);
BOOL    SHGetPathFromIDListW(const void* pidl, LPWSTR path);
LPVOID  ILCreateFromPathW(LPCWSTR path);
void    ILFree(LPVOID pidl);
/* shell32 序数 import 分 (Windows 10/11 の序数表: 16/17/18/19/21/25/152/153/155/190。R3)。
 * PIDL は shimx 自前形式 ([u16 cb][UTF-16 path + NUL][u16 0]) で実装する */
LPVOID  ILFindLastID(const void* pidl);
BOOL    ILRemoveLastID(void* pidl);
LPVOID  ILClone(const void* pidl);
LPVOID  ILCloneFirst(const void* pidl);
BOOL    ILIsEqual(const void* a, const void* b);
LPVOID  ILCombine(const void* a, const void* b);
UINT    ILGetSize(const void* pidl);
LPVOID  ILGetNext(const void* pidl);
HRESULT SHGetMalloc(LPVOID* out);
/* 序数 import でしか参照されない 3 API (SHX-T8 / src/shord.c): shell32 #74 / shlwapi #12 / #219 */
HRESULT SHCreateStdEnumFmtEtc(UINT cfmt, const void* afmt, LPVOID* out);
LPVOID  SHCreateMemStream(const BYTE* data, UINT len);
HRESULT QISearch(void* that, const void* tab, const GUID* riid, LPVOID* out);
HRESULT SHGetDesktopFolder(LPVOID* out);
HRESULT SHCreateItemFromParsingName(LPCWSTR p, LPVOID bc, const GUID* iid, LPVOID* out);
HRESULT SHOpenFolderAndSelectItems(LPVOID pidl, UINT n, LPVOID* children, DWORD flags);
int     SHCreateDirectoryExW(HWND w, LPCWSTR path, LPVOID sa);
int     SHFileOperationW(void* op);
void    SHAddToRecentDocs(UINT flags, LPCVOID pv);
UINT_PTR_T SHAppBarMessage(DWORD msg, void* data);
ULONG   SHChangeNotifyRegister(HWND w, int src, LONG events, UINT msg, int n, const void* entries);
BOOL    SHChangeNotifyDeregister(ULONG id);
HINSTANCE ShellExecuteW(HWND w, LPCWSTR op, LPCWSTR file, LPCWSTR params, LPCWSTR dir, int show);
HINSTANCE ShellExecuteA(HWND w, LPCSTR op, LPCSTR file, LPCSTR params, LPCSTR dir, int show);
BOOL    ShellExecuteExW(void* info);
BOOL    Shell_NotifyIconW(DWORD msg, void* data);
void    DragAcceptFiles(HWND w, BOOL accept);
void    DragFinish(HANDLE drop);
UINT    DragQueryFileW(HANDLE drop, UINT idx, LPWSTR buf, UINT cch);
BOOL    DragQueryPoint(HANDLE drop, void* pt);
BOOL    PathUnExpandEnvStringsW(LPCWSTR path, LPWSTR out, UINT cch);
DWORD   GetFileVersionInfoSizeW(LPCWSTR file, LPDWORD handle);
BOOL    GetFileVersionInfoW(LPCWSTR file, DWORD handle, DWORD len, LPVOID data);
BOOL    VerQueryValueW(LPCVOID block, LPCWSTR sub, LPVOID* buf, UINT* len);
void*   ImageNtHeader(PVOID base);
void*   ImageRvaToVa(void* nt, PVOID base, ULONG rva, void** sect);
void*   ImageDirectoryEntryToData(PVOID base, BOOLEAN mapped, USHORT_T dir, ULONG* size);
DWORD   WNetOpenEnumW(DWORD scope, DWORD type, DWORD usage, LPVOID res, LPHANDLE h);
DWORD   WNetEnumResourceW(HANDLE h, LPDWORD count, LPVOID buf, LPDWORD n);
DWORD   WNetCloseEnum(HANDLE h);
DWORD   WNetGetUniversalNameW(LPCWSTR local, DWORD level, LPVOID buf, LPDWORD n);
LONG    WinVerifyTrust(HWND w, GUID* action, LPVOID data);
BOOL    GetOpenFileNameW(LPVOID ofn);
BOOL    GetSaveFileNameW(LPVOID ofn);
DWORD   CommDlgExtendedError(void);
LRESULT_T LresultFromObject(const GUID* iid, LRESULT_T wp, LPVOID unk);
HRESULT UuidCreate(GUID* g);
ULONG_PTR SHGetFileInfoW(LPCWSTR path, DWORD attrs, LPVOID info, UINT cb, UINT flags);
HRESULT CreateILockBytesOnHGlobal(HGLOBAL h, BOOL del, LPVOID* out);
HRESULT StgCreateDocfileOnILockBytes(LPVOID lb, DWORD mode, DWORD rsv, LPVOID* out);
HRESULT CreateDataAdviseHolder(LPVOID* out);
HRESULT OleDraw(LPVOID unk, DWORD aspect, HANDLE dc, LPVOID rc);
BOOL    IsAccelerator(HANDLE haccel, int n, LPVOID msg, WORD* cmd);
HRESULT OleSetMenuDescriptor(HANDLE h, HWND frame, HWND obj, LPVOID f, LPVOID o);
LPVOID  shimx_get_drop_target(HWND w);
BOOL    SHGetSpecialFolderPathW(HWND w, LPWSTR path, int csidl, BOOL create);
BOOL    ShellExecuteExA(void* info);
HANDLE  ExtractAssociatedIconW(HANDLE inst, LPWSTR path, WORD* idx);
HRESULT SHCreateStreamOnFileEx(LPCWSTR path, DWORD mode, DWORD attrs, BOOL create, LPVOID tmpl, LPVOID* out);
void*   CreateThreadpoolWork(void (*cb)(void*, void*, void*), void* ctx, void* env);
void    SubmitThreadpoolWork(void* work);
void    CloseThreadpoolWork(void* work);
void    FreeLibraryWhenCallbackReturns(void* instance, HMODULE m);
HANDLE  CreateIoCompletionPort(HANDLE file, HANDLE port, ULONG_PTR key, DWORD threads);
BOOL    GetQueuedCompletionStatus(HANDLE port, LPDWORD n, ULONG_PTR* key, LPOVERLAPPED* ov, DWORD ms);
BOOL    CryptAcquireContextA(LPHANDLE prov, LPCSTR cont, LPCSTR name, DWORD type, DWORD flags);
BOOL    CryptCreateHash(HANDLE prov, DWORD alg, HANDLE key, DWORD flags, LPHANDLE hash);
BOOL    CryptHashData(HANDLE h, const BYTE* d, DWORD n, DWORD flags);
BOOL    CryptGetHashParam(HANDLE h, DWORD p, BYTE* d, LPDWORD n, DWORD flags);
BOOL    CryptDestroyHash(HANDLE h);
BOOL    CryptReleaseContext(HANDLE prov, DWORD flags);

/* winmm (MIDI は「デバイス 0 台」スタブ。Web MIDI 連携は下流) */
UINT    timeBeginPeriod(UINT ms);
UINT    timeEndPeriod(UINT ms);
UINT    timeGetDevCaps(void* caps, UINT n);

/* ネットワーク (常にエラー返却) */
LPVOID  InternetOpenW(LPCWSTR agent, DWORD access, LPCWSTR proxy, LPCWSTR bypass, DWORD flags);
BOOL    InternetGetConnectedState(LPDWORD flags, DWORD rsv);
BOOL    InternetCheckConnectionW(LPCWSTR url, DWORD flags, DWORD rsv);
BOOL    InternetCheckConnectionA(LPCSTR url, DWORD flags, DWORD rsv);
BOOL    InternetCloseHandle(LPVOID h);
LPVOID  InternetConnectW(LPVOID h, LPCWSTR server, WORD port, LPCWSTR user, LPCWSTR pass, DWORD service, DWORD flags, ULONG_PTR ctx);
LPVOID  InternetOpenUrlW(LPVOID h, LPCWSTR url, LPCWSTR hdr, DWORD hdrLen, DWORD flags, ULONG_PTR ctx);
BOOL    InternetReadFile(LPVOID h, LPVOID buf, DWORD n, LPDWORD read);
BOOL    InternetWriteFile(LPVOID h, LPCVOID buf, DWORD n, LPDWORD written);
BOOL    InternetSetOptionW(LPVOID h, DWORD opt, LPVOID buf, DWORD n);
BOOL    InternetGetLastResponseInfoW(LPDWORD err, LPWSTR buf, LPDWORD n);
LPVOID  HttpOpenRequestW(LPVOID h, LPCWSTR verb, LPCWSTR obj, LPCWSTR ver, LPCWSTR ref, LPCWSTR* accept, DWORD flags, ULONG_PTR ctx);
BOOL    HttpSendRequestW(LPVOID h, LPCWSTR hdr, DWORD hl, LPVOID opt, DWORD ol);
BOOL    HttpSendRequestA(LPVOID h, LPCSTR hdr, DWORD hl, LPVOID opt, DWORD ol);
BOOL    HttpSendRequestExW(LPVOID h, LPVOID in, LPVOID out, DWORD flags, ULONG_PTR ctx);
BOOL    HttpEndRequestW(LPVOID h, LPVOID out, DWORD flags, ULONG_PTR ctx);
BOOL    HttpAddRequestHeadersW(LPVOID h, LPCWSTR hdr, DWORD n, DWORD mod);
BOOL    HttpQueryInfoW(LPVOID h, DWORD level, LPVOID buf, LPDWORD n, LPDWORD idx);
BOOL    HttpQueryInfoA(LPVOID h, DWORD level, LPVOID buf, LPDWORD n, LPDWORD idx);

/* =============================================================
 * 運用フック (shimx 独自 API)
 * ============================================================= */
typedef int (*shimx_path_mapper_fn)(const char* winPathUtf8, char* outPosix, size_t outSize);
typedef void* (*shimx_callback_translator_fn)(const char* api, void* callback);   /* R2: 関数ポインタ引数の変換フック */
/* R2 実体 (cbtrans.c / CAB-177): lift 側 VA→関数解決の正本 (__icall_dispatch 関数表+BLK 方式 または
 * m11_icall) を登録する invoke 契約。未知 va は例外でなく 0 を返す (列挙の穏当な打切り)。 */
typedef unsigned long long (*shimx_cb_invoke_fn)(unsigned long long va, unsigned long long a0,
                                                 unsigned long long a1, unsigned long long a2,
                                                 unsigned long long a3, unsigned long long a4,
                                                 unsigned long long a5, unsigned long long a6,
                                                 unsigned long long a7);
/* R3 実体: lift ABI トークン (SHX_LIFTTAB_TOKEN_BASE+index) → u64×8 uniform ABI の型付き thunk */
typedef unsigned long long (*shimx_lift_thunk_fn)(unsigned long long a0, unsigned long long a1,
                                                  unsigned long long a2, unsigned long long a3,
                                                  unsigned long long a4, unsigned long long a5,
                                                  unsigned long long a6, unsigned long long a7);
void shimx_init(void);                                      /* 省略可 (遅延初期化) */
void shimx_set_trace(int on);                               /* stderr にトレース出力 (環境変数 SHIMX_TRACE=1 でも可) */
int  shimx_set_trace_file(const char* path);                /* file API の JSON Lines トレース先 (NULL で停止)。環境変数 SHIMX_TRACE_FILE=<path> でも可 */
void shimx_set_strict(int on);                              /* 1: 未知 GetProcAddress 名を fail-fast */
void shimx_set_intptr_limit(uint32_t lim);                  /* R1: 値 < lim を序数/整数 (MAKEINTRESOURCE 等) とみなす閾値。既定 0x10000 */
uint32_t shimx_get_intptr_limit(void);
void shimx_set_callback_translator(shimx_callback_translator_fn fn);  /* R2: 列挙系・CreateThread・FlsAlloc・タイマ・スレッドプールのコールバック変換 */
shimx_callback_translator_fn shimx_get_callback_translator(void);     /* R2: 現在のフック (未設定は NULL) */
void* shimx_cb_translator(const char* api, void* cb);       /* R2 実体: VA≥intptr_limit → slot トランポリン (invoke 経由) / 未満は恒等 */
void* shimx_cbtrans_install(void);                          /* R2 実体の取付 (set_callback_translator(shimx_cb_translator))。戻り=前のフック */
void shimx_cbtrans_set_invoke(shimx_cb_invoke_fn fn);       /* lift 側 dispatch (m11_icall / __icall_dispatch(BLK) 相当) を登録 */
shimx_cb_invoke_fn shimx_cbtrans_get_invoke(void);
struct shimx_midi_vtbl;
void shimx_set_midi_backend(const struct shimx_midi_vtbl *t);   /* #179 SHX-T6: winmm midi* の実体表 (midi_backend.h) を登録。NULL で解除 */
int  shimx_cbtrans_slots(void);                             /* 使用中スロット数 (distinct VA 数) */
unsigned shimx_cbtrans_slot_va(int slot);                   /* slot → 登録 VA (診断) */
unsigned shimx_cbtrans_registrations(void);                 /* 累計登録数 */
unsigned shimx_cbtrans_calls(void);                         /* トランポリン実呼出回数 */
void shimx_cbtrans_reset(void);                             /* スロット/統計を掃除 (テスト用。invoke は保持) */
unsigned shimx_lifttab_token(const char* name, DWORD ordinal);  /* R3: 名前/序数 → lift ABI トークン (0=対象外) */
void* shimx_lifttab_proc_resolver(HMODULE m, const char* name, DWORD ordinal); /* R3: shimx_set_proc_resolver 用 (IL* と UI言語 をトークン化) */
shimx_lift_thunk_fn shimx_lifttab_trampoline(unsigned token);   /* R3: トークン → u64×8 thunk (実 C 署名へ marshal)。未知は NULL */
int  shimx_lifttab_count(void);
const char* shimx_lifttab_name(int i);
/* SHX-T23 (#1388): RegisterDragDrop 経路。guest の IDropTarget は shimx_drop_invoke が vtable 経由で呼ぶ (C→guest = shimx_cbtrans_get_invoke)。
 * guest が渡された IDataObject の vtable は lifttab トークン (shimx_lifttab_token("IDataObject.*")) で組む (guest→C = trampoline)。 */
HRESULT shimx_ido_QueryInterface(void* self, const GUID* iid, void** out);
ULONG shimx_ido_AddRef(void* self);
ULONG shimx_ido_Release(void* self);
HRESULT shimx_ido_GetData(void* self, const void* fe, void* sm);
HRESULT shimx_ido_QueryGetData(void* self, const void* fe);
HRESULT shimx_ido_NotImpl(void);
int  shimx_drop_invoke(void* target, uint64_t hwnd, size_t hdrop, int x, int y);   /* gui_set_drop_target_invoker の実体。0=未処理 / 1=Drop 受理 */
void shimx_set_pseudo_load(int on);                         /* R4: 1 = 未知 DLL の LoadLibrary を擬似モジュール登録で成功させる (既定 0 = 失敗) */
void shimx_set_cs_null_ok(int on);                          /* R7: 1 = CRITICAL_SECTION の NULL/非整列を no-op で通す (既定 0 = fail-fast = Win32 AV 相当) */
void shimx_set_path_mapper(shimx_path_mapper_fn fn);        /* VFS 連携: Win パス → FS パス */
int  shimx_path_to_posix(const char* winUtf8, char* out, size_t outSize);
void shimx_set_acp(UINT cp);
void shimx_set_locale(LCID lcid);
void shimx_set_exe_path(const char* winPathUtf8);
void shimx_set_command_line(const char* utf8);
void shimx_set_exit_hook(void (*fn)(UINT code));
void shimx_set_raise_hook(int (*fn)(EXCEPTION_RECORD64* rec));   /* 戻り 1=処理済 (VEH より前に呼ばれる外部上書き口) */

/* ---- SEH 実巻き戻し (#171): lift した try 関数が frame を登録する setjmp 系ランタイム ----
 * scope table は Delphi x64 の UNWIND_INFO inline 形式 (tools/icall/landing/REPORT.md §2):
 *   uint32 count; count × { begin, end, kind, target }  (RVA)
 *   kind==2 : catch-all。pc が [begin,end) なら捕捉 → 巻き戻し後 frame->jb へ longjmp (resume_ip = target)
 *   kind>2  : typed except。kind は descriptor list の RVA。shimx_seh_set_typed_matcher で照合
 *   kind 0/1: handler 領域。巻き戻し時に pc が範囲内なら target (pad) を pad(&{rec,ctx}, frame) で呼ぶ
 * 使い方 (lift 側):  ShxSehFrame f = {0}; f.frame = ..; f.scopes = ..;
 *   shimx_seh_enter(&f); if (setjmp(f.jb)) { f.resume_ip へ分岐 } ... f.pc = <RVA>; call ...; shimx_seh_leave(&f);
 * frame が 1 つも登録されていない場合の RaiseException/RtlUnwind(Ex) は従来どおり fail-fast。 */
typedef struct ShxSehScope { uint32_t begin, end, kind, target; } ShxSehScope;
typedef struct ShxSehFrame {
    struct ShxSehFrame* prev;      /* ランタイム管理 (スレッド毎の frame 鎖) */
    uint64_t frame;                /* establisher frame 識別子 (pad の第 2 引数 / RtlUnwindEx の targetFrame と照合) */
    const uint32_t* scopes;        /* count + ShxSehScope[count] (NULL = scope 無し) */
    volatile uint32_t pc;          /* 現在の ControlPc (RVA)。lift 側が try 内の call 前に更新 */
    uint64_t resume_ip;            /* longjmp で戻る時の再開先 (catch-all=scope target RVA / RtlUnwind(Ex)=targetIp) */
    uint64_t resume_ret;           /* RtlUnwind(Ex) の retval */
    jmp_buf jb;
} ShxSehFrame;
typedef uint64_t (*shimx_seh_pad_fn)(uint64_t excptrs, uint64_t frame);
void shimx_seh_enter(ShxSehFrame* f);
void shimx_seh_leave(ShxSehFrame* f);                                  /* f と f より内側を鎖から外す */
void shimx_seh_set_pad_resolver(shimx_seh_pad_fn (*fn)(uint32_t rva)); /* scope target RVA → pad 関数 */
void shimx_seh_set_typed_matcher(int (*fn)(const EXCEPTION_RECORD64* rec, uint32_t descRva, uint32_t* handlerRva));
const EXCEPTION_RECORD64* shimx_seh_current_exception(void);           /* 直近に捕捉/巻き戻し中の例外 (スレッド毎) */
unsigned shimx_seh_depth(void);                                        /* 登録中 frame 数 (スレッド毎) */
/* MX-45 (#4161): FH3 FuncInfo (RVA 形) の funclet RVA 集合。img は RVA で引ける平坦バッファ。
 * out には先頭 out_cap 件まで書く。戻り値 n は、n <= out_cap なら重複を除いた件数 (正確)。
 * n > out_cap なら out は先頭 out_cap 件のみ有効で、n は真の件数の上界 (重複を含みうる)。
 * 呼出し側は n > out_cap のとき cap を増やして再呼出しする。FuncInfo 不正・上限超過は -1。 */
int shimx_fh3_funclets(const uint8_t* img, uint32_t img_size, uint32_t fi_rva, uint32_t* out, uint32_t out_cap);
/* FH3 try map + IP-to-state map → ShxSehScope 表 (out に先頭 out_cap 件)。戻り値は件数 (超過も真の件数)。FuncInfo 不正は -1。 */
int shimx_fh3_scopes(const uint8_t* img, uint32_t img_size, uint32_t fi_rva, uint32_t func_end_rva, ShxSehScope* out, uint32_t out_cap);
HMODULE shimx_module_register(const char* name, HMODULE base, const char* winPath);
int  shimx_proc_register(HMODULE m, const char* name, DWORD ordinal, void* fn);
void shimx_set_proc_resolver(void* (*fn)(HMODULE m, const char* name, DWORD ordinal));
void shimx_set_load_hook(HMODULE (*fn)(const char* nameUtf8, DWORD flags));
void shimx_set_resource_provider(const void* (*fn)(HMODULE m, const WCHAR* name, const WCHAR* type, DWORD* size));
void shimx_set_shell_execute_hook(int (*fn)(const char* verb, const char* file, const char* params));
/* GUI 連携 (#172 SHX-T5): gui が user32 側 (MsgWait* / WM_DROPFILES) から呼ぶ口 */
void shimx_set_notify_hook(void (*fn)(void));                  /* kernel object の状態変化ごとに呼ぶ (任意スレッド・shx_lock 外) */
void shimx_set_file_close_hook(void (*fn)(const char *));      /* #958: 書込み用 file handle を CloseHandle したとき posix path で呼ぶ (shx_lock 外) */
int  shimx_drag_accepts(HWND w);                               /* DragAcceptFiles(w, TRUE) 済みか */
HANDLE shimx_hdrop_create(const WCHAR* const* wpaths, DWORD n, int x, int y, int nc);   /* DROPFILES を作り HDROP を返す (DragFinish で解放) */
const uint8_t* shimx_hdrop_bytes(HANDLE drop, size_t* sz);                              /* HDROP の生ブロックと大きさ (IDataObject::GetData のコピー元)。無効は NULL */
void shimx_set_trust_ok(int on);
unsigned shimx_wininet_call_count(void);   /* wininet 接続系 API の呼出回数 (全て失敗扱い) */
void shimx_set_version(DWORD major, DWORD minor, DWORD build, DWORD fileHi, DWORD fileLo);
int  shimx_setenv_utf8(const char* name, const char* value);
void shimx_handle_stats(int* open, int* peak);

/* fail-fast: 未対応 API を即 abort + 関数名出力 (M4 継承) */
void shim_unimplemented(const char* apiName);

#ifdef __cplusplus
}
#endif
#include "shimx_stubs.h"
#endif /* SHIMX_H */
