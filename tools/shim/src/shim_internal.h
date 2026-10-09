/* shim 内部共通 (file.c が所有する HANDLE テーブルを sync.c と共有する)。
 * 外部 (lifter 生成コード) からは使わない。
 */
#ifndef SHIM_INTERNAL_H
#define SHIM_INTERNAL_H

#include "shim.h"

#define SHIM_MAX_HANDLES 256

enum {
    SHIM_TYPE_NONE   = 0,
    SHIM_TYPE_FILE   = 1,
    SHIM_TYPE_EVENT  = 2,
    SHIM_TYPE_THREAD = 3
};

typedef struct ShimSlot {
    int used;
    int type;
    /* file */
    int fd;
    /* thread / event */
#if defined(__EMSCRIPTEN_PTHREADS__)
    pthread_t pt;
#endif
    int joined;
    volatile uint32_t done;  /* thread 終了フラグ */
    volatile uint32_t state; /* event 状態 */
    int manual_reset;
    DWORD exit_code;
    LPTHREAD_START_ROUTINE fn;
    LPVOID param;
} ShimSlot;

extern ShimSlot g_slots[SHIM_MAX_HANDLES];

ShimSlot* shim_alloc_slot(int type);      /* 失敗時 NULL */
void      shim_free_slot(ShimSlot* s);
ShimSlot* shim_slot_lookup(HANDLE h);     /* 失敗時 NULL */
HANDLE    shim_handle_from_slot(ShimSlot* s);

#endif /* SHIM_INTERNAL_H */
