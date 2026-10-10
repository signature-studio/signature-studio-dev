#!/usr/bin/env bash
# lift 済み kernel IR + SIMD helper C → wasm (node 用 cjs)。
# usage: build_wasm.sh <work dir> <name> <exports csv>
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
W="$1"; N="$2"; EXPORTS="$3"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
CF="-w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing -frounding-math -fno-fast-math -O1 -msimd128"
emcc -c "$W/$N.final.ll" -o "$W/$N.ll.o" $CF
emcc -c "$W/${N}_simd.c" -o "$W/$N.simd.o" $CF -I"$HERE/../passes"
EXP="$(echo "$EXPORTS" | sed 's/[^,]\+/_&/g')"
emcc "$W/$N.ll.o" "$W/$N.simd.o" -o "$W/$N.cjs" -O1 \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=1MB -sGLOBAL_BASE=$((0x10000000)) -sINITIAL_MEMORY=$((0x12000000)) \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=lifted -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=0 --no-entry \
  -sEXPORTED_FUNCTIONS="$EXP" -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPF32,HEAP32 2> "$W/$N.link.log" || { tail -20 "$W/$N.link.log"; exit 1; }
echo "[build] OK $W/$N.cjs ($(wc -c < "$W/$N.wasm") B wasm), warnings: $(grep -c warning "$W/$N.link.log" || true)"
