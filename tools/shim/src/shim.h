/* M4 shim core: Win32 API 相当 (v1) の共通型・定数・宣言。
 * 対応範囲: strategy.md §3 の #2 (file) / #3 (timer) / #4 (thread・同期) /
 * #7 (heap) / #8 (CRT 最小限 GetLastError 系)。
 * 「wine 的な全部つくり」ではなく FLEngine が wasm で動くための最小面だけを実装する。
 *
 * ビルド: tools/shim/test.sh (MT=pthread / ST=シングルスレッド両対応)
 */
#ifndef SHIM_H
#define SHIM_H

#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

/* Win 風の大きさ揃え (SysV/win64 ANSI 系の名前差を吸収) */
#if !defined(SIZE_T_DEFINED)
#define SIZE_T_DEFINED
typedef size_t SIZE_T;
#endif

#if defined(__EMSCRIPTEN__)
#include <emscripten.h>
#include <emscripten/threading_primitives.h> /* emscripten_futex_wait/wake */
#endif

#if defined(__EMSCRIPTEN_PTHREADS__)
#include <pthread.h>
#endif

/* ---------------------------------------------------------------
 * 基本型 (x64 Windows 相当の幅。wasm32 上では LP64/ILP32 境界に注意)
 * --------------------------------------------------------------- */
typedef uint32_t DWORD;
typedef int32_t  LONG;
typedef uint16_t WORD;
typedef unsigned char BYTE;
typedef int      BOOL;
typedef void*    LPVOID;
typedef const void* LPCVOID;
typedef DWORD*   LPDWORD;
typedef LONG*    PLONG;
typedef uint16_t WCHAR;
typedef const WCHAR* LPCWSTR;
typedef void*    LPSECURITY_ATTRIBUTES;   /* 未使用 (常に NULL 前提) */
typedef void*    LPOVERLAPPED;            /* 未使用 (同期 I/O 前提)   */
typedef size_t   ULONG_PTR;
typedef ULONG_PTR HANDLE;
typedef HANDLE*  LPHANDLE;

#define INVALID_HANDLE_VALUE ((HANDLE)(ULONG_PTR)-1)

#ifndef TRUE
#define TRUE  1
#define FALSE 0
#endif

#define INFINITE            0xFFFFFFFFu
#define WAIT_OBJECT_0       0u
#define WAIT_TIMEOUT        258u
#define WAIT_FAILED         0xFFFFFFFFu
#define INVALID_SET_FILE_POINTER 0xFFFFFFFFu

/* エラーコード (最小限) */
#define ERROR_SUCCESS          0u
#define ERROR_INVALID_FUNCTION 1u
#define ERROR_FILE_NOT_FOUND   2u
#define ERROR_SHARING_VIOLATION 32u
#define ERROR_INVALID_PARAMETER 87u
#define ERROR_NEGATIVE_SEEK   131u
#define ERROR_HANDLE_EOF      38u
#define ERROR_NOT_ENOUGH_MEMORY 8u

/* CreateFileW 用 */
#define GENERIC_READ      0x80000000u
#define GENERIC_WRITE     0x40000000u
#define CREATE_NEW        1u
#define CREATE_ALWAYS     2u
#define OPEN_EXISTING     3u
#define OPEN_ALWAYS       4u
#define TRUNCATE_EXISTING 5u
/* whence */
#define FILE_BEGIN   0u
#define FILE_CURRENT 1u
#define FILE_END     2u

/* GlobalAlloc / LocalAlloc 用 */
#define GMEM_FIXED      0x0000u
#define GMEM_MOVEABLE   0x0002u
#define GMEM_ZEROINIT   0x0040u
#define GHND            (GMEM_MOVEABLE | GMEM_ZEROINIT)
#define GPTR            (GMEM_FIXED | GMEM_ZEROINIT)
#define HEAP_ZERO_MEMORY 0x00000008u

typedef HANDLE HGLOBAL;
typedef HANDLE HLOCAL;
typedef HANDLE HEAP_HANDLE;   /* HeapCreate の戻り値 (実体はダミー値) */

typedef struct _LARGE_INTEGER {
    int64_t QuadPart;
} LARGE_INTEGER, *PLARGE_INTEGER;

#ifndef WINAPI
#define WINAPI       /* Win32 装飾の字面を吸収 (wasm では素の C 呼び出し) */
#endif
#ifndef APIENTRY
#define APIENTRY
#endif
#ifndef CALLBACK
#define CALLBACK
#endif

typedef DWORD (*LPTHREAD_START_ROUTINE)(LPVOID lpParameter);

typedef void* PCRITICAL_SECTION; /* クライアント側確保メモリへのポインタ (中身は shim が管理) */
typedef void* PSRWLOCK;          /* v1 未対応 */

/* ---------------------------------------------------------------
 * timer / time  (§3 #3)
 * --------------------------------------------------------------- */
uint64_t     GetTickCount64(void);
DWORD        GetTickCount(void);
DWORD        timeGetTime(void);
BOOL         QueryPerformanceCounter(LARGE_INTEGER* out);
BOOL         QueryPerformanceFrequency(LARGE_INTEGER* out);
void         Sleep(DWORD ms);

/* ---------------------------------------------------------------
 * file  (§3 #2) — Emscripten FS (MEMFS) への写影
 * --------------------------------------------------------------- */
HANDLE CreateFileW(LPCWSTR fileName, DWORD desiredAccess, DWORD shareMode,
                   LPSECURITY_ATTRIBUTES sa, DWORD creationDisposition,
                   DWORD flagsAndAttributes, HANDLE hTemplateFile);
BOOL   ReadFile(HANDLE h, LPVOID buf, DWORD bytesToRead, LPDWORD bytesRead,
                LPOVERLAPPED overlapped);
BOOL   WriteFile(HANDLE h, LPCVOID buf, DWORD bytesToWrite, LPDWORD bytesWritten,
                 LPOVERLAPPED overlapped);
DWORD  SetFilePointer(HANDLE h, LONG distanceLow, PLONG distanceHigh, DWORD method);
BOOL   SetFilePointerEx(HANDLE h, LARGE_INTEGER distance,
                        PLARGE_INTEGER newPos, DWORD method);
BOOL   SetEndOfFile(HANDLE h);
DWORD  GetFileSize(HANDLE h, LPDWORD sizeHigh);
BOOL   GetFileSizeEx(HANDLE h, PLARGE_INTEGER size);

/* ---------------------------------------------------------------
 * thread / sync  (§3 #4)
 * --------------------------------------------------------------- */
HANDLE CreateThread(LPSECURITY_ATTRIBUTES sa, SIZE_T stackSize,
                    LPTHREAD_START_ROUTINE start, LPVOID param,
                    DWORD flags, LPDWORD threadId);
void   ExitThread(DWORD exitCode);
DWORD  GetCurrentThreadId(void);

BOOL   CloseHandle(HANDLE h);              /* thread/event/file 共通 */
DWORD  WaitForSingleObject(HANDLE h, DWORD ms);
DWORD  WaitForSingleObjectEx(HANDLE h, DWORD ms, BOOL alertable);

HANDLE CreateEventW(LPSECURITY_ATTRIBUTES sa, BOOL manualReset, BOOL initialState,
                    LPCWSTR name);
HANDLE CreateEventA(LPSECURITY_ATTRIBUTES sa, BOOL manualReset, BOOL initialState,
                    const char* nameA);
BOOL   SetEvent(HANDLE h);
BOOL   ResetEvent(HANDLE h);

void   InitializeCriticalSection(PCRITICAL_SECTION cs);
BOOL   InitializeCriticalSectionAndSpinCount(PCRITICAL_SECTION cs, DWORD spin);
void   EnterCriticalSection(PCRITICAL_SECTION cs);
BOOL   TryEnterCriticalSection(PCRITICAL_SECTION cs);
void   LeaveCriticalSection(PCRITICAL_SECTION cs);
void   DeleteCriticalSection(PCRITICAL_SECTION cs);

void   MemoryBarrier(void);
LONG   InterlockedIncrement(volatile LONG* v);
LONG   InterlockedDecrement(volatile LONG* v);
LONG   InterlockedExchange(volatile LONG* v, LONG newVal);
LONG   InterlockedExchangeAdd(volatile LONG* v, LONG add);

DWORD  TlsAlloc(void);
BOOL   TlsFree(DWORD idx);
LPVOID TlsGetValue(DWORD idx);
BOOL   TlsSetValue(DWORD idx, LPVOID val);

/* ---------------------------------------------------------------
 * heap  (§3 #7) — Emscripten malloc ラッパ
 * --------------------------------------------------------------- */
HGLOBAL     GlobalAlloc(DWORD flags, SIZE_T bytes);
LPVOID      GlobalLock(HGLOBAL h);
BOOL        GlobalUnlock(HGLOBAL h);
HGLOBAL     GlobalFree(HGLOBAL h);
HLOCAL      LocalAlloc(DWORD flags, SIZE_T bytes);
HLOCAL      LocalReAlloc(HLOCAL h, SIZE_T bytes, DWORD flags);
HLOCAL      LocalFree(HLOCAL h);
HEAP_HANDLE HeapCreate(DWORD flags, SIZE_T initial, SIZE_T maximum);
LPVOID      HeapAlloc(HEAP_HANDLE heap, DWORD flags, SIZE_T bytes);
LPVOID      HeapReAlloc(HEAP_HANDLE heap, DWORD flags, LPVOID p, SIZE_T bytes);
BOOL        HeapFree(HEAP_HANDLE heap, DWORD flags, LPVOID p);

/* ---------------------------------------------------------------
 * CRT 最小限  (§3 #8 のうち thread/shim 側で必要な面)
 * --------------------------------------------------------------- */
DWORD GetLastError(void);
void  SetLastError(DWORD e);

/* ---------------------------------------------------------------
 * fail-fast: 未対応 import を即 abort + 関数名出力
 * (M5 以降の lifter 生成コードから、実装していない面に到達した時点で
 *  「何が未実装か」を stderr に出して即終了させる)
 * --------------------------------------------------------------- */
void shim_unimplemented(const char* apiName);

#endif /* SHIM_H */
