/* shimx 単体テスト: winmm midi* の win64 ABI 変換層 (midi_conv.c, #179 SHX-T6)。
 *   - 模擬 backend (audio 側 flm_midi* の代役) を shimx_set_midi_backend で登録し、guest win64 MIDIHDR (112B) が
 *     native shx_midihdr_nat (48B) へ copy-in され、完了時に copy-out + p1 が guest アドレスへ戻ることを検査
 *   - 未登録時は従来どおり 0 台 (shimx 単体ビルドの挙動不変)
 *   - 登録解除 (NULL) で既定動作に戻る
 */
#include "test_common.h"
#include "../src/midi_backend.h"
#include <string.h>

typedef struct __attribute__((packed)) {
    uint64_t lpData; uint32_t dwBufferLength, dwBytesRecorded; uint64_t dwUser; uint32_t dwFlags;
    uint64_t lpNext; uint64_t reserved; uint32_t dwOffset; uint64_t dwReserved[8];
} w64_hdr;
_Static_assert(sizeof(w64_hdr) == 112, "win64 MIDIHDR");

static shx_midihdr_nat *g_seen_hdr;
static uint32_t g_seen_len, g_seen_flags_in;
static char *g_seen_data;
static int g_prep_calls, g_add_calls, g_unprep_calls, g_short_calls;

static uint32_t b_inGetNumDevs(void) { return 1; }
static uint32_t b_outGetNumDevs(void) { return 1; }
static uint32_t b_inGetDevCapsW(uintptr_t id, void *c, uint32_t n) { (void)id; (void)c; (void)n; return 0; }
static uint32_t b_outGetDevCapsW(uintptr_t id, void *c, uint32_t n) { (void)id; (void)c; (void)n; return 0; }
static uint32_t b_inOpen(uintptr_t *h, uint32_t id, uintptr_t cb, uintptr_t inst, uint32_t fl) {
    (void)id; (void)cb; (void)inst; (void)fl; *h = 0x100; return 0;
}
static uint32_t b_outOpen(uintptr_t *h, uint32_t id, uintptr_t cb, uintptr_t inst, uint32_t fl) {
    (void)id; (void)cb; (void)inst; (void)fl; *h = 0x200; return 0;
}
static uint32_t b_close(uintptr_t h) { (void)h; return 0; }
static uint32_t b_start(uintptr_t h) { (void)h; return 0; }
static uint32_t b_prep(uintptr_t h, void *hdr, uint32_t n) {
    (void)h; (void)n; g_prep_calls++; g_seen_hdr = hdr; return 0;
}
static uint32_t b_add(uintptr_t h, void *hdr, uint32_t n) {
    shx_midihdr_nat *m = hdr; (void)h; (void)n; g_add_calls++;
    g_seen_len = m->dwBufferLength; g_seen_data = m->lpData; g_seen_flags_in = m->dwFlags;
    m->dwBytesRecorded = 5; m->dwFlags |= 2; /* MHDR_DONE 相当の書込み (backend 側の完了) */
    return 0;
}
static uint32_t b_unprep(uintptr_t h, void *hdr, uint32_t n) { (void)h; (void)hdr; (void)n; g_unprep_calls++; return 0; }
static uint32_t b_short(uintptr_t h, uint32_t msg) { (void)h; (void)msg; g_short_calls++; return 0; }
static void b_set_cb(shx_midi_cb_fn fn) { (void)fn; }

static const shimx_midi_vtbl g_test_vtbl = {
    .inGetNumDevs = b_inGetNumDevs, .outGetNumDevs = b_outGetNumDevs,
    .inGetDevCapsW = b_inGetDevCapsW, .outGetDevCapsW = b_outGetDevCapsW,
    .inOpen = b_inOpen, .outOpen = b_outOpen, .inClose = b_close, .outClose = b_close,
    .inStart = b_start, .inStop = b_start, .inReset = b_start,
    .inPrepareHeader = b_prep, .inUnprepareHeader = b_unprep, .inAddBuffer = b_add,
    .outPrepareHeader = b_prep, .outUnprepareHeader = b_unprep,
    .outShortMsg = b_short, .outLongMsg = b_add, .set_cb_invoke = b_set_cb,
};

static void test_midi_default_zero_devices(void) {
    shimx_set_midi_backend(NULL);
    CHECK(midiInGetNumDevs() == 0 && midiOutGetNumDevs() == 0);
    CHECK(midiOutShortMsg(0, 0) == 5);   /* MMSYSERR_INVALHANDLE */
}

static void test_midi_backend_routes(void) {
    shimx_set_midi_backend(&g_test_vtbl);
    CHECK(midiInGetNumDevs() == 1 && midiOutGetNumDevs() == 1);
    HANDLE h = 0;
    CHECK(midiInOpen(&h, 0, 0, 0, 0) == 0 && h == 0x100);
    CHECK(midiOutShortMsg(0x200, 0x903c64) == 0 && g_short_calls == 1);
    CHECK(midiInClose(h) == 0);
}

static void test_midi_header_copy_in_out(void) {
    shimx_set_midi_backend(&g_test_vtbl);
    char data[32] = "abcde";
    w64_hdr g; memset(&g, 0, sizeof g);
    g.lpData = (uint64_t)(uintptr_t)data; g.dwBufferLength = 32; g.dwFlags = 0;
    CHECK(midiInPrepareHeader(0x100, &g, sizeof g) == 0);
    CHECK(g_prep_calls == 1);
    CHECK(g_seen_hdr != NULL && (void*)g_seen_hdr != (void*)&g);   /* native mirror は guest と別領域 */
    CHECK(midiInAddBuffer(0x100, &g, sizeof g) == 0);
    CHECK(g_add_calls == 1 && g_seen_len == 32 && g_seen_data == data);
    CHECK(g.dwBytesRecorded == 5);                  /* copy-out: backend の書込みが guest へ戻る */
    CHECK((g.dwFlags & 2) != 0);
    CHECK(midiInUnprepareHeader(0x100, &g, sizeof g) == 0 && g_unprep_calls == 1);
    CHECK(midiInAddBuffer(0x100, &g, sizeof g) == 64);   /* 解放後は MIDIERR_UNPREPARED (64) */
}

static uintptr_t g_cb_p1_seen;
static void cb_record(uintptr_t h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2) {
    (void)h; (void)msg; (void)inst; (void)p2; g_cb_p1_seen = p1;
}

static void test_midi_completion_restores_guest_ptr(void) {
    shimx_set_midi_backend(&g_test_vtbl);
    w64_hdr g; memset(&g, 0, sizeof g);
    CHECK(midiOutPrepareHeader(0x200, &g, sizeof g) == 0);
    CHECK(g_seen_hdr != NULL);
    g.dwFlags = 0;
    /* backend が完了を通知: p1 = native mirror。shimx は copy-out して p1 を guest アドレスへ戻してから callback へ渡す */
    g_seen_hdr->dwBytesRecorded = 7;
    g_seen_hdr->dwFlags = 2;
    /* cb は C 関数ポインタ (< intptr_limit) として直接呼ばれる: 受けた p1 を記録して guest アドレスに戻っていることを確認 */
    g_cb_p1_seen = 0;
    shimx_midi_dispatch_for_test((uintptr_t)cb_record, 0x200, 0x3C9u /* MOM_DONE */, 0, (uintptr_t)g_seen_hdr, 0);
    CHECK(g_cb_p1_seen == (uintptr_t)&g);                     /* p1 は guest アドレスへ戻されている */
    CHECK(g.dwBytesRecorded == 7 && (g.dwFlags & 2) != 0);   /* copy-out が guest 側へ反映 */
    CHECK(midiOutUnprepareHeader(0x200, &g, sizeof g) == 0);
}

void run_midi_tests(int multithread) {
    (void)multithread;
    test_midi_default_zero_devices();
    test_midi_backend_routes();
    test_midi_header_copy_in_out();
    test_midi_completion_restores_guest_ptr();
    shimx_set_midi_backend(NULL);
}
