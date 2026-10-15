#!/usr/bin/env bash
# OTT (M10 最終 IR + helper C) を任意の emcc 構成でビルドする。
#   ott_build.sh <variant> [--opt -O2] [--cflags "..."] [--link-opt -O0] [--ldflags "..."] [--exports min|full] [--gc 0|1] [--lto 0|1] [--pthread 0|1]
# 産物: work/ott/<variant>/ott.mjs (+ ott.wasm) ; ENVIRONMENT=web,worker,node で node/Chrome 共用。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$HERE/../flags.sh"
IN="$WORK/inputs/ott"; SH="$WORK/inputs/shim"
V="$1"; shift
OPT=-O2; LOPT=""; CF=""; LF=""; EXPORTS=min; GC=1; LTO=0; PTHREAD=0
while [ $# -gt 0 ]; do case "$1" in
  --opt) OPT="$2"; shift 2;; --link-opt) LOPT="$2"; shift 2;; --cflags) CF="$2"; shift 2;; --ldflags) LF="$2"; shift 2;;
  --exports) EXPORTS="$2"; shift 2;; --gc) GC="$2"; shift 2;; --lto) LTO="$2"; shift 2;;
  --pthread) PTHREAD="$2"; shift 2;;
  *) echo "unknown $1" >&2; exit 2;; esac; done
OUT="$WORK/ott/$V"; rm -rf "$OUT"; mkdir -p "$OUT/obj"
FL=(); [ "$LTO" = 1 ] && FL+=(-flto)
[ "$PTHREAD" = 1 ] && FL+=(-pthread)
SRCS=("$IN/msimd6.c" "$IN/m6_stubs.c" "$IN/m6_data.c" "$SH/heap.c" "$SH/failfast.c" "$IN/m6_rt.c" "$IN/m6_stubs_hand.c" "$IN/m6_stubs_hand2.c" "$IN/m8_rt.c" "$IN/m9_rt.c" "$IN/m10_boot.c" "$IN/ott_m10.ll")
COMMONC=(-w -Wno-error=int-conversion -Wno-implicit-function-declaration "$OPT" "${FL[@]}" -I"$IN" -I"$SH")
i=0; PIDS=()
for s in "${SRCS[@]}"; do
  o="$OUT/obj/$(printf %02d $i)_$(basename "$s").o"; i=$((i+1))
  # shellcheck disable=SC2086
  emcc -c "${COMMONC[@]}" $CF "$s" -o "$o" &
  PIDS+=($!)
  while [ "$(jobs -rp | wc -l)" -ge 6 ]; do wait -n; done
done
for p in "${PIDS[@]}"; do wait "$p"; done

FULL_EXPORTS=$(python3 - "$HERE/../../m6/m6_build.sh" <<'PY'
import re, sys
src=open(sys.argv[1]).read()
print(re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', src).group(1))
PY
)
MIN_EXPORTS=_function_18011d400,_function_180120af0,_function_180120800,_function_18011ec20,_m6_data_install
[ "$EXPORTS" = full ] && EXP="$FULL_EXPORTS" || EXP="$MIN_EXPORTS"
GCF=-Wl,--gc-sections; [ "$GC" = 0 ] && GCF=-Wl,--no-gc-sections
INITMEM=$((0x36000000)); LOPT="${LOPT:-$OPT}"
# shellcheck disable=SC2086
emcc -w "$OUT"/obj/*.o "$LOPT" "${FL[@]}" -o "$OUT/ott.mjs" -sEXPORT_ES6=1 \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 -sASSERTIONS=0 \
  -sENVIRONMENT=web,worker,node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=0 -sEXPORTED_FUNCTIONS="$EXP" \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 --no-entry \
  $GCF -sINITIAL_MEMORY=$INITMEM -sMAXIMUM_MEMORY=$INITMEM -Wl,--initial-memory=$INITMEM -Wl,--max-memory=$INITMEM $LF 2>"$OUT/link.log" || { tail -20 "$OUT/link.log"; exit 1; }
ls -l "$OUT/ott.wasm" | awk '{print "[ott_build] '"$V"' wasm bytes:", $5}'
