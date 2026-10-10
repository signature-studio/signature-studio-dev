/* 待機 / Event / Mutex / Semaphore (名前付き対応)。
 *
 * 待機方式: 全 kernel object の状態変化で g_shx_sig_seq を進めて futex wake。
 *   待機側は seq を読む → (shx_lock 下で) 全 object を評価 → 取れなければ seq で futex_wait。
 *   WaitForMultipleObjects(waitAll) は shx_lock 保持中に「全員 signaled」を確認して一括取得。
 */
#include "shimx_internal.h"

extern volatile uint32_t g_shx_sig_seq;

/* shx_lock 保持中。signaled か (取得はしない) */
static int obj_signaled(ShxObj* o, DWORD tid) {
    switch (o->type) {
        case OBJ_EVENT:   return o->state != 0;
        case OBJ_THREAD:
        case OBJ_PROCESS: return o->state != 0;
        case OBJ_MUTEX:   return o->owner == 0 || o->owner == tid;
        case OBJ_SEM:     return o->count > 0;
        case OBJ_FILE:    return 1;
        default:          return -1;   /* 待機不可 */
    }
}

/* shx_lock 保持中。signaled なら取得 (auto-reset 消費等) */
static void obj_acquire(ShxObj* o, DWORD tid) {
    switch (o->type) {
        case OBJ_EVENT:  if (!o->manual) o->state = 0; break;
        case OBJ_MUTEX:  o->owner = tid; o->rec++; break;
        case OBJ_SEM:    o->count--; break;
        default: break;
    }
}

DWORD shx_wait_objs(DWORD n, ShxObj** objs, BOOL all, DWORD ms) {
    DWORD tid = shx_tid();
    double deadline = (ms == INFINITE) ? INFINITY : shx_now_ms() + (double)ms;
    for (;;) {
        uint32_t seq = __atomic_load_n(&g_shx_sig_seq, __ATOMIC_SEQ_CST);
        int idx = -1;
        shx_lock();
        if (all) {
            int ok = 1;
            for (DWORD i = 0; i < n; i++) {
                int s = obj_signaled(objs[i], tid);
                if (s < 0) { shx_unlock(); shx_set_last_error(ERROR_INVALID_HANDLE); return WAIT_FAILED; }
                if (!s) ok = 0;
            }
            if (ok) {
                for (DWORD i = 0; i < n; i++) obj_acquire(objs[i], tid);
                idx = 0;
            }
        } else {
            for (DWORD i = 0; i < n; i++) {
                int s = obj_signaled(objs[i], tid);
                if (s < 0) { shx_unlock(); shx_set_last_error(ERROR_INVALID_HANDLE); return WAIT_FAILED; }
                if (s) { obj_acquire(objs[i], tid); idx = (int)i; break; }
            }
        }
        shx_unlock();
        if (idx >= 0) { shx_set_last_error(ERROR_SUCCESS); return WAIT_OBJECT_0 + (DWORD)idx; }
        double remain = deadline - shx_now_ms();
        if (ms == 0 || remain <= 0.0) return WAIT_TIMEOUT;
#if !defined(__EMSCRIPTEN_PTHREADS__)
        if (ms == INFINITE) shim_unimplemented("WaitFor*Object(INFINITE) would deadlock (single-thread build)");
#endif
        shx_futex_wait(&g_shx_sig_seq, seq, remain);
    }
}

static DWORD wait_handles(DWORD n, const HANDLE* hs, BOOL all, DWORD ms) {
    shx_ensure_init();
    if (n == 0 || n > MAXIMUM_WAIT_OBJECTS || !hs) { shx_set_last_error(ERROR_INVALID_PARAMETER); return WAIT_FAILED; }
    ShxObj* objs[MAXIMUM_WAIT_OBJECTS];
    DWORD got = 0;
    for (; got < n; got++) {
        objs[got] = shx_ref(hs[got], 0);
        if (!objs[got]) break;
    }
    DWORD rc;
    if (got < n) { shx_set_last_error(ERROR_INVALID_HANDLE); rc = WAIT_FAILED; }
    else rc = shx_wait_objs(n, objs, all, ms);
    for (DWORD i = 0; i < got; i++) shx_unref(objs[i]);
    return rc;
}

DWORD WaitForSingleObject(HANDLE h, DWORD ms) { return wait_handles(1, &h, FALSE, ms); }
DWORD WaitForSingleObjectEx(HANDLE h, DWORD ms, BOOL alertable) { (void)alertable; return wait_handles(1, &h, FALSE, ms); }
DWORD WaitForMultipleObjects(DWORD n, const HANDLE* hs, BOOL all, DWORD ms) { return wait_handles(n, hs, all, ms); }
DWORD WaitForMultipleObjectsEx(DWORD n, const HANDLE* hs, BOOL all, DWORD ms, BOOL alertable) {
    (void)alertable; return wait_handles(n, hs, all, ms);
}

/* user32 由来だが同期の一種: メッセージキューは無いので kernel object 待ちだけ。weak (gui 担当が上書き可) */
SHIMX_WEAK DWORD MsgWaitForMultipleObjects(DWORD n, const HANDLE* hs, BOOL all, DWORD ms, DWORD mask) {
    (void)mask;
    if (n == 0) {
        if (ms == INFINITE) shim_unimplemented("MsgWaitForMultipleObjects(0 handles, INFINITE)");
        Sleep(ms);
        return WAIT_TIMEOUT;
    }
    return wait_handles(n, hs, all, ms);
}
SHIMX_WEAK DWORD MsgWaitForMultipleObjectsEx(DWORD n, const HANDLE* hs, DWORD ms, DWORD mask, DWORD flags) {
    return MsgWaitForMultipleObjects(n, hs, (flags & 1u) /* MWMO_WAITALL */ ? TRUE : FALSE, ms, mask);
}

/* ---------------------------------------------------------------
 * 名前付き作成/オープンの共通処理
 * --------------------------------------------------------------- */
static HANDLE named_create(int type, ShxObj* fresh, char* name) {
    if (!fresh) { free(name); shx_set_last_error(ERROR_NOT_ENOUGH_MEMORY); return 0; }
    ShxObj* existing = NULL;
    if (name) {
        shx_lock();
        existing = shx_named_find(name);
        if (existing && existing->type == type) {
            __atomic_add_fetch(&existing->refs, 1, __ATOMIC_SEQ_CST);
        } else if (existing) {
            shx_unlock();
            free(name);
            shx_unref(fresh);
            shx_set_last_error(ERROR_INVALID_HANDLE);
            return 0;
        } else {
            shx_named_add(fresh, name);
        }
        shx_unlock();
        free(name);
    }
    if (existing) {
        shx_unref(fresh);
        HANDLE h = shx_handle_new(existing);
        if (h) shx_set_last_error(ERROR_ALREADY_EXISTS);
        return h;
    }
    HANDLE h = shx_handle_new(fresh);
    if (h) shx_set_last_error(ERROR_SUCCESS);
    return h;
}

static HANDLE named_open(int type, char* name) {
    if (!name) { shx_set_last_error(ERROR_INVALID_PARAMETER); return 0; }
    shx_lock();
    ShxObj* o = shx_named_find(name);
    if (o && o->type == type) __atomic_add_fetch(&o->refs, 1, __ATOMIC_SEQ_CST);
    else o = NULL;
    shx_unlock();
    free(name);
    if (!o) { shx_set_last_error(ERROR_FILE_NOT_FOUND); return 0; }
    HANDLE h = shx_handle_new(o);
    if (h) shx_set_last_error(ERROR_SUCCESS);
    return h;
}

/* 他モジュール (mapping) からも使う */
HANDLE shx_named_create(int type, ShxObj* fresh, char* name) { return named_create(type, fresh, name); }
HANDLE shx_named_open(int type, char* name) { return named_open(type, name); }

/* ---------------------------------------------------------------
 * Event
 * --------------------------------------------------------------- */
static HANDLE create_event(BOOL manual, BOOL initial, char* name) {
    shx_ensure_init();
    ShxObj* o = shx_obj_new(OBJ_EVENT);
    if (o) { o->manual = manual ? 1 : 0; o->state = initial ? 1 : 0; }
    return named_create(OBJ_EVENT, o, name);
}
HANDLE CreateEventW(LPSECURITY_ATTRIBUTES sa, BOOL manual, BOOL initial, LPCWSTR name) {
    (void)sa; return create_event(manual, initial, shx_wname(name));
}
HANDLE CreateEventA(LPSECURITY_ATTRIBUTES sa, BOOL manual, BOOL initial, const char* name) {
    (void)sa; return create_event(manual, initial, shx_aname(name));
}
HANDLE CreateEventExW(LPSECURITY_ATTRIBUTES sa, LPCWSTR name, DWORD flags, DWORD access) {
    (void)sa; (void)access;
    return create_event((flags & 1u) /* CREATE_EVENT_MANUAL_RESET */, (flags & 2u) /* INITIAL_SET */, shx_wname(name));
}
HANDLE OpenEventW(DWORD access, BOOL inherit, LPCWSTR name) { (void)access; (void)inherit; return named_open(OBJ_EVENT, shx_wname(name)); }
HANDLE OpenEventA(DWORD access, BOOL inherit, const char* name) { (void)access; (void)inherit; return named_open(OBJ_EVENT, shx_aname(name)); }

BOOL SetEvent(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_EVENT);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    shx_lock(); o->state = 1; shx_unlock();
    shx_notify();
    shx_unref(o);
    shx_set_last_error(ERROR_SUCCESS);
    return TRUE;
}
BOOL ResetEvent(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_EVENT);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    shx_lock(); o->state = 0; shx_unlock();
    shx_unref(o);
    shx_set_last_error(ERROR_SUCCESS);
    return TRUE;
}
BOOL PulseEvent(HANDLE h) {
    /* 近似: 立てて即クリア (待機者が拾えるのは notify 直後に評価できた場合のみ) */
    if (!SetEvent(h)) return FALSE;
    Sleep(0);
    return ResetEvent(h);
}

/* ---------------------------------------------------------------
 * Mutex
 * --------------------------------------------------------------- */
static HANDLE create_mutex(BOOL initialOwner, char* name) {
    shx_ensure_init();
    ShxObj* o = shx_obj_new(OBJ_MUTEX);
    if (o && initialOwner) { o->owner = shx_tid(); o->rec = 1; }
    return named_create(OBJ_MUTEX, o, name);
}
HANDLE CreateMutexW(LPSECURITY_ATTRIBUTES sa, BOOL own, LPCWSTR name) { (void)sa; return create_mutex(own, shx_wname(name)); }
HANDLE CreateMutexA(LPSECURITY_ATTRIBUTES sa, BOOL own, LPCSTR name) { (void)sa; return create_mutex(own, shx_aname(name)); }
HANDLE OpenMutexW(DWORD access, BOOL inherit, LPCWSTR name) { (void)access; (void)inherit; return named_open(OBJ_MUTEX, shx_wname(name)); }

BOOL ReleaseMutex(HANDLE h) {
    ShxObj* o = shx_ref(h, OBJ_MUTEX);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    DWORD tid = shx_tid();
    BOOL ok = TRUE;
    shx_lock();
    if (o->owner != tid || o->rec == 0) ok = FALSE;
    else if (--o->rec == 0) o->owner = 0;
    shx_unlock();
    if (ok) shx_notify();
    shx_unref(o);
    shx_set_last_error(ok ? ERROR_SUCCESS : ERROR_NOT_OWNER);
    return ok;
}

/* ---------------------------------------------------------------
 * Semaphore
 * --------------------------------------------------------------- */
static HANDLE create_sem(LONG initial, LONG maximum, char* name) {
    shx_ensure_init();
    if (maximum <= 0 || initial < 0 || initial > maximum) { free(name); shx_set_last_error(ERROR_INVALID_PARAMETER); return 0; }
    ShxObj* o = shx_obj_new(OBJ_SEM);
    if (o) { o->count = initial; o->max = maximum; }
    return named_create(OBJ_SEM, o, name);
}
HANDLE CreateSemaphoreW(LPSECURITY_ATTRIBUTES sa, LONG i, LONG m, LPCWSTR name) { (void)sa; return create_sem(i, m, shx_wname(name)); }
HANDLE CreateSemaphoreA(LPSECURITY_ATTRIBUTES sa, LONG i, LONG m, LPCSTR name) { (void)sa; return create_sem(i, m, shx_aname(name)); }
HANDLE OpenSemaphoreW(DWORD access, BOOL inherit, LPCWSTR name) { (void)access; (void)inherit; return named_open(OBJ_SEM, shx_wname(name)); }

BOOL ReleaseSemaphore(HANDLE h, LONG release, PLONG prev) {
    ShxObj* o = shx_ref(h, OBJ_SEM);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    BOOL ok = TRUE;
    shx_lock();
    if (release <= 0 || o->count + release > o->max) ok = FALSE;
    else { if (prev) *prev = o->count; o->count += release; }
    shx_unlock();
    if (ok) shx_notify();
    shx_unref(o);
    shx_set_last_error(ok ? ERROR_SUCCESS : ERROR_TOO_MANY_POSTS);
    return ok;
}

/* ---------------------------------------------------------------
 * SignalObjectAndWait
 * --------------------------------------------------------------- */
DWORD SignalObjectAndWait(HANDLE sig, HANDLE wait, DWORD ms, BOOL alertable) {
    ShxObj* o = shx_ref(sig, 0);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return WAIT_FAILED; }
    int t = o->type;
    shx_unref(o);
    BOOL ok;
    switch (t) {
        case OBJ_EVENT: ok = SetEvent(sig); break;
        case OBJ_MUTEX: ok = ReleaseMutex(sig); break;
        case OBJ_SEM:   ok = ReleaseSemaphore(sig, 1, NULL); break;
        default: shx_set_last_error(ERROR_INVALID_HANDLE); return WAIT_FAILED;
    }
    if (!ok) return WAIT_FAILED;
    return WaitForSingleObjectEx(wait, ms, alertable);
}
