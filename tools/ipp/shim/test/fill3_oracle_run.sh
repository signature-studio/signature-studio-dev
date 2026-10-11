#!/usr/bin/env bash
# CAB-262 (IPP-7): 次層 stub 28 関数のオラクル (実 DLL vs 自前実装, native + wasm replay)。
# shim_e2e.sh の S13 から呼ばれる。成果は work/fill7/ (gitignore)。
set -euo pipefail
cd "$(dirname "$0")"; HERE=$PWD; IPP=$(cd ../.. && pwd); W=$IPP/work/fill7; mkdir -p "$W" /tmp/opencode
DLL=/home/ubuntu/work/analysis/win64/extracted/block24356_PE.bin
CF="-O1 -g -I $IPP/src -ffp-contract=off -fno-fast-math"
IMPL="$HERE/../impl/ipp_sig_fill3.c"
gcc $CF -o "$W/fill3_oracle" "$HERE/fill3_oracle.c" "$IPP/ref/pe_load.c" $IMPL -lm
"$W/fill3_oracle" "$DLL" --dump "$W/cases.hash" > "$W/oracle.log" 2>&1
tail -3 "$W/oracle.log"
# wasm replay (native 記録ハッシュとの突合 — bit 一致する関数は mismatch 0)
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc $CF -DWASM_REPLAY -sENVIRONMENT=node -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH=1 -sNODERAWFS \
  -lnodefs.js -lnoderawfs.js \
  -o "$W/fill3_oracle.wasm.cjs" "$HERE/fill3_oracle.c" $IMPL 2> "$W/emcc.log"
node "$W/fill3_oracle.wasm.cjs" --replay "$W/cases.hash" > "$W/oracle_wasm.log" 2>&1
tail -1 "$W/oracle_wasm.log"
