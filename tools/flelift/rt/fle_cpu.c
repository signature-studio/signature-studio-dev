/* fle_cpu.c: lifted code の CPU 状態 + 実行時 fail-fast + Win32/CRT import (FLEngine 用)。
 * 原型 = tools/ott/rt/ott_cpu.c。FLEngine 拡張: DF/AF flag, YL (ymm 上位), x87 制御モデル,
 * TEB (gs) 敷設, alloc log, IAT pseudo-VA index 参照。 */
#include "fle_cpu.h"
#include <stdio.h>
#ifdef FLE_WWATCH_JS
#include <emscripten.h>
#endif
#include "fle_approx.inc"
uint64_t R[16];
X128 X[16];
X128 YL[16];
uint64_t M[8];                  /* MMX (実機非 alias 実測) */
uint8_t fZF, fSF, fCF, fOF, fPF, fAF, fDF;
uint16_t x87_cw = 0x037f, x87_sw = 0;
uint32_t mxcsr = 0x1f80;
uint32_t XCR0 = 0x7;            /* x87|SSE|AVX (xgetbv モデル値) */
uint64_t SEG_GS = FLE_TEB, SEG_FS = FLE_TEB;
uint64_t ott_xrip;
/* FLE-2 boot hook (fle_cpu.h 参照)。未設定 = abort (fle_native の spot diff 経路と同一挙動)。 */
void (*fle_ff_hook)(const char* kind, uint64_t a) = 0;
/* FLE-2 boot: ott_dispatch probe (未設定 = 何もしない) */
void (*fle_dispatch_probe)(uint64_t t) = 0;
uint64_t (*fle_gpa_hook)(uint64_t h, uint64_t nm) = 0;

#define FLE_FF(kind, a) do { if (fle_ff_hook) { fle_ff_hook((kind), (uint64_t)(a)); } } while (0)

void ott_unsup(uint64_t addr, const char* what) {
    FLE_FF("unsup", addr);
    fprintf(stderr, "[fle] UNSUPPORTED instruction at %#llx: %s\n", (unsigned long long)addr, what); abort();
}
void ott_unlifted(uint64_t va) {
    /* FLE-2: hook が戻した場合は「ret 0 扱い」で継続 (m11 の icall-miss 揃え)。hook は retaddr を pop する。 */
    if (fle_ff_hook) { fle_ff_hook("unlifted", va); return; }
    fprintf(stderr, "[fle] call to UNLIFTED function %#llx ret=%#llx\n", (unsigned long long)va, (unsigned long long)LD64(R[RSP])); abort();
}
void ott_badjump(uint64_t addr, uint64_t target) {
    FLE_FF("badjump", target);
    fprintf(stderr, "[fle] bad jump at %#llx target %#llx\n", (unsigned long long)addr, (unsigned long long)target); abort();
}
void ott_missing_import(const char* nm) {
    FLE_FF(nm, 0);
    fprintf(stderr, "[fle] MISSING IMPORT %s\n", nm); abort();
}
#ifdef FLE_WWATCH
/* PY-123 (#3028): 監視 slot の値を変える書込みを、書込み元の C の __FILE__:__LINE__ 付きで出す (件数上限あり)。 */
#ifndef FLE_WWATCH_SLOTS
#define FLE_WWATCH_SLOTS 0x15e1c78ull, 0x15e4790ull   /* 既定の監視 slot (-DFLE_WWATCH_SLOTS=a,b で上書き) */
#endif
void fle_wwatch(uint64_t a, uint32_t n, const void* src, const char* file, int line) {
    static const uint64_t slot[] = { FLE_WWATCH_SLOTS };
    static int nlog = 0;
    for (int k = 0; k < (int)(sizeof slot / sizeof slot[0]); k++) {
        uint64_t w = slot[k];
        if (a >= w + 8 || a + n <= w) continue;
        uint8_t oldb[8], newb[8];
        memcpy(oldb, (void*)(uintptr_t)w, 8); memcpy(newb, oldb, 8);
        for (uint32_t i = 0; i < n; i++) {
            uint64_t p = a + i;
            if (p >= w && p < w + 8) newb[p - w] = ((const uint8_t*)src)[i];
        }
        if (memcmp(oldb, newb, 8) == 0 || nlog >= 5000) continue;
        uint64_t ov, nv; memcpy(&ov, oldb, 8); memcpy(&nv, newb, 8);
        nlog++;
        fprintf(stderr, "[fle_wwatch] ret=%p slot=%#llx a=%#llx n=%u old=%#llx new=%#llx at %s:%d\n", __builtin_return_address(0),
                (unsigned long long)w, (unsigned long long)a, n, (unsigned long long)ov, (unsigned long long)nv, file, line);
#ifdef FLE_WWATCH_JS
        if (nv == 0 && ov != 0) {
            /* 書込み時点の wasm 呼出し連鎖 (--profiling-funcs の関数名 f_xxxx)。診断のみ・既定無効。 */
            EM_ASM({ console.error("[fle_wwatch_js] slot=" + ($0 >>> 0).toString(16) + "\n" + new Error().stack.split("\n").slice(0, 40).join("\n")); }, (int)w);
        }
#endif
#ifdef FLE_WWATCH_STACK
        if (nv == 0 && ov != 0) {
            fprintf(stderr, "[fle_wwatch_stack] slot=%#llx xrip=%#llx", (unsigned long long)w, (unsigned long long)ott_xrip);
            for (int i = 0; i < 32; i++) {
                uint64_t v = LD64(R[RSP] + 8ull * i);
                if (v >= 0x400000ull && v < 0x2000000ull) fprintf(stderr, " [%d]=%#llx", i, (unsigned long long)v);
            }
            fprintf(stderr, "\n");
        }
#endif
    }
}
#endif
#ifdef FLE_RWATCH
/* #4426: 読出し監視。[FLE_RWATCH_LO, FLE_RWATCH_HI) に重なる読出しを、読出し元 (__FILE__:__LINE__) 付きで出す。
 * guest_ret は読出し時の [rsp] の値であり、読出し元の戻り番地とは限らない (関数本体で sub rsp・push の後の読出しはローカル変数になる)。 */
#ifndef FLE_RWATCH_LO
#define FLE_RWATCH_LO 0x12d677d0ull + 0x18ull
#endif
#ifndef FLE_RWATCH_HI
#define FLE_RWATCH_HI 0x12d677d0ull + 0x28ull
#endif
void fle_rwatch(uint64_t a, uint32_t n, const char* file, int line) {
    static int nlog = 0;
    if (a >= FLE_RWATCH_HI || a + n <= FLE_RWATCH_LO || nlog >= 200) return;
    nlog++;
    fprintf(stderr, "[fle_rwatch] rsp_val=%#llx a=%#llx n=%u at %s:%d\n",
            (unsigned long long)(*(u64u*)A_(R[RSP])), (unsigned long long)a, n, file, line);
}
#endif
#ifdef FLE_CHK
void fle_chk(uint64_t a, int line) {
    /* wasm linear 上限 (initial-memory) と emcc static 領域 (GLOBAL_BASE 0x10000000..) を避ける */
    if (a >= 0x36000000ull || (a >= 0x10000000ull && a < 0x1D00000ull) || (a >= 0x1e00000ull && a < 0x2000000ull)) {
        fprintf(stderr, "[fle] bad guest address %#llx (fle_cpu.h line %d)\n", (unsigned long long)a, line);
        /* FLE-2: どこから来たか (guest return address 連鎖) を出して巻き戻れるようにする */
        fprintf(stderr, "[fle]   RSP=%#llx ret=%#llx xrip=%#llx\n",
                (unsigned long long)R[RSP], (unsigned long long)LD64(R[RSP]), (unsigned long long)ott_xrip);
        for (int i = 0; i < 64; i++) {
            uint64_t v = LD64(R[RSP] + 8ull * i);
            if (v >= 0x401000ull && v < 0x13a44b0ull) fprintf(stderr, "[fle]   stack[+%d] = %#llx\n", i, (unsigned long long)v);
        }
        /* 壊れたアドレスの出所: 不正値がどのレジスタ由来か (直近命令の痕跡) を出す */
        fprintf(stderr, "[fle]   regs: rax=%#llx rcx=%#llx rdx=%#llx rbx=%#llx rbp=%#llx rsi=%#llx rdi=%#llx r8=%#llx r9=%#llx\n",
                (unsigned long long)R[RAX], (unsigned long long)R[RCX], (unsigned long long)R[RDX],
                (unsigned long long)R[RBX], (unsigned long long)R[RBP], (unsigned long long)R[RSI],
                (unsigned long long)R[RDI], (unsigned long long)R[8], (unsigned long long)R[9]);
        /* live chain 再現: rbp chain を辿る (Delphi MSVC 形はフレームポインタ有り) */
        {
            uint64_t fr = R[RBP];
            for (int k = 0; k < 12 && fr >= 0x100000ull && fr < 0x3000000ull; k++) {
                uint64_t ra = LD64(fr + 8);
                if (ra >= 0x401000ull && ra < 0x13a44b0ull) fprintf(stderr, "[fle]   frame[%d] ret=%#llx\n", k, (unsigned long long)ra);
                fr = LD64(fr);
            }
        }
        abort();
    }
}
#endif

void cpuid_model(void) {
    /* 最小 CPUID モデル: leaf 0 = max 1 / "GenuineIntel" 風, leaf 1 = SSE2+SSSE3+SSE4 家系, 他 0 */
    switch (R[RAX] & 0xffffffffULL) {
    case 0:
        R[RAX] = 1; R[RBX] = 0x756e6547; R[RDX] = 0x49656e69; R[RCX] = 0x6c65746e; break;
    case 1:
        R[RAX] = 0x000306a9; R[RBX] = 0; R[RCX] = 0x00000001; R[RDX] = 0x178bfbff; break; /* edx: SSE2 等, ecx: SSSE3 bit */
    default:
        R[RAX] = 0; R[RBX] = 0; R[RCX] = 0; R[RDX] = 0; break;
    }
}
static uint64_t g_tsc;
void rdtsc_model(void) { g_tsc += 1000; R[RAX] = g_tsc & 0xffffffffULL; R[RDX] = g_tsc >> 32; }

/* ---- TEB / TLS 敷設 (gs:[0x58] = ThreadLocalStoragePointer 等) ---- */
void fle_install_teb(void) {
    memset((void*)A_(FLE_TEB), 0, 0x400);
    memset((void*)A_(FLE_TLSARRAY), 0, 64 * 8);
    for (int i = 0; i < 64; i++)
        ST64(FLE_TLSARRAY + 8 * (uint64_t)i, FLE_TLSBLOCK + 0x10000ull * (uint64_t)i);
    ST64(FLE_TEB + 0x30, FLE_TEB);            /* Self (TEB self reference) */
    ST64(FLE_TEB + 0x58, FLE_TLSARRAY);       /* ThreadLocalStoragePointer */
    ST64(FLE_TEB + 0x08, 0x1D8000ull);        /* StackBase (概算) */
    ST64(FLE_TEB + 0x10, 0x1D0000ull);        /* StackLimit */
    ST64(FLE_TEB + 0x60, 0);                  /* GDI/環境系は 0 */
    SEG_GS = FLE_TEB; SEG_FS = FLE_TEB;
}

/* ---- alloc log (native 側 heap 再生用) ---- */
void fle_alog(void* p, uint64_t n) {
    volatile uint32_t* L = (volatile uint32_t*)A_(FLE_ALOG);
    uint32_t c = L[0];
    if (c < 0x8000u) { L[2 + 2 * c] = (uint32_t)(uintptr_t)p; L[3 + 2 * c] = (uint32_t)n; L[0] = c + 1; }
}

/* ---- imports: callee 側が ret 相当 (R[RSP] += 8) を行う ---- */
#define IMP_RET() (R[RSP] += 8)
static void* fle_alloc(uint64_t sz, int zero) {
    void* p = malloc(sz ? (size_t)sz : 1);
    if (p && zero) memset(p, 0, sz);
    if (p) fle_alog(p, sz);
    return p;
}
void imp_HeapAlloc(void) {
    uint64_t flags = R[RDX] & 0xffffffff, sz = R[R8];
    void* p = fle_alloc(sz, (flags & 8) != 0);
    R[RAX] = (uint64_t)(uintptr_t)p; IMP_RET();
}
void imp_HeapFree(void) { R[RAX] = 1; IMP_RET(); }
void imp_HeapReAlloc(void) {
    /* 本体は未実装: 旧ポインタ内容は引継ぎせず新規確保 (使用経路で要確認) */
    void* p = fle_alloc(R[R9], 0);
    R[RAX] = (uint64_t)(uintptr_t)p; IMP_RET();
}
void imp_HeapSize(void) { R[RAX] = 0; IMP_RET(); }
void imp_HeapValidate(void) { R[RAX] = 1; IMP_RET(); }
void imp_GetProcessHeap(void) { R[RAX] = 0x1000; IMP_RET(); }
void imp_GetLastError(void) { R[RAX] = 0; IMP_RET(); }
void imp_SetLastError(void) { IMP_RET(); }
void imp_EnterCriticalSection(void) { IMP_RET(); }
void imp_LeaveCriticalSection(void) { IMP_RET(); }
void imp_InitializeCriticalSection(void) { IMP_RET(); }
void imp_InitializeCriticalSectionAndSpinCount(void) { R[RAX] = 1; IMP_RET(); }
void imp_DeleteCriticalSection(void) { IMP_RET(); }
void imp_GetCurrentThreadId(void) { R[RAX] = 1; IMP_RET(); }
void imp_GetCurrentProcessId(void) { R[RAX] = 1000; IMP_RET(); }
void imp_GetCurrentProcess(void) { R[RAX] = 0x2000; IMP_RET(); }
void imp_IsDebuggerPresent(void) { R[RAX] = 0; IMP_RET(); }
void imp_IsProcessorFeaturePresent(void) { R[RAX] = 1; IMP_RET(); }
/* Win32 TLS slot (TlsAlloc/TlsGetValue/TlsSetValue)。gs:[0x58] の TLS 配列 (コンパイラ生成 TLS 用) とは別。
 * 割当は連番、未設定 slot の値は 0 (仕様)。 */
static uint64_t g_tls_val[64];
static uint32_t g_tls_next;
void imp_TlsAlloc(void) {
    R[RAX] = g_tls_next < 64 ? g_tls_next++ : 0xFFFFFFFFULL; IMP_RET();
}
void imp_TlsGetValue(void) {
    uint32_t i = (uint32_t)R[RCX];
    R[RAX] = i < g_tls_next ? g_tls_val[i] : 0; IMP_RET();
}
void imp_TlsSetValue(void) {
    uint32_t i = (uint32_t)R[RCX];
    if (i < g_tls_next) { g_tls_val[i] = R[RDX]; R[RAX] = 1; } else R[RAX] = 0;
    IMP_RET();
}
void imp_QueryPerformanceCounter(void) { ST64(R[RCX], 0); R[RAX] = 1; IMP_RET(); }
void imp_QueryPerformanceFrequency(void) { ST64(R[RCX], 1000000000ULL); R[RAX] = 1; IMP_RET(); }
void imp_Sleep(void) { IMP_RET(); }
void imp_GetTickCount(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetTickCount64(void) { R[RAX] = 0; IMP_RET(); }
void imp_InitializeConditionVariable(void) { IMP_RET(); }
void imp_SleepConditionVariableCS(void) { R[RAX] = 0; IMP_RET(); }
void imp_WakeAllConditionVariable(void) { IMP_RET(); }
void imp_WakeConditionVariable(void) { IMP_RET(); }
void imp_TryEnterCriticalSection(void) { R[RAX] = 1; IMP_RET(); }
void imp_LoadLibraryExW(void) { R[RAX] = 0; IMP_RET(); }
void imp_LoadLibraryW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetModuleHandleW(void) { R[RAX] = 0x3000; IMP_RET(); }
void imp_GetProcAddress(void) { R[RAX] = fle_gpa_hook ? fle_gpa_hook(R[RCX], R[RDX]) : 0; IMP_RET(); }
void imp_FreeLibrary(void) { R[RAX] = 1; IMP_RET(); }
void imp_GetSystemTimeAsFileTime(void) { ST64(R[RCX], 0); IMP_RET(); }
void imp_GetSystemInfo(void) { memset((void*)A_(R[RCX]), 0, 40); ST32(R[RCX] + 0x18, 16); ST32(R[RCX] + 0x1c, 4096); IMP_RET(); } /* dwNumberOfProcessors=16, pageSize */
void imp_GetVersionExW(void) { memset((void*)A_(R[RCX]), 0, 284); ST32(R[RCX], 284); ST32(R[RCX] + 4, 6); ST32(R[RCX] + 8, 1); ST32(R[RCX] + 12, 7601); R[RAX] = 1; IMP_RET(); }
void imp_GetModuleFileNameW(void) { R[RAX] = 0; IMP_RET(); }
void imp_MultiByteToWideChar(void) { R[RAX] = 0; IMP_RET(); }
void imp_WideCharToMultiByte(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetLocaleInfoW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetUserDefaultUILanguage(void) { R[RAX] = 0x409; IMP_RET(); }
void imp_GetSystemDefaultLangID(void) { R[RAX] = 0x409; IMP_RET(); }
void imp_GetComputerNameW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetUserNameW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetEnvironmentVariableW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetEnvironmentStringsW(void) { R[RAX] = (uint64_t)(uintptr_t)L"\0"; IMP_RET(); }
void imp_FreeEnvironmentStringsW(void) { R[RAX] = 1; IMP_RET(); }
void imp_ExitProcess(void) { fprintf(stderr, "[fle] ExitProcess(%llu)\n", (unsigned long long)R[RCX]); exit((int)(R[RCX] & 0xff)); }
void imp_TerminateProcess(void) { fprintf(stderr, "[fle] TerminateProcess\n"); exit(3); }
void imp_RaiseException(void) { fprintf(stderr, "[fle] RaiseException(0x%llx) — fail-fast (SEH は対象外)\n", (unsigned long long)R[RCX]); abort(); }
void imp_SetUnhandledExceptionFilter(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetStdHandle(void) { R[RAX] = 0; IMP_RET(); }
void imp_WriteFile(void) { R[RAX] = 1; IMP_RET(); }
void imp_CloseHandle(void) { R[RAX] = 1; IMP_RET(); }
void imp_CreateFileW(void) { R[RAX] = (uint64_t)(uintptr_t)-1; IMP_RET(); }
void imp_VirtualAlloc(void) {
    /* bump allocator (liftdiff ld_core と同型) */
    static uint64_t cur = 0x2100000ull;
    uint64_t sz = (R[RDX] + 0xffff) & ~0xffffull;
    void* p = (void*)A_(cur); cur += sz;
    memset(p, 0, sz);
    R[RAX] = (uint64_t)(uintptr_t)p; IMP_RET();
}
void imp_VirtualFree(void) { R[RAX] = 1; IMP_RET(); }
void imp_VirtualProtect(void) { R[RAX] = 1; IMP_RET(); }
void imp_FlushInstructionCache(void) { R[RAX] = 1; IMP_RET(); }
void imp_GetCPInfo(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetACP(void) { R[RAX] = 1252; IMP_RET(); }
void imp_GetOEMCP(void) { R[RAX] = 437; IMP_RET(); }
void imp_IsValidCodePage(void) { R[RAX] = 1; IMP_RET(); }
void imp_GetStringTypeW(void) { R[RAX] = 0; IMP_RET(); }
void imp_LCMapStringW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetFileType(void) { R[RAX] = 2; IMP_RET(); }
void imp_SetHandleCount(void) { R[RAX] = 32; IMP_RET(); }
void imp_GetStartupInfoW(void) { memset((void*)A_(R[RCX]), 0, 68); IMP_RET(); }
void imp_GetCommandLineA(void) { R[RAX] = (uint64_t)(uintptr_t)""; IMP_RET(); }
void imp_GetCommandLineW(void) { R[RAX] = (uint64_t)(uintptr_t)L""; IMP_RET(); }
void imp_GetModuleFileNameA(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetModuleHandleA(void) { R[RAX] = 0x3000; IMP_RET(); }
void imp_RtlUnwind(void) { IMP_RET(); }
void imp_SetFilePointer(void) { R[RAX] = (uint64_t)-1; IMP_RET(); }
void imp_ReadFile(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetFileAttributesW(void) { R[RAX] = (uint64_t)-1; IMP_RET(); }
void imp_GetTempPathW(void) { R[RAX] = 0; IMP_RET(); }
void imp_CreateDirectoryW(void) { R[RAX] = 0; IMP_RET(); }
void imp_DeleteFileW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetCurrentDirectoryW(void) { R[RAX] = 0; IMP_RET(); }
void imp_SetCurrentDirectoryW(void) { R[RAX] = 0; IMP_RET(); }
void imp_FindFirstFileW(void) { R[RAX] = (uint64_t)(uintptr_t)-1; IMP_RET(); }
void imp_FindNextFileW(void) { R[RAX] = 0; IMP_RET(); }
void imp_FindClose(void) { R[RAX] = 1; IMP_RET(); }
void imp_InterlockedIncrement(void) { ST32(R[RCX], LD32(R[RCX]) + 1); R[RAX] = LD32(R[RCX]); IMP_RET(); }
void imp_InterlockedDecrement(void) { ST32(R[RCX], LD32(R[RCX]) - 1); R[RAX] = LD32(R[RCX]); IMP_RET(); }
void imp_InterlockedExchange(void) { uint32_t o = LD32(R[RCX]); ST32(R[RCX], (uint32_t)R[RDX]); R[RAX] = o; IMP_RET(); }
void imp_InitializeSRWLock(void) { IMP_RET(); }
void imp_AcquireSRWLockExclusive(void) { IMP_RET(); }
void imp_ReleaseSRWLockExclusive(void) { IMP_RET(); }
void imp_AcquireSRWLockShared(void) { IMP_RET(); }
void imp_ReleaseSRWLockShared(void) { IMP_RET(); }
void imp_GetLogicalDrives(void) { R[RAX] = 0x4; IMP_RET(); }
void imp_GetDriveTypeW(void) { R[RAX] = 3; IMP_RET(); }
void imp_GetDiskFreeSpaceExW(void) { R[RAX] = 0; IMP_RET(); }
void imp_OutputDebugStringW(void) { IMP_RET(); }
void imp_IsDBCSLeadByte(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetProcessAffinityMask(void) { ST64(R[RDX], 0xffff); ST64(R[R8], 0xffff); R[RAX] = 1; IMP_RET(); }
void imp_SetThreadAffinityMask(void) { R[RAX] = 1; IMP_RET(); }
void imp_SwitchToThread(void) { R[RAX] = 1; IMP_RET(); }
void imp_MapViewOfFile(void) { R[RAX] = 0; IMP_RET(); }
void imp_UnmapViewOfFile(void) { R[RAX] = 1; IMP_RET(); }
void imp_CreateFileMappingW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetPrivateProfileIntW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetPrivateProfileStringW(void) { R[RAX] = 0; IMP_RET(); }
void imp_WritePrivateProfileStringW(void) { R[RAX] = 1; IMP_RET(); }
void imp_GetWindowsDirectoryW(void) { R[RAX] = 0; IMP_RET(); }
void imp_GetSystemDirectoryW(void) { R[RAX] = 0; IMP_RET(); }
void imp_CoInitialize(void) { R[RAX] = 0; IMP_RET(); }
void imp_CoUninitialize(void) { IMP_RET(); }
void imp_CoCreateInstance(void) { R[RAX] = (uint64_t)-1; IMP_RET(); }
void imp_CoTaskMemAlloc(void) { void* p = fle_alloc(R[RCX], 1); R[RAX] = (uint64_t)(uintptr_t)p; IMP_RET(); }
void imp_CoTaskMemFree(void) { IMP_RET(); }
void imp_PropVariantClear(void) { R[RAX] = 0; IMP_RET(); }

/* rsqrtps の実機近似 (gen_simd.py の kh_rsqrt_exact と同一式・同一表)。
 * 指数則 (実測): rsqrtps 190-((e+1)>>1)。奇偶で別表 (√2 因子)。rcpps は x64c.py が生成 C 内の kh_rcp_exact を使う。 */
uint32_t fle_rsqrt_exact(uint32_t x) {
    uint32_t s = x & 0x80000000u, e = (x >> 23) & 0xff, man = x & 0x7fffffu;
    if (e == 0) return s | 0x7f800000u;
    if (e == 0xff) return man ? (s | 0x7f800000u | (man | 0x400000u)) : (s ? 0xffc00000u : 0u);
    if (s) return 0xffc00000u;
    return (((uint32_t)(190 - (int)((e + 1) >> 1)) << 23) | ((e & 1) ? kh_at_rsq_odd[(x >> 11) & 0xfffu]
                                                                : kh_at_rsq_even[(x >> 11) & 0xfffu]));
}
