#!/usr/bin/env bash
# membench.c (+ membench2.c) を wasm32 / wasm64 で work/bench/{mem32,mem64,memb2_32,memb2_64}.wasm にビルド
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; OUT="$HERE/../work/bench"; mkdir -p "$OUT"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
for v in 32 64; do
  X=(); [ $v = 64 ] && X=(-sMEMORY64=1)
  emcc -O2 "$HERE/membench.c" -o "$OUT/mem$v.wasm" -sSTANDALONE_WASM=1 --no-entry -sINITIAL_MEMORY=$((320<<20)) -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=1MB "${X[@]}" 2>&1 | grep -v "INFO\|deprecated" || true
  emcc -O2 "$HERE/membench2.c" -o "$OUT/memb2_$v.wasm" -sSTANDALONE_WASM=1 --no-entry -sINITIAL_MEMORY=$((160<<20)) -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=1MB "${X[@]}" 2>&1 | grep -v "INFO\|deprecated" || true
done
ls -la "$OUT"/mem*.wasm
