#!/usr/bin/env bash
# shim (loader + 420 名表 + thunk) + ipp 実装 -> standalone wasm (work/shim/ipp_shim.wasm; EXTRA=-msimd128 OUT=... で SIMD 版)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; IPP="$(dirname "$HERE")"; W="$IPP/work/shim"; mkdir -p "$W"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
python3 "$HERE/gen_shim.py" > "$W/gen_shim.log"
OUT="${OUT:-$W/ipp_shim.wasm}"; EXTRA="${EXTRA:-}"
EXPORTS="['_ipp_shim_find','_ipp_shim_cookie','_ipp_shim_getproc','_ipp_shim_load_library_w','_ipp_shim_get_proc_address','_ipp_shim_owns','_ipp_shim_dispatch','_ipp_shim_set_mode','_ipp_shim_get_mode','_ipp_shim_calls','_ipp_shim_stub_calls_total','_ipp_shim_stub_distinct','_ipp_shim_stub_first','_ipp_shim_last_stub','_ipp_shim_reset','_ipp_shim_table_count','_malloc','_free']"
emcc -O2 -DNDEBUG -DPFFFT_ENABLE_WASM -ffp-contract=off -fno-fast-math -Wall -Wno-unused-function -Wno-misleading-indentation $EXTRA -I"$IPP/src" \
  "$IPP"/src/ipp_*.c "$HERE"/fft/*.c "$HERE"/fft/pffft/*.c "$HERE/src/ipp_shim.c" "$HERE/gen/ipp_shim_tab.c" $(ls "$HERE"/impl/*.c 2>/dev/null || true) -o "$OUT" \
  -sSTANDALONE_WASM=1 -sEXPORTED_FUNCTIONS="$EXPORTS" -sINITIAL_MEMORY=33554432 -sALLOW_MEMORY_GROWTH=1 -sERROR_ON_UNDEFINED_SYMBOLS=1 -Wl,--no-entry
ls -l "$OUT" | awk '{print $9 " bytes:", $5}'
