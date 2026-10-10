#!/usr/bin/env bash
# OTT DSP (M10 lifted IR) を wasm32 / wasm64(Memory64) の 2 通りに同一ソース・同一フラグ(-O2)でビルドし
# work/bench/{ott32,ott64}.wasm を作る。入力は tools/m10/work/ott_m10.ll (読取のみ)。
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
OUT="$HERE/../work/bench"; mkdir -p "$OUT"
M6="$ROOT/tools/m6"; M8="$ROOT/tools/m8"; M9="$ROOT/tools/m9"; M10="$ROOT/tools/m10"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export TMPDIR="$OUT/tmp"; mkdir -p "$TMPDIR"
OPT="${OTT_OPT:--O2}"
EXPORTS=$(python3 - "$M6/m6_build.sh" <<'PY'
import re,sys
print(re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', open(sys.argv[1]).read()).group(1))
PY
)
sed 's/^target datalayout = .*/target datalayout = "e-m:e-p:64:64-p10:8:8-p20:8:8-i64:64-i128:128-n32:64-S128-ni:1:10:20"/' "$M10/work/ott_m10.ll" > "$OUT/ott_m10_p64.ll"
cd "$M6"
build() { # $1=name $2=ir $3..=extra
  local name=$1 ir=$2; shift 2
  emcc msimd6.c work/m6_stubs.c work/m6_data.c ../shim/src/heap.c ../shim/src/failfast.c m6_rt.c work/m6_stubs_hand.c work/m6_stubs_hand2.c \
    "$M8/m8_rt.c" "$M9/m9_rt.c" "$M10/m10_boot.c" "$ir" -o "$OUT/$name.js" \
    -w -Wno-error=int-conversion -Wno-implicit-function-declaration $OPT \
    -sALLOW_MEMORY_GROWTH=0 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
    -sENVIRONMENT=web,worker,node -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXPORTED_FUNCTIONS="$EXPORTS" --no-entry \
    -Wl,--no-gc-sections -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) "$@" 2>&1 | grep -v "^warning\|^$" | tail -3 || true
  ls -la "$OUT/$name.wasm"
}
build ott32 "$M10/work/ott_m10.ll" &
build ott64 "$OUT/ott_m10_p64.ll" -sMEMORY64=1 &
wait
