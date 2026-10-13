/* flmidi_test.c — MIDI shim テスト wasm (FL 非依存)。emcc -pthread, PROXY_TO_PTHREAD=1。
 * JS (page_midi.mjs) とフェーズ同期 (step) で進む: wasm が g_phase=N を公開 → JS が動作 (モック MIDI 入力の注入等) → g_go=N → 続行。
 * 注入データは決定的: 短メッセージ n = status 0x90|(n&15), d1 = n&0x7f, d2 = (n>>7)&0x7f。SysEx = F0 + (i*7+3)&0x7f 列 + F7。
 * wasm が内容を自分で検算し、結果を checks[] (name, ok, detail) の JSON で返す。判定は harness/midi_run.mjs。 */
#include "flmidi_winmm.h"
#include <emscripten.h>
#include <pthread.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uintptr_t flmidi_last_cb_thread(void);

static char g_result[32768];
static uint32_t g_done, g_phase, g_go;
EMSCRIPTEN_KEEPALIVE uint32_t *fla_midi_test_done_ptr(void) { return &g_done; }
EMSCRIPTEN_KEEPALIVE char *fla_midi_test_result_ptr(void) { return g_result; }
EMSCRIPTEN_KEEPALIVE uint32_t *fla_midi_test_phase_ptr(void) { return &g_phase; }
EMSCRIPTEN_KEEPALIVE uint32_t *fla_midi_test_go_ptr(void) { return &g_go; }

#define LD(x) __atomic_load_n(&(x), __ATOMIC_SEQ_CST)
#define INC(x) __atomic_add_fetch(&(x), 1, __ATOMIC_SEQ_CST)

static struct { char name[48]; int ok; char detail[120]; } C[96];
static int nC;
static void check(const char *name, int ok, const char *fmt, ...) __attribute__((format(printf, 3, 4)));
#include <stdarg.h>
static void check(const char *name, int ok, const char *fmt, ...) {
    if (nC >= 96) return;
    snprintf(C[nC].name, sizeof C[nC].name, "%s", name); C[nC].ok = ok;
    va_list ap; va_start(ap, fmt); vsnprintf(C[nC].detail, sizeof C[nC].detail, fmt, ap); va_end(ap);
    nC++;
}

static void step(uint32_t n) {
    __atomic_store_n(&g_phase, n, __ATOMIC_SEQ_CST);
    __builtin_wasm_memory_atomic_notify((int *)&g_phase, 0x7fffffff);
    double t0 = emscripten_get_now();
    while (LD(g_go) < n) {
        if (emscripten_get_now() - t0 > 30000) { check("phase_timeout", 0, "phase %u", n); return; }
        __builtin_wasm_memory_atomic_wait32((int *)&g_go, (int)LD(g_go), 100 * 1000000LL);
    }
}
static int wait_until(volatile uint32_t *v, uint32_t want, double ms) {
    double t0 = emscripten_get_now();
    while (LD(*v) < want) { if (emscripten_get_now() - t0 > ms) return 0; usleep(2 * 1000); }
    return 1;
}

/* ---- 入力コールバック状態 ---- */
static volatile uint32_t n_open, n_close, n_data, n_long, n_mom_open, n_mom_close, n_mom_done, seq_bad, ts_bad, readd, long_bad, long_zero;
static uint32_t expect_n;
static uint32_t last_ts;
static uintptr_t opener_thread, cb_thread_seen, cb_thread_other;
static FLM_HANDLE g_in_h, g_out_h;
static volatile uint32_t long_ids_seen;
static uint32_t long_expect_len[8]; static uint32_t long_idx;
static uint8_t long_acc[2048]; static uint32_t long_acc_n;
static flm_midihdr_t H[4]; static char HB[4][512];
static flm_midihdr_t HO[3]; static char *HOB[3];
static uint32_t cb_order_bad;

static void in_cb(uintptr_t h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2) {
    uintptr_t me = (uintptr_t)pthread_self();
    if (msg == FLM_MIM_DATA || msg == FLM_MIM_LONGDATA) {   /* MIM_OPEN/CLOSE は API 呼出スレッド上で発火する (winmm 同様)。データ系だけが MIDI スレッド */
        if (!cb_thread_seen) cb_thread_seen = me; else if (cb_thread_seen != me) cb_thread_other = me;
    }
    if (inst != 0xABCD) cb_order_bad++;
    if (h != g_in_h && msg != FLM_MIM_OPEN) cb_order_bad++;
    if (msg == FLM_MIM_OPEN) INC(n_open);
    else if (msg == FLM_MIM_CLOSE) INC(n_close);
    else if (msg == FLM_MIM_DATA) {
        uint32_t m = (uint32_t)p1, st = m & 0xff, d1 = (m >> 8) & 0xff, d2 = (m >> 16) & 0xff;
        uint32_t n = d1 | d2 << 7;
        if (st != (0x90u | (n & 15)) || n != (expect_n & 0x3fff)) { INC(seq_bad); expect_n = n + 1; } else expect_n++;
        if ((uint32_t)p2 < last_ts) INC(ts_bad);
        last_ts = (uint32_t)p2;
        INC(n_data);
    } else if (msg == FLM_MIM_LONGDATA) {
        flm_midihdr_t *hd = (flm_midihdr_t *)p1;
        if (hd->dwBytesRecorded == 0) { INC(long_zero); }
        else {
            if (long_acc_n + hd->dwBytesRecorded <= sizeof long_acc) memcpy(long_acc + long_acc_n, hd->lpData, hd->dwBytesRecorded);
            long_acc_n += hd->dwBytesRecorded;
            if (long_idx < 8 && long_acc_n == long_expect_len[long_idx]) {   /* 1 メッセージ分が揃った: 内容検算 */
                int ok = long_acc[0] == 0xF0 && long_acc[long_acc_n - 1] == 0xF7;
                for (uint32_t i = 1; i + 1 < long_acc_n && ok; i++) if (long_acc[i] != (uint8_t)((i * 7 + 3) & 0x7f)) ok = 0;
                if (!ok) INC(long_bad);
                long_idx++; long_acc_n = 0; INC(long_ids_seen);
            } else if (long_idx < 8 && long_acc_n > long_expect_len[long_idx]) { INC(long_bad); long_acc_n = 0; long_idx++; }
        }
        INC(n_long);
        if (readd && hd->dwBytesRecorded) flm_midiInAddBuffer(h, hd, sizeof *hd);   /* FL と同様にコールバック内で AddBuffer */
    }
}
static void out_cb(uintptr_t h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2) {
    (void)h; (void)p1; (void)p2;
    if (inst != 0xBEEF) cb_order_bad++;
    if (msg == FLM_MOM_OPEN) INC(n_mom_open); else if (msg == FLM_MOM_CLOSE) INC(n_mom_close); else if (msg == FLM_MOM_DONE) INC(n_mom_done);
}

static void u16_to_ascii(const uint16_t *w, char *o, int n) { int i = 0; for (; i < n - 1 && w[i]; i++) o[i] = (char)w[i]; o[i] = 0; }

static void run(void) {
    uint32_t st[16];
    opener_thread = (uintptr_t)pthread_self();
    /* ---- A. 列挙 ---- */
    FLM_UINT ni = flm_midiInGetNumDevs(), no = flm_midiOutGetNumDevs();
    check("numdevs", ni == 2 && no == 2, "in=%u out=%u (want 2/2)", ni, no);
    flm_midiincaps_t ic; memset(&ic, 0xAA, sizeof ic);
    FLM_UINT r = flm_midiInGetDevCapsW(0, &ic, sizeof ic); char nm[40]; u16_to_ascii(ic.szPname, nm, 40);
    check("in_caps_name", r == 0 && !strcmp(nm, "Mock Keyboard"), "r=%u name='%s'", r, nm);
    r = flm_midiInGetDevCapsW(1, &ic, sizeof ic); u16_to_ascii(ic.szPname, nm, 40);
    check("in_caps_longname_trunc31", r == 0 && strlen(nm) == 31 && ic.szPname[31] == 0, "len=%zu (want 31, NUL-terminated)", strlen(nm));
    check("in_caps_badid", flm_midiInGetDevCapsW(2, &ic, sizeof ic) == MM_BADDEVICEID, "id=2 -> BADDEVICEID");
    flm_midioutcaps_t oc; memset(&oc, 0, sizeof oc);
    r = flm_midiOutGetDevCapsW(FLM_MIDI_MAPPER, &oc, sizeof oc); u16_to_ascii(oc.szPname, nm, 40);
    check("out_caps_mapper", r == 0 && !strcmp(nm, "Mock Synth"), "r=%u name='%s'", r, nm);
    {
        FLM_WCHAR tb[64]; memset(tb, 0, sizeof tb);
        FLM_UINT e1 = flm_midiInGetErrorTextW(MM_BADDEVICEID, tb, 64), e2 = flm_midiOutGetErrorTextW(9999, tb, 64), e3 = flm_midiInGetErrorTextW(MIDIERR_STILLPLAYING, tb, 64);
        char t[80]; u16_to_ascii(tb, t, 80);
        check("errtext", e1 == 0 && e2 == MM_BADERRNUM && e3 == 0 && strstr(t, "Still"), "known=%u unknown=%u(want 9) text='%s'", e1, e2, t);
    }
    /* ---- B. midiIn open (CALLBACK_FUNCTION) ---- */
    FLM_HANDLE hh = 0;
    check("in_open_bad_id", flm_midiInOpen(&hh, 7, (uintptr_t)in_cb, 0xABCD, FLM_CALLBACK_FUNCTION) == MM_BADDEVICEID, "id=7");
    check("in_open_cb_null_ptr", flm_midiInOpen(&hh, 0, 0, 0, FLM_CALLBACK_FUNCTION) == MM_INVALPARAM, "CALLBACK_FUNCTION with cb=0");
    check("in_open_window_unsupported", flm_midiInOpen(&hh, 0, 1, 0, 0x10000) == MM_NOTSUPPORTED, "CALLBACK_WINDOW");
    r = flm_midiInOpen(&g_in_h, 0, (uintptr_t)in_cb, 0xABCD, FLM_CALLBACK_FUNCTION);
    check("in_open", r == 0 && g_in_h != 0 && wait_until(&n_open, 1, 2000), "r=%u MIM_OPEN=%u", r, n_open);
    check("in_open_twice_allocated", flm_midiInOpen(&hh, 0, (uintptr_t)in_cb, 0xABCD, FLM_CALLBACK_FUNCTION) == MM_ALLOCATED, "same device");
    for (int i = 0; i < 2; i++) {
        memset(&H[i], 0, sizeof H[i]); H[i].lpData = HB[i]; H[i].dwBufferLength = sizeof HB[i];
        r = flm_midiInPrepareHeader(g_in_h, &H[i], sizeof H[i]);
        if (r) check("in_prepare", 0, "r=%u", r);
    }
    check("in_addbuffer_unprepared", ({ memset(&H[2], 0, sizeof H[2]); H[2].lpData = HB[2]; H[2].dwBufferLength = 512; flm_midiInAddBuffer(g_in_h, &H[2], sizeof H[2]); }) == MIDIERR_UNPREPARED, "unprepared hdr");
    check("in_addbuffer_badhandle", flm_midiInAddBuffer(0x12345, &H[0], sizeof H[0]) == MM_INVALHANDLE, "bad handle");
    r = flm_midiInAddBuffer(g_in_h, &H[0], sizeof H[0]); FLM_UINT r2 = flm_midiInAddBuffer(g_in_h, &H[1], sizeof H[1]);
    check("in_addbuffer", r == 0 && r2 == 0 && (H[0].dwFlags & FLM_MHDR_INQUEUE), "r=%u,%u flags=%x", r, r2, H[0].dwFlags);
    check("in_addbuffer_twice", flm_midiInAddBuffer(g_in_h, &H[0], sizeof H[0]) == MIDIERR_STILLPLAYING, "already queued");
    check("in_unprepare_inqueue", flm_midiInUnprepareHeader(g_in_h, &H[0], sizeof H[0]) == MIDIERR_STILLPLAYING, "inqueue");
    readd = 1;

    /* ---- C. Start 前は捨てる ---- */
    step(1);                                                   /* JS: n=0..9 を注入 (Start 前) */
    usleep(300 * 1000);
    flmidi_get_stats(st);
    check("prestart_dropped", n_data == 0 && st[9] == 10, "callbacks=%u prestart=%u (want 0/10)", n_data, st[9]);
    check("in_start", flm_midiInStart(g_in_h) == 0, "start");
    expect_n = 0; last_ts = 0;
    step(2);                                                   /* JS: n=0..999 (corrupt では 500 を欠落) */
    int got = wait_until(&n_data, 1000, 8000);
    flmidi_get_stats(st);
    check("short_all_delivered", got || n_data >= 999, "callbacks=%u (want 1000)", n_data);
    check("short_seq_ok", seq_bad == 0 && n_data == 1000, "seq_bad=%u callbacks=%u (want 0/1000)", seq_bad, n_data);
    check("short_ts_monotonic", ts_bad == 0, "ts_bad=%u", ts_bad);
    check("cb_thread_not_caller", cb_thread_seen && cb_thread_seen != opener_thread, "cb thread != midiInOpen caller (%s)", cb_thread_seen != opener_thread ? "yes" : "NO");
    check("cb_single_thread", cb_thread_other == 0, "all MIM_DATA/LONGDATA on one MIDI thread (other=%lu)", (unsigned long)cb_thread_other);

    /* ---- D. SysEx (バッファ 512B) ---- */
    long_expect_len[0] = 300; long_expect_len[1] = 1000; long_expect_len[2] = 100; long_expect_len[3] = 100;
    step(3);                                                   /* JS: sysex 300B, 1000B (= 512 + 488 に分割される) */
    wait_until(&long_ids_seen, 2, 5000);
    check("sysex_content", long_ids_seen == 2 && long_bad == 0, "messages=%u bad=%u (want 2/0), LONGDATA calls=%u (want 3)", long_ids_seen, long_bad, n_long);
    check("sysex_split_across_buffers", n_long == 3, "LONGDATA=%u (300B:1 + 1000B:2)", n_long);
    readd = 0;
    step(4);                                                   /* JS: sysex 100B ×3 (空きバッファ 2) → 3 つ目は sx_nobuf */
    wait_until(&long_ids_seen, 4, 5000);
    usleep(200 * 1000);
    flmidi_get_stats(st);
    check("sysex_nobuf_counted", st[7] == 1 && long_ids_seen == 4, "sx_nobuf=%u (want 1) delivered=%u (want 4 total)", st[7], long_ids_seen);
    check("in_close_with_queued", ({ memset(&H[3], 0, sizeof H[3]); H[3].lpData = HB[3]; H[3].dwBufferLength = 512; flm_midiInPrepareHeader(g_in_h, &H[3], sizeof H[3]); flm_midiInAddBuffer(g_in_h, &H[3], sizeof H[3]); flm_midiInClose(g_in_h); }) == MIDIERR_STILLPLAYING, "close with queued buffer");

    /* ---- E. Stop / Reset ---- */
    check("in_stop", flm_midiInStop(g_in_h) == 0, "stop");
    uint32_t before = n_data; flmidi_get_stats(st); uint32_t pre0 = st[9];
    step(5);                                                   /* JS: n=0..4 (Stop 中) */
    usleep(300 * 1000);
    flmidi_get_stats(st);
    check("stopped_dropped", n_data == before && st[9] == pre0 + 5, "callbacks +%u (want 0), prestart +%u (want 5)", n_data - before, st[9] - pre0);
    uint32_t lz = long_zero;
    check("in_reset", flm_midiInReset(g_in_h) == 0 && long_zero == lz + 1, "returned unused buffers via LONGDATA(bytes=0): +%u (want 1)", long_zero - lz);
    check("in_unprepare", flm_midiInUnprepareHeader(g_in_h, &H[3], sizeof H[3]) == 0, "after reset");

    /* ---- F. 入力 ring 溢れ (MIDI スレッド停止中に 5000 通) ---- */
    check("in_restart", flm_midiInStart(g_in_h) == 0, "restart");
    flmidi_get_stats(st); uint32_t acc0 = st[1], drop0 = st[2], d0 = n_data;
    flmidi_test_pause(1);
    expect_n = 0; last_ts = 0;
    step(6);                                                   /* JS: n=0..4999 を一気に注入 */
    flmidi_get_stats(st);
    uint32_t acc = st[1] - acc0, drop = st[2] - drop0;
    check("ring_overflow_counted", acc + drop == 5000 && drop > 0 && acc == 4096, "accepted=%u dropped=%u (sum want 5000, accepted want 4096 = ring 65536B / 16B)", acc, drop);
    flmidi_test_pause(0);
    wait_until(&n_data, d0 + acc, 8000);
    check("ring_overflow_oldest_kept", n_data - d0 == acc && seq_bad == 0, "delivered=%u (want %u) seq_bad=%u (first %u in order)", n_data - d0, acc, seq_bad, acc);

    /* ---- G. close ---- */
    check("in_close", flm_midiInClose(g_in_h) == 0 && wait_until(&n_close, 1, 2000), "MIM_CLOSE=%u", n_close);
    uint32_t after_close = n_data;
    check("in_close_again_invalhandle", flm_midiInClose(g_in_h) == MM_INVALHANDLE, "double close");
    check("in_start_closed_invalhandle", flm_midiInStart(g_in_h) == MM_INVALHANDLE, "closed handle");
    step(7);                                                   /* JS: 閉じた入力ポートのハンドラが外れていること / 注入しても届かないこと */
    usleep(200 * 1000);
    flmidi_get_stats(st);
    check("stale_slot_dropped", st[8] == 3 && n_data == after_close, "in_stale=%u (want 3, injected to closed slot) callbacks after close +%u (want 0)", st[8], n_data - after_close);
    check("cb_order_inst_handle", cb_order_bad == 0, "inst/handle mismatches=%u", cb_order_bad);

    /* ---- H. midiOut ---- */
    check("out_open_bad_id", flm_midiOutOpen(&hh, 9, 0, 0, 0) == MM_BADDEVICEID, "id=9");
    r = flm_midiOutOpen(&g_out_h, FLM_MIDI_MAPPER, (uintptr_t)out_cb, 0xBEEF, FLM_CALLBACK_FUNCTION);
    check("out_open_mapper", r == 0 && wait_until(&n_mom_open, 1, 2000), "r=%u MOM_OPEN=%u", r, n_mom_open);
    int sm_ok = 1;
    for (uint32_t n = 0; n < 100; n++) if (flm_midiOutShortMsg(g_out_h, 0x90u | (n & 15) | (n & 0x7f) << 8 | ((n >> 7) & 0x7f) << 16)) sm_ok = 0;
    check("out_shortmsg_100", sm_ok, "100 messages accepted");
    check("out_shortmsg_badhandle", flm_midiOutShortMsg(0x777, 0x90) == MM_INVALHANDLE, "bad handle");
    for (int i = 0; i < 3; i++) { uint32_t len = i == 0 ? 3000 : i == 1 ? 40000 : 40000; HOB[i] = malloc(len); HO[i].lpData = HOB[i]; HO[i].dwBufferLength = len; HO[i].dwFlags = 0;
        HOB[i][0] = (char)0xF0; for (uint32_t k = 1; k + 1 < len; k++) HOB[i][k] = (char)((k * 7 + 3) & 0x7f); HOB[i][len - 1] = (char)0xF7; }
    check("out_long_unprepared", flm_midiOutLongMsg(g_out_h, &HO[0], sizeof HO[0]) == MIDIERR_UNPREPARED, "unprepared");
    flm_midiOutPrepareHeader(g_out_h, &HO[0], sizeof HO[0]);
    r = flm_midiOutLongMsg(g_out_h, &HO[0], sizeof HO[0]);
    check("out_long_3000", r == 0 && wait_until(&n_mom_done, 1, 3000) && (HO[0].dwFlags & FLM_MHDR_DONE) && !(HO[0].dwFlags & FLM_MHDR_INQUEUE), "r=%u MOM_DONE=%u flags=%x", r, n_mom_done, HO[0].dwFlags);
    check("out_unprepare", flm_midiOutUnprepareHeader(g_out_h, &HO[0], sizeof HO[0]) == 0, "after done");
    /* ring 満杯: JS が出力消費を止めている間に 40000B を 2 本 (ring 65536B) */
    step(8);                                                   /* JS: 出力消費を停止 */
    flm_midiOutPrepareHeader(g_out_h, &HO[1], sizeof HO[1]); flm_midiOutPrepareHeader(g_out_h, &HO[2], sizeof HO[2]);
    FLM_UINT a = flm_midiOutLongMsg(g_out_h, &HO[1], sizeof HO[1]), b = flm_midiOutLongMsg(g_out_h, &HO[2], sizeof HO[2]);
    check("out_ring_full_notready", a == 0 && b == MIDIERR_NOTREADY && !(HO[2].dwFlags & FLM_MHDR_INQUEUE), "first=%u second=%u (want 0/67)", a, b);
    check("out_close_inflight", flm_midiOutClose(g_out_h) == MIDIERR_STILLPLAYING, "close while in flight");
    uint32_t md = n_mom_done;
    step(9);                                                   /* JS: 出力消費を再開 */
    check("out_long_40000_done", wait_until(&n_mom_done, md + 1, 5000), "MOM_DONE +%u", n_mom_done - md);
    flm_midiOutUnprepareHeader(g_out_h, &HO[1], sizeof HO[1]);
    check("out_close", flm_midiOutClose(g_out_h) == 0 && wait_until(&n_mom_close, 1, 2000), "MOM_CLOSE=%u", n_mom_close);
    check("out_shortmsg_after_close", flm_midiOutShortMsg(g_out_h, 0x90) == MM_INVALHANDLE, "closed handle");

    /* ---- I. 再スキャン ---- */
    uint32_t g0 = flmidi_scan_gen();
    step(10);                                                  /* JS: 入力を 1 台追加 + onstatechange */
    int tries = 0; while (flm_midiInGetNumDevs() != 3 && tries++ < 100) usleep(20 * 1000);
    check("hotplug_statechange", flm_midiInGetNumDevs() == 3 && flmidi_scan_gen() > g0, "numdevs=%u scan_gen %u->%u", flm_midiInGetNumDevs(), g0, flmidi_scan_gen());
    flm_midiincaps_t ic3; flm_midiInGetDevCapsW(2, &ic3, sizeof ic3); u16_to_ascii(ic3.szPname, nm, 40);
    check("hotplug_new_name", !strcmp(nm, "Hotplugged Pad"), "name='%s'", nm);
    step(11);                                                  /* JS: 入力を 1 台除去 (statechange は発火しない) */
    check("rescan_rpc", flmidi_rescan() == 0 && flm_midiInGetNumDevs() == 2, "numdevs=%u (want 2)", flm_midiInGetNumDevs());

    flmidi_get_stats(st);
    int n = snprintf(g_result, sizeof g_result, "{\"checks\":[");
    for (int i = 0; i < nC; i++) {
        n += snprintf(g_result + n, sizeof g_result - n, "%s{\"name\":\"%s\",\"ok\":%d,\"detail\":\"", i ? "," : "", C[i].name, C[i].ok);
        for (const char *p = C[i].detail; *p && n < (int)sizeof g_result - 8; p++) { if (*p == '"' || *p == '\\') g_result[n++] = '\\'; g_result[n++] = ((unsigned char)*p >= 32 && (unsigned char)*p < 127) ? *p : '?'; }
        n += snprintf(g_result + n, sizeof g_result - n, "\"}");
    }
    n += snprintf(g_result + n, sizeof g_result - n, "],\"stats\":[");
    for (int i = 0; i < 15; i++) n += snprintf(g_result + n, sizeof g_result - n, "%s%u", i ? "," : "", st[i]);
    snprintf(g_result + n, sizeof g_result - n, "]}");
}

int main(void) {
    flm_init();
    for (int i = 0; i < 500 && !__atomic_load_n(&flm_ctl()->ctrl_ready, __ATOMIC_SEQ_CST); i++) usleep(20 * 1000);   /* JS コントローラ常駐待ち */
    run();
    __atomic_store_n(&g_done, 1, __ATOMIC_SEQ_CST);
    __builtin_wasm_memory_atomic_notify((int *)&g_done, 0x7fffffff);
    return 0;
}
