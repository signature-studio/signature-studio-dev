#!/usr/bin/env bash
# fa_wc_build.sh — fa_route_build.sh の成果物 (work/fa_route) を流用し、oi.flat.ll だけ
#   fa_wc.py instr で書き込み監視を入れて wasm を作る (ICALL-54 #1998)。出力: work/fa_wc/fa_wc.{cjs,wasm}
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ICALL="$HERE/.."
SRC="$ICALL/work/fa_route"
W="$ICALL/work/fa_wc"; mkdir -p "$W"
[ -f "$SRC/oi.flat.ll" ] || { echo "[fa_wc] $SRC/oi.flat.ll が無い: 先に tools/icall/fa_route_build.sh" >&2; exit 2; }
BLK_SHIFTED="$(python3 -c "import json,sys;m=json.load(open(sys.argv[1]));print(hex(m['blk']-0x180000000+0x30000000))" "$ICALL/work/rt_freshair-core/map.json")"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
python3 "$HERE/fa_wc.py" instr "$SRC/oi.flat.ll" "$W/oi.wc.ll"
emcc "$W/oi.wc.ll" "$SRC/oi.simd.c" "$SRC/oi.vex.c" "$SRC/oi.table.c" "$SRC/fa_data.c" "$ICALL/rt/icall_rt.c" "$ICALL/rt/icall_ovr.c" "$ICALL/rt/icall_simd_extra.c" "$HERE/fa_wc_rt.c" \
  -DICALL_BLK=$BLK_SHIFTED -w -O0 -g -ffp-contract=off -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 -sERROR_ON_UNDEFINED_SYMBOLS=0 \
  -sEXPORTED_FUNCTIONS=_ott_run,_ott_xmm0,_ott_data_install,_malloc -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x3c000000)) -Wl,--max-memory=$((0x3c000000)) -o "$W/fa_wc.cjs" 2> "$W/emcc.log" || { grep -v 'warning' "$W/emcc.log" | head; exit 1; }
echo "[fa_wc] OK: $W/fa_wc.cjs"
