#!/usr/bin/env bash
# fla_test (ASIO/WASAPI shim テストバイナリ) を emcc でビルドして build/web/ に配置する。
# 使い方: bash tools/audio/build.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd -- "$HERE/../.." && pwd)"
OUT="$HERE/build/web"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
if [ -f "$EMSDK" ]; then set +u; . "$EMSDK" >/dev/null 2>&1 || true; set -u; fi
command -v emcc >/dev/null || { echo "[audio] emcc not found" >&2; exit 1; }
. "$HERE/flags.sh"
mkdir -p "$OUT/worklets" "$OUT/js"
# FLA_DEFS: ビルド variant 用の追加 -D (例 FLA_DEFS="-DFLASIO_PROFILE_ILWASAPI=0 -DFLASIO_SYSTIME_AUDIBLE=1")。既定は空
# shellcheck disable=SC2086
emcc "${FLA_CLANG_FLAGS[@]}" "${FLA_EMCC_FLAGS[@]}" ${FLA_DEFS:-} \
  -I"$HERE/src" \
  "$HERE/src/flaudio.c" "$HERE/src/flasio.c" "$HERE/src/flwasapi.c" "$HERE/test/fla_test.c" \
  -o "$OUT/fla_test.js"
# JS 側: TS を ES module へトランスパイル (型検査は pnpm typecheck 側)、worklet は public/ をそのまま配置
cp "$ROOT/public/worklets/fl-audio-worklet.js" "$OUT/worklets/"
"$ROOT/node_modules/.bin/tsc" --target es2022 --module es2022 --moduleResolution bundler --skipLibCheck \
  --lib es2022,dom,dom.iterable --outDir "$OUT/js" --rootDir "$ROOT/src/runtime" --noEmit false --isolatedModules \
  --strict --ignoreConfig "$ROOT/src/runtime/audio-layout.ts" "$ROOT/src/runtime/audio-shim.ts"
sed -i 's|from "./audio-layout"|from "./audio-layout.js"|' "$OUT/js/audio-shim.js"
cp "$HERE/test/index.html" "$HERE/test/page.mjs" "$OUT/"
# MIDI shim (AU-3 #188): flmidi_test.wasm + midi-shim.ts
MIDI_EMCC_FLAGS=(); for f in "${FLA_EMCC_FLAGS[@]}"; do case "$f" in -sEXPORTED_FUNCTIONS=*) ;; *) MIDI_EMCC_FLAGS+=("$f") ;; esac; done
emcc "${FLA_CLANG_FLAGS[@]}" "${MIDI_EMCC_FLAGS[@]}" \
  -sEXPORTED_FUNCTIONS=_main,_flm_init,_flm_ctl_ptr,_flm_layout_count,_flm_layout_off,_flm_layout_name,_fla_midi_test_done_ptr,_fla_midi_test_result_ptr,_fla_midi_test_phase_ptr,_fla_midi_test_go_ptr \
  -I"$HERE/src" "$HERE/src/flmidi.c" "$HERE/src/flmidi_winmm.c" "$HERE/test/flmidi_test.c" -o "$OUT/flmidi_test.js"
"$ROOT/node_modules/.bin/tsc" --target es2022 --module es2022 --moduleResolution bundler --skipLibCheck \
  --lib es2022,dom,dom.iterable --outDir "$OUT/js" --rootDir "$ROOT/src/runtime" --noEmit false --isolatedModules \
  --strict --ignoreConfig "$ROOT/src/runtime/midi-layout.ts" "$ROOT/src/runtime/midi-shim.ts"
sed -i 's|from "./midi-layout"|from "./midi-layout.js"|' "$OUT/js/midi-shim.js"
cp "$HERE/test/index_midi.html" "$HERE/test/index_midiprobe.html" "$HERE/test/page_midi.mjs" "$OUT/"
echo "[audio] build OK -> $OUT"
