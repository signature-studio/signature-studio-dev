/* midi_conv.c — winmm midi* の shimx 側 (#179 SHX-T6): guest win64 ABI ⇄ wasm ネイティブ幅の backend 表。
 *
 * 経路: guest → shimx midi* (本ファイル, weak) → shimx_midi_vtbl (shimx_set_midi_backend で登録) → audio 側 flm_midi*。
 * 未登録時は従来どおり「デバイス 0 台」を返す (shimx 単体ビルドの挙動は不変)。
 *
 * MIDIHDR 変換 (guest → native / 方向は REPORT_SHX-T6 §変換表):
 *   - guest MIDIHDR = win64 112B (8B ポインタ, pack(1))。native = shx_midihdr_nat 48B (flm_midihdr_t と同一レイアウト)。
 *   - Prepare: native mirror を確保し全フィールドを copy-in。以後 AddBuffer / LongMsg も copy-in → backend → copy-out。
 *   - Unprepare 成功で mirror を解放。mirror は guest ヘッダと 1:1 (guest アドレスで引く)。
 *   - 完了通知 (MIM_LONGDATA / MOM_DONE, p1 = native hdr): copy-out してから p1 を guest アドレスへ戻す。
 *   - lpData は guest バッファを直接指す (wasm 線形メモリ共有)。SysEx は backend が直接書くので追加コピー無し。
 * MIDIINCAPSW / MIDIOUTCAPSW は win64 と wasm で同一レイアウト (ポインタ無し) のため素通し。
 * HANDLE / cb / inst は shimx の既存規約どおり ULONG_PTR (wasm32 4B)。 */
#include "shimx_internal.h"
#include "midi_backend.h"

#define MMSYSERR_INVALPARAM 11u
#define MMSYSERR_BADDEVICEID 2u
#define MMSYSERR_INVALHANDLE 5u
#define MIDIERR_UNPREPARED 64u
void shimx_midi_dispatch_for_test(uintptr_t cb, uintptr_t h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2);
#define MIM_LONGDATA_MSG 0x3C4u
#define MOM_DONE_MSG 0x3C9u

/* guest 側 win64 MIDIHDR (112B)。ポインタ 8B・pack(1) (mingw-w64 mmsystem.h と一致, offset は実測で確認済み) */
typedef struct __attribute__((packed)) {
    uint64_t lpData; uint32_t dwBufferLength, dwBytesRecorded; uint64_t dwUser; uint32_t dwFlags;
    uint64_t lpNext; uint64_t reserved; uint32_t dwOffset; uint64_t dwReserved[8];
} shx_midihdr_w64;
_Static_assert(sizeof(shx_midihdr_w64) == 112, "win64 MIDIHDR は 112B");
_Static_assert(sizeof(shx_midihdr_nat) == 48, "native MIDIHDR (flm_midihdr_t 同形) は 48B (wasm32)");

typedef struct mir {
    shx_midihdr_w64 *g;          /* guest ヘッダ (win64 レイアウト) */
    shx_midihdr_nat n;           /* backend へ渡す native 幅の mirror */
    struct mir *next;
} mir_t;

static const shimx_midi_vtbl *g_mt;
static mir_t *g_mir;
static shx_mutex_t g_mir_lk;

static mir_t *mir_find_guest(const void *g) {
    for (mir_t *m = g_mir; m; m = m->next) if (m->g == g) return m;
    return NULL;
}
static mir_t *mir_find_nat(const void *n) {
    for (mir_t *m = g_mir; m; m = m->next) if (&m->n == n) return m;
    return NULL;
}
static void copy_in(mir_t *m) {
    shx_midihdr_w64 *g = m->g;
    m->n.lpData = (char *)(uintptr_t)(uint32_t)g->lpData;
    m->n.dwBufferLength = g->dwBufferLength;
    m->n.dwBytesRecorded = g->dwBytesRecorded;
    m->n.dwUser = (uintptr_t)(uint32_t)g->dwUser;
    m->n.dwFlags = g->dwFlags;
    m->n.dwOffset = g->dwOffset;
}
static void copy_out(mir_t *m) {
    m->g->dwFlags = m->n.dwFlags;
    m->g->dwBytesRecorded = m->n.dwBytesRecorded;
}

/* midi 完了コールバック (backend → shimx)。guest VA は shimx_cbtrans_get_invoke (__icall_dispatch BLK 同等の invoke) 経由、
 * 実 C 関数ポインタ (< intptr_limit) は直接呼ぶ。p1 が native hdr のときは guest アドレスへ戻す。 */
static void midi_dispatch(uintptr_t cb, uintptr_t h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2) {
    if (!cb) return;   /* CALLBACK_NULL / 未設定: winmm と同じく通知しない */
    if (msg == MIM_LONGDATA_MSG || msg == MOM_DONE_MSG) {
        shx_mutex_lock(&g_mir_lk);
        mir_t *m = mir_find_nat((const void *)p1);
        if (m) { copy_out(m); p1 = (uintptr_t)m->g; }
        shx_mutex_unlock(&g_mir_lk);
    }
    if (shx_is_iptr(cb)) { ((void (*)(uintptr_t, uint32_t, uintptr_t, uintptr_t, uintptr_t))cb)(h, msg, inst, p1, p2); return; }
    shimx_cb_invoke_fn f = shimx_cbtrans_get_invoke();
    if (f) f((unsigned long long)cb, (unsigned long long)h, (unsigned long long)msg, (unsigned long long)inst,
             (unsigned long long)p1, (unsigned long long)p2, 0, 0, 0);
    else SHX_TRACE("midi: callback VA 0x%x dropped (invoke 未登録)", (unsigned)cb);
}

void shimx_set_midi_backend(const shimx_midi_vtbl *t) {
    g_mt = t;
    if (t && t->set_cb_invoke) t->set_cb_invoke(midi_dispatch);
}
void shimx_midi_dispatch_for_test(uintptr_t cb, uintptr_t h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2) {
    midi_dispatch(cb, h, msg, inst, p1, p2);
}

/* ---- Prepare / Unprepare / AddBuffer / LongMsg (guest 側ヘッダ操作) ---- */
static UINT hdr_prepare(shx_midi_hdr_fn fn, uintptr_t h, LPVOID hdr, UINT n) {
    if (!hdr) return MMSYSERR_INVALPARAM;
    shx_mutex_lock(&g_mir_lk);
    mir_t *m = mir_find_guest(hdr);
    if (!m) {
        m = calloc(1, sizeof *m);
        if (!m) { shx_mutex_unlock(&g_mir_lk); return 7u; /* MMSYSERR_NOMEM */ }
        m->g = (shx_midihdr_w64 *)hdr; m->next = g_mir; g_mir = m;
    }
    shx_mutex_unlock(&g_mir_lk);
    copy_in(m);
    UINT rc = fn(h, &m->n, n);
    copy_out(m);
    return rc;
}
static UINT hdr_op(shx_midi_hdr_fn fn, uintptr_t h, LPVOID hdr, UINT n, int release) {
    if (!hdr) return MMSYSERR_INVALPARAM;
    shx_mutex_lock(&g_mir_lk);
    mir_t *m = mir_find_guest(hdr);
    shx_mutex_unlock(&g_mir_lk);
    if (!m) return MIDIERR_UNPREPARED;
    copy_in(m);
    UINT rc = fn(h, &m->n, n);
    copy_out(m);
    if (release && rc == 0) {
        shx_mutex_lock(&g_mir_lk);
        mir_t **pp = &g_mir;
        while (*pp && *pp != m) pp = &(*pp)->next;
        if (*pp) *pp = m->next;
        shx_mutex_unlock(&g_mir_lk);
        free(m);
    }
    return rc;
}

/* ---- winmm midi* (weak: audio 側の表が登録されていればそこへ委譲, 未登録は従来どおり 0 台) ---- */
SHIMX_WEAK UINT midiInGetNumDevs(void) { return g_mt ? g_mt->inGetNumDevs() : 0; }
SHIMX_WEAK UINT midiOutGetNumDevs(void) { return g_mt ? g_mt->outGetNumDevs() : 0; }
SHIMX_WEAK UINT midiInGetDevCapsW(UINT_PTR_T id, LPVOID caps, UINT n) {
    return g_mt ? g_mt->inGetDevCapsW(id, caps, n) : MMSYSERR_BADDEVICEID;
}
SHIMX_WEAK UINT midiOutGetDevCapsW(UINT_PTR_T id, LPVOID caps, UINT n) {
    return g_mt ? g_mt->outGetDevCapsW(id, caps, n) : MMSYSERR_BADDEVICEID;
}
SHIMX_WEAK UINT midiInOpen(LPHANDLE h, UINT id, ULONG_PTR cb, ULONG_PTR inst, DWORD flags) {
    uintptr_t hh = 0;
    UINT rc = g_mt ? g_mt->inOpen(&hh, id, cb, inst, flags) : MMSYSERR_BADDEVICEID;
    if (h) *h = hh;
    return rc;
}
SHIMX_WEAK UINT midiOutOpen(LPHANDLE h, UINT id, ULONG_PTR cb, ULONG_PTR inst, DWORD flags) {
    uintptr_t hh = 0;
    UINT rc = g_mt ? g_mt->outOpen(&hh, id, cb, inst, flags) : MMSYSERR_BADDEVICEID;
    if (h) *h = hh;
    return rc;
}
SHIMX_WEAK UINT midiInClose(HANDLE h) { return g_mt ? g_mt->inClose(h) : MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiOutClose(HANDLE h) { return g_mt ? g_mt->outClose(h) : MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInStart(HANDLE h) { return g_mt ? g_mt->inStart(h) : MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInStop(HANDLE h) { return g_mt ? g_mt->inStop(h) : MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInReset(HANDLE h) { return g_mt ? g_mt->inReset(h) : MMSYSERR_INVALHANDLE; }
SHIMX_WEAK UINT midiInPrepareHeader(HANDLE h, LPVOID hdr, UINT n) {
    return g_mt ? hdr_prepare(g_mt->inPrepareHeader, h, hdr, n) : MMSYSERR_INVALHANDLE;
}
SHIMX_WEAK UINT midiInUnprepareHeader(HANDLE h, LPVOID hdr, UINT n) {
    return g_mt ? hdr_op(g_mt->inUnprepareHeader, h, hdr, n, 1) : MMSYSERR_INVALHANDLE;
}
SHIMX_WEAK UINT midiInAddBuffer(HANDLE h, LPVOID hdr, UINT n) {
    return g_mt ? hdr_op(g_mt->inAddBuffer, h, hdr, n, 0) : MMSYSERR_INVALHANDLE;
}
SHIMX_WEAK UINT midiOutPrepareHeader(HANDLE h, LPVOID hdr, UINT n) {
    return g_mt ? hdr_prepare(g_mt->outPrepareHeader, h, hdr, n) : MMSYSERR_INVALHANDLE;
}
SHIMX_WEAK UINT midiOutUnprepareHeader(HANDLE h, LPVOID hdr, UINT n) {
    return g_mt ? hdr_op(g_mt->outUnprepareHeader, h, hdr, n, 1) : MMSYSERR_INVALHANDLE;
}
SHIMX_WEAK UINT midiOutShortMsg(HANDLE h, DWORD msg) {
    return g_mt ? g_mt->outShortMsg((uintptr_t)h, msg) : MMSYSERR_INVALHANDLE;
}
SHIMX_WEAK UINT midiOutLongMsg(HANDLE h, LPVOID hdr, UINT n) {
    return g_mt ? hdr_op(g_mt->outLongMsg, h, hdr, n, 0) : MMSYSERR_INVALHANDLE;
}
