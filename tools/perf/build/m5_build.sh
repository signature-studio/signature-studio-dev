#!/usr/bin/env bash
# M5 純計算カーネル (a1 waveshaper / a2 distortion; FLEngine 実機能由来 SSE) を emcc 構成別にビルド。
#   m5_build.sh <kind a1|a2> <variant> <opt> [extra flags...]   → work/<kind>/<variant>/<kind>.mjs
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../flags.sh"
IN="$WORK/inputs/m5"
K="$1"; V="$2"; OPT="$3"; shift 3
OUT="$WORK/$K/$V"; rm -rf "$OUT"; mkdir -p "$OUT"
if [ "$K" = a1 ]; then SRC=("$IN/m5_a1.ll" "$IN/msimd_a1.c"); EXP=_function_6a7540
else SRC=("$IN/m5_a2.ll" "$IN/msimd_a2.c" "$IN/a2g.c"); EXP=_function_6a2fb0; fi
emcc -w "${SRC[@]}" "$OPT" "$@" -I"$IN" -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=672MB -sSTACK_SIZE=8MB -sGLOBAL_BASE=536870912 -sASSERTIONS=0 \
  -sENVIRONMENT=web,worker,node -sMODULARIZE=1 -sEXPORT_ES6=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=0 -sEXPORTED_FUNCTIONS=$EXP \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32 --no-entry -Wl,--gc-sections \
  -o "$OUT/$K.mjs" 2>"$OUT/link.log" || { tail "$OUT/link.log"; exit 1; }
echo "[m5_build] $K/$V $(stat -c %s "$OUT/$K.wasm") bytes"
