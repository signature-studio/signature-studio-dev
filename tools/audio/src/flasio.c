/* flasio.c — ASIO 互換層 (コールバック駆動 bufferSwitch を shim スレッドから SAB リングへ)。
 * 設計: docs/PROTOCOL.md §3。ILWASAPI2ASIO_x64 実測値 (2in/2out, Float32LSB, "Internal" clock,
 * 22050/44100/48000/96000/192000, outputReady=ASE_NotPresent) を既定とする。 */
#include "flasio.h"
#include "flaudio.h"
#include <emscripten.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LD(x) __atomic_load_n(&(x), __ATOMIC_SEQ_CST)

#define FLASIO_NUM_IN  2
#define FLASIO_NUM_OUT 2

#ifndef FLASIO_SHRINK_STABLE_MS
#define FLASIO_SHRINK_STABLE_MS 3000   /* underrun 無しがこの時間続いたら T を B 刻みで 1 段減衰 (閾値は AU-2 実機データで調整) */
#endif

static struct {
    int inited, created, running;
    ASIOCallbacks cb;
    double sr;
    uint32_t B, depth, hint;
    int nOut, nIn;                          /* ring に開くチャネル数 (使用最大 index + 1) */
    int useOut[FLA_MAX_CH], useIn[FLA_MAX_CH];
    float *obuf[2][FLA_MAX_CH], *ibuf[2][FLA_MAX_CH];
    pthread_t th;
    volatile int stop;
    uint32_t ready;
    uint32_t reset_requests, latency_changes, T, timeinfo_cb;
    uint32_t grows, shrinks, T_max, T0;
    int use_timeinfo, notify_lat;
    uint32_t seg_max_us[4];                 /* do_buffer 区間の最大 µs: in_read / memset / bufferSwitch 本体 / out_write */
} A = { .sr = 48000.0, .depth = 2, .hint = 0 };
static uint32_t g_open_depth;   /* 診断計装: fla_open 直後の実効 depth */

static void wake32(uint32_t *a) { __builtin_wasm_memory_atomic_notify((int *)a, 0x7fffffff); }

void flasio_set_notify_latency_changes(int on) { A.notify_lat = on; }

void flasio_configure(uint32_t depth, uint32_t latency_hint) {
    if (A.created) fla_failfast("flasio_configure", "must be called before CreateBuffers");
    if (depth < 2 || depth > 8) fla_failfast("flasio_configure", "depth in [2,8]");
    A.depth = depth; A.hint = latency_hint;
}

ASIOBool flasio_init(void *sysHandle) {
    (void)sysHandle;
    A.inited = 1;
    return 1;
}
void flasio_get_driver_name(char name[32]) { memset(name, 0, 32); strcpy(name, "FL Studio ASIO"); }
ASIOLong flasio_get_driver_version(void) { return 1; }

static void need_init(const char *api) { if (!A.inited) fla_failfast(api, "driver not initialised (call flasio_init)"); }

/* ASIOTime.systemTime / getSamplePosition の timeStamp (ns)。ILWASAPI2ASIO (0x1800039b0) と同じく timeGetTime() ms × 1e6。 */
static uint64_t systime_ns(const fla_clock_t *k) {
#if FLASIO_SYSTIME_AUDIBLE
    return k->audible_ns;
#else
    (void)k;
    return (uint64_t)(uint32_t)(uint64_t)emscripten_get_now() * 1000000ULL;
#endif
}

ASIOError flasio_get_channels(ASIOLong *numIn, ASIOLong *numOut) {
    need_init("flasio_get_channels");
    *numIn = FLASIO_NUM_IN; *numOut = FLASIO_NUM_OUT;
    return ASE_OK;
}

ASIOError flasio_get_buffer_size(ASIOLong *minS, ASIOLong *maxS, ASIOLong *prefS, ASIOLong *gran) {
    need_init("flasio_get_buffer_size");
#if FLASIO_PROFILE_ILWASAPI
    *minS = 256; *maxS = 4096; *gran = 0;
#else
    *minS = FLA_QUANTUM; *maxS = 4096; *gran = FLA_QUANTUM;
#endif
    *prefS = A.created ? (ASIOLong)A.B : 512;
    return ASE_OK;
}

ASIOError flasio_can_sample_rate(double r) {
    need_init("flasio_can_sample_rate");
    static const double ok[] = { 22050.0, 44100.0, 48000.0, 96000.0, 192000.0 };
    for (unsigned i = 0; i < sizeof ok / sizeof ok[0]; i++) if (r == ok[i]) return ASE_OK;
    return ASE_NoClock;
}
ASIOError flasio_get_sample_rate(double *r) { need_init("flasio_get_sample_rate"); *r = A.sr; return ASE_OK; }
ASIOError flasio_set_sample_rate(double r) {
    need_init("flasio_set_sample_rate");
    if (flasio_can_sample_rate(r) != ASE_OK) return ASE_NoClock;
    if (A.running) return ASE_InvalidMode;
    if (r == A.sr) return ASE_OK;
    if (A.created) {
        fla_ctl_t *c = fla_ctl();
        c->sample_rate = (uint32_t)r;
        if (fla_cmd(FLA_CMD_SET_SR, (uint32_t)r, 0, 0, 0, NULL, 10000) != 0) return ASE_HWMalfunction;
    }
    A.sr = r;
    if (A.cb.sampleRateDidChange) A.cb.sampleRateDidChange(r);
    return ASE_OK;
}
ASIOError flasio_get_clock_sources(ASIOClockSource *clocks, ASIOLong *num) {
    need_init("flasio_get_clock_sources");
    memset(clocks, 0, sizeof *clocks);
    clocks[0].index = 0; clocks[0].associatedChannel = -1; clocks[0].associatedGroup = -1;
    clocks[0].isCurrentSource = 1; strcpy(clocks[0].name, "Internal");
    *num = 1;
    return ASE_OK;
}
ASIOError flasio_set_clock_source(ASIOLong ref) { need_init("flasio_set_clock_source"); return ref == 0 ? ASE_OK : ASE_InvalidParameter; }

ASIOError flasio_get_channel_info(ASIOChannelInfo *info) {
    need_init("flasio_get_channel_info");
    int n = info->isInput ? FLASIO_NUM_IN : FLASIO_NUM_OUT;
    if (info->channel < 0 || info->channel >= n) return ASE_InvalidParameter;
    info->type = ASIOSTFloat32LSB; info->channelGroup = 0;
    info->isActive = A.created && (info->isInput ? A.useIn[info->channel] : A.useOut[info->channel]);
    snprintf(info->name, sizeof info->name, info->isInput ? "In %i" : "Out %i", info->channel + 1);
    return ASE_OK;
}

ASIOError flasio_get_latencies(ASIOLong *inLat, ASIOLong *outLat) {
    need_init("flasio_get_latencies");
    if (!A.created) { *inLat = *outLat = 0; return ASE_OK; }   /* ASIO 仕様: CreateBuffers 後のみ有効 */
    fla_ctl_t *c = fla_ctl();
    double hw_out = (LD(c->base_latency_us) + LD(c->out_latency_us)) * 1e-6 * A.sr;
    double hw_in = LD(c->base_latency_us) * 1e-6 * A.sr;
    *outLat = (ASIOLong)(A.depth * A.B + FLA_QUANTUM + hw_out + 0.5);   /* depth は動的拡張後の値 */
    *inLat = (ASIOLong)(A.B + FLA_QUANTUM + hw_in + 0.5);
    return ASE_OK;
}

ASIOError flasio_create_buffers(ASIOBufferInfo *infos, ASIOLong n, ASIOLong bufferSize, ASIOCallbacks *cb) {
    need_init("flasio_create_buffers");
    if (A.created) return ASE_InvalidMode;
    if (!infos || n <= 0 || !cb) return ASE_InvalidParameter;
    if (!cb->bufferSwitch) fla_failfast("flasio_create_buffers", "ASIOCallbacks.bufferSwitch is NULL");
    if (bufferSize < (ASIOLong)FLA_QUANTUM || bufferSize > 4096 || bufferSize % FLA_QUANTUM) return ASE_InvalidMode;
    memset(A.useOut, 0, sizeof A.useOut); memset(A.useIn, 0, sizeof A.useIn);
    int nOut = 0, nIn = 0;
    for (int i = 0; i < n; i++) {
        int ch = infos[i].channelNum;
        if (ch < 0 || ch >= (infos[i].isInput ? FLASIO_NUM_IN : FLASIO_NUM_OUT)) return ASE_InvalidMode;
        if (infos[i].isInput) { A.useIn[ch] = 1; if (ch + 1 > nIn) nIn = ch + 1; }
        else { A.useOut[ch] = 1; if (ch + 1 > nOut) nOut = ch + 1; }
    }
    if (nOut == 0) nOut = 1;                    /* 出力ゼロ指定でも ring は 1ch 必要 */
    A.B = (uint32_t)bufferSize; A.nOut = nOut; A.nIn = nIn; A.cb = *cb;
    int orc = fla_open((uint32_t)A.sr, (uint32_t)nOut, (uint32_t)nIn, A.B, A.depth, FLA_F_DECLICK | FLA_F_T_FLOOR | (A.hint << 8));
    if (orc == FLA_E_BURST_TOO_LARGE) return ASE_NoMemory;   /* FL: "Couldn't create the streaming ASIO buffer." (ホストは落とさない) */
    if (orc != 0) return ASE_NotPresent;
    A.depth = fla_ctl()->depth;                 /* burst に合わせて自動拡張された実効 depth */
    g_open_depth = A.depth;
    for (int b = 0; b < 2; b++) {
        for (int ch = 0; ch < nOut; ch++) A.obuf[b][ch] = calloc(A.B, sizeof(float));
        for (int ch = 0; ch < nIn; ch++) A.ibuf[b][ch] = calloc(A.B, sizeof(float));
    }
    for (int i = 0; i < n; i++) {
        int ch = infos[i].channelNum;
        for (int b = 0; b < 2; b++) infos[i].buffers[b] = infos[i].isInput ? (void *)A.ibuf[b][ch] : (void *)A.obuf[b][ch];
    }
    /* ホストの対応メッセージ問い合わせ (ASIO ハンドシェイク) */
    A.use_timeinfo = 0;
    if (cb->asioMessage) {
        cb->asioMessage(kAsioSelectorSupported, kAsioEngineVersion, NULL, NULL);
        cb->asioMessage(kAsioEngineVersion, 0, NULL, NULL);
        /* FL の asioMessage は kAsioSupportsTimeInfo に 1 を返す (実測) → bufferSwitchTimeInfo 経路を使う */
        if (cb->asioMessage(kAsioSelectorSupported, kAsioSupportsTimeInfo, NULL, NULL) == 1 &&
            cb->asioMessage(kAsioSupportsTimeInfo, 0, NULL, NULL) == 1 && cb->bufferSwitchTimeInfo)
            A.use_timeinfo = 1;
    }
    A.created = 1;
    return ASE_OK;
}

static void seg_note(int k, double us) {
    uint32_t u = (uint32_t)us;
    if (u > A.seg_max_us[k]) A.seg_max_us[k] = u;
}

/* 診断 (判定に使わない): producer の周期記録。行 = [notify (worklet の Date.now 下位32bit), fill, underruns, wake, cb0, cb1, wr]。
 * wake/cb0/cb1/wr は fla_now_ms (performance.timeOrigin + now、epoch ms)。fla_ctl_t の外に置く (共有 SAB の layout を変えない)。 */
#define FLASIO_TL_N 2048
static double g_tl[FLASIO_TL_N][7];
static uint32_t g_tl_n;
static double g_cb0, g_cb1, g_cb_tb, g_cb_t0;
static double g_tl2[FLASIO_TL_N][3];
double *flasio_tl2_ptr(void) { return &g_tl2[0][0]; }
double *flasio_tl_ptr(void) { return &g_tl[0][0]; }
uint32_t flasio_tl_count(void) { return g_tl_n; }
/* 診断計装 (判定に使わない): fla_open 直後 (床と burst 拡張の後) の初期 depth。実行中の動的拡張で変わる前の値 */
uint32_t flasio_open_depth(void) { return g_open_depth; }

static void do_buffer(int idx) {
    fla_ctl_t *c = fla_ctl();
    double ta = emscripten_get_now();
    g_cb0 = fla_now_ms();
    if (A.nIn) fla_in_read(A.ibuf[idx], A.B);       /* 入力 buffers[idx] を更新してからコールバック */
    double tb = emscripten_get_now();
    g_cb_tb = fla_now_ms();
    for (int ch = 0; ch < A.nOut; ch++) memset(A.obuf[idx][ch], 0, A.B * sizeof(float));
    double t0 = emscripten_get_now();
    g_cb_t0 = fla_now_ms();
    if (A.use_timeinfo) {
        ASIOTime t;
        memset(&t, 0, sizeof t);
        fla_clock_t k;
        fla_clock_read(&k);
        /* play_start は worklet が新 gen を認識した時に更新される (wl_state != IDLE でそれが確定)。それ以前は原点 0 に固定し、起動直後の位置巻き戻りを防ぐ */
        uint64_t pos = (LD(c->wl_state) != FLA_WL_IDLE && k.pos_frames > k.play_start) ? k.pos_frames - k.play_start : 0;
        t.timeInfo.samplePosition.hi = (uint32_t)(pos >> 32); t.timeInfo.samplePosition.lo = (uint32_t)pos;
        uint64_t st = systime_ns(&k);
        t.timeInfo.systemTime.hi = (uint32_t)(st >> 32); t.timeInfo.systemTime.lo = (uint32_t)st;
        t.timeInfo.sampleRate = A.sr; t.timeInfo.speed = 1.0;
        t.timeInfo.flags = kSampleRateValid | kSamplePositionValid | (st ? kSystemTimeValid : 0);
        A.timeinfo_cb++;
        A.cb.bufferSwitchTimeInfo(&t, idx, 1);
    } else {
        A.cb.bufferSwitch(idx, 1);
    }
    double t1 = emscripten_get_now();
    g_cb1 = fla_now_ms();
    double us = (t1 - t0) * 1000.0;
    uint32_t u = (uint32_t)us;
    c->cb_count++;
    c->cb_sum_us_lo += u;
    if (u > c->cb_max_us) { c->cb_max_us = u; c->cb_max_q = LD(c->quanta); }
    fla_out_write((const float *const *)A.obuf[idx], A.B);
    double te = emscripten_get_now();
    seg_note(0, (tb - ta) * 1000.0);
    seg_note(1, (t0 - tb) * 1000.0);
    seg_note(2, (t1 - t0) * 1000.0);
    seg_note(3, (te - t1) * 1000.0);
}

static void *thread_fn(void *arg) {
    (void)arg;
    fla_ctl_t *c = fla_ctl();
    int idx = 0;
    for (uint32_t k = 0; k < A.depth; k++) { do_buffer(idx); idx ^= 1; }     /* prefill (ASIO: 起動時に連続 bufferSwitch) */
    c->cb_count = 0; c->cb_sum_us_lo = 0; c->cb_max_us = 0; c->cb_max_q = 0; c->in_underflows = 0;   /* prefill 分は統計から除外 */
    for (int k = 0; k < 4; k++) A.seg_max_us[k] = 0;
    fla_go();
    __atomic_store_n(&A.ready, 1, __ATOMIC_SEQ_CST);
    wake32(&A.ready);
    /* 目標充填 T の動的調整: (1) worklet が観測した最長バースト × FLA_BURST_PCT% + B を下限に (2) underrun 毎に +B (上限 ring-2B)。
     * (3) underrun が FLASIO_SHRINK_STABLE_MS 続いたら +B を 1 段ずつ戻す (下限 (1) は下げない = 拡張とのヒステリシス)。
     * 変更時はホストへ kAsioLatenciesChanged (既定 OFF = A.notify_lat)。 */
    uint32_t T = A.depth * A.B, T0 = T, esc = 0, last_u = 0;
    const uint32_t Tmax = c->ring_frames - 2 * A.B;
    double quiet_t0 = emscripten_get_now();
    while (!A.stop) {
        uint32_t burst = LD(c->burst_obs);
        uint32_t need = (uint32_t)(((uint64_t)burst * FLA_BURST_PCT / 100 + A.B + A.B - 1) / A.B * A.B);
        uint32_t u = LD(c->underruns);
        double now = emscripten_get_now();
        if (u != last_u) { esc += A.B; last_u = u; quiet_t0 = now; }
        else if (esc > 0 && now - quiet_t0 >= FLASIO_SHRINK_STABLE_MS) { esc -= A.B; quiet_t0 = now; }
        uint32_t Tn = (need > T0 ? need : T0) + esc;
        if (Tn > Tmax) Tn = Tmax;
        if (Tn != T) {
            if (Tn < T) A.shrinks++; else A.grows++;
            T = Tn; A.depth = T / A.B; A.T = T;
            if (T > A.T_max) A.T_max = T;
            c->depth = T / A.B; A.latency_changes++;
            if (A.notify_lat && A.cb.asioMessage) A.cb.asioMessage(kAsioLatenciesChanged, 0, NULL, NULL);
        }
        int rc = fla_out_wait_fill_le(T - A.B, 50);
        uint32_t ev = __atomic_exchange_n(&c->dev_events, 0, __ATOMIC_SEQ_CST);
        if (ev & (FLA_EV_CLOSED | FLA_EV_SUSPENDED | FLA_EV_RATE_CHANGED | FLA_EV_INPUT_CHANGED)) {
            A.reset_requests++;
            if (A.cb.asioMessage) A.cb.asioMessage(kAsioResetRequest, 0, NULL, NULL);
        }
        if (rc < 0) break;
        if (rc == 1) continue;
        double tw = fla_now_ms();
        uint32_t fill = fla_out_fill();
        if (fill < c->min_fill) c->min_fill = fill;
        c->fill_sum_lo += fill; c->fill_samples++;
        if (fill < FLA_QUANTUM) c->cb_late++;
        uint32_t w0 = c->out_write, k = (c->pw_n % FLA_PW_N) * 4;
        double tl_wake = fla_now_ms();
        do_buffer(idx); idx ^= 1;
        double td = fla_now_ms();
        if (g_tl_n < FLASIO_TL_N) {
            double *r2 = g_tl2[g_tl_n];
            r2[0] = g_cb_tb; r2[1] = g_cb_t0; r2[2] = g_cb1;
            double *r = g_tl[g_tl_n++];
            r[0] = (double)LD(c->notify_ms); r[1] = fill; r[2] = LD(c->underruns);
            r[3] = tl_wake; r[4] = g_cb0; r[5] = g_cb1; r[6] = td;
        }
        c->pw_trace[k] = w0; c->pw_trace[k + 1] = fill;
        c->pw_trace[k + 2] = (uint32_t)(uint64_t)(tw * 1000.0); c->pw_trace[k + 3] = (uint32_t)(uint64_t)(td * 1000.0);
        c->pw_n++;
    }
    return NULL;
}

ASIOError flasio_start(void) {
    need_init("flasio_start");
    if (!A.created) return ASE_InvalidMode;
    if (A.running) return ASE_OK;
    fla_halt();
    fla_reset_indexes();
    A.stop = 0; A.ready = 0;
    g_tl_n = 0;
    A.grows = 0; A.shrinks = 0; A.T0 = A.T_max = A.depth * A.B;
    if (pthread_create(&A.th, NULL, thread_fn, NULL) != 0) return ASE_HWMalfunction;
    while (!__atomic_load_n(&A.ready, __ATOMIC_SEQ_CST))
        __builtin_wasm_memory_atomic_wait32((int *)&A.ready, 0, 50 * 1000000LL);
    A.running = 1;
    return ASE_OK;
}

ASIOError flasio_stop(void) {
    need_init("flasio_stop");
    if (!A.running) return ASE_OK;
    A.stop = 1;
    wake32(&fla_ctl()->out_read);
    pthread_join(A.th, NULL);
    fla_halt();
    A.running = 0;
    return ASE_OK;
}

ASIOError flasio_dispose_buffers(void) {
    need_init("flasio_dispose_buffers");
    flasio_stop();
    if (!A.created) return ASE_InvalidMode;
    fla_close();
    for (int b = 0; b < 2; b++) {
        for (int ch = 0; ch < A.nOut; ch++) { free(A.obuf[b][ch]); A.obuf[b][ch] = NULL; }
        for (int ch = 0; ch < A.nIn; ch++) { free(A.ibuf[b][ch]); A.ibuf[b][ch] = NULL; }
    }
    A.created = 0;
    return ASE_OK;
}

ASIOError flasio_get_sample_position(ASIOSamples *sPos, ASIOSamples *tStamp) {
    need_init("flasio_get_sample_position");
    if (!A.running) return ASE_SPNotAdvancing;
    fla_clock_t k;
    fla_clock_read(&k);
    uint64_t pos = k.pos_frames > k.play_start ? k.pos_frames - k.play_start : 0;
    sPos->hi = (uint32_t)(pos >> 32); sPos->lo = (uint32_t)pos;
    uint64_t st = systime_ns(&k);
    tStamp->hi = (uint32_t)(st >> 32); tStamp->lo = (uint32_t)st;
    return ASE_OK;
}

ASIOError flasio_output_ready(void) { need_init("flasio_output_ready"); return ASE_NotPresent; }  /* ILWASAPI 実測: 0xfffffc18 */
/* FL の asiopanelbtn → controlPanel。ASIO ドライバ同様 UI を開いて即返す。UI 未登録なら ASE_NotPresent
 * (FL 側は 'Could not open ASIO control panel' を出す経路) */
ASIOError flasio_control_panel(void) {
    need_init("flasio_control_panel");
    return fla_cmd(FLA_CMD_CONTROL_PANEL, 0, 0, 0, 0, NULL, 5000) == 0 ? ASE_OK : ASE_NotPresent;
}
ASIOError flasio_future(ASIOLong selector, void *opt) { (void)selector; (void)opt; need_init("flasio_future"); return ASE_InvalidParameter; }

void flasio_get_stats(flasio_stats_t *s) {
    fla_ctl_t *c = fla_ctl();
    memset(s, 0, sizeof *s);
    s->cb_count = c->cb_count; s->cb_late = c->cb_late; s->cb_max_us = c->cb_max_us;
    s->cb_avg_us = c->cb_count ? c->cb_sum_us_lo / c->cb_count : 0;
    s->underruns = LD(c->underruns); s->silence_frames = LD(c->silence_frames); s->in_overruns = LD(c->in_overruns);
    s->in_underflows = c->in_underflows;
    s->min_fill = c->min_fill; s->avg_fill = c->fill_sum_lo ? c->fill_sum_lo / (c->fill_samples ? c->fill_samples : 1) : 0;
    s->wake_count = c->wake_count; s->wait_timeouts = c->wait_timeouts;
    s->buffer_frames = A.B; s->depth = A.depth; s->ring_frames = c->ring_frames; s->quanta = LD(c->quanta);
    s->reset_requests = A.reset_requests;
    s->timeinfo_cb = A.timeinfo_cb; s->latency_changes = A.latency_changes; s->T = A.depth * A.B; s->burst_obs = LD(c->burst_obs);
    s->grows = A.grows; s->shrinks = A.shrinks; s->T_max = A.T_max; s->T0 = A.T0;
    for (int k = 0; k < 6; k++) s->wake_hist[k] = c->wake_hist[k];
    for (int k = 0; k < 32; k++) s->burst_hist[k] = LD(c->burst_hist[k]);
    for (int k = 0; k < 4; k++) s->seg_max_us[k] = A.seg_max_us[k];
}

