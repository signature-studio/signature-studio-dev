#!/usr/bin/env bash
# flapi provider (fl_api_call) を単体 wasm (dist/flprov.{js,wasm}) にビルドする。
#   bash tools/python/provider/build.sh      前提: emsdk (EMSDK_ENV 既定 /opt/emsdk/emsdk_env.sh)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
D="$HERE/../dist"; mkdir -p "$D"
# shellcheck disable=SC1090
source "${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}" >/dev/null 2>&1

python3 "$HERE/gen_provider.py" --check-handlers "$HERE/fl_engine.c"
emcc -O2 -g0 -Wall -Wextra -Wno-unused-parameter -Wno-unused-variable -Wno-unused-but-set-variable \
  "$HERE/fl_dispatch.c" "$HERE/fl_engine.c" "$HERE/gen/fl_table.c" \
  --no-entry -sALLOW_MEMORY_GROWTH -sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=createFlProvider -sENVIRONMENT=web,worker,node \
  -sEXPORTED_FUNCTIONS=_fl_api_call,_fl_engine_reset,_fl_engine_highlight_cb,_fl_engine_channel_count,_fl_engine_midi_out_count,_fl_engine_grid_bit,_fl_engine_display_time,_fl_engine_step_item_probe,_fl_engine_note_enum_probe,_fl_engine_note_enum_out,_malloc,_free \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,UTF8ToString,stringToUTF8,lengthBytesUTF8 \
  -o "$D/flprov.js"
ls -la "$D"/flprov.*
