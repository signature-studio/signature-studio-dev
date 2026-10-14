/* flaudio.c — FL audio shim core (SAB リング + コントロールブロック + RPC)。設計は docs/PROTOCOL.md */
#include "flaudio.h"
#include <emscripten.h>
#include <emscripten/threading.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LD(x)     __atomic_load_n(&(x), __ATOMIC_SEQ_CST)
#define ST(x, v)  __atomic_store_n(&(x), (v), __ATOMIC_SEQ_CST)

static fla_ctl_t g_ctl __attribute__((aligned(64)));
static pthread_mutex_t g_cmd_lock = PTHREAD_MUTEX_INITIALIZER;
static float *g_out_ring, *g_in_ring;

_Static_assert(sizeof(fla_ctl_t) == FLA_CTL_SIZE, "fla_ctl_t size");

void fla_failfast(const char *api, const char *why) {
    fprintf(stderr, "[flaudio] FAIL-FAST: %s: %s\n", api, why);
    fflush(stderr);
    abort();
}

#define OFF(f) { #f, (uint32_t)offsetof(fla_ctl_t, f) }
static const fla_layout_entry_t g_layout[] = {
    OFF(magic), OFF(state), OFF(sample_rate), OFF(out_ch), OFF(in_ch), OFF(ring_frames), OFF(ring_mask),
    OFF(buffer_frames), OFF(depth), OFF(rebuffer_frames), OFF(out_ring_ptr), OFF(in_ring_ptr), OFF(flags),
    OFF(dev_events), OFF(dev_frames), OFF(dev_ctx_time_bits), OFF(out_read), OFF(in_write), OFF(underruns),
    OFF(silence_frames), OFF(quanta), OFF(in_overruns), OFF(wl_state), OFF(clock_seq), OFF(play_start_frame), OFF(clock_jumps), OFF(clock_jump_frames),
    OFF(out_write), OFF(in_read), OFF(wake_target), OFF(gen), OFF(go), OFF(in_wake_target), OFF(tick_target), OFF(notify_ms), OFF(burst_obs),
    OFF(clock_skip_frames), OFF(clock_dup_frames), OFF(clock_jump_max), OFF(clock_jump_max_q),
    OFF(clock_first_q), OFF(clock_last_q), OFF(cb_max_q), OFF(wake_hist),
    OFF(ref_ctx_time_bits), OFF(ref_epoch_ms_bits), OFF(ref_seq), OFF(out_latency_us), OFF(base_latency_us),
    OFF(cmd_seq), OFF(cmd_op), OFF(cmd_arg), OFF(ack_seq), OFF(ack_status), OFF(ack_res), OFF(ctrl_ready),
    OFF(cb_count), OFF(cb_late), OFF(cb_max_us), OFF(cb_sum_us_lo), OFF(wake_count), OFF(wait_timeouts),
    OFF(in_underflows), OFF(min_fill), OFF(fill_sum_lo), OFF(fill_samples),
};
const fla_layout_entry_t *fla_layout_offsets(int *count) {
    *count = (int)(sizeof g_layout / sizeof g_layout[0]);
    return g_layout;
}
/* JS 自己検証用: i 番目のオフセット / 個数 / 名前 */
EMSCRIPTEN_KEEPALIVE int fla_layout_count(void) { return (int)(sizeof g_layout / sizeof g_layout[0]); }
EMSCRIPTEN_KEEPALIVE uint32_t fla_layout_off(int i) { return g_layout[i].off; }
EMSCRIPTEN_KEEPALIVE const char *fla_layout_name(int i) { return g_layout[i].name; }

fla_ctl_t *fla_ctl(void) { return &g_ctl; }
EMSCRIPTEN_KEEPALIVE uintptr_t fla_ctl_ptr(void) { return (uintptr_t)&g_ctl; }

EM_JS(double, fla_now_ms, (void), { return performance.timeOrigin + performance.now(); });

static int wait32(uint32_t *addr, uint32_t expect, int64_t timeout_ns) {
    return __builtin_wasm_memory_atomic_wait32((int *)addr, (int)expect, timeout_ns);
}
static void wake32(uint32_t *addr) { __builtin_wasm_memory_atomic_notify((int *)addr, 0x7fffffff); }

static void require_worker(const char *api) {
    if (emscripten_is_main_browser_thread())
        fla_failfast(api, "blocking call on the main browser thread (use PROXY_TO_PTHREAD / worker)");
}

int fla_cmd(uint32_t op, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t res[4], uint32_t timeout_ms) {
    require_worker("fla_cmd");
    fla_ctl_t *c = &g_ctl;
    pthread_mutex_lock(&g_cmd_lock);
    c->cmd_op = op;
    c->cmd_arg[0] = a0; c->cmd_arg[1] = a1; c->cmd_arg[2] = a2; c->cmd_arg[3] = a3;
    uint32_t seq = __atomic_add_fetch(&c->cmd_seq, 1, __ATOMIC_SEQ_CST);
    wake32(&c->cmd_seq);
    double t0 = emscripten_get_now();
    int rc = -1;
    for (;;) {
        uint32_t ack = LD(c->ack_seq);
        if (ack == seq) { rc = c->ack_status; break; }
        double left = timeout_ms - (emscripten_get_now() - t0);
        if (left <= 0) break;
        wait32(&c->ack_seq, ack, (int64_t)(left * 1e6));
    }
    if (rc == 0 && res) memcpy(res, c->ack_res, sizeof c->ack_res);
    pthread_mutex_unlock(&g_cmd_lock);
    return rc;
}

static uint32_t pow2_ge(uint32_t v) { uint32_t p = 1; while (p < v) p <<= 1; return p; }

static uint32_t g_burst_floor;
void fla_test_set_burst_floor(uint32_t frames) { g_burst_floor = frames; }

int fla_open(uint32_t sr, uint32_t out_ch, uint32_t in_ch, uint32_t buffer_frames, uint32_t depth, uint32_t flags) {
    fla_ctl_t *c = &g_ctl;
    if (LD(c->state) != FLA_ST_CLOSED) fla_failfast("fla_open", "already open");
    if (sr < 8000 || sr > 192000) fla_failfast("fla_open", "sample_rate out of range");
    if (out_ch < 1 || out_ch > FLA_MAX_CH || in_ch > FLA_MAX_CH) fla_failfast("fla_open", "channel count out of range");
    if (buffer_frames < FLA_QUANTUM || buffer_frames % FLA_QUANTUM || buffer_frames > 8192)
        fla_failfast("fla_open", "buffer_frames must be a multiple of 128 in [128, 8192]");
    if (depth < 2 || depth > 8) fla_failfast("fla_open", "depth must be in [2, 8]");
    /* phase 1: AudioContext 生成 → ブラウザの音声コールバック粒度 (burst) を取得 */
    uint32_t res[4] = {0};
    int rc = fla_cmd(FLA_CMD_OPEN, sr, out_ch, in_ch, flags >> 8 & 0xff, res, 15000);
    if (rc != 0) return rc ? rc : -1;
    uint32_t burst = (res[0] + FLA_QUANTUM - 1) / FLA_QUANTUM * FLA_QUANTUM;
    if (burst < g_burst_floor) burst = g_burst_floor;
    if (burst < FLA_QUANTUM) burst = FLA_QUANTUM;
    /* 目標充填 T: worklet は burst (= baseLatency 相当, 通常 128..1024; 96kHz では 2048..4096) フレームを連続で引く。
     * T >= burst + buffer_frames でないと 1 回の burst で枯渇する (PROTOCOL.md §4) */
    uint64_t need = ((uint64_t)burst * FLA_BURST_PCT / 100 + buffer_frames + buffer_frames - 1) / buffer_frames;
    if (need > depth) depth = (uint32_t)need;
    /* depth の固定上限は置かない。制約は ring 容量のみ: 動的 T 拡張 (flasio, 上限 ring-2B) の余地を含め
     * (depth+2)*B <= FLA_MAX_RING が必要。超過はホストを落とさずエラー返却 (呼び側が CreateBuffers エラーに写像) */
    uint64_t t_min = ((uint64_t)depth + 2) * buffer_frames;
    if (t_min > FLA_MAX_RING) {
        fprintf(stderr, "[flaudio] fla_open: burst %u frames needs depth %u x B=%u (+2B headroom = %llu frames) > FLA_MAX_RING %u -> FLA_E_BURST_TOO_LARGE\n",
                burst, depth, buffer_frames, (unsigned long long)t_min, FLA_MAX_RING);
        fla_cmd(FLA_CMD_CLOSE, 0, 0, 0, 0, NULL, 5000);   /* phase 1 で作った AudioContext を片付ける */
        return FLA_E_BURST_TOO_LARGE;
    }
    /* 動的 T 拡張 (flasio) の余地として 4x を確保。最小 16384 frames */
    uint32_t ring = pow2_ge(4 * (depth + 1) * buffer_frames);
    if (ring < 16384) ring = 16384;
    if (ring > FLA_MAX_RING) ring = FLA_MAX_RING;
    g_out_ring = aligned_alloc(64, (size_t)ring * out_ch * sizeof(float));
    g_in_ring = in_ch ? aligned_alloc(64, (size_t)ring * in_ch * sizeof(float)) : NULL;
    if (!g_out_ring || (in_ch && !g_in_ring)) fla_failfast("fla_open", "out of memory");
    memset(g_out_ring, 0, (size_t)ring * out_ch * sizeof(float));
    if (g_in_ring) memset(g_in_ring, 0, (size_t)ring * in_ch * sizeof(float));
    c->magic = FLA_MAGIC; c->abi = FLA_ABI; c->quantum = FLA_QUANTUM;
    c->sample_rate = res[1] ? res[1] : sr; c->out_ch = out_ch; c->in_ch = in_ch;
    c->ring_frames = ring; c->ring_mask = ring - 1;
    c->buffer_frames = buffer_frames; c->depth = depth; c->rebuffer_frames = buffer_frames;
    c->out_ring_ptr = (uint32_t)(uintptr_t)g_out_ring; c->in_ring_ptr = (uint32_t)(uintptr_t)g_in_ring;
    c->flags = (flags & 0xff) | (in_ch ? FLA_F_INPUT : 0);
    ST(c->go, 0);
    ST(c->state, FLA_ST_OPENED);
    /* phase 2: ring 確保後に AudioWorkletNode を生成 (最新の wasm SAB を渡す) */
    rc = fla_cmd(FLA_CMD_ATTACH, 0, 0, 0, 0, NULL, 15000);
    if (rc != 0) {
        ST(c->state, FLA_ST_CLOSED);
        free(g_out_ring); free(g_in_ring); g_out_ring = g_in_ring = NULL;
        return rc ? rc : -1;
    }
    return 0;
}

void fla_close(void) {
    fla_ctl_t *c = &g_ctl;
    if (LD(c->state) == FLA_ST_CLOSED) return;
    fla_halt();
    ST(c->state, FLA_ST_CLOSED);
    fla_cmd(FLA_CMD_CLOSE, 0, 0, 0, 0, NULL, 5000);
    free(g_out_ring); free(g_in_ring); g_out_ring = g_in_ring = NULL;
}

void fla_halt(void) {
    fla_ctl_t *c = &g_ctl;
    ST(c->go, 0);
    wake32(&c->out_read);
    double t0 = emscripten_get_now();
    while (LD(c->wl_state) != FLA_WL_IDLE && emscripten_get_now() - t0 < 300) {
        wait32(&c->wl_state, LD(c->wl_state), 20 * 1000000LL);
    }
    if (LD(c->state) == FLA_ST_RUNNING) ST(c->state, FLA_ST_OPENED);
}

void fla_reset_indexes(void) {
    fla_ctl_t *c = &g_ctl;
    if (LD(c->go)) fla_failfast("fla_reset_indexes", "worklet is running (call fla_halt first)");
    memset(g_out_ring, 0, (size_t)c->ring_frames * c->out_ch * sizeof(float));
    if (g_in_ring) memset(g_in_ring, 0, (size_t)c->ring_frames * c->in_ch * sizeof(float));
    ST(c->out_write, 0); ST(c->out_read, 0); ST(c->in_read, 0); ST(c->in_write, 0);
    ST(c->wake_target, 0);
    ST(c->burst_obs, 0);
    ST(c->underruns, 0); ST(c->silence_frames, 0); ST(c->in_overruns, 0);
    c->cb_count = c->cb_late = c->cb_max_us = c->cb_sum_us_lo = c->wake_count = c->wait_timeouts = 0;
    c->in_underflows = 0; c->min_fill = 0xffffffffu; c->fill_sum_lo = 0; c->fill_samples = 0;
    memset(c->wake_hist, 0, sizeof c->wake_hist);
}

void fla_go(void) {
    fla_ctl_t *c = &g_ctl;
    if (LD(c->state) == FLA_ST_CLOSED) fla_failfast("fla_go", "not open");
    ST(c->state, FLA_ST_RUNNING);
    __atomic_add_fetch(&c->gen, 1, __ATOMIC_SEQ_CST);
    ST(c->go, 1);
}

uint32_t fla_out_fill(void) { return g_ctl.out_write - LD(g_ctl.out_read); }

int fla_out_wait_fill_le(uint32_t max_fill, uint32_t timeout_ms) {
    require_worker("fla_out_wait_fill_le");
    fla_ctl_t *c = &g_ctl;
    uint32_t w = c->out_write;
    double t0 = emscripten_get_now();
    for (;;) {
        if (LD(c->state) != FLA_ST_RUNNING) return -1;
        uint32_t r = LD(c->out_read);
        if (w - r <= max_fill) return 0;
        uint32_t target = w - max_fill;
        ST(c->wake_target, target);
        uint32_t r2 = LD(c->out_read);
        if ((int32_t)(r2 - target) >= 0) continue;
        double left = timeout_ms - (emscripten_get_now() - t0);
        if (left <= 0) { __atomic_add_fetch(&c->wait_timeouts, 1, __ATOMIC_RELAXED); return 1; }
        int rc = wait32(&c->out_read, r2, (int64_t)(left * 1e6));
        if (rc == 0) {
            __atomic_add_fetch(&c->wake_count, 1, __ATOMIC_RELAXED);
            int32_t d = (int32_t)((uint32_t)(uint64_t)fla_now_ms() - LD(c->notify_ms));
            int b = d < 1 ? 0 : d < 2 ? 1 : d < 4 ? 2 : d < 8 ? 3 : d < 16 ? 4 : 5;
            if (d > -1000 && d < 100000) __atomic_add_fetch(&c->wake_hist[b], 1, __ATOMIC_RELAXED);
        }
    }
}

void fla_out_write(const float *const *planar, uint32_t frames) {
    fla_ctl_t *c = &g_ctl;
    uint32_t w = c->out_write, mask = c->ring_mask, ring = c->ring_frames;
    uint32_t r = LD(c->out_read);
    if (w - r + frames > ring) fla_failfast("fla_out_write", "ring overflow (producer wrote beyond capacity)");
    uint32_t pos = w & mask;
    uint32_t first = frames < ring - pos ? frames : ring - pos;
    for (uint32_t ch = 0; ch < c->out_ch; ch++) {
        float *dst = g_out_ring + (size_t)ch * ring;
        const float *src = planar[ch];
        memcpy(dst + pos, src, (size_t)first * sizeof(float));
        if (frames > first) memcpy(dst, src + first, (size_t)(frames - first) * sizeof(float));
    }
    ST(c->out_write, w + frames);
}

void fla_out_write_silence(uint32_t frames) {
    fla_ctl_t *c = &g_ctl;
    uint32_t w = c->out_write, mask = c->ring_mask, ring = c->ring_frames;
    uint32_t pos = w & mask;
    uint32_t first = frames < ring - pos ? frames : ring - pos;
    for (uint32_t ch = 0; ch < c->out_ch; ch++) {
        float *dst = g_out_ring + (size_t)ch * ring;
        memset(dst + pos, 0, (size_t)first * sizeof(float));
        if (frames > first) memset(dst, 0, (size_t)(frames - first) * sizeof(float));
    }
    ST(c->out_write, w + frames);
}

uint32_t fla_in_avail(void) { return LD(g_ctl.in_write) - g_ctl.in_read; }

uint32_t fla_in_read(float *const *planar, uint32_t frames) {
    fla_ctl_t *c = &g_ctl;
    uint32_t r = c->in_read, avail = LD(c->in_write) - r;
    uint32_t n = avail < frames ? avail : frames;
    uint32_t mask = c->ring_mask, ring = c->ring_frames;
    uint32_t pos = r & mask;
    uint32_t first = n < ring - pos ? n : ring - pos;
    for (uint32_t ch = 0; ch < c->in_ch; ch++) {
        const float *src = g_in_ring + (size_t)ch * ring;
        float *dst = planar[ch];
        memcpy(dst, src + pos, (size_t)first * sizeof(float));
        if (n > first) memcpy(dst + first, src, (size_t)(n - first) * sizeof(float));
        if (n < frames) memset(dst + n, 0, (size_t)(frames - n) * sizeof(float));
    }
    if (n < frames) __atomic_add_fetch(&c->in_underflows, 1, __ATOMIC_RELAXED);
    ST(c->in_read, r + n);
    return n;
}

int fla_wait_dev_frames(uint32_t target_lo, uint32_t timeout_ms) {
    require_worker("fla_wait_dev_frames");
    fla_ctl_t *c = &g_ctl;
    double t0 = emscripten_get_now();
    for (;;) {
        if (LD(c->state) == FLA_ST_CLOSED) return -1;
        uint32_t q = LD(c->quanta);
        uint32_t cur = (uint32_t)__atomic_load_n(&c->dev_frames, __ATOMIC_SEQ_CST);
        if ((int32_t)(cur - target_lo) >= 0) return 0;
        ST(c->tick_target, target_lo);
        if (LD(c->quanta) != q) continue;
        double left = timeout_ms - (emscripten_get_now() - t0);
        if (left <= 0) return 1;
        wait32(&c->quanta, q, (int64_t)(left * 1e6));
    }
}

static double bits_to_f64(uint64_t b) { double d; memcpy(&d, &b, 8); return d; }

void fla_clock_read(fla_clock_t *out) {
    fla_ctl_t *c = &g_ctl;
    uint32_t s0, s1;
    uint64_t fr, tb;
    do {
        s0 = LD(c->clock_seq);
        fr = __atomic_load_n(&c->dev_frames, __ATOMIC_SEQ_CST);
        tb = __atomic_load_n(&c->dev_ctx_time_bits, __ATOMIC_SEQ_CST);
        s1 = LD(c->clock_seq);
    } while ((s0 & 1) || s0 != s1);
    double ctx = bits_to_f64(tb);
    uint32_t r0, r1;
    uint64_t rc, re;
    do {
        r0 = LD(c->ref_seq);
        rc = __atomic_load_n(&c->ref_ctx_time_bits, __ATOMIC_SEQ_CST);
        re = __atomic_load_n(&c->ref_epoch_ms_bits, __ATOMIC_SEQ_CST);
        r1 = LD(c->ref_seq);
    } while ((r0 & 1) || r0 != r1);
    out->pos_frames = fr;
    out->ctx_time = ctx;
    out->play_start = __atomic_load_n(&c->play_start_frame, __ATOMIC_SEQ_CST);
    out->audible_ns = r0 ? (uint64_t)((bits_to_f64(re) + (ctx - bits_to_f64(rc)) * 1000.0) * 1e6) : 0;
}
