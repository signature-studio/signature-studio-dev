/* flmidi_winmm.h — winmm midiIn と midiOut 20 関数の Web MIDI 実体 (wasm ネイティブ ABI)。
 *
 * 関数名・引数は winmm と同順。HANDLE/ポインタは wasm のネイティブ幅 (uintptr_t)。win64 ABI (8B ポインタの MIDIHDR / MIDIINCAPSW 等) への
 * 変換と、shimx の weak スタブ (tools/shimx/src/net.c) の強定義への差替えは #179 [SHX-T6] の import 解決層が担当する。
 * コールバックは flmidi_set_invoke() で差し替え可能 (既定 = cb を実 C 関数ポインタとして直接呼ぶ。lift 側は shimx_cb_translator 経由の thunk を登録)。 */
#ifndef FLMIDI_WINMM_H
#define FLMIDI_WINMM_H
#include <stdint.h>
#include "flmidi.h"

typedef uint32_t FLM_UINT;
typedef uintptr_t FLM_HANDLE;
typedef uint16_t FLM_WCHAR;

#define FLM_CALLBACK_TYPEMASK 0x70000u
#define FLM_CALLBACK_NULL     0x00000u
#define FLM_CALLBACK_FUNCTION 0x30000u
#define FLM_MIDI_MAPPER       0xFFFFFFFFu

enum { MM_NOERROR = 0, MM_BADDEVICEID = 2, MM_NODRIVER = 6, MM_ALLOCATED = 4, MM_INVALHANDLE = 5, MM_NOMEM = 7, MM_NOTSUPPORTED = 8, MM_BADERRNUM = 9,
       MM_INVALFLAG = 10, MM_INVALPARAM = 11,
       MIDIERR_UNPREPARED = 64, MIDIERR_STILLPLAYING = 65, MIDIERR_NOTREADY = 67, MIDIERR_NODEVICE = 68 };
enum { FLM_MIM_OPEN = 0x3C1, FLM_MIM_CLOSE = 0x3C2, FLM_MIM_DATA = 0x3C3, FLM_MIM_LONGDATA = 0x3C4,
       FLM_MOM_OPEN = 0x3C7, FLM_MOM_CLOSE = 0x3C8, FLM_MOM_DONE = 0x3C9 };
enum { FLM_MHDR_DONE = 1, FLM_MHDR_PREPARED = 2, FLM_MHDR_INQUEUE = 4 };

typedef struct flm_midihdr {
    char *lpData; uint32_t dwBufferLength, dwBytesRecorded; uintptr_t dwUser; uint32_t dwFlags;
    struct flm_midihdr *lpNext; uintptr_t reserved; uint32_t dwOffset; uintptr_t dwReserved[4];
} flm_midihdr_t;
typedef struct { uint16_t wMid, wPid; uint32_t vDriverVersion; FLM_WCHAR szPname[32]; uint32_t dwSupport; } flm_midiincaps_t;       /* 76B */
typedef struct { uint16_t wMid, wPid; uint32_t vDriverVersion; FLM_WCHAR szPname[32]; uint16_t wTechnology, wVoices, wNotes, wChannelMask; uint32_t dwSupport; } flm_midioutcaps_t; /* 84B */

typedef void (*flm_cb_invoke_fn)(uintptr_t cb, FLM_HANDLE h, uint32_t msg, uintptr_t inst, uintptr_t p1, uintptr_t p2);
void flmidi_set_invoke(flm_cb_invoke_fn fn);

FLM_UINT flm_midiInGetNumDevs(void);
FLM_UINT flm_midiInGetDevCapsW(uintptr_t id, void *caps, FLM_UINT n);
FLM_UINT flm_midiInGetErrorTextW(FLM_UINT err, FLM_WCHAR *buf, FLM_UINT n);
FLM_UINT flm_midiInOpen(FLM_HANDLE *h, FLM_UINT id, uintptr_t cb, uintptr_t inst, uint32_t flags);
FLM_UINT flm_midiInClose(FLM_HANDLE h);
FLM_UINT flm_midiInStart(FLM_HANDLE h);
FLM_UINT flm_midiInStop(FLM_HANDLE h);
FLM_UINT flm_midiInReset(FLM_HANDLE h);
FLM_UINT flm_midiInPrepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n);
FLM_UINT flm_midiInUnprepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n);
FLM_UINT flm_midiInAddBuffer(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n);
FLM_UINT flm_midiOutGetNumDevs(void);
FLM_UINT flm_midiOutGetDevCapsW(uintptr_t id, void *caps, FLM_UINT n);
FLM_UINT flm_midiOutGetErrorTextW(FLM_UINT err, FLM_WCHAR *buf, FLM_UINT n);
FLM_UINT flm_midiOutOpen(FLM_HANDLE *h, FLM_UINT id, uintptr_t cb, uintptr_t inst, uint32_t flags);
FLM_UINT flm_midiOutClose(FLM_HANDLE h);
FLM_UINT flm_midiOutShortMsg(FLM_HANDLE h, uint32_t msg);
FLM_UINT flm_midiOutLongMsg(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n);
FLM_UINT flm_midiOutPrepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n);
FLM_UINT flm_midiOutUnprepareHeader(FLM_HANDLE h, flm_midihdr_t *hdr, FLM_UINT n);
#endif
