/* pump_ctrl.c — C→host の要求リングと host→C の応答メールボックス。
 *
 * 「C 側はリングに要求を書き、ホスト (JS) が排水して戻す」経路の実装。
 * ホストが同期的に提供すべきサービス (実時刻 / 将来の VFS・入力状態など) を
 * 要求スロットに積み、応答を 1 深度のメールボックスで戻す。
 *
 * - 要求リング: Vyukov 型 MPSC (C が push、ホスト JS が排水)。レイアウトは pump ring と同型。
 * - 応答: 同一時刻に 1 件のみ in-flight (req_id 照合)。単一 UI スレッド前提の単純化。
 * - C 側の応答待ち戦略: pump_wait_mode に従う (ATOMIC= futex / SPIN= ビジー / SLICE= スライス寝 /
 *   HOSTED・NONE= ブロックせず -1 を返し、後続の pump_step / take 時に pctrl_service_done が完了させる)。
 * - タイムアウト: pump_set_ctrl_timeout_ms (既定 1000ms)。超過時は in-flight を破棄し -1。
 */
#include "pump_internal.h"

#define PCTRL_CAP 16u

/* 要求ブロックはヘッダ+スロットを**連続**配置 (ホスト JS が reqAddr+16語 をスロット先頭として排水する) */
typedef struct PctrlBlock {
    int32_t hdr[16] __attribute__((aligned(64)));              /* [0]=enq [1]=deq [2]=wake [3]=cap */
    int32_t slot[PCTRL_CAP][PCTRL_REQ_I32] __attribute__((aligned(64)));
} PctrlBlock;
static PctrlBlock g_pctrl;
#define g_pctrl_hdr g_pctrl.hdr
#define g_req_slot  g_pctrl.slot
int32_t g_pctrl_resp[PCTRL_RESP_I32] __attribute__((aligned(64)));  /* [0]=seq [1]=req_id [2..3]=ret(f64) [6..7]=t_resp(f64) */

static uint32_t g_req_next;        /* 最後に発行した req_id */
int      g_ctrl_done_flag;         /* 直近要求の応答完了 (内部.h で共有) */
double   g_ctrl_pending_treq;      /* in-flight 要求の発行時刻 (C clock) */
int      g_calibrating;            /* 時刻較正要求 in-flight */
static uint32_t g_inflight;        /* 応答待ち req_id (0=無し) */
static uint32_t g_resp_seen;       /* 最後に読んだ応答 seq */
static double g_ctrl_ret;   /* 応答 f64 (resp ワード 2..3) */
static double g_ctrl_t_done;
static double g_ctrl_timeout_ms = 1000.0;
static int32_t g_clock_offset_set;
static double g_clock_offset;      /* host epoch ms - C clock ms (pump_calibrate が推定) */

/* RTT ログ (µs): 応答完了順に積む。host/run_e2e.mjs が統計を取る */
#define PCTRL_LOG_N 512
static double g_ctrl_log[PCTRL_LOG_N];
static uint32_t g_ctrl_log_n;

__attribute__((constructor)) static void pctrl_ctor(void) {
    if (__atomic_load_n(&g_pctrl_hdr[3], __ATOMIC_RELAXED) == (int32_t)PCTRL_CAP) return;
    for (uint32_t i = 0; i < PCTRL_CAP; i++)
        __atomic_store_n(&g_req_slot[i][0], (int32_t)i, __ATOMIC_RELAXED);
    __atomic_store_n(&g_pctrl_hdr[3], (int32_t)PCTRL_CAP, __ATOMIC_RELEASE);
    __atomic_store_n(&g_pctrl_resp[0], 0, __ATOMIC_RELEASE);
}

int32_t pctrl_req_seq(void) { return (int32_t)(uintptr_t)&g_pctrl; }   /* ブロック先頭 (ヘッダ+スロット連続) */
int32_t pctrl_resp_seq(void) { return (int32_t)(uintptr_t)g_pctrl_resp; }

/* ---- 要求 push (C → host)。ホスト JS 側は同一 Vyukov プロトコルで排水する ---- */
static int pctrl_push(uint32_t op, uint32_t a0, uint32_t a1, double t_req) {
    const int32_t cap = (int32_t)PCTRL_CAP;
    for (;;) {
        int32_t pos = __atomic_load_n(&g_pctrl_hdr[0], __ATOMIC_ACQUIRE);
        int32_t* s = g_req_slot[pos & (cap - 1)];
        int32_t seq = __atomic_load_n(&s[0], __ATOMIC_ACQUIRE);
        int32_t dif = (int32_t)(seq - pos);
        if (dif == 0) {
            if (__atomic_compare_exchange_n(&g_pctrl_hdr[0], &pos, pos + 1, 0,
                                            __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE) != 1)
                continue;
            s[1] = (int32_t)op; s[2] = (int32_t)a0; s[3] = (int32_t)a1;
            s[4] = (int32_t)g_inflight; s[5] = 0;
            *(double*)(void*)&s[6] = t_req;
            __atomic_store_n(&s[0], pos + 1, __ATOMIC_RELEASE);
            __atomic_add_fetch(&g_pctrl_hdr[2], 1, __ATOMIC_ACQ_REL);
#ifdef __EMSCRIPTEN_PTHREADS__
            __builtin_wasm_memory_atomic_notify(&g_pctrl_hdr[2], 1);
#endif
            return 1;
        }
        if (dif < 0) return 0;   /* 満杯: fail-soft */
    }
}

/* ---- 応答の非ブロック吸い出し (take / pump_step の頭で呼ぶ) ---- */
void pctrl_service_done(void) {
    int32_t seq = __atomic_load_n(&g_pctrl_resp[0], __ATOMIC_ACQUIRE);
    if (seq == (int32_t)g_resp_seen) return;
    int32_t rid = __atomic_load_n(&g_pctrl_resp[1], __ATOMIC_ACQUIRE);
    g_ctrl_ret = *(const double*)(const void*)&g_pctrl_resp[2];
    double t_resp = *(const double*)(const void*)&g_pctrl_resp[6];
    g_resp_seen = (uint32_t)seq;
    if (g_inflight && rid == (int32_t)g_inflight) {
        /* RTT 記録: t_req は要求スロット経由でなく完了側で持つ (簡単化: 要求時刻は呼び出し側が知る) */
        g_ctrl_t_done = t_resp;
        if (g_ctrl_pending_treq > 0) {
            double rtt_us = (pnow() - g_ctrl_pending_treq) * 1000.0;
            if (g_ctrl_log_n < PCTRL_LOG_N) g_ctrl_log[g_ctrl_log_n++] = rtt_us;
        }
        if (g_calibrating && !g_clock_offset_set) {
            double host_t = g_ctrl_ret;
            double c_mid = (g_ctrl_pending_treq + pnow()) * 0.5;
            g_clock_offset = host_t - c_mid;
            g_clock_offset_set = 1;
        }
        g_ctrl_pending_treq = 0;
        g_ctrl_done_flag = 1;
        g_calibrating = 0;
        g_inflight = 0;
        __atomic_add_fetch(&g_pstat.ctrl_ok, 1u, __ATOMIC_RELAXED);
    }
}

/* ---- 応答待ち本体 ---- */
static int pctrl_wait_result(double deadline, int allow_block) {
    for (;;) {
        pctrl_service_done();
        if (g_ctrl_done_flag) return 0;
        double now = pnow();
        if (now >= deadline) {   /* タイムアウト: in-flight を破棄 (後から来た応答は req_id 不一致で捨てられる) */
            g_ctrl_pending_treq = 0;
            g_calibrating = 0;
            g_inflight = 0;
            __atomic_add_fetch(&g_pstat.ctrl_timeout, 1u, __ATOMIC_RELAXED);
            return -1;
        }
        if (!allow_block) return -1;   /* HOSTED/NONE: 後続の service_done で完了する (pending) */
        int32_t expect = __atomic_load_n(&g_pctrl_resp[0], __ATOMIC_ACQUIRE);
        double remain_ms = deadline - now;
        switch (g_wait_mode) {
            case PUMP_WAIT_SPIN:
                __atomic_add_fetch(&g_pstat.waits_spin, 1u, __ATOMIC_RELAXED);
                break;
            case PUMP_WAIT_SLICE: {
                __atomic_add_fetch(&g_pstat.waits_slice, 1u, __ATOMIC_RELAXED);
                double s = g_slice_ms < remain_ms ? g_slice_ms : remain_ms;
#ifdef __EMSCRIPTEN_PTHREADS__
                __builtin_wasm_memory_atomic_wait32(&g_pctrl_resp[0], expect, (int64_t)(s * 1e6));
#endif
                break;
            }
            default: {   /* PUMP_WAIT_ATOMIC */
                __atomic_add_fetch(&g_pstat.waits_atomic, 1u, __ATOMIC_RELAXED);
#ifdef __EMSCRIPTEN_PTHREADS__
                __builtin_wasm_memory_atomic_wait32(&g_pctrl_resp[0], expect, (int64_t)(remain_ms * 1e6));
#endif
                break;
            }
        }
    }
}

int pump_ctrl_request(uint32_t op, uint32_t a0, uint32_t a1, double* ret0, double* ret1) {
    if (g_inflight) return -2;   /* 多重 in-flight は不許可 (単一 UI スレッド前提) */
    __atomic_add_fetch(&g_pstat.ctrl_req, 1u, __ATOMIC_RELAXED);
    uint32_t rid = ++g_req_next;
    g_inflight = rid;
    g_ctrl_done_flag = 0;
    g_ctrl_pending_treq = pnow();
    if (!pctrl_push(op, a0, a1, g_ctrl_pending_treq)) {
        g_inflight = 0;
        return -3;   /* リング満杯 */
    }
    int allow_block = (pump_eff_wait_mode() == PUMP_WAIT_ATOMIC || pump_eff_wait_mode() == PUMP_WAIT_SLICE ||
                       pump_eff_wait_mode() == PUMP_WAIT_SPIN);
    double deadline = g_ctrl_pending_treq + g_ctrl_timeout_ms;
    int rc = pctrl_wait_result(deadline, allow_block);
    if (rc == 0) {
        if (ret0) *ret0 = g_ctrl_ret;
        if (ret1) *ret1 = 0.0;
    }
    return rc;   /* 0=完了 / -1=未完了・タイムアウト / -2=busy / -3=満杯 */
}

/* ---- 時刻オフセット較正: host epoch ms との差を 1 回推定 (node では ≈0) ---- */
void pump_calibrate(void) {
    if (g_clock_offset_set || g_calibrating || g_inflight) return;
    g_calibrating = 1;
    int allow_block = (pump_eff_wait_mode() == PUMP_WAIT_ATOMIC || pump_eff_wait_mode() == PUMP_WAIT_SLICE ||
                       pump_eff_wait_mode() == PUMP_WAIT_SPIN);
    uint32_t rid = ++g_req_next;
    g_inflight = rid;
    g_ctrl_done_flag = 0;
    g_ctrl_pending_treq = pnow();
    if (!pctrl_push(PCTRL_OP_EPOCH_NOW, 0, 0, g_ctrl_pending_treq)) { g_inflight = 0; g_calibrating = 0; }
    else if (allow_block) pctrl_wait_result(g_ctrl_pending_treq + g_ctrl_timeout_ms, 1);
    /* HOSTED/NONE: 後続の service_done で完了 */
}

double pump_clock_offset(void) { return g_clock_offset; }
void pump_force_clock_offset(double o) { g_clock_offset = o; g_clock_offset_set = 1; }
int    pump_clock_calibrated(void) { return g_clock_offset_set; }

/* 完了済み応答の取り出し (HOSTED/NONE の非同期完了をテスト・ホストが確認する用) */
int pump_ctrl_take_done(double* ret0) {
    pctrl_service_done();
    if (!g_ctrl_done_flag) return 0;
    g_ctrl_done_flag = 0;
    if (ret0) *ret0 = g_ctrl_ret;
    return 1;
}
__attribute__((export_name("pump_ctrl_rtt"))) double pump_ctrl_rtt(int i) {
    return (uint32_t)i < g_ctrl_log_n ? g_ctrl_log[i] : -1.0;
}
__attribute__((export_name("pump_ctrl_rtt_count"))) uint32_t pump_ctrl_rtt_count(void) { return g_ctrl_log_n; }
void   pump_set_ctrl_timeout_ms(double ms) { if (ms > 0) g_ctrl_timeout_ms = ms; }
