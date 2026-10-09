#!/usr/bin/env bash
# M5 (b): FastMM → shim heap 結合 wasm のビルド (tools/m5 配下)
set -euo pipefail
cd "$(dirname "$0")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc -w -O1 -Wno-error=int-conversion -Wno-error=implicit-function-declaration -msimd128 \
  -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=672MB -sSTACK_SIZE=8MB -sGLOBAL_BASE=536870912 \
  -sENVIRONMENT=node -sEXPORTED_RUNTIME_METHODS=HEAPU32,HEAPF32 -sMODULARIZE=1 -sEXPORT_NAME=createModule5 \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 --no-entry \
  -Wl,--no-gc-sections \
  -Wl,--export=mm_alloc -Wl,--export=mm_release \
  -Wl,--export=mm_test_1000 -Wl,--export=mm_get_alloc_count \
  -Wl,--export=mm_get_free_count -Wl,--export=mm_failfast_double_free \
  -Wl,--export=mm_test_underflow_leak \
  work/m5_b.ll msimd.c mm_harness.c ../shim/src/heap.c ../shim/src/failfast.c ../shim/src/file.c ../shim/src/timer.c ../shim/src/sync.c \
  -o work/m5_b.js
mv work/m5_b.js work/m5_b.cjs
