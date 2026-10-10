#!/usr/bin/env bash
# dbg_trap.sh <name> <tag>  : profiling-funcs 付きで再ビルドし compare.mjs --v で trap の wasm スタックを出す
set -e
cd "$(dirname "$0")/.."
N=$1; T=${2:-s0}; D=work/$N/$T
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
EXP=$(python3 -c "import json;print(','.join(['_function_'+k for k in json.load(open('$D/sigs.json'))]+['_malloc','_free']))")
emcc -w -O1 --profiling-funcs -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=96MB -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=KhSnap -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry \
  -sEXPORTED_FUNCTIONS=$EXP -sEXPORTED_RUNTIME_METHODS=HEAPU8 -Wl,--no-gc-sections -Ilift $D/final.ll $D/simd.c $D/globals.c $D/stubs.c -o $D/dbg.cjs
node harness/compare.mjs ${4:-work/$N/vec_200_1.bin} $D/dbg.cjs $D/sigs.json --v 2>&1 | head -${3:-14}
