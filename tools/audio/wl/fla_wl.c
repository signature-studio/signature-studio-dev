/* fla_wl.c — AU-8 (#194): ミキサ代役を Wasm Audio Worklet の process() 内で直接走らせる比較実装 (ring 無し)。
 * 引数 (Module.arguments): mode=sine|ramp|loop buf=256 secs=10 sr=48000 work_us=0 probe=0
 *   buf = ミキサのブロック長 (FL の ASIO バッファ相当, 128 の倍数)。worklet の 128f quantum を buf/128 個集めて 1 回 render する。
 *   work_us = render 1 回あたりの模擬 CPU 負荷 (ring 側 fla_test の work_us と同じ意味: bufferSwitch 1 回 = render 1 ブロック)。
 *   probe=2 : process() 内で memory.atomic.wait32 (timeout 0) を試す (trap すれば abort) (worklet のブロッキング可否)。
 * 結果は g_result (JSON) + g_done。出力/入力は wasm 線形メモリ上のキャプチャ配列 (worklet が書き、page が読む)。 */
#include <emscripten.h>
#include <emscripten/webaudio.h>
#include <emscripten/em_js.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define Q 128
#define CAPN (1u << 20)   /* 1,048,576 frames (48kHz で 21.8 s) */
#define MAXB 4096

static struct { int mode; uint32_t buf, sr, work_us, probe, neg; double secs; } P = { .mode = 0, .buf = 256, .sr = 48000, .secs = 10 };

static float g_cap_out[2][CAPN], g_cap_in[2][CAPN];
EMSCRIPTEN_KEEPALIVE float *fla_wl_cap_out(void) { return &g_cap_out[0][0]; }
EMSCRIPTEN_KEEPALIVE float *fla_wl_cap_in(void) { return &g_cap_in[0][0]; }
EMSCRIPTEN_KEEPALIVE uint32_t fla_wl_capn(void) { return CAPN; }

static float g_in_acc[2][MAXB], g_out_blk[2][MAXB];
static uint32_t g_pos;          /* 現ブロック内のフレーム位置 (0, 128, ...) */
static uint64_t g_n;            /* render 済みフレーム数 (mixer 側) */
static volatile uint32_t g_q;   /* process() 呼出数 (= キャプチャ済み quantum 数) */
static uint32_t g_renders, g_jumps; static int64_t g_jump_frames;
static double g_prev_frame = -1;
static uint32_t g_gap_hist[6]; static double g_prev_ms; static uint32_t g_gap_max;
static double g_iters_per_us;
static int g_calibrated;
static uint32_t g_q0; static double g_t0;
static volatile uint32_t g_sink;
static uint32_t g_done, g_started;
static char g_result[4096];
static volatile int g_probe_wait = -99;
static double g_ctx_sr;

EMSCRIPTEN_KEEPALIVE uint32_t *fla_wl_done_ptr(void) { return &g_done; }
EMSCRIPTEN_KEEPALIVE char *fla_wl_result_ptr(void) { return g_result; }

EM_JS(double, wl_current_frame, (void), { return typeof currentFrame === "undefined" ? -1 : currentFrame; })
EM_JS(double, wl_date_now, (void), { return Date.now(); })

static void spin_iters(double us) {
    uint64_t n = (uint64_t)(us * g_iters_per_us);
    uint32_t x = g_sink;
    for (uint64_t i = 0; i < n; i++) x = x * 1664525u + 1013904223u;
    g_sink = x;
}

/* worklet 内較正: process() が呼ばれる同じスレッド・同じ tier (V8 の tier-up 後) で 1 回あたりの反復数を Date.now (ms) 区間で測る。
 * 3 ラウンド (各 40 回 x 1M iter) の最後を採用。起動時に約 0.3 s の無音区間ができる (キャプチャ開始前)。 */
static void calibrate_in_worklet(void) {
    const uint64_t N = 1000000; const int CALLS = 40;
    for (int round = 0; round < 3; round++) {
        double t0 = wl_date_now();
        uint32_t x = g_sink;
        for (int c = 0; c < CALLS; c++) { for (uint64_t i = 0; i < N; i++) x = x * 1664525u + 1013904223u; g_sink = x; }
        double dt_ms = wl_date_now() - t0;
        if (dt_ms < 1) dt_ms = 1;
        g_iters_per_us = (double)N * CALLS / (dt_ms * 1000.0);
    }
    g_calibrated = 1;
}

static void mixer_render(uint32_t frames) {
    for (uint32_t k = 0; k < frames; k++) {
        uint64_t n = g_n + k;
        if (P.mode == 0) {
            g_out_blk[0][k] = (float)(0.5 * sin(2.0 * M_PI * 440.0 * (double)n / g_ctx_sr));
            g_out_blk[1][k] = (float)(0.5 * sin(2.0 * M_PI * 660.0 * (double)n / g_ctx_sr));
        } else if (P.mode == 1) {
            g_out_blk[0][k] = (float)((n & 0xFFFFFFu) + 1);
            g_out_blk[1][k] = -(float)((n & 0xFFFFFFu) + 1);
        } else {
            g_out_blk[0][k] = g_in_acc[0][k];
            g_out_blk[1][k] = g_in_acc[1][k];
        }
    }
    g_n += frames;
    if (P.work_us) spin_iters((double)P.work_us);
    g_renders++;
}

static bool process(int numInputs, const AudioSampleFrame *inputs, int numOutputs, AudioSampleFrame *outputs, int numParams, const AudioParamFrame *params, void *data) {
    (void)numParams; (void)params; (void)data;
    if (!g_calibrated) {
        if (P.work_us) calibrate_in_worklet(); else g_calibrated = 1;
        for (int c = 0; c < outputs[0].numberOfChannels; c++) memset(outputs[0].data + c * Q, 0, Q * sizeof(float));
        return true;
    }
    const uint32_t q = g_q;
    double fr = wl_current_frame();
    if (g_prev_frame >= 0 && fr != g_prev_frame + Q) { g_jumps++; g_jump_frames += (int64_t)(fr - g_prev_frame - Q); }
    g_prev_frame = fr;
    double now = wl_date_now();
    if (g_prev_ms > 0) {
        double g = now - g_prev_ms;
        g_gap_hist[g < 1 ? 0 : g <= 5 ? 1 : g <= 12 ? 2 : g <= 20 ? 3 : g <= 40 ? 4 : 5]++;
        if ((uint32_t)g > g_gap_max) g_gap_max = (uint32_t)g;
    }
    g_prev_ms = now;
    if (!g_started) { g_started = 1; }

    if (P.probe == 2 && q == 10) {
        int32_t cell = 0;
        g_probe_wait = 100;   /* 到達マーカ: wait32 が trap すればこの値のまま abort/例外で page に出る */
        g_probe_wait = __builtin_wasm_memory_atomic_wait32(&cell, 0, 0);
    }

    const float *in0 = numInputs > 0 && inputs[0].numberOfChannels > 0 ? inputs[0].data : NULL;
    const int inch = numInputs > 0 ? inputs[0].numberOfChannels : 0;
    /* 入力を block 蓄積へ */
    for (int c = 0; c < 2; c++) {
        if (in0 && c < inch) memcpy(&g_in_acc[c][g_pos], in0 + c * Q, Q * sizeof(float));
        else memset(&g_in_acc[c][g_pos], 0, Q * sizeof(float));
    }
    /* 出力: 直前ブロックの render 結果の g_pos 位置 (= 入力は 1 ブロック遅れて出る: ASIO 風 double buffer と同型) */
    float *o = outputs[0].data;
    const int och = outputs[0].numberOfChannels;
    for (int c = 0; c < och; c++) {
        if (c < 2) memcpy(o + c * Q, &g_out_blk[c][g_pos], Q * sizeof(float));
        else memset(o + c * Q, 0, Q * sizeof(float));
    }
    /* キャプチャ (出力は worklet が実際に返した値 / 入力は受けた値) */
    if (q < CAPN / Q) {
        for (int c = 0; c < 2; c++) {
            memcpy(&g_cap_out[c][q * Q], c < och ? o + c * Q : (float[Q]){0}, Q * sizeof(float));
            memcpy(&g_cap_in[c][q * Q], &g_in_acc[c][g_pos], Q * sizeof(float));
        }
    }
    g_q = q + 1;
    g_pos += Q;
    if (g_pos >= P.buf) {   /* ブロック完成 → mixer を 1 回 render (ここが ring 方式の bufferSwitch に相当) */
        mixer_render(P.buf);
        g_pos = 0;
    }
    (void)numOutputs;
    return true;
}

EM_JS(void, attach_noise, (EMSCRIPTEN_WEBAUDIO_T ctxID, EMSCRIPTEN_WEBAUDIO_T nodeID), {
    var ctx = emscriptenGetAudioObject(ctxID), node = emscriptenGetAudioObject(nodeID);
    var n = Math.floor(ctx.sampleRate * 1), b = ctx.createBuffer(2, n, ctx.sampleRate), s = 12345;
    for (var c = 0; c < 2; c++) {
        var d = b.getChannelData(c);
        for (var i = 0; i < n; i++) { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; d[i] = ((s >>> 8) / 8388608 - 1) * 0.5; }
    }
    var src = ctx.createBufferSource(); src.buffer = b; src.loop = true; src.connect(node); src.start();
    Module.__ctxInfo = { sampleRate: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: ctx.outputLatency };
})

EM_JS(void, ctx_info, (EMSCRIPTEN_WEBAUDIO_T ctxID), {
    var ctx = emscriptenGetAudioObject(ctxID);
    Module.__ctxInfo = { sampleRate: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: ctx.outputLatency, state: ctx.state };
})

static EMSCRIPTEN_WEBAUDIO_T g_ctx;
static void finish(void) {
    uint32_t q = g_q;
    double wall_ms = emscripten_get_now() - g_t0;
    double rt_ratio = wall_ms > 0 ? ((double)(q - g_q0) * Q / g_ctx_sr) / (wall_ms / 1000.0) : 0;
    snprintf(g_result, sizeof g_result,
        "{\"api\":\"worklet_direct\",\"mode\":%d,\"buf\":%u,\"sr\":%u,\"work_us\":%u,\"secs\":%.1f,\"covered_frames\":%u,\"quanta\":%u,\"renders\":%u,"
        "\"clock_jumps\":%u,\"clock_jump_frames\":%lld,\"gap_hist\":[%u,%u,%u,%u,%u,%u],\"gap_max_ms\":%u,\"iters_per_us\":%.1f,\"wall_ms\":%.1f,\"rt_ratio\":%.4f,"
        "\"probe\":{\"atomic_wait32\":%d}}",
        P.mode, P.buf, P.sr, P.work_us, P.secs, q * Q > CAPN ? CAPN : q * Q, q, g_renders, g_jumps, (long long)g_jump_frames,
        g_gap_hist[0], g_gap_hist[1], g_gap_hist[2], g_gap_hist[3], g_gap_hist[4], g_gap_hist[5], g_gap_max, g_iters_per_us, wall_ms, rt_ratio,
        g_probe_wait);
    __atomic_store_n(&g_done, 1, __ATOMIC_SEQ_CST);
}

static bool tick(double t, void *d) {
    (void)t; (void)d;
    static double t0;
    if (!t0) { if (g_started) { t0 = emscripten_get_now(); g_t0 = t0; g_q0 = g_q; } return true; }
    if (emscripten_get_now() - t0 >= P.secs * 1000.0) { ctx_info(g_ctx); finish(); return false; }
    return true;
}

static void on_node_ready(EMSCRIPTEN_WEBAUDIO_T ctx, bool ok, void *ud) {
    (void)ud;
    if (!ok) { snprintf(g_result, sizeof g_result, "{\"error\":\"processor create failed\"}"); __atomic_store_n(&g_done, 2, __ATOMIC_SEQ_CST); return; }
    int och[1] = { 2 };
    EmscriptenAudioWorkletNodeCreateOptions o = { .numberOfInputs = P.mode == 2 ? 1 : 0, .numberOfOutputs = 1, .outputChannelCounts = och,
        .channelCount = 2, .channelCountMode = WEBAUDIO_CHANNEL_COUNT_MODE_EXPLICIT };
        EMSCRIPTEN_WEBAUDIO_T node = emscripten_create_wasm_audio_worklet_node(ctx, "fl-wl-mixer", &o, &process, NULL);
    emscripten_audio_node_connect(node, ctx, 0, 0);
    if (P.mode == 2 && !P.neg) attach_noise(ctx, node);
    emscripten_resume_audio_context_sync(ctx);
    ctx_info(ctx);
    emscripten_set_timeout_loop(tick, 50, NULL);
}

static void on_thread_ready(EMSCRIPTEN_WEBAUDIO_T ctx, bool ok, void *ud) {
    (void)ud;
    if (!ok) { snprintf(g_result, sizeof g_result, "{\"error\":\"worklet thread start failed\"}"); __atomic_store_n(&g_done, 2, __ATOMIC_SEQ_CST); return; }
    WebAudioWorkletProcessorCreateOptions po = { .name = "fl-wl-mixer" };
    emscripten_create_wasm_audio_worklet_processor_async(ctx, &po, on_node_ready, NULL);
}

int main(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        char *a = argv[i], *v = strchr(a, '=');
        if (!v) continue;
        *v++ = 0;
        if (!strcmp(a, "mode")) P.mode = !strcmp(v, "ramp") ? 1 : !strcmp(v, "loop") ? 2 : 0;
        else if (!strcmp(a, "buf")) P.buf = (uint32_t)atoi(v);
        else if (!strcmp(a, "secs")) P.secs = atof(v);
        else if (!strcmp(a, "sr")) P.sr = (uint32_t)atoi(v);
        else if (!strcmp(a, "work_us")) P.work_us = (uint32_t)atoi(v);
        else if (!strcmp(a, "neg")) P.neg = (uint32_t)atoi(v);
        else if (!strcmp(a, "probe")) P.probe = (uint32_t)atoi(v);
    }
    if (P.buf < Q || P.buf > MAXB || P.buf % Q) { snprintf(g_result, sizeof g_result, "{\"error\":\"bad buf\"}"); __atomic_store_n(&g_done, 2, __ATOMIC_SEQ_CST); return 0; }
    EmscriptenWebAudioCreateAttributes at = { .latencyHint = "interactive", .sampleRate = P.sr };
    g_ctx = emscripten_create_audio_context(&at);
    g_ctx_sr = (double)emscripten_audio_context_sample_rate(g_ctx);
    void *stack = memalign(16, 65536);
    emscripten_start_wasm_audio_worklet_thread_async(g_ctx, stack, 65536, on_thread_ready, NULL);
    emscripten_exit_with_live_runtime();
    return 0;
}
