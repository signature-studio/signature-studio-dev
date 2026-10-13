/* sx_midi_boot.c — M11 shimx リンクへの winmm midi* 強定義の配線 (#179 SHX-T6, --midi)。
 *
 * build.sh --midi が tools/audio/src/flmidi*.c を同リンクに入れる。本ファイルは link 側の 1 ファイル:
 *   - constructor で flmidi_shimx_install() を 1 回呼び、shimx の midi* の backend 表を audio 側 flm_midi* に登録する。
 *     未登録時 (--midi 無し) は shimx の weak 実装 (デバイス 0 台) のまま。
 *   - sx_midi_probe_numdevs: 結線の実測口。flm_init() の後で flm_ctl()->n_out に値を入れ、midiOutGetNumDevs() の戻りを返す。
 *     登録済みなら n_out がそのまま返り、未登録 (weak) なら常に 0 になるため、結線の有無を判別できる。
 */
#include <stdint.h>
#include <emscripten.h>
#include "../../audio/src/flmidi.h"
#include "../../audio/src/flmidi_winmm.h"

void flmidi_shimx_install(void);
unsigned midiOutGetNumDevs(void);

__attribute__((constructor)) static void sx_midi_boot(void) { flmidi_shimx_install(); }

EMSCRIPTEN_KEEPALIVE unsigned sx_midi_probe_numdevs(unsigned n_out) {
    flm_init();
    flm_ctl()->n_out = n_out;
    return midiOutGetNumDevs();
}
