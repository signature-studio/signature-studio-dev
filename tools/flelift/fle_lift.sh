#!/usr/bin/env bash
# fle_lift.sh — FLEngine_x64.dll 全体を x64c (flelift fork) で lift → C → emcc → wasm (1 コマンド)。
#   env: FLE_ENTRIES (default work/fle_entries.json), FLE_OUT (default work/lift), FLE_NAME (default flel)
#   entries が無ければコミット済み fle_entries.json (M11 closure F 集合 7,421 roots) から生成。
#   env: EMSDK_ENV (emsdk_env.sh の場所, default は [EMSDK] の emsdk_env.sh)
#   前提: python3 (capstone, pefile), emsdk 6.0.12
set -euo pipefail
FLE="$(cd -- "$(dirname -- "$0")" && pwd)"
source "$FLE/../shared/env.sh"
PE="${FLE_PE:-$FL_WIN64_DIR/extracted/block00031_PE.bin}"
export FLE_PE="$PE"
ENT="${FLE_ENTRIES:-$FLE/work/fle_entries.json}"
OUT="${FLE_OUT:-$FLE/work/lift}"
NAME="${FLE_NAME:-flel}"
EMSDK_SH="${EMSDK_ENV:-/opt/emsdk/emsdk_env.sh}"
[ -f "$EMSDK_SH" ] || { echo "[fle_lift] emsdk_env.sh not found: $EMSDK_SH (EMSDK_ENV で指定)" >&2; exit 2; }
source "$EMSDK_SH" >/dev/null 2>&1
mkdir -p "$OUT" "$(dirname -- "$ENT")"
export TMPDIR="$OUT/tmp"; mkdir -p "$TMPDIR"
[ -f "$ENT" ] || python3 -c "import json; json.dump(json.load(open('$FLE/fle_entries.json')), open('$ENT','w'))"
T0=$(date +%s)
python3 "$FLE/x64c.py" --pe "$PE" --entries "$ENT" --out "$OUT" --closure 0 \
  --img 0x400000 --shift 0 --img-size 0x18c0000 --impbase 0x1D80000
T1=$(date +%s)
echo "[fle_lift] lift done in $((T1-T0))s"
python3 "$FLE/fle_data_gen.py" "$PE" "$OUT/fle_data.c" "$OUT/lift_meta.json"
EXPORTS=_fle_run,_fle_xmm0,_fle_xmm1,_fle_rget,_fle_mget,_fle_set_stackarg,_fle_data_install,_fle_init,_fle_reset,_malloc
emcc -O0 -ffp-contract=off -fno-fast-math -I"$FLE/rt" \
  "$OUT/fle_lifted.c" "$OUT/fle_data.c" "$FLE/rt/fle_cpu.c" "$FLE/rt/fle_glue.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=8MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$OUT/$NAME.cjs" 2>&1 | tail -20
T2=$(date +%s)
echo "[fle_lift] OK: $OUT/$NAME.cjs (emcc $((T2-T1))s, total $((T2-T0))s)"
ls -la "$OUT/$NAME.wasm" "$OUT/$NAME.cjs" | awk '{print $9, $5}'
