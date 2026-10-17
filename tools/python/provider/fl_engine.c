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
#define GRID_N 16
#define NWIN 64
#define NAME 96
#define NPARAM 3
#define ROOT_NAME "Plugin database"

/* pv / spv: plugin パラメータの値 (インスタンスごと。channel の generator と mixer track の insert slot)。PY-228 (#3656) */
typedef struct { char name[NAME], plugin[NAME]; double vol, pan; int mute, solo, sel, fx; int64_t color; uint8_t steps[NSTEP]; uint8_t vel[NSTEP]; int64_t pitch_n; double pv[NPARAM]; } Chan;
typedef struct { char name[NAME]; double vol, pan; int mute, solo, sel; int64_t color; int color_set; char slots[NSLOT][NAME]; double spv[NSLOT][NPARAM]; int act[NMIX]; double lvl[NMIX]; } Mix;
typedef struct { char name[NAME]; int64_t color; uint8_t lock; double act; int loop, trig_mode, pos_snap, trig_snap; } Pl;

static Chan ch[NCH_MAX];
static int nch;
static int grid_n;
static Mix mx[NMIX];
static Pl pl[NPL];
static int win[NWIN];
static double tempo;
static int playing;
static int64_t hl_cb;
static int n_pr, n_run;
static int dev_port, midi_out_n;
static double idle_elapsed;
static int midi_out_assigned, master_sync;
/* PY-227 (#3655): midiOutMsg が送った 32bit word の列。dev_assigned=0 は -7・link_assigned=0 は -6 (PE 0xd747f0) */
#define NMIDI 256
static uint32_t midi_words[NMIDI];
static int midi_word_n, dev_assigned, link_assigned;
#define FCC_N 16
static int64_t fcc_last[FCC_N];
static int fcc_init;
static int sel_chan;
static const struct { const char *n; double v; } params[] = {{"Cutoff", 0.5}, {"Resonance", 0.2}, {"Gain", 0.8}};
static int changed_flag, use_metronome, precount, rec_ppq;
static int lm_pages;
static int ui_closing, ui_time_disp_min, ui_start_on_input, ui_loop_rec, ui_step_edit, ui_browser_auto_hide, ui_snap_mode;
/* PY-246 (#3759): 送出キーの記録 (PE 0x8186a0 → SendInput)。ui 送出 15 関数が書き、tests/ui_keys_diff.mjs が読む */
#define KEY_N 256
typedef struct { int vk, mod, count; } Key;
static Key keys[KEY_N];
static int key_n;
static int undo_pos, undo_count, undo_last, safe_edit;
static char proj_title[NAME], proj_author[NAME], proj_genre[NAME];
static int sel_start, sel_end, live_anchor;
static int64_t disp_time;
static int browser_op;
static int64_t arr_time;
static int scr_blanked, scr_unblank, scr_active, scr_dflt;
static int scr_alive, scr_menu_show, scr_dirty;
static int64_t scr_setup_l;
static int scr_setup_t[5];
/* PY-224 (#3628): getGridBitWithLoop の loop 行 T[G1] (G1 = 1・G2 = 24)。行の作成経路 (0x12da6d0・PY-223) は未モデルで、既定は行なし (.bss の 0)。テストは fl_engine_loop_set / fl_engine_loop_add で置く */
#define LP_N 8
#define LP_G2 24
static int lp_row, lp_flag49e, lp_flag54, lp_n;
static int64_t lp_cid[LP_N], lp_f4[LP_N], lp_len[LP_N];

static void set_name(char *dst, const char *s) { snprintf(dst, NAME, "%s", s); }
static void init_chan(Chan *c, const char *name, const char *plugin, double vol, double pan, int sel, int fx, int64_t color) {
    memset(c, 0, sizeof *c);
    set_name(c->name, name); set_name(c->plugin, plugin);
    c->vol = vol; c->pan = pan; c->sel = sel; c->fx = fx; c->color = color;
    c->pitch_n = 2; /* N の既定 2: reset 0xfe9090 (REPORT_PY72 §PY-77 受入 E)。chan との同一性は未確定 */
    for (int q = 0; q < NPARAM; q++) c->pv[q] = params[q].v;
}

/* PY-117 (#2959): 試験用。準備判定 (general.safeToEdit) の値を設定する */
void fl_engine_set_safe_edit(int v) { safe_edit = v ? 1 : 0; }

void fl_engine_reset(void) {
    nch = 3;
    grid_n = 0;
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
        for (int s = 0; s < NSLOT; s++) for (int q = 0; q < NPARAM; q++) mx[i].spv[s][q] = params[q].v;
    }
    for (int i = 0; i < NPL; i++) { memset(&pl[i], 0, sizeof pl[i]); snprintf(pl[i].name, NAME, "Track %d", i + 1); pl[i].color = 0x485156; }
    memset(win, 0, sizeof win);
    win[0] = win[2] = win[4] = 1;
    tempo = 130; playing = 0; hl_cb = 0; n_pr = n_run = 0;
    changed_flag = 0; use_metronome = 0; precount = 0; rec_ppq = 96;
    lm_pages = 0;
    key_n = 0; ui_closing = 0; ui_time_disp_min = 0; ui_start_on_input = 0; ui_loop_rec = 0; ui_step_edit = 0; ui_browser_auto_hide = 0; ui_snap_mode = 0;
    undo_pos = 0; undo_count = 0; undo_last = 0; safe_edit = 1;
    set_name(proj_title, ""); set_name(proj_author, ""); set_name(proj_genre, "");
    sel_start = -1; sel_end = -1; live_anchor = -1;
    arr_time = 0;
    scr_blanked = 0; scr_unblank = 0; scr_active = 0; scr_dflt = 0;
    scr_alive = 0; scr_menu_show = 0; scr_dirty = 0; scr_setup_l = 0; for (int i = 0; i < 5; i++) scr_setup_t[i] = 0;
    dev_port = 0; midi_out_n = 0; sel_chan = 0; disp_time = 0; browser_op = 0;
    idle_elapsed = 0; midi_out_assigned = 0; master_sync = 0;
    midi_word_n = 0; dev_assigned = 1; link_assigned = 1;
    fcc_init = 0;
    lp_row = lp_flag49e = lp_flag54 = lp_n = 0;
}
int64_t fl_engine_highlight_cb(void) { return hl_cb; }
int fl_engine_channel_count(void) { return nch; }
int fl_engine_midi_out_count(void) { return midi_out_n; }
/* 検査用の読出し口: midiOutMsg が送った word の件数と i 番目 (範囲外は -1)。tests/device_diff.mjs が mock と照合 */
int fl_engine_midi_word_count(void) { return midi_word_n; }
int64_t fl_engine_midi_word(int i) { return i < 0 || i >= midi_word_n ? -1 : (int64_t)midi_words[i]; }
/* 検査用の設定口: device 割当 (0 で -7) と送出先 (0 で -6)。既定は両方あり */
void fl_engine_set_device_link(int dev, int link) { dev_assigned = dev != 0; link_assigned = link != 0; }
/* 検査用の読出し口: 最後に作用先へ渡した時間引数 (頭打ち後)。tests/ui_display_diff.mjs が mock と照合 */
int64_t fl_engine_display_time(void) { return disp_time; }
/* 検査用の読出し口: 最後に要求した browser ノードの開閉の分岐 (0 なし・1 切替 (-1)・2 閉じる (0)・3 開く (1))。tests/ui_browser_diff.mjs が mock と照合 */
int fl_engine_browser_op(void) { return browser_op; }
/* 検査用の読出し口: チャンネル c のステップ p (範囲外は -1)。tests/midi_path_diff.mjs が副作用を比べる */
int fl_engine_grid_bit(int c, int p) {
    if (c < 0 || c >= nch || p < 0 || p >= NSTEP) return -1;
    return ch[c].steps[p];
}
/* 検査用: 行 T[1] の有無・flag49e・flag54 を置き、record を消す。record は fl_engine_loop_add で追加。上限 LP_N 件を超えた追加は 0 を返して捨てる (mock は setLoop で throw) */
void fl_engine_loop_set(int row, int flag49e, int flag54) { lp_row = row != 0; lp_flag49e = flag49e != 0; lp_flag54 = flag54 != 0; lp_n = 0; }
int fl_engine_loop_add(int cid, int f4, int len) { if (lp_n >= LP_N) return 0; lp_cid[lp_n] = cid; lp_f4[lp_n] = f4; lp_len[lp_n] = len; lp_n++; return 1; }
/* PE 0x12d3ff0 の loop 分岐 (REPORT_PY224)。行 T[1] と flag49e・flag54 が非 0 で、channel ci の最初の record (f4 != 0) が L = len / 24 を与えるとき、p < L は base(p)、それ以外は base(p mod L) (1 なら 2・0 なら 0 で、戻り値は bool に写る) */
static int grid_bit(int64_t index, const Chan *k, int32_t p);
static int grid_bit_loop(int64_t ci, const Chan *k, int32_t p) {
    int base = grid_bit(ci, k, p);
    if (!lp_row || !lp_flag49e || !lp_flag54) return base;
    for (int r = 0; r < lp_n; r++) {
        if (lp_cid[r] != ci || lp_f4[r] == 0) continue;
        int64_t L = lp_len[r] / LP_G2;
        if (L <= 0 || p < L) return base;
        return grid_bit(ci, k, (int32_t)(p % L)) ? 2 : 0;
    }
    return base;
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
/* PE 0xd5b420: 0x12d3e20 は position<0 で 0 を返す。0xd5b420 は position の範囲検査を持たず、件数以上は event 経路 (0x12d16a0・0x12df210) の値を返す (エラーにしない)。PY-218 (#3596) で event を grid_event に写した。
 * 件数 n = ceil(L/96)*4 (既定 L = 384 で 16・REPORT_PY225 PY-230 節)。境界は GRID_N (件数)。steps の配列長と setGridBit の範囲 (NSTEP) は PE 未照合のため据え置き */
static int grid_event(int64_t index, int32_t p);
static int grid_bit(int64_t index, const Chan *k, int32_t p) {
    if (p < 0) return 0;
    if (p >= GRID_N) return grid_event(index, p);
    return k->steps[p] != 0;
}
FL_H(channels, getGridBit) { CH(0); return fl_ret_b(c, grid_bit(_i, k, (int32_t)A_INT(1, 0))); }
/* PE 0xd5b360: grid (+0x7ac) は channel 生成 0xff5aa0 が直接 call する 0xff63f0 で作られ非 null。null の経路 (status 0) は直接 call の範囲では到達しない (間接呼出しは未走査・REPORT_PY101) */
FL_H(channels, isGridBitAssigned) { CH(0); (void)k; (void)A_INT(1, 0); return fl_ret_b(c, 1); }
/* PE 0xd5bc10 → 0x12d3ff0: loop 分岐は grid_bit_loop。base は grid_bit (件数以上の event 経路 PY-218) */
FL_H(channels, getGridBitWithLoop) { CH(0); return fl_ret_b(c, grid_bit_loop(_i, k, (int32_t)A_INT(1, 0))); }
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
/* PE 0xd59b40 (job 実行) → 0xd843d0: value == -1 は反転、他は現在値 (0/1) の下位 1 B と一致すれば不変・不一致なら反転。useGlobalIndex は未モデル (PE は lookup container を切替える) */
FL_H(channels, soloChannel) { CH(0); int64_t v = A_INT(1, -1); (void)A_INT(2, 0); if (v == -1 || (uint8_t)v != k->solo) k->solo = !k->solo; return fl_ret_none(c); }
FL_H(channels, getChannelVolume) { CH(0); int64_t m = A_INT(1, 0); return fl_ret_d(c, m ? db(k->vol, 0.78125) : k->vol); }
FL_H(channels, setChannelVolume) { CH(0); k->vol = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(channels, getChannelPan) { CH(0); return fl_ret_d(c, k->pan); }
FL_H(channels, setChannelPan) { CH(0); k->pan = A_DBL(1, 0); return fl_ret_none(c); }
/* PY-76 (#2563): PE 0xd5aa30 → 0xd843d0 → callback 0xd5a720 の判定順 (REPORT_PY72): index 範囲外 -4 → value の NaN -1 → pitchUnit。
 * 未モデル: guard (常に真)・useGlobalIndex (一覧 A/B は同一扱い)・unit 0/1 の効果 (効果関数 0x1046a30 の書込み条件が未確定。状態は変えない)・通知 PostMessageW。
 * unit 2 は PE どおり N = clamp(cvtsd2si(value), 1, 48) を書く */
static int64_t cvt_si64(double x) { return (x >= -9223372036854775808.0 && x < 9223372036854775808.0) ? llrint(x) : INT64_MIN; }
FL_H(channels, setChannelPitch) {
    int64_t idx = A_INT(0, 0); float v = (float)A_DBL(1, 0); int64_t unit = A_INT(2, 0);
    (void)A_INT(3, 0); (void)A_INT(4, 0);
    if (idx < 0 || idx >= nch) RANGE();
    if (isnan(v)) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error");
    if (unit == 2) { int64_t n = cvt_si64(v); ch[idx].pitch_n = n < 1 ? 1 : n > 48 ? 48 : n; }
    return fl_ret_none(c);
}
FL_H(channels, setChannelColor) { CH(0); k->color = A_INT(1, 0); return fl_ret_none(c); }
FL_H(channels, getTargetFxTrack) { CH(0); return fl_ret_i(c, k->fx); }
FL_H(channels, setTargetFxTrack) { CH(0); k->fx = (int)A_INT(1, 0); return fl_ret_none(c); }
FL_H(channels, setGridBit) {
    CH(0); int64_t p = A_INT(1, 0), v = A_INT(2, 0);
    if (p < 0 || p >= NSTEP) RANGE();
    k->steps[p] = v ? 1 : 0; if (v) k->vel[p] = 100; return fl_ret_none(c);
}
FL_H(channels, quickQuantize) { CH(0); (void)k; return fl_ret_none(c); }
FL_H(channels, selectedChannel) {
    (void)A_INT(0, 0); int64_t off = A_INT(1, 0); (void)A_INT(2, 0);
    return fl_ret_i(c, sel_chan + off);
}
FL_H(channels, fillEachNSteps) {
    CH(0); int64_t st = A_INT(1, 1), off = A_INT(2, 0), vel = A_INT(3, 100);
    (void)A_INT(4, 0);
    if (vel < 0) vel = 0; else if (vel > 127) vel = 127;
    if (st < 1) RANGE();
    int64_t p = off;
    if (p < 0) { p %= st; if (p < 0) p += st; }
    while (p < NSTEP) { k->steps[p] = 1; k->vel[p] = (uint8_t)vel; if (st > NSTEP - p) break; p += st; }
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
/* PY-100 (#2879): PE 0xd5b930 の readout。構造体は grid bit が立つ step にあるとみなす。
 * PY-111 (#2929): 生成経路を PE で確認 (REPORT_PY111.md)。setGridBit の note は 0x12d4100 の creation path で作られ、
 * param 0 = 60 (0x1062200)・1 = 100 (setGridBit が 100 を渡す)・2/3/4 = 64/120/64 (init 0x1062210)・5/6 = 128 (同 G の byte 2/3)・
 * 7 = 開始 tick = step × V (V 静的 24)・8 = 0 (0x12d42ac)。構造体が無い・param が 0..8 の外は -1 (PE: 構造体 NULL で -1) */
static const int64_t step_def[9] = {60, 100, 64, 120, 64, 128, 128, 0, 0};
static int64_t step_param(const Chan *k, int64_t pos, int64_t prm) {
    if (pos < 0 || pos >= NSTEP || !k->steps[pos] || prm < 0 || prm > 8) return -1;
    return prm == 7 ? pos * 24 : prm == 1 ? k->vel[pos] : step_def[prm];
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
/* PY-78 (#2581): PE 0x130f3d0 の項目書換え規則 (param 0..8)。項目の字段位置は PE 実測 (+0 dword, +0xc word, +0x10・+0x11・+0x12・+0x14・+0x15・+0x16・+0x17 byte)。
 * delta は先頭項目の字段から value - 字段 (param 0..7)。param 8 は value の低 8 bit を代入。項目列挙 (0x130f200) と換算用グローバルは未接続 */
typedef struct { int32_t d0; uint8_t p4[2]; uint16_t ch; int32_t len; int16_t w0c; uint8_t p2[2]; uint8_t b10, b11, b12, b13, b14, b15, b16, b17; } StepItem;
static int64_t clamp_hi(int64_t v, int64_t hi) { return v <= 0 ? 0 : v > hi ? hi : v; }
static int64_t step_item_get(const StepItem *it, int64_t prm) {
    switch (prm) {
    case 0: return it->w0c;
    case 1: return it->b15;
    case 2: return it->b12;
    case 3: return it->b10;
    case 4: return it->b14;
    case 5: return it->b16;
    case 6: return it->b17;
    case 7: return it->d0;
    case 8: return it->b11;
    default: return 0;
    }
}
static void step_item_write(StepItem *it, int64_t prm, int64_t value, int64_t delta) {
    switch (prm) {
    case 0: it->w0c = (int16_t)clamp_hi(it->w0c + delta, 0x83); break;
    case 1: it->b15 = (uint8_t)clamp_hi(it->b15 + delta, 0x80); break;
    case 2: it->b12 = (uint8_t)clamp_hi(it->b12 + delta, 0x80); break;
    case 3: it->b10 = (uint8_t)clamp_hi(it->b10 + delta, 0xf0); break;
    case 4: it->b14 = (uint8_t)clamp_hi(it->b14 + delta, 0x80); break;
    case 5: it->b16 = (uint8_t)clamp_hi(it->b16 + delta, 0xff); break;
    case 6: it->b17 = (uint8_t)clamp_hi(it->b17 + delta, 0xff); break;
    case 7: it->d0 += (int32_t)delta; break;
    case 8: it->b11 = (uint8_t)value; break;
    default: break;
    }
}
static void step_items_set(StepItem *const *items, int n, int64_t prm, int64_t value) {
    if (n <= 0 || prm < 0 || prm > 8) return;
    int64_t delta = prm == 8 ? value : value - step_item_get(items[0], prm);
    for (int i = 0; i < n; i++) step_item_write(items[i], prm, value, delta);
}
/* 検査用の読出し口: 項目 2 件に字段の初期値 seed0・seed1 を入れ、規則を 1 回適用して 2 件目の param の字段を返す。tests/step_item_diff.mjs が mock と照合 */
int fl_engine_step_item_probe(int prm, int value, int seed0, int seed1) {
    StepItem a, b, *items[2] = {&a, &b};
    memset(&a, 0, sizeof a); memset(&b, 0, sizeof b);
    step_item_write(&a, prm, 0, seed0); step_item_write(&b, prm, 0, seed1);
    step_items_set(items, 2, prm, value);
    return (int)step_item_get(&b, prm);
}
/* PY-184 (#3309): 項目列挙 PE 0x130f200 の判定式 (項目 = note)。PE の反復子 0x12df320 は cursor の先頭 dword が閾値未満の要素を返し、最初の start >= 閾値で止まる。
 * 終端 PE 0x105f2e0 = start + max(len, 1) (32bit)。V (PE の量子 [0x15e25f8]) は子 PY-185 (#3310) で確定。V <= 0 は PE 未確認のため空を返す */
static StepItem *note_next(StepItem *arr, int n, int *cur, int32_t thr) {
    if (*cur >= n || arr[*cur].d0 >= thr) return NULL;
    return &arr[(*cur)++];
}
static int32_t note_end(const StepItem *it) {
    int64_t l = it->len < 1 ? 1 : it->len;
    return (int32_t)((uint32_t)it->d0 + (uint32_t)l);
}
static int note_enum(StepItem *arr, int n, int chan, int32_t step, int32_t V, int *out) {
    if (V <= 0) return 0;
    int cur = 0, k = 0;
    StepItem *it;
    while ((it = note_next(arr, n, &cur, (int32_t)((uint32_t)step + (uint32_t)V))) != NULL) {
        int32_t sq = (int32_t)((uint32_t)(it->d0 / V) * (uint32_t)V);
        int64_t end = note_end(it);
        int64_t lo = (int32_t)((uint32_t)sq + (uint32_t)V - 1);
        if (lo > end) end = lo;
        if (step < sq || step >= (int32_t)end || (uint32_t)it->ch != (uint32_t)chan) continue;
        out[k++] = (int)(it - arr);
    }
    return k;
}
#define NOTE_PROBE_MAX 256
static StepItem note_probe_arr[NOTE_PROBE_MAX];
static int note_probe_out[NOTE_PROBE_MAX];
/* 検査用の読出し口: seed から n 件の note を決定的に作り (LCG。host/fl_mock.mjs の noteGen と同一)、chan・step・V で列挙して件数を返す。index 列は fl_engine_note_enum_out が指す。tests/note_enum_diff.mjs が mock と照合 */
int fl_engine_note_enum_probe(int seed, int n, int chan, int step, int V) {
    uint32_t s = (uint32_t)seed;
    if (n < 0) n = 0;
    if (n > NOTE_PROBE_MAX) n = NOTE_PROBE_MAX;
    for (int i = 0; i < n; i++) {
        StepItem *it = &note_probe_arr[i];
        memset(it, 0, sizeof *it);
        s = s * 1103515245u + 12345u; it->d0 = (int32_t)((s >> 16) % 200) - 50;
        s = s * 1103515245u + 12345u; it->len = (int32_t)((s >> 16) % 40) - 5;
        s = s * 1103515245u + 12345u; it->ch = (uint16_t)((s >> 16) % 4);
    }
    for (int i = 1; i < n; i++) {
        StepItem t = note_probe_arr[i];
        int j = i;
        while (j > 0 && note_probe_arr[j - 1].d0 > t.d0) { note_probe_arr[j] = note_probe_arr[j - 1]; j--; }
        note_probe_arr[j] = t;
    }
    return note_enum(note_probe_arr, n, chan, step, V, note_probe_out);
}
int *fl_engine_note_enum_out(void) { return note_probe_out; }

/* PY-218 (#3596): 件数超え (position >= NSTEP) の event 経路 PE 0x12d3e20 (REPORT_PY218.md)。pattern 1 の項目 (字段 +0 start・+6 ch・+0x13 flag) を、
 * 閾値 start < (position+1)*V (V = 24・PE [0x15e25f8])・start >= position*V (PE の lower_bound) で走査し、channel 一致・flag 0x20 無しが 1 件でもあれば 1 */
#define GRID_V 24
#define GRID_ITEM_MAX 256
static StepItem grid_items[GRID_ITEM_MAX];
static int grid_event(int64_t index, int32_t p) {
    int32_t lo = (int32_t)((uint32_t)p * GRID_V), hi = (int32_t)((uint32_t)lo + GRID_V);
    int cur = 0;
    while (cur < grid_n && grid_items[cur].d0 < lo) cur++;
    for (; cur < grid_n && grid_items[cur].d0 < hi; cur++) {
        if ((int64_t)grid_items[cur].ch == index && !(grid_items[cur].b13 & 0x20)) return 1;
    }
    return 0;
}
/* 検査用: seed から n 件の項目を決定的に作って入れる (host/fl_mock.mjs の gridGen と同一の LCG)。n = 0 で空に戻す。件数を返す。tests/channels_diff.mjs が mock と照合 */
int fl_engine_grid_items_probe(int seed, int n) {
    uint32_t s = (uint32_t)seed;
    if (n < 0) n = 0;
    if (n > GRID_ITEM_MAX) n = GRID_ITEM_MAX;
    for (int i = 0; i < n; i++) {
        StepItem *it = &grid_items[i];
        memset(it, 0, sizeof *it);
        s = s * 1103515245u + 12345u; it->d0 = (int32_t)((s >> 16) % 2000) - 200;
        s = s * 1103515245u + 12345u; it->ch = (uint16_t)((s >> 16) % 4);
        s = s * 1103515245u + 12345u; it->b13 = (uint8_t)((s >> 16) & 0xff);
    }
    for (int i = 1; i < n; i++) {
        StepItem t = grid_items[i];
        int j = i;
        while (j > 0 && grid_items[j - 1].d0 > t.d0) { grid_items[j] = grid_items[j - 1]; j--; }
        grid_items[j] = t;
    }
    grid_n = n;
    return grid_n;
}

/* ---- mixer (21) ---- */
/* 色の R/B 入替え (PY-115 / REPORT_PY115.md §2)。格納は入替え + alpha 0xff、取得は入替えを再度通して alpha 0xff。 */
/* 既定色 (フラグ無し track) は FL の .bss 0x15f6774 の初期値 (init 0x770ba6・REPORT_PY118) */
#define MIX_DEFAULT_COLOR 0xff636c71u
static uint32_t fl_swap_rb(uint32_t v) { return ((v & 0xff) << 16) | (v & 0xff00) | ((v >> 16) & 0xff); }
FL_H(mixer, trackCount) { return fl_ret_i(c, NMIX); }
/* PE 0xd641d0: ポインタ大域 0x15e2198 を読み、その指す先の dword − 2 を変換スロット 0x15e4280 に渡す (trackCount と同じ読み方・REPORT_PY205) */
FL_H(mixer, getTrackCount) { return fl_ret_i(c, NMIX - 2); }
/* PE 0xd63870: ecx=3 を変換スロット 0x15e4280 (PyLong_FromLong・REPORT_PY152 §42) に渡すのみ (REPORT_PY205) */
FL_H(mixer, getEqBandCount) { return fl_ret_i(c, 3); }
/* UTF-8 ⇄ UTF-16 (名前は UTF-8 で持つ。不正・孤立サロゲートは U+FFFD。境界の TextEncoder/TextDecoder と同じ) */
static int u8_to_u16(const char *s, uint16_t *o) {
    const unsigned char *p = (const unsigned char *)s;
    int n = 0;
    while (*p) {
        uint32_t cp = *p++;
        int k = 0;
        if (cp >= 0xc2 && cp <= 0xdf) cp &= 0x1f, k = 1;
        else if (cp >= 0xe0 && cp <= 0xef) cp &= 0x0f, k = 2;
        else if (cp >= 0xf0 && cp <= 0xf4) cp &= 0x07, k = 3;
        else if (cp >= 0x80) cp = 0xfffd;
        for (; k && (*p & 0xc0) == 0x80; k--) cp = cp << 6 | (*p++ & 0x3f);
        if (k) cp = 0xfffd;
        if (cp >= 0x10000) o[n++] = (uint16_t)(0xd800 + ((cp - 0x10000) >> 10)), o[n++] = (uint16_t)(0xdc00 + ((cp - 0x10000) & 0x3ff));
        else o[n++] = (uint16_t)cp;
    }
    return n;
}
static void u16_to_u8(const uint16_t *u, int n, char *o) {
    int k = 0;
    for (int i = 0; i < n; i++) {
        uint32_t cp = u[i];
        if (cp >= 0xd800 && cp < 0xdc00 && i + 1 < n && u[i + 1] >= 0xdc00 && u[i + 1] < 0xe000) cp = 0x10000 + ((cp - 0xd800) << 10) + (u[++i] - 0xdc00);
        else if (cp >= 0xd800 && cp < 0xe000) cp = 0xfffd;
        if (cp < 0x80) o[k++] = (char)cp;
        else if (cp < 0x800) o[k++] = (char)(0xc0 | cp >> 6), o[k++] = (char)(0x80 | (cp & 0x3f));
        else if (cp < 0x10000) o[k++] = (char)(0xe0 | cp >> 12), o[k++] = (char)(0x80 | (cp >> 6 & 0x3f)), o[k++] = (char)(0x80 | (cp & 0x3f));
        else o[k++] = (char)(0xf0 | cp >> 18), o[k++] = (char)(0x80 | (cp >> 12 & 0x3f)), o[k++] = (char)(0x80 | (cp >> 6 & 0x3f)), o[k++] = (char)(0x80 | (cp & 0x3f));
    }
    o[k] = 0;
}
/* PE 0x12be470 (maxLen > 0 のみ): PE の文字列は UTF-16 で、長さ・削除は code unit 単位 (0x12be5a4 の判定・0x414f20 の 1 unit 削除)。
 * 長さが maxLen を超える間、末尾から 1 unit ずつ見て mask 外を削除する (a-z は大文字化してから判定。mask = 0-9 と大文字子音。非 ASCII は全て mask 外)。
 * 長さが maxLen 以下になったら止め、最後に先頭 maxLen unit へ切る */
static void track_name_fit(char *s, int64_t m) {
    uint16_t u[NAME];
    char o[3 * NAME];
    int n = u8_to_u16(s, u);
    if (m <= 0 || n <= m) return;
    for (int i = n; i >= 1 && n > m; i--) {
        uint16_t ch = u[i - 1];
        if (ch >= 'a' && ch <= 'z') ch -= 0x20;
        if (ch > 0xff || !strchr("0123456789BCDFGHJKLMNPQRSTVWXYZ", ch)) {
            memmove(u + i - 1, u + i, (size_t)(n - i) * sizeof u[0]);
            n--;
        }
    }
    if (n > m) n = (int)m;
    u16_to_u8(u, n, o);
    snprintf(s, NAME, "%s", o);
}
FL_H(mixer, getTrackName) { MX(0); int64_t m = A_INT(1, -1); char b[NAME]; snprintf(b, sizeof b, "%s", t->name); track_name_fit(b, m); return fl_ret_s(c, b); }
FL_H(mixer, setTrackName) { MX(0); const char *s = A_STR(1); set_name(t->name, s); return fl_ret_none(c); }
FL_H(mixer, getTrackVolume) { MX(0); int64_t m = A_INT(1, 0); return fl_ret_d(c, m ? db(t->vol, 0.8) : t->vol); }
FL_H(mixer, setTrackVolume) { MX(0); t->vol = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(mixer, getTrackPan) { MX(0); return fl_ret_d(c, t->pan); }
FL_H(mixer, setTrackPan) { MX(0); t->pan = A_DBL(1, 0); return fl_ret_none(c); }
FL_H(mixer, setTrackColor) { MX(0); t->color = fl_swap_rb((uint32_t)A_INT(1, 0)) | 0xff000000u; t->color_set = 1; return fl_ret_none(c); }
/* PE 0xd5ec60: idx < 0 は例外を立てず int 0 を返す (警告は初回のみ・REPORT_PY118 §8.1)。idx ≥ NMIX は従来どおり RANGE (PE 上限 N-1 の実行時値は #3553) */
FL_H(mixer, getTrackColor) {
    int64_t _m = A_INT(0, 0); if (_m < 0) return fl_ret_i(c, 0); if (_m >= NMIX) RANGE();
    Mix *t = &mx[_m]; uint32_t u = t->color_set ? (uint32_t)t->color : fl_swap_rb(MIX_DEFAULT_COLOR);
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

/* ---- transport (2) / playlist (4) / ui (3 + PY-95 の 9) ---- */
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
/* PY-62 (#2027): REPORT_PY61 §2 で型・範囲 code (index 1..500 外は -4) を確定した 8 関数。
 * 既定値 (lock 0・act 0・各 live mode 0) は実機未測定の仮置き。getTrackColor は setTrackColor (PY-113) の逆変換 */
FL_H(playlist, getTrackColor) { PL(0); uint32_t u = (uint32_t)p->color; return fl_ret_i(c, (int64_t)(((u & 0xff) << 16) | (u & 0xff00) | ((u >> 16) & 0xff) | 0xff000000u)); }
FL_H(playlist, isTrackMuteLock) { PL(0); return fl_ret_b(c, p->lock != 0); }
FL_H(playlist, getTrackActivityLevelVis) { PL(0); return fl_ret_d(c, p->act); }
FL_H(playlist, getLiveLoopMode) { PL(0); return fl_ret_i(c, p->loop); }
FL_H(playlist, getLiveTriggerMode) { PL(0); return fl_ret_i(c, p->trig_mode); }
FL_H(playlist, getLivePosSnap) { PL(0); return fl_ret_i(c, p->pos_snap); }
FL_H(playlist, getLiveTrigSnap) { PL(0); return fl_ret_i(c, p->trig_snap); }
/* 表 (gen/fl_table.c・main #2927 で kwsig 'i|i' に合わせ value 引数が入った)。REPORT_PY61 §3 確定: value -1 (省略を含む) は反転、それ以外は下位 1 byte を lock に書く。
 * 準備判定 (-2) は PY-117 (#2959) で muteTrackLock に入れた */
/* PY-102 (#2883): binary 0xd56510 に従う。index 1..500 の外は RANGE (-4)、value -1 は反転、他は下位 1 byte を書く。
   PY-117 (#2959): 準備判定 (call [rax+0x98] = general.safeToEdit と同じ式) が偽なら、範囲検査より先に UNSAFE (-2) */
FL_H(playlist, muteTrackLock) { int64_t v = A_INT(1, -1); if (!safe_edit) return fl_err(c, FL_E_UNSAFE, "Operation unsafe at current time"); PL(0); p->lock = v == -1 ? !p->lock : (uint8_t)v; return fl_ret_none(c); }
#define WN(a) int64_t _w = A_INT((a), 0); if (_w < 0 || _w >= NWIN) RANGE()
FL_H(ui, getVisible) { WN(0); return fl_ret_b(c, win[_w]); }
FL_H(ui, showWindow) { WN(0); win[_w] = 1; return fl_ret_none(c); }
FL_H(ui, hideWindow) { WN(0); win[_w] = 0; return fl_ret_none(c); }
/* PY-95 (#2831): PE で状態を読んで返すだけの ui ゲッター 9 件 (REPORT_PY95)。値は未実測の仮置き。
   isMetronomeEnabled / isPrecountEnabled は general.getUseMetronome / getPrecount と同じ状態 */
FL_H(ui, isClosing) { NARGS(0, 0); return fl_ret_b(c, ui_closing); }
FL_H(ui, getTimeDispMin) { NARGS(0, 0); return fl_ret_b(c, ui_time_disp_min); }
FL_H(ui, isMetronomeEnabled) { NARGS(0, 0); return fl_ret_b(c, use_metronome); }
FL_H(ui, isPrecountEnabled) { NARGS(0, 0); return fl_ret_b(c, precount); }
FL_H(ui, isStartOnInputEnabled) { NARGS(0, 0); return fl_ret_b(c, ui_start_on_input); }
FL_H(ui, isLoopRecEnabled) { NARGS(0, 0); return fl_ret_b(c, ui_loop_rec); }
FL_H(ui, getStepEditMode) { NARGS(0, 0); return fl_ret_b(c, ui_step_edit); }
FL_H(ui, isBrowserAutoHide) { NARGS(0, 0); return fl_ret_b(c, ui_browser_auto_hide); }
FL_H(ui, getSnapMode) { NARGS(0, 0); return fl_ret_i(c, ui_snap_mode); }
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
/* PE 0xd6f2e0 (showPicker 'i|i'): 1 個目は必須、2 個目は既定 -1。署名なし (np=-1) のため個数と型はここで検査。作用先 (picker の vtbl[0x48]) は未モデル。戻り None */
FL_H(ui, showPicker) { NARGS(1, 2); (void)A_INT(0, 0); (void)A_INT(1, -1); return fl_ret_none(c); }
/* PE 0xd6ef80 (openEventEditor 'Ii|i'): 型と個数は fl_table の 'iib' (2..3) が検査する。作用先 (0xe34450) は未モデル。戻り None (PE の 0xd82c20 に status 0 を渡す経路) */
FL_H(ui, openEventEditor) { return fl_ret_none(c); }
/* PY-132 (#3013): PE 0xd6dcd0 (toggleBrowserNode '|i'・既定 -1)。作用先 0xa89690 は値 -1/0/1 で 0xa26190・0xa07d00(0)・0xa07d00(1) に分岐し、他の値は何もしない (分岐のみ。ノード状態は未モデル) */
FL_H(ui, toggleBrowserNode) { NARGS(0, 1); int64_t v = A_INT(0, -1); browser_op = v == -1 ? 1 : v == 0 ? 2 : v == 1 ? 3 : 0; return fl_ret_none(c); }
/* PE 0xd6e170 (selectBrowserMenuItem)・0xd6e330 (previewBrowserMenuItem): NOARGS。作用 (0xfdd2c0 のキー送出) は未モデル */
FL_H(ui, selectBrowserMenuItem) { NARGS(0, 0); return fl_ret_none(c); }
FL_H(ui, previewBrowserMenuItem) { NARGS(0, 0); return fl_ret_none(c); }
/* PY-119 (#2980): PE 0xd6cd80 / 0xd6ca80 / 0xd6c9d0 / 0xd6cab0 / 0xd6c4c0 / 0xd6d6b0 は呼出し経路を確定 (REPORT_PY119)。値は未実測の仮置き */
FL_H(ui, getFocused) { NARGS(1, 1); (void)A_INT(0, 0); return fl_ret_b(c, 0); }
FL_H(ui, getFocusedFormID) { NARGS(0, 0); return fl_ret_i(c, 0); }
FL_H(ui, getFocusedFormCaption) { NARGS(0, 0); return fl_ret_s(c, ""); }
FL_H(ui, getFocusedPluginName) { NARGS(0, 0); return fl_ret_s(c, ""); }
FL_H(ui, getHintMsg) { NARGS(0, 0); return fl_ret_s(c, ""); }
FL_H(ui, isInPopupMenu) { NARGS(0, 0); return fl_ret_b(c, 0); }
/* PY-129 (#3006): PE 0xd6c5b0 (setHintMsg 's')・0xd6ce50 (setFocused 'i')・0xd6b7b0 (setSnapMode 'i') は呼出し経路を確定 (REPORT_PY129)。状態は持たない (仮置き) */
FL_H(ui, setHintMsg) { NARGS(1, 1); (void)A_STR(0); return fl_ret_none(c); }
FL_H(ui, setFocused) { NARGS(1, 1); (void)A_INT(0, 0); return fl_ret_none(c); }
FL_H(ui, setSnapMode) { NARGS(1, 1); int64_t i = A_INT(0, 0); if (i < 0 || i > 14) RANGE(); return fl_ret_none(c); }
/* PY-128 (#3005): PE 0xd6c250 は状態を読まず、rodata の UTF-16 定数 "FL Studio 2026" (長さ接頭辞 14) を返す (REPORT_PY128) */
FL_H(ui, getProgTitle) { NARGS(0, 0); return fl_ret_s(c, "FL Studio 2026"); }
/* PE 0xd6cb60 は PyArg "ii" (None・文字列・実数は TypeError) の後、0x11f1a70 で (int32)(value*100) を max で割り、
 * 最近接偶数 (cvtsd2si) で整数化して "%" を付ける。状態は読まない。範囲外と NaN は INT64_MIN (REPORT_PY128) */
FL_H(ui, getHintValue) {
    NARGS(2, 2);
    for (int i = 0; i < 2; i++) if (c->a[i].tag != 'I' && c->a[i].tag != 'B') WRONGN();
    int64_t v = A_INT(0, 0), m = A_INT(1, 0);
    int32_t num = (int32_t)((uint32_t)v * 100u);
    double q = (double)num / (double)(int32_t)m;
    int64_t n = (q >= -9223372036854775808.0 && q < 9223372036854775808.0) ? (int64_t)nearbyint(q) : INT64_MIN;
    char buf[32];
    snprintf(buf, sizeof buf, "%lld%%", (long long)n);
    return fl_ret_s(c, buf);
}
/* PY-130 (#3007): PE 0xd6ee00 (setBrowserAutoHide) は O+0x8c4 に (v==1) を書く。0xd6f170 (setStepEditMode) は S=[O+0xab8] の +0x49e を (v==1) にする (末端は vtbl[0x200] 経由で未確定)。値は未実測の仮置き (REPORT_PY130_3007) */
FL_H(ui, setBrowserAutoHide) { NARGS(1, 1); ui_browser_auto_hide = A_INT(0, 0) == 1; return fl_ret_none(c); }
FL_H(ui, setStepEditMode) { NARGS(1, 1); ui_step_edit = A_INT(0, 0) == 1; return fl_ret_none(c); }
/* PY-236 (#3706): PE 0xd6cc60 は引数を読まず、gate 真なら byte [0x16bc9f2] を反転する。getTimeDispMin は同じ byte を読む (REPORT_PY236_3706) */
FL_H(ui, setTimeDispMin) { NARGS(0, 0); ui_time_disp_min = !ui_time_disp_min; return fl_ret_none(c); }
/* PY-130: ui 版 getVersion (PE 0xd6c2f0 '|i'・既定 4) は mode 0..3 で int、4..6 で str、他は int 0 (分岐表は REPORT_PY130_3007) */
FL_H(ui, getVersion) { NARGS(0, 1); int64_t m = A_INT(0, 4); return (m >= 4 && m <= 6) ? fl_ret_s(c, "") : fl_ret_i(c, 0); }
/* PY-246 (#3759): 送出キー 15 関数。VK・修飾 (1 Shift・2 Alt・4 Ctrl)・回数は PE 0xfdd2c0 の leaf → 0x8186a0 (REPORT_PY140)。
 * 送出の成否のゲートは PY-245 (#3758) で未確定のため、送出 leaf に入った経路を記録する。戻り値は PY-141 (#3034) で未確定 (仮置き 0) */
static void key_send(int vk, int mod, int64_t count) {
    if (count <= 0 || key_n >= KEY_N) return;
    if (count > 0x7fffffff) count = 0x7fffffff;
    keys[key_n].vk = vk; keys[key_n].mod = mod; keys[key_n].count = (int)count; key_n++;
}
int fl_engine_key_n(void) { return key_n; }
int fl_engine_key_get(int i, int f) { if (i < 0 || i >= key_n) return -1; return f == 0 ? keys[i].vk : f == 1 ? keys[i].mod : keys[i].count; }
void fl_engine_key_clear(void) { key_n = 0; }
FL_H(ui, up) { NARGS(0, 1); key_send(0x26, 0, A_INT(0, 1)); return fl_ret_i(c, 0); }
FL_H(ui, down) { NARGS(0, 1); key_send(0x28, 0, A_INT(0, 1)); return fl_ret_i(c, 0); }
FL_H(ui, left) { NARGS(0, 1); key_send(0x25, 0, A_INT(0, 1)); return fl_ret_i(c, 0); }
FL_H(ui, right) { NARGS(0, 1); key_send(0x27, 0, A_INT(0, 1)); return fl_ret_i(c, 0); }
FL_H(ui, cut) { NARGS(0, 0); key_send(0x58, 4, 1); return fl_ret_i(c, 0); }
FL_H(ui, copy) { NARGS(0, 0); key_send(0x43, 4, 1); return fl_ret_i(c, 0); }
FL_H(ui, paste) { NARGS(0, 0); key_send(0x56, 4, 1); return fl_ret_i(c, 0); }
FL_H(ui, insert) { NARGS(0, 0); key_send(0x2d, 0, 1); return fl_ret_i(c, 0); }
FL_H(ui, delete) { NARGS(0, 0); key_send(0x2e, 0, 1); return fl_ret_i(c, 0); }
FL_H(ui, enter) { NARGS(0, 0); key_send(0x0d, 0, 1); return fl_ret_i(c, 0); }
FL_H(ui, escape) { NARGS(0, 0); key_send(0x1b, 0, 1); return fl_ret_i(c, 0); }
FL_H(ui, yes) { NARGS(0, 0); key_send(0x59, 0, 1); return fl_ret_i(c, 0); }
FL_H(ui, no) { NARGS(0, 0); key_send(0x4e, 0, 1); return fl_ret_i(c, 0); }
FL_H(ui, nextWindow) { NARGS(0, 0); key_send(0x09, 0, 1); return fl_ret_i(c, 0); }
/* PE: arg > 0 で修飾 0 (Tab)、arg <= 0 で Shift (修飾 1) + Tab。stub の引数名 shift と符号が逆 (REPORT_PY140 の未解決) */
FL_H(ui, selectWindow) { NARGS(1, 1); key_send(0x09, A_INT(0, 0) > 0 ? 0 : 1, 1); return fl_ret_i(c, 0); }

/* ---- general (1) ---- mock と同じ MIDI scripting API バージョン (実機値は未実測) */
FL_H(general, getVersion) { NARGS(0, 0); return fl_ret_i(c, 1); }
/* PY-87 (#2738): PE 0xd69800/0xd69820/0xd69840/0xd69330 は状態 1 つを読んで変換スロット 0x15e4280 に渡すだけ。値は未実測の仮置き (REPORT_PY87) */
FL_H(general, getChangedFlag) { NARGS(0, 0); return fl_ret_i(c, changed_flag); }
FL_H(general, getUseMetronome) { NARGS(0, 0); return fl_ret_b(c, use_metronome); }
FL_H(general, getPrecount) { NARGS(0, 0); return fl_ret_b(c, precount); }
FL_H(general, getRecPPQ) { NARGS(0, 0); return fl_ret_i(c, rec_ppq); }
/* PY-94 (#2830): PE 0xd69a90/0xd69ab0/0xd69ad0 は状態の dword 1 つを読んで 0x15e4280 に渡す。0xd6a2c0 は vtbl[0x98] の bool。
   0xd6a2f0/0xd6a3a0/0xd6a450 は project 物 (*(G)+0x10) の vtbl 0x20/0x28/0x30 から文字列を得る。値は未実測の仮置き (REPORT_PY94) */
FL_H(general, getUndoHistoryPos) { NARGS(0, 0); return fl_ret_i(c, undo_pos); }
FL_H(general, getUndoHistoryCount) { NARGS(0, 0); return fl_ret_i(c, undo_count); }
FL_H(general, getUndoHistoryLast) { NARGS(0, 0); return fl_ret_i(c, undo_last); }
FL_H(general, safeToEdit) { NARGS(0, 0); return fl_ret_b(c, safe_edit); }
FL_H(general, getProjectTitle) { NARGS(0, 0); return fl_ret_s(c, proj_title); }
FL_H(general, getProjectAuthor) { NARGS(0, 0); return fl_ret_s(c, proj_author); }
FL_H(general, getProjectGenre) { NARGS(0, 0); return fl_ret_s(c, proj_genre); }
/* PY-125 (#3001): PE 0xd6a1f0 (clearLog) と 0xd6a060 (dumpScoreLog) は、成功経路 (述語 P 真・gate 真) で dispatch 0xd843d0 を経て None を返す (REPORT_PY125 §4)。効果は API から観測できないため状態を持たない */
FL_H(general, clearLog) { NARGS(0, 0); return fl_ret_none(c); }
FL_H(general, dumpScoreLog) { NARGS(1, 2); (void)A_INT(0, 0); (void)A_INT(1, 0); return fl_ret_none(c); }
/* PY-235 (#3701): 成功経路 (gate 0 を仮定) は戻り値 = value (int32)。family の定義は host/fl_mock.mjs の recPassFamily と同一 (REPORT_PY235) */
static int rec_pass_family(uint32_t e, uint32_t f) {
    return (e & 0xffff) != 8 && ((e >= 0x10000000u && e < 0x40000000u) || (e >= 0x40000003u && e <= 0x40000004u) || (e > 0x40000005u && e < 0x70000000u) || e >= 0xf0000000u || ((e == 0x40000000u || e == 0x40000001u || e == 0x40000002u || e == 0x40000005u) && (f & 0x22u) == 0));
}
/* PY-146 (#2544): channels 版 0xd58e00 は general 版と同じ 0xd84740 → 0x1046a30 (REPORT_PY146)。成功経路は PY-235 と同じ */
FL_H(channels, processRECEvent) {
    NARGS(3, 3);
    uint32_t e = (uint32_t)A_INT(0, 0);
    int64_t v = A_INT(1, 0);
    uint32_t f = (uint32_t)A_INT(2, 0);
    if (!rec_pass_family(e, f)) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error (not implemented: channels.processRECEvent)");
    return fl_ret_i(c, (int32_t)v);
}
FL_H(general, processRECEvent) {
    NARGS(3, 3);
    uint32_t e = (uint32_t)A_INT(0, 0);
    int64_t v = A_INT(1, 0);
    uint32_t f = (uint32_t)A_INT(2, 0);
    if (!rec_pass_family(e, f)) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error (not implemented: general.processRECEvent)");
    return fl_ret_i(c, (int32_t)v);
}
/* PY-119 (#2977): PE 0xd69350/0xd694e0/0xd69670 は範囲外で status -3 (Range error)。ゲートは未確定のため真と仮定 (REPORT_PY119_2977) */
static int numerator = 4, denominator = 4;
FL_H(general, setRecPPQ) { NARGS(1, 1); int64_t v = A_INT(0, 0); if (v < 24 || v > 960) RANGE_MSG("Range error"); rec_ppq = (int)v; return fl_ret_none(c); }
FL_H(general, setNumerator) { NARGS(1, 1); int64_t v = A_INT(0, 0); if (v < 1 || v > 16) RANGE_MSG("Range error"); numerator = (int)v; return fl_ret_none(c); }
FL_H(general, setDenominator) { NARGS(1, 1); int64_t v = A_INT(0, 0); if (v < 2 || v > 16) RANGE_MSG("Range error"); denominator = (int)v; return fl_ret_none(c); }
/* undo 3 件: PE 0xd69af0 は範囲検査なし (kind 0=Pos → +0x1c, 1=Count → +0x24, 2=Last → +0x20)。getter と同じ変数に書く */
FL_H(general, setUndoHistoryPos) { NARGS(1, 1); undo_pos = (int)A_INT(0, 0); return fl_ret_none(c); }
FL_H(general, setUndoHistoryCount) { NARGS(1, 1); undo_count = (int)A_INT(0, 0); return fl_ret_none(c); }
FL_H(general, setUndoHistoryLast) { NARGS(1, 1); undo_last = (int)A_INT(0, 0); return fl_ret_none(c); }

/* ---- launchMapPages (1 of 12, PY-120 #2984) ---- PE 0xd791b0: obj.+0x50 の配列 (+0x3c0) の件数を返す。件数は仮置き 0 (REPORT_PY120_2984)。
 * obj.+0x50 == 0 の経路 (0xd82c20 に code -7 = "Device not assigned") は未モデル (例外化の述語が実行時値のため) */
FL_H(launchMapPages, length) { NARGS(0, 0); return fl_ret_i(c, lm_pages); }
/* ---- launchMapPages (3 of 12, PY-138 #3029) ---- PE init 0xd79020 (sii)・updateMap 0xd79290 (i)・createOverlayMap 0xd7a130 (iiii) は書式と成功時の戻り (定数 = None) を確定。
 * page 配列への副作用は未確定のため状態を変えない (REPORT_PY138)。 */
FL_H(launchMapPages, init) { NARGS(3, 3); (void)A_STR(0); (void)A_INT(1, 0); (void)A_INT(2, 0); return fl_ret_none(c); }
FL_H(launchMapPages, updateMap) { NARGS(1, 1); (void)A_INT(0, 0); return fl_ret_none(c); }
FL_H(launchMapPages, createOverlayMap) { NARGS(4, 4); for (int i = 0; i < 4; i++) (void)A_INT(i, 0); return fl_ret_none(c); }
/* ---- launchMapPages (PY-243 #3745) ---- PE 0xd7a3a0 は書式 iii・成功時の戻り None (REPORT_PY243)。項目書込みは項目の状態を持たないため状態を変えない */
FL_H(launchMapPages, setMapItemTarget) { NARGS(3, 3); for (int i = 0; i < 3; i++) (void)A_INT(i, 0); return fl_ret_none(c); }

/* ---- arrangement (4, PY-96 #2832) ---- PE 0xd786e0/0xd78700/0xd78500 が obj+0xd74/+0xd78 を読み、0xd78720 は 0xe43e80 (両方 >= 0) を bool で返す。初期値 -1 は未実測の仮置き */
FL_H(arrangement, selectionStart) { NARGS(0, 0); return fl_ret_i(c, sel_start); }
FL_H(arrangement, selectionEnd) { NARGS(0, 0); return fl_ret_i(c, sel_end); }
FL_H(arrangement, liveSelectionStart) { NARGS(0, 0); return fl_ret_i(c, sel_start); }
FL_H(arrangement, selectionIsActive) { NARGS(0, 0); return fl_ret_b(c, sel_start >= 0 && sel_end >= 0); }
/* ---- arrangement (6) ---- PY-152 (#2983): 呼出し構造と PyArg 書式は PE で確定。個数は fl_table (stub 由来・必須 2) に合わせた暫定で、
 * jumpToMarker は PE (必須 1) と不一致 (REPORT_PY152 未解決)。currentTime は仮置きの状態 arr_time を返す。
 * 選択の 2 件は sel_set (PE 0xe43d30 の規則・PY-144 #3043) で状態を変える。マーカー・liveSelection・jumpToMarker の 3 件は副作用が未同定のため状態を変えず、引数検査だけ行う (REPORT_PY152) */
static void sel_set(int x, int y) { sel_start = x; sel_end = y; if (x == y) sel_end = -1; else if (x > y) { sel_start = y; sel_end = x; } }
FL_H(arrangement, currentTime) { (void)A_INT(0, 0); return fl_ret_i(c, arr_time); }
FL_H(arrangement, selectionClear) { NARGS(0, 0); sel_set(-1, -1); return fl_ret_none(c); }
FL_H(arrangement, selectionSet) { NARGS(2, 5); int64_t x = A_INT(0, 0), y = A_INT(1, 0); for (int i = 2; i < 5; i++) (void)A_INT(i, 0); sel_set((int)x, (int)y); return fl_ret_none(c); }
static void live_sel(int a, int flag) { int anc = live_anchor; if (flag && anc >= 0 && anc != a) sel_set(anc, a); else sel_set(-1, -1); live_anchor = flag ? -1 : a; }
FL_H(arrangement, liveSelection) { NARGS(2, 2); int64_t a = A_INT(0, 0), b = A_INT(1, 0); live_sel((int)a, b == 1); return fl_ret_none(c); }
FL_H(arrangement, addAutoTimeMarker) { (void)A_INT(0, 0); (void)A_STR(1); return fl_ret_none(c); }
FL_H(arrangement, jumpToMarker) { (void)A_INT(0, 0); (void)A_INT(1, 0); return fl_ret_none(c); }
/* ---- arrangement (2) ---- PY-143 (#3041): PE 0xd78030 (getMarkerName)・0xd785a0 (currentTimeHint) の呼出し構造と戻り str は REPORT_PY143 で確定。
 * マーカー表は件数 0 の仮置き (addAutoTimeMarker の副作用は未同定のため登録しない)。範囲外は空文字。
 * currentTimeHint の BBT 分解 (PE 0x1312080) は未同定のため、PPQ 96・4 拍子の仮置きで bar:beat:tick を返す (mock と同じ) */
FL_H(arrangement, getMarkerName) { NARGS(1, 1); (void)A_INT(0, 0); return fl_ret_s(c, ""); }
FL_H(arrangement, currentTimeHint) {
  NARGS(2, 4);
  (void)A_INT(0, 0);
  int64_t t = A_INT(1, 0);
  (void)A_INT(2, rec_ppq);
  int zb = A_INT(3, 0) == 1;
  int64_t per = 4 * 96, bar = t / per, beat = (t % per) / 96, tick = t % 96;
  char b[64];
  snprintf(b, sizeof b, "%lld:%lld:%lld", (long long)(bar + !zb), (long long)(beat + !zb), (long long)tick);
  return fl_ret_s(c, b);
}
/* ---- patterns (2 of 4, PY-172 #3219): PE 0xd67000 は配列 null で 0・非 null で ptr-8 の件数を返す。0xd67030 は索引 [0, 件数-1] の外を status -4。
 * グループ配列の実状態は未実測のため、件数 0 (null の経路) を仮置きする。件数 0 では全索引が範囲外 (REPORT_PY172) */
#define PGRP_N 0
FL_H(patterns, getPatternGroupCount) { NARGS(0, 0); return fl_ret_i(c, PGRP_N); }
FL_H(patterns, getPatternGroupName) { NARGS(1, 1); int64_t i = A_INT(0, 0); if (i < 0 || i >= PGRP_N) RANGE(); return fl_ret_s(c, ""); }
FL_H(patterns, getActivePatternGroup) { NARGS(0, 0); return fl_ret_i(c, -1); }
/* ---- patterns (4, PY-179 #3271): 述語 pred の E = 0x193fce0+i*0xc0 は .bss で未投入 (全 0) のため pred は偽。patternCount は ¬pred を i=1..999 で数えて 999。
 * patternNumber は slot 0x15e4018 → 0x15d51a0 の dword の PE 初期値 1 (1 始まり)。isPatternDefault の範囲外は status -4 = FL_E_RANGE。
 * isPatternSelected は G = [[0x15e35c8]+0xd34] の静的値 0 (null) で [0x16b82e0] (.bss 0) を返す = 偽。値は未実測の仮置き (REPORT_PY179) */
#define PAT_N 999
#define PAT_NUMBER 1
FL_H(patterns, patternCount) { NARGS(0, 0); return fl_ret_i(c, PAT_N); }
FL_H(patterns, patternNumber) { NARGS(0, 0); return fl_ret_i(c, PAT_NUMBER); }
FL_H(patterns, isPatternDefault) { NARGS(1, 1); int64_t i = A_INT(0, 0); if (i < 1 || i > PAT_N) RANGE(); return fl_ret_b(c, 0); }
FL_H(patterns, isPatternSelected) { NARGS(1, 1); (void)A_INT(0, 0); return fl_ret_b(c, 0); }
/* ---- screen (5) ---- PY-121 (#2985): PE 0xd7c7e0・0xd7c830・0xd7c880・0xd7c8c0・0xd7c740 (REPORT_PY121_2985)。値は未実測の仮置き */
FL_H(screen, isBlanked) { NARGS(0, 0); return fl_ret_b(c, scr_blanked); }
FL_H(screen, isUnBlank) { NARGS(0, 0); return fl_ret_b(c, scr_unblank); }
FL_H(screen, getScreenActiveCounter) { NARGS(0, 0); return fl_ret_i(c, scr_active); }
FL_H(screen, setScreenActiveCounter) { NARGS(1, 1); scr_active = (int)((unsigned)scr_active + (unsigned)A_INT(0, 0)); return fl_ret_none(c); }
FL_H(screen, unBlank) { NARGS(1, 1); scr_unblank = A_INT(0, 0) == 1; return fl_ret_none(c); }
/* ---- screen 描画・メーター系 (7) ---- PY-135 (#3022): PE 0xd7ada0・0xd7b690・0xd7ae80・0xd7af40・0xd7bcb0・0xd7bec0・0xd7c600 (REPORT_PY135)。addMeter 以外は状態を持たない */
/* addMeter: 成功経路 (rc>0・scr≠0) で PE 0xd7d9e0 が isUnBlank を真にし activeCounter を scr+0x1dc (仮置き 0) にする。A_INT は失敗で返るので解析失敗は状態を変えない */
FL_H(screen, addMeter) { NARGS(4, 5); for (int i = 0; i < 4; i++) (void)A_INT(i, 0); (void)A_INT(4, 0); scr_unblank = 1; scr_active = scr_dflt; return fl_ret_none(c); }
/* addTextLine (#5328): 書式 siiii。成功経路 (scr≠0) で PE 0xd7d460 の副作用 scr+0x1cc←scr+0x1dc・scr+0x1d1←1 を模す。行 record は未確定のため模さない (REPORT_PY5328) */
FL_H(screen, addTextLine) { NARGS(5, 5); (void)A_STR(0); for (int i = 1; i < 5; i++) (void)A_INT(i, 0); if (scr_alive) { scr_active = scr_dflt; scr_unblank = 1; } return fl_ret_none(c); }
FL_H(screen, displayBar) { NARGS(5, 5); (void)A_INT(0, 0); (void)A_INT(1, 0); (void)A_STR(2); (void)A_DBL(3, 0); (void)A_INT(4, 0); return fl_ret_none(c); }
FL_H(screen, fillRect) { NARGS(5, 5); for (int i = 0; i < 5; i++) (void)A_INT(i, 0); return fl_ret_none(c); }
FL_H(screen, drawRect) { NARGS(5, 5); for (int i = 0; i < 5; i++) (void)A_INT(i, 0); return fl_ret_none(c); }
FL_H(screen, drawText) { NARGS(6, 6); (void)A_INT(0, 0); (void)A_STR(1); for (int i = 2; i < 6; i++) (void)A_INT(i, 0); return fl_ret_none(c); }
FL_H(screen, eraseRect) { NARGS(4, 4); for (int i = 0; i < 4; i++) (void)A_INT(i, 0); return fl_ret_none(c); }
/* blank: 第 1 引数が 1 なら isBlanked を真に書く。真→偽の解除では activeCounter を scr+0x1dc (仮置き 0) から戻す (REPORT_PY135) */
FL_H(screen, blank) { NARGS(2, 2); int b = A_INT(0, 0) == 1; (void)A_INT(1, 0); if (b != scr_blanked) { if (!b) scr_active = scr_dflt; scr_blanked = b; } return fl_ret_none(c); }
/* ---- screen 初期化・メニュー系 (10) ---- PY-136 (#3025): PE 0xd7aa40・0xd7ab00・0xd7b0a0・0xd7b000・0xd7ccb0・0xd7b1f0・0xd7b170・0xd7c9a0・0xd7cac0・0xd7cbe0 (REPORT_PY136)。
   scr は init で生成し deInit で破棄する。scr 未生成の経路は PE で AV (例外を返さない) なので Unspecified error を仮置き */
#define SCR_NEED() do { if (!scr_alive) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error"); } while (0)
static void scr_new(void) {
    static const int def[5] = {30, 10, 10, 2, 4000};
    scr_alive = 1; scr_dirty = 0; scr_menu_show = 0; scr_setup_l = 0;
    for (int i = 0; i < 5; i++) scr_setup_t[i] = def[i];
}
FL_H(screen, init) { NARGS(6, 6); scr_new(); return fl_ret_none(c); }
FL_H(screen, setup) { NARGS(6, 6); SCR_NEED(); scr_setup_l = A_INT(0, 0); for (int i = 0; i < 5; i++) scr_setup_t[i] = (int)A_INT(i + 1, 0); return fl_ret_none(c); }
FL_H(screen, update) { NARGS(0, 0); if (scr_alive) scr_dirty = 0; return fl_ret_none(c); }
FL_H(screen, deInit) { NARGS(0, 0); scr_alive = 0; scr_dirty = 0; scr_menu_show = 0; return fl_ret_none(c); }
FL_H(screen, keepDisplayActive) { NARGS(0, 0); if (scr_alive) scr_dirty = 1; return fl_ret_none(c); }
FL_H(screen, hideMenu) { NARGS(0, 0); SCR_NEED(); scr_menu_show = 0; return fl_ret_none(c); }
FL_H(screen, menuShowing) { NARGS(0, 0); SCR_NEED(); return fl_ret_b(c, scr_menu_show); }
/* メニュー項目の選択・移動は PE で scr 有りのときだけ helper を呼ぶ。helper の効果は未同定 (REPORT_PY136) */
FL_H(screen, menuItemClick) { NARGS(0, 0); return fl_ret_none(c); }
FL_H(screen, menuNext) { NARGS(0, 0); return fl_ret_none(c); }
FL_H(screen, menuPrev) { NARGS(0, 0); return fl_ret_none(c); }

/* ---- device (5, MIDI scripting 用の最小面) ---- mock と同じ: forwardMIDICC / midiOutMsg は呼出しを数える */
FL_H(device, getPortNumber) { return fl_ret_i(c, dev_port); }
FL_H(device, isAssigned) { return fl_ret_b(c, 1); }
FL_H(device, setHasMeters) { return fl_ret_none(c); }
/* PE 0xd747f0 (midiOutMsg) と PE 0xd748e0 (forwardMIDICC) の共通判定: device 無し → -7、送出先無し → -6 (送出の前に判定)。0 なら通過 */
static int midi_check(fl_call *c) {
    if (!dev_assigned) return fl_err(c, FL_E_DEVICE, "Device not assigned");
    if (!link_assigned) return fl_err(c, FL_E_LINKED_DEVICE, "Linked device not assigned");
    return 0;
}
/* 判定を通った word を送出として記録する */
static int midi_record(fl_call *c, uint32_t w) {
    midi_out_n++;
    if (midi_word_n < NMIDI) midi_words[midi_word_n++] = w;
    return fl_ret_none(c);
}
static int midi_send(fl_call *c, uint32_t w) {
    int r = midi_check(c);
    if (r != 0) return r;
    return midi_record(c, w);
}
/* PY-215 (#3568): PE 0xd75d30 (書式 'I'、引数 1)。-1 は -1 を返す (0xd75dc0)。それ以外は連動表を末尾から走査し、一致が無い・表が空なら status 1 → None (0xd75dce)。device・link の割当は見ない (-6/-7 経路なし)。表の供給元は未確定のため空と仮定 (REPORT_PY215 §3) */
FL_H(device, getLinkedChannel) { int64_t i = A_INT(0, 0); if (i == -1) return fl_ret_i(c, -1); return fl_ret_none(c); }
/* PY-4846 (#3568 子 B): PE 0xd75bc0 (getLinkedValue)・0xd75ed0 (getLinkedInfo)・0xd75de0 (getLinkedParamName)・0xd75c40 (getLinkedValueString) の index == -1 経路だけを確定 (REPORT_PY215 §1 の表)。index >= 0 は連動表・helper (0x1051170・0x1050f90・0x104f580・0x1046a30) が未確定のため未実装 */
#define LINK_UNIMPL(name) return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error (not implemented: device." name " index>=0)")
FL_H(device, getLinkedValue) { int64_t i = A_INT(0, 0); if (i == -1) return fl_ret_d(c, -1.0); LINK_UNIMPL("getLinkedValue"); }
FL_H(device, getLinkedInfo) { int64_t i = A_INT(0, 0); if (i == -1) return fl_ret_i(c, -1); LINK_UNIMPL("getLinkedInfo"); }
FL_H(device, getLinkedParamName) { int64_t i = A_INT(0, 0); if (i == -1) return fl_err(c, FL_E_PLUGIN, "Plugin not valid"); LINK_UNIMPL("getLinkedParamName"); }
FL_H(device, getLinkedValueString) { int64_t i = A_INT(0, 0); if (i == -1) return fl_err(c, FL_E_PLUGIN, "Plugin not valid"); LINK_UNIMPL("getLinkedValueString"); }
/* PY-260 (#3840) / PY-390 (#4830): PE 0xd75b60 (書式 "i|i"・引数 2 つは型だけ見る)。成功経路の表 (helper 0xf8c8e0 の表 0x16bacb8) は供給元未確定のため空と仮定し、未発見の -1 を返す (PE 確定・REPORT_PY390 §7)。device の割当は見ない */
FL_H(device, findEventID) { NARGS(1, 2); (void)A_INT(0, 0); (void)A_INT(1, 0); return fl_ret_i(c, -1); }
/* PY-260 (#3840) / PY-390 (#4830): PE 0xd76060 (書式 "i")。device 無し (sub object 0) は status -7 (PE 確定)。準備判定 (0x11d1430) は真と仮定。device 有りの値 (plugin の vtbl+0x80) は未確定のため未実装 */
FL_H(device, isDoubleClick) {
    NARGS(1, 1); (void)A_INT(0, 0);
    if (!dev_assigned) return fl_err(c, FL_E_DEVICE, "Device not assigned");
    return fl_err(c, FL_E_UNSPECIFIED, "Unspecified error (not implemented: device.isDoubleClick assigned)");
}
/* PY-5407 (#5947): PE 0xd762f0 (repeatMidiEvent, 書式 "O|ii"・delay/rate は既定 300) と 0xd764a0 (stopRepeatMidiEvent・引数なし)。
   dispatch 0xd843d0 の callback (0xd76190 / 0xd76450) は述語 0x11d1430 が真のとき assigned (obj+0x50) の vtbl を呼ぶ。assigned 無し → status -7 (0xd82c20)。
   述語は真と仮定。vtbl 先の効果 (repeat の 0x90・stop の 0x88) は未読のため状態を持たない */
FL_H(device, repeatMidiEvent) { NARGS(1, 3); (void)A_INT(1, 300); (void)A_INT(2, 300); if (!dev_assigned) return fl_err(c, FL_E_DEVICE, "Device not assigned"); return fl_ret_none(c); }
FL_H(device, stopRepeatMidiEvent) { NARGS(0, 0); if (!dev_assigned) return fl_err(c, FL_E_DEVICE, "Device not assigned"); return fl_ret_none(c); }
FL_H(device, createRefreshThread) { return fl_ret_none(c); }
FL_H(device, destroyRefreshThread) { return fl_ret_none(c); }
FL_H(device, fullRefresh) { return fl_ret_none(c); }
FL_H(device, getIdleElapsed) { return fl_ret_d(c, idle_elapsed); }
FL_H(device, isMidiOutAssigned) { return fl_ret_b(c, midi_out_assigned); }
FL_H(device, getMasterSync) { return fl_ret_b(c, master_sync); }
FL_H(device, setMasterSync) { master_sync = A_INT(0, 0) == 1; return fl_ret_none(c); }
/* PE 0xd75120 (書式 "L|i"・第 2 引数の既定 1 は解析前に PE が書く・REPORT_PY231 §1b)。送るのは第 1 引数の word。第 2 引数は送出先テーブルの添字 (PE 0xfdc8a0)。
   0xfdc8a0 は [sink+0x5c+4*添字] と同じ 32bit 値なら送らず、変わったときだけ送ってテーブルを書く (REPORT_PY231 §1)。
   テーブルの初期値と添字の範囲は未確定 (#3949): 未設定 (-1) を初期値とみなし、範囲外の添字は重複検出せず送る仮置き */
FL_H(device, forwardMIDICC) {
    int64_t msg = A_INT(0, 0), idx = A_INT(1, 1);
    uint32_t w = (uint32_t)msg;
    if (!fcc_init) { for (int i = 0; i < FCC_N; i++) fcc_last[i] = -1; fcc_init = 1; }
    if (idx < 0 || idx >= FCC_N) return midi_send(c, w);
    int r = midi_check(c);
    if (r != 0) return r;
    if (fcc_last[idx] == (int64_t)w) return fl_ret_none(c);
    fcc_last[idx] = (int64_t)w;
    return midi_record(c, w);
}
/* PE 0xd747f0 (書式 i|iiii)。channel ≤ -1 は message だけ、channel ≥ 0 は arg4 を bit 24–31 に入れた word を送る */
FL_H(device, midiOutMsg) {
    int64_t msg = A_INT(0, 0), ch = A_INT(1, -1), d1 = A_INT(2, 0), d2 = A_INT(3, 0), a4 = A_INT(4, 0);
    uint32_t w = (uint32_t)msg;
    if (ch >= 0) w = ((uint32_t)(ch & 0xf) | w) + ((uint32_t)d1 << 8) + ((uint32_t)d2 << 16) + ((uint32_t)a4 << 24);
    return midi_send(c, w);
}

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
FL_H(plugins, getParamName) { int64_t q = A_INT(0, 0); return fl_ret_s(c, (q >= 0 && q < NPARAM) ? params[q].n : ""); }
/* PY-228 (#3656): getParamValue / getParamValueString / setParamValue の解決 (PE 0xd7fda0・0xd7f940・0xd80160 と同じ順)。
 * slot == -1: index は channel (0x1005730)。slot >= 0: index は mixer track [0, NMIX)、slot は [0, NSLOT)、空 slot は code 8 (0x132f780)。
 * paramIndex は [0, count) (count = [obj+0x68] = NPARAM)。useGlobalIndex は group 配列 A/B (0x1005730 の dl) の選択だが、
 * group 無しの model では両方とも identity (REPORT_PY228)。 */
static int pinst(fl_call *c, int64_t index, int64_t slot, int64_t q, double **out) {
    if (slot == -1) {
        if (index < 0 || index >= nch) return fl_err(c, FL_E_RANGE, "Index out of range");
        if (q < 0 || q >= NPARAM) return fl_err(c, FL_E_RANGE, "Index out of range");
        *out = &ch[index].pv[q];
        return 0;
    }
    if (index < 0 || index >= NMIX || slot < 0 || slot >= NSLOT) return fl_err(c, FL_E_RANGE, "Index out of range");
    if (!mx[index].slots[slot][0]) return fl_err(c, FL_E_PLUGIN, "Plugin not valid");
    if (q < 0 || q >= NPARAM) return fl_err(c, FL_E_RANGE, "Index out of range");
    *out = &mx[index].spv[slot][q];
    return 0;
}
FL_H(plugins, getParamValue) {
    int64_t q = A_INT(0, 0), i = A_INT(1, 0), s = A_INT(2, -1); (void)A_INT(3, 0);
    double *v; int r = pinst(c, i, s, q, &v); if (r) return r;
    return fl_ret_d(c, *v);
}
FL_H(plugins, getParamValueString) {
    int64_t q = A_INT(0, 0), i = A_INT(1, 0), s = A_INT(2, -1); (void)A_INT(3, 0);
    double *v; int r = pinst(c, i, s, q, &v); if (r) return r;
    char b[48]; snprintf(b, sizeof b, "%.1f %%", *v * 100); return fl_ret_s(c, b);
}
FL_H(plugins, setParamValue) {
    double x = A_DBL(0, 0);
    int64_t q = A_INT(1, 0), i = A_INT(2, 0), s = A_INT(3, -1); (void)A_INT(4, 0); (void)A_INT(5, 0);
    double *v; int r = pinst(c, i, s, q, &v); if (r) return r;
    *v = x; return fl_ret_none(c);
}

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
    set_name(mx[t].slots[s], pn);
    for (int q = 0; q < NPARAM; q++) mx[t].spv[s][q] = params[q].v;
    return fl_ret_b(c, 1);
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
