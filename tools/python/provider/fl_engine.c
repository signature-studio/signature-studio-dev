/* MCPTools.pyc が静的に参照する flapi 60 関数 (公開 52 + ilmcp 8) のハンドラ + 最小エンジン状態。
 * 意味論は host/fl_mock.mjs (公開 52) と host/ilmcp.mjs (ilmcp 8) と同一 (実エンジンとの差は REPORT 未解決参照)。
 * 実 FLEngine 結合時は このファイルのハンドラだけを FLEngine の内部 API 呼出しに置換し、fl_dispatch.c / fl_table.c は流用する。 */
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fl_api.h"
#include "gen/ilmcp_data.h"

#define NMIX 127
#define NSLOT 10
#define NCH_MAX 512
#define NPL 500
#define NSTEP 64
#define NWIN 64
#define NAME 96
#define ROOT_NAME "Plugin database"

typedef struct { char name[NAME], plugin[NAME]; double vol, pan; int mute, solo, sel, fx; int64_t color; uint8_t steps[NSTEP]; } Chan;
typedef struct { char name[NAME]; double vol, pan; int mute, solo, sel; int64_t color; int color_set; char slots[NSLOT][NAME]; int act[NMIX]; double lvl[NMIX]; } Mix;
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
static int dev_port, midi_out_n;
static int sel_chan;
static const struct { const char *n; double v; } params[] = {{"Cutoff", 0.5}, {"Resonance", 0.2}, {"Gain", 0.8}};
static double pvals[3];
#define NPARAM 3
static int changed_flag, use_metronome, precount, rec_ppq;
static int sel_start, sel_end;
static int64_t disp_time;
static int64_t arr_time;
static int scr_blanked, scr_unblank, scr_active;

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
        mx[i].vol = 0.8; mx[i].sel = (i == 0);
        if (i) { mx[i].act[0] = 1; mx[i].lvl[0] = 1.0; }
    }
    for (int i = 0; i < NPL; i++) { snprintf(pl[i].name, NAME, "Track %d", i + 1); pl[i].color = 0x485156; }
    memset(win, 0, sizeof win);
    win[0] = win[2] = win[4] = 1;
    for (int i = 0; i < NPARAM; i++) pvals[i] = params[i].v;
    tempo = 130; playing = 0; hl_cb = 0; n_pr = n_run = 0;
    changed_flag = 0; use_metronome = 0; precount = 0; rec_ppq = 96;
    sel_start = -1; sel_end = -1;
    arr_time = 0;
    scr_blanked = 0; scr_unblank = 0; scr_active = 0;
    dev_port = 0; midi_out_n = 0; sel_chan = 0; disp_time = 0;
}
int64_t fl_engine_highlight_cb(void) { return hl_cb; }
int fl_engine_channel_count(void) { return nch; }
int fl_engine_midi_out_count(void) { return midi_out_n; }
/* 検査用の読出し口: 最後に作用先へ渡した時間引数 (頭打ち後)。tests/ui_display_diff.mjs が mock と照合 */
int64_t fl_engine_display_time(void) { return disp_time; }
/* 検査用の読出し口: チャンネル c のステップ p (範囲外は -1)。tests/midi_path_diff.mjs が副作用を比べる */
int fl_engine_grid_bit(int c, int p) {
    if (c < 0 || c >= nch || p < 0 || p >= NSTEP) return -1;
    return ch[c].steps[p];
}

#define WRONGN() return fl_err(c, FL_E_WRONG_PARAM, "Wrong number of function parameters or wrong parameter type")
/* 署名なし (np=-1) の関数は dispatch が個数を見ないので handler が検査する */
#define NARGS(lo, hi) do { if (c->n < (lo) || c->n > (hi)) WRONGN(); } while (0)
#define RANGE() return fl_err(c, FL_E_RANGE, "Index out of range")
#define RANGE_MSG(m) return fl_err(c, FL_E_RANGE, (m))
#define CH(a) int64_t _i = A_INT((a), 0); if (_i < 0 || _i >= nch) RANGE(); Chan *k = &ch[_i]
#define MX(a) int64_t _m = A_INT((a), 0); if (_m < 0 || _m >= NMIX) RANGE(); Mix *t = &mx[_m]
#define TOG(cur, v) ((v) == -1 ? !(cur) : ((v) != 0))
static double db(double v, double ref) { return 20.0 * log10((v > 1e-6 ? v : 1e-6) / ref); }

/* ---- channels (18) ---- */
FL_H(channels, channelCount) { return fl_ret_i(c, nch); }
FL_H(channels, getChannelName) { CH(0); return fl_ret_s(c, k->name); }
FL_H(channels, setChannelName) { CH(0); const char *s = A_STR(1); set_name(k->name, s); return fl_ret_none(c); }
FL_H(channels, isChannelSelected) { CH(0); return fl_ret_b(c, k->sel); }
/* PY-41 (#1514): 公開 stub (IL-Group/FL-Studio-API-Stubs) の戻り型と説明で決めた 5 関数。useGlobalIndex は未モデル (グループ無し) */
FL_H(channels, isChannelMuted) { CH(0); return fl_ret_b(c, k->mute); }
FL_H(channels, isChannelSolo) { CH(0); return fl_ret_b(c, k->solo); }
FL_H(channels, getChannelColor) { CH(0); return fl_ret_i(c, k->color); }
FL_H(channels, getGridBit) { CH(0); int64_t p = A_INT(1, 0); if (p < 0 || p >= NSTEP) RANGE(); return fl_ret_b(c, k->steps[p]); }
/* 選択の並びで offset 番目 (0 = 先頭)、超えたら最後の選択。負の offset は先頭扱い (stub に記述なし・仮置き)。無選択は canBeNone で -1 / 0 */
FL_H(channels, channelNumber) {
    int64_t none = A_INT(0, 0), off = A_INT(1, 0), n = 0, pick = -1;
    int last = -1;
    if (off < 0) off = 0;
    for (int i = 0; i < nch; i++) {
        if (!ch[i].sel) continue;
        if (pick < 0 && n == off) pick = i;
        last = i; n++;
    }
    if (last < 0) return fl_ret_i(c, none ? -1 : 0);
    return fl_ret_i(c, pick < 0 ? last : pick);
}
/* 型定数 (stub midi.CT_*): Sampler = 0、生成プラグイン = CT_GenPlug 2。Hybrid 1・Layer 3・AudioClip 4・AutoClip 5 は mock に無いため未モデル */
FL_H(channels, getChannelType) { CH(0); return fl_ret_i(c, strcmp(k->plugin, "Sampler") == 0 ? 0 : 2); }
/* PY-89 (#2805): getChannelIndex は全 channel を 1 グループとみなして identity (PE 0xd5bd60 は 0..nch-1 の範囲検査)。getChannelMidiInPort は既定 -2 (未割当・PE 0xfe976e の初期化)。設定経路は公開 API に無いため状態は持たない。useGlobalIndex は未モデル */
FL_H(channels, getChannelIndex) { CH(0); return fl_ret_i(c, _i); }
FL_H(channels, getChannelMidiInPort) { CH(0); (void)A_INT(1, 0); return fl_ret_i(c, -2); }
FL_H(channels, selectChannel) { CH(0); int64_t v = A_INT(1, -1); k->sel = TOG(k->sel, v); return fl_ret_none(c); }
FL_H(channels, deselectAll) { for (int i = 0; i < nch; i++) ch[i].sel = 0; return fl_ret_none(c); }
/* PE 0xd5afc0 → 0xd5af30 → 0x11e84a0: 範囲外は -4 (Index out of range)、他 channel の選択を解除して対象だけ選ぶ。未モデル: useGlobalIndex・前提ゲート 0xd5af58・選択 gating 0xffac20 (REPORT_PY69) */
FL_H(channels, selectOneChannel) {
    CH(0); (void)A_INT(1, 0);
    for (int i = 0; i < nch; i++) ch[i].sel = (i == _i);
    return fl_ret_none(c);
}
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
FL_H(channels, selectedChannel) {
    (void)A_INT(0, 0); int64_t off = A_INT(1, 0); (void)A_INT(2, 0);
    return fl_ret_i(c, sel_chan + off);
}
FL_H(channels, fillEachNSteps) {
    CH(0); int64_t st = A_INT(1, 1), off = A_INT(2, 0), vel = A_INT(3, 0);
    (void)vel; (void)A_INT(4, 0);
    if (st < 1) RANGE();
    int64_t p = off;
    if (p < 0) { p %= st; if (p < 0) p += st; }
    while (p < NSTEP) { k->steps[p] = 1; if (st > NSTEP - p) break; p += st; }
    return fl_ret_none(c);
}
FL_H(channels, showEditor) { CH(0); (void)k; return fl_ret_none(c); }
/* PY-40 (#1529): PE 0xd5ca50 / 0xd5c920 / 0xd5cbd0 / 0xd5c180 / 0xd5c5d0。引数は PyArg 順に全部読んでから index を検査 (範囲外は code 4)。
 * 述語 (前提ゲート) は真と仮定し、UI 副作用・戻り値の内部経路・useGlobalIndex による配列の違いは未モデル (REPORT_PY40 §8) */
FL_H(channels, closeGraphEditor) { (void)A_INT(0, 0); return fl_ret_none(c); }
FL_H(channels, updateGraphEditor) { return fl_ret_none(c); }
FL_H(channels, showGraphEditor) {
    (void)A_INT(0, 0); (void)A_INT(1, 0); (void)A_INT(2, 0);
    int64_t idx = A_INT(3, 0); (void)A_INT(4, 1);
    if (idx < 0 || idx >= nch) RANGE();
    return fl_ret_none(c);
}
FL_H(channels, showCSForm) {
    int64_t idx = A_INT(0, 0); (void)A_INT(1, 1); (void)A_INT(2, 0);
    if (idx < 0 || idx >= nch) RANGE();
    return fl_ret_none(c);
}
FL_H(channels, focusEditor) {
    int64_t idx = A_INT(0, 0); (void)A_INT(1, 0);
    if (idx < 0 || idx >= nch) RANGE();
    return fl_ret_none(c);
}
/* PY-100 (#2879): PE 0xd5b930 の readout。構造体は grid bit が立つ step にあるとみなす (生成条件は未確定)。
 * 既定値は stub の並び (param 0..7 = pitch 60・velocity 100・release 64・fine pitch 120・pan 64・mod X 64・mod Y 64・ticks 0)。
 * 構造体が無い・param が 0..7 の外は -1 (PE: 構造体 NULL で -1)。param 8 (PE: byte +0x11) は既定値未確定のため未モデル (-1) */
static const int64_t step_def[8] = {60, 100, 64, 120, 64, 64, 64, 0};
static int64_t step_param(const Chan *k, int64_t pos, int64_t prm) {
    if (pos < 0 || pos >= NSTEP || !k->steps[pos] || prm < 0 || prm > 7) return -1;
    return step_def[prm];
}
/* PE 0xd5bb30: 引数を読んでから index を検査 (範囲外は Index out of range)。useGlobalIndex は未モデル (グループ無し) */
FL_H(channels, getCurrentStepParam) {
    NARGS(3, 4);
    int64_t step = A_INT(1, 0), prm = A_INT(2, 0);
    (void)A_INT(3, 0);
    CH(0);
    return fl_ret_i(c, step_param(k, step, prm));
}
/* PE 0xd5ba00: 5 引数 (padsStride 既定 16)。padsStride 0 は Range error。対象 channel は list[step / padsStride + offset]、位置は step % padsStride + startPos */
FL_H(channels, getStepParam) {
    NARGS(4, 5);
    int64_t step = A_INT(0, 0), prm = A_INT(1, 0), off = A_INT(2, 0), st0 = A_INT(3, 0), pads = A_INT(4, 16);
    if (pads == 0) return fl_err(c, FL_E_RANGE, "Range error");
    int64_t q = step / pads, idx = q + off;
    if (idx < 0 || idx >= nch) RANGE();
    return fl_ret_i(c, step_param(&ch[idx], step - q * pads + st0, prm));
}

/* ---- mixer (19) ---- */
/* 色の R/B 入替え (PY-115 / REPORT_PY115.md §2)。格納は入替え + alpha 0xff、取得は入替えを再度通して alpha 0xff。 */
/* 既定色 (フラグ無し track) は FL の .bss 0x15f6774 の初期値 (init 0x770ba6・REPORT_PY118) */
#define MIX_DEFAULT_COLOR 0xff636c71u
static uint32_t fl_swap_rb(uint32_t v) { return ((v & 0xff) << 16) | (v & 0xff00) | ((v >> 16) & 0xff); }
FL_H(mixer, trackCount) { return fl_ret_i(c, NMIX); }
FL_H(mixer, getTrackName) { MX(0); return fl_ret_s(c, t->name); }
FL_H(mixer, setTrackName) { MX(0); const char *s = A_STR(1); set_name(t->name, s); return fl_ret_none(c); }
FL_H(mixer, getTrackVolume) { MX(0); int64_t m = A_INT(1, 0); return fl_ret_d(c, m ? db(t->vol, 0.8) : t->vol); }
FL_H(mixer, setTrackVolume) { MX(0); t->vol = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(mixer, getTrackPan) { MX(0); return fl_ret_d(c, t->pan); }
FL_H(mixer, setTrackPan) { MX(0); t->pan = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(mixer, setTrackColor) { MX(0); t->color = fl_swap_rb((uint32_t)A_INT(1, 0)) | 0xff000000u; t->color_set = 1; return fl_ret_none(c); }
FL_H(mixer, getTrackColor) {
    MX(0); uint32_t u = t->color_set ? (uint32_t)t->color : fl_swap_rb(MIX_DEFAULT_COLOR);
    return fl_ret_i(c, (int64_t)(fl_swap_rb(u) | 0xff000000u));
}
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
FL_H(transport, isPlaying) { return fl_ret_b(c, playing); }
#define PL(a) int64_t _p = A_INT((a), 0); if (_p < 1 || _p > NPL) RANGE(); Pl *p = &pl[_p - 1]
FL_H(playlist, trackCount) { return fl_ret_i(c, NPL); }
FL_H(playlist, getTrackName) {
    int64_t i = A_INT(0, 0);
    return fl_ret_s(c, (i >= 1 && i <= NPL) ? pl[i - 1].name : ""); /* mock と同一: 範囲外は空文字 */
}
FL_H(playlist, setTrackName) { PL(0); const char *s = A_STR(1); set_name(p->name, s); return fl_ret_none(c); }
/* FL の格納式 (setTrackColor 0xd55f30 → 0x12e5d80): R/B を入替えて 0xffffff で切る。getTrackColor の逆変換 */
FL_H(playlist, setTrackColor) { PL(0); uint32_t u = (uint32_t)A_INT(1, 0); p->color = (int64_t)((((u & 0xff) << 16) | (u & 0xff00) | ((u >> 16) & 0xff)) & 0xffffff); return fl_ret_none(c); }
#define WN(a) int64_t _w = A_INT((a), 0); if (_w < 0 || _w >= NWIN) RANGE()
FL_H(ui, getVisible) { WN(0); return fl_ret_b(c, win[_w]); }
FL_H(ui, showWindow) { WN(0); win[_w] = 1; return fl_ret_none(c); }
FL_H(ui, hideWindow) { WN(0); win[_w] = 0; return fl_ret_none(c); }
/* PY-121 (#2982): PE 0xd6e860 (crDisplayRect 'iiiii|i')・0xd6ea40 (miDisplayRect 'iii|i')・0xd6ebf0 (miDisplayDockRect 'iiii') は
 * PyArg で読み、時間引数 (duration / time) を 0x7d0 で頭打ちにして作用先へ渡す (cmp rax,0x7d0)。表示そのものは未モデル */
#define DISP_MAX 0x7d0
FL_H(ui, crDisplayRect) { NARGS(5, 6); int64_t v[6]; for (int i = 0; i < 6; i++) v[i] = A_INT(i, 0); disp_time = v[4] > DISP_MAX ? DISP_MAX : v[4]; return fl_ret_none(c); }
FL_H(ui, miDisplayRect) { NARGS(3, 4); int64_t v[4]; for (int i = 0; i < 4; i++) v[i] = A_INT(i, 0); disp_time = v[2] > DISP_MAX ? DISP_MAX : v[2]; return fl_ret_none(c); }
FL_H(ui, miDisplayDockRect) { NARGS(4, 4); int64_t v[4]; for (int i = 0; i < 4; i++) v[i] = A_INT(i, 0); disp_time = v[3] > DISP_MAX ? DISP_MAX : v[3]; return fl_ret_none(c); }
/* PE 0xd6c8b0 (showNotification 'i')・0xd6d7c0 / 0xd6d8e0 (NOARGS): 引数の範囲検査は PE に無い。作用は未モデル */
FL_H(ui, showNotification) { NARGS(1, 1); (void)A_INT(0, 0); return fl_ret_none(c); }
FL_H(ui, closeAllMenu) { NARGS(0, 0); return fl_ret_none(c); }
FL_H(ui, closeActivePopupMenu) { NARGS(0, 0); return fl_ret_none(c); }
/* PY-119 (#2980): PE 0xd6cd80 / 0xd6ca80 / 0xd6c9d0 / 0xd6cab0 / 0xd6c4c0 / 0xd6d6b0 は呼出し経路を確定 (REPORT_PY119)。値は未実測の仮置き */
FL_H(ui, getFocused) { NARGS(1, 1); (void)A_INT(0, 0); return fl_ret_b(c, 0); }
FL_H(ui, getFocusedFormID) { NARGS(0, 0); return fl_ret_i(c, 0); }
FL_H(ui, getFocusedFormCaption) { NARGS(0, 0); return fl_ret_s(c, ""); }
FL_H(ui, getFocusedPluginName) { NARGS(0, 0); return fl_ret_s(c, ""); }
FL_H(ui, getHintMsg) { NARGS(0, 0); return fl_ret_s(c, ""); }
FL_H(ui, isInPopupMenu) { NARGS(0, 0); return fl_ret_b(c, 0); }

/* ---- general (1) ---- mock と同じ MIDI scripting API バージョン (実機値は未実測) */
FL_H(general, getVersion) { NARGS(0, 0); return fl_ret_i(c, 1); }
/* PY-87 (#2738): PE 0xd69800/0xd69820/0xd69840/0xd69330 は状態 1 つを読んで変換スロット 0x15e4280 に渡すだけ。値は未実測の仮置き (REPORT_PY87) */
FL_H(general, getChangedFlag) { NARGS(0, 0); return fl_ret_i(c, changed_flag); }
FL_H(general, getUseMetronome) { NARGS(0, 0); return fl_ret_b(c, use_metronome); }
FL_H(general, getPrecount) { NARGS(0, 0); return fl_ret_b(c, precount); }
FL_H(general, getRecPPQ) { NARGS(0, 0); return fl_ret_i(c, rec_ppq); }
/* PY-125 (#3001): PE 0xd6a1f0 (clearLog) と 0xd6a060 (dumpScoreLog) は、成功経路 (述語 P 真・gate 真) で dispatch 0xd843d0 を経て None を返す (REPORT_PY125 §4)。効果は API から観測できないため状態を持たない */
FL_H(general, clearLog) { NARGS(0, 0); return fl_ret_none(c); }
FL_H(general, dumpScoreLog) { NARGS(1, 2); (void)A_INT(0, 0); (void)A_INT(1, 0); return fl_ret_none(c); }
/* PY-119 (#2977): PE 0xd69350/0xd694e0/0xd69670 は範囲外で status -3 (Range error)。ゲートは未確定のため真と仮定 (REPORT_PY119_2977) */
static int numerator = 4, denominator = 4;
FL_H(general, setRecPPQ) { NARGS(1, 1); int64_t v = A_INT(0, 0); if (v < 24 || v > 960) RANGE_MSG("Range error"); rec_ppq = (int)v; return fl_ret_none(c); }
FL_H(general, setNumerator) { NARGS(1, 1); int64_t v = A_INT(0, 0); if (v < 1 || v > 16) RANGE_MSG("Range error"); numerator = (int)v; return fl_ret_none(c); }
FL_H(general, setDenominator) { NARGS(1, 1); int64_t v = A_INT(0, 0); if (v < 2 || v > 16) RANGE_MSG("Range error"); denominator = (int)v; return fl_ret_none(c); }
/* undo 3 件: PE 0xd69af0 は範囲検査なし (kind 0=Pos → +0x1c, 1=Count → +0x24, 2=Last → +0x20) */
static int undo_pos, undo_count, undo_last;
FL_H(general, setUndoHistoryPos) { NARGS(1, 1); undo_pos = (int)A_INT(0, 0); return fl_ret_none(c); }
FL_H(general, setUndoHistoryCount) { NARGS(1, 1); undo_count = (int)A_INT(0, 0); return fl_ret_none(c); }
FL_H(general, setUndoHistoryLast) { NARGS(1, 1); undo_last = (int)A_INT(0, 0); return fl_ret_none(c); }

/* ---- arrangement (4, PY-96 #2832) ---- PE 0xd786e0/0xd78700/0xd78500 が obj+0xd74/+0xd78 を読み、0xd78720 は 0xe43e80 (両方 >= 0) を bool で返す。初期値 -1 は未実測の仮置き */
FL_H(arrangement, selectionStart) { NARGS(0, 0); return fl_ret_i(c, sel_start); }
FL_H(arrangement, selectionEnd) { NARGS(0, 0); return fl_ret_i(c, sel_end); }
FL_H(arrangement, liveSelectionStart) { NARGS(0, 0); return fl_ret_i(c, sel_start); }
FL_H(arrangement, selectionIsActive) { NARGS(0, 0); return fl_ret_b(c, sel_start >= 0 && sel_end >= 0); }
/* ---- arrangement (6) ---- PY-152 (#2983): 呼出し構造と PyArg 書式は PE で確定。個数は fl_table (stub 由来・必須 2) に合わせた暫定で、
 * jumpToMarker は PE (必須 1) と不一致 (REPORT_PY152 未解決)。currentTime は仮置きの状態 arr_time を返す。
 * 選択・マーカーの 5 件は副作用が未同定のため状態を変えず、引数検査だけ行う (REPORT_PY152) */
FL_H(arrangement, currentTime) { (void)A_INT(0, 0); return fl_ret_i(c, arr_time); }
FL_H(arrangement, selectionClear) { NARGS(0, 0); return fl_ret_none(c); }
FL_H(arrangement, selectionSet) { NARGS(2, 5); for (int i = 0; i < 5; i++) (void)A_INT(i, 0); return fl_ret_none(c); }
FL_H(arrangement, liveSelection) { (void)A_INT(0, 0); (void)A_INT(1, 0); return fl_ret_none(c); }
FL_H(arrangement, addAutoTimeMarker) { (void)A_INT(0, 0); (void)A_STR(1); return fl_ret_none(c); }
FL_H(arrangement, jumpToMarker) { (void)A_INT(0, 0); (void)A_INT(1, 0); return fl_ret_none(c); }
/* ---- screen (5) ---- PY-121 (#2985): PE 0xd7c7e0・0xd7c830・0xd7c880・0xd7c8c0・0xd7c740 (REPORT_PY121_2985)。値は未実測の仮置き */
FL_H(screen, isBlanked) { NARGS(0, 0); return fl_ret_b(c, scr_blanked); }
FL_H(screen, isUnBlank) { NARGS(0, 0); return fl_ret_b(c, scr_unblank); }
FL_H(screen, getScreenActiveCounter) { NARGS(0, 0); return fl_ret_i(c, scr_active); }
FL_H(screen, setScreenActiveCounter) { NARGS(1, 1); scr_active = (int)((unsigned)scr_active + (unsigned)A_INT(0, 0)); return fl_ret_none(c); }
FL_H(screen, unBlank) { NARGS(1, 1); scr_unblank = A_INT(0, 0) == 1; return fl_ret_none(c); }

/* ---- device (5, MIDI scripting 用の最小面) ---- mock と同じ: forwardMIDICC / midiOutMsg は呼出しを数える */
FL_H(device, getPortNumber) { return fl_ret_i(c, dev_port); }
FL_H(device, isAssigned) { return fl_ret_b(c, 1); }
FL_H(device, setHasMeters) { return fl_ret_none(c); }
FL_H(device, forwardMIDICC) { (void)A_INT(0, 0); (void)A_INT(1, 1); midi_out_n++; return fl_ret_none(c); }
FL_H(device, midiOutMsg) { (void)A_INT(0, 0); (void)A_INT(1, -1); (void)A_INT(2, -1); (void)A_INT(3, -1); midi_out_n++; return fl_ret_none(c); }

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

/* ---- ilmcp (8) ---- host/ilmcp.mjs と同じ意味論 (エラー code・木の並び・検証)。
 * 木・プラグイン名・highlight 名は gen/ilmcp_data.h (analysis/ilmcp の JSON から生成)。 */
static int plugin_kind_ok(const char *name, const char *kind) {
    for (int i = 0; i < ilmcp_plugin_n; i++)
        if (!strcmp(ilmcp_plugins[i].name, name) && !strcmp(ilmcp_plugins[i].kind, kind)) return 1;
    return 0;
}

/* JS の Error(msg, code) 相当: "<pre><s>" を code で返す */
static int fl_err_fmt(fl_call *c, int code, const char *pre, const char *s) {
    size_t n = strlen(pre) + strlen(s) + 1;
    char *m = malloc(n);
    if (!m) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error");
    snprintf(m, n, "%s%s", pre, s);
    int r = fl_err(c, code, m);
    free(m);
    return r;
}

/* JS norm 相当: \ を / とみなし、各区切りを trim して空を除く。先頭は "Plugin database" でなければならない。
 * 残りを "/" で連結した木のキーを out に書く (out は in と同じ大きさ以下で足りる)。 */
static int browser_key(const char *in, char *out) {
    size_t n = strlen(in), o = 0, segs = 0, i = 0;
    while (i <= n) {
        size_t e = i;
        while (e < n && in[e] != '/' && in[e] != '\\') e++;
        size_t s = i, t = e;
        while (s < t && isspace((unsigned char)in[s])) s++;
        while (t > s && isspace((unsigned char)in[t - 1])) t--;
        if (t > s) {
            if (segs == 0) {
                if (t - s != strlen(ROOT_NAME) || memcmp(in + s, ROOT_NAME, t - s)) return 0;
            } else {
                if (o) out[o++] = '/';
                memcpy(out + o, in + s, t - s);
                o += t - s;
            }
            segs++;
        }
        i = e + 1;
    }
    if (!segs) return 0;
    out[o] = 0;
    return 1;
}

static const ilmcp_dir *find_dir(const char *key) {
    for (int i = 0; i < ilmcp_dir_n; i++)
        if (!strcmp(ilmcp_dirs[i].key, key)) return &ilmcp_dirs[i];
    return NULL;
}

/* 文字列の list を JSON 配列で返す (NULL 終端の表。中身は生成時に引用符・\ を含まないと検査済み) */
static int ret_list(fl_call *c, const char *const *items) {
    size_t n = 3;
    for (const char *const *p = items; *p; p++) n += strlen(*p) + 4;
    char *b = malloc(n);
    if (!b) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error");
    size_t o = 0;
    b[o++] = '[';
    for (const char *const *p = items; *p; p++) {
        if (p != items) b[o++] = ',';
        o += (size_t)sprintf(b + o, "\"%s\"", *p);
    }
    b[o++] = ']';
    b[o] = 0;
    int r = fl_ret_json(c, b);
    free(b);
    return r;
}

FL_H(ilmcp, getBrowserNames) {
    NARGS(0, 2);
    const char *nm = (c->n > 0 && c->a[0].tag == 'S') ? A_STR(0) : "";
    int64_t rec = A_INT(1, 0);
    char *key = malloc(strlen(nm) + 1);
    if (!key) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error");
    const ilmcp_dir *d = browser_key(nm, key) ? find_dir(key) : NULL;
    free(key);
    if (!d) return fl_err_fmt(c, FL_E_INVALID_VALUE, "Unknown browser path: ", nm);
    return ret_list(c, rec ? d->flat1 : d->flat0);
}
FL_H(ilmcp, getHighlightNames) {
    NARGS(0, 0);
    return ret_list(c, ilmcp_highlights);
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
    if (!plugin_kind_ok(pn, "generator")) return fl_err_fmt(c, FL_E_INVALID_VALUE, "Unknown generator plugin: ", pn);
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
    if (pn[0] && !plugin_kind_ok(pn, "effect")) return fl_err_fmt(c, FL_E_INVALID_VALUE, "Unknown effect plugin: ", pn);
    set_name(mx[t].slots[s], pn); return fl_ret_b(c, 1);
}
FL_H(ilmcp, storePRScript) {
    NARGS(2, 2);
    const char *nm = A_STR(0); (void)A_STR(1);
    if (!nm[0] || strpbrk(nm, "\\/:")) return fl_err_fmt(c, FL_E_INVALID_VALUE, "Invalid script name: ", nm);
    n_pr++; return fl_ret_b(c, 1);
}
FL_H(ilmcp, runPRScript) { NARGS(1, 1); (void)A_STR(0); n_run++; return fl_ret_b(c, 1); }
/* 引数 arity は未確認 (REPORT_PY74 §7c)。mock と同じく個数を見ず、何も返さない */
FL_H(ilmcp, forwardTutorialEvent) { return fl_ret_none(c); }
