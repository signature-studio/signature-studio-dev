#!/usr/bin/env bash
# lift_build.sh: DLL 機械語 → (x64c.py) C → emcc → wasm.  RetDec 不要。
#   env: LIFT_ENTRIES (default work/entries.json), LIFT_OUT (default work/lift), LIFT_CLOSURE (default 0), LIFT_NAME (default ottl)
set -euo pipefail
OTT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
DLL=/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
ENT="${LIFT_ENTRIES:-$OTT/work/entries.json}"
OUT="${LIFT_OUT:-$OTT/work/lift}"
NAME="${LIFT_NAME:-ottl}"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
mkdir -p "$OUT"
python3 "$OTT/lift/x64c.py" --pe "$DLL" --entries "$ENT" --out "$OUT" --closure "${LIFT_CLOSURE:-2}" \
  --override 1801c8c00=ovr_handle_error_d --override 1801c8cb8=ovr_handle_error_f --override 1801a9a6c=ovr_sqrt_d --override 1801a9b38=ovr_sqrt_f
python3 "$OTT/lift/data_gen.py" "$DLL" "$OUT/ott_data.c" "$OUT/lift_meta.json" >/dev/null
EXPORTS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc
emcc -O1 -ffp-contract=off -fno-fast-math -I"$OTT/rt" ${LIFT_CFLAGS:-} \
  "$OUT/ott_lifted.c" "$OUT/ott_data.c" "$OTT/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=268435456 \
  -sENVIRONMENT=node -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -Wl,--initial-memory=$((0x36000000)) -Wl,--max-memory=$((0x36000000)) \
  -o "$OUT/$NAME.cjs" 2>&1 | tail -20
echo "[lift_build] OK: $OUT/$NAME.cjs"
