/* flmidi_shimx.c — winmm midi* の shimx 登録口 (#179 SHX-T6)。
 *
 * shimx (tools/shimx/src/midi_conv.c) は weak な midi* から shimx_midi_vtbl を呼ぶ。本ファイルは audio 側で
 * flm_midi* (flmidi_winmm.c) を表へ束ねて shimx_set_midi_backend() に登録する。shimx 側は emscripten.h 非依存のまま。
 *
 * 登録は flmidi_shimx_install() を呼んだときに 1 回行う (shimx_init 後・guest 起動前)。
 * flmidi_set_invoke は shimx_cbtrans_get_invoke の正本 (lift 側 __icall_dispatch BLK 相当) に接続する。 */
#include <stdint.h>
#include "flmidi_winmm.h"
#include "../../shimx/src/midi_backend.h"
#include "../../shimx/src/shimx.h"

/* shimx の midi_dispatch (VA→invoke / p1 の native→guest 戻し) を audio の発火口に接続する。形は flm_cb_invoke_fn と同一 */
static void set_cb_invoke(shx_midi_cb_fn fn) { flmidi_set_invoke((flm_cb_invoke_fn)fn); }

/* 表の関数ポインタ型 (shx_midi_hdr_fn 等) と flm_* の実型は引数の並びが同じ (wasm32 では uintptr_t = 4B)。
 * C 規格上は関数ポインタの cast 自体が未定義動作だが、wasm の呼出規約では引数幅・順序が一致するため動作する。 */
static const shimx_midi_vtbl g_vtbl = {
    .inGetNumDevs = flm_midiInGetNumDevs,
    .outGetNumDevs = flm_midiOutGetNumDevs,
    .inGetDevCapsW = flm_midiInGetDevCapsW,
    .outGetDevCapsW = flm_midiOutGetDevCapsW,
    .inOpen = (uint32_t (*)(uintptr_t *, uint32_t, uintptr_t, uintptr_t, uint32_t))flm_midiInOpen,
    .outOpen = (uint32_t (*)(uintptr_t *, uint32_t, uintptr_t, uintptr_t, uint32_t))flm_midiOutOpen,
    .inClose = flm_midiInClose,
    .outClose = flm_midiOutClose,
    .inStart = flm_midiInStart,
    .inStop = flm_midiInStop,
    .inReset = flm_midiInReset,
    .inPrepareHeader = (shx_midi_hdr_fn)flm_midiInPrepareHeader,
    .inUnprepareHeader = (shx_midi_hdr_fn)flm_midiInUnprepareHeader,
    .inAddBuffer = (shx_midi_hdr_fn)flm_midiInAddBuffer,
    .outPrepareHeader = (shx_midi_hdr_fn)flm_midiOutPrepareHeader,
    .outUnprepareHeader = (shx_midi_hdr_fn)flm_midiOutUnprepareHeader,
    .outShortMsg = flm_midiOutShortMsg,
    .outLongMsg = (shx_midi_hdr_fn)flm_midiOutLongMsg,
    .set_cb_invoke = set_cb_invoke,
};

void flmidi_shimx_install(void) { shimx_set_midi_backend(&g_vtbl); }
