#!/usr/bin/env bash
# ipp_min.c + 生成表 → work/ipp_min.wasm (JS glue なし standalone wasm)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
mkdir -p "$HERE/work"
mkdir -p /tmp/opencode
IMPL=$(for f in "$HERE"/src/ipp_*.c; do gcc -c -O0 -o /tmp/opencode/_ipp_nm.o "$f" && nm -g --defined-only /tmp/opencode/_ipp_nm.o; done | awk '$2=="T" && $3 ~ /^ipp/ {print "_" $3}' | sort -u | paste -sd, -)
EXPORTS="[$(echo "$IMPL" | sed "s/[^,]*/'&'/g"),'_ipp_lookup','_ipp_table_count','_ipp_table_name','_ipp_table_fn','_ipp_table_impl','_ipp_unimpl_name','_ipp_call0','_malloc','_free']"
OUT="${OUT:-$HERE/work/ipp_min.wasm}"; EXTRA="${EXTRA:-}"   # SIMD 版: EXTRA=-msimd128 OUT=work/ipp_min_simd.wasm
emcc -O2 -ffp-contract=off -fno-fast-math -Wall $EXTRA \
  "$HERE"/src/ipp_*.c "$HERE/src/gen/ipp_table.c" -o "$OUT" \
  -sSTANDALONE_WASM=1 -sEXPORTED_FUNCTIONS="$EXPORTS" -sINITIAL_MEMORY=33554432 -sALLOW_MEMORY_GROWTH=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 -Wl,--no-entry
ls -l "$OUT" | awk '{print $9 " bytes:", $5}'
