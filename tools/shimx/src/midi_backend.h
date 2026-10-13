/* midi_backend.h — winmm midi* の強定義実体 (audio 側) を shimx へ登録する関数表 (#179 SHX-T6)。
 *
 * shimx は emscripten.h に依存しない。表の各関数は wasm ネイティブ幅 (uintptr_t / uint32_t / 同 ABI の pointer) で、
 * tools/audio/src/flmidi_winmm.h の flm_midi* と同じ wasm 呼出規約。audio 側 (tools/audio/src/flmidi_shimx.c) が
 * 強い表を shimx_set_midi_backend() で登録する。未登録時は shimx の midi* は従来どおり「デバイス 0 台」を返す。
 * hdr は guest の win64 MIDIHDR を shimx が変換した shx_midihdr_nat (48B, flm_midihdr_t と同一レイアウト) を渡す。 */
#ifndef SHIMX_MIDI_BACKEND_H
#define SHIMX_MIDI_BACKEND_H
#include <stdint.h>

typedef struct shx_midihdr_nat {
    char *lpData; uint32_t dwBufferLength, dwBytesRecorded; uintptr_t dwUser; uint32_t dwFlags;
    struct shx_midihdr_nat *lpNext; uintptr_t reserved; uint32_t dwOffset; uintptr_t dwReserved[4];
} shx_midihdr_nat;

typedef void (*shx_midi_cb_fn)(uintptr_t cb, uintptr_t h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2);
/* hdr は shx_midihdr_nat* (= audio 側 flm_midihdr_t と同一レイアウト)。表の型では void* で受け、登録側でキャストする */
typedef uint32_t (*shx_midi_hdr_fn)(uintptr_t h, void *hdr, uint32_t n);

typedef struct shimx_midi_vtbl {
    uint32_t (*inGetNumDevs)(void);
    uint32_t (*outGetNumDevs)(void);
    uint32_t (*inGetDevCapsW)(uintptr_t id, void *caps, uint32_t n);
    uint32_t (*outGetDevCapsW)(uintptr_t id, void *caps, uint32_t n);
    uint32_t (*inOpen)(uintptr_t *h, uint32_t id, uintptr_t cb, uintptr_t inst, uint32_t flags);
    uint32_t (*outOpen)(uintptr_t *h, uint32_t id, uintptr_t cb, uintptr_t inst, uint32_t flags);
    uint32_t (*inClose)(uintptr_t h);
    uint32_t (*outClose)(uintptr_t h);
    uint32_t (*inStart)(uintptr_t h);
    uint32_t (*inStop)(uintptr_t h);
    uint32_t (*inReset)(uintptr_t h);
    shx_midi_hdr_fn inPrepareHeader;
    shx_midi_hdr_fn inUnprepareHeader;
    shx_midi_hdr_fn inAddBuffer;
    shx_midi_hdr_fn outPrepareHeader;
    shx_midi_hdr_fn outUnprepareHeader;
    uint32_t (*outShortMsg)(uintptr_t h, uint32_t msg);
    shx_midi_hdr_fn outLongMsg;
    void (*set_cb_invoke)(shx_midi_cb_fn fn);   /* 登録時に shimx のコールバック変換口を渡す */
} shimx_midi_vtbl;

#endif
