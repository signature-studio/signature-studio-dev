/* スレッドローカル状態: LastError / TID / 擬似 TEB (gs: アクセス) / TLS / FLS。
 *
 * M4 差分: GetLastError はプロセス単位だった → スレッドローカル化 (TEB+0x68 に置く)。
 * 擬似 TEB は Win64 TEB のオフセットを再現する (lifted MSVC CRT の __readgsqword 用):
 *   +0x30 Self, +0x40 UniqueProcess, +0x48 UniqueThread, +0x58 ThreadLocalStoragePointer,
 *   +0x60 PEB, +0x68 LastErrorValue, +0x1480 TlsSlots[64], +0x1780 TlsExpansionSlots
 */
#include "shimx_internal.h"

#define TEB_SIZE 0x1840
#define PEB_SIZE 0x400
#define SHX_TLS_MIN 64
#define SHX_TLS_MAX 1088
#define SHX_FLS_MAX 256

static _Thread_local uint8_t t_teb[TEB_SIZE] __attribute__((aligned(16)));
static _Thread_local int t_teb_ready;
static _Thread_local uint64_t t_tls_exp[SHX_TLS_MAX - SHX_TLS_MIN];
static _Thread_local uint64_t t_tls_ptrs[8];
static _Thread_local DWORD t_tid;
static _Thread_local ShxObj* t_self_obj;
static _Thread_local void* t_fls[SHX_FLS_MAX];
static uint8_t g_peb[PEB_SIZE] __attribute__((aligned(16)));
static volatile uint32_t g_tid_counter = 0x100;
static uint8_t g_tls_used[SHX_TLS_MAX];
static uint8_t g_fls_used[SHX_FLS_MAX];
static PFLS_CALLBACK_FUNCTION g_fls_cb[SHX_FLS_MAX];

#define U64(off) (*(uint64_t*)&t_teb[(off)])
#define U32(off) (*(uint32_t*)&t_teb[(off)])

DWORD shx_tid(void) {
    if (!t_tid) t_tid = __atomic_add_fetch(&g_tid_counter, 4u, __ATOMIC_SEQ_CST);
    return t_tid;
}

void* shx_teb(void) {
    if (!t_teb_ready) {
        t_teb_ready = 1;
        U64(0x30) = (uint64_t)(uintptr_t)t_teb;
        U64(0x40) = 0x1000;                       /* pid */
        U64(0x48) = shx_tid();
        U64(0x58) = (uint64_t)(uintptr_t)t_tls_ptrs;
        U64(0x60) = (uint64_t)(uintptr_t)g_peb;
        U64(0x1780) = (uint64_t)(uintptr_t)t_tls_exp;
        /* PEB: +0x02 BeingDebugged=0, +0xB8 NumberOfProcessors, +0x118 OSMajor, +0x11C OSMinor, +0x120 OSBuild */
        *(uint32_t*)&g_peb[0xB8] = 8;
        *(uint32_t*)&g_peb[0x118] = 10;
        *(uint32_t*)&g_peb[0x11C] = 0;
        *(uint16_t*)&g_peb[0x120] = 19045;
        *(uint32_t*)&g_peb[0x124] = 2;
    }
    return t_teb;
}

DWORD GetLastError(void) { return U32(0x68); }
void  SetLastError(DWORD e) { U32(0x68) = e; }
void  shx_set_last_error(DWORD e) { U32(0x68) = e; }

/* ---- gs: 読み書き ---- */
static void gs_range(uint64_t off, uint64_t n) {
    if (off + n > TEB_SIZE) {
        fprintf(stderr, "[shim] FAIL-FAST: unimplemented Win32 API: __readgs*(off=0x%llx, size=%llu) (擬似 TEB 範囲外)\n",
                (unsigned long long)off, (unsigned long long)n);
        fflush(stderr);
        abort();
    }
}
uint64_t __readgsqword(uint64_t off) { shx_teb(); gs_range(off, 8); return *(uint64_t*)&t_teb[off]; }
uint32_t __readgsdword(uint64_t off) { shx_teb(); gs_range(off, 4); return *(uint32_t*)&t_teb[off]; }
uint16_t __readgsword(uint64_t off)  { shx_teb(); gs_range(off, 2); return *(uint16_t*)&t_teb[off]; }
uint8_t  __readgsbyte(uint64_t off)  { shx_teb(); gs_range(off, 1); return t_teb[off]; }
void __writegsqword(uint64_t off, uint64_t v) { shx_teb(); gs_range(off, 8); *(uint64_t*)&t_teb[off] = v; }
void __writegsdword(uint64_t off, uint32_t v) { shx_teb(); gs_range(off, 4); *(uint32_t*)&t_teb[off] = v; }

/* ---- 呼び出しスレッドの OBJ_THREAD ---- */
ShxObj* shx_self_thread_obj(void) {
    if (!t_self_obj) {
        ShxObj* o = shx_obj_new(OBJ_THREAD);
        o->tid = shx_tid();
        o->started = 1;
        o->joined = 1;               /* 外来 (main など): join 対象外 */
        o->exit_code = STILL_ACTIVE;
        t_self_obj = o;              /* thread-local が参照 1 を保持 */
    }
    __atomic_add_fetch(&t_self_obj->refs, 1, __ATOMIC_SEQ_CST);
    return t_self_obj;
}
/* sync.c の trampoline から: 新スレッド自身の ShxObj を thread-local に設定 (内部参照 1 を移譲) */
void shx_set_self(ShxObj* o) { t_self_obj = o; t_tid = o->tid; }
void shx_clear_self(void)    { t_self_obj = NULL; }
DWORD shx_alloc_tid(void)    { return __atomic_add_fetch(&g_tid_counter, 4u, __ATOMIC_SEQ_CST); }

/* ---------------------------------------------------------------
 * TLS (TlsAlloc: 最大 1088 スロット)
 * --------------------------------------------------------------- */
DWORD TlsAlloc(void) {
    shx_teb();
    DWORD found = TLS_OUT_OF_INDEXES;
    shx_lock();
    for (DWORD i = 0; i < SHX_TLS_MAX; i++) {
        if (!g_tls_used[i]) { g_tls_used[i] = 1; found = i; break; }
    }
    shx_unlock();
    if (found == TLS_OUT_OF_INDEXES) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return found; }
    if (found < SHX_TLS_MIN) U64(0x1480 + found * 8) = 0; else t_tls_exp[found - SHX_TLS_MIN] = 0;
    SetLastError(ERROR_SUCCESS);
    return found;
}

BOOL TlsFree(DWORD idx) {
    BOOL ok = FALSE;
    shx_lock();
    if (idx < SHX_TLS_MAX && g_tls_used[idx]) { g_tls_used[idx] = 0; ok = TRUE; }
    shx_unlock();
    if (!ok) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    shx_teb();
    if (idx < SHX_TLS_MIN) U64(0x1480 + idx * 8) = 0; else t_tls_exp[idx - SHX_TLS_MIN] = 0;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

LPVOID TlsGetValue(DWORD idx) {
    shx_teb();
    if (idx >= SHX_TLS_MAX) { SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    SetLastError(ERROR_SUCCESS);
    uint64_t v = idx < SHX_TLS_MIN ? U64(0x1480 + idx * 8) : t_tls_exp[idx - SHX_TLS_MIN];
    return (LPVOID)(uintptr_t)v;
}

BOOL TlsSetValue(DWORD idx, LPVOID val) {
    shx_teb();
    if (idx >= SHX_TLS_MAX || !g_tls_used[idx]) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (idx < SHX_TLS_MIN) U64(0x1480 + idx * 8) = (uint64_t)(uintptr_t)val;
    else t_tls_exp[idx - SHX_TLS_MIN] = (uint64_t)(uintptr_t)val;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

/* ---------------------------------------------------------------
 * FLS (Fiber Local Storage; MSVC CRT が使用)。スレッド終了時にコールバックを呼ぶ
 * --------------------------------------------------------------- */
DWORD FlsAlloc(PFLS_CALLBACK_FUNCTION cb) {
    DWORD found = FLS_OUT_OF_INDEXES;
    shx_lock();
    for (DWORD i = 0; i < SHX_FLS_MAX; i++) {
        if (!g_fls_used[i]) { g_fls_used[i] = 1; g_fls_cb[i] = cb; found = i; break; }
    }
    shx_unlock();
    if (found == FLS_OUT_OF_INDEXES) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return found; }
    t_fls[found] = NULL;
    SetLastError(ERROR_SUCCESS);
    return found;
}

BOOL FlsFree(DWORD idx) {
    PFLS_CALLBACK_FUNCTION cb = NULL;
    BOOL ok = FALSE;
    shx_lock();
    if (idx < SHX_FLS_MAX && g_fls_used[idx]) { g_fls_used[idx] = 0; cb = g_fls_cb[idx]; g_fls_cb[idx] = NULL; ok = TRUE; }
    shx_unlock();
    if (!ok) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    void* v = t_fls[idx];
    t_fls[idx] = NULL;
    if (cb && v) cb(v);
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

PVOID FlsGetValue(DWORD idx) {
    if (idx >= SHX_FLS_MAX || !g_fls_used[idx]) { SetLastError(ERROR_INVALID_PARAMETER); return NULL; }
    SetLastError(ERROR_SUCCESS);
    return t_fls[idx];
}

BOOL FlsSetValue(DWORD idx, PVOID val) {
    if (idx >= SHX_FLS_MAX || !g_fls_used[idx]) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    t_fls[idx] = val;
    SetLastError(ERROR_SUCCESS);
    return TRUE;
}

void shx_thread_exit_cleanup(void) {
    for (int pass = 0; pass < 4; pass++) {
        int any = 0;
        for (DWORD i = 0; i < SHX_FLS_MAX; i++) {
            if (g_fls_used[i] && g_fls_cb[i] && t_fls[i]) {
                void* v = t_fls[i];
                t_fls[i] = NULL;
                g_fls_cb[i](v);
                any = 1;
            }
        }
        if (!any) break;
    }
}

/* ---------------------------------------------------------------
 * EncodePointer / DecodePointer (恒等。保護目的の符号化は不要)
 * --------------------------------------------------------------- */
PVOID EncodePointer(PVOID p) { return p; }
PVOID DecodePointer(PVOID p) { return p; }

/* ---------------------------------------------------------------
 * fail-fast (M4 継承)
 * --------------------------------------------------------------- */
void shim_unimplemented(const char* apiName) {
    fprintf(stderr, "[shim] FAIL-FAST: unimplemented Win32 API: %s\n",
            apiName ? apiName : "(unknown)");
    fflush(stderr);
    abort();
}
