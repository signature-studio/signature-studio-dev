/* pump_ring.c — Vyukov bounded MPSC ring の C 実装 (消費 + 投稿の両面)。
 *
 * レイアウト・プロトコルは src/runtime/worker_pump.ts の PumpRing と同一:
 *   push: enq を CAS で予約 → スロットに書き込み → seq publish (pos+1) → wake++ + notify
 *   pop : deq のスロット seq が pos+1 なら実取り出し → seq = pos+capacity → deq++
 * 満杯は false + dropped++ (worker_pump.ts push の失敗と同一挙動)。
 * producers: JS (worker_pump.ts PumpRing.push, 任意個) + C (PostMessageW, 任意スレッド)。
 * consumer : 単一 (wasm UI スレッド = 本 TU)。
 */
#include "pump_internal.h"

PrRing g_pring __attribute__((aligned(64)));

/* 呼び出し順序に注意: pring_init は他のどのコードより先 (静的初期化はゼロで良い)。
 * emcc の constructor は __wasm_call_ctors で実行される → ホストが PumpRing を構築する前に完了。 */
__attribute__((constructor)) static void pring_ctor(void) { pring_init(); }

void pring_init(void) {
    int32_t* h = g_pring.hdr;
    if (__atomic_load_n(&h[PR_H_MAGIC], __ATOMIC_ACQUIRE) == PR_MAGIC) return;  /* 多重初期化ガード */
    for (uint32_t i = 0; i < PR_CAP_DEFAULT; i++)
        __atomic_store_n(&g_pring.slot[i][PR_S_SEQ], (int32_t)i, __ATOMIC_RELAXED);
    __atomic_store_n(&h[PR_H_CAPACITY], (int32_t)PR_CAP_DEFAULT, __ATOMIC_RELEASE);
    __atomic_store_n(&h[PR_H_MAGIC], (int32_t)PR_MAGIC, __ATOMIC_RELEASE);
}

static inline int32_t* hword(int idx) { return &g_pring.hdr[idx]; }

int pring_pop(uint32_t out[11], double* t_post) {
    int32_t* h = g_pring.hdr;
    const int32_t cap = __atomic_load_n(&h[PR_H_CAPACITY], __ATOMIC_ACQUIRE);
    int32_t pos = __atomic_load_n(&h[PR_H_DEQ], __ATOMIC_ACQUIRE);
    int32_t* s = g_pring.slot[pos & (cap - 1)];
    if (__atomic_load_n(&s[PR_S_SEQ], __ATOMIC_ACQUIRE) - (pos + 1) != 0) return 0;
    for (int i = 0; i < 11; i++) out[i] = (uint32_t)s[i];
    *t_post = *(const double*)(const void*)&s[PR_S_TPOST_I32];
    __atomic_store_n(&s[PR_S_SEQ], pos + cap, __ATOMIC_RELEASE);
    __atomic_store_n(&h[PR_H_DEQ], pos + 1, __ATOMIC_RELEASE);
    return 1;
}

int pring_push(void* hwnd, uint32_t msg, uint64_t wp, uint64_t lp, double t_post) {
    int32_t* h = g_pring.hdr;
    const int32_t cap = __atomic_load_n(&h[PR_H_CAPACITY], __ATOMIC_ACQUIRE);
    const int32_t mask = cap - 1;
    for (;;) {
        int32_t pos = __atomic_load_n(&h[PR_H_ENQ], __ATOMIC_ACQUIRE);
        int32_t* s = g_pring.slot[pos & mask];
        int32_t seq = __atomic_load_n(&s[PR_S_SEQ], __ATOMIC_ACQUIRE);
        int32_t dif = (int32_t)(seq - pos);
        if (dif == 0) {
            if (__atomic_compare_exchange_n(&h[PR_H_ENQ], &pos, pos + 1, 0,
                                            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE) != 1)
                continue;   /* 他 producer が先行 → 再読込 */
            s[PR_S_MSG] = (int32_t)msg;
            s[PR_S_HWND_LO] = (int32_t)(uint32_t)(uintptr_t)hwnd;
            s[PR_S_HWND_HI] = 0;                        /* wasm32: hwnd は 32bit */
            s[PR_S_W_LO] = (int32_t)(uint32_t)wp;
            s[PR_S_W_HI] = (int32_t)(uint32_t)(wp >> 32);
            s[PR_S_L_LO] = (int32_t)(uint32_t)lp;
            s[PR_S_L_HI] = (int32_t)(uint32_t)(lp >> 32);
            s[PR_S_TIME] = (int32_t)(uint32_t)pnow();
            s[PR_S_PTX] = 0;
            s[PR_S_PTY] = 0;
            *(double*)(void*)&s[PR_S_TPOST_I32] = t_post;
            __atomic_store_n(&s[PR_S_SEQ], pos + 1, __ATOMIC_RELEASE);   /* publish */
            __atomic_add_fetch(&h[PR_H_WAKE], 1, __ATOMIC_ACQ_REL);
            pring_notify();
            return 1;
        }
        if (dif < 0) {   /* 満杯: Win32 PostMessage 失敗相当 (dropped++ は TS push と同一) */
            __atomic_add_fetch(&h[PR_H_DROPPED], 1, __ATOMIC_RELAXED);
            return 0;
        }
        /* dif > 0: 他 producer が先行 → 再読込 */
    }
}

int32_t pring_wake(void) { return __atomic_load_n(hword(PR_H_WAKE), __ATOMIC_ACQUIRE); }

void pring_notify(void) {
#ifdef __EMSCRIPTEN_PTHREADS__
    /* 共有メモリの futex を 1 本起床 (JS 側 Atomics.notify と同一アドレス → 相互に起床し合う) */
    __builtin_wasm_memory_atomic_notify(hword(PR_H_WAKE), 1);
#else
    /* ST ビルド: 通知相手は同一スレッドのみ → no-op */
#endif
}
