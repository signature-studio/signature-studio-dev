#!/usr/bin/env bash
# build_h2_lb.sh — HB-H2 (CAB-91): lift 済み OTT (入口拡張版, tools/ott/entry 成果) を lowbase (LB_BASE=0x10000)
#   の hostbridge module としてビルドする。旧 surrogate (poc/plugin_ott_entry.c) は使わない。
#   入力 (全て読取のみ): tools/ott/lift/x64c.py, tools/ott/lift/data_gen.py, tools/ott/rt/*,
#     tools/ott/entry/{entry_roots.py}, tools/hostbridge/lowbase/{lb_layout.py,x64c/lb_x64c.py,x64c/lb_data_gen.py},
#     tools/hostbridge/poc/hb_lib.js, tools/ott/work/entrylift/cov_entry.json (entry_e2e.sh 産物)
#   出力: tools/hostbridge/h2/work/ott_h2.cjs (+.wasm)
#   env: LB_BASE(0x10000) LB_INIT_MIB(16) LB_MAX_MIB(64)
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
HB="$(cd -- "$HERE/.." && pwd)"; T="$HB/.."
OTT="$T/ott"; LB="$HB/lowbase"; POC="$HB/poc"
DLL=/home/ubuntu/work/analysis/plugins/ott/binaries/OTT_vst2_win64.dll
LB_BASE="${LB_BASE:-0x10000}"; LB_INIT_MIB="${LB_INIT_MIB:-16}"; LB_MAX_MIB="${LB_MAX_MIB:-64}"
OUT="$HERE/work"; mkdir -p "$OUT"

COV="$OTT/work/entrylift/cov_entry.json"
[ -f "$COV" ] || { echo "[build_h2_lb] $COV 無し: 先に bash tools/ott/entry/entry_e2e.sh" >&2; exit 1; }
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1

echo "[build_h2_lb] [1/4] layout (LB_BASE=$LB_BASE)"
eval "$(python3 "$LB/lb_layout.py" --base "$LB_BASE" --init-mib "$LB_INIT_MIB" --max-mib "$LB_MAX_MIB")"

echo "[build_h2_lb] [2/4] lift (x64c, 入口拡張 entries を lowbase shift で再利用)"
python3 "$OTT/entry/entry_roots.py" "$OTT/ref/cov_all.json" "$COV" "$OUT/entries.json"
python3 "$LB/x64c/lb_x64c.py" --base "$LB_BASE" -- \
  --pe "$DLL" --entries "$OUT/entries.json" --out "$OUT" --closure 3 \
  --override 1801c8c00=ovr_handle_error_d --override 1801c8cb8=ovr_handle_error_f \
  --override 1801a9a6c=ovr_sqrt_d --override 1801a9b38=ovr_sqrt_f \
  --override 180120ff0=ovr_editor_null \
  --override 1802f8000=ovr_am_shim_hb | tail -2 | cut -c1-200
python3 "$LB/x64c/lb_data_gen.py" "$DLL" "$OUT/ott_data.c" "$OUT/lift_meta.json" "$LB_BASE" | tail -1

echo "[build_h2_lb] [3/4] emcc (module glue = vst_module_entry.c + hb_rt_entry.c)"
EXPORTS=_ott_run,_ott_xmm0,_ott_set_stackarg,_ott_data_install,_ott_rget,_malloc,_VSTPluginMain,_hb_icall,_hb_plugin_init,_hb_scratch
emcc -O1 -ffp-contract=off -fno-fast-math -I"$OTT/rt" -DLB_BASE=${LB_BASE}u -DLB_ARENA_ADDR=${LB_ARENA}u \
  "$OUT/ott_lifted.c" "$OUT/ott_data.c" "$LB/x64c/rt/ott_cpu.c" "$OTT/rt/ott_glue.c" "$OTT/rt/ott_ovr.c" \
  "$HERE/hb_rt_entry.c" "$HERE/vst_module_entry.c" \
  --js-library "$POC/hb_lib.js" \
  -w -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=2MB -sGLOBAL_BASE=$LB_GLOBAL_BASE \
  -sENVIRONMENT=node,web,worker -sMODULARIZE=1 -sEXPORT_NAME=createModule -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=$EXPORTS -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32,HEAPF64 \
  -sINITIAL_MEMORY=$LB_INIT -sMAXIMUM_MEMORY=$LB_MAX \
  -o "$OUT/ott_h2.cjs" 2>&1 | tail -6

echo "[build_h2_lb] [4/4] mini VST2 host (poc/host_vst2.c, freestanding wasm32)"
/opt/emsdk/upstream/bin/clang --target=wasm32 -O2 -nostdlib -ffreestanding -fno-builtin -I "$POC" \
  -Wl,--no-entry -Wl,--export-dynamic -Wl,--export-table -Wl,--allow-undefined -Wl,-z,stack-size=262144 -Wl,--initial-memory=2097152 \
  "$POC/host_vst2.c" -o "$OUT/host_vst2.wasm"
echo "[build_h2_lb] OK: $OUT/ott_h2.cjs (base=$LB_BASE arena=0x$(printf %x $LB_ARENA) gb=0x$(printf %x $LB_GLOBAL_BASE) init=${LB_INIT_MIB}MiB max=${LB_MAX_MIB}MiB)"
