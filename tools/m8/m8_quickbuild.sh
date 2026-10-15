#!/usr/bin/env bash
# m8_quickbuild.sh: m7_build 相当に ir8 前処理 + m8_rt.c を追加した高速 build (実験用。
# 整備品は m8_build.sh)。入力 IR は $1 (既定 work/ott_vf0.ll)、出力は work/ott_m8.cjs。
set -euo pipefail
M8="$(cd -- "$(dirname -- "$0")" && pwd)"
M6="$M8/../m6"
cd "$M6"
source ../m1/flags.sh 2>/dev/null || true
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
mkdir -p "$M8/work"
MSIMD_SRC="${MSIMD:-$M6/msimd6.c}"
IN=${1:-$M8/work/ott_vf0.ll}
case "$IN" in /*) ;; *) IN="$M8/$IN";; esac
STACK=8MB
GLOBAL_BASE=268435456
INITMEM=$((0x36000000))
MAXMEM=$((0x36000000))
EXPORTS=$(python3 - <<'PYEOF'
import re
src=open('m6_build.sh').read()
m=re.search(r'-sEXPORTED_FUNCTIONS=(\S+)', src)
print(m.group(1))
PYEOF
)
emcc "$MSIMD_SRC" work/m6_stubs.c work/m6_data.c ../shim/src/heap.c ../shim/src/failfast.c m6_rt.c work/m6_stubs_hand.c work/m6_stubs_hand2.c \
  "$M8/m8_rt.c" \
  "$IN" \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAP32,HEAPF64 \
  -o "$M8/work/ott_m8.cjs.tmp" \
  -w -Wno-error=int-conversion -Wno-implicit-function-declaration \
  -O0 -g1 -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=$STACK -sGLOBAL_BASE=$GLOBAL_BASE \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 -sEXPORTED_FUNCTIONS=$EXPORTS \
  -Wl,--no-gc-sections \
  -Wl,--initial-memory=$INITMEM \
  -Wl,--max-memory=$MAXMEM 2>&1 | tee "$M8/work/build_m8.log" | tail -3
mv "$M8/work/ott_m8.cjs.tmp" "$M8/work/ott_m8.cjs"
echo "[m8_quickbuild] OK: m8/work/ott_m8.cjs (input: $IN)"
