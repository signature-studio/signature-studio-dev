#!/usr/bin/env bash
# M11 boot closure (FLEngine 部分 lift, 7361 関数 / x86 1.42MB) を任意 -O で wasm 化 (サイズ/compile 実験用)。
#   m11_build.sh <variant> <opt> [extra emcc flags]   → work/m11/<variant>/m11.wasm (+ build.log, 所要秒)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../flags.sh"
IN="$WORK/inputs/m11"; SH="$WORK/inputs/shim"
V="$1"; OPT="$2"; shift 2
OUT="$WORK/m11/$V"; rm -rf "$OUT"; mkdir -p "$OUT/obj" "$OUT/tmp"; export TMPDIR="$OUT/tmp"
s=$(date +%s.%N)
SRCS=("$IN/msimd11.c" "$IN/m11_fwd.c" "$IN/m11_winstubs.c" "$IN/m11_fnstubs.c" "$IN/m11_rt.c" "$IN/m11_data.c" "$SH/heap.c" "$SH/failfast.c" "$SH/file.c" "$SH/timer.c" "$SH/sync.c" "$IN/boot_final2.ll")
i=0
for src in "${SRCS[@]}"; do
  o="$OUT/obj/$(printf %02d $i)_$(basename "$src").o"; i=$((i+1))
  emcc -c -w -Wno-error=int-conversion -Wno-implicit-function-declaration "$OPT" -I"$IN" -I"$SH" "$@" "$src" -o "$o" &
  while [ "$(jobs -rp | wc -l)" -ge 4 ]; do wait -n; done
done
wait
e1=$(date +%s.%N)
emcc -w "$OUT"/obj/*.o "$OPT" "$@" -o "$OUT/m11.js" \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=$((0x10000000)) -sASSERTIONS=0 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=m11create -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=0 \
  --no-entry -Wl,--export-all -sEXPORTED_FUNCTIONS=_m11_boot_enter,_entry_point \
  -Wl,--initial-memory=$((0x12000000)) -Wl,--max-memory=$((0x72000000)) 2>"$OUT/link.log" || { tail -5 "$OUT/link.log"; exit 1; }
e2=$(date +%s.%N)
printf '{"variant":"%s","opt":"%s","extra":"%s","wasmBytes":%s,"compileSec":%.1f,"linkSec":%.1f}\n' "$V" "$OPT" "$*" "$(stat -c %s "$OUT/m11.wasm")" "$(echo "$e1 - $s" | bc)" "$(echo "$e2 - $e1" | bc)" | tee "$OUT/build.json"
rm -rf "$OUT/obj" "$OUT/tmp"
