#!/usr/bin/env bash
# CAB-245: Resize/GetBufSize/信号4関数のオラクル (実 DLL vs 自前実装, native + wasm replay)。
# shim_e2e.sh の S10/S11 から呼ばれる。成果は work/resize/ (gitignore)。
set -euo pipefail
cd "$(dirname "$0")"; HERE=$PWD; IPP=$(cd ../.. && pwd); W=$IPP/work/resize; mkdir -p "$W"
DLL=/home/ubuntu/work/analysis/win64/extracted/block24356_PE.bin
CF="-O1 -g -I $IPP/src -ffp-contract=off -fno-fast-math"
IMPL="$HERE/../impl/ipp_resize.c $HERE/../impl/ipp_sig_fill2.c"
gcc $CF -o "$W/resize_oracle" "$HERE/resize_oracle.c" "$IPP/ref/pe_load.c" $IMPL -lm
"$W/resize_oracle" "$DLL" --dump "$W/cases.hash" > "$W/oracle.log" 2>&1
tail -2 "$W/oracle.log"
# wasm replay (native 記録ハッシュとの突合 — 可搬 sin/lround により bit 一致)
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc $CF -DWASM_REPLAY -sENVIRONMENT=node -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1 -sNODERAWFS \
  -lnodefs.js -lnoderawfs.js \
  -o "$W/resize_oracle.wasm.cjs" "$HERE/resize_oracle.c" $IMPL 2> "$W/emcc.log"
node "$W/resize_oracle.wasm.cjs" --replay "$W/cases.hash" > "$W/oracle_wasm.log" 2>&1
tail -1 "$W/oracle_wasm.log"
