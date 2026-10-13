#!/usr/bin/env bash
# Ghidra ルート: <va>.c → ghidra_to_c.py → emcc → 同一 ctx-fuzz (snapins/harness) で実機 x86 と全バイト突合。
#   bash ghidra_route/build_cmp.sh <gain|haas|gate> [trials] [seed] [fix]
# 前提: work/ghidra/out (DecompEach.java), snapins/work/native_ref (snapins/run_all.sh [1] と同じ cc ビルド)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; KH="$(cd -- "$HERE/.." && pwd)"
N=$1; TR=${2:-1000}; SEED=${3:-7}; FIX=${4:-}
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
CORE="$KH/work/winpkg/HeartCore.core_64"; O="$KH/work/gr/$N"
python3 "$HERE/ghidra_to_c.py" $N "$O" "$KH/work/ghidra/out" "$CORE" ${FIX:+--fix $FIX} >/dev/null
t0=$(date +%s.%N)
emcc -w -O1 -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=incompatible-pointer-types-discards-qualifiers -I"$HERE" -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=96MB -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=KhSnap \
  -sERROR_ON_UNDEFINED_SYMBOLS=0 --no-entry -sEXPORTED_FUNCTIONS=$(python3 -c "import json;print(','.join('_function_'+k for k in json.load(open('$O/sigs.json')))+',_malloc,_free')") \
  -sEXPORTED_RUNTIME_METHODS=HEAPU8 -Wl,--no-gc-sections "$O/$N.c" -o "$O/mod.cjs" 2> "$O/emcc.log" || { echo "EMCC FAIL"; head -20 "$O/emcc.log"; exit 3; }
echo "emcc $(printf '%.1f' $(echo "$(date +%s.%N) - $t0" | bc)) s, wasm $(stat -c %s $O/mod.wasm) B"
VEC="$KH/snapins/work/$N/vec_${TR}_${SEED}.bin"
[ -f "$VEC" ] || "$KH/snapins/work/native_ref" "$CORE" $N $TR $SEED "$VEC"
node "$KH/snapins/harness/compare.mjs" "$VEC" "$O/mod.cjs" "$O/sigs.json" | tail -8
