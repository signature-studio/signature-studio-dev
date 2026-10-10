/* SEH 第一手スタブ + CRT ロック群。
 *
 * 方針 (inventory 参照): wasm には構造化例外の巻き戻し機構が無いため、
 *   - AddVectoredExceptionHandler/Remove: ハンドラ表を持つ (RaiseException 時に先頭から呼ぶ)
 *   - RaiseException: VEH → (任意) raise フック → UnhandledExceptionFilter の順に試し、
 *     EXCEPTION_CONTINUE_EXECUTION が返れば復帰、それ以外は *fail-fast* (例外コード+引数を stderr に出して abort)
 *   - RtlUnwind/RtlUnwindEx: fail-fast (try-finally / except の実巻き戻しは lift 側 (M2: UHANDLER 8,021 件) の課題)
 *   - RtlCaptureContext/RtlLookupFunctionEntry/RtlVirtualUnwind/RtlPcToFileHeader: MSVC CRT の致命エラー経路
 *     (abort/invalid_parameter → UnhandledExceptionFilter → TerminateProcess) を link・通過させる最小実装
 */
#include "shimx_internal.h"

typedef struct VehNode { PVECTORED_EXCEPTION_HANDLER h; struct VehNode* next; } VehNode;
static VehNode* g_veh;
static shx_mutex_t g_veh_lk;
static LPTOP_LEVEL_EXCEPTION_FILTER g_uef;
static int (*g_raise_hook)(EXCEPTION_RECORD64*);
void shimx_set_raise_hook(int (*fn)(EXCEPTION_RECORD64*)) { g_raise_hook = fn; }

PVOID AddVectoredExceptionHandler(ULONG first, PVECTORED_EXCEPTION_HANDLER h) {
    if (!h) return NULL;
    VehNode* n = (VehNode*)calloc(1, sizeof(VehNode));
    n->h = h;
    shx_mutex_lock(&g_veh_lk);
    if (first || !g_veh) { n->next = g_veh; g_veh = n; }
    else { VehNode* t = g_veh; while (t->next) t = t->next; t->next = n; }
    shx_mutex_unlock(&g_veh_lk);
    return n;
}
ULONG RemoveVectoredExceptionHandler(PVOID p) {
    ULONG ok = 0;
    shx_mutex_lock(&g_veh_lk);
    for (VehNode** pp = &g_veh; *pp; pp = &(*pp)->next)
        if (*pp == (VehNode*)p) { VehNode* d = *pp; *pp = d->next; free(d); ok = 1; break; }
    shx_mutex_unlock(&g_veh_lk);
    return ok;
}
LPTOP_LEVEL_EXCEPTION_FILTER SetUnhandledExceptionFilter(LPTOP_LEVEL_EXCEPTION_FILTER f) {
    LPTOP_LEVEL_EXCEPTION_FILTER old = g_uef;
    g_uef = f;
    return old;
}

static void describe(const EXCEPTION_RECORD64* r, char* out, size_t n) {
    int k = snprintf(out, n, "code=0x%08X flags=0x%X nparams=%u", r->ExceptionCode, r->ExceptionFlags, r->NumberParameters);
    for (DWORD i = 0; i < r->NumberParameters && i < 4 && (size_t)k < n; i++)
        k += snprintf(out + k, n - (size_t)k, " p%u=0x%llX", i, (unsigned long long)r->ExceptionInformation[i]);
}

LONG UnhandledExceptionFilter(EXCEPTION_POINTERS64* ep) {
    char d[256] = "(null)";
    if (ep && ep->ExceptionRecord) describe((EXCEPTION_RECORD64*)(uintptr_t)ep->ExceptionRecord, d, sizeof d);
    fprintf(stderr, "[shimx] UnhandledExceptionFilter: %s\n", d);
    fflush(stderr);
    return EXCEPTION_EXECUTE_HANDLER;
}

void RaiseException(DWORD code, DWORD flags, DWORD nargs, const uint64_t* args) {
    EXCEPTION_RECORD64 rec;
    uint8_t ctx[1232];
    memset(&rec, 0, sizeof rec);
    memset(ctx, 0, sizeof ctx);
    rec.ExceptionCode = code;
    rec.ExceptionFlags = flags & EXCEPTION_NONCONTINUABLE;
    rec.NumberParameters = nargs > EXCEPTION_MAXIMUM_PARAMETERS ? EXCEPTION_MAXIMUM_PARAMETERS : nargs;
    for (DWORD i = 0; args && i < rec.NumberParameters; i++) rec.ExceptionInformation[i] = args[i];
    if (code == 0x40010006u || code == 0x4001000Au || code == 0x406D1388u) return;   /* DbgPrint / スレッド命名: 無害 */
    EXCEPTION_POINTERS64 ep = { (uint64_t)(uintptr_t)&rec, (uint64_t)(uintptr_t)ctx };
    if (g_raise_hook && g_raise_hook(&rec)) return;
    VehNode* snapshot[16]; int ns = 0;
    shx_mutex_lock(&g_veh_lk);
    for (VehNode* v = g_veh; v && ns < 16; v = v->next) snapshot[ns++] = v;
    shx_mutex_unlock(&g_veh_lk);
    for (int i = 0; i < ns; i++) {
        LONG r = snapshot[i]->h(&ep);
        if (r == EXCEPTION_CONTINUE_EXECUTION && !(rec.ExceptionFlags & EXCEPTION_NONCONTINUABLE)) return;
    }
    if (g_uef) {
        LONG r = g_uef(&ep);
        if (r == EXCEPTION_CONTINUE_EXECUTION && !(rec.ExceptionFlags & EXCEPTION_NONCONTINUABLE)) return;
    }
    char d[256]; describe(&rec, d, sizeof d);
    char msg[400];
    snprintf(msg, sizeof msg, "RaiseException (%s) — SEH 巻き戻し未対応 (第一手: fail-fast)", d);
    shim_unimplemented(msg);
}

void RtlUnwind(PVOID targetFrame, PVOID targetIp, EXCEPTION_RECORD64* rec, PVOID retval) {
    (void)targetFrame; (void)targetIp; (void)rec; (void)retval;
    shim_unimplemented("RtlUnwind — SEH 巻き戻し未対応 (第一手: fail-fast)");
}
void RtlUnwindEx(PVOID targetFrame, PVOID targetIp, EXCEPTION_RECORD64* rec, PVOID retval, PVOID ctx, PVOID hist) {
    (void)targetFrame; (void)targetIp; (void)rec; (void)retval; (void)ctx; (void)hist;
    shim_unimplemented("RtlUnwindEx — SEH 巻き戻し未対応 (第一手: fail-fast)");
}

void RtlCaptureContext(PVOID ctx) { if (ctx) memset(ctx, 0, 1232); }
PVOID RtlLookupFunctionEntry(DWORD64 pc, DWORD64* base, PVOID hist) {
    (void)pc; (void)hist;
    if (base) *base = 0;
    return NULL;     /* 関数表なし = leaf 扱い */
}
PVOID RtlVirtualUnwind(DWORD type, DWORD64 base, DWORD64 pc, PVOID fe, PVOID ctx, PVOID* hdata,
                       DWORD64* frame, PVOID ctxptrs) {
    (void)type; (void)base; (void)pc; (void)fe; (void)ctx; (void)ctxptrs;
    if (hdata) *hdata = NULL;
    if (frame) *frame = 0;
    return NULL;     /* ハンドラ無し */
}
PVOID RtlPcToFileHeader(PVOID pc, PVOID* base) {
    HMODULE m = 0;
    GetModuleHandleExW(4u | 2u, (LPCWSTR)pc, &m);
    if (base) *base = (PVOID)m;
    return (PVOID)m;
}

/* ---------------------------------------------------------------
 * CRT ロック群: 64 本の CRITICAL_SECTION (Win64 40B レイアウト) を遅延初期化
 * --------------------------------------------------------------- */
static uint64_t g_crt_cs[64][5];
static volatile uint32_t g_crt_inited[64];
static void* crt_cs(int n) {
    unsigned i = (unsigned)n & 63u;
    if (!g_crt_inited[i]) {
        shx_lock();
        if (!g_crt_inited[i]) { InitializeCriticalSection(g_crt_cs[i]); g_crt_inited[i] = 1; }
        shx_unlock();
    }
    return g_crt_cs[i];
}
void _lock(int n) { EnterCriticalSection(crt_cs(n)); }
void _unlock(int n) { LeaveCriticalSection(crt_cs(n)); }
void _mlock(int n) { _lock(n); }
void _munlock(int n) { _unlock(n); }
void __acrt_lock(int n) { _lock(n); }
void __acrt_unlock(int n) { _unlock(n); }
void _lock_file(void* fp) { EnterCriticalSection(crt_cs(32 + (int)(((uintptr_t)fp >> 4) % 31))); }
void _unlock_file(void* fp) { LeaveCriticalSection(crt_cs(32 + (int)(((uintptr_t)fp >> 4) % 31))); }
void _amsg_exit(int n) {
    fprintf(stderr, "[shimx] _amsg_exit(%d): CRT runtime error\n", n);
    ExitProcess(255);
}
