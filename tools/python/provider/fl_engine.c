/* MCPTools.pyc が静的に参照する flapi 60 関数 (公開 52 + ilmcp 8) のハンドラ + 最小エンジン状態。
 * 意味論は host/fl_mock.mjs と同一 (実エンジンとの差は REPORT 未解決参照)。実 FLEngine 結合時は
 * このファイルのハンドラだけを FLEngine の内部 API 呼出しに置換し、fl_dispatch.c / fl_table.c は流用する。 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fl_api.h"

#define NMIX 127
#define NSLOT 10
#define NCH_MAX 512
#define NPL 500
#define NSTEP 64
#define NWIN 64
#define NAME 96

typedef struct { char name[NAME], plugin[NAME]; double vol, pan; int mute, solo, sel, fx; int64_t color; uint8_t steps[NSTEP]; } Chan;
typedef struct { char name[NAME]; double vol, pan; int mute, solo, sel; int64_t color; char slots[NSLOT][NAME]; int act[NMIX]; double lvl[NMIX]; } Mix;
typedef struct { char name[NAME]; int64_t color; } Pl;

static Chan ch[NCH_MAX];
static int nch;
static Mix mx[NMIX];
static Pl pl[NPL];
static int win[NWIN];
static double tempo;
static int playing;
static int64_t hl_cb;
static int n_pr, n_run;
static const struct { const char *n; double v; } params[] = {{"Cutoff", 0.5}, {"Resonance", 0.2}, {"Gain", 0.8}};
static double pvals[3];
#define NPARAM 3

static void set_name(char *dst, const char *s) { snprintf(dst, NAME, "%s", s); }
static void init_chan(Chan *c, const char *name, const char *plugin, double vol, double pan, int sel, int fx, int64_t color) {
    memset(c, 0, sizeof *c);
    set_name(c->name, name); set_name(c->plugin, plugin);
    c->vol = vol; c->pan = pan; c->sel = sel; c->fx = fx; c->color = color;
}

void fl_engine_reset(void) {
    nch = 3;
    init_chan(&ch[0], "Kick", "Sampler", 0.78125, 0, 1, 1, 0x5A6B7C);
    init_chan(&ch[1], "Snare", "Sampler", 0.78125, 0, 0, 2, 0x5A6B7C);
    init_chan(&ch[2], "3x Osc", "3x Osc", 0.5, 0.25, 0, 0, 0x7C5A6B);
    memset(mx, 0, sizeof mx);
    for (int i = 0; i < NMIX; i++) {
        if (i == 0) set_name(mx[i].name, "Master");
        else if (i == 125) set_name(mx[i].name, "Current");
        else snprintf(mx[i].name, NAME, "Insert %d", i);
        mx[i].vol = 0.8; mx[i].color = 0x5A6B7C; mx[i].sel = (i == 0);
        if (i) { mx[i].act[0] = 1; mx[i].lvl[0] = 1.0; }
    }
    for (int i = 0; i < NPL; i++) { snprintf(pl[i].name, NAME, "Track %d", i + 1); pl[i].color = 0x485156; }
    memset(win, 0, sizeof win);
    win[0] = win[2] = win[4] = 1;
    for (int i = 0; i < NPARAM; i++) pvals[i] = params[i].v;
    tempo = 130; playing = 0; hl_cb = 0; n_pr = n_run = 0;
}
int64_t fl_engine_highlight_cb(void) { return hl_cb; }
int fl_engine_channel_count(void) { return nch; }

#define WRONGN() return fl_err(c, FL_E_WRONG_PARAM, "Wrong number of function parameters or wrong parameter type")
/* 署名なし (np=-1) の関数は dispatch が個数を見ないので handler が検査する */
#define NARGS(lo, hi) do { if (c->n < (lo) || c->n > (hi)) WRONGN(); } while (0)
#define RANGE() return fl_err(c, FL_E_RANGE, "Index out of range")
#define CH(a) int64_t _i = A_INT((a), 0); if (_i < 0 || _i >= nch) RANGE(); Chan *k = &ch[_i]
#define MX(a) int64_t _m = A_INT((a), 0); if (_m < 0 || _m >= NMIX) RANGE(); Mix *t = &mx[_m]
#define TOG(cur, v) ((v) == -1 ? !(cur) : ((v) != 0))
static double db(double v, double ref) { return 20.0 * log10((v > 1e-6 ? v : 1e-6) / ref); }

/* ---- channels (18) ---- */
FL_H(channels, channelCount) { return fl_ret_i(c, nch); }
FL_H(channels, getChannelName) { CH(0); return fl_ret_s(c, k->name); }
FL_H(channels, setChannelName) { CH(0); const char *s = A_STR(1); set_name(k->name, s); return fl_ret_none(c); }
FL_H(channels, isChannelSelected) { CH(0); return fl_ret_b(c, k->sel); }
FL_H(channels, selectChannel) { CH(0); int64_t v = A_INT(1, -1); k->sel = TOG(k->sel, v); return fl_ret_none(c); }
FL_H(channels, deselectAll) { for (int i = 0; i < nch; i++) ch[i].sel = 0; return fl_ret_none(c); }
FL_H(channels, muteChannel) { CH(0); int64_t v = A_INT(1, -1); k->mute = TOG(k->mute, v); return fl_ret_none(c); }
FL_H(channels, soloChannel) { CH(0); k->solo = !k->solo; return fl_ret_none(c); }
FL_H(channels, getChannelVolume) { CH(0); int64_t m = A_INT(1, 0); return fl_ret_d(c, m ? db(k->vol, 0.78125) : k->vol); }
FL_H(channels, setChannelVolume) { CH(0); k->vol = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(channels, getChannelPan) { CH(0); return fl_ret_d(c, k->pan); }
FL_H(channels, setChannelPan) { CH(0); k->pan = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(channels, setChannelColor) { CH(0); k->color = A_INT(1, 0); return fl_ret_none(c); }
FL_H(channels, getTargetFxTrack) { CH(0); return fl_ret_i(c, k->fx); }
FL_H(channels, setTargetFxTrack) { CH(0); k->fx = (int)A_INT(1, 0); return fl_ret_none(c); }
FL_H(channels, setGridBit) {
    CH(0); int64_t p = A_INT(1, 0), v = A_INT(2, 0);
    if (p < 0 || p >= NSTEP) RANGE();
    k->steps[p] = v ? 1 : 0; return fl_ret_none(c);
}
FL_H(channels, quickQuantize) { CH(0); (void)k; return fl_ret_none(c); }
FL_H(channels, showEditor) { CH(0); (void)k; return fl_ret_none(c); }

/* ---- mixer (18) ---- */
FL_H(mixer, trackCount) { return fl_ret_i(c, NMIX); }
FL_H(mixer, getTrackName) { MX(0); return fl_ret_s(c, t->name); }
FL_H(mixer, setTrackName) { MX(0); const char *s = A_STR(1); set_name(t->name, s); return fl_ret_none(c); }
FL_H(mixer, getTrackVolume) { MX(0); int64_t m = A_INT(1, 0); return fl_ret_d(c, m ? db(t->vol, 0.8) : t->vol); }
FL_H(mixer, setTrackVolume) { MX(0); t->vol = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(mixer, getTrackPan) { MX(0); return fl_ret_d(c, t->pan); }
FL_H(mixer, setTrackPan) { MX(0); t->pan = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(mixer, setTrackColor) { MX(0); t->color = A_INT(1, 0); return fl_ret_none(c); }
FL_H(mixer, isTrackSelected) { MX(0); return fl_ret_b(c, t->sel); }
FL_H(mixer, muteTrack) { MX(0); int64_t v = A_INT(1, -1); t->mute = TOG(t->mute, v); return fl_ret_none(c); }
FL_H(mixer, soloTrack) { MX(0); t->solo = !t->solo; return fl_ret_none(c); }
FL_H(mixer, focusEditor) { MX(0); (void)t; return fl_ret_none(c); }
FL_H(mixer, getRouteSendActive) {
    MX(0); int64_t d = A_INT(1, 0); if (d < 0 || d >= NMIX) RANGE();
    return fl_ret_b(c, t->act[d]);
}
FL_H(mixer, setRouteTo) {
    MX(0); int64_t d = A_INT(1, 0), v = A_INT(2, 0); if (d < 0 || d >= NMIX) RANGE();
    if (v) { if (!t->act[d]) t->lvl[d] = 1.0; t->act[d] = 1; } else t->act[d] = 0;
    return fl_ret_none(c);
}
FL_H(mixer, getRouteToLevel) {
    MX(0); int64_t d = A_INT(1, 0); if (d < 0 || d >= NMIX) RANGE();
    return fl_ret_d(c, t->act[d] ? t->lvl[d] : 0.0);
}
FL_H(mixer, setRouteToLevel) {
    MX(0); int64_t d = A_INT(1, 0); double v = A_DBL(2, 0); if (d < 0 || d >= NMIX) RANGE();
    t->act[d] = 1; t->lvl[d] = v; return fl_ret_none(c);
}
/* MCPTools は getCurrentTempo(1)/setCurrentTempo(bpm,1) を素の BPM として扱う (mock と同一。実機の意味は未確認) */
FL_H(mixer, getCurrentTempo) {
    int64_t as_int = A_INT(0, 0);
    return as_int ? fl_ret_i(c, (int64_t)llround(tempo)) : fl_ret_d(c, tempo);
}
FL_H(mixer, setCurrentTempo) {
    NARGS(1, 2);
    double bpm = A_DBL(0, 0);
    tempo = bpm >= 10000 ? bpm / 1000 : bpm;
    return fl_ret_none(c);
}

/* ---- transport (2) / playlist (4) / ui (3) ---- */
FL_H(transport, start) { playing = 1; return fl_ret_none(c); }
FL_H(transport, stop) { playing = 0; return fl_ret_none(c); }
#define PL(a) int64_t _p = A_INT((a), 0); if (_p < 1 || _p > NPL) RANGE(); Pl *p = &pl[_p - 1]
FL_H(playlist, trackCount) { return fl_ret_i(c, NPL); }
FL_H(playlist, getTrackName) {
    int64_t i = A_INT(0, 0);
    return fl_ret_s(c, (i >= 1 && i <= NPL) ? pl[i - 1].name : ""); /* mock と同一: 範囲外は空文字 */
}
FL_H(playlist, setTrackName) { PL(0); const char *s = A_STR(1); set_name(p->name, s); return fl_ret_none(c); }
FL_H(playlist, setTrackColor) { PL(0); p->color = A_INT(1, 0); return fl_ret_none(c); }
#define WN(a) int64_t _w = A_INT((a), 0); if (_w < 0 || _w >= NWIN) RANGE()
FL_H(ui, getVisible) { WN(0); return fl_ret_b(c, win[_w]); }
FL_H(ui, showWindow) { WN(0); win[_w] = 1; return fl_ret_none(c); }
FL_H(ui, hideWindow) { WN(0); win[_w] = 0; return fl_ret_none(c); }

/* ---- plugins (7) ---- (引数順: paramIndex 系は先頭、index/slotIndex/useGlobalIndex が後続) */
FL_H(plugins, isValid) {
    int64_t i = A_INT(0, 0), s = A_INT(1, -1);
    if (s < 0) return fl_ret_b(c, i >= 0 && i < nch);
    return fl_ret_b(c, i >= 0 && i < NMIX && s < NSLOT && mx[i].slots[s][0]);
}
FL_H(plugins, getPluginName) {
    int64_t i = A_INT(0, 0), s = A_INT(1, -1);
    if (s < 0) { if (i < 0 || i >= nch) RANGE(); return fl_ret_s(c, ch[i].plugin); }
    if (i < 0 || i >= NMIX || s >= NSLOT) RANGE();
    return fl_ret_s(c, mx[i].slots[s]);
}
FL_H(plugins, getParamCount) { return fl_ret_i(c, NPARAM); }
#define PP(a) int64_t _q = A_INT((a), 0); if (_q < 0 || _q >= NPARAM) RANGE()
FL_H(plugins, getParamName) { int64_t q = A_INT(0, 0); return fl_ret_s(c, (q >= 0 && q < NPARAM) ? params[q].n : ""); }
FL_H(plugins, getParamValue) { PP(0); return fl_ret_d(c, pvals[_q]); }
FL_H(plugins, getParamValueString) { PP(0); char b[48]; snprintf(b, sizeof b, "%.1f %%", pvals[_q] * 100); return fl_ret_s(c, b); }
FL_H(plugins, setParamValue) { double v = A_DBL(0, 0); int64_t q = A_INT(1, 0); if (q < 0 || q >= NPARAM) RANGE(); pvals[q] = v; return fl_ret_none(c); }

/* ---- ilmcp (8) ---- */
static void json_str(char *dst, size_t cap, const char *s) {
    size_t o = 0;
    dst[o++] = '"';
    for (; *s && o + 8 < cap; s++) {
        unsigned char ch_ = (unsigned char)*s;
        if (ch_ == '"' || ch_ == '\\') { dst[o++] = '\\'; dst[o++] = (char)ch_; }
        else if (ch_ < 0x20) o += (size_t)snprintf(dst + o, 8, "\\u%04x", ch_);
        else dst[o++] = (char)ch_;
    }
    dst[o++] = '"'; dst[o] = 0;
}
FL_H(ilmcp, getBrowserNames) {
    NARGS(0, 2);
    const char *nm = (c->n > 0 && c->a[0].tag == 'S') ? A_STR(0) : "";
    char q[512], b[2048], *w = b;
    json_str(q, sizeof q, nm);
    static const char *items[] = {"Fruity Slicer", "3x Osc", "Sampler"};
    w += snprintf(w, sizeof b, "{\"name\":%s,\"items\":[", q);
    for (int i = 0; i < 3; i++) {
        char full[NAME * 3], e[NAME * 6];
        snprintf(full, sizeof full, "%s/%s", nm, items[i]);
        json_str(e, sizeof e, full);
        w += snprintf(w, (size_t)(b + sizeof b - w), "%s%s", i ? "," : "", e);
    }
    snprintf(w, (size_t)(b + sizeof b - w), "]}");
    return fl_ret_json(c, b);
}
FL_H(ilmcp, getHighlightNames) {
    NARGS(0, 0);
    return fl_ret_json(c, "[\"Toolbar: Show Piano roll\",\"Toolbar: Show playlist\",\"Toolbar: Show Mixer\",\"Toolbar: Show Channel Rack\"]");
}
FL_H(ilmcp, showHighlight) {
    /* MCPTools 実測: 引数 5 (item,name,caption,whenDone,flag) と、whenDone 内のクリア呼出し 3 (""×3) */
    NARGS(3, 5);
    int64_t cb = 0;
    if (c->n > 3 && c->a[3].tag != 'N' && fl_a_cb(c, 3, &cb)) return FL_E_WRONG_PARAM;
    hl_cb = cb; return fl_ret_b(c, 1);
}
FL_H(ilmcp, addChannel) {
    NARGS(1, 1);
    const char *pn = A_STR(0);
    if (nch >= NCH_MAX) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error");
    init_chan(&ch[nch], pn, pn, 0.78125, 0, 0, 0, 0x5A6B7C);
    return fl_ret_i(c, nch++);
}
FL_H(ilmcp, removeChannel) {
    NARGS(1, 1);
    int64_t i = A_INT(0, 0); if (i < 0 || i >= nch) RANGE();
    memmove(&ch[i], &ch[i + 1], (size_t)(nch - i - 1) * sizeof(Chan)); nch--;
    return fl_ret_none(c);
}
FL_H(ilmcp, addEffect) {
    NARGS(3, 3);
    const char *pn = A_STR(0); int64_t t = A_INT(1, 0), s = A_INT(2, 0);
    if (t < 0 || t >= NMIX || s < 0 || s >= NSLOT) RANGE();
    set_name(mx[t].slots[s], pn); return fl_ret_b(c, 1);
}
FL_H(ilmcp, storePRScript) { NARGS(2, 2); (void)A_STR(0); (void)A_STR(1); n_pr++; return fl_ret_b(c, 1); }
FL_H(ilmcp, runPRScript) { NARGS(1, 1); (void)A_STR(0); n_run++; return fl_ret_b(c, 1); }
