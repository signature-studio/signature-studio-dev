/* SEH 第一手スタブ + CRT ロック群。
 *
 * 方針 (inventory 参照): wasm には構造化例外の巻き戻し機構が無いため、
 *   - AddVectoredExceptionHandler/Remove: ハンドラ表を持つ (RaiseException 時に先頭から呼ぶ)
 *   - RaiseException: VEH → (任意) raise フック → UnhandledExceptionFilter の順に試し、
 *     EXCEPTION_CONTINUE_EXECUTION が返れば復帰、それ以外は *fail-fast* (例外コード+引数を stderr に出して abort)
 *   - SEH 実巻き戻し (#171): lift 側が ShxSehFrame (setjmp 系) を shimx_seh_enter で登録した場合、RaiseException は
 *     VEH → frame 鎖の 2 相ディスパッチ (検索相: scope table の catch-all / typed except、unwind 相: 内側 frame の
 *     pad を pad(&{rec,ctx}, frame) で実行) → longjmp で捕捉 frame へ復帰。RtlUnwind/RtlUnwindEx も同じ機構で
 *     targetFrame まで巻き戻す。frame が 1 つも無い場合は従来どおり fail-fast (scope table 形式は shimx.h 参照)
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

/* ---------------------------------------------------------------
 * SEH frame 鎖 (スレッド毎)
 * --------------------------------------------------------------- */
#define SEH_UNWINDING        0x2u
#define SEH_EXIT_UNWIND      0x4u
#define STATUS_UNWIND        0xC0000027u
static _Thread_local ShxSehFrame* t_seh_top;
static _Thread_local unsigned t_seh_depth;
static _Thread_local EXCEPTION_RECORD64 t_seh_exc;
static _Thread_local int t_seh_exc_valid;
static shimx_seh_pad_fn (*g_pad_resolver)(uint32_t);
static int (*g_typed_matcher)(const EXCEPTION_RECORD64*, uint32_t, uint32_t*);

void shimx_seh_set_pad_resolver(shimx_seh_pad_fn (*fn)(uint32_t rva)) { g_pad_resolver = fn; }
void shimx_seh_set_typed_matcher(int (*fn)(const EXCEPTION_RECORD64*, uint32_t, uint32_t*)) { g_typed_matcher = fn; }
const EXCEPTION_RECORD64* shimx_seh_current_exception(void) { return t_seh_exc_valid ? &t_seh_exc : NULL; }
unsigned shimx_seh_depth(void) { return t_seh_depth; }

void shimx_seh_enter(ShxSehFrame* f) {
    f->prev = t_seh_top;
    t_seh_top = f;
    t_seh_depth++;
}
void shimx_seh_leave(ShxSehFrame* f) {
    for (ShxSehFrame* p = t_seh_top; p; p = p->prev) {
        if (p == f) {
            unsigned n = 0;
            for (ShxSehFrame* q = f->prev; q; q = q->prev) n++;
            t_seh_top = f->prev;
            t_seh_depth = n;
            return;
        }
    }
}

static uint32_t scope_count(const ShxSehFrame* f) { return f->scopes ? f->scopes[0] : 0; }
static const ShxSehScope* scope_at(const ShxSehFrame* f, uint32_t i) { return (const ShxSehScope*)(f->scopes + 1) + i; }

/* 検索相: 捕捉する frame と再開先を返す (1=見つかった) */
static int seh_search(const EXCEPTION_RECORD64* rec, ShxSehFrame** out, uint64_t* ip) {
    for (ShxSehFrame* f = t_seh_top; f; f = f->prev) {
        uint32_t n = scope_count(f), pc = f->pc;
        for (uint32_t i = 0; i < n; i++) {
            const ShxSehScope* s = scope_at(f, i);
            if (pc < s->begin || pc >= s->end) continue;
            if (s->kind == 2) { *out = f; *ip = s->target; return 1; }
            if (s->kind > 2 && g_typed_matcher) {
                uint32_t h = 0;
                if (g_typed_matcher(rec, s->kind, &h)) { *out = f; *ip = h; return 1; }
            }
        }
    }
    return 0;
}

/* frame f の kind 0/1 scope のうち f->pc を含むものの pad を実行する */
static void seh_run_pads(ShxSehFrame* f, EXCEPTION_POINTERS64* ep) {
    uint32_t n = scope_count(f), pc = f->pc;
    for (uint32_t i = 0; i < n; i++) {
        const ShxSehScope* s = scope_at(f, i);
        if (s->kind > 1 || pc < s->begin || pc >= s->end) continue;
        shimx_seh_pad_fn pad = g_pad_resolver ? g_pad_resolver(s->target) : NULL;
        if (!pad) shim_unimplemented("SEH unwind: pad resolver が未設定または pad 未解決 (shimx_seh_set_pad_resolver)");
        pad((uint64_t)(uintptr_t)ep, f->frame);
    }
}

/* target より内側の frame の pad を内側から実行して鎖から外す。target=NULL なら全 frame。
 * pad 実行中は当該 frame を鎖から外す (pad 内の再送出は外側 frame だけを見る)。 */
static void seh_unwind_pads(ShxSehFrame* target, const EXCEPTION_RECORD64* rec, DWORD extra) {
    EXCEPTION_RECORD64 ur;
    uint8_t ctx[1232];
    memset(ctx, 0, sizeof ctx);
    if (rec) ur = *rec; else { memset(&ur, 0, sizeof ur); ur.ExceptionCode = STATUS_UNWIND; }
    ur.ExceptionFlags |= SEH_UNWINDING | extra;
    EXCEPTION_POINTERS64 ep = { (uint64_t)(uintptr_t)&ur, (uint64_t)(uintptr_t)ctx };
    while (t_seh_top && t_seh_top != target) {
        ShxSehFrame* g = t_seh_top;
        t_seh_top = g->prev;
        if (t_seh_depth) t_seh_depth--;
        seh_run_pads(g, &ep);
    }
}

static void seh_resume(ShxSehFrame* f, uint64_t ip, uint64_t ret) {
    unsigned n = 0;
    for (ShxSehFrame* q = f; q; q = q->prev) n++;
    t_seh_top = f;
    t_seh_depth = n;
    f->resume_ip = ip;
    f->resume_ret = ret;
    longjmp(f->jb, 1);
}

static int seh_frame_linked(const ShxSehFrame* f) {
    for (const ShxSehFrame* p = t_seh_top; p; p = p->prev) if (p == f) return 1;
    return 0;
}

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
    if (t_seh_top) {
        ShxSehFrame* target = NULL; uint64_t ip = 0;
        if (seh_search(&rec, &target, &ip)) {
            t_seh_exc = rec; t_seh_exc_valid = 1;
            seh_unwind_pads(target, &rec, 0);
            seh_resume(target, ip, 0);          /* 戻らない */
        }
    }
    if (g_uef) {
        LONG r = g_uef(&ep);
        if (r == EXCEPTION_CONTINUE_EXECUTION && !(rec.ExceptionFlags & EXCEPTION_NONCONTINUABLE)) return;
    }
    char d[256]; describe(&rec, d, sizeof d);
    char msg[400];
    snprintf(msg, sizeof msg, "RaiseException (%s) — 捕捉する SEH frame なし (fail-fast)", d);
    shim_unimplemented(msg);
}

/* targetFrame = ShxSehFrame.frame の値。一致する frame まで内側を巻き戻し、targetIp (=resume_ip) へ longjmp。
 * targetFrame==NULL は全 frame を巻き戻して復帰 (exit unwind)。frame 未登録なら従来どおり fail-fast。 */
static void seh_rtl_unwind(const char* api, PVOID targetFrame, PVOID targetIp, EXCEPTION_RECORD64* rec, PVOID retval) {
    if (!t_seh_top) {
        char m[96]; snprintf(m, sizeof m, "%s — SEH frame 未登録 (fail-fast)", api);
        shim_unimplemented(m);
    }
    if (!targetFrame) {
        seh_unwind_pads(NULL, rec, SEH_EXIT_UNWIND);
        return;
    }
    ShxSehFrame* target = NULL;
    for (ShxSehFrame* f = t_seh_top; f; f = f->prev) if (f->frame == (uint64_t)(uintptr_t)targetFrame) { target = f; break; }
    if (!target) {
        char m[96]; snprintf(m, sizeof m, "%s — targetFrame に一致する SEH frame なし (fail-fast)", api);
        shim_unimplemented(m);
    }
    seh_unwind_pads(target, rec, 0);
    if (!seh_frame_linked(target)) shim_unimplemented("SEH unwind: target frame が pad 内で破棄された");
    seh_resume(target, (uint64_t)(uintptr_t)targetIp, (uint64_t)(uintptr_t)retval);
}
void RtlUnwind(PVOID targetFrame, PVOID targetIp, EXCEPTION_RECORD64* rec, PVOID retval) {
    seh_rtl_unwind("RtlUnwind", targetFrame, targetIp, rec, retval);
}
void RtlUnwindEx(PVOID targetFrame, PVOID targetIp, EXCEPTION_RECORD64* rec, PVOID retval, PVOID ctx, PVOID hist) {
    (void)ctx; (void)hist;
    seh_rtl_unwind("RtlUnwindEx", targetFrame, targetIp, rec, retval);
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
