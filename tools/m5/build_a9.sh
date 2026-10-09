#!/usr/bin/env bash
# M5 [A9] pass 実証: M3 の mm closure (ft7.ll 677 define, 残存 187→A9 后) emcc 通過試験
set -euo pipefail
cd "$(dirname "$0")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc -w -O1 -msimd128 -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=672MB -sSTACK_SIZE=8MB -sGLOBAL_BASE=536870912 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 --no-entry \
  -Wl,--no-gc-sections \
  work/a9_ft7.ll ../shim/src/heap.c ../shim/src/failfast.c -o work/a9_ft7.cjs
echo "[a9] built work/a9_ft7.cjs"
