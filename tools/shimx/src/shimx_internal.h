/* shimx 内部共通: 統一ハンドル表 / オブジェクトモデル / ロック / 待機。
 * 外部 (lifter 生成コード) からは使わない。
 */
#ifndef SHIMX_INTERNAL_H
#define SHIMX_INTERNAL_H

#include "shimx.h"
#include <math.h>
#include <errno.h>

#define SHX_MAX_HANDLES 16384

enum {
    OBJ_NONE = 0, OBJ_FILE, OBJ_EVENT, OBJ_THREAD, OBJ_MUTEX, OBJ_SEM,
    OBJ_PROCESS, OBJ_MAPPING, OBJ_FIND, OBJ_KEY, OBJ_TOKEN, OBJ_TIMERQ
};

typedef struct ShxObj {
    int type;
    volatile int32_t refs;
    char* name;                  /* named object key (UTF-8, 小文字化しない) */
    struct ShxObj* nnext;
    volatile uint32_t state;     /* event: signaled / thread,process: done */
    int manual;                  /* event */
    /* file */
    int fd; char* path; DWORD access; int is_std; int is_dir;
    /* thread */
#if defined(__EMSCRIPTEN_PTHREADS__)
    pthread_t pt;
#endif
    int joined; int started; DWORD tid; DWORD exit_code;
    LPTHREAD_START_ROUTINE fn; void* param;
    volatile int suspend_count; volatile uint32_t gate; int prio; ULONG_PTR affinity;
    /* mutex */
    DWORD owner; DWORD rec; int abandoned;
    /* semaphore */
    LONG count, max;
    /* mapping / key / find */
    void* map_base; size_t map_size; int map_fd; DWORD map_prot; int map_anon;
    void* node;
    char* find_pat; char** find_list; int find_n, find_i;
} ShxObj;

/* ---- 軽量 futex mutex (CRITICAL_SECTION でも使用) ---- */
typedef struct { volatile uint32_t v; } shx_mutex_t;
void shx_mutex_lock(shx_mutex_t* m);
int  shx_mutex_trylock(shx_mutex_t* m);
void shx_mutex_unlock(shx_mutex_t* m);
void shx_futex_wait(volatile uint32_t* addr, uint32_t expected, double ms); /* ms=INFINITY 可 */
void shx_futex_wake(volatile uint32_t* addr, int n);
double shx_now_ms(void);

/* ---- グローバルロック (ハンドル表/名前表/待機状態) ---- */
void shx_lock(void);
void shx_unlock(void);
void shx_notify(void);                 /* 待機中スレッドを起こす (どれかの kernel object 状態変化後に呼ぶ) */

/* ---- ハンドル表 ---- */
ShxObj* shx_obj_new(int type);          /* refs=1, ハンドル未割当 */
HANDLE  shx_handle_new(ShxObj* o);      /* o の参照をハンドルへ移譲。失敗時 0 (o は破棄済み) */
HANDLE  shx_handle_dup(ShxObj* o);      /* 追加参照を取ってハンドル割当。失敗時 0 */
ShxObj* shx_ref(HANDLE h, int type);    /* type=0 で型不問。成功時 refs++ (要 shx_unref) */
void    shx_unref(ShxObj* o);
ShxObj* shx_named_find(const char* name);   /* shx_lock 保持中に呼ぶ */
void    shx_named_add(ShxObj* o, const char* name); /* shx_lock 保持中に呼ぶ */
char*   shx_wname(LPCWSTR w);           /* wide → malloc UTF-8 (NULL/空は NULL) */
char*   shx_aname(LPCSTR a);

/* 型別デストラクタ (各 .c が提供) */
void shx_file_destroy(ShxObj* o);
void shx_map_destroy(ShxObj* o);
void shx_find_destroy(ShxObj* o);
void shx_key_destroy(ShxObj* o);
void shx_thread_destroy(ShxObj* o);

/* スレッド / TEB */
DWORD   shx_tid(void);
ShxObj* shx_self_thread_obj(void);       /* 呼び出しスレッドの OBJ_THREAD (無ければ lazily 作成、refs++) */
void    shx_thread_exit_cleanup(void);   /* FLS callback 等 */
void*   shx_teb(void);
void    shx_set_self(ShxObj* o);
void    shx_clear_self(void);
DWORD   shx_alloc_tid(void);
void    shx_set_last_error(DWORD e);

/* wait 内部 (他 .c から) */
DWORD shx_wait_objs(DWORD n, ShxObj** objs, BOOL all, DWORD ms);

/* パス / 文字列ユーティリティ (file.c / str.c) */
int  shx_wpath_to_posix(LPCWSTR w, char* out, size_t outSize);   /* 0=OK, -1=エラー(LastError設定済) */
int  shx_apath_to_posix(LPCSTR a, char* out, size_t outSize);
int  shx_posix_to_wpath_out(const char* posix, LPWSTR out, size_t cch); /* 現状 identity (将来 drive 復元) */
int  shx_acp(void);
int  shx_wstr_len(const WCHAR* w);
int  shx_wcsicmp(const WCHAR* a, const WCHAR* b);
int  shx_wcsnicmp(const WCHAR* a, const WCHAR* b, size_t n);
WCHAR* shx_wcsdup_utf8(const char* s);
int  shx_wcopy_out(const WCHAR* src, int srcLen, LPWSTR dst, DWORD dstCch); /* Win32 流儀: 戻り=必要長(NUL含まず)等 */

/* 遅延初期化 */
void shx_ensure_init(void);

/* R1: 値 < g_shx_intptr_limit は序数/整数 (MAKEINTRESOURCE / ordinal GetProcAddress / 単一文字 Char*)。
 * lowbase (LB_BASE≥0x10000) では既定値のままで guest ポインタが全て ≥ lim に敷設される。
 * LVA=0 敷設 (M11 旧式) の場合は shimx_set_intptr_limit() で下げる */
extern uint32_t g_shx_intptr_limit;
static inline int shx_is_iptr(uintptr_t v) { return v < g_shx_intptr_limit; }

/* R2: lifted コードが渡す関数ポインタ (VA/LVA 整数) → 呼出可能な関数ポインタへの変換フック。
 * fn 未設定 (既定) は恒等変換。hostbridge が m11_icall トランポリンを返す想定 (shimx T2) */
void* shx_translate_cb(const char* api, void* cb);

/* モジュール表内部 (module.c): HMODULE → モジュール名 (小文字, .dll 付き。無ければ NULL) */
const char* shx_mod_name(HMODULE h);

/* strict モード参照 (module.c) */
int shx_strict_mode(void);

/* R7: CRITICAL_SECTION の NULL/非整列を no-op で通す (既定 0 = fail-fast) */
extern int g_shx_cs_null_ok;

/* 統計 */
extern int g_shx_trace;
#define SHX_TRACE(...) do { if (g_shx_trace) { fprintf(stderr, "[shimx] " __VA_ARGS__); fputc('\n', stderr); } } while (0)

#endif /* SHIMX_INTERNAL_H */
