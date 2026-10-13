/* flmidi.c — FL MIDI shim 転送層 (ctl / SAB ring / mailbox RPC / デバイス表)。設計は docs/PROTOCOL.md §9, flmidi.h */
#include "flmidi.h"
#include <emscripten.h>
#include <emscripten/threading.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LD(x)    __atomic_load_n(&(x), __ATOMIC_SEQ_CST)
#define ST(x, v) __atomic_store_n(&(x), (v), __ATOMIC_SEQ_CST)

static flm_ctl_t g_ctl __attribute__((aligned(64)));
static uint8_t g_in_ring[FLM_IN_RING_BYTES] __attribute__((aligned(64)));
static uint8_t g_out_ring[FLM_OUT_RING_BYTES] __attribute__((aligned(64)));
static flm_dev_t g_devtbl[2][FLM_MAX_DEV] __attribute__((aligned(64)));
static pthread_mutex_t g_rpc_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t g_once = PTHREAD_ONCE_INIT;

_Static_assert(sizeof(flm_ctl_t) == FLM_CTL_SIZE, "flm_ctl_t size");
_Static_assert(sizeof(flm_dev_t) == FLM_DEV_ENTRY, "flm_dev_t size");

void flm_failfast(const char *api, const char *why) {
    fprintf(stderr, "[flmidi] FAIL-FAST: %s: %s\n", api, why);
    fflush(stderr);
    abort();
}

#define OFF(f) { #f, (uint32_t)offsetof(flm_ctl_t, f) }
static const flm_layout_entry_t g_layout[] = {
    OFF(magic), OFF(state), OFF(in_ring_ptr), OFF(in_ring_bytes), OFF(out_ring_ptr), OFF(out_ring_bytes), OFF(dev_tbl_ptr), OFF(max_dev), OFF(ctrl_ready),
    OFF(in_w), OFF(in_dropped), OFF(in_accepted), OFF(main_errors), OFF(out_r), OFF(out_errors), OFF(out_sent),
    OFF(in_r), OFF(out_w), OFF(wake), OFF(out_full), OFF(sx_nobuf), OFF(in_stale), OFF(in_prestart), OFF(cb_events),
    OFF(tbl_seq), OFF(n_in), OFF(n_out), OFF(scan_gen),
    OFF(cmd_seq), OFF(cmd_op), OFF(cmd_arg), OFF(ack_seq), OFF(ack_status), OFF(ack_res),
};
EMSCRIPTEN_KEEPALIVE int flm_layout_count(void) { return (int)(sizeof g_layout / sizeof g_layout[0]); }
EMSCRIPTEN_KEEPALIVE uint32_t flm_layout_off(int i) { return g_layout[i].off; }
EMSCRIPTEN_KEEPALIVE const char *flm_layout_name(int i) { return g_layout[i].name; }
EMSCRIPTEN_KEEPALIVE uintptr_t flm_ctl_ptr(void) { return (uintptr_t)&g_ctl; }
flm_ctl_t *flm_ctl(void) { return &g_ctl; }

EM_JS(double, flm_now_ms, (void), { return performance.timeOrigin + performance.now(); });

static void init_once(void) {
    flm_ctl_t *c = &g_ctl;
    c->abi = FLM_ABI;
    c->in_ring_ptr = (uint32_t)(uintptr_t)g_in_ring;   c->in_ring_bytes = FLM_IN_RING_BYTES;
    c->out_ring_ptr = (uint32_t)(uintptr_t)g_out_ring; c->out_ring_bytes = FLM_OUT_RING_BYTES;
    c->dev_tbl_ptr = (uint32_t)(uintptr_t)g_devtbl;    c->max_dev = FLM_MAX_DEV;
    ST(c->magic, FLM_MAGIC);
    ST(c->state, 1);
}
EMSCRIPTEN_KEEPALIVE void flm_init(void) { pthread_once(&g_once, init_once); }

void flm_bump_wake(void) {
    __atomic_add_fetch(&g_ctl.wake, 1, __ATOMIC_SEQ_CST);
    __builtin_wasm_memory_atomic_notify((int *)&g_ctl.wake, 0x7fffffff);
}
int flm_wait_wake(uint32_t seen, uint32_t timeout_ms) {
    if (LD(g_ctl.wake) != seen) return 0;
    return __builtin_wasm_memory_atomic_wait32((int *)&g_ctl.wake, (int)seen, (int64_t)timeout_ms * 1000000);
}

int flm_rpc(uint32_t op, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t res[4], uint32_t timeout_ms) {
    if (emscripten_is_main_browser_thread()) flm_failfast("flm_rpc", "blocking call on the main browser thread");
    flm_ctl_t *c = &g_ctl;
    if (!LD(c->ctrl_ready)) return FLM_E_DENIED;       /* controller 不在: 待たずに失敗 (FL を固めない) */
    pthread_mutex_lock(&g_rpc_lock);
    c->cmd_op = op; c->cmd_arg[0] = a0; c->cmd_arg[1] = a1; c->cmd_arg[2] = a2; c->cmd_arg[3] = a3;
    uint32_t seq = __atomic_add_fetch(&c->cmd_seq, 1, __ATOMIC_SEQ_CST);
    __builtin_wasm_memory_atomic_notify((int *)&c->cmd_seq, 0x7fffffff);
    double t0 = emscripten_get_now();
    int rc = FLM_E_DENIED;
    for (;;) {
        uint32_t ack = LD(c->ack_seq);
        if (ack == seq) { rc = c->ack_status; break; }
        double left = timeout_ms - (emscripten_get_now() - t0);
        if (left <= 0) break;
        __builtin_wasm_memory_atomic_wait32((int *)&c->ack_seq, (int)ack, (int64_t)(left * 1e6));
    }
    if (rc == 0 && res) memcpy(res, c->ack_res, sizeof c->ack_res);
    pthread_mutex_unlock(&g_rpc_lock);
    return rc;
}

static uint32_t rec_span(uint32_t payload) { return FLM_REC + ((payload + FLM_REC - 1) & ~(FLM_REC - 1)); }

static void ring_get(const uint8_t *ring, uint32_t size, uint32_t pos, void *dst, uint32_t n) {
    uint32_t p = pos & (size - 1), first = size - p < n ? size - p : n;
    memcpy(dst, ring + p, first);
    if (first < n) memcpy((uint8_t *)dst + first, ring, n - first);
}
static void ring_put(uint8_t *ring, uint32_t size, uint32_t pos, const void *src, uint32_t n) {
    uint32_t p = pos & (size - 1), first = size - p < n ? size - p : n;
    memcpy(ring + p, src, first);
    if (first < n) memcpy(ring, (const uint8_t *)src + first, n - first);
}

int flm_in_pop(flm_rec_t *r, uint8_t *payload, uint32_t cap) {
    flm_ctl_t *c = &g_ctl;
    uint32_t rd = c->in_r, wr = LD(c->in_w);
    if (rd == wr) return 0;
    uint8_t hdr[FLM_REC];
    ring_get(g_in_ring, FLM_IN_RING_BYTES, rd, hdr, FLM_REC);
    uint32_t w0, w1; double ts;
    memcpy(&w0, hdr, 4); memcpy(&w1, hdr + 4, 4); memcpy(&ts, hdr + 8, 8);
    r->slot = w0 & 0xff; r->kind = (w0 >> 8) & 0xff; r->gen = w0 >> 16; r->val = w1; r->ts = ts;
    uint32_t plen = r->kind == FLM_K_SYSEX ? w1 : 0;
    if (plen > cap || plen > FLM_MAX_SYSEX) flm_failfast("flm_in_pop", "corrupt record length");
    if (plen) ring_get(g_in_ring, FLM_IN_RING_BYTES, rd + FLM_REC, payload, plen);
    ST(c->in_r, rd + rec_span(plen));
    return 1;
}

int flm_out_push(uint32_t slot, uint32_t gen, uint32_t kind, uint32_t val, const uint8_t *data, uint32_t len, uint32_t *end) {
    flm_ctl_t *c = &g_ctl;
    uint32_t span = rec_span(len), wr = c->out_w, rd = LD(c->out_r);
    if (len > FLM_MAX_SYSEX || FLM_OUT_RING_BYTES - (wr - rd) < span) return -1;
    uint8_t hdr[FLM_REC] = {0};
    uint32_t w0 = (slot & 0xff) | (kind & 0xff) << 8 | (gen & 0xffff) << 16;
    double ts = 0;
    memcpy(hdr, &w0, 4); memcpy(hdr + 4, &val, 4); memcpy(hdr + 8, &ts, 8);
    ring_put(g_out_ring, FLM_OUT_RING_BYTES, wr, hdr, FLM_REC);
    if (len) ring_put(g_out_ring, FLM_OUT_RING_BYTES, wr + FLM_REC, data, len);
    ST(c->out_w, wr + span);
    __builtin_wasm_memory_atomic_notify((int *)&c->out_w, 0x7fffffff);
    if (end) *end = wr + span;
    return 0;
}

int flm_dev_snapshot(flm_dev_t out[2][FLM_MAX_DEV], uint32_t n[2]) {
    flm_ctl_t *c = &g_ctl;
    for (;;) {
        uint32_t s0 = LD(c->tbl_seq);
        if (s0 & 1) { __builtin_wasm_memory_atomic_wait32((int *)&c->tbl_seq, (int)s0, 1000000); continue; }
        n[0] = LD(c->n_in); n[1] = LD(c->n_out);
        memcpy(out, g_devtbl, sizeof g_devtbl);
        uint32_t gen = LD(c->scan_gen);
        if (LD(c->tbl_seq) == s0) return (int)gen;
    }
}
