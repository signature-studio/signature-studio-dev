#!/usr/bin/env bash
# build_bal_lb.sh — multi-load 用の 2 つ目の module (Fruity Balance mix kernel + VST2 facade) を低位・小 memory でビルド.
#   入力: tools/plugins/work/balance/{k.final.ll,k_simd.c} (t0_balance の lift 成果; 無ければ bash tools/plugins/lift/t0_balance/t0_e2e.sh)
#   kernel は PE image を読まない → V-shift 不要 (image 敷設なし = 配置コスト 0). LB_GLOBAL_BASE は 64KiB.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"; LB="$HERE/.."; T="$LB/../.."
W="$T/plugins/work/balance"; HB="$T/hostbridge"
OUT="${LB_OUT:-$LB/work/bal_lb}"; mkdir -p "$OUT"
[ -f "$W/k.final.ll" ] && [ -f "$W/k_simd.c" ] || { echo "$W/k.final.ll 無し: bash tools/plugins/lift/t0_balance/t0_e2e.sh" >&2; exit 1; }
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
emcc "$W/k.final.ll" "$W/k_simd.c" "$LB/multi/plugin_bal_entry.c" --js-library "$HB/poc/hb_lib.js" -I "$HB/poc" -I "$T/plugins/lift/passes" \
  -o "$OUT/bal_hb.tmp.cjs" -w -Wno-error=int-conversion -Wno-implicit-function-declaration -fno-strict-aliasing -frounding-math -fno-fast-math -O1 -msimd128 \
  -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=512KB -sGLOBAL_BASE=$((0x10000)) -sINITIAL_MEMORY=$((4<<20)) -sMAXIMUM_MEMORY=$((16<<20)) \
  -sENVIRONMENT=node,web,worker -sMODULARIZE=1 -sEXPORT_NAME=createModule -sERROR_ON_UNDEFINED_SYMBOLS=0 -sEXIT_RUNTIME=1 \
  -sEXPORTED_FUNCTIONS=_VSTPluginMain,_hb_icall,_hb_plugin_init,_hb_scratch,_function_5dee90,_function_5df940 -sEXPORTED_RUNTIME_METHODS=HEAPU8,HEAPU32,HEAPF32 -Wl,--no-gc-sections 2>&1 | tail -5
mv "$OUT/bal_hb.tmp.cjs" "$OUT/bal_hb.cjs"; mv "$OUT/bal_hb.tmp.wasm" "$OUT/bal_hb.wasm"; sed -i 's/bal_hb.tmp.wasm/bal_hb.wasm/g' "$OUT/bal_hb.cjs"
echo "[build_bal_lb] OK: $OUT/bal_hb.cjs"
