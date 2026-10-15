/* fla_test.c — shim PoC テストプログラム (emcc -pthread, PROXY_TO_PTHREAD=1 で main が worker 上で走る)。
 * 引数: api=asio|wasapi mode=sine|ramp|loop buf=256 depth=2 secs=10 sr=48000 stress=0 work_us=0
 *       hiccup_ms=0 hiccup_every=0 profile=0
 *       DirectSound: api=ds|ds_apicheck|ds_stopresume|ff_ds_excl  ds_fmt=pcm16|f32 ds_mode=poll|notify ds_size=<frames> mode=ramp|ramp16|sine|sine16
 * 結果は g_result (JSON 文字列) + g_done (futex) で main thread JS へ返す。 */
#include "flasio.h"
#include "flwasapi.h"
#include "flds.h"
#include "flaudio.h"
#include <emscripten.h>
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct {
    int asio; int apikind; int mode; /* 0 sine 1 ramp 2 loop */
    uint32_t buf, depth, sr, stress, work_us, hiccup_ms, hiccup_every, hiccup_stop_ms, timeinfo, sr_after, burst_floor, panel;
    uint32_t ds_f32, ds_notify, ds_size;
    double secs;
} P = { .asio = 1, .mode = 0, .buf = 256, .depth = 2, .sr = 48000, .secs = 10, .ds_size = 16384 };

static char g_result[8192];
static uint32_t g_done;
EMSCRIPTEN_KEEPALIVE uint32_t *fla_test_done_ptr(void) { return &g_done; }
EMSCRIPTEN_KEEPALIVE char *fla_test_result_ptr(void) { return g_result; }

static float *g_obuf[2][2], *g_ibuf[2][2];
static uint64_t g_n;           /* producer 側の生成フレーム数 (prefill 含む) */
static volatile int g_stress_stop;
static uint32_t g_cbs_since;
static double g_hiccup_t0;     /* run_asio 開始時刻。hiccup_stop_ms 経過後は hiccup を止める (減衰の検証用) */

static void spin_us(double us) {
    double t0 = emscripten_get_now();
    while ((emscripten_get_now() - t0) * 1000.0 < us) { }
}

static void gen_block(float *o0, float *o1, const float *i0, const float *i1, uint32_t frames) {
    for (uint32_t k = 0; k < frames; k++) {
        uint64_t n = g_n + k;
        if (P.mode == 0) {
            o0[k] = (float)(0.5 * sin(2.0 * M_PI * 440.0 * (double)n / (double)P.sr));
            o1[k] = (float)(0.5 * sin(2.0 * M_PI * 660.0 * (double)n / (double)P.sr));
        } else if (P.mode == 1) {
            o0[k] = (float)((n & 0xFFFFFFu) + 1);
            o1[k] = -(float)((n & 0xFFFFFFu) + 1);
        } else {
            o0[k] = i0 ? i0[k] : 0.f;
            o1[k] = i1 ? i1[k] : 0.f;
        }
    }
    g_n += frames;
}

static void load_sim(void) {
    if (P.work_us) spin_us(P.work_us);
    if (P.hiccup_every && ++g_cbs_since >= P.hiccup_every && (!P.hiccup_stop_ms || emscripten_get_now() - g_hiccup_t0 < P.hiccup_stop_ms)) { g_cbs_since = 0; spin_us(P.hiccup_ms * 1000.0); }
}

static void bufferSwitch(ASIOLong idx, ASIOBool direct) {
    (void)direct;
    gen_block(g_obuf[idx][0], g_obuf[idx][1], g_ibuf[idx][0], g_ibuf[idx][1], P.buf);
    load_sim();
}
static uint32_t g_resets, g_rate_changes;
static int g_panel_code = 1;   /* flasio_control_panel の戻り値 (1 = 未呼出) */
static uint64_t g_ti_last; static uint32_t g_ti_bad, g_ti_n;
/* FLEngine (0xc56ae0, AU-7 #193) は timeInfo.flags の kSystemTimeValid と systemTime だけを読み、ns を 1e6 で割って int32 ms にし
 * timeGetTime() (= shimx の emscripten_get_now() 下位 32bit) と同じ時間軸で扱う。同じ変換で d = systemTime_ms − timeGetTime() を測る。 */
static uint32_t g_st_n, g_st_invalid, g_st_nonmono; static int32_t g_st_dmin = 0x7fffffff, g_st_dmax = -0x7fffffff, g_st_last;
static ASIOTime *bufferSwitchTimeInfo(ASIOTime *t, ASIOLong idx, ASIOBool direct) {
    uint64_t pos = ((uint64_t)t->timeInfo.samplePosition.hi << 32) | t->timeInfo.samplePosition.lo;
    if (g_ti_n && pos < g_ti_last) g_ti_bad++;            /* サンプル位置の単調性 */
    if (t->timeInfo.sampleRate != (double)P.sr) g_ti_bad++;
    if (!(t->timeInfo.flags & kSystemTimeValid)) g_st_invalid++;
    else {
        int64_t ns = (int64_t)(((uint64_t)t->timeInfo.systemTime.hi << 32) | t->timeInfo.systemTime.lo);
        int32_t ms = (int32_t)(ns / 1000000);
        int32_t d = (int32_t)((uint32_t)ms - (uint32_t)(uint64_t)emscripten_get_now());
        if (d < g_st_dmin) g_st_dmin = d;
        if (d > g_st_dmax) g_st_dmax = d;
        if (g_st_n && (int32_t)((uint32_t)ms - (uint32_t)g_st_last) < 0) g_st_nonmono++;
        g_st_last = ms; g_st_n++;
    }
    g_ti_last = pos; g_ti_n++;
    bufferSwitch(idx, direct);
    return NULL;
}
static void sampleRateDidChange(double r) { (void)r; g_rate_changes++; }
static ASIOLong asioMessage(ASIOLong sel, ASIOLong val, void *msg, double *opt) {
    (void)msg; (void)opt;
    switch (sel) {
    case kAsioSelectorSupported: return (val >= 2 && val <= 6) || (P.timeinfo && val == kAsioSupportsTimeInfo) ? 1 : 0;
    case kAsioSupportsTimeInfo: return P.timeinfo ? 1 : 0;
    case kAsioEngineVersion: return 2;
    case kAsioResetRequest: g_resets++; return 1;
    default: return 0;
    }
}

static void *stress_fn(void *a) { (void)a; volatile uint64_t x = 0; while (!g_stress_stop) x++; return NULL; }

static void wait_ms(double ms) {
    static uint32_t dummy;
    __builtin_wasm_memory_atomic_wait32((int *)&dummy, 0, (int64_t)(ms * 1e6));
}

typedef struct { double pos, ns, now_ms; } pos_sample_t;

static int fit_rate(const pos_sample_t *s, int n, double *rate, double *offs_ms, double *rate_resid_ppm) {
    if (n < 4) return -1;
    double sx = 0, sy = 0, sxx = 0, sxy = 0;
    const double x0 = s[0].ns * 1e-9, y0 = s[0].pos;
    for (int i = 0; i < n; i++) { double x = s[i].ns * 1e-9 - x0, y = s[i].pos - y0; sx += x; sy += y; sxx += x * x; sxy += x * y; }
    double d = n * sxx - sx * sx;
    if (d == 0) return -1;
    *rate = (n * sxy - sx * sy) / d;
    double mean_off = 0;
    for (int i = 0; i < n; i++) mean_off += s[i].ns * 1e-6 - s[i].now_ms;
    *offs_ms = mean_off / n;
    *rate_resid_ppm = 0;
    return 0;
}

static int run_asio(char *j, size_t jn) {
    ASIOLong nin, nout, mn, mx, pref, gran;
    char name[32];
    flasio_init(NULL);
    flasio_get_driver_name(name);
    flasio_get_channels(&nin, &nout);
    flasio_get_buffer_size(&mn, &mx, &pref, &gran);
    if (flasio_can_sample_rate((double)P.sr) != ASE_OK) { snprintf(j, jn, "{\"error\":\"canSampleRate\"}"); return 1; }
    if (P.sr != 48000 && flasio_set_sample_rate((double)P.sr) != ASE_OK) { snprintf(j, jn, "{\"error\":\"setSampleRate\"}"); return 1; }
    flasio_configure(P.depth, 0);
    fla_test_set_burst_floor(P.burst_floor);
    ASIOBufferInfo infos[4]; int n = 0;
    for (int c = 0; c < 2; c++) { infos[n].isInput = 0; infos[n].channelNum = c; n++; }
    if (P.mode == 2) for (int c = 0; c < 2; c++) { infos[n].isInput = 1; infos[n].channelNum = c; n++; }
    ASIOCallbacks cb = { bufferSwitch, sampleRateDidChange, asioMessage, P.timeinfo ? bufferSwitchTimeInfo : NULL };
    ASIOError e = flasio_create_buffers(infos, n, (ASIOLong)P.buf, &cb);
    if (e != ASE_OK) { snprintf(j, jn, "{\"error\":\"createBuffers\",\"code\":%d}", e); return 1; }
    for (int i = 0; i < n; i++)
        for (int b = 0; b < 2; b++) (infos[i].isInput ? g_ibuf : g_obuf)[b][infos[i].channelNum] = infos[i].buffers[b];
    if (P.panel) g_panel_code = flasio_control_panel();   /* FL の asiopanelbtn 相当 */
    if (P.sr_after) {   /* CreateBuffers 後・Start 前の SetSampleRate → main が AudioContext を再生成 */
        if (flasio_set_sample_rate((double)P.sr_after) != ASE_OK) { snprintf(j, jn, "{\"error\":\"setSampleRate_after\"}"); return 1; }
        P.sr = P.sr_after;
    }
    ASIOLong lin, lout;
    flasio_get_latencies(&lin, &lout);
    const ASIOLong lout0 = lout; const uint32_t olat_us0 = fla_ctl()->out_latency_us;   /* FL が createBuffers 直後に読む値 (0xc58348) */
    ASIOChannelInfo ci = { .channel = 0, .isInput = 0 };
    flasio_get_channel_info(&ci);
    for (uint32_t k = 0; k < P.stress; k++) { pthread_t t; pthread_create(&t, NULL, stress_fn, NULL); pthread_detach(t); }
    if (flasio_start() != ASE_OK) { snprintf(j, jn, "{\"error\":\"start\"}"); return 1; }
    double t0 = emscripten_get_now();
    g_hiccup_t0 = t0;
    pos_sample_t smp[256]; int ns = 0;
    int mono = 1; double lastpos = -1;
    while (emscripten_get_now() - t0 < P.secs * 1000.0) {
        wait_ms(250);
        ASIOSamples sp, ts;
        if (flasio_get_sample_position(&sp, &ts) == ASE_OK && ns < 256) {
            double pos = (double)(((uint64_t)sp.hi << 32) | sp.lo);
            (void)ts;
            fla_clock_t k; fla_clock_read(&k);     /* 「聴こえる時刻」の写像は ASIO systemTime の意味 (コールバック時刻) とは独立に直接測る */
            if (k.audible_ns) { smp[ns].pos = pos; smp[ns].ns = (double)k.audible_ns; smp[ns].now_ms = fla_now_ms(); ns++; }
            if (pos < lastpos) mono = 0;
            lastpos = pos;
        }
    }
    double elapsed = emscripten_get_now() - t0;
    flasio_stats_t st;
    flasio_get_stats(&st);
    char hb[32 * 12];
    for (size_t n = 0, k = 0; k < 32; k++) n += (size_t)snprintf(hb + n, sizeof hb - n, "%s%u", k ? "," : "", st.burst_hist[k]);
    flasio_get_latencies(&lin, &lout);
    flasio_stop();
    double rate = 0, offs = 0, rr = 0;
    int fit = fit_rate(smp, ns, &rate, &offs, &rr);
    flasio_dispose_buffers();
    g_stress_stop = 1;
    snprintf(j, jn,
        "{\"api\":\"asio\",\"driver\":\"%s\",\"buf\":%u,\"depth\":%u,\"sr\":%u,\"mode\":%d,\"secs_wall\":%.3f,"
        "\"reported\":{\"nin\":%d,\"nout\":%d,\"min\":%d,\"max\":%d,\"pref\":%d,\"gran\":%d,\"lat_in\":%d,\"lat_out\":%d,\"lat_out0\":%d,\"olat_us0\":%u,\"ch_type\":%d},"
        "\"stats\":{\"cb_count\":%u,\"cb_late\":%u,\"cb_max_us\":%u,\"cb_avg_us\":%u,\"underruns\":%u,\"silence_frames\":%u,"
        "\"in_overruns\":%u,\"in_underflows\":%u,\"min_fill\":%u,\"avg_fill\":%u,\"wake_count\":%u,\"wait_timeouts\":%u,"
        "\"ring_frames\":%u,\"quanta\":%u,\"reset_requests\":%u,\"wake_hist\":[%u,%u,%u,%u,%u,%u],\"latency_changes\":%u,\"T\":%u,\"burst_obs\":%u,\"timeinfo_cb\":%u,\"grows\":%u,\"shrinks\":%u,\"T_max\":%u,\"T0\":%u,\"burst_hist\":[%s]},\"timeinfo\":{\"calls\":%u,\"bad\":%u,\"st_n\":%u,\"st_invalid\":%u,\"st_nonmono\":%u,\"st_dmin\":%d,\"st_dmax\":%d},"
        "\"clock\":{\"samples\":%d,\"fit_ok\":%d,\"rate_hz\":%.3f,\"audible_minus_now_ms\":%.3f,\"monotonic\":%d},"
        "\"produced_frames\":%llu,\"resets_seen\":%u,\"rate_changes\":%u,\"panel_code\":%d}",
        name, P.buf, st.depth, P.sr, P.mode, elapsed / 1000.0,
        nin, nout, mn, mx, pref, gran, lin, lout, lout0, olat_us0, ci.type,
        st.cb_count, st.cb_late, st.cb_max_us, st.cb_avg_us, st.underruns, st.silence_frames,
        st.in_overruns, st.in_underflows, st.min_fill, st.avg_fill, st.wake_count, st.wait_timeouts,
        st.ring_frames, st.quanta, st.reset_requests,
        st.wake_hist[0], st.wake_hist[1], st.wake_hist[2], st.wake_hist[3], st.wake_hist[4], st.wake_hist[5], st.latency_changes, st.T, st.burst_obs, st.timeinfo_cb, st.grows, st.shrinks, st.T_max, st.T0, hb, g_ti_n, g_ti_bad,
        g_st_n, g_st_invalid, g_st_nonmono, g_st_n ? g_st_dmin : 0, g_st_n ? g_st_dmax : 0,
        ns, fit == 0, rate, offs, mono, (unsigned long long)g_n, g_resets, g_rate_changes, g_panel_code);
    return 0;
}

static int run_wasapi(char *j, size_t jn) {
    flwasapi_fmt_t f; int64_t defp, minp;
    flwasapi_get_mix_format(&f);
    f.sample_rate = P.sr;
    flwasapi_get_device_period(&defp, &minp);
    int64_t period_hns = (int64_t)P.buf * 10000000LL / P.sr;
    FLHR hr = flwasapi_initialize(FL_AUDCLNT_SHAREMODE_SHARED, FL_AUDCLNT_STREAMFLAGS_EVENTCALLBACK,
                                  period_hns * P.depth, period_hns, &f);
    if (hr != FL_S_OK) { snprintf(j, jn, "{\"error\":\"initialize\",\"hr\":%d}", hr); return 1; }
    uint32_t bufsize; int64_t lat;
    flwasapi_get_buffer_size(&bufsize);
    flwasapi_get_stream_latency(&lat);
    flwasapi_set_event_handle(1);
    for (uint32_t k = 0; k < P.stress; k++) { pthread_t t; pthread_create(&t, NULL, stress_fn, NULL); pthread_detach(t); }
    /* prime: 全バッファを埋める */
    float *data; float *o0 = malloc(bufsize * sizeof(float)), *o1 = malloc(bufsize * sizeof(float));
    uint32_t calls = 0, polls = 0, timeouts = 0;
    gen_block(o0, o1, NULL, NULL, bufsize);
    flwasapi_render_get_buffer(bufsize, &data);
    for (uint32_t i = 0; i < bufsize; i++) { data[2 * i] = o0[i]; data[2 * i + 1] = o1[i]; }
    flwasapi_render_release_buffer(bufsize, 0);
    flwasapi_start();
    double t0 = emscripten_get_now();
    double maxcb = 0, sumcb = 0;
    while (emscripten_get_now() - t0 < P.secs * 1000.0) {
        if (flwasapi_wait_event(100) != FL_WAIT_OBJECT_0) { timeouts++; continue; }
        polls++;
        uint32_t pad; flwasapi_get_current_padding(&pad);
        uint32_t room = bufsize - pad;
        if (room < P.buf) continue;
        uint32_t frames = room / P.buf * P.buf;
        double c0 = emscripten_get_now();
        gen_block(o0, o1, NULL, NULL, frames);
        load_sim();
        if (flwasapi_render_get_buffer(frames, &data) != FL_S_OK) fla_failfast("test", "GetBuffer failed");
        for (uint32_t i = 0; i < frames; i++) { data[2 * i] = o0[i]; data[2 * i + 1] = o1[i]; }
        flwasapi_render_release_buffer(frames, 0);
        double us = (emscripten_get_now() - c0) * 1000.0;
        if (us > maxcb) maxcb = us;
        sumcb += us; calls++;
    }
    double elapsed = emscripten_get_now() - t0;
    fla_ctl_t *c = fla_ctl();
    uint32_t underruns = __atomic_load_n(&c->underruns, __ATOMIC_SEQ_CST), sil = __atomic_load_n(&c->silence_frames, __ATOMIC_SEQ_CST);
    uint32_t quanta = __atomic_load_n(&c->quanta, __ATOMIC_SEQ_CST);
    flwasapi_release();
    g_stress_stop = 1;
    snprintf(j, jn,
        "{\"api\":\"wasapi\",\"buf\":%u,\"depth\":%u,\"sr\":%u,\"mode\":%d,\"secs_wall\":%.3f,"
        "\"reported\":{\"bufsize\":%u,\"stream_latency_hns\":%lld,\"default_period_hns\":%lld,\"min_period_hns\":%lld},"
        "\"stats\":{\"fills\":%u,\"events\":%u,\"event_timeouts\":%u,\"fill_max_us\":%.1f,\"fill_avg_us\":%.1f,"
        "\"underruns\":%u,\"silence_frames\":%u,\"quanta\":%u},\"produced_frames\":%llu}",
        P.buf, P.depth, P.sr, P.mode, elapsed / 1000.0, bufsize, (long long)lat, (long long)defp, (long long)minp,
        calls, polls, timeouts, maxcb, calls ? sumcb / calls : 0.0, underruns, sil, quanta, (unsigned long long)g_n);
    free(o0); free(o1);
    return 0;
}

/* burst 超過 → CreateBuffers エラー返却 (abort しない) と、失敗後の再 CreateBuffers 成功 (CLOSED へ復帰) を確認 */
static int run_nomem(char *j, size_t jn) {
    ASIOCallbacks cb = { bufferSwitch, NULL, NULL, NULL };
    ASIOBufferInfo infos[2] = { { 0, 0, { 0, 0 } }, { 0, 1, { 0, 0 } } };
    flasio_init(NULL);
    fla_test_set_burst_floor(P.burst_floor);
    ASIOError e1 = flasio_create_buffers(infos, 2, (ASIOLong)P.buf, &cb);
    fla_test_set_burst_floor(0);
    ASIOError e2 = flasio_create_buffers(infos, 2, (ASIOLong)P.buf, &cb);
    ASIOError e3 = e2 == ASE_OK ? flasio_dispose_buffers() : -1;
    snprintf(j, jn, "{\"api\":\"nomem\",\"codes\":{\"first\":%d,\"retry\":%d,\"dispose\":%d},\"buf\":%u,\"burst_floor\":%u}", e1, e2, e3, P.buf, P.burst_floor);
    return 0;
}

/* 検証系 API の戻り値確認 (AudioContext を開かない) */
static void cb_dummy(ASIOLong i, ASIOBool d) { (void)i; (void)d; }
static int run_apicheck(char *j, size_t jn) {
    ASIOCallbacks cb = { cb_dummy, NULL, NULL, NULL };
    ASIOBufferInfo bi[1] = { { 0, 0, { 0, 0 } } };
    ASIOBufferInfo bad_ch[1] = { { 0, 5, { 0, 0 } } };
    flasio_init(NULL);
    double sr = 0;
    ASIOSamples sp, ts;
    ASIOChannelInfo ci = { .channel = 7, .isInput = 0 };
    ASIOClockSource cs; ASIOLong ncs = 0;
    snprintf(j, jn,
        "{\"api\":\"apicheck\",\"codes\":{\"createBuffers_100\":%d,\"createBuffers_8192\":%d,\"createBuffers_badch\":%d,\"createBuffers_nullinfo\":%d,"
        "\"setSampleRate_12345\":%d,\"canSampleRate_44100\":%d,\"getSamplePosition_stopped\":%d,\"outputReady\":%d,\"future\":%d,"
        "\"getChannelInfo_ch7\":%d,\"setClockSource_1\":%d,\"getClockSources\":%d,\"clock_n\":%d,\"start_nobuf\":%d,\"getSampleRate\":%d,\"rate\":%d}}",
        flasio_create_buffers(bi, 1, 100, &cb), flasio_create_buffers(bi, 1, 8192, &cb), flasio_create_buffers(bad_ch, 1, 256, &cb),
        flasio_create_buffers(NULL, 1, 256, &cb), flasio_set_sample_rate(12345.0), flasio_can_sample_rate(44100.0),
        flasio_get_sample_position(&sp, &ts), flasio_output_ready(), flasio_future(1, NULL), flasio_get_channel_info(&ci),
        flasio_set_clock_source(1), flasio_get_clock_sources(&cs, &ncs), (int)ncs, flasio_start(), flasio_get_sample_rate(&sr), (int)sr);
    return 0;
}


/* ---- DirectSound shim テスト: FL の呼出手順 (INVENTORY §2 / results/ds_static.txt) を再現するクライアント ----
 * SetCooperativeLevel(PRIORITY) → CreateSoundBuffer(primary) → SetFormat → CreateSoundBuffer(secondary: 0x18000|0x100|0x8) →
 * (notify: SetNotificationPositions 2 点) → 全域 Lock/Unlock でプリフィル → SetCurrentPosition(0) → Play(LOOPING) → 供給ループ。
 * ds_fmt=pcm16 は WAVE_FORMAT_PCM (FL の 0x674e10 組立)、f32 は EXTENSIBLE+IEEE_FLOAT (0x674e50 組立)。 */
static void ds_make_wfx(flds_wfx_t *w, int f32, uint32_t sr) {
    memset(w, 0, sizeof *w);
    w->nChannels = 2; w->nSamplesPerSec = sr;
    if (f32) {
        static const uint8_t sub[16] = { 3, 0, 0, 0, 0, 0, 0x10, 0, 0x80, 0, 0, 0xaa, 0, 0x38, 0x9b, 0x71 };
        w->wFormatTag = FLDS_WAVE_FORMAT_EXTENSIBLE; w->wBitsPerSample = 32; w->cbSize = 22; w->wValidBitsPerSample = 32; w->dwChannelMask = 3;
        memcpy(w->SubFormat, sub, 16);
    } else { w->wFormatTag = FLDS_WAVE_FORMAT_PCM; w->wBitsPerSample = 16; w->cbSize = 0; }
    w->nBlockAlign = (uint16_t)(2 * w->wBitsPerSample / 8);
    w->nAvgBytesPerSec = sr * w->nBlockAlign;
}
static uint64_t g_ds_n;   /* クライアントが生成した総フレーム */
static void ds_gen(uint8_t *dst, uint32_t frames, int f32) {
    for (uint32_t k = 0; k < frames; k++) {
        uint64_t n = g_ds_n + k;
        if (f32) {
            float *o = (float *)(dst + (size_t)k * 8);
            if (P.mode == 0) { o[0] = (float)(0.5 * sin(2.0 * M_PI * 440.0 * (double)n / (double)P.sr)); o[1] = (float)(0.5 * sin(2.0 * M_PI * 660.0 * (double)n / (double)P.sr)); }
            else { o[0] = (float)((n & 0xFFFFFFu) + 1); o[1] = -o[0]; }
        } else {
            int16_t *o = (int16_t *)(dst + (size_t)k * 4);
            o[0] = (int16_t)(n % 30000 + 1); o[1] = (int16_t)-o[0];   /* page.mjs の ramp16 期待値と同じ式 */
        }
    }
    g_ds_n += frames;
}
static int ds_write(uint32_t off_bytes, uint32_t bytes, int f32, uint32_t blk) {
    void *p1, *p2; uint32_t n1, n2;
    FLDSHR hr = flds_buf_lock(off_bytes, bytes, &p1, &n1, &p2, &n2, 0);
    if (hr != FLDS_OK) return -1;
    ds_gen((uint8_t *)p1, n1 / blk, f32);
    if (p2 && n2) ds_gen((uint8_t *)p2, n2 / blk, f32);
    return flds_buf_unlock(p1, n1, p2, n2) == FLDS_OK ? 0 : -2;
}
/* FL と同じ前処理。secondary を作り、プリフィルまで行う。失敗時 FLDSHR のステップ番号を負で返す */
static int ds_setup(int f32, uint32_t size_frames, int notify, flds_wfx_t *wfx, uint32_t *size_bytes) {
    flds_configure(P.buf, P.depth);
    uint32_t blk = f32 ? 8 : 4;
    ds_make_wfx(wfx, f32, P.sr);
    flds_bufdesc_t pd = { 20, FLDSBCAPS_PRIMARYBUFFER, 0, 0, NULL };
    uint32_t fl = 0x18000u | 0x8u | (notify ? FLDSBCAPS_CTRLPOSITIONNOTIFY : 0);
    flds_bufdesc_t sd = { 20, fl, size_frames * blk, 0, wfx };
    if (flds_create() != FLDS_OK) return -1;
    if (flds_set_cooperative_level(FLDSSCL_PRIORITY) != FLDS_OK) return -2;
    if (flds_create_sound_buffer(&pd) != FLDS_OK) return -3;
    if (flds_primary_set_format(wfx) != FLDS_OK) return -4;
    if (flds_create_sound_buffer(&sd) != FLDS_OK) return -5;
    *size_bytes = size_frames * blk;
    if (notify) {
        flds_notify_pos_t np[2] = { { 0, 0 }, { *size_bytes / 2, 1 } };
        if (flds_notify_set_positions(2, np) != FLDS_OK) return -6;
    }
    if (ds_write(0, *size_bytes, f32, blk) != 0) return -7;
    if (flds_buf_set_current_position(0) != FLDS_OK) return -8;
    return 0;
}

static int run_ds(char *j, size_t jn) {
    const int f32 = P.ds_f32, notify = P.ds_notify;
    const uint32_t S = P.ds_size, blk = f32 ? 8 : 4, half = S / 2;
    flds_wfx_t wfx; uint32_t sb = 0;
    int st = ds_setup(f32, S, notify, &wfx, &sb);
    if (st) { snprintf(j, jn, "{\"error\":\"ds_setup\",\"step\":%d}", st); return 1; }
    for (uint32_t k = 0; k < P.stress; k++) { pthread_t t; pthread_create(&t, NULL, stress_fn, NULL); pthread_detach(t); }
    flds_wfx_t got; flds_primary_get_format(&got);
    if (flds_buf_play(0, 0, FLDSBPLAY_LOOPING) != FLDS_OK) { snprintf(j, jn, "{\"error\":\"play\"}"); return 1; }
    double t0 = emscripten_get_now();
    uint64_t filled = S;            /* クライアントが書いた総フレーム (プリフィル済み = S) */
    uint64_t played = 0; uint32_t last_p = 0;
    uint32_t polls = 0, notifies = 0, fills = 0, back = 0;
    uint32_t ahead_min = 0xffffffffu, ahead_max = 0, wrapped = 0, misses = 0, order_bad = 0;
    uint32_t next_half = 0;         /* notify: 次に補充する半面 (0/1)。初回は S/2 を通過した時 = 半面 0 */
    while (emscripten_get_now() - t0 < P.secs * 1000.0) {
        uint32_t pb, wb;
        if (notify) {
            uint32_t mask = 0;
            int rc = flds_wait_notify(100, &mask);
            if (rc != 0) { if (rc == 1) misses++; continue; }
            notifies++;
            if (flds_buf_get_current_position(&pb, &wb) != FLDS_OK) fla_failfast("test", "GetCurrentPosition failed");
            /* 通知 1 回 = 半面 1 個を再生し終えた。合体 (複数 bit) は fill_half を複数回呼ぶ */
            /* bit1 (offset S/2 を通過) → 半面 0 が再生済み、bit0 (offset 0 を通過) → 半面 1 が再生済み。
             * 通知は再生順に交互にしか来ないので、単独 bit は期待する半面と一致しなければならない (順序違反の検出)。合体 (2 bit) は 2 面分補充 */
            uint32_t nb = (uint32_t)__builtin_popcount(mask);
            if (nb == 1 && (mask == 2u ? 0u : 1u) != next_half) order_bad++;
            for (uint32_t b = 0; b < nb; b++) {
                if (ds_write(next_half * half * blk, half * blk, f32, blk) != 0) fla_failfast("test", "Lock/Unlock failed");
                filled += half; fills++; next_half ^= 1;
            }
            load_sim();
        } else {
            wait_ms(1);
            polls++;
            if (flds_buf_get_current_position(&pb, &wb) != FLDS_OK) fla_failfast("test", "GetCurrentPosition failed");
            uint32_t pf = pb / blk;
            uint32_t d = (pf + S - last_p) % S;
            if (d > S / 2) back++; else { if (pf < last_p) wrapped++; played += d; }
            last_p = pf;
            if (filled - played < S / 2) {   /* 先行量が半分を切ったら S/4 を補充 (連続領域を Lock) */
                uint32_t k = S / 4;
                if (ds_write((uint32_t)(filled % S) * blk, k * blk, f32, blk) != 0) fla_failfast("test", "Lock/Unlock failed");
                filled += k; fills++;
            }
            load_sim();
        }
        uint32_t pf = pb / blk, wf = wb / blk;
        uint32_t ahead = (wf + S - pf) % S;   /* write cursor が play cursor から何フレーム先か */
        if (pb >= sb || wb >= sb || pb % blk || wb % blk) back += 1000;   /* 範囲/整列違反 */
        if (ahead < ahead_min) ahead_min = ahead;
        if (ahead > ahead_max) ahead_max = ahead;
    }
    double elapsed = emscripten_get_now() - t0;
    flds_stats_t s; flds_get_stats(&s);
    fla_ctl_t *c = fla_ctl();
    uint32_t quanta = __atomic_load_n(&c->quanta, __ATOMIC_SEQ_CST);
    flds_release();
    g_stress_stop = 1;
    snprintf(j, jn,
        "{\"api\":\"ds\",\"fmt\":\"%s\",\"notify\":%d,\"buf\":%u,\"depth\":%u,\"sr\":%u,\"mode\":%d,\"secs_wall\":%.3f,"
        "\"reported\":{\"size_frames\":%u,\"primary_tag\":%u,\"primary_bits\":%u},"
        "\"stats\":{\"underruns\":%u,\"silence_frames\":%u,\"quanta\":%u,\"T\":%u,\"ring_frames\":%u,\"latency_changes\":%u,"
        "\"polls\":%u,\"notifies\":%u,\"notify_timeouts\":%u,\"notify_order_bad\":%u,\"fills\":%u,\"unlocked_frames\":%llu},"
        "\"cursor\":{\"backward_or_range_bad\":%u,\"wraps_seen\":%u,\"write_ahead_min\":%u,\"write_ahead_max\":%u},"
        "\"produced_frames\":%llu}",
        f32 ? "f32" : "pcm16", notify, P.buf, s.depth, P.sr, P.mode, elapsed / 1000.0,
        S, got.wFormatTag, got.wBitsPerSample,
        s.underruns, s.silence_frames, quanta, s.T, s.ring_frames, s.latency_changes,
        polls, notifies, misses, order_bad, fills, (unsigned long long)(s.bytes_unlocked / blk),
        back, wrapped, ahead_min, ahead_max, (unsigned long long)g_ds_n);
    return 0;
}

/* Stop → カーソル凍結 → SetCurrentPosition → Play で再開、を検証する */
static int run_ds_stopresume(char *j, size_t jn) {
    const int f32 = P.ds_f32; const uint32_t S = P.ds_size, blk = f32 ? 8 : 4;
    flds_wfx_t wfx; uint32_t sb = 0;
    int st = ds_setup(f32, S, 0, &wfx, &sb);
    if (st) { snprintf(j, jn, "{\"error\":\"ds_setup\",\"step\":%d}", st); return 1; }
    uint32_t pos[8] = {0}, fills = 0;
    uint64_t filled = S, played = 0; uint32_t last_p = 0;
    uint32_t stat_bits = 0, stat_run, stat_stop;
    flds_buf_get_status(&stat_bits);
    uint32_t stat_idle = stat_bits;
    FLDSHR setpos_playing = 0;
    flds_buf_play(0, 0, FLDSBPLAY_LOOPING);
    flds_buf_get_status(&stat_run);
    double t0 = emscripten_get_now();
    while (emscripten_get_now() - t0 < P.secs * 400.0) {
        wait_ms(1);
        uint32_t pb; flds_buf_get_current_position(&pb, NULL);
        uint32_t pf = pb / blk, d = (pf + S - last_p) % S; played += d; last_p = pf;
        if (filled - played < S / 2) { uint32_t k = S / 4; ds_write((uint32_t)(filled % S) * blk, k * blk, f32, blk); filled += k; fills++; }
    }
    setpos_playing = flds_buf_set_current_position(0);          /* 再生中は INVALIDCALL */
    flds_buf_stop();
    flds_buf_get_status(&stat_stop);
    flds_buf_get_current_position(&pos[0], NULL);
    wait_ms(400);
    flds_buf_get_current_position(&pos[1], NULL);                /* 停止中は不変 */
    FLDSHR sp = flds_buf_set_current_position(1024 * blk);       /* 停止中は移動可 */
    flds_buf_get_current_position(&pos[2], NULL);
    flds_buf_play(0, 0, FLDSBPLAY_LOOPING);
    wait_ms(400);
    flds_buf_get_current_position(&pos[3], NULL);
    double t1 = emscripten_get_now();
    uint32_t pw = 0;
    while (emscripten_get_now() - t1 < 800) { wait_ms(2); flds_buf_get_current_position(&pw, NULL); }
    pos[4] = pw;
    flds_buf_stop();
    flds_release();
    snprintf(j, jn,
        "{\"api\":\"ds_stopresume\",\"fmt\":\"%s\",\"size_frames\":%u,\"blk\":%u,"
        "\"pos\":[%u,%u,%u,%u,%u],\"set_pos_playing\":%d,\"set_pos_stopped\":%d,\"status\":{\"idle\":%u,\"run\":%u,\"stop\":%u},\"fills\":%u}",
        f32 ? "f32" : "pcm16", S, blk, pos[0], pos[1], pos[2], pos[3], pos[4], setpos_playing, sp, stat_idle, stat_run, stat_stop, fills);
    return 0;
}

static int run_ds_apicheck(char *j, size_t jn) {
    flds_wfx_t w16, w24, wbad;
    ds_make_wfx(&w16, 0, 48000); ds_make_wfx(&w24, 0, 48000); w24.wBitsPerSample = 24; w24.nBlockAlign = 6; w24.nAvgBytesPerSec = 48000 * 6;
    ds_make_wfx(&wbad, 0, 48000); wbad.wFormatTag = 7;
    void *p1, *p2; uint32_t n1, n2;
    int c_lock_nosec = flds_buf_lock(0, 16, &p1, &n1, &p2, &n2, 0);
    int c_create_noinit = flds_set_cooperative_level(FLDSSCL_PRIORITY);
    flds_create();
    flds_bufdesc_t pd = { 20, FLDSBCAPS_PRIMARYBUFFER, 0, 0, NULL };
    int c_setfmt_noprim = flds_primary_set_format(&w16);
    int c_prim = flds_create_sound_buffer(&pd);
    int c_prim_twice = flds_create_sound_buffer(&pd);
    int c_setfmt_nopri = flds_primary_set_format(&w16);       /* NORMAL 協調レベルでは PRIOLEVELNEEDED */
    flds_set_cooperative_level(FLDSSCL_PRIORITY);
    int c_setfmt_bad = flds_primary_set_format(&wbad);
    int c_setfmt_24 = flds_primary_set_format(&w24);
    int c_setfmt_ok = flds_primary_set_format(&w16);
    flds_configure(256, 2);
    flds_bufdesc_t hw = { 20, FLDSBCAPS_LOCHARDWARE, 16384, 0, &w16 };
    int c_hw = flds_create_sound_buffer(&hw);
    flds_bufdesc_t tiny = { 20, 0, 4 * 100, 0, &w16 };
    int c_tiny = flds_create_sound_buffer(&tiny);
    flds_bufdesc_t odd = { 20, 0, 4 * 4096 + 2, 0, &w16 };
    int c_odd = flds_create_sound_buffer(&odd);
    flds_bufdesc_t nof = { 20, 0, 4 * 4096, 0, NULL };
    int c_nofmt = flds_create_sound_buffer(&nof);
    flds_bufdesc_t ok = { 20, 0x18000u | FLDSBCAPS_LOCSOFTWARE, 4 * 16384, 0, &w16 };
    int c_sec = flds_create_sound_buffer(&ok);
    int c_sec_twice = flds_create_sound_buffer(&ok);
    flds_notify_pos_t np[1] = { { 0, 0 } };
    int c_notify_nocaps = flds_notify_set_positions(1, np);
    int c_lock_wrap = flds_buf_lock(4 * 16384 - 4, 16, &p1, &n1, &p2, &n2, 0);
    uint32_t wrap_n1 = n1, wrap_n2 = n2; int wrap_p2_is_base = 0;
    uint8_t *base1 = (uint8_t *)p1 - (4 * 16384 - 4);
    wrap_p2_is_base = p2 == (void *)base1;
    int c_lock_twice = flds_buf_lock(0, 16, &p1, &n1, &p2, &n2, 0);      /* lock 中の再 Lock → INVALIDCALL */
    int c_unlock_bad = flds_buf_unlock((uint8_t *)base1 + 8, 4, NULL, 0);  /* lock 区間と一致しない → INVALIDPARAM */
    int c_unlock_ok = flds_buf_unlock((uint8_t *)base1 + (4 * 16384 - 4), 4, base1, 12);
    int c_unlock_again = flds_buf_unlock((uint8_t *)base1 + (4 * 16384 - 4), 4, base1, 12);
    int c_lock_oob = flds_buf_lock(4 * 16384, 4, &p1, &n1, &p2, &n2, 0);
    int c_lock_entire = flds_buf_lock(77, 3, &p1, &n1, &p2, &n2, FLDSBLOCK_ENTIREBUFFER);
    uint32_t ent_n1 = n1; flds_buf_unlock(p1, n1, p2, n2);
    int c_setpos_unaligned = flds_buf_set_current_position(2);
    int c_setpos_oob = flds_buf_set_current_position(4 * 16384);
    int c_setpos_ok = flds_buf_set_current_position(4096);
    uint32_t play = 0, write = 0;
    int c_getpos = flds_buf_get_current_position(&play, &write);
    int c_getpos_null = flds_buf_get_current_position(NULL, NULL);
    uint32_t status = 99; flds_buf_get_status(&status);
    int c_stop_idle = flds_buf_stop();
    flds_release();
    int c_after_release = flds_buf_get_current_position(&play, &write);
    snprintf(j, jn,
        "{\"api\":\"ds_apicheck\",\"codes\":{\"lock_nosec\":%d,\"coop_noinit\":%d,\"setfmt_noprim\":%d,\"prim\":%d,\"prim_twice\":%d,\"setfmt_nopri\":%d,\"setfmt_bad\":%d,\"setfmt_24\":%d,\"setfmt_ok\":%d,"
        "\"hw\":%d,\"tiny\":%d,\"odd\":%d,\"nofmt\":%d,\"sec\":%d,\"sec_twice\":%d,\"notify_nocaps\":%d,\"lock_wrap\":%d,\"wrap_n1\":%u,\"wrap_n2\":%u,\"wrap_p2_is_base\":%d,"
        "\"lock_twice\":%d,\"unlock_bad\":%d,\"unlock_ok\":%d,\"unlock_again\":%d,\"lock_oob\":%d,\"lock_entire\":%d,\"ent_n1\":%u,"
        "\"setpos_unaligned\":%d,\"setpos_oob\":%d,\"setpos_ok\":%d,\"getpos\":%d,\"play\":%u,\"write\":%u,\"getpos_null\":%d,\"status\":%u,\"stop_idle\":%d,\"after_release\":%d}}",
        c_lock_nosec, c_create_noinit, c_setfmt_noprim, c_prim, c_prim_twice, c_setfmt_nopri, c_setfmt_bad, c_setfmt_24, c_setfmt_ok,
        c_hw, c_tiny, c_odd, c_nofmt, c_sec, c_sec_twice, c_notify_nocaps, c_lock_wrap, wrap_n1, wrap_n2, wrap_p2_is_base,
        c_lock_twice, c_unlock_bad, c_unlock_ok, c_unlock_again, c_lock_oob, c_lock_entire, ent_n1,
        c_setpos_unaligned, c_setpos_oob, c_setpos_ok, c_getpos, play, write, c_getpos_null, status, c_stop_idle, c_after_release);
    return 0;
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        char *a = argv[i], *v = strchr(a, '=');
        if (!v) continue;
        *v++ = 0;
        if (!strcmp(a, "api")) { P.asio = strcmp(v, "wasapi") != 0; P.apikind = !strcmp(v, "ff_uninit") ? 2 : !strcmp(v, "ff_excl") ? 3 : !strcmp(v, "apicheck") ? 4 : !strcmp(v, "nomem") ? 5 :
            !strcmp(v, "ds") ? 6 : !strcmp(v, "ds_apicheck") ? 7 : !strcmp(v, "ds_stopresume") ? 8 : !strcmp(v, "ff_ds_excl") ? 9 : 0; }
        else if (!strcmp(a, "panel")) P.panel = (uint32_t)atoi(v);
        else if (!strcmp(a, "ds_fmt")) P.ds_f32 = !strcmp(v, "f32");
        else if (!strcmp(a, "ds_mode")) P.ds_notify = !strcmp(v, "notify");
        else if (!strcmp(a, "ds_size")) P.ds_size = (uint32_t)atoi(v);
        else if (!strcmp(a, "burst_floor")) P.burst_floor = (uint32_t)atoi(v);
        else if (!strcmp(a, "mode")) P.mode = !strcmp(v, "ramp") ? 1 : !strcmp(v, "loop") ? 2 : 0;
        else if (!strcmp(a, "buf")) P.buf = (uint32_t)atoi(v);
        else if (!strcmp(a, "depth")) P.depth = (uint32_t)atoi(v);
        else if (!strcmp(a, "secs")) P.secs = atof(v);
        else if (!strcmp(a, "sr")) P.sr = (uint32_t)atoi(v);
        else if (!strcmp(a, "stress")) P.stress = (uint32_t)atoi(v);
        else if (!strcmp(a, "work_us")) P.work_us = (uint32_t)atoi(v);
        else if (!strcmp(a, "hiccup_ms")) P.hiccup_ms = (uint32_t)atoi(v);
        else if (!strcmp(a, "timeinfo")) P.timeinfo = (uint32_t)atoi(v);
        else if (!strcmp(a, "sr_after")) P.sr_after = (uint32_t)atoi(v);
        else if (!strcmp(a, "hiccup_every")) P.hiccup_every = (uint32_t)atoi(v);
        else if (!strcmp(a, "hiccup_stop_ms")) P.hiccup_stop_ms = (uint32_t)atoi(v);
    }
    int rc;
    if (P.apikind == 2) { ASIOLong a, b; flasio_get_channels(&a, &b); rc = 0; }                 /* init 前の呼出 → fail-fast abort */
    else if (P.apikind == 3) { flwasapi_fmt_t f = { 48000, 2 }; flwasapi_initialize(1, 0, 0, 0, &f); rc = 0; }   /* exclusive → fail-fast */
    else if (P.apikind == 4) rc = run_apicheck(g_result, sizeof g_result);
    else if (P.apikind == 5) rc = run_nomem(g_result, sizeof g_result);
    else if (P.apikind == 6) rc = run_ds(g_result, sizeof g_result);
    else if (P.apikind == 7) rc = run_ds_apicheck(g_result, sizeof g_result);
    else if (P.apikind == 8) rc = run_ds_stopresume(g_result, sizeof g_result);
    else if (P.apikind == 9) { flds_create(); flds_set_cooperative_level(FLDSSCL_EXCLUSIVE); rc = 0; }   /* exclusive → fail-fast */
    else rc = P.asio ? run_asio(g_result, sizeof g_result) : run_wasapi(g_result, sizeof g_result);
    __atomic_store_n(&g_done, rc ? 2 : 1, __ATOMIC_SEQ_CST);
    __builtin_wasm_memory_atomic_notify((int *)&g_done, 0x7fffffff);
    return 0;
}
