/* flmidi_winmm.c — winmm midiIn と midiOut 20 関数の Web MIDI 実体。設計は docs/PROTOCOL.md §9, flmidi_winmm.h
 *
 * スレッド: FL スレッド (API 呼出) / MIDI スレッド (専用 pthread, ring 消費 + CALLBACK_FUNCTION の呼出元 + 出力完了通知) / JS (Web MIDI)。
 * ロック順序: g_cb (再帰) → g_lock。コールバックは g_cb を保持して呼ぶ → midiInClose/Reset は復帰後に「進行中コールバックが無い」ことを保証 (winmm の契約)。
 * 入力ポリシー: midiInStart 前 / Stop 後 / Start より古い timestamp / 閉じた slot / gen 違い宛のデータは捨てて計数 (winmm と同じく蓄積しない)。 */
#include "flmidi_winmm.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LD(x) __atomic_load_n(&(x), __ATOMIC_SEQ_CST)
#define ST(x, v) __atomic_store_n(&(x), (v), __ATOMIC_SEQ_CST)
#define INC(x) __atomic_add_fetch(&(x), 1, __ATOMIC_SEQ_CST)

#define H_IN  0x80000000u
#define H_OUT 0x40000000u

typedef struct {
    int used; uint32_t gen, key; uintptr_t cb, inst; uint32_t flags; int started; double start_ms;
    flm_midihdr_t *q_head, *q_tail;
} in_slot_t;
typedef struct { int used; uint32_t gen, key; uintptr_t cb, inst; uint32_t flags; } out_slot_t;
typedef struct out_pend { flm_midihdr_t *hdr; uint32_t end, slot, gen; struct out_pend *next; } out_pend_t;

static in_slot_t g_in[FLM_MAX_DEV];
static out_slot_t g_out[FLM_MAX_DEV];
static out_pend_t *g_pend_head, *g_pend_tail;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER, g_out_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t g_cb;
static pthread_once_t g_cb_once = PTHREAD_ONCE_INIT;
static pthread_t g_thr;
static int g_thr_started, g_paused;
static flm_cb_invoke_fn g_invoke;
static uint32_t g_gen_ctr = 1, g_cb_events;
static volatile pthread_t g_cb_thread_id;   /* 直近コールバックを呼んだスレッド (診断・テスト用) */

static void cb_once(void) {
    pthread_mutexattr_t a; pthread_mutexattr_init(&a); pthread_mutexattr_settype(&a, PTHREAD_MUTEX_RECURSIVE);
    pthread_mutex_init(&g_cb, &a);
}
static void default_invoke(uintptr_t cb, FLM_HANDLE h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2) {
    ((void (*)(uintptr_t, uint32_t, uintptr_t, uintptr_t, uintptr_t))cb)(h, msg, inst, p1, p2);
}
void flmidi_set_invoke(flm_cb_invoke_fn fn) { g_invoke = fn; }

/* g_cb 保持下で呼ぶこと */
static void fire(uintptr_t cb, FLM_HANDLE h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2) {
    if (!cb) return;
    INC(g_cb_events); INC(flm_ctl()->cb_events);
    g_cb_thread_id = pthread_self();
    (g_invoke ? g_invoke : default_invoke)(cb, h, msg, inst, p1, p2);
}
uintptr_t flmidi_last_cb_thread(void) { return (uintptr_t)g_cb_thread_id; }

static uint32_t next_gen(void) { uint32_t g = g_gen_ctr++ & 0xffff; if (!g) g = g_gen_ctr++ & 0xffff; return g; }
static FLM_HANDLE mkh(uint32_t dir, uint32_t gen, uint32_t slot) { return dir | gen << 8 | slot; }
/* ハンドル検証 (g_lock 保持下)。有効なら slot index を返し、無効は -1 */
static int in_of(FLM_HANDLE h) { uint32_t s = h & 0xff; if (!(h & H_IN) || (h & H_OUT) || s >= FLM_MAX_DEV) return -1; return g_in[s].used && g_in[s].gen == ((h >> 8) & 0xffff) ? (int)s : -1; }
static int out_of(FLM_HANDLE h) { uint32_t s = h & 0xff; if (!(h & H_OUT) || (h & H_IN) || s >= FLM_MAX_DEV) return -1; return g_out[s].used && g_out[s].gen == ((h >> 8) & 0xffff) ? (int)s : -1; }

static uint32_t rpc_err(int rc) { return rc == FLM_E_NODEV ? MM_BADDEVICEID : rc == FLM_E_OPEN ? MM_ALLOCATED : MM_NODRIVER; }

/* ---- MIDI スレッド ------------------------------------------------------------------------------ */
static void deliver_short(const flm_rec_t *r) {
    pthread_mutex_lock(&g_cb); pthread_mutex_lock(&g_lock);
    in_slot_t *s = &g_in[r->slot & (FLM_MAX_DEV - 1)];
    if (r->slot >= FLM_MAX_DEV || !s->used || s->gen != r->gen) { INC(flm_ctl()->in_stale); goto out; }
    if (!s->started || r->ts < s->start_ms) { INC(flm_ctl()->in_prestart); goto out; }
    {
        uintptr_t cb = s->cb, inst = s->inst; uint32_t fl = s->flags; double st = s->start_ms;
        FLM_HANDLE h = mkh(H_IN, s->gen, r->slot);
        pthread_mutex_unlock(&g_lock);
        if ((fl & FLM_CALLBACK_TYPEMASK) == FLM_CALLBACK_FUNCTION) fire(cb, h, FLM_MIM_DATA, inst, r->val, (uintptr_t)(uint32_t)(r->ts - st));
        pthread_mutex_unlock(&g_cb);
        return;
    }
out:
    pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb);
}

static void deliver_sysex(const flm_rec_t *r, const uint8_t *data) {
    uint32_t len = r->val, off = 0;
    pthread_mutex_lock(&g_cb);
    while (off < len || len == 0) {
        pthread_mutex_lock(&g_lock);
        in_slot_t *s = &g_in[r->slot & (FLM_MAX_DEV - 1)];
        if (r->slot >= FLM_MAX_DEV || !s->used || s->gen != r->gen) { INC(flm_ctl()->in_stale); pthread_mutex_unlock(&g_lock); break; }
        if (!s->started || r->ts < s->start_ms) { INC(flm_ctl()->in_prestart); pthread_mutex_unlock(&g_lock); break; }
        flm_midihdr_t *h = s->q_head;
        if (!h) { INC(flm_ctl()->sx_nobuf); pthread_mutex_unlock(&g_lock); break; }   /* AddBuffer 済みの空きが無い = 取りこぼし (winmm と同じ) */
        s->q_head = h->lpNext; if (!s->q_head) s->q_tail = NULL;
        uint32_t n = len - off < h->dwBufferLength ? len - off : h->dwBufferLength;
        memcpy(h->lpData, data + off, n);
        h->dwBytesRecorded = n; h->lpNext = NULL;
        h->dwFlags = (h->dwFlags & ~(uint32_t)FLM_MHDR_INQUEUE) | FLM_MHDR_DONE;
        uintptr_t cb = s->cb, inst = s->inst; uint32_t fl = s->flags; double st = s->start_ms;
        FLM_HANDLE hh = mkh(H_IN, s->gen, r->slot);
        pthread_mutex_unlock(&g_lock);
        if ((fl & FLM_CALLBACK_TYPEMASK) == FLM_CALLBACK_FUNCTION) fire(cb, hh, FLM_MIM_LONGDATA, inst, (uintptr_t)h, (uintptr_t)(uint32_t)(r->ts - st));
        off += n;
        if (len == 0) break;
    }
    pthread_mutex_unlock(&g_cb);
}

static void complete_out(void) {
    uint32_t rd = LD(flm_ctl()->out_r);
    for (;;) {
        pthread_mutex_lock(&g_cb); pthread_mutex_lock(&g_lock);
        out_pend_t *p = g_pend_head;
        if (!p || (int32_t)(rd - p->end) < 0) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return; }
        g_pend_head = p->next; if (!g_pend_head) g_pend_tail = NULL;
        flm_midihdr_t *h = p->hdr;
        h->dwFlags = (h->dwFlags & ~(uint32_t)FLM_MHDR_INQUEUE) | FLM_MHDR_DONE;
        out_slot_t *s = &g_out[p->slot];
        int live = s->used && s->gen == p->gen;
        uintptr_t cb = s->cb, inst = s->inst; uint32_t fl = s->flags;
        FLM_HANDLE hh = mkh(H_OUT, p->gen, p->slot);
        free(p);
        pthread_mutex_unlock(&g_lock);
        if (live && (fl & FLM_CALLBACK_TYPEMASK) == FLM_CALLBACK_FUNCTION) fire(cb, hh, FLM_MOM_DONE, inst, (uintptr_t)h, 0);
        pthread_mutex_unlock(&g_cb);
    }
}

static void *midi_thread(void *arg) {
    (void)arg;
    static uint8_t payload[FLM_MAX_SYSEX];
    for (;;) {
        uint32_t seen = LD(flm_ctl()->wake);
        int did = 0;
        if (!LD(g_paused)) {
            flm_rec_t r;
            while (!LD(g_paused) && flm_in_pop(&r, payload, sizeof payload)) {
                did = 1;
                if (r.kind == FLM_K_SHORT) deliver_short(&r);
                else if (r.kind == FLM_K_SYSEX) deliver_sysex(&r, payload);
                /* FLM_K_STATE: 予約 (切断通知)。現状 winmm へは伝えない */
            }
        }
        complete_out();
        if (!did) flm_wait_wake(seen, 100);
    }
    return NULL;
}
static void ensure_thread(void) {
    pthread_once(&g_cb_once, cb_once);
    pthread_mutex_lock(&g_lock);
    int need = !g_thr_started; g_thr_started = 1;
    pthread_mutex_unlock(&g_lock);
    if (need) {
        pthread_attr_t a; pthread_attr_init(&a); pthread_attr_setstacksize(&a, 256 * 1024);
        if (pthread_create(&g_thr, &a, midi_thread, NULL)) flm_failfast("flmidi", "pthread_create failed");
        pthread_detach(g_thr);
    }
}
void flmidi_test_pause(int on) { ST(g_paused, on); if (!on) flm_bump_wake(); }

/* ---- 共通 ------------------------------------------------------------------------------------- */
static const char *errtext(FLM_UINT e) {
    switch (e) {
    case MM_NOERROR: return "The specified command was carried out.";
    case MM_BADDEVICEID: return "The specified device identifier is out of range.";
    case MM_ALLOCATED: return "The specified resource is already allocated.";
    case MM_INVALHANDLE: return "The specified device handle is invalid.";
    case MM_NODRIVER: return "There is no driver installed on your system.";
    case MM_NOMEM: return "Not enough memory is available.";
    case MM_NOTSUPPORTED: return "The function is not supported.";
    case MM_BADERRNUM: return "The specified error number is out of range.";
    case MM_INVALFLAG: return "Invalid flag passed.";
    case MM_INVALPARAM: return "Invalid parameter passed.";
    case MIDIERR_UNPREPARED: return "The MIDI header was not prepared.";
    case MIDIERR_STILLPLAYING: return "Still something playing.";
    case MIDIERR_NOTREADY: return "The hardware is busy with other data.";
    case MIDIERR_NODEVICE: return "The port is no longer connected.";
    default: return NULL;
    }
}
static FLM_UINT errtext_w(FLM_UINT e, FLM_WCHAR *buf, FLM_UINT n) {
    const char *t = errtext(e);
    if (!t) return MM_BADERRNUM;
    if (!buf || !n) return MM_INVALPARAM;
    FLM_UINT i = 0;
    for (; t[i] && i + 1 < n; i++) buf[i] = (FLM_WCHAR)(uint8_t)t[i];
    buf[i] = 0;
    return MM_NOERROR;
}

static FLM_UINT numdevs(int dir) { flm_init(); return dir ? LD(flm_ctl()->n_out) : LD(flm_ctl()->n_in); }
static int dev_at(int dir, uint32_t id, flm_dev_t *d) {
    flm_init();
    static __thread flm_dev_t tbl[2][FLM_MAX_DEV]; uint32_t n[2];
    flm_dev_snapshot(tbl, n);
    if (id >= n[dir]) return 0;
    *d = tbl[dir][id];
    return 1;
}
static FLM_UINT getcaps(int dir, uintptr_t id, void *caps, FLM_UINT n) {
    flm_dev_t d;
    if (dir == 1 && (uint32_t)id == FLM_MIDI_MAPPER) id = 0;
    if (id >= FLM_MAX_DEV || !dev_at(dir, (uint32_t)id, &d)) return MM_BADDEVICEID;
    if (!caps) return MM_INVALPARAM;
    union { flm_midiincaps_t i; flm_midioutcaps_t o; } u; memset(&u, 0, sizeof u);
    uint32_t sz = dir ? sizeof(flm_midioutcaps_t) : sizeof(flm_midiincaps_t);
    flm_midiincaps_t *c = &u.i;
    c->wMid = (uint16_t)(d.mid_pid & 0xffff); c->wPid = (uint16_t)(d.mid_pid >> 16); c->vDriverVersion = 0x0100;
    for (int k = 0; k < 31 && d.name[k]; k++) c->szPname[k] = d.name[k];   /* szPname[32]: 31 文字 + NUL に切詰め */
    if (dir) { u.o.wTechnology = 1; u.o.wChannelMask = 0xffff; }
    memcpy(caps, &u, n < sz ? n : sz);
    return MM_NOERROR;
}

/* ---- midiIn ----------------------------------------------------------------------------------- */
FLM_UINT flm_midiInGetNumDevs(void) { return numdevs(0); }
FLM_UINT flm_midiInGetDevCapsW(uintptr_t id, void *caps, FLM_UINT n) { return getcaps(0, id, caps, n); }
FLM_UINT flm_midiInGetErrorTextW(FLM_UINT err, FLM_WCHAR *buf, FLM_UINT n) { return errtext_w(err, buf, n); }

FLM_UINT flm_midiInOpen(FLM_HANDLE *ph, FLM_UINT id, uintptr_t cb, uintptr_t inst, uint32_t flags) {
    flm_dev_t d;
    uint32_t ty = flags & FLM_CALLBACK_TYPEMASK;
    if (!ph) return MM_INVALPARAM;
    if (ty != FLM_CALLBACK_NULL && ty != FLM_CALLBACK_FUNCTION) return MM_NOTSUPPORTED;   /* 範囲: FL が使う CALLBACK_FUNCTION のみ (+ NULL) */
    if (ty == FLM_CALLBACK_FUNCTION && !cb) return MM_INVALPARAM;
    if (id >= FLM_MAX_DEV || !dev_at(0, id, &d)) return MM_BADDEVICEID;
    ensure_thread();
    pthread_mutex_lock(&g_cb); pthread_mutex_lock(&g_lock);
    int si = -1;
    for (int k = 0; k < (int)FLM_MAX_DEV; k++) if (g_in[k].used && g_in[k].key == d.key) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MM_ALLOCATED; }
    for (int k = 0; k < (int)FLM_MAX_DEV; k++) if (!g_in[k].used) { si = k; break; }
    if (si < 0) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MM_NOMEM; }
    in_slot_t *s = &g_in[si];
    memset(s, 0, sizeof *s);
    s->used = 1; s->gen = next_gen(); s->key = d.key; s->cb = cb; s->inst = inst; s->flags = flags;
    uint32_t gen = s->gen;
    pthread_mutex_unlock(&g_lock);
    int rc = flm_rpc(FLM_CMD_OPEN_IN, d.key, (uint32_t)si, gen, 0, NULL, 5000);
    if (rc != 0) { pthread_mutex_lock(&g_lock); memset(s, 0, sizeof *s); pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return rpc_err(rc); }
    FLM_HANDLE h = mkh(H_IN, gen, (uint32_t)si);
    *ph = h;
    if (ty == FLM_CALLBACK_FUNCTION) fire(cb, h, FLM_MIM_OPEN, inst, 0, 0);
    pthread_mutex_unlock(&g_cb);
    return MM_NOERROR;
}

FLM_UINT flm_midiInClose(FLM_HANDLE h) {
    pthread_mutex_lock(&g_cb); pthread_mutex_lock(&g_lock);
    int si = in_of(h);
    if (si < 0) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MM_INVALHANDLE; }
    in_slot_t *s = &g_in[si];
    if (s->q_head) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MIDIERR_STILLPLAYING; }
    uintptr_t cb = s->cb, inst = s->inst; uint32_t fl = s->flags;
    memset(s, 0, sizeof *s);   /* 以降この gen 宛のデータは stale として捨てられる */
    pthread_mutex_unlock(&g_lock);
    flm_rpc(FLM_CMD_CLOSE_IN, (uint32_t)si, 0, 0, 0, NULL, 5000);
    if ((fl & FLM_CALLBACK_TYPEMASK) == FLM_CALLBACK_FUNCTION) fire(cb, h, FLM_MIM_CLOSE, inst, 0, 0);
    pthread_mutex_unlock(&g_cb);
    return MM_NOERROR;
}

FLM_UINT flm_midiInStart(FLM_HANDLE h) {
    pthread_mutex_lock(&g_lock);
    int si = in_of(h);
    if (si >= 0 && !g_in[si].started) { g_in[si].started = 1; g_in[si].start_ms = flm_now_ms(); }
    pthread_mutex_unlock(&g_lock);
    return si < 0 ? MM_INVALHANDLE : MM_NOERROR;
}
FLM_UINT flm_midiInStop(FLM_HANDLE h) {
    pthread_mutex_lock(&g_lock);
    int si = in_of(h);
    if (si >= 0) g_in[si].started = 0;
    pthread_mutex_unlock(&g_lock);
    return si < 0 ? MM_INVALHANDLE : MM_NOERROR;
}
FLM_UINT flm_midiInReset(FLM_HANDLE h) {
    pthread_mutex_lock(&g_cb); pthread_mutex_lock(&g_lock);
    int si = in_of(h);
    if (si < 0) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MM_INVALHANDLE; }
    in_slot_t *s = &g_in[si];
    s->started = 0;
    flm_midihdr_t *q = s->q_head; s->q_head = s->q_tail = NULL;
    uintptr_t cb = s->cb, inst = s->inst; uint32_t fl = s->flags;
    for (flm_midihdr_t *p = q; p; p = p->lpNext) { p->dwBytesRecorded = 0; p->dwFlags = (p->dwFlags & ~(uint32_t)FLM_MHDR_INQUEUE) | FLM_MHDR_DONE; }
    pthread_mutex_unlock(&g_lock);
    /* 返却: 未使用バッファを dwBytesRecorded=0 の MIM_LONGDATA で全て返す (winmm の midiInReset の契約) */
    while (q) {
        flm_midihdr_t *nx = q->lpNext; q->lpNext = NULL;
        if ((fl & FLM_CALLBACK_TYPEMASK) == FLM_CALLBACK_FUNCTION) fire(cb, h, FLM_MIM_LONGDATA, inst, (uintptr_t)q, 0);
        q = nx;
    }
    pthread_mutex_unlock(&g_cb);
    return MM_NOERROR;
}

static FLM_UINT prep(flm_midihdr_t *hdr, FLM_UINT n) {
    if (!hdr || n < 48) return MM_INVALPARAM;
    return MM_NOERROR;
}
FLM_UINT flm_midiInPrepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n) {
    FLM_UINT e = prep(hdr, n);
    pthread_mutex_lock(&g_lock);
    int si = in_of(h);
    if (si < 0) e = MM_INVALHANDLE;
    else if (!e) { if (!hdr->lpData || !hdr->dwBufferLength) e = MM_INVALPARAM; else if (!(hdr->dwFlags & FLM_MHDR_PREPARED)) { hdr->dwFlags |= FLM_MHDR_PREPARED; hdr->dwFlags &= ~(uint32_t)(FLM_MHDR_DONE | FLM_MHDR_INQUEUE); } }
    pthread_mutex_unlock(&g_lock);
    return e;
}
FLM_UINT flm_midiInUnprepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n) {
    FLM_UINT e = prep(hdr, n);
    pthread_mutex_lock(&g_lock);
    int si = in_of(h);
    if (si < 0) e = MM_INVALHANDLE;
    else if (!e) { if (hdr->dwFlags & FLM_MHDR_INQUEUE) e = MIDIERR_STILLPLAYING; else hdr->dwFlags &= ~(uint32_t)FLM_MHDR_PREPARED; }
    pthread_mutex_unlock(&g_lock);
    return e;
}
FLM_UINT flm_midiInAddBuffer(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n) {
    FLM_UINT e = prep(hdr, n);
    pthread_mutex_lock(&g_lock);
    int si = in_of(h);
    if (si < 0) e = MM_INVALHANDLE;
    else if (!e) {
        if (!(hdr->dwFlags & FLM_MHDR_PREPARED)) e = MIDIERR_UNPREPARED;
        else if (hdr->dwFlags & FLM_MHDR_INQUEUE) e = MIDIERR_STILLPLAYING;
        else {
            in_slot_t *s = &g_in[si];
            hdr->dwFlags = (hdr->dwFlags & ~(uint32_t)FLM_MHDR_DONE) | FLM_MHDR_INQUEUE; hdr->dwBytesRecorded = 0; hdr->lpNext = NULL;
            if (s->q_tail) s->q_tail->lpNext = hdr; else s->q_head = hdr;
            s->q_tail = hdr;
        }
    }
    pthread_mutex_unlock(&g_lock);
    return e;
}

/* ---- midiOut ---------------------------------------------------------------------------------- */
FLM_UINT flm_midiOutGetNumDevs(void) { return numdevs(1); }
FLM_UINT flm_midiOutGetDevCapsW(uintptr_t id, void *caps, FLM_UINT n) { return getcaps(1, id, caps, n); }
FLM_UINT flm_midiOutGetErrorTextW(FLM_UINT err, FLM_WCHAR *buf, FLM_UINT n) { return errtext_w(err, buf, n); }

FLM_UINT flm_midiOutOpen(FLM_HANDLE *ph, FLM_UINT id, uintptr_t cb, uintptr_t inst, uint32_t flags) {
    flm_dev_t d;
    uint32_t ty = flags & FLM_CALLBACK_TYPEMASK;
    if (!ph) return MM_INVALPARAM;
    if (ty != FLM_CALLBACK_NULL && ty != FLM_CALLBACK_FUNCTION) return MM_NOTSUPPORTED;
    if (ty == FLM_CALLBACK_FUNCTION && !cb) return MM_INVALPARAM;
    if (id == FLM_MIDI_MAPPER) id = 0;
    if (id >= FLM_MAX_DEV || !dev_at(1, id, &d)) return MM_BADDEVICEID;
    ensure_thread();
    pthread_mutex_lock(&g_cb); pthread_mutex_lock(&g_lock);
    int si = -1;
    for (int k = 0; k < (int)FLM_MAX_DEV; k++) if (g_out[k].used && g_out[k].key == d.key) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MM_ALLOCATED; }
    for (int k = 0; k < (int)FLM_MAX_DEV; k++) if (!g_out[k].used) { si = k; break; }
    if (si < 0) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MM_NOMEM; }
    out_slot_t *s = &g_out[si];
    memset(s, 0, sizeof *s);
    s->used = 1; s->gen = next_gen(); s->key = d.key; s->cb = cb; s->inst = inst; s->flags = flags;
    uint32_t gen = s->gen;
    pthread_mutex_unlock(&g_lock);
    int rc = flm_rpc(FLM_CMD_OPEN_OUT, d.key, (uint32_t)si, gen, 0, NULL, 5000);
    if (rc != 0) { pthread_mutex_lock(&g_lock); memset(s, 0, sizeof *s); pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return rpc_err(rc); }
    FLM_HANDLE h = mkh(H_OUT, gen, (uint32_t)si);
    *ph = h;
    if (ty == FLM_CALLBACK_FUNCTION) fire(cb, h, FLM_MOM_OPEN, inst, 0, 0);
    pthread_mutex_unlock(&g_cb);
    return MM_NOERROR;
}

FLM_UINT flm_midiOutClose(FLM_HANDLE h) {
    pthread_mutex_lock(&g_cb); pthread_mutex_lock(&g_lock);
    int si = out_of(h);
    if (si < 0) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MM_INVALHANDLE; }
    for (out_pend_t *p = g_pend_head; p; p = p->next) if (p->slot == (uint32_t)si && p->gen == g_out[si].gen) { pthread_mutex_unlock(&g_lock); pthread_mutex_unlock(&g_cb); return MIDIERR_STILLPLAYING; }
    out_slot_t *s = &g_out[si];
    uintptr_t cb = s->cb, inst = s->inst; uint32_t fl = s->flags;
    memset(s, 0, sizeof *s);
    pthread_mutex_unlock(&g_lock);
    flm_rpc(FLM_CMD_CLOSE_OUT, (uint32_t)si, 0, 0, 0, NULL, 5000);
    if ((fl & FLM_CALLBACK_TYPEMASK) == FLM_CALLBACK_FUNCTION) fire(cb, h, FLM_MOM_CLOSE, inst, 0, 0);
    pthread_mutex_unlock(&g_cb);
    return MM_NOERROR;
}

FLM_UINT flm_midiOutShortMsg(FLM_HANDLE h, uint32_t msg) {
    pthread_mutex_lock(&g_lock);
    int si = out_of(h); uint32_t gen = si >= 0 ? g_out[si].gen : 0;
    pthread_mutex_unlock(&g_lock);
    if (si < 0) return MM_INVALHANDLE;
    pthread_mutex_lock(&g_out_lock);
    int rc = flm_out_push((uint32_t)si, gen, FLM_K_SHORT, msg, NULL, 0, NULL);
    pthread_mutex_unlock(&g_out_lock);
    if (rc) { INC(flm_ctl()->out_full); return MIDIERR_NOTREADY; }
    return MM_NOERROR;
}

FLM_UINT flm_midiOutPrepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n) {
    FLM_UINT e = prep(hdr, n);
    pthread_mutex_lock(&g_lock);
    int si = out_of(h);
    if (si < 0) e = MM_INVALHANDLE;
    else if (!e) { if (!hdr->lpData || !hdr->dwBufferLength) e = MM_INVALPARAM; else if (!(hdr->dwFlags & FLM_MHDR_PREPARED)) { hdr->dwFlags |= FLM_MHDR_PREPARED; hdr->dwFlags &= ~(uint32_t)(FLM_MHDR_DONE | FLM_MHDR_INQUEUE); } }
    pthread_mutex_unlock(&g_lock);
    return e;
}
FLM_UINT flm_midiOutUnprepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n) {
    FLM_UINT e = prep(hdr, n);
    pthread_mutex_lock(&g_lock);
    int si = out_of(h);
    if (si < 0) e = MM_INVALHANDLE;
    else if (!e) { if (hdr->dwFlags & FLM_MHDR_INQUEUE) e = MIDIERR_STILLPLAYING; else hdr->dwFlags &= ~(uint32_t)FLM_MHDR_PREPARED; }
    pthread_mutex_unlock(&g_lock);
    return e;
}
FLM_UINT flm_midiOutLongMsg(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n) {
    FLM_UINT e = prep(hdr, n);
    pthread_mutex_lock(&g_lock);
    int si = out_of(h); uint32_t gen = si >= 0 ? g_out[si].gen : 0;
    if (si < 0) e = MM_INVALHANDLE;
    else if (!e) {
        if (!(hdr->dwFlags & FLM_MHDR_PREPARED)) e = MIDIERR_UNPREPARED;
        else if (hdr->dwFlags & FLM_MHDR_INQUEUE) e = MIDIERR_STILLPLAYING;
        else if (hdr->dwBufferLength > FLM_MAX_SYSEX) e = MM_INVALPARAM;
    }
    if (e) { pthread_mutex_unlock(&g_lock); return e; }
    hdr->dwFlags = (hdr->dwFlags & ~(uint32_t)FLM_MHDR_DONE) | FLM_MHDR_INQUEUE;
    pthread_mutex_unlock(&g_lock);
    uint32_t len = hdr->dwBufferLength, end = 0;
    pthread_mutex_lock(&g_out_lock);
    int rc = flm_out_push((uint32_t)si, gen, FLM_K_SYSEX, len, (const uint8_t *)hdr->lpData, len, &end);
    if (!rc) {
        out_pend_t *p = calloc(1, sizeof *p);
        p->hdr = hdr; p->end = end; p->slot = (uint32_t)si; p->gen = gen;
        pthread_mutex_lock(&g_lock);
        if (g_pend_tail) g_pend_tail->next = p; else g_pend_head = p;
        g_pend_tail = p;
        pthread_mutex_unlock(&g_lock);
    }
    pthread_mutex_unlock(&g_out_lock);
    if (rc) {
        pthread_mutex_lock(&g_lock); hdr->dwFlags &= ~(uint32_t)FLM_MHDR_INQUEUE; pthread_mutex_unlock(&g_lock);
        INC(flm_ctl()->out_full);
        return MIDIERR_NOTREADY;
    }
    flm_bump_wake();   /* 出力完了 (JS の send 後) を MIDI スレッドが拾うためのフォールバック起床 */
    return MM_NOERROR;
}

/* ---- 管理 ------------------------------------------------------------------------------------- */
int flmidi_rescan(void) { flm_init(); return flm_rpc(FLM_CMD_SCAN, 0, 0, 0, 0, NULL, 5000); }
uint32_t flmidi_scan_gen(void) { flm_init(); return LD(flm_ctl()->scan_gen); }
void flmidi_get_stats(uint32_t o[16]) {
    flm_ctl_t *c = flm_ctl();
    uint32_t v[16] = { LD(c->cb_events), LD(c->in_accepted), LD(c->in_dropped), LD(c->main_errors), LD(c->out_sent), LD(c->out_errors), LD(c->out_full), LD(c->sx_nobuf),
                       LD(c->in_stale), LD(c->in_prestart), LD(c->scan_gen), LD(c->n_in), LD(c->n_out), LD(c->in_r), LD(c->in_w), 0 };
    memcpy(o, v, sizeof v);
}
