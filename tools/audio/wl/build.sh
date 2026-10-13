#!/usr/bin/env bash
# AU-8 (#194): worklet 直走行版 (fla_wl) を build/web/ に出力する。ring 版 (fla_test) は ../build.sh が同じ build/web/ に出す。
# 使い方: bash tools/audio/wl/build.sh
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
OUT="$HERE/../build/web"
EMSDK="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
if [ -f "$EMSDK" ]; then set +u; . "$EMSDK" >/dev/null 2>&1 || true; set -u; fi
command -v emcc >/dev/null || { echo "[wl] emcc not found" >&2; exit 1; }
mkdir -p "$OUT"
# -sAUDIO_WORKLET=1 は -sWASM_WORKERS=1 必須。ring 版 (-pthread/PROXY_TO_PTHREAD) と違い main thread で動かす (worklet が mixer を直接走らせるため producer スレッド無し)。
emcc -Wall -Wextra -Wno-unused-parameter -O2 -fno-strict-aliasing \
  -sAUDIO_WORKLET=1 -sWASM_WORKERS=1 -sENVIRONMENT=web,worker,worklet \
  -sINITIAL_MEMORY=67108864 -sSTACK_SIZE=1048576 -sASSERTIONS=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 \
  -sEXPORTED_FUNCTIONS=_main,_fla_wl_cap_out,_fla_wl_cap_in,_fla_wl_capn,_fla_wl_done_ptr,_fla_wl_result_ptr \
  -sEXPORTED_RUNTIME_METHODS=wasmMemory,UTF8ToString \
  "$HERE/fla_wl.c" -o "$OUT/fla_wl.js"
cp "$HERE/wl.html" "$HERE/wl.mjs" "$OUT/"
echo "[wl] build OK -> $OUT/fla_wl.js"
