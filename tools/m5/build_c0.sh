#!/usr/bin/env bash
# M5 (c): try-finally (0x409fe0) + FastMM 再利用 wasm モジュールのビルド
set -euo pipefail
cd "$(dirname "$0")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc -w -O0 -Wno-error=int-conversion -Wno-error=implicit-function-declaration -msimd128 \
  -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=672MB -sSTACK_SIZE=8MB -sGLOBAL_BASE=536870912 \
  -sENVIRONMENT=node -sEXPORTED_RUNTIME_METHODS=HEAPU32,HEAPU16,HEAPF32 \
  -sMODULARIZE=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 --no-entry \
  -Wl,--no-gc-sections \
  -Wl,--export=m5_run_paramcount -Wl,--export=mm_set_cmdline_va \
  -Wl,--export=mm_get_alloc_count -Wl,--export=mm_get_free_count \
  -Wl,--export=GetCommandLineW \
  work/c_main.ll work/m5stubs.c msimd.c mm_harness.c ../shim/src/heap.c ../shim/src/failfast.c ../shim/src/file.c ../shim/src/timer.c ../shim/src/sync.c \
  -o work/m5_c.cjs
