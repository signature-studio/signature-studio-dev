#!/usr/bin/env bash
# build_x64c.sh — OTT (tools/ott の x64c 自作 lifter) を低位 base・小 memory で wasm 化する.
#   env: LB_BASE (既定 0x10000) LB_INIT_MIB (16) LB_MAX_MIB (64) LB_PREFIX ('') LB_OUT (work/x64c_<base>) LB_NAME (ottl) LB_DLL
#   出力: $LB_OUT/$LB_NAME.cjs (+.wasm), layout.sh, lift_meta.json.   tools/ott は読取専用 (lifter 本体を import して使うのみ).
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; LB="$HERE/.."; OTT="$LB/../../ott"
LB_BASE="${LB_BASE:-0x10000}"; LB_INIT_MIB="${LB_INIT_MIB:-16}"; LB_MAX_MIB="${LB_MAX_MIB:-64}"; LB_PREFIX="${LB_PREFIX:-}"
DLL="${LB_DLL:-/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll}"
OUT="${LB_OUT:-$LB/work/x64c_$LB_BASE}"; NAME="${LB_NAME:-ottl}"
mkdir -p "$OUT"
eval "$(python3 "$LB/lb_layout.py" --base "$LB_BASE" --init-mib "$LB_INIT_MIB" --max-mib "$LB_MAX_MIB")"
echo "LB_BASE=$LB_BASE" > /dev/null
python3 "$LB/lb_layout.py" --base "$LB_BASE" --init-mib "$LB_INIT_MIB" --max-mib "$LB_MAX_MIB" > "$OUT/layout.sh"
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
ENT="$OUT/entries.json"
python3 "$OTT/lift/mkentries.py" "$OTT/ref/cov_all.json" "$ENT"
python3 "$HERE/lb_x64c.py" --base "$LB_BASE" ${LB_PREFIX:+--prefix "$LB_PREFIX"} -- --pe "$DLL" --entries "$ENT" --out "$OUT" --closure 2 \
  --override 1801c8c00=ovr_handle_error_d --override 1801c8cb8=ovr_handle_error_f --override 1801a9a6c=ovr_sqrt_d --override 1801a9b38=ovr_sqrt_f | tail -3 | cut -c1-160
python3 "$HERE/lb_data_gen.py" "$DLL" "$OUT/ott_data.c" "$OUT/lift_meta.json" "$LB_BASE" | tail -1
EXPORTS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc,_ott_alog_addr
emcc -O1 -ffp-contract=off -fno-fast-math -I"$OTT/rt" -DLB_IMG_BASE=$LB_BASE \
  "$OUT/ott_lifted.c" "$OUT/ott_data.c" "$HERE/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=$LB_GLOBAL_BASE \
  -sENVIRONMENT=node,web,worker -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -sINITIAL_MEMORY=$LB_INIT -sMAXIMUM_MEMORY=$LB_MAX \
  -o "$OUT/$NAME.cjs" 2>&1 | tail -20
echo "[build_x64c] OK: $OUT/$NAME.cjs  (base=$LB_BASE init=$((LB_INIT>>20))MiB max=$((LB_MAX>>20))MiB)"
