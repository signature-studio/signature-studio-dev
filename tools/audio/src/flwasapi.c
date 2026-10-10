/* flwasapi.c — WASAPI 互換 (render, shared, float, event/polling)。同じリング/worklet を使う。 */
#include "flwasapi.h"
#include "flaudio.h"
#include <emscripten.h>
#include <stdlib.h>
#include <string.h>

#define LD(x) __atomic_load_n(&(x), __ATOMIC_SEQ_CST)

static struct {
    int inited, running, event_mode, outstanding;
    uint32_t sr, ch, period, bufframes;
    float *stage;                   /* interleaved */
    float *planar[FLA_MAX_CH];
    uint32_t evt_next;              /* 次に発火すべき device frames (低32bit) */
    int evt_primed;
} W;

#define HNS_TO_FRAMES(h, sr) ((uint32_t)(((h) * (int64_t)(sr) + 5000000LL) / 10000000LL))
#define FRAMES_TO_HNS(f, sr) ((int64_t)(f) * 10000000LL / (int64_t)(sr))

FLHR flwasapi_get_mix_format(flwasapi_fmt_t *f) { f->sample_rate = 48000; f->channels = 2; return FL_S_OK; }
FLHR flwasapi_get_device_period(int64_t *d, int64_t *m) {
    *d = FRAMES_TO_HNS(512, 48000); *m = FRAMES_TO_HNS(FLA_QUANTUM, 48000);
    return FL_S_OK;
}
FLHR flwasapi_is_format_supported(const flwasapi_fmt_t *f) {
    return (f->sample_rate >= 8000 && f->sample_rate <= 192000 && f->channels >= 1 && f->channels <= FLA_MAX_CH)
               ? FL_S_OK : FL_AUDCLNT_E_UNSUPPORTED_FORMAT;
}

FLHR flwasapi_initialize(int share_mode, uint32_t stream_flags, int64_t bufdur, int64_t period_hns, const flwasapi_fmt_t *f) {
    if (W.inited) return FL_AUDCLNT_E_ALREADY_INITIALIZED;
    if (share_mode != FL_AUDCLNT_SHAREMODE_SHARED) fla_failfast("flwasapi_initialize", "exclusive mode not supported (browser has no exclusive path)");
    if (flwasapi_is_format_supported(f) != FL_S_OK) return FL_AUDCLNT_E_UNSUPPORTED_FORMAT;
    uint32_t period = period_hns ? HNS_TO_FRAMES(period_hns, f->sample_rate) : 512;
    period = (period + FLA_QUANTUM - 1) / FLA_QUANTUM * FLA_QUANTUM;
    if (period < FLA_QUANTUM) period = FLA_QUANTUM;
    uint32_t buf = bufdur ? HNS_TO_FRAMES(bufdur, f->sample_rate) : 2 * period;
    uint32_t depth = (buf + period - 1) / period;
    if (depth < 2) depth = 2;
    if (depth > 8 || period > 8192) return FL_AUDCLNT_E_INVALID_SIZE;
    if (fla_open(f->sample_rate, f->channels, 0, period, depth, FLA_F_DECLICK) != 0) return FL_AUDCLNT_E_DEVICE_INVALIDATED;
    depth = fla_ctl()->depth;
    W.sr = f->sample_rate; W.ch = f->channels; W.period = period; W.bufframes = depth * period;
    W.event_mode = (stream_flags & FL_AUDCLNT_STREAMFLAGS_EVENTCALLBACK) != 0;
    W.stage = calloc((size_t)W.bufframes * W.ch, sizeof(float));
    for (uint32_t c = 0; c < W.ch; c++) W.planar[c] = calloc(W.bufframes, sizeof(float));
    fla_reset_indexes();
    W.inited = 1;
    return FL_S_OK;
}

#define NEED() do { if (!W.inited) return FL_AUDCLNT_E_NOT_INITIALIZED; } while (0)

FLHR flwasapi_get_buffer_size(uint32_t *fr) { NEED(); *fr = W.bufframes; return FL_S_OK; }
FLHR flwasapi_get_stream_latency(int64_t *hns) {
    NEED();
    fla_ctl_t *c = fla_ctl();
    double hw = (LD(c->base_latency_us) + LD(c->out_latency_us)) * 1e-6 * W.sr;
    *hns = FRAMES_TO_HNS((uint32_t)(W.period + FLA_QUANTUM + hw), W.sr);
    return FL_S_OK;
}
FLHR flwasapi_get_current_padding(uint32_t *fr) { NEED(); *fr = fla_out_fill(); return FL_S_OK; }
FLHR flwasapi_set_event_handle(int enable) {
    NEED();
    if (!W.event_mode) return FL_AUDCLNT_E_EVENTHANDLE_NOT_SET;
    (void)enable;
    return FL_S_OK;
}

int flwasapi_wait_event(uint32_t timeout_ms) {
    if (!W.inited || !W.event_mode) fla_failfast("flwasapi_wait_event", "no event handle set (stream not initialised with EVENTCALLBACK)");
    if (!W.evt_primed) fla_failfast("flwasapi_wait_event", "call after flwasapi_start");
    int rc = fla_wait_dev_frames(W.evt_next, timeout_ms);
    if (rc != 0) return FL_WAIT_TIMEOUT;
    /* 取りこぼしは 1 回に合体 (auto-reset event 相当) */
    uint32_t cur = (uint32_t)__atomic_load_n(&fla_ctl()->dev_frames, __ATOMIC_SEQ_CST);
    W.evt_next += W.period;
    if ((int32_t)(cur - W.evt_next) >= 0) W.evt_next = cur + W.period - ((cur - W.evt_next) % W.period);
    return FL_WAIT_OBJECT_0;
}

FLHR flwasapi_start(void) {
    NEED();
    if (W.running) return FL_S_OK;
    fla_go();
    W.running = 1;
    uint32_t cur = (uint32_t)__atomic_load_n(&fla_ctl()->dev_frames, __ATOMIC_SEQ_CST);
    W.evt_next = (cur + W.period) / FLA_QUANTUM * FLA_QUANTUM;
    W.evt_primed = 1;
    return FL_S_OK;
}
FLHR flwasapi_stop(void) { NEED(); if (W.running) { fla_halt(); W.running = 0; W.evt_primed = 0; } return FL_S_OK; }
FLHR flwasapi_reset(void) {
    NEED();
    if (W.running) return FL_AUDCLNT_E_NOT_STOPPED;
    if (W.outstanding) return FL_AUDCLNT_E_BUFFER_TOO_LARGE;
    fla_reset_indexes();
    return FL_S_OK;
}

FLHR flwasapi_render_get_buffer(uint32_t frames, float **data) {
    NEED();
    if (W.outstanding) return FL_AUDCLNT_E_OUT_OF_ORDER;
    if (frames > W.bufframes - fla_out_fill()) return FL_AUDCLNT_E_BUFFER_TOO_LARGE;
    W.outstanding = (int)frames ? (int)frames : -1;
    *data = W.stage;
    return FL_S_OK;
}
FLHR flwasapi_render_release_buffer(uint32_t frames, uint32_t flags) {
    NEED();
    if (!W.outstanding) return FL_AUDCLNT_E_OUT_OF_ORDER;
    uint32_t got = W.outstanding < 0 ? 0 : (uint32_t)W.outstanding;
    W.outstanding = 0;
    if (frames > got) return FL_AUDCLNT_E_INVALID_SIZE;
    if (frames == 0) return FL_S_OK;
    if (flags & FL_AUDCLNT_BUFFERFLAGS_SILENT) { fla_out_write_silence(frames); return FL_S_OK; }
    for (uint32_t i = 0; i < frames; i++)
        for (uint32_t c = 0; c < W.ch; c++) W.planar[c][i] = W.stage[(size_t)i * W.ch + c];
    fla_out_write((const float *const *)W.planar, frames);
    return FL_S_OK;
}

FLHR flwasapi_release(void) {
    if (!W.inited) return FL_S_OK;
    flwasapi_stop();
    fla_close();
    free(W.stage); W.stage = NULL;
    for (uint32_t c = 0; c < W.ch; c++) { free(W.planar[c]); W.planar[c] = NULL; }
    memset(&W, 0, sizeof W);
    return FL_S_OK;
}

FLHR flwasapi_capture_get_buffer(float **d, uint32_t *f, uint32_t *fl) {
    (void)d; (void)f; (void)fl;
    fla_failfast("flwasapi_capture_get_buffer", "IAudioCaptureClient not implemented (design: docs/PROTOCOL.md §6; ASIO input path is implemented)");
    return 0;
}
FLHR flwasapi_capture_release_buffer(uint32_t f) {
    (void)f;
    fla_failfast("flwasapi_capture_release_buffer", "IAudioCaptureClient not implemented");
    return 0;
}
