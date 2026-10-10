/* fa_win_shim.h — lift 済みコード (mlift 出力) が呼ぶ Win32 / CRT 境界の最小実装。
 * native 参照ハーネス (IAT 差替, ms_abi) と wasm (win_<dll>_<name> 外部関数) の両方が同じ本体を共有する。
 * 本体は (rcx,rdx,r8,r9) の 4 つの 64bit 引数 → rax の 64bit 戻り。
 * 未実装 API は SH_TRAP (native: SIGTRAP / wasm: unreachable) — 使われた時点で shim 不足として顕在化させる。 */
#ifndef FA_WIN_SHIM_H
#define FA_WIN_SHIM_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t u64;
#ifdef __wasm__
#define SH_TRAP() __builtin_trap()
#else
#define SH_TRAP() __builtin_debugtrap()
#endif
static u64 g_lasterr;
static u64 g_tls[64];
static u64 g_shim_calls_HeapAlloc, g_shim_calls_HeapFree, g_shim_calls_HeapReAlloc;
static u64 sh_HeapAlloc(u64 h, u64 flags, u64 size, u64 d)   { g_shim_calls_HeapAlloc++; void* p = (flags & 8) ? calloc(1, size) : malloc(size); return (u64)(uintptr_t)p; }
static u64 sh_HeapFree(u64 h, u64 flags, u64 p, u64 d)       { g_shim_calls_HeapFree++; free((void*)(uintptr_t)p); return 1; }
static u64 sh_HeapReAlloc(u64 h, u64 flags, u64 p, u64 size) { g_shim_calls_HeapReAlloc++; return (u64)(uintptr_t)realloc((void*)(uintptr_t)p, size); }
static u64 sh_GetLastError(u64 a, u64 b, u64 c, u64 d)       { return g_lasterr; }
static u64 sh_SetLastError(u64 a, u64 b, u64 c, u64 d)       { g_lasterr = (uint32_t)a; return 0; }
static u64 sh_TlsGetValue(u64 i, u64 b, u64 c, u64 d)        { return i < 64 ? g_tls[i] : 0; }
static u64 sh_TlsSetValue(u64 i, u64 v, u64 c, u64 d)        { if (i < 64) g_tls[i] = v; return 1; }
static u64 sh_nop0(u64 a, u64 b, u64 c, u64 d)               { return 0; }
static u64 sh_nop1(u64 a, u64 b, u64 c, u64 d)               { return 1; }
static u64 sh_trap(u64 a, u64 b, u64 c, u64 d)               { SH_TRAP(); return 0; }
/* name, body */
#define FA_SHIM_TABLE(X) \
  X(HeapAlloc, sh_HeapAlloc) X(HeapFree, sh_HeapFree) X(HeapReAlloc, sh_HeapReAlloc) \
  X(GetLastError, sh_GetLastError) X(SetLastError, sh_SetLastError) \
  X(TlsGetValue, sh_TlsGetValue) X(TlsSetValue, sh_TlsSetValue) \
  X(EnterCriticalSection, sh_nop0) X(LeaveCriticalSection, sh_nop0) \
  X(LoadLibraryExW, sh_nop0) X(GetProcAddress, sh_nop0) X(FreeLibrary, sh_nop0) \
  X(IsProcessorFeaturePresent, sh_nop0) X(GetCurrentProcess, sh_nop0) \
  X(RaiseException, sh_trap) X(TerminateProcess, sh_trap) X(RtlCaptureContext, sh_trap) \
  X(RtlLookupFunctionEntry, sh_trap) X(RtlVirtualUnwind, sh_trap) \
  X(SetUnhandledExceptionFilter, sh_trap) X(UnhandledExceptionFilter, sh_trap)
#endif
