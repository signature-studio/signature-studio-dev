#!/usr/bin/env bash
# M5 (a): SSE 純計算 2 本の wasm ビルド (a1: waveshaper / a2: distortion)
set -euo pipefail
cd "$(dirname "$0")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
COMMON=(-w -O1 -Wno-error=int-conversion -Wno-error=implicit-function-declaration
  -msimd128
  -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=672MB -sSTACK_SIZE=8MB -sGLOBAL_BASE=536870912
  -sENVIRONMENT=node -sEXPORTED_RUNTIME_METHODS=HEAPU32,HEAPF32
  -sMODULARIZE=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 --no-entry
  -Wl,--no-gc-sections)
# (a1) — C8 で xmm 引数 (k) を linear memory VA 0x1000100 から取る構成
emcc "${COMMON[@]}" work/m5_a1.ll msimd_a1.c \
  -Wl,--export=function_6a7540 \
  -o work/m5_a1.js && mv work/m5_a1.js work/m5_a1.cjs
# (a2) — DLL 内定数 (g=2.0f x4) を a2g.c で供給
emcc "${COMMON[@]}" work/m5_a2.ll msimd_a2.c work/a2g.c \
  -Wl,--export=function_6a2fb0 \
  -o work/m5_a2.js && mv work/m5_a2.js work/m5_a2.cjs
