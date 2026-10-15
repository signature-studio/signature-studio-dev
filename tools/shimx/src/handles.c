/* 統一ハンドル表 / オブジェクトモデル / futex mutex / グローバルロック。
 * M4 の ShimSlot (256 固定, file/event/thread) を置換:
 *   - 16384 スロット, HANDLE 値 = (idx+1)*4 (Win32 流儀: 4 の倍数, 非 0)
 *   - 参照カウント: DuplicateHandle / スレッド生存中の内部参照
 *   - 名前付きオブジェクト表 (Event/Mutex/Semaphore/FileMapping 共通名前空間)
 */
#include "shimx_internal.h"

int g_shx_trace = 0;

/* ---------------------------------------------------------------
 * futex ラッパ / 時計
 * --------------------------------------------------------------- */
double shx_now_ms(void) { return emscripten_get_now(); }

void shx_futex_wait(volatile uint32_t* addr, uint32_t expected, double ms) {
    emscripten_futex_wait((volatile void*)addr, expected, ms);
}
void shx_futex_wake(volatile uint32_t* addr, int n) {
    emscripten_futex_wake((volatile void*)addr, n);
}

/* Drepper の 3 状態 mutex (0=free 1=locked 2=contended) */
int shx_mutex_trylock(shx_mutex_t* m) {
    uint32_t z = 0;
    return __atomic_compare_exchange_n(&m->v, &z, 1u, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
}
void shx_mutex_lock(shx_mutex_t* m) {
    uint32_t c = 0;
    if (__atomic_compare_exchange_n(&m->v, &c, 1u, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return;
    if (c != 2) c = __atomic_exchange_n(&m->v, 2u, __ATOMIC_ACQUIRE);
    while (c != 0) {
        shx_futex_wait(&m->v, 2u, INFINITY);
        c = __atomic_exchange_n(&m->v, 2u, __ATOMIC_ACQUIRE);
    }
}
void shx_mutex_unlock(shx_mutex_t* m) {
    if (__atomic_sub_fetch(&m->v, 1u, __ATOMIC_RELEASE) != 0) {
        __atomic_store_n(&m->v, 0u, __ATOMIC_RELEASE);
        shx_futex_wake(&m->v, 1);
    }
}

static shx_mutex_t g_big;
void shx_lock(void)   { shx_mutex_lock(&g_big); }
void shx_unlock(void) { shx_mutex_unlock(&g_big); }

volatile uint32_t g_shx_sig_seq = 0;
static void (*g_notify_hook)(void);
void shimx_set_notify_hook(void (*fn)(void)) { g_notify_hook = fn; }   /* #172: GUI メッセージ待ち (MsgWait*) を kernel object の状態変化で起こす */
static void (*g_file_close_hook)(const char *);
void shimx_set_file_close_hook(void (*fn)(const char *)) { g_file_close_hook = fn; }   /* #958: 書込み用 file handle の CloseHandle で posix path を渡す (save 反映の契機) */
void shx_notify(void) {
    __atomic_add_fetch(&g_shx_sig_seq, 1u, __ATOMIC_SEQ_CST);
    shx_futex_wake(&g_shx_sig_seq, 0x7fffffff);
    void (*h)(void) = g_notify_hook;
    if (h) h();
}

/* ---------------------------------------------------------------
 * 名前
 * --------------------------------------------------------------- */
char* shx_wname(LPCWSTR w) {
    if (!w || !*w) return NULL;
    char tmp[1024];
    int n = shimx_utf16_to_utf8(w, -1, tmp, sizeof(tmp));
    if (n < 0) return NULL;
    const char* p = tmp;
    if (!strncmp(p, "Local\\", 6)) p += 6;
    else if (!strncmp(p, "Global\\", 7)) p += 7;
    return strdup(p);
}
char* shx_aname(LPCSTR a) {
    if (!a || !*a) return NULL;
    const char* p = a;
    if (!strncmp(p, "Local\\", 6)) p += 6;
    else if (!strncmp(p, "Global\\", 7)) p += 7;
    return strdup(p);
}

static ShxObj* g_named_head;
ShxObj* shx_named_find(const char* name) {
    for (ShxObj* o = g_named_head; o; o = o->nnext)
        if (o->name && !strcmp(o->name, name)) return o;
    return NULL;
}
void shx_named_add(ShxObj* o, const char* name) {
    o->name = strdup(name);
    o->nnext = g_named_head;
    g_named_head = o;
}
static void named_remove(ShxObj* o) {
    ShxObj** pp = &g_named_head;
    while (*pp) {
        if (*pp == o) { *pp = o->nnext; return; }
        pp = &(*pp)->nnext;
    }
}

/* ---------------------------------------------------------------
 * ハンドル表
 * --------------------------------------------------------------- */
static ShxObj* g_tab[SHX_MAX_HANDLES];
static uint32_t g_hint = 0;
static int g_open = 0, g_peak = 0;
static ShxObj* g_proc_obj;

ShxObj* shx_obj_new(int type) {
    ShxObj* o = (ShxObj*)calloc(1, sizeof(ShxObj));
    if (!o) return NULL;
    o->type = type;
    o->refs = 1;
    o->fd = -1;
    o->map_fd = -1;
    return o;
}

static void obj_destroy(ShxObj* o) {
    shx_lock();
    if (o->name) named_remove(o);
    shx_unlock();
    switch (o->type) {
        case OBJ_FILE:    shx_file_destroy(o); break;
        case OBJ_MAPPING: shx_map_destroy(o); break;
        case OBJ_FIND:    shx_find_destroy(o); break;
        case OBJ_KEY:     shx_key_destroy(o); break;
        case OBJ_THREAD:  shx_thread_destroy(o); break;
        default: break;
    }
    free(o->name);
    free(o);
}

void shx_unref(ShxObj* o) {
    if (!o) return;
    if (__atomic_sub_fetch(&o->refs, 1, __ATOMIC_ACQ_REL) == 0) obj_destroy(o);
}

HANDLE shx_handle_new(ShxObj* o) {
    shx_lock();
    for (uint32_t k = 0; k < SHX_MAX_HANDLES; k++) {
        uint32_t i = (g_hint + k) % SHX_MAX_HANDLES;
        if (!g_tab[i]) {
            g_tab[i] = o;
            g_hint = i + 1;
            g_open++;
            if (g_open > g_peak) g_peak = g_open;
            shx_unlock();
            return (HANDLE)((i + 1) << 2);
        }
    }
    shx_unlock();
    shx_set_last_error(ERROR_TOO_MANY_OPEN_FILES);
    shx_unref(o);
    return 0;
}

HANDLE shx_handle_dup(ShxObj* o) {
    __atomic_add_fetch(&o->refs, 1, __ATOMIC_SEQ_CST);
    return shx_handle_new(o);
}

static ShxObj* tab_lookup_locked(HANDLE h) {
    if (h == 0 || (h & 3) != 0) return NULL;
    size_t idx = (h >> 2) - 1;
    if (idx >= SHX_MAX_HANDLES) return NULL;
    return g_tab[idx];
}

static ShxObj* proc_obj(void) {
    shx_lock();
    if (!g_proc_obj) {
        g_proc_obj = shx_obj_new(OBJ_PROCESS);
        g_proc_obj->exit_code = STILL_ACTIVE;
    }
    ShxObj* o = g_proc_obj;
    shx_unlock();
    return o;
}

ShxObj* shx_ref(HANDLE h, int type) {
    shx_ensure_init();
    ShxObj* o;
    if (h == (HANDLE)-2) {
        o = shx_self_thread_obj();           /* refs++ 済み */
        if (type && o->type != type) { shx_unref(o); return NULL; }
        return o;
    }
    if (h == (HANDLE)-1) {
        o = proc_obj();
        if (type && o->type != type) return NULL;
        __atomic_add_fetch(&o->refs, 1, __ATOMIC_SEQ_CST);
        return o;
    }
    shx_lock();
    o = tab_lookup_locked(h);
    if (o && (type == 0 || o->type == type)) {
        __atomic_add_fetch(&o->refs, 1, __ATOMIC_SEQ_CST);
    } else {
        o = NULL;
    }
    shx_unlock();
    return o;
}

BOOL CloseHandle(HANDLE h) {
    shx_ensure_init();
    if (h == (HANDLE)-1 || h == (HANDLE)-2) { shx_set_last_error(ERROR_SUCCESS); return TRUE; }
    shx_lock();
    ShxObj* o = tab_lookup_locked(h);
    if (!o) {
        shx_unlock();
        shx_set_last_error(ERROR_INVALID_HANDLE);
        return FALSE;
    }
    g_tab[(h >> 2) - 1] = NULL;
    g_open--;
    shx_unlock();
    if (g_file_close_hook && o->type == OBJ_FILE && o->path && (o->access & (GENERIC_WRITE | GENERIC_ALL))) g_file_close_hook(o->path);
    shx_unref(o);
    shx_set_last_error(ERROR_SUCCESS);
    return TRUE;
}

BOOL DuplicateHandle(HANDLE srcProc, HANDLE src, HANDLE dstProc, LPHANDLE dst,
                     DWORD access, BOOL inherit, DWORD options) {
    (void)access; (void)inherit;
    if ((srcProc != (HANDLE)-1 && srcProc != 0) || (dstProc != (HANDLE)-1 && dstProc != 0 && dst)) {
        /* 他プロセスのハンドルは存在しない (単一プロセス) */
        if (srcProc != (HANDLE)-1 || dstProc != (HANDLE)-1) {
            ShxObj* p = shx_ref(srcProc, OBJ_PROCESS);
            if (!p) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
            shx_unref(p);
        }
    }
    ShxObj* o = shx_ref(src, 0);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    HANDLE nh = 0;
    if (dst) {
        nh = shx_handle_dup(o);   /* 追加参照 + 割当 */
        if (!nh) { shx_unref(o); return FALSE; }
        *dst = nh;
    }
    shx_unref(o);                 /* shx_ref で取った参照を解放 */
    if (options & DUPLICATE_CLOSE_SOURCE) CloseHandle(src);
    shx_set_last_error(ERROR_SUCCESS);
    return TRUE;
}

BOOL GetHandleInformation(HANDLE h, LPDWORD flags) {
    ShxObj* o = shx_ref(h, 0);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    shx_unref(o);
    if (flags) *flags = 0;
    return TRUE;
}
BOOL SetHandleInformation(HANDLE h, DWORD mask, DWORD flags) {
    (void)mask; (void)flags;
    ShxObj* o = shx_ref(h, 0);
    if (!o) { shx_set_last_error(ERROR_INVALID_HANDLE); return FALSE; }
    shx_unref(o);
    return TRUE;
}

void shimx_handle_stats(int* open, int* peak) {
    shx_lock();
    if (open) *open = g_open;
    if (peak) *peak = g_peak;
    shx_unlock();
}

/* ---------------------------------------------------------------
 * 遅延初期化 (1 回のみ。最初に来たスレッドが実施、他は完了まで待つ)
 * --------------------------------------------------------------- */
extern void shx_init_std_handles(void);
extern void shx_init_env(void);
extern void shx_init_reg(void);
extern void shx_init_modules(void);
static volatile uint32_t g_init_state = 0; /* 0=未, 1=実行中, 2=完了 */
static _Thread_local int t_in_init;

void shx_ensure_init(void) {
    if (__atomic_load_n(&g_init_state, __ATOMIC_ACQUIRE) == 2 || t_in_init) return;
    uint32_t z = 0;
    if (__atomic_compare_exchange_n(&g_init_state, &z, 1u, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        t_in_init = 1;
        const char* t = getenv("SHIMX_TRACE");
        g_shx_trace = (t && *t && *t != '0');
        shx_ftrace_open_env();
        shx_init_env();
        shx_init_std_handles();
        shx_init_reg();
        shx_init_modules();
        t_in_init = 0;
        __atomic_store_n(&g_init_state, 2u, __ATOMIC_RELEASE);
        shx_futex_wake(&g_init_state, 0x7fffffff);
    } else {
        while (__atomic_load_n(&g_init_state, __ATOMIC_ACQUIRE) != 2)
            shx_futex_wait(&g_init_state, 1u, 10.0);
    }
}

void shimx_init(void) { shx_ensure_init(); }
void shimx_set_trace(int on) { shx_ensure_init(); g_shx_trace = on; }

/* ---------------------------------------------------------------
 * R1: 「値 < 0x10000 は序数/整数」判定の閾値 ( 既定 0x10000 )
 * R2: 関数ポインタ引数の変換フック (既定 = 恒等)
 * --------------------------------------------------------------- */
uint32_t g_shx_intptr_limit = 0x10000;
static shimx_callback_translator_fn g_cb_trans;

void shimx_set_intptr_limit(uint32_t lim) { g_shx_intptr_limit = lim; }
uint32_t shimx_get_intptr_limit(void) { return g_shx_intptr_limit; }
void shimx_set_callback_translator(shimx_callback_translator_fn fn) { g_cb_trans = fn; }
shimx_callback_translator_fn shimx_get_callback_translator(void) { return g_cb_trans; }
void* shx_translate_cb(const char* api, void* cb) {
    if (!cb || !g_cb_trans) return cb;
    void* r = g_cb_trans(api, cb);
    return r ? r : cb;          /* 翻訳結果 NULL の場合は元の値を維持 (呼出側の NULL 判定を壊さない) */
}
